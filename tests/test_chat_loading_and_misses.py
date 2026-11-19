"""Checkpoint 20D: terminal contextual-ID misses and real chat processing status."""
import copy
import unittest
from unittest.mock import Mock, patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from app.chatbot import Chatbot, PRIMARY
from app.config import REPO_ROOT
from app.presentation import captured_date
from app.property_search import interpret, load_properties


class ChatLoadingAndMissTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_properties(REPO_ROOT / 'data/wasalt/listings.jsonl')

    def setUp(self):
        self.network = patch('socket.socket.connect', side_effect=AssertionError('20D forbids live network calls'))
        self.network.start(); self.addCleanup(self.network.stop)
        self.environment = patch.dict('os.environ', {'OPENROUTER_MODEL': PRIMARY, 'OPENROUTER_ENABLE_FALLBACK': 'false'})
        self.environment.start(); self.addCleanup(self.environment.stop)
        st.cache_resource.clear()
        self.addCleanup(st.cache_resource.clear)
        self.retrieval = Mock()
        self.generator = Mock()
        self.generator.generate.return_value = {'response_text': 'Historical record. [S1]'}
        self.bot = Chatbot(self.retrieval, self.generator, self.records)

    def app(self, conversation=None):
        app = AppTest.from_file(str(REPO_ROOT / 'app/streamlit_app.py'))
        if conversation is not None:
            app.session_state.conversation = conversation
        app.run(timeout=30)
        self.assertFalse(app.exception)
        return app

    def test_eight_digit_miss_has_exact_filter_and_no_unrelated_sources(self):
        question = 'Show me the details of Wasalt property listing 99999999.'
        result = self.bot.answer(question)
        self.assertEqual(result['route'], 'properties')
        self.assertEqual(result['filters'], {'listing_id': '99999999'})
        self.assertFalse(result['properties']['listing_lookup']['found'])
        self.assertEqual(result['properties']['total_matches'], 0)
        self.assertFalse(result['sources']); self.assertIsNone(result['generation'])
        self.assertIn('not in the collected Wasalt dataset', result['answer'])
        self.assertIn('does not establish whether the listing exists on the live Wasalt website', result['answer'])
        self.retrieval.retrieve.assert_not_called(); self.generator.generate.assert_not_called()

    def test_contextual_unknown_ids_are_not_limited_to_dataset_digit_count(self):
        for identifier in ('1', '12345', '9999999', '99999999', '123456789', '123456789012', '00001234'):
            with self.subTest(identifier=identifier):
                result = self.bot.answer('Show listing ' + identifier)
                self.assertEqual(result['filters']['listing_id'], identifier)
                self.assertFalse(result['properties']['listing_lookup']['found'])
                self.assertIn(identifier, result['answer'])
        self.retrieval.retrieve.assert_not_called(); self.generator.generate.assert_not_called()

    def test_arabic_unknown_requests_and_live_existence_caveat(self):
        for question in ('أخبرني عن عقار رقم 99999999', 'تفاصيل العقار رقم ٩٩٩٩٩٩٩٩'):
            result = self.bot.answer(question)
            self.assertEqual(result['filters']['listing_id'], '99999999')
            self.assertIn('غير موجود في بيانات وصلت المجمعة', result['answer'])
            self.assertIn('موقع وصلت حالياً', result['answer'])
            self.assertIn('تاريخية', result['disclaimer'])
        self.retrieval.retrieve.assert_not_called(); self.generator.generate.assert_not_called()

    def test_default_runtime_miss_constructs_no_retrieval_and_makes_no_external_calls(self):
        with patch('app.chatbot.Retrieval') as factory, \
             patch('app.chatbot.EmbeddingClient.embed_query') as embed, \
             patch('app.chatbot.Generator.generate') as generate, \
             patch('requests.Session.send', side_effect=AssertionError('No HTTP request allowed')):
            bot = Chatbot(records=self.records)
            stages = []
            result = bot.answer('Show listing 99999999', on_status=stages.append)
            self.assertEqual(result['properties']['total_matches'], 0)
            self.assertEqual(stages, ['Checking Wasalt listings...'])
            factory.assert_not_called(); embed.assert_not_called(); generate.assert_not_called()

    def test_miss_is_terminal_even_in_a_mixed_source_request(self):
        result = self.bot.answer('DarGlobal and Wasalt property listing 99999999')
        self.assertFalse(result['properties']['listing_lookup']['found'])
        self.assertFalse(result['sources'])
        self.retrieval.retrieve.assert_not_called(); self.generator.generate.assert_not_called()

    def test_known_id_keeps_verified_card_url_and_historical_disclaimer(self):
        stages = []
        result = self.bot.answer('Show listing 5891036', on_status=stages.append)
        row = result['properties']['matches'][0]
        original = next(r for r in self.records if r['listing_id'] == '5891036')
        self.assertEqual(row['source_url'], original['source_url'])
        self.assertEqual((row['price_sar'], row['area_sqm'], row['bedrooms'], row['bathrooms']), (120000, 250, 9, 6))
        self.assertIn('Historical', result['disclaimer'])
        self.assertEqual(stages, ['Checking Wasalt listings...'])
        self.retrieval.retrieve.assert_not_called()

    def test_quantities_years_and_phone_contexts_are_not_ids(self):
        for question in ('Wasalt property 2026', 'Wasalt property built in 2026',
                         'Wasalt property 99999999 SAR', 'Wasalt property 99999999 sqm',
                         'Wasalt property 99999999/year', 'Wasalt phone 0545752077',
                         'Wasalt property phone 99999999', 'Wasalt in 2026'):
            with self.subTest(question=question):
                self.assertNotIn('listing_id', interpret(question, self.records).filters)
        price = interpret('Villas for rent in Riyadh under SAR 99999999/year', self.records)
        self.assertEqual(price.filters['max_price'], 99999999)
        self.assertNotIn('listing_id', price.filters)
        area = interpret('Villas for rent with at least 99999999 sqm', self.records)
        self.assertEqual(area.filters['min_area_sqm'], 99999999)
        self.assertNotIn('listing_id', area.filters)

    def test_lazy_semantic_initialization_is_cached_and_reports_only_real_stages(self):
        service = Mock(); service.retrieve.return_value = []
        with patch('app.chatbot.Retrieval', return_value=service) as factory:
            bot = Chatbot(generator=self.generator, records=self.records)
            factory.assert_not_called()
            for _ in range(2):
                stages = []
                bot.answer('DarGlobal Spain developments', on_status=stages.append)
                self.assertEqual(stages, ['Searching the knowledge base...'])
            factory.assert_called_once()
        self.generator.generate.assert_not_called()

    def test_user_history_and_running_status_exist_before_initialization_and_backend(self):
        previous = [{'role': 'user', 'content': 'Earlier question'},
                    {'role': 'assistant', 'content': 'Earlier answer', 'result': {
                        'answer': 'Earlier answer', 'sources': [], 'error': '', 'properties': None}}]
        question = 'Show listing 99999999'
        statuses, updates, events = [], [], []
        actual_status = st.status
        actual_chat = st.chat_message

        def status_spy(label, **kwargs):
            events.append('status')
            container = actual_status(label, **kwargs)
            statuses.append(container)
            update = container.update
            def update_spy(**values):
                updates.append(values)
                return update(**values)
            container.update = update_spy
            return container

        def chat_spy(role, *args, **kwargs):
            events.append('chat:' + role)
            return actual_chat(role, *args, **kwargs)

        def construct():
            events.append('initialize')
            self.assertEqual(st.session_state.conversation[-1], {'role': 'user', 'content': question})
            self.assertEqual(statuses[-1]._current_state, 'running')
            return frontend

        def answer(query, history, explicit_filters=None, on_status=None):
            events.append('backend')
            self.assertEqual(query, question)
            self.assertEqual(history, previous)
            self.assertEqual(st.session_state.conversation, previous + [{'role': 'user', 'content': question}])
            self.assertTrue(st.session_state.pending_request['started'])
            self.assertEqual(statuses[-1]._current_state, 'running')
            return self.bot.answer(query, history, explicit_filters, on_status)

        frontend = Mock(); frontend.answer.side_effect = answer
        with patch('app.chatbot.Chatbot', side_effect=construct), \
             patch('streamlit.status', side_effect=status_spy), \
             patch('streamlit.chat_message', side_effect=chat_spy):
            app = self.app(copy.deepcopy(previous))
            events.clear()
            app.chat_input[0].set_value(question).run(timeout=30)
            self.assertFalse(app.exception)
            self.assertLess(events.index('status'), events.index('initialize'))
            self.assertLess(events.index('initialize'), events.index('backend'))
            self.assertEqual(events[:4], ['chat:user', 'chat:assistant', 'chat:user', 'chat:assistant'])
            self.assertIn({'label': 'Checking Wasalt listings...'}, updates)
            self.assertNotIn({'label': 'Generating answer...'}, updates)
            self.assertEqual(statuses[-1]._current_state, 'complete')
            self.assertEqual([turn['role'] for turn in app.session_state.conversation], ['user', 'assistant', 'user', 'assistant'])
            self.assertIsNone(app.session_state.pending_request)
            self.assertFalse(app.chat_input[0].disabled)
            app.run(timeout=30)
            frontend.answer.assert_called_once()
            self.assertEqual(len(app.session_state.conversation), 4)
            next(b for b in app.button if b.label == 'New chat').click().run(timeout=30)
            self.assertFalse(app.session_state.conversation)
            self.assertIsNone(app.session_state.pending_request)

    def test_error_status_preserves_card_and_history(self):
        self.generator.generate.side_effect = RuntimeError('Rate limit reached')
        statuses, updates = [], []
        actual_status = st.status
        def watch(label, **kwargs):
            container = actual_status(label, **kwargs)
            statuses.append(container)
            update = container.update
            def capture(**values):
                updates.append(values)
                return update(**values)
            container.update = capture
            return container
        with patch('app.chatbot.Chatbot', return_value=self.bot), patch('streamlit.status', side_effect=watch):
            app = self.app()
            app.chat_input[0].set_value('Explain listing 5891036').run(timeout=30)
            self.assertFalse(app.exception)
        self.assertEqual(statuses[-1]._current_state, 'error')
        self.assertIn({'label': 'Generating answer...'}, updates)
        self.assertTrue(any('Listing 5891036' in item.value for item in app.markdown))
        self.assertTrue(any('Historical' in item.value for item in app.info))
        self.assertTrue(any('Rate limit' in item.value for item in app.warning))
        self.assertEqual([turn['role'] for turn in app.session_state.conversation], ['user', 'assistant'])

    def test_initialization_failure_is_saved_beneath_user_and_reenables_input(self):
        with patch('app.chatbot.Chatbot', side_effect=RuntimeError('Private SDK details')):
            app = self.app()
            app.chat_input[0].set_value('Show listing 5891036').run(timeout=30)
            self.assertFalse(app.exception)
        turns = app.session_state.conversation
        self.assertEqual([turn['role'] for turn in turns], ['user', 'assistant'])
        self.assertIn('unavailable', turns[-1]['content'])
        self.assertNotIn('Private', turns[-1]['content'])
        self.assertFalse(app.chat_input[0].disabled)

    def test_interrupted_pending_request_is_not_automatically_repeated(self):
        with patch('app.chatbot.Chatbot') as factory:
            app = AppTest.from_file(str(REPO_ROOT / 'app/streamlit_app.py'))
            app.session_state.conversation = [{'role': 'user', 'content': 'Wasalt question'}]
            app.session_state.pending_request = {'id': 'existing', 'question': 'Wasalt question', 'filters': None, 'started': True}
            app.run(timeout=30)
            self.assertFalse(app.exception)
            factory.assert_not_called()
            self.assertIn('interrupted', app.session_state.conversation[-1]['content'])
            self.assertIsNone(app.session_state.pending_request)
            self.assertFalse(app.chat_input[0].disabled)

    def test_human_capture_date_and_collapsed_precise_timestamp(self):
        result = self.bot.answer('Show listing 5891036')
        timestamp = result['properties']['matches'][0]['scraped_at']
        self.assertEqual(captured_date(timestamp), '18 Nov 2026')
        self.assertEqual(captured_date(None), 'Unknown')
        self.assertEqual(captured_date('not a timestamp'), 'Unknown')
        app = self.app([{'role': 'assistant', 'content': result['answer'], 'result': result}])
        captions = [item.value for item in app.caption]
        self.assertIn('Captured: 18 Nov 2026', captions)
        self.assertFalse(any(timestamp in value for value in captions))
        technical = next(e for e in app.expander if e.label == 'Technical details')
        self.assertFalse(technical.proto.expanded)
        self.assertIn(timestamp, technical.get('json')[0].value)
        self.assertFalse(any('0 other records' in value for value in captions))

    def test_nonzero_unknown_count_remains_visible(self):
        result = self.bot.answer('Show listing 5872251 with exactly 6 bathrooms')
        app = self.app([{'role': 'assistant', 'content': result['answer'], 'result': result}])
        self.assertTrue(any('1 other records have unknown required attributes' in item.value for item in app.caption))

    def test_session_history_remains_bounded_without_duplicate_user_turn(self):
        previous = []
        for index in range(10):
            previous.extend([{'role': 'user', 'content': str(index)}, {'role': 'assistant', 'content': 'Answer', 'result': {'answer': 'Answer', 'properties': None, 'sources': [], 'error': ''}}])
        with patch('app.chatbot.Chatbot', return_value=self.bot):
            app = self.app(previous)
            app.chat_input[0].set_value('Show listing 99999999').run(timeout=30)
            self.assertFalse(app.exception)
            self.assertEqual(len(app.session_state.conversation), 20)
            self.assertEqual([t['role'] for t in app.session_state.conversation], ['user', 'assistant'] * 10)
            self.assertEqual(sum(t['content'] == 'Show listing 99999999' for t in app.session_state.conversation), 1)

    def test_example_and_form_submit_each_run_backend_once(self):
        with patch('app.chatbot.Chatbot', return_value=self.bot):
            app = self.app()
            next(b for b in app.button if b.label == 'Find villas for rent in Riyadh').click().run(timeout=30)
            self.assertFalse(app.exception)
            self.assertEqual(len(app.session_state.conversation), 2)
            self.assertEqual(self.generator.generate.call_count, 0)
            app.run(timeout=30)
            self.assertEqual(self.generator.generate.call_count, 0)
            next(b for b in app.button if b.label == 'New chat').click().run(timeout=30)
            for label, value in [('Purpose', 'rent'), ('City', 'Riyadh'), ('Property type', 'villa'), ('Price period', 'year')]:
                next(s for s in app.selectbox if s.label == label).select(value)
            next(n for n in app.number_input if n.label.startswith('Maximum price')).set_value(100000)
            next(b for b in app.button if b.label == 'Search historical listings').click().run(timeout=30)
            self.assertFalse(app.exception)
            self.assertEqual(len(app.session_state.conversation), 2)
            self.assertEqual(self.generator.generate.call_count, 0)
            app.run(timeout=30)
            self.assertEqual(self.generator.generate.call_count, 0)

    def test_clear_during_processing_does_not_append_a_late_answer(self):
        frontend = Mock()
        def clear_while_running(*args, **kwargs):
            st.session_state.conversation = []
            st.session_state.pending_request = None
            return {'answer': 'Late answer', 'sources': [], 'properties': None, 'error': ''}
        frontend.answer.side_effect = clear_while_running
        with patch('app.chatbot.Chatbot', return_value=frontend):
            app = self.app()
            app.chat_input[0].set_value('A question').run(timeout=30)
            self.assertFalse(app.exception)
            self.assertFalse(app.session_state.conversation)
            self.assertIsNone(app.session_state.pending_request)
            self.assertFalse(any('Late answer' in item.value for item in app.markdown))
            app.run(timeout=30)
            self.assertFalse(app.chat_input[0].disabled)
            frontend.answer.assert_called_once()

    def test_documented_empty_key_manual_mode_still_returns_known_card_without_http(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': '', 'OPENROUTER_API_KEY': ''}), \
             patch('requests.Session.send', side_effect=AssertionError('No HTTP call in offline manual mode')) as send, \
             patch('app.chatbot.Retrieval') as retrieval:
            bot = Chatbot(records=self.records)
            result = bot.answer('Show listing 5891036')
            self.assertEqual(result['properties']['matches'][0]['listing_id'], '5891036')
            self.assertFalse(result['error'])
            send.assert_not_called(); retrieval.assert_not_called()


if __name__ == '__main__':
    unittest.main()
