"""Offline real-SDK smoke test. Synthetic vectors only, temporary storage only."""

from contextlib import ExitStack
from dataclasses import replace
from importlib.metadata import version
import json
import os
from pathlib import Path
import resource
import socket
import subprocess
import sys
import tempfile
from unittest.mock import patch

from .config import IndexConfig,REPO_ROOT,load_environment


def peak_mib():
    scale=1024**2 if sys.platform=='darwin' else 1024
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/scale,2)


def synthetic_rows():
    return [{'chunk_id':key,'text':text,'source':source,'document_id':'synthetic:'+key,
             'title':key,'source_url':'https://example.invalid/'+key,'content_type':'synthetic',
             'chunk_index':0} for key,text,source in [
        ('alpha','Synthetic DarGlobal document.','darglobal'),
        ('beta','Synthetic Wasalt document. نص عربي','wasalt'),
        ('gamma','Another synthetic DarGlobal document.','darglobal')]]


def synthetic_vectors():
    return [[1.0,0.0]+[0.0]*1534,[0.0,1.0]+[0.0]*1534,[0.8,0.2]+[0.0]*1534]


def phase(storage,create):
    """Run in a fresh child, guarding SDK initialization and every DB operation."""
    if storage.resolve().is_relative_to((REPO_ROOT/'artifacts').resolve()):
        raise ValueError('Smoke test refuses all production artifact directories')
    attempted=[]

    def no_network(*args,**kwargs):
        attempted.append('blocked')
        raise AssertionError('Network is forbidden during local integration verification')

    before=peak_mib()
    with ExitStack() as guards:
        guards.enter_context(patch.dict(os.environ,{'OTEL_SDK_DISABLED':'true','HF_HUB_OFFLINE':'1',
                                                    'TRANSFORMERS_OFFLINE':'1','ANONYMIZED_TELEMETRY':'False'}))
        for target in ('socket.socket.connect','socket.socket.connect_ex','socket.create_connection','socket.getaddrinfo'):
            guards.enter_context(patch(target,side_effect=no_network))
        import httpx
        import requests
        guards.enter_context(patch.object(httpx.Client,'send',side_effect=no_network))
        guards.enter_context(patch.object(httpx.AsyncClient,'send',side_effect=no_network))
        guards.enter_context(patch.object(requests.sessions.Session,'request',side_effect=no_network))

        from .embeddings import EmbeddingClient
        environment=load_environment()
        real_config=IndexConfig.from_env()
        if not environment['api_key_configured']:
            raise ValueError('OPENAI_API_KEY is missing; cannot verify real client initialization')
        embedding=EmbeddingClient(real_config)
        assert embedding.client.max_retries==0
        embedding.client.close()
        after_openai=peak_mib()

        from .vector_store import ChromaStore,identity
        from chromadb.errors import DuplicateIDError,InvalidArgumentError
        after_import=peak_mib()
        config=replace(real_config,storage_path=storage,collection='checkpoint_19a_synthetic',expected_chunks=3)
        if config.corpus.embedding_dimensions!=1536 or config.corpus.embedding_model!='text-embedding-3-small':
            raise ValueError('Unexpected model/dimensions for this approved checkpoint')
        build_identity=identity(config,'synthetic-only-not-a-production-corpus')
        rows=synthetic_rows();vectors=synthetic_vectors()
        store=ChromaStore(config,build_identity,create=create)
        try:
            if create:
                store.put(rows,vectors)
            assert store.count()==3 and store.ids()=={'alpha','beta','gamma'}
            store.verify(rows)
            result=store.query(vectors[0],3)
            assert result['ids'][0]==['alpha','gamma','beta']
            assert abs(result['distances'][0][0])<1e-6
            filtered=store.query(vectors[0],3,source='wasalt')
            assert filtered['ids'][0]==['beta']
            assert filtered['metadatas'][0][0]['source']=='wasalt'
            assert 'نص عربي' in filtered['documents'][0][0]
            if create:
                # Idempotent application upsert, then direct Chroma duplicate behavior.
                store.put(rows[:1],vectors[:1]);assert store.count()==3
                try:
                    store.collection.add(ids=['duplicate','duplicate'],documents=['a','b'],embeddings=vectors[:2])
                except DuplicateIDError:
                    pass
                else:
                    raise AssertionError('Chroma accepted duplicate IDs in one request')
                store.collection.add(ids=['alpha'],documents=['Must not replace the original'],embeddings=vectors[:1])
                store.verify(rows);assert store.count()==3
                try:
                    store.put(rows[:1],[vectors[0][:-1]])
                except ValueError:
                    pass
                else:
                    raise AssertionError('Adapter accepted an invalid dimension')
                for operation in (
                    lambda:store.collection.add(ids=['wrong_dimension'],documents=['Invalid'],embeddings=[vectors[0][:-1]]),
                    lambda:store.collection.query(query_embeddings=[vectors[0][:-1]],n_results=1)):
                    try:
                        operation()
                    except InvalidArgumentError:
                        pass
                    else:
                        raise AssertionError('Chroma accepted an invalid dimension')
                store.verify(rows);assert store.count()==3
        finally:
            store.client.close()
        # A new client after the last reference was explicitly closed.
        reopened=ChromaStore(config,build_identity,create=False)
        try:
            assert reopened.client is not store.client
            assert reopened.count()==3
            reopened.verify(rows)
            assert reopened.query(vectors[0],1)['ids'][0]==['alpha']
        finally:
            reopened.client.close()
        if attempted:
            raise AssertionError('A network attempt was blocked during verification')
        return {'phase':'create' if create else 'fresh_process_reopen','records':3,'dimensions':1536,
                'cosine_ranking_verified':True,'metadata_filter_verified':True,'arabic_text_preserved':True,
                'close_and_new_client_verified':True,'stored_text_metadata_vectors_verified':True,
                'duplicate_and_dimension_checks':create,'network_attempts':len(attempted),
                'openai_initialized':True,'environment':environment,
                'embedding_model':config.corpus.embedding_model,
                'versions':{'openai':version('openai'),'chromadb':version('chromadb')},
                'peak_rss_mib':{'before_sdk_imports':before,'after_openai_initialization':after_openai,
                    'after_chroma_import':after_import,'after_collection_operations':peak_mib()}}


def verify():
    """Create only our own TemporaryDirectory; clean it after both children exit."""
    reports=[]
    with tempfile.TemporaryDirectory(prefix='wasalt-sdk-19a-') as temporary:
        root=Path(temporary)
        for mode in ('create','reopen'):
            result=subprocess.run([sys.executable,'-B','-m','app.verify_local_integrations',
                                   '--child',mode,str(root/'db')],cwd=REPO_ROOT,
                                  capture_output=True,text=True,timeout=90)
            if result.returncode:
                # Do not echo arbitrary SDK exceptions, request bodies or credentials.
                raise RuntimeError(f'Local {mode} integration process failed; exit={result.returncode}')
            reports.append(json.loads(result.stdout))
        size=sum(path.stat().st_size for path in root.rglob('*') if path.is_file())
    assert not root.exists()
    return {'phases':reports,'temporary_database_bytes':size,'temporary_artifacts_cleaned':True,
            'fresh_process_persistence_verified':True,'production_index_created':False,
            'platform':sys.platform,'python':sys.version.split()[0]}


if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--child' and sys.argv[2] in ('create','reopen'):
        value=phase(Path(sys.argv[3]),sys.argv[2]=='create')
    elif len(sys.argv)==1:
        value=verify()
    else:
        raise SystemExit('Use python -B -m app.verify_local_integrations')
    print(json.dumps(value,ensure_ascii=False,indent=2))
