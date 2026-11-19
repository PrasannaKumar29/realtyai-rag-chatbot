"""Mocked free-model evaluation tests; no live API or index writes."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import requests

from app.evaluate_openrouter import (MODELS,OpenRouterAPI,digest,is_free,messages_for,
                                    prepare_evidence,run,validate_model)


def model_record(model):
    return {'model_id':model,'available':True,'pricing':{'prompt':'0','completion':'0'},
            'architecture':{'input_modalities':['text'],'output_modalities':['text']},
            'supported_parameters':['max_tokens','temperature','reasoning'],
            'top_provider':{'max_completion_tokens':4000}}


def answer(status=200,text='Supported answer [S1].',**extra):
    response=Mock(status_code=status)
    response.json.return_value={'model':MODELS[0],'choices':[{'message':{'content':text},'finish_reason':'stop'}],
                                'usage':{'prompt_tokens':100,'completion_tokens':20,'cost':0},**extra}
    return response


class OpenRouterEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.network=patch('socket.socket.connect',side_effect=AssertionError('No network in tests'))
        self.network.start();self.addCleanup(self.network.stop)
        self.session=Mock();self.session.headers={};self.session.post.return_value=answer()
        self.api=OpenRouterAPI('fixture-key',session=self.session)

    def test_only_approved_models_zero_price_and_no_fallback(self):
        with self.assertRaises(ValueError):self.api.generate('other/paid',[])
        self.session.post.assert_not_called()
        result=self.api.generate(MODELS[0],[{'role':'user','content':'example'}])
        arguments=self.session.post.call_args.kwargs
        self.assertFalse(arguments['allow_redirects'])
        payload=arguments['json']
        self.assertEqual(payload['model'],MODELS[0]);self.assertEqual(payload['temperature'],0)
        self.assertTrue(payload['reasoning']['enabled']);self.assertEqual(payload['max_tokens'],4000)
        self.assertEqual(payload['provider']['max_price'],{'prompt':0,'completion':0})
        self.assertFalse(payload['provider']['allow_fallbacks']);self.assertEqual(result['status'],'success')

    def test_free_availability_and_supported_parameters(self):
        record=model_record(MODELS[0]);self.assertTrue(validate_model(record))
        for pricing in ({'prompt':'0.001','completion':'0'},{'prompt':'0'},{'prompt':'bad','completion':'0'}):
            self.assertFalse(is_free({'pricing':pricing}))
        self.assertFalse(validate_model({**record,'available':False}))
        self.assertFalse(validate_model({**record,'supported_parameters':[]}))
        self.assertFalse(validate_model({**record,'model_id':'unapproved:free'}))

    def test_no_automatic_retry_auth_rate_limit_and_provider_errors(self):
        for status in (401,403,404,429,500,503):
            self.session.post.return_value=answer(status,error={'code':status,'message':'API rejected'})
            result=self.api.generate(MODELS[0],[])
            self.assertEqual(result['status'],'failed');self.assertEqual(result['http_status'],status)
        self.assertEqual(self.session.post.call_count,6)

    def test_network_empty_malformed_and_invalid_citations(self):
        self.session.post.side_effect=requests.Timeout('secret should not be echoed')
        result=self.api.generate(MODELS[0],[])
        self.assertNotIn('secret',json.dumps(result));self.assertEqual(result['status'],'failed')
        self.session.post.side_effect=None
        for text in ('',None):
            self.session.post.return_value=answer(text=text)
            self.assertEqual(self.api.generate(MODELS[0],[])['status'],'failed')
        self.session.post.return_value=answer(text='Claim [S99] and [S1]')
        self.assertEqual(self.api.generate(MODELS[0],[])['invalid_source_ids'],['S99'])
        self.session.post.return_value=answer();self.session.post.return_value.json.side_effect=ValueError()
        self.assertEqual(self.api.generate(MODELS[0],[])['status'],'failed')

    def test_ten_attempt_cap_and_secret_redaction(self):
        self.session.post.return_value=answer(text='fixture-key must be redacted [S1]')
        for _ in range(10):
            self.assertNotIn('fixture-key',json.dumps(self.api.generate(MODELS[0],[])))
        with self.assertRaisesRegex(ValueError,'budget'):self.api.generate(MODELS[0],[])
        self.assertEqual(self.session.post.call_count,10)

    def test_same_prompt_evidence_and_ten_results(self):
        evidence={'questions':[{'query_id':'q'+str(i),'question':'Question '+str(i),
            'sources':[{'source_id':'S1','text':'Full unchanged evidence'}],
            'evidence_sha256':digest(['same',i])} for i in range(5)]}
        availability={'authenticated':True,'models':[model_record(model) for model in MODELS]}
        with tempfile.TemporaryDirectory() as directory,patch('builtins.print'):
            results=run(evidence,availability,self.api,Path(directory))
            self.assertEqual(len(results),10)
            for question in evidence['questions']:
                paired=[r for r in results if r['query_id']==question['query_id']]
                self.assertEqual(paired[0]['messages_sha256'],paired[1]['messages_sha256'])
                self.assertEqual(paired[0]['evidence_sha256'],paired[1]['evidence_sha256'])
            self.assertEqual(json.loads((Path(directory)/'run_manifest.json').read_text())['generation_attempts'],10)
            with self.assertRaises(FileExistsError):run(evidence,availability,self.api,Path(directory))
        self.assertEqual(self.session.post.call_count,10)

    def test_unavailable_rate_limited_and_auth_do_not_trigger_fallback(self):
        evidence={'questions':[{'query_id':'q'+str(i),'question':'Question',
                              'sources':[],'evidence_sha256':'same'} for i in range(5)]}
        availability={'authenticated':True,'models':[model_record(model) for model in MODELS]}
        self.session.post.return_value=answer(429,error={'code':429,'message':'rate limited'})
        with tempfile.TemporaryDirectory() as directory,patch('builtins.print'):
            result=run(evidence,availability,self.api,Path(directory))
        self.assertEqual(self.session.post.call_count,2)
        self.assertEqual(sum(r['status']=='unavailable' for r in result),8)
        self.session.post.reset_mock();self.api.generation_attempts=0
        self.session.post.return_value=answer(401,error={'code':401,'message':'not authorized'})
        with tempfile.TemporaryDirectory() as directory,patch('builtins.print'):
            result=run(evidence,availability,self.api,Path(directory))
        self.assertEqual(self.session.post.call_count,1)
        self.assertEqual(sum(r['status']=='unavailable' for r in result),9)

    def test_nonzero_cost_stops_and_no_paid_requests_follow(self):
        evidence={'questions':[{'query_id':'q'+str(i),'question':'Question','sources':[],
                               'evidence_sha256':'same'} for i in range(5)]}
        self.session.post.return_value=answer(usage={'cost':0.01})
        with tempfile.TemporaryDirectory() as directory,patch('builtins.print'):
            result=run(evidence,{'authenticated':True,'models':[model_record(m) for m in MODELS]},self.api,Path(directory))
        self.assertEqual(self.session.post.call_count,1);self.assertTrue(result[0]['billing_anomaly'])

    def test_parameter_rejection_stops_that_model_after_one_attempt(self):
        evidence={'questions':[{'query_id':'q'+str(i),'question':'Question','sources':[],
                               'evidence_sha256':'same'} for i in range(5)]}
        self.session.post.return_value=answer(400,error={'code':400,'message':'parameter rejected'})
        with tempfile.TemporaryDirectory() as directory,patch('builtins.print'):
            results=run(evidence,{'authenticated':True,'models':[model_record(m) for m in MODELS]},self.api,Path(directory))
        self.assertEqual(self.session.post.call_count,2)
        self.assertEqual(sum(r['status']=='unavailable' for r in results),8)

    def test_actual_saved_evidence_is_full_ranked_and_index_read_only(self):
        evidence=prepare_evidence()
        self.assertEqual(evidence['index_records_verified_read_only'],1709)
        self.assertEqual(len(evidence['questions']),5)
        for question in evidence['questions']:
            self.assertEqual([s['source_id'] for s in question['sources']],['S1','S2','S3','S4','S5'])
            self.assertTrue(all(s['text'].strip() and s['source_url'] for s in question['sources']))
        self.assertIn('فيلا',evidence['questions'][4]['question'])
        self.assertIn('historical snapshots',messages_for(evidence['questions'][0])[0]['content'])


if __name__=='__main__':
    unittest.main()
