"""Dry-run by default. Paid embedding/index work requires explicit --execute."""

import argparse
from contextlib import contextmanager
from datetime import datetime,timezone
from importlib import metadata,util
import json
import os
from pathlib import Path
import tempfile

from .chunking import OfflineTokenizer
from .config import IndexConfig,REPO_ROOT,load_environment
from .embeddings import EmbeddingClient,validate_vectors
from .prepare_corpus import iter_chunks
from .vector_store import ChromaStore,collection_metadata,fingerprint,identity,metadata_for
import hashlib


def now():
    return datetime.now(timezone.utc).isoformat()


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def portable_path(path):
    resolved=Path(path).resolve()
    return str(resolved.relative_to(REPO_ROOT)) if resolved.is_relative_to(REPO_ROOT) else str(resolved)


def packages():
    result={}
    for name,distribution in [('openai','openai'),('chromadb','chromadb'),('dotenv','python-dotenv'),
                              ('tiktoken','tiktoken'),('yaml','PyYAML')]:
        try: installed=metadata.version(distribution)
        except metadata.PackageNotFoundError: installed=None
        result[distribution]={'available':util.find_spec(name) is not None,'version':installed}
    return result


def load_chunks(config):
    before=checksum(config.chunks_path)
    rows=list(iter_chunks(config.chunks_path))
    if len(rows)!=config.expected_chunks or len({row.get('chunk_id') for row in rows})!=len(rows):
        raise ValueError('Unexpected chunk count or duplicate IDs')
    tokenizer=OfflineTokenizer(config.corpus)
    for row in rows:
        for key in ('chunk_id','document_id','source','title','source_url','content_type','text'):
            if not isinstance(row.get(key),str) or not row[key].strip():
                raise ValueError('Required chunk text/identity metadata is missing')
        if type(row.get('chunk_index')) is not int or row['chunk_index']<0:
            raise ValueError('Invalid chunk index')
        tokens=tokenizer.count(row['text'])
        if type(row.get('token_count')) is not int or tokens!=row['token_count'] or not 1<=tokens<=config.input_token_limit:
            raise ValueError('Chunk token count mismatch or embedding input limit exceeded')
        metadata_for(row)
    if before!=checksum(config.chunks_path):
        raise ValueError('Chunk file changed while reading')
    return rows,before


def batches(rows,config):
    batch=[];tokens=0
    for row in rows:
        if row['token_count']>config.batch_token_limit:
            raise ValueError('Single chunk exceeds batch token limit')
        if batch and (len(batch)>=config.batch_size or tokens+row['token_count']>config.batch_token_limit):
            yield batch;batch=[];tokens=0
        batch.append(row);tokens+=row['token_count']
    if batch:
        yield batch


def read_manifest(config,build_identity):
    if not config.manifest_path.exists():
        # Never adopt an unproven collection or discard orphaned checkpoints.
        if config.storage_path.exists() and any(config.storage_path.iterdir()):
            raise ValueError('Index directory contains files without a compatible manifest; manual review required')
        return None
    value=json.loads(config.manifest_path.read_text(encoding='utf-8'))
    if value.get('identity')!=build_identity or value.get('index_fingerprint')!=fingerprint(build_identity):
        raise ValueError('Index source checksum/model/dimensions/collection mismatch; use a fresh storage path')
    if value.get('indexing_status') not in ('initializing','partial','failed','complete'):
        raise ValueError('Invalid index manifest status')
    count=value.get('indexed_chunk_count')
    if type(count) is not int or not 0<=count<=config.expected_chunks:
        raise ValueError('Invalid manifest record count')
    if value['indexing_status']=='complete' and (count!=config.expected_chunks or
            not value.get('validation_results',{}).get('complete')):
        raise ValueError('Completed index lacks successful validation')
    ledger=value.get('completed_batches',{})
    completed=[]
    for key,batch in ledger.items():
        ids=batch['ids']
        if fingerprint(ids)!=key:
            raise ValueError('Manifest batch identity mismatch')
        completed.extend(ids)
    if len(completed)!=len(set(completed)) or len(completed)!=count:
        raise ValueError('Manifest ledger and indexed count differ')
    return value


