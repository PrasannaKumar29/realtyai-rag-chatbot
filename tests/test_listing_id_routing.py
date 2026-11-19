"""Checkpoint 20C: contextual listing IDs, exact JSONL lookup and no FAQ substitution."""
import json
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from app.chatbot import Chatbot
from app.config import REPO_ROOT
from app.property_search import CARD_FIELDS, interpret, load_properties


class ListingIDRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_properties(REPO_ROOT / 'data/wasalt/listings.jsonl')
        cls.target = next(row for row in cls.records if row['listing_id'] == '5891036')

    def setUp(self):
        self.network = patch('socket.socket.connect', side_effect=AssertionError('No live calls in Checkpoint 20C'))
        self.network.start(); self.addCleanup(self.network.stop)
        self.retrieval = Mock()
        self.generator = Mock()
        self.generator.generate.return_value = {'response_text': 'Historical property record. [S1]'}
        self.bot = Chatbot(self.retrieval, self.generator, self.records)

    def test_exact_reported_failure_returns_verified_jsonl_record(self):
        result = self.bot.answer('Show me the details of Wasalt property listing 5891036.')
        self.assertEqual(result['route'], 'properties')
        self.assertEqual(result['filters'], {'listing_id': '5891036'})
        self.assertEqual(result['properties']['total_matches'], 1)
        self.assertEqual(result['properties']['matches'], [{key: self.target.get(key) for key in CARD_FIELDS}])
        self.assertTrue(result['properties']['listing_lookup']['found'])
        self.assertIn('Historical dataset', result['disclaimer'])
        self.retrieval.retrieve.assert_not_called()

    def test_common_short_english_and_punctuated_forms(self):
        for question in ('Show listing 5891036', 'Details of Wasalt property 5891036',
                         'Tell me about property ID 5891036', 'Listing #5891036',
                         'Wasalt property ID: 5891036', 'Property no. 5891036',
                         'How can I view Wasalt listing 5891036?', 'Contact details for listing 5891036'):
            with self.subTest(question=question):
                plan = interpret(question, self.records)
                self.assertEqual(plan.route, 'properties')
                self.assertEqual(plan.filters['listing_id'], '5891036')
                self.assertFalse(plan.clarification)

    def test_arabic_and_arabic_indic_ids(self):
        for question in ('أخبرني عن عقار رقم 5891036', 'تفاصيل العقار رقم ٥٨٩١٠٣٦',
                         'اعلان رقم 5891036', 'أخبرني عن فيلا وصلت رقم 5891036',
                         'فيلا للايجار ٥٨٩١٠٣٦'):
            with self.subTest(question=question):
                result = self.bot.answer(question)
                self.assertEqual(result['route'], 'properties')
                self.assertEqual(result['properties']['matches'][0]['listing_id'], '5891036')
                self.assertIn('تاريخية', result['disclaimer'])
        self.retrieval.retrieve.assert_not_called()

    def test_unknown_ids_are_explicit_dataset_misses_without_substitution(self):
        self.assertNotIn('9999999', {row['listing_id'] for row in self.records})
        result = self.bot.answer('Show listing 9999999')
        self.assertIn('Listing 9999999 is not in the collected Wasalt dataset.', result['answer'])
        self.assertEqual(result['properties']['total_matches'], 0)
        self.assertEqual(result['properties']['matches'], [])
        self.assertFalse(result['properties']['listing_lookup']['found'])
        self.assertFalse(result['sources'])
        arabic = self.bot.answer('أخبرني عن عقار رقم 9999999')
        self.assertIn('غير موجود', arabic['answer'])
        self.generator.generate.assert_not_called()
        self.retrieval.retrieve.assert_not_called()

    def test_price_and_area_numbers_are_exact_constraints_not_ids(self):
        for question, field in (
            ('Villas for sale in Riyadh under SAR 5891036', 'max_price'),
            ('Wasalt villas for rent in Riyadh under SAR 5891036/year', 'max_price'),
            ('Wasalt properties for rent with at least 5891036 sqm', 'min_area_sqm'),
            ('Villas for rent with exactly 5891036 sqm', 'exact_area_sqm')):
            with self.subTest(question=question):
                plan = interpret(question, self.records)
                self.assertEqual(plan.route, 'properties')
                self.assertNotIn('listing_id', plan.filters)
                self.assertEqual(plan.filters[field], 5891036)
                self.assertFalse(plan.clarification)

    def test_arbitrary_year_phone_price_area_and_bare_numbers_are_not_ids(self):
        for question in ('5891036', 'Wasalt 5891036', 'Wasalt in 2026',
                         'Wasalt phone 5891036', 'Wasalt phone 0545752077',
                         'Wasalt property phone 5891036', 'Wasalt property 5891036 sqm',
                         'Wasalt property 5891036 SAR', 'Wasalt property 5891036/year',
                         'Wasalt property 5891036.50', 'Wasalt property 5891036-077'):
            with self.subTest(question=question):
                self.assertNotIn('listing_id', interpret(question, self.records).filters)

    def test_listing_id_and_other_constraints_all_apply(self):
        question = 'Show listing 5891036 in Riyadh for rent with at least 9 bedrooms and at least 250 sqm'
        result = self.bot.answer(question)
        self.assertEqual(result['filters'], {'listing_id': '5891036', 'city': 'Riyadh', 'purpose': 'rent',
                                              'min_bedrooms': 9.0, 'min_area_sqm': 250.0})
        self.assertEqual(result['properties']['total_matches'], 1)
        self.retrieval.retrieve.assert_not_called()

    def test_known_id_contradicting_filter_is_not_called_missing_from_dataset(self):
        result = self.bot.answer('Show listing 5891036 in Jeddah')
        self.assertEqual(result['properties']['total_matches'], 0)
        lookup = result['properties']['listing_lookup']
        self.assertTrue(lookup['found']); self.assertEqual(lookup['status'], 'mismatch')
        self.assertEqual(lookup['mismatched_fields'], ['city'])
        self.assertIn('does not match the additional filters', result['answer'])
        self.assertNotIn('not in the collected', result['answer'])
        self.generator.generate.assert_not_called(); self.retrieval.retrieve.assert_not_called()

    def test_known_id_unknown_attribute_is_not_a_confirmed_mismatch(self):
        result = self.bot.answer('Show listing 5872251 with exactly 6 bathrooms')
        self.assertEqual(result['properties']['unknown_count'], 1)
        lookup = result['properties']['listing_lookup']
        self.assertTrue(lookup['found']); self.assertEqual(lookup['status'], 'unknown')
        self.assertEqual(lookup['unknown_fields'], ['bathrooms'])
        self.assertIn('required attributes are unknown', result['answer'])
        self.assertNotIn('does not match', result['answer'])
        self.generator.generate.assert_not_called(); self.retrieval.retrieve.assert_not_called()

    def test_listing_evidence_and_card_source_are_the_actual_property_url(self):
        result = self.bot.answer('Show listing 5891036', explain_properties=True)
        message = self.generator.generate.call_args.args[0][-1]['content']
        evidence = json.loads(message.split('\nEVIDENCE\n')[1])
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]['source_id'], 'S1')
        self.assertEqual(evidence[0]['source_url'], self.target['source_url'])
        self.assertEqual(evidence[0]['content_type'], 'verified_property')
        self.assertEqual(json.loads(evidence[0]['text'])['listing_id'], '5891036')
        self.assertEqual(result['properties']['matches'][0]['source_url'], self.target['source_url'])
        self.assertFalse(result['sources'])  # Deterministic cards supply their own URLs.
        self.retrieval.retrieve.assert_not_called()

    def test_card_renders_despite_openrouter_failure(self):
        self.generator.generate.side_effect = RuntimeError('Rate limit reached; no retry')
        result = self.bot.answer('Show me the details of Wasalt property listing 5891036.', explain_properties=True)
        self.assertIn('Rate limit', result['error'])
        self.assertEqual(result['properties']['matches'][0]['price_sar'], 120000)
        app = AppTest.from_file(str(REPO_ROOT / 'app/streamlit_app.py'))
        app.session_state.conversation = [{'role': 'assistant', 'content': result['answer'], 'result': result}]
        app.run(timeout=30)
        self.assertFalse(app.exception)
        text = '\n'.join(item.value for item in app.markdown)
        self.assertIn('Listing 5891036', text)
        self.assertIn('SAR 120,000 / year', text)
        self.assertEqual([item.url for item in app.get('link_button')], [self.target['source_url']])
        self.assertTrue(any('Historical' in item.value for item in app.info))
        self.retrieval.retrieve.assert_not_called()

    def test_procedures_and_existing_other_routes_remain_available(self):
        for question, route in (
            ('How can I list my property on Wasalt?', 'wasalt'),
            ('Wasalt listing procedure', 'wasalt'), ('Wasalt services', 'wasalt'),
            ('كيف اعرض عقاري على وصلت؟', 'wasalt'),
            ('Trump Dubai amenities', 'darglobal'),
            ('Compare DarGlobal and Wasalt services', 'both'),
            ('Wasalt villas for rent in Riyadh', 'properties')):
            with self.subTest(question=question):
                self.assertEqual(interpret(question, self.records).route, route)

    def test_multiple_explicit_ids_ask_for_clarification(self):
        result = self.bot.answer('Show listing 5891036 and listing 5907001')
        self.assertIn('one property listing ID at a time', result['answer'])
        self.assertIsNone(result['properties'])
        self.generator.generate.assert_not_called(); self.retrieval.retrieve.assert_not_called()


if __name__ == '__main__':
    unittest.main()
