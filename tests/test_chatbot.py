"""Offline application guardrails and real JSONL exact-filter regressions."""
import json
import unittest
from unittest.mock import Mock, patch

from app.chatbot import Chatbot, Generator, PRIMARY, Retrieval, safe_answer, select_evidence
from app.config import REPO_ROOT
from app.evaluate_openrouter import OpenRouterAPI
from app.property_search import classify, interpret, load_properties, search_properties


class ChatbotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_properties(REPO_ROOT / 'data/wasalt/listings.jsonl')

    def setUp(self):
        self.net = patch('socket.socket.connect', side_effect=AssertionError('Offline test attempted network'))
        self.net.start(); self.addCleanup(self.net.stop)
        self.retrieval = Mock()
        self.source = {'chunk_id': 'fixture', 'source': 'darglobal', 'source_url': 'https://darglobal.co.uk/tierra-viva',
                       'content_type': 'developments', 'title': 'Tierra Viva', 'text': 'Tierra Viva is in Spain.'}
        self.retrieval.retrieve.return_value = [self.source]
        self.generator = Mock()
        self.generator.generate.return_value = {'response_text': 'Tierra Viva is in Spain. [S1]'}
        self.bot = Chatbot(self.retrieval, self.generator, self.records)

    def test_routes(self):
        for q, route in [('Trump Dubai amenities', 'darglobal'), ('How can I list my property on Wasalt?', 'wasalt'),
                         ('Wasalt services', 'wasalt'), ('Villas for rent in Riyadh', 'properties'),
                         ('Compare DarGlobal and Wasalt services', 'both'), ('hello', 'clarify'),
                         ('DarGlobal projects and Wasalt villas for rent in Riyadh', 'both_properties')]:
            self.assertEqual(interpret(q, self.records).route, route, q)

    def test_real_structured_rent_results(self):
        plan = interpret('Villas for rent in Riyadh under SAR 100,000/year', self.records)
        self.assertFalse(plan.clarification)
        result = search_properties(self.records, plan.filters, limit=261)
        self.assertGreater(result['total_matches'], 0)
        for row in result['matches']:
            self.assertEqual((row['city'], row['property_type'], row['purpose'], row['price_period']), ('Riyadh', 'villa', 'rent', 'year'))
            self.assertLess(row['price_sar'], 100000)
        self.assertNotIn('5891036', [r['listing_id'] for r in result['matches']])

    def test_under_excludes_equal_price_and_period_is_exact(self):
        row = {'price_sar': 100000, 'price_period': 'year'}
        self.assertEqual(classify(row, {'max_price': 100000, 'price_exclusive': True})['status'], 'mismatch')
        self.assertEqual(classify(row, {'max_price': 100000})['status'], 'exact')
        self.assertEqual(classify(row, {'price_period': 'month'})['status'], 'mismatch')

    def test_unknown_is_not_mismatch_or_zero(self):
        row = {'bedrooms': None, 'city': 'Riyadh'}
        self.assertEqual(classify(row, {'min_bedrooms': 1})['status'], 'unknown')
        self.assertEqual(classify(row, {'min_bedrooms': 0})['status'], 'unknown')
        result = classify(row, {'min_bedrooms': 2, 'city': 'Jeddah'})
        self.assertEqual(result['unknown_fields'], ['bedrooms'])
        self.assertEqual(result['mismatched_fields'], ['city'])

    def test_english_and_arabic_attributes(self):
        for q in ['Villas for rent in Riyadh at least 5 bedrooms at least 250 sqm', 'فيلا للايجار في حي النرجس بالرياض 250 متر و6 دورات مياه']:
            plan = interpret(q, self.records)
            self.assertFalse(plan.clarification)
            results = search_properties(self.records, plan.filters)
            self.assertGreater(results['total_matches'], 0)
            for row in results['matches']:
                self.assertEqual(classify(row, plan.filters)['status'], 'exact')
        self.assertEqual(interpret('فيلا للايجار ٥٨٩١٠٣٦', self.records).filters['listing_id'], '5891036')

    def test_ambiguous_constraints_stop_before_calls(self):
        for q in ['Villas for rent in Riyadh under 100000', 'Villas for rent in Riyadh or Jeddah', 'Villas for rent with a pool', 'Villas in Paris', 'Villas under SAR 100000', 'Villas for rent under SAR 100000/year with 3+ bedrooms']:
            self.assertTrue(self.bot.answer(q)['answer'])
        self.retrieval.retrieve.assert_not_called(); self.generator.generate.assert_not_called()

    def test_factual_and_faq_routing(self):
        for question, route in [('DarGlobal Spain developments', 'darglobal'), ('How can I list my property on Wasalt?', 'wasalt'), ('DarGlobal and Wasalt services', 'both')]:
            result = self.bot.answer(question)
            self.assertEqual(result['route'], route)
            self.retrieval.retrieve.assert_called_with(question, route)
            self.assertIn('https://darglobal.co.uk/tierra-viva', result['answer'])

    def test_retrieval_tools_filter_informational_and_divide_both_sources(self):
        retrieval = Retrieval.__new__(Retrieval)
        retrieval.tokenizer = Mock(); retrieval.client = Mock(); retrieval.store = Mock()
        retrieval.client.embed_query.return_value = [1.0]
        info = {**self.source, 'chunk_id': 'faq', 'source': 'wasalt', 'content_type': 'informational_faq',
                'title': 'Wasalt FAQ', 'text': 'Listing procedure: create an account.', 'source_url': 'https://wasalt.sa/en'}
        retrieval.rows = {'fixture': self.source, 'faq': info}
        def query(**kwargs):
            key = 'faq' if 'content_type' in kwargs['where'] else 'fixture'
            return {'ids': [[key]], 'distances': [[.3]]}
        retrieval.store.collection.query.side_effect = query
        rows = retrieval.retrieve('Compare DarGlobal and Wasalt services', 'both')
        self.assertEqual({r['source'] for r in rows}, {'darglobal', 'wasalt'})
        clauses = [c.kwargs['where'] for c in retrieval.store.collection.query.call_args_list]
        self.assertEqual(len(clauses), 3)
        informational = clauses[-1]['content_type']['$in']
        self.assertTrue(all(value.startswith('informational_') for value in informational))
        retrieval.client.embed_query.assert_called_once()

    def test_deterministic_property_cards_and_history_bound(self):
        self.generator.generate.return_value = {'response_text': 'سجل تاريخي للفيلا. [S1]'}
        result = self.bot.answer('أخبرني عن فيلا وصلت رقم 5891036', [{'role': 'user', 'content': 'x'*3000}]*30, explain_properties=True)
        row = result['properties']['matches'][0]
        self.assertEqual((row['listing_id'], row['price_sar'], row['bedrooms'], row['bathrooms']), ('5891036', 120000, 9, 6))
        self.assertIn('تاريخية', result['disclaimer'])
        self.retrieval.retrieve.assert_not_called()
        messages = self.generator.generate.call_args.args[0]
        self.assertLessEqual(len(messages), 6)
        self.assertTrue(all(len(m['content']) <= 1000 for m in messages[1:-1]))

    def test_invalid_citations_and_links_rejected(self):
        sources = [{'source_id': 'S1', 'source_url': 'https://wasalt.sa/en'}]
        for text in ['Claim [S9]', 'Claim [S1] https://evil.test', 'Claim [S1](javascript:alert(1))', 'Claim [S1, S7]', 'Claim <img src=x> [S1]', 'Claim without citation']:
            self.assertIsNone(safe_answer(text, sources)[0], text)
        text, used, error = safe_answer('Fact [S1]', sources + [{'source_id': 'S2', 'source_url': 'https://wasalt.sa/en/faq'}])
        self.assertIn('https://wasalt.sa/en', text); self.assertEqual(len(used), 1); self.assertFalse(error)

    def test_insufficient_evidence_no_generation(self):
        self.retrieval.retrieve.return_value = []
        self.assertIn('insufficient', self.bot.answer('DarGlobal Neptune project')['answer'])
        self.assertEqual(self.bot.answer('Villas for rent in Riyadh under SAR 1/year')['properties']['total_matches'], 0)
        self.generator.generate.assert_not_called()

    def test_current_availability_claims_blocked(self):
        source = [{'source_id': 'S1', 'source_url': 'https://wasalt.sa/en'}]
        for text in ['This villa is currently available [S1]', 'The apartments are available now [S1]', 'الفيلا متاحة حاليا [S1]']:
            self.assertIsNone(safe_answer(text, source, True)[0])

    def test_press_hub_excluded_and_development_preferred(self):
        hub = {**self.source, 'source_url': 'https://darglobal.co.uk/press', 'content_type': 'press'}
        blog = {**self.source, 'chunk_id': 'blog', 'content_type': 'blog', 'source_url': 'https://darglobal.co.uk/blog'}
        selected = select_evidence([(hub, .1), (blog, .30), (self.source, .32)], 'DarGlobal Spain developments')
        self.assertEqual(selected[0], self.source); self.assertNotIn(hub, selected)
        self.assertEqual(len(select_evidence([({**self.source, 'chunk_id': str(i)}, .2) for i in range(6)], 'Spain')), 2)

    def test_unrelated_project_excluded(self):
        self.assertFalse(select_evidence([(self.source, .3)], 'Trump Dubai amenities'))
        self.assertFalse(select_evidence([(self.source, .99)], 'DarGlobal question'))

    def test_generator_failure_preserves_cards(self):
        self.generator.generate.side_effect = RuntimeError('Rate limit reached; no retry')
        result = self.bot.answer('Wasalt listing 5891036', explain_properties=True)
        self.assertEqual(len(result['properties']['matches']), 1)
        self.assertIn('Rate limit', result['error'])

    def test_retrieval_failure_is_safe_and_does_not_generate(self):
        self.retrieval.retrieve.side_effect = RuntimeError('Private SDK request details')
        result = self.bot.answer('Trump Dubai amenities')
        self.assertIn('unavailable', result['answer'])
        self.assertNotIn('Private', result['error'])
        self.generator.generate.assert_not_called()

    def test_ernie_configuration_and_no_retry(self):
        session = Mock(); session.headers = {}
        session.post.return_value.status_code = 200
        session.post.return_value.json.return_value = {'model': PRIMARY, 'choices': [{'message': {'content': 'Fact [S1]'}, 'finish_reason': 'stop'}], 'usage': {'cost': 0}}
        generator = Generator(OpenRouterAPI('fixture', session=session, attempt_limit=5))
        generator.generate([])
        payload = session.post.call_args.kwargs['json']
        self.assertEqual(payload['reasoning'], {'enabled': True}); self.assertEqual(payload['max_tokens'], 4000)
        self.assertEqual(payload['model'], PRIMARY); self.assertFalse(payload['provider']['allow_fallbacks'])
        self.assertEqual(payload['provider']['max_price'], {'prompt': 0, 'completion': 0})
        session.post.return_value.status_code = 429
        session.post.return_value.json.return_value = {'error': {'code': 429}}
        with self.assertRaisesRegex(RuntimeError, 'Rate limit'): generator.generate([])
        self.assertEqual(session.post.call_count, 2)

    def test_empty_timeout_wrong_model_and_truncation(self):
        for result in [{'status': 'failed'}, {'status': 'success', 'model_returned': 'other'},
                       {'status': 'success', 'model_returned': PRIMARY, 'truncated': True},
                       {'status': 'success', 'model_returned': PRIMARY, 'usage': {'cost': 1}}]:
            api = Mock(); api.generate.return_value = result
            with self.assertRaises(RuntimeError): Generator(api).generate([])
            api.generate.assert_called_once()


if __name__ == '__main__':
    unittest.main()