def dry_run(config):
    rows,sha=load_chunks(config)
    build_identity=identity(config,sha)
    manifest=read_manifest(config,build_identity)
    tokens=sum(row['token_count'] for row in rows)
    cost=tokens*config.usd_per_million_tokens/1_000_000
    available=packages()
    return {'mode':'dry-run','no_api_calls':True,'index_opened_or_modified':False,
            'environment':load_environment(),'packages':available,
            'missing_packages':[name for name,info in available.items() if not info['available']],
            'chunks':len(rows),'unique_chunk_ids':len({row['chunk_id'] for row in rows}),
            'source_chunks_path':portable_path(config.chunks_path),'chunks_sha256':sha,
            'embedding_input_tokens':tokens,'batch_size':config.batch_size,
            'expected_full_batches':sum(1 for _ in batches(rows,config)),
            'usd_per_million_tokens':config.usd_per_million_tokens,'estimated_full_cost_usd':cost,
            'estimated_cost_with_max_retries_usd':cost*(config.max_retries+1),
            'cost_ceiling_usd':config.cost_ceiling_usd,
            'within_cost_ceiling':cost*(config.max_retries+1)<=config.cost_ceiling_usd,
            'collection_metadata':collection_metadata(build_identity),
            'existing_index':{'manifest_compatible':bool(manifest),
                              'status':manifest['indexing_status'] if manifest else 'not_built',
                              'manifest_indexed_count':manifest['indexed_chunk_count'] if manifest else 0,
                              'database_validated':False},
            'storage_path':portable_path(config.storage_path),'manifest_path':portable_path(config.manifest_path),
            'pending_batch_path':portable_path(config.pending_path),
            'notes':['Cost is a conservative full-corpus estimate; resumptions skip verified existing IDs.',
                     'Dry run checks manifest compatibility only; live DB integrity is checked before execution/query.']}


def atomic_json(path,value):
    """Write, fsync, replace, then fsync parent. Caller holds the exclusive build lock."""
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.index-',suffix='.tmp',delete=False) as handle:
            temporary=Path(handle.name)
            json.dump(value,handle,ensure_ascii=False,sort_keys=True,allow_nan=False)
            handle.write('\n');handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,path)
        if os.name=='posix':
            descriptor=os.open(path.parent,os.O_RDONLY)
            try: os.fsync(descriptor)
            finally: os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def index_lock(config):
    config.storage_path.mkdir(parents=True,exist_ok=True)
    lock=config.storage_path/'.index.lock'
    try: descriptor=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:
        raise ValueError('Index is locked. Verify no writer is running before manually removing a stale lock') from None
    try:
        with os.fdopen(descriptor,'w') as handle:
            handle.write(str(os.getpid()));handle.flush();os.fsync(handle.fileno())
        yield
    finally:
        lock.unlink(missing_ok=True)


def batch_key(rows):
    return fingerprint([row['chunk_id'] for row in rows])


def load_pending(config,build_identity,by_id):
    if not config.pending_path.exists():
        return None
    pending=json.loads(config.pending_path.read_text(encoding='utf-8'))
    digest=pending.pop('payload_sha256',None)
    if digest!=fingerprint(pending) or pending.get('index_fingerprint')!=fingerprint(build_identity):
        raise ValueError('Pending batch checksum or configuration mismatch')
    ids=pending['ids']
    if not ids or len(set(ids))!=len(ids) or any(key not in by_id for key in ids):
        raise ValueError('Pending batch has invalid IDs')
    rows=[by_id[key] for key in ids]
    if pending.get('batch_key')!=batch_key(rows):
        raise ValueError('Pending batch identity mismatch')
    validate_vectors(pending['vectors'],len(rows),config.corpus.embedding_dimensions)
    usage=pending.get('input_tokens')
    if usage is not None and (type(usage) is not int or usage<0):
        raise ValueError('Pending batch has invalid API usage')
    return pending


