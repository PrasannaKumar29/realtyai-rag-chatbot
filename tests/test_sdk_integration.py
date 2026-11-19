"""Real local SDK regressions. No paid requests and no persistent test artifacts."""

import importlib.util
import json
import os
import unittest
from unittest.mock import patch

from app.config import IndexConfig
from app.embeddings import EmbeddingClient


@unittest.skipUnless(importlib.util.find_spec('openai') and importlib.util.find_spec('chromadb'),
                     'Approved OpenAI/Chroma dependencies are required')
class SDKIntegrationTests(unittest.TestCase):
    def test_real_chroma_temporary_persistence_and_fresh_process(self):
        from app.verify_local_integrations import verify
        # The CLI separately verifies the real root .env. Tests use a fake key;
        # process environment must win over .env and no key is transmitted.
        with patch.dict(os.environ,{'OPENAI_API_KEY':'offline-fixture-not-a-real-key',
                                   'OPENAI_EMBEDDING_MODEL':'text-embedding-3-small',
                                   'OPENAI_EMBEDDING_DIMENSIONS':'1536'}):
            report=verify()
        self.assertTrue(report['temporary_artifacts_cleaned'])
        self.assertTrue(report['fresh_process_persistence_verified'])
        self.assertEqual(len(report['phases']),2)
        for phase in report['phases']:
            self.assertEqual(phase['records'],3)
            self.assertEqual(phase['network_attempts'],0)
            self.assertTrue(phase['cosine_ranking_verified'])
            self.assertTrue(phase['metadata_filter_verified'])

    def test_real_openai_sdk_serialization_with_in_memory_transport(self):
        import httpx
        from openai import OpenAI
        captured=[]

        def respond(request):
            payload=json.loads(request.content)
            captured.append(payload)
            return httpx.Response(200,json={'object':'list','model':'text-embedding-3-small',
                'data':[{'object':'embedding','index':index,'embedding':[float(index+1)]*1536}
                        for index in (1,0)],'usage':{'prompt_tokens':4,'total_tokens':4}})

        with (patch('socket.socket.connect',side_effect=AssertionError('No network')),
              httpx.Client(transport=httpx.MockTransport(respond)) as transport,
              OpenAI(api_key='offline-fixture-not-a-real-key',http_client=transport,max_retries=0) as sdk):
            result=EmbeddingClient(IndexConfig(),client=sdk).embed(['first','second'],[1,1])
        self.assertEqual(captured[0]['model'],'text-embedding-3-small')
        self.assertEqual(captured[0]['dimensions'],1536)
        self.assertEqual(captured[0]['encoding_format'],'float')
        self.assertEqual(captured[0]['input'],['first','second'])
        self.assertEqual([vector[0] for vector in result.vectors],[1.0,2.0])
        self.assertEqual(result.input_tokens,4)


if __name__=='__main__':
    unittest.main()
