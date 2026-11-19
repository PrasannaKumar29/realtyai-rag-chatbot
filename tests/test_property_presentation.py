"""Offline 20B regressions: authoritative counts, compact cards and query labels."""
import copy
import json
import unittest
from unittest.mock import Mock, patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from app.chatbot import Chatbot, safe_answer
from app.config import REPO_ROOT
from app.presentation import filter_question, property_card, property_summary
from app.property_search import classify, load_properties, search_properties


class PropertyPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_properties(REPO_ROOT / 'data/wasalt/listings.jsonl')

    def setUp(self):
        self.network = patch('socket.socket.connect', side_effect=AssertionError('20B permits no live requests'))
        self.network.start(); self.addCleanup(self.network.stop)
        st.cache_resource.clear()
        self.filters = {'purpose': 'rent', 'city': 'Riyadh', 'property_type': 'villa',
                        'max_price': 100000, 'price_period': 'year'}
        self.generator = Mock()
        self.generator.generate.return_value = {'response_text': 'Only five listings match your search. [S1]'}
        self.retrieval = Mock()
        self.bot = Chatbot(self.retrieval, self.generator, self.records)

    def result(self):
        return self.bot.answer(filter_question(self.filters), explicit_filters=self.filters, explain_properties=True)

    def render(self, result):
        app = AppTest.from_file(str(REPO_ROOT / 'app/streamlit_app.py'))
        app.session_state.conversation = [{'role': 'assistant', 'content': result['answer'], 'result': result}]
        app.run(timeout=30)
        self.assertFalse(app.exception)
        return app

    def test_eight_matches_five_evidence_records_never_become_five_matches(self):
        result = self.result()
        self.assertEqual(result['properties']['total_matches'], 8)
        self.assertEqual(len(result['properties']['matches']), 8)
        self.assertEqual(result['properties']['evidence_count'], 5)
        self.assertIn('matches: **8**', result['answer'])
        self.assertIn('**5 of 8**', result['answer'])
        self.assertNotIn('Only five', result['answer'])
        message = self.generator.generate.call_args.args[0][-1]['content']
        self.assertEqual(len(json.loads(message.split('\nEVIDENCE\n')[1])), 5)
        counts = json.loads(message.split('\nVERIFIED SEARCH COUNTS (evidence is a subset, never the full match count)\n')[1].split('\nEVIDENCE\n')[0])
        self.assertEqual(counts, {'total_verified_matches': 8, 'displayed_listing_cards': 8, 'property_evidence_records': 5, 'unknown_required_attributes': 0})
        self.retrieval.retrieve.assert_not_called()

    def test_correct_totals_on_success_failure_and_invalid_generated_citations(self):
        for response in ('There are 5 matches. [S1]', 'There are twenty matches. [S1]', 'Invalid count [S99]'):
            self.generator.generate.return_value = {'response_text': response}
            result = self.result()
            self.assertIn('matches: **8**', result['answer'])
            self.assertFalse(result['sources'])
        self.generator.generate.side_effect = RuntimeError('Rate limit reached')
        result = self.result()
        self.assertIn('matches: **8**', result['answer'])
        self.assertEqual(len(result['properties']['matches']), 8)
        self.assertIn('Rate limit', result['error'])

    def test_summary_distinguishes_total_display_limit_and_evidence_limit(self):
        result = self.bot.answer('Wasalt properties for rent', explicit_filters={'purpose': 'rent'}, explain_properties=True)
        self.assertEqual(result['properties']['total_matches'], 130)
        self.assertIn('matches: **130**', result['answer'])
        self.assertIn('Displaying **10**', result['answer'])
        self.assertIn('**5 of 130**', result['answer'])

    def test_zero_and_unknown_are_not_mismatches_or_matches(self):
        row = self.records[0]
        unknown = {**row, 'bedrooms': None}
        wrong = {**row, 'listing_id': 'other', 'bedrooms': 2}
        properties = search_properties([unknown, wrong], {'min_bedrooms': 3})
        self.assertEqual(properties['total_matches'], 0)
        self.assertEqual(properties['unknown_count'], 1)
        self.assertEqual(classify(unknown, {'min_bedrooms': 3})['status'], 'unknown')
        self.assertEqual(classify(wrong, {'min_bedrooms': 3})['status'], 'mismatch')
        self.assertIn('matches: **0**', property_summary(properties))

    def test_arabic_summary_is_also_deterministic(self):
        result = self.bot.answer('فلل للايجار بالرياض', explicit_filters=self.filters, explain_properties=True)
        self.assertIn('النتائج التاريخية المؤكدة: **8**', result['answer'])
        self.assertIn('**5 من 8**', result['answer'])

    def test_compact_cards_use_verified_fields_and_unknowns(self):
        row = self.result()['properties']['matches'][0]
        before = copy.deepcopy(row)
        card = property_card(row)
        self.assertEqual(card['heading'], 'Listing 5872251 · Villa for rent')
        self.assertEqual(card['location'], 'Ohod · Riyadh')
        self.assertEqual(card['price'], 'SAR 39,000 / year')
        self.assertIn('Area: 240 sqm', card['attributes'])
        self.assertIn('Bedrooms: 4', card['attributes'])
        self.assertIn('Bathrooms: Unknown', card['attributes'])
        self.assertEqual(row, before)
        missing = property_card({**row, 'area_sqm': None, 'bedrooms': None, 'bathrooms': None, 'price_sar': None})
        self.assertEqual(missing['price'], 'Price: Unknown')
        self.assertIn('Area: Unknown', missing['attributes'])
        self.assertIn('Bedrooms: Unknown', missing['attributes'])
        self.assertNotIn(': 0', missing['attributes'])

    def test_cards_render_without_default_json_and_keep_urls_and_quality(self):
        result = self.result()
        app = self.render(result)
        text = '\n'.join(item.value for item in app.markdown)
        self.assertIn('matches: **8**', text)
        self.assertNotIn('Only five', text)
        self.assertEqual(sum('Listing ' in item.value for item in app.markdown), 8)
        self.assertIn('SAR 39,000 / year', text)
        self.assertIn('Bathrooms: Unknown', text)
        self.assertNotIn('price_sar', text)
        self.assertNotIn('bedrooms"', text)
        technical = [e for e in app.expander if e.label == 'Technical details']
        self.assertEqual(len(technical), 8)
        self.assertTrue(all(not e.proto.expanded for e in technical))
        for record, expander in zip(result['properties']['matches'], technical):
            self.assertEqual(len(expander.get('json')), 1)
        links = [item.url for item in app.get('link_button')]
        self.assertEqual(links, [r['source_url'] for r in result['properties']['matches']])
        self.assertTrue(any('recorded warnings' in item.value for item in app.caption))
        self.assertTrue(any('Historical dataset' in item.value for item in app.info))

    def test_legacy_conversation_wrong_count_cannot_reappear_on_rerender(self):
        saved = json.loads((REPO_ROOT / 'artifacts/checkpoint_20/q04.json').read_text())
        saved['answer'] = 'Only five listings match your search.'
        app = self.render(saved)
        text = '\n'.join(item.value for item in app.markdown)
        self.assertIn('matches: **8**', text)
        self.assertNotIn('Only five', text)

    def test_adjacent_citations_have_readable_labels_separators_and_only_cited_sources(self):
        sources = [{'source_id': 'S1', 'source_url': 'https://darglobal.co.uk/tierra-viva'},
                   {'source_id': 'S2', 'source_url': 'https://darglobal.co.uk/marea'},
                   {'source_id': 'S3', 'source_url': 'https://wasalt.sa/en'}]
        text, used, error = safe_answer('Supported claim[S1][S2].', sources)
        self.assertFalse(error)
        self.assertEqual(text, 'Supported claim [Source S1](https://darglobal.co.uk/tierra-viva) · [Source S2](https://darglobal.co.uk/marea).')
        self.assertEqual([s['source_id'] for s in used], ['S1', 'S2'])
        self.assertNotIn('wasalt.sa', text)
        self.assertIsNone(safe_answer('Invalid [S9]', sources)[0])
        self.assertIsNone(safe_answer('Invented https://fake.example [S1]', sources)[0])

    def test_filter_question_is_readable_inclusive_and_does_not_mutate_filters(self):
        before = copy.deepcopy(self.filters)
        self.assertEqual(filter_question(self.filters), 'Find Wasalt villas for rent in Riyadh, up to SAR 100,000/year.')
        self.assertEqual(self.filters, before)
        self.assertIn('under SAR', filter_question({**self.filters, 'price_exclusive': True}))
        self.assertIn('at least 3 bedrooms', filter_question({**self.filters, 'min_bedrooms': 3}))
        self.assertIn('at least 250 sqm', filter_question({**self.filters, 'min_area_sqm': 250}))

    def test_form_submission_displays_natural_question_and_passes_original_filters(self):
        frontend = Mock(); frontend.answer.return_value = self.result()
        with patch('app.chatbot.Chatbot', return_value=frontend):
            app = AppTest.from_file(str(REPO_ROOT / 'app/streamlit_app.py')).run(timeout=30)
            for label, value in [('Purpose', 'rent'), ('City', 'Riyadh'), ('Property type', 'villa'), ('Price period', 'year')]:
                next(s for s in app.selectbox if s.label == label).select(value)
            next(n for n in app.number_input if n.label.startswith('Maximum price')).set_value(100000)
            next(b for b in app.button if b.label == 'Search historical listings').click().run(timeout=30)
            self.assertFalse(app.exception)
            self.assertEqual(frontend.answer.call_args.kwargs['explicit_filters'], self.filters)
            question = app.session_state.conversation[0]['content']
            self.assertEqual(question, filter_question(self.filters))
            self.assertNotIn('{', question)
            self.assertNotIn('max_price', question)
            self.assertIn('matches: **8**', app.session_state.conversation[1]['content'])


if __name__ == '__main__':
    unittest.main()