def execute(config,allow_cost_override=False,store_factory=ChromaStore,client_factory=EmbeddingClient):
    """Durable vectors precede upsert; recovery replays local vectors without API calls."""
    rows,sha=load_chunks(config)
    build_identity=identity(config,sha)
    # Fail before any mutation or paid call if configuration/cost is incompatible.
    read_manifest(config,build_identity)
    cost=sum(row['token_count'] for row in rows)*config.usd_per_million_tokens/1_000_000
    if cost*(config.max_retries+1)>config.cost_ceiling_usd and not allow_cost_override:
        raise ValueError('Estimated cost exceeds ceiling; explicit --allow-cost-override required')
    by_id={row['chunk_id']:row for row in rows}
    with index_lock(config):
        # Lock file is the only allowed pre-manifest file on a new build.
        if config.manifest_path.exists():
            manifest=read_manifest(config,build_identity)
        else:
            if any(path.name!='.index.lock' for path in config.storage_path.iterdir()):
                raise ValueError('Unrecognized index files; manual review required')
            manifest={'identity':build_identity,'index_fingerprint':fingerprint(build_identity),
                'source_chunk_file':portable_path(config.chunks_path),'build_timestamp':now(),
                'updated_at':now(),'indexing_status':'initializing','indexed_chunk_count':0,
                'api_input_tokens_reported':0,'api_batches_without_usage':0,'completed_batches':{},
                'chroma_package_version':packages()['chromadb']['version'],'validation_results':{}}
            atomic_json(config.manifest_path,manifest)
        try:
            # A crash between collection creation and manifest update can leave an empty
            # or partially initialized store. Never create over an existing collection.
            create=manifest['indexed_chunk_count']==0 and not manifest['completed_batches']
            store=store_factory(config,build_identity,create=create)
            existing=store.ids()
            if existing-set(by_id):
                raise ValueError('Collection has unexpected chunk IDs')
            for batch in batches([row for row in rows if row['chunk_id'] in existing],config):
                store.verify(batch)
            pending=load_pending(config,build_identity,by_id)
            completed={key for batch in manifest['completed_batches'].values() for key in batch['ids']}
            pending_ids=set(pending['ids']) if pending else set()
            if not completed<=existing or existing-completed-pending_ids:
                raise ValueError('Database IDs do not reconcile with manifest and pending checkpoint')
            if (pending and pending_ids & completed
                    and pending['batch_key'] not in manifest['completed_batches']):
                raise ValueError('Pending batch overlaps different completed batches')

            def commit(checkpoint):
                batch=[by_id[key] for key in checkpoint['ids']]
                store.put(batch,checkpoint['vectors'])
                store.verify(batch)
                if checkpoint['batch_key'] not in manifest['completed_batches']:
                    usage=checkpoint['input_tokens']
                    manifest['api_input_tokens_reported']+=usage or 0
                    manifest['api_batches_without_usage']+=int(usage is None)
                    manifest['completed_batches'][checkpoint['batch_key']]={
                        'ids':checkpoint['ids'],'input_tokens':usage,'persisted_at':now()}
                manifest.update(indexed_chunk_count=store.count(),indexing_status='partial',updated_at=now())
                atomic_json(config.manifest_path,manifest)
                config.pending_path.unlink()

            if pending:
                commit(pending)
                existing=store.ids()
            remaining=[row for row in rows if row['chunk_id'] not in existing]
            # Instantiate the paid client only if records still need vectors.
            client=client_factory(config) if remaining else None
            for batch in batches(remaining,config):
                if checksum(config.chunks_path)!=sha:
                    raise ValueError('Chunk file changed during indexing')
                result=client.embed([row['text'] for row in batch],[row['token_count'] for row in batch])
                checkpoint={'index_fingerprint':fingerprint(build_identity),'batch_key':batch_key(batch),
                    'ids':[row['chunk_id'] for row in batch],'vectors':result.vectors,
                    'input_tokens':result.input_tokens}
                atomic_json(config.pending_path,{**checkpoint,'payload_sha256':fingerprint(checkpoint)})
                commit(checkpoint)
            if store.ids()!=set(by_id) or store.count()!=len(rows):
                raise ValueError('Final collection IDs/count differ from source')
            for batch in batches(rows,config):
                store.verify(batch)
            if checksum(config.chunks_path)!=sha:
                raise ValueError('Chunk source changed')
            manifest.update(indexing_status='complete',indexed_chunk_count=len(rows),updated_at=now(),
                validation_results={'complete':True,'source_sha256_verified':True,'ids_and_count_verified':True,
                    'dimensions_verified':True,'documents_and_metadata_verified':True})
            atomic_json(config.manifest_path,manifest)
            return manifest
        except Exception as error:
            manifest.update(indexing_status='failed',updated_at=now(),last_error_type=type(error).__name__)
            atomic_json(config.manifest_path,manifest)
            raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run',action='store_true')
    mode.add_argument('--execute',action='store_true')
    parser.add_argument('--allow-cost-override',action='store_true')
    args=parser.parse_args(argv)
    if args.allow_cost_override and not args.execute:
        parser.error('Cost override requires --execute')
    config=IndexConfig.from_env()
    if args.execute:
        missing=[name for name,info in packages().items() if not info['available']]
        if missing:
            raise RuntimeError('Missing dependencies: '+', '.join(missing))
        if not os.environ.get('OPENAI_API_KEY','').strip():
            raise ValueError('OPENAI_API_KEY is not configured')
        manifest=execute(config,args.allow_cost_override)
        result={key:manifest[key] for key in ('indexing_status','indexed_chunk_count','api_input_tokens_reported',
                                             'api_batches_without_usage','validation_results')}
        result['manifest_path']=portable_path(config.manifest_path)
    else:
        result=dry_run(config)
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))


if __name__=='__main__':
    try:
        main()
    except (ValueError,RuntimeError,FileNotFoundError) as error:
        raise SystemExit(str(error)) from None
    except Exception as error:
        raise SystemExit(f'Indexing failed ({type(error).__name__}); inspect local state before resuming') from None
