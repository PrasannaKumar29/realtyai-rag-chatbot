"""Mocked regressions for the eight-call saved-evidence comparison."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from app.evaluate_openrouter import MODELS,OpenRouterAPI,digest
from app.evaluate_openrouter_matched import QUESTION_IDS,prepare_matched,run_matched


class MatchedEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.network=patch('socket.socket.connect',side_effect=AssertionError('No network in tests'))
        self.network.start();self.addCleanup(self.network.stop)
        self.session=Mock();self.session.headers={}
        self.session.post.return_value.status_code=200
        self.session.post.return_value.json.return_value={'model':'mocked','choices':[{
            'message':{'content':'Grounded example [S1]'},'finish_reason':'stop'}],'usage':{'cost':0}}
        self.api=OpenRouterAPI('offline-fixture-key',session=self.session,attempt_limit=8)

    def test_only_four_saved_questions_and_corrected_spain_provenance(self):
        prepared=prepare_matched()
        self.assertEqual(tuple(q['query_id'] for q in prepared['questions']),QUESTION_IDS)
        self.assertNotIn('q02',QUESTION_IDS)
        for question in prepared['questions']:
            self.assertEqual(digest(question['messages']),question['messages_sha256'])
        for reused in prepared['reused_spain']:
            raw=reused['raw_response']
            self.assertEqual(raw['query_id'],'q02');self.assertTrue(raw['request_parameters']['reasoning']['enabled'])
            self.assertIn('adjustment_responses',reused['source_path'])

    def test_eight_calls_identical_prompt_and_generation_settings(self):
        prepared=prepare_matched()
        with tempfile.TemporaryDirectory() as temporary,patch('builtins.print'):
            results=run_matched(prepared,self.api,Path(temporary)/'new')
        self.assertEqual(self.session.post.call_count,8)
        self.assertEqual(len(results),8)
        for question in prepared['questions']:
            paired=[r for r in results if r['query_id']==question['query_id']]
            self.assertEqual(paired[0]['messages_sha256'],paired[1]['messages_sha256'])
            self.assertEqual(paired[0]['evidence_sha256'],paired[1]['evidence_sha256'])
        for call in self.session.post.call_args_list:
            payload=call.kwargs['json']
            self.assertEqual(payload['max_tokens'],4000);self.assertEqual(payload['temperature'],0)
            self.assertEqual(payload['reasoning'],{'enabled':True});self.assertIn(payload['model'],MODELS)
            self.assertFalse(payload['provider']['allow_fallbacks'])
        with self.assertRaises(ValueError):self.api.generate(MODELS[0],[])

    def test_parameter_rejection_stops_entire_run_without_retry(self):
        self.session.post.return_value.status_code=400
        self.session.post.return_value.json.return_value={'error':{'code':400,'message':'Parameter adjustment needed'}}
        with tempfile.TemporaryDirectory() as temporary,patch('builtins.print'):
            path=Path(temporary)/'new'
            results=run_matched(prepare_matched(),self.api,path)
            state=json.loads((path/'run_manifest.json').read_text())
        self.assertEqual(self.session.post.call_count,1)
        self.assertEqual(len(results),1);self.assertEqual(state['status'],'stopped_for_review')

    def test_existing_output_refused_without_requests(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileExistsError):run_matched(prepare_matched(),self.api,Path(temporary))
        self.session.post.assert_not_called()


if __name__=='__main__':
    unittest.main()
