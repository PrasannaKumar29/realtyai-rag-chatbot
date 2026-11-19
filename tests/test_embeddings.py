"""Checkpoint 19 uses only fake API responses/stores; all network is prohibited."""

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch

from app.chunking import OfflineTokenizer
from app.config import CorpusConfig,IndexConfig,REPO_ROOT,load_environment
from app.embeddings import EmbeddingClient,EmbeddingResult,validate_vectors
from app.index_embeddings import (atomic_json,batches,checksum,dry_run,execute,identity,
                                  index_lock,load_chunks,main,read_manifest)
from app.prepare_corpus import jsonl_text
from app.search import format_results,search
from app.vector_store import ChromaStore,collection_metadata,metadata_for


class TransientError(Exception):
    def __init__(self,status=429,code=None):
        self.status_code=status;self.code=code
        super().__init__('Do not display this exception body or request text')


def response(texts,dimensions=3):
    return NS(model='text-embedding-3-small',data=[NS(index=i,embedding=[float(i+1)]*dimensions)
        for i in reversed(range(len(texts)))],usage=NS(prompt_tokens=len(texts)*2))


class MemoryStore:
    """Shared across execute calls to simulate Chroma's durable state."""
    def __init__(self):
        self.rows={};self.vectors={};self.fail_after_put=False;self.query_args=None

    def factory(self,*args,**kwargs):
        return self

    def ids(self):
        return set(self.rows)

    def count(self):
        return len(self.rows)

    def put(self,rows,vectors):
        for row,vector in zip(rows,vectors):
            self.rows[row['chunk_id']]=dict(row);self.vectors[row['chunk_id']]=list(vector)
        if self.fail_after_put:
            self.fail_after_put=False
            raise RuntimeError('Simulated crash after database commit')

    def verify(self,rows):
        for row in rows:
            if self.rows.get(row['chunk_id'])!=row:
                raise ValueError('Stored row differs')
            validate_vectors([self.vectors[row['chunk_id']]],1,3)

    def query(self,vector,top_k,source):
        self.query_args=(vector,top_k,source)
        rows=[row for row in self.rows.values() if not source or row['source']==source][:top_k]
        return {'ids':[[r['chunk_id'] for r in rows]],'documents':[[r['text'] for r in rows]],
                'metadatas':[[metadata_for(r) for r in rows]],'distances':[[0.1]*len(rows)]}


class EmbeddingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokenizer=OfflineTokenizer(CorpusConfig())

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root=Path(self.directory.name)
        self.config=IndexConfig(corpus=replace(CorpusConfig(),embedding_dimensions=3),
            chunks_path=root/'chunks.jsonl',storage_path=root/'index',expected_chunks=5,batch_size=2,
            retry_initial_seconds=0.01,retry_max_seconds=0.02)
        self.rows=[]
        for index in range(5):
            text=f'Property {index}. نص عربي'
            self.rows.append({'chunk_id':f'chunk_{index}','document_id':f'wasalt:property:{index}',
                'source':'wasalt','title':f'Property {index}','source_url':f'https://example.test/{index}',
                'content_type':'property_sale','chunk_index':0,'text':text,'token_count':self.tokenizer.count(text),
                'listing_id':str(index)})
        self.config.chunks_path.write_text(jsonl_text(self.rows),encoding='utf-8')
        self.api=Mock()
        self.api.embeddings.create.side_effect=lambda **kwargs:response(kwargs['input'])
        self.client=EmbeddingClient(self.config,client=self.api,sleep=Mock())
        self.store=MemoryStore()
        self.network=patch('socket.socket.connect',side_effect=AssertionError('No network allowed'))
        self.network.start();self.addCleanup(self.network.stop)

    def run_index(self,**kwargs):
        return execute(self.config,store_factory=self.store.factory,client_factory=lambda _:self.client,**kwargs)

    def test_missing_key_fails_before_sdk_import(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,'OPENAI_API_KEY'):
                EmbeddingClient(self.config)

    def test_explicit_dotenv_and_environment_precedence(self):
        root=Path(self.directory.name)
        (root/'.env').write_text('OPENAI_API_KEY=test-fixture-key\nOPENAI_EMBEDDING_MODEL=text-embedding-3-small\n')
        with patch.dict(os.environ,{'OPENAI_EMBEDDING_MODEL':'process-value'},clear=True):
            result=load_environment(root)
            self.assertTrue(result['env_values_loaded']);self.assertTrue(result['api_key_configured'])
            self.assertNotIn('test-fixture-key',str(result))
            self.assertEqual(os.environ['OPENAI_EMBEDDING_MODEL'],'process-value')
        with patch.dict(os.environ,{'OPENAI_API_KEY':'process-key'},clear=True):
            self.assertTrue(load_environment(root/'absent')['api_key_configured'])

    def test_config_uses_openai_variables_in_shared_corpus_policy(self):
        with patch('app.config.load_environment'),patch.dict(os.environ,{
                'OPENAI_EMBEDDING_MODEL':'text-embedding-3-small','OPENAI_EMBEDDING_DIMENSIONS':'512'},clear=True):
            config=IndexConfig.from_env()
        self.assertEqual(config.corpus.embedding_dimensions,512)

    def test_response_alignment_and_dimensions(self):
        result=self.client.embed(['first','second'],[1,1])
        self.assertEqual(result.vectors,[[1.0]*3,[2.0]*3])
        self.assertEqual(result.input_tokens,4)
        self.assertEqual(self.api.embeddings.create.call_args.kwargs['dimensions'],3)
        bad=response(['one']);bad.data[0].embedding=[1.0]
        self.api.embeddings.create.side_effect=None;self.api.embeddings.create.return_value=bad
        with self.assertRaisesRegex(ValueError,'dimensions'):self.client.embed(['one'],[1])

    def test_bad_indices_count_model_and_finite_vectors_rejected(self):
        for value in (NS(model='other',data=[],usage=None),
                      NS(model='text-embedding-3-small',data=[NS(index=1,embedding=[1]*3)],usage=None),
                      NS(model='text-embedding-3-small',data=[],usage=None)):
            self.api.embeddings.create.side_effect=None;self.api.embeddings.create.return_value=value
            with self.assertRaises(ValueError):self.client.embed(['one'],[1])
        for vector in ([0,0,0],[1,float('nan'),1],[1,float('inf'),1],[True,1,1]):
            with self.assertRaises(ValueError):validate_vectors([vector],1,3)

    def test_empty_inputs_and_limits_never_reach_api(self):
        for texts,counts in [([],[]),([''],[1]),([' '],[1]),(['text'],[]),(['text'],[0]),
                              (['text'],[8192]),(['a','b','c'],[1,1,1])]:
            with self.assertRaises(ValueError):self.client.embed(texts,counts)
        self.api.embeddings.create.assert_not_called()

    def test_bounded_exponential_retries_and_hard_errors(self):
        self.api.embeddings.create.side_effect=[TransientError(429),TransientError(503),response(['one'])]
        self.client.embed(['one'],[1])
        self.assertEqual([call.args[0] for call in self.client.sleep.call_args_list],[0.01,0.02])
        self.api.reset_mock();self.api.embeddings.create.side_effect=TransientError(503)
        with self.assertRaisesRegex(RuntimeError,'503'):self.client.embed(['one'],[1])
        self.assertEqual(self.api.embeddings.create.call_count,4)
        for error in [TransientError(401),TransientError(403),TransientError(400),TransientError(429,'insufficient_quota')]:
            self.api.reset_mock();self.api.embeddings.create.side_effect=error
            with self.assertRaises(RuntimeError) as caught:self.client.embed(['one'],[1])
            self.assertNotIn('exception body',str(caught.exception));self.assertEqual(self.api.embeddings.create.call_count,1)

    def test_network_timeout_retry_is_bounded(self):
        APITimeoutError=type('APITimeoutError',(Exception,),{})
        self.api.embeddings.create.side_effect=[APITimeoutError(),response(['one'])]
        self.client.embed(['one'],[1]);self.assertEqual(self.api.embeddings.create.call_count,2)

    def test_token_bounded_batches_preserve_order(self):
        config=replace(self.config,batch_token_limit=self.rows[0]['token_count'])
        grouped=list(batches(self.rows,config))
        self.assertEqual(len(grouped),5)
        self.assertEqual([r for batch in grouped for r in batch],self.rows)

    def test_metadata_omits_null_rejects_non_scalar(self):
        meta=metadata_for({**self.rows[0],'bedrooms':None,'quality_flags_json':'["warning"]'})
        self.assertNotIn('text',meta);self.assertNotIn('chunk_id',meta);self.assertNotIn('bedrooms',meta)
        self.assertEqual(meta['listing_id'],'0')
        with self.assertRaises(ValueError):metadata_for({'bad':['list']})
        with self.assertRaises(ValueError):metadata_for({'bad':float('nan')})

    def test_index_complete_rerun_no_duplicates_no_api(self):
        manifest=self.run_index()
        self.assertEqual(manifest['indexing_status'],'complete');self.assertEqual(self.store.count(),5)
        self.assertEqual(self.api.embeddings.create.call_count,3)
        self.assertEqual(manifest['api_input_tokens_reported'],10)
        self.api.reset_mock();self.run_index();self.api.embeddings.create.assert_not_called()
        self.assertFalse(self.config.pending_path.exists())

    def test_crash_after_upsert_resumes_local_vectors_without_reembedding(self):
        self.store.fail_after_put=True
        with self.assertRaises(RuntimeError):self.run_index()
        self.assertTrue(self.config.pending_path.is_file());self.assertEqual(self.store.count(),2)
        self.assertEqual(self.api.embeddings.create.call_count,1)
        self.run_index()
        self.assertEqual(self.api.embeddings.create.call_count,3)
        manifest=json.loads(self.config.manifest_path.read_text())
        self.assertEqual(manifest['api_input_tokens_reported'],10);self.assertEqual(self.store.count(),5)

    def test_failed_api_leaves_partial_progress_resumable(self):
        self.api.embeddings.create.side_effect=[response(['a','b']),TransientError(401)]
        with self.assertRaises(RuntimeError):self.run_index()
        self.assertEqual(self.store.count(),2)
        self.api.embeddings.create.side_effect=lambda **kwargs:response(kwargs['input'])
        self.run_index();self.assertEqual(self.store.count(),5)
        sent=[call.kwargs['input'] for call in self.api.embeddings.create.call_args_list]
        self.assertEqual(sum(self.rows[0]['text'] in batch for batch in sent),1)

    def test_pending_checkpoint_corruption_fails_without_new_api(self):
        self.store.fail_after_put=True
        with self.assertRaises(RuntimeError):self.run_index()
        pending=json.loads(self.config.pending_path.read_text());pending['vectors'][0][0]=999
        atomic_json(self.config.pending_path,pending);self.api.reset_mock()
        with self.assertRaisesRegex(ValueError,'checksum'):self.run_index()
        self.api.embeddings.create.assert_not_called()

    def test_completed_checkpoint_replay_does_not_double_count_usage(self):
        from app.index_embeddings import batch_key,fingerprint
        manifest=self.run_index();batch=self.rows[-1:]
        pending={'index_fingerprint':manifest['index_fingerprint'],'batch_key':batch_key(batch),
                 'ids':[batch[0]['chunk_id']],'vectors':[self.store.vectors[batch[0]['chunk_id']]],'input_tokens':2}
        atomic_json(self.config.pending_path,{**pending,'payload_sha256':fingerprint(pending)})
        self.api.reset_mock();result=self.run_index()
        self.assertEqual(result['api_input_tokens_reported'],10);self.api.embeddings.create.assert_not_called()

    def test_checksum_model_and_dimensions_mismatch_fail_before_api(self):
        self.run_index();self.api.reset_mock()
        build=identity(self.config,checksum(self.config.chunks_path))
        for key,value in [('embedding_model','other'),('embedding_dimensions',512),('chunks_sha256','other')]:
            with self.assertRaisesRegex(ValueError,'mismatch'):read_manifest(self.config,{**build,key:value})
        self.api.embeddings.create.assert_not_called()

    def test_corrupted_collection_and_unknown_or_missing_ids_not_reembedded(self):
        self.run_index();self.api.reset_mock()
        self.store.rows['extra']=self.rows[0]
        with self.assertRaises(ValueError):self.run_index()
        del self.store.rows['extra'];del self.store.rows['chunk_0']
        with self.assertRaises(ValueError):self.run_index()
        self.api.embeddings.create.assert_not_called()

    def test_orphaned_storage_and_lock_fail_safely(self):
        self.config.storage_path.mkdir();(self.config.storage_path/'unknown').write_text('preserve')
        with self.assertRaisesRegex(ValueError,'without a compatible manifest'):self.run_index()
        with index_lock(self.config):
            with self.assertRaisesRegex(ValueError,'locked'):
                with index_lock(self.config):pass

    def test_cost_ceiling_enforced_before_directory_or_api(self):
        self.config=replace(self.config,cost_ceiling_usd=0)
        with self.assertRaisesRegex(ValueError,'cost'):self.run_index()
        self.assertFalse(self.config.storage_path.exists());self.api.embeddings.create.assert_not_called()
        self.run_index(allow_cost_override=True);self.assertEqual(self.store.count(),5)

    def test_dry_run_offline_no_index_creation_or_secret(self):
        original=self.config.chunks_path.read_bytes()
        with patch.dict(os.environ,{'OPENAI_API_KEY':'fixture-must-not-appear'}):
            report=dry_run(self.config)
        self.assertEqual(report['chunks'],5);self.assertEqual(report['expected_full_batches'],3)
        self.assertNotIn('fixture-must-not-appear',json.dumps(report))
        self.assertFalse(self.config.storage_path.exists())
        self.assertEqual(self.config.chunks_path.read_bytes(),original)
        self.api.embeddings.create.assert_not_called()

    def test_default_cli_is_dry_run_and_requires_explicit_execute(self):
        with (patch('app.index_embeddings.IndexConfig.from_env',return_value=self.config),
              patch('builtins.print') as output,patch('app.index_embeddings.execute') as paid):
            main([])
        paid.assert_not_called();self.assertIn('dry-run',output.call_args.args[0])

    def test_input_duplicate_empty_and_wrong_token_counts(self):
        for rows in ([self.rows[0]]*5,[{**r,'text':''} for r in self.rows],
                     [{**r,'token_count':1} for r in self.rows]):
            self.config.chunks_path.write_text(jsonl_text(rows))
            with self.assertRaises(ValueError):load_chunks(self.config)

    def test_retrieval_mocked_query_embedding_filter_and_format(self):
        self.run_index()
        result=search(self.config,'Where are villas?',top_k=2,source='wasalt',
            store_factory=self.store.factory,client_factory=lambda _:self.client)
        self.assertEqual(len(result),2);self.assertEqual(result[0]['rank'],1)
        self.assertEqual(result[0]['source_url'],self.rows[0]['source_url'])
        self.assertIn('نص عربي',result[0]['excerpt']);self.assertEqual(self.store.query_args[2],'wasalt')
        self.assertEqual(result[0]['cosine_distance'],0.1)

    def test_retrieval_missing_partial_or_incompatible_fails_before_query(self):
        with self.assertRaisesRegex(ValueError,'not been built'):search(self.config,'query')
        self.api.embeddings.create.side_effect=TransientError(401)
        with self.assertRaises(RuntimeError):self.run_index()
        self.api.reset_mock()
        with self.assertRaisesRegex(ValueError,'incomplete'):
            search(self.config,'query',store_factory=self.store.factory,client_factory=lambda _:self.client)
        self.api.embeddings.create.assert_not_called()

    def test_chroma_adapter_always_explicit_embeddings_and_cosine(self):
        collection=Mock();build=identity(self.config,checksum(self.config.chunks_path))
        collection.metadata=collection_metadata(build)
        chroma=NS(PersistentClient=Mock());chroma.PersistentClient.return_value.get_or_create_collection.return_value=collection
        with patch.dict('sys.modules',{'chromadb':chroma,'chromadb.config':NS(Settings=Mock())}):
            store=ChromaStore(self.config,build,create=True)
        args=chroma.PersistentClient.return_value.get_or_create_collection.call_args.kwargs
        self.assertIsNone(args['embedding_function']);self.assertEqual(args['metadata']['hnsw:space'],'cosine')
        store.put(self.rows[:1],[[1.0]*3])
        self.assertEqual(collection.upsert.call_args.kwargs['embeddings'],[[1.0]*3])
        collection.get.return_value={'ids':['chunk_0'],'documents':[self.rows[0]['text']],
            'metadatas':[metadata_for(self.rows[0])],'embeddings':[[1.0]*3]}
        store.verify(self.rows[:1])

    def test_actual_prepared_corpus_dry_run_without_mutation(self):
        config=IndexConfig()
        before=checksum(config.chunks_path)
        report=dry_run(config)
        self.assertEqual(report['chunks'],1709);self.assertEqual(report['embedding_input_tokens'],611245)
        self.assertEqual(report['expected_full_batches'],23)
        self.assertAlmostEqual(report['estimated_full_cost_usd'],0.0122249)
        self.assertEqual(checksum(config.chunks_path),before)


if __name__=='__main__':
    unittest.main()
