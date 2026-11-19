"""Checkpoint 20A: strictly offline diagnostics and controlled fallback regressions."""
import json
import os
import unittest
from unittest.mock import Mock, patch

import requests

from app.chatbot import Chatbot, FALLBACK, GenerationError, Generator, PRIMARY
from app.config import REPO_ROOT
from app.evaluate_openrouter import OpenRouterAPI
from app.openrouter_diagnostics import extract_diagnostics, fallback_eligible
from app.property_search import load_properties


def failure(source=None, status=429, **metadata):
    if source is not None:
        metadata['limit_source'] = source
    response = Mock(status_code=status)
    response.headers = {}
    response.json.return_value = {'error': {'code': status, 'message': 'Raw provider response must not be retained', 'metadata': metadata}}
    return response


def success(model=PRIMARY, text='Supported fact [S1]', cost=0):
    response = Mock(status_code=200)
    response.headers = {}
    response.json.return_value = {'model': model, 'provider': 'Baidu Qianfan', 'choices': [
        {'message': {'content': text}, 'finish_reason': 'stop'}], 'usage': {'cost': cost}}
    return response


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.network = patch('socket.socket.connect', side_effect=AssertionError('Zero live requests in Checkpoint 20A tests'))
        self.network.start(); self.addCleanup(self.network.stop)
        self.environment = patch.dict(os.environ, {'OPENROUTER_MODEL': PRIMARY, 'OPENROUTER_ENABLE_FALLBACK': 'false'})
        self.environment.start(); self.addCleanup(self.environment.stop)
        self.session = Mock(); self.session.headers = {}
        self.api = OpenRouterAPI('fixture-secret', session=self.session, attempt_limit=10)

    def run_generator(self, enabled=False):
        with patch.dict(os.environ, {'OPENROUTER_ENABLE_FALLBACK': str(enabled).lower()}):
            return Generator(self.api).generate([{'role': 'user', 'content': 'bounded evidence'}])

    def test_rate_limit_classifications(self):
        for source, expected in [('openrouter_free_tier_per_minute', 'openrouter_free_per_minute'),
                                 ('openrouter_free_tier_per_day', 'daily_or_account_quota'),
                                 ('openrouter_free_tier_daily', 'daily_or_account_quota'),
                                 ('openrouter_account_quota', 'daily_or_account_quota'),
                                 ('openrouter_key_limit', 'daily_or_account_quota'),
                                 ('openrouter_credits', 'daily_or_account_quota'),
                                 ('upstream_provider_shared_pool', 'upstream_provider_capacity'),
                                 ('upstream_provider_capacity', 'upstream_provider_capacity'),
                                 ('upstream_provider_rate_limit', 'upstream_provider_capacity'),
                                 ('new_unknown_limit', 'unknown_429'), (None, 'unknown_429')]:
            with self.subTest(source=source):
                diagnostic = extract_diagnostics(429, failure(source).json())
                self.assertEqual(diagnostic['rate_limit_category'], expected)

    def test_allowlisted_headers_metadata_and_duration(self):
        response = failure('upstream_provider_shared_pool', provider_name='Baidu Qianfan',
                           retry_after_seconds=40, resets_at='2026-11-19T16:00:00Z',
                           headers={'X-RateLimit-Reset': '1795104000000'})
        response.headers = {'Retry-After': '30', 'X-RateLimit-Reset': '1795104000000',
                            'x-ratelimit-reset-tokens': '1m2s', 'Authorization': 'private', 'Set-Cookie': 'private'}
        self.session.post.return_value = response
        diagnostic = self.api.generate(PRIMARY, [])['diagnostics']
        self.assertEqual(diagnostic['http_status'], 429)
        self.assertEqual(diagnostic['limit_source'], 'upstream_provider_shared_pool')
        self.assertEqual(diagnostic['provider_name'], 'Baidu Qianfan')
        self.assertEqual(diagnostic['retry_after_seconds'], 30)
        self.assertEqual(diagnostic['retry_after'], '30')
        self.assertEqual(diagnostic['rate_limit_reset']['metadata.x-ratelimit-reset'], '1795104000000')
        self.assertEqual(diagnostic['rate_limit_reset']['metadata.resets_at'], '2026-11-19T16:00:00+00:00')
        self.assertEqual(diagnostic['rate_limit_reset']['x-ratelimit-reset-tokens'], '1m2s')
        self.assertGreaterEqual(diagnostic['request_duration_seconds'], 0)
        self.assertNotIn('private', json.dumps(diagnostic))

    def test_http_date_retry_after(self):
        diagnostic = extract_diagnostics(429, headers={'retry-after': 'Thu, 19 Nov 2026 16:00:00 GMT'})
        self.assertEqual(diagnostic['retry_after'], '2026-11-19T16:00:00+00:00')
        self.assertIsNone(diagnostic['retry_after_seconds'])

    def test_missing_metadata_provider_or_retry_delay_does_not_identify_cause(self):
        for metadata in ({}, {'provider_name': 'Baidu Qianfan'}, {'error_type': 'rate_limit_exceeded', 'provider_code': 'rate_limited'}):
            response = failure(**metadata); response.headers = {'Retry-After': '1'}
            self.session.post.return_value = response
            with self.assertRaises(GenerationError) as caught:
                self.run_generator(enabled=True)
            self.assertEqual(caught.exception.diagnostics[0]['rate_limit_category'], 'unknown_429')
        self.assertEqual(self.session.post.call_count, 3)

    def test_malformed_metadata_headers_and_non_429(self):
        for metadata in (None, [], 'raw', 42, {'limit_source': {'raw': 'private'}, 'provider_name': ['private']}):
            diagnostic = extract_diagnostics(429, {'error': {'metadata': metadata}}, {'Retry-After': 'private', 'X-RateLimit-Reset': 'private'})
            self.assertEqual(diagnostic['rate_limit_category'], 'unknown_429')
            self.assertIsNone(diagnostic['retry_after']); self.assertFalse(diagnostic['rate_limit_reset'])
        self.assertEqual(extract_diagnostics(401)['rate_limit_category'], 'not_http_429')

    def test_safe_error_metadata_redaction_and_account_data_exclusion(self):
        prompt = 'full private prompt with punctuation !'
        response = failure('upstream_provider_shared_pool', provider_name='fixture-secret',
                           raw={'secret': prompt}, user_id='private-account', account_balance=99,
                           remedy_hint=prompt, provider_code='insufficient_quota')
        data = response.json.return_value
        data.update(provider='private-account', id='private-account', model=prompt, usage={'account_id': 'private-account'})
        data['error']['message'] = prompt + ' fixture-secret another-secret'
        data['error']['metadata']['unknown'] = 'another-secret'
        response.headers = {'Authorization': 'Bearer fixture-secret', 'Set-Cookie': prompt,
                            'Retry-After': 'another-secret', 'X-RateLimit-Reset': prompt}
        self.session.post.return_value = response
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'another-secret'}):
            result = self.api.generate(PRIMARY, [{'role': 'user', 'content': prompt}])
        saved = json.dumps(result)
        for private in (prompt, 'fixture-secret', 'another-secret', 'private-account', 'account_balance', 'Authorization', 'Set-Cookie'):
            self.assertNotIn(private, saved)
        self.assertIsNone(result['usage']); self.assertIsNone(result['provider_returned'])
        self.assertEqual(result['diagnostics']['provider_name'], '[REDACTED]')

    def test_default_is_disabled_and_does_not_change_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(Generator(self.api).fallback_enabled)
            self.assertNotIn('OPENROUTER_ENABLE_FALLBACK', os.environ)
        self.session.post.return_value = failure('upstream_provider_shared_pool')
        with self.assertRaises(GenerationError): self.run_generator()
        self.session.post.assert_called_once()

    def test_full_prompt_echo_in_allowlisted_label_is_removed(self):
        self.session.post.return_value = failure('upstream_provider_shared_pool', provider_name='Private prompt')
        result = self.api.generate(PRIMARY, [{'role': 'user', 'content': 'Private prompt'}])
        self.assertIsNone(result['diagnostics']['provider_name'])
        self.assertNotIn('Private prompt', json.dumps(result))

    def test_invalid_flag_and_nonprimary_configuration_fail_closed(self):
        with patch.dict(os.environ, {'OPENROUTER_ENABLE_FALLBACK': 'yes'}):
            with self.assertRaises(ValueError): Generator(self.api)
        with patch.dict(os.environ, {'OPENROUTER_MODEL': FALLBACK}):
            with self.assertRaises(ValueError): Generator(self.api)
        self.session.post.assert_not_called()

    def test_primary_success_no_fallback_even_when_enabled(self):
        self.session.post.return_value = success()
        result = self.run_generator(enabled=True)
        self.assertEqual(result['model_returned'], PRIMARY)
        self.assertEqual(len(result['attempt_diagnostics']), 1)
        self.session.post.assert_called_once()

    def test_positive_upstream_limit_gets_one_approved_fallback_with_same_evidence(self):
        self.session.post.side_effect = [failure('upstream_provider_shared_pool'), success(FALLBACK)]
        result = self.run_generator(enabled=True)
        calls = self.session.post.call_args_list
        self.assertEqual([call.kwargs['json']['model'] for call in calls], [PRIMARY, FALLBACK])
        self.assertEqual(calls[0].kwargs['json']['messages'], calls[1].kwargs['json']['messages'])
        for call in calls:
            payload = call.kwargs['json']
            self.assertEqual(payload['reasoning'], {'enabled': True}); self.assertEqual(payload['max_tokens'], 4000)
            self.assertEqual(payload['provider']['max_price'], {'prompt': 0, 'completion': 0})
            self.assertFalse(payload['provider']['allow_fallbacks']); self.assertFalse(call.kwargs['allow_redirects'])
        self.assertEqual(result['model_returned'], FALLBACK)
        self.assertEqual(len(result['attempt_diagnostics']), 2)

    def test_fallback_failure_is_terminal_no_third_call(self):
        self.session.post.side_effect = [failure('upstream_provider_shared_pool'), failure('upstream_provider_shared_pool')]
        with self.assertRaises(GenerationError) as caught: self.run_generator(enabled=True)
        self.assertEqual(len(caught.exception.diagnostics), 2)
        self.assertIn('fallback was attempted once', str(caught.exception))
        self.assertEqual(self.session.post.call_count, 2)

    def test_helper_disallows_a_second_fallback(self):
        self.session.post.return_value = failure('upstream_provider_shared_pool')
        result = self.api.generate(PRIMARY, [])
        self.assertTrue(fallback_eligible(result, True))
        self.assertFalse(fallback_eligible(result, True, fallback_used=True))
        self.assertFalse(fallback_eligible(result, False))

    def test_minute_daily_account_credit_and_unknown_never_fallback(self):
        for source in ('openrouter_free_tier_per_minute', 'openrouter_free_tier_per_day',
                       'openrouter_key_limit', 'openrouter_credits', 'openrouter_in_flight_budget',
                       'unknown_source', None):
            self.session.post.return_value = failure(source)
            with self.assertRaises(GenerationError): self.run_generator(enabled=True)
        self.assertEqual(self.session.post.call_count, 7)

    def test_quota_or_auth_indicators_override_upstream_label(self):
        for metadata in ({'provider_code': 'insufficient_quota'}, {'provider_error_code': 'daily_quota_exceeded'},
                         {'error_type': 'quota_exceeded'}, {'reason': 'daily_limit_exceeded'},
                         {'provider_code': 'invalid_api_key'}, {'provider_code': 'insufficient_credits'}):
            self.session.post.return_value = failure('upstream_provider_shared_pool', **metadata)
            with self.assertRaises(GenerationError): self.run_generator(enabled=True)
        self.assertEqual(self.session.post.call_count, 6)

    def test_non_429_and_contradictory_body_codes_never_fallback(self):
        for status in (400, 401, 402, 403, 500, 503):
            self.session.post.return_value = failure('upstream_provider_shared_pool', status=status)
            with self.assertRaises(GenerationError): self.run_generator(enabled=True)
        for body_code in (401, 402, 403, 500):
            response = failure('upstream_provider_shared_pool')
            response.json.return_value['error']['code'] = body_code
            self.session.post.return_value = response
            with self.assertRaises(GenerationError): self.run_generator(enabled=True)
        self.assertEqual(self.session.post.call_count, 10)

    def test_timeout_empty_and_wrong_model_do_not_trigger_fallback(self):
        self.session.post.side_effect = requests.Timeout('private request details')
        with self.assertRaises(GenerationError) as caught: self.run_generator(enabled=True)
        self.assertNotIn('private', str(caught.exception))
        self.session.post.side_effect = None
        for response in (success(text=''), success(model=FALLBACK), success(cost=.1)):
            self.session.post.return_value = response
            with self.assertRaises(GenerationError): self.run_generator(enabled=True)
        self.assertEqual(self.session.post.call_count, 4)

    def test_existing_attempt_cap_is_not_bypassed(self):
        self.api.attempt_limit = 1
        self.session.post.return_value = failure('upstream_provider_shared_pool')
        with self.assertRaises(ValueError): self.run_generator(enabled=True)
        self.session.post.assert_called_once()

    def test_both_models_fail_cards_disclaimer_and_internal_diagnostics_survive(self):
        self.session.post.side_effect = [failure('upstream_provider_shared_pool'), failure('upstream_provider_shared_pool')]
        with patch.dict(os.environ, {'OPENROUTER_ENABLE_FALLBACK': 'true'}):
            bot = Chatbot(Mock(), Generator(self.api), load_properties(REPO_ROOT / 'data/wasalt/listings.jsonl'))
        result = bot.answer('Wasalt listing 5891036', explain_properties=True)
        self.assertEqual(result['properties']['matches'][0]['listing_id'], '5891036')
        self.assertIn('Historical', result['disclaimer'])
        self.assertIn('Verified historical matches', result['answer'])
        self.assertEqual(len(result['generation']['attempt_diagnostics']), 2)
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(REPO_ROOT / 'app/streamlit_app.py'))
        app.session_state.conversation = [{'role': 'assistant', 'content': result['answer'], 'result': result}]
        app.run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any('Listing 5891036' in item.value for item in app.markdown))
        self.assertTrue(any('Historical' in item.value for item in app.info))
        self.assertEqual(self.session.post.call_count, 2)

    def test_fallback_answer_still_requires_valid_citations(self):
        self.session.post.side_effect = [failure('upstream_provider_shared_pool'), success(FALLBACK, text='Invented claim [S99]')]
        with patch.dict(os.environ, {'OPENROUTER_ENABLE_FALLBACK': 'true'}):
            bot = Chatbot(Mock(), Generator(self.api), load_properties(REPO_ROOT / 'data/wasalt/listings.jsonl'))
        result = bot.answer('Wasalt listing 5891036', explain_properties=True)
        self.assertFalse(result['sources']); self.assertIn('Untrusted citation', result['error'])
        self.assertNotIn('Invented claim', result['answer'])

    def test_historical_failures_have_no_classifiable_metadata(self):
        for number in range(2, 6):
            saved = json.loads((REPO_ROOT / f'artifacts/checkpoint_20/q{number:02}.json').read_text())
            self.assertIsNone(saved['generation'])
            self.assertNotIn('diagnostics', saved)
            self.assertIn('Rate limit', saved['error'])


if __name__ == '__main__':
    unittest.main()
