"""RealtyAI routing, portfolio coverage, prompt and native welcome regressions."""
import unittest
from unittest.mock import Mock, patch
import streamlit as st
from streamlit.testing.v1 import AppTest
from app.answer_prompt import SYSTEM_PROMPT
from app.chatbot import Chatbot, Retrieval, select_evidence
from app.development_evidence import development_index, inventory_rows
from app.config import REPO_ROOT
from app.property_search import interpret, load_properties


class RealtyAITests(unittest.TestCase):
    def setUp(self):
        self.network=patch('socket.socket.connect',side_effect=AssertionError('No network'))
        self.network.start(); self.addCleanup(self.network.stop)
        st.cache_resource.clear(); self.addCleanup(st.cache_resource.clear)
        self.index=development_index()

    def test_ordinary_questions_default_to_bounded_general_retrieval(self):
        for question in ('How do real estate investments work?', 'What are branded residences?', 'What is a mortgage?'):
            self.assertEqual(interpret(question).route,'general')
        self.assertEqual(interpret('What is Neptune?').route,'clarify')

    def test_broad_inventory_has_provenance_and_no_marketing_records(self):
        rows=inventory_rows(self.index)
        self.assertGreater(len(rows),10)
        self.assertEqual(len({r['source_url'] for r in rows}),len(rows))
        for row in rows:
            self.assertIn(row['chunk_id'],self.index.inventory[row['source_url']]['chunk_ids'])
            self.assertRegex(row['text'].lower(),r'property type|unit type')
        self.assertFalse(any(r['source_url'].endswith('/Invest-crypto') for r in rows))

    def test_broad_context_is_representative_bounded_and_not_a_business_ranking(self):
        rows=inventory_rows(self.index)
        chosen=select_evidence([(r,None) for r in rows], 'What are some iconic properties developed by DarGlobal?',10,self.index)
        self.assertEqual(len(chosen),10)
        self.assertEqual(len({r['source_url'] for r in chosen}),10)
        self.assertLessEqual(sum(r['token_count'] for r in chosen),5000)
        markets={m for r in chosen for m in self.index.inventory[r['source_url']]['markets']}
        self.assertGreaterEqual(len(markets),4)

    def test_general_retrieval_keeps_both_scopes_and_excludes_listing_documents(self):
        retrieval=Retrieval.__new__(Retrieval)
        row=inventory_rows(self.index)[0]
        from app.prepare_corpus import iter_chunks
        faq=next(r for r in iter_chunks(REPO_ROOT/'artifacts/chunks/chunks.jsonl') if r['content_type']=='informational_faq')
        retrieval.rows={r['chunk_id']:r for r in (row,faq)}
        retrieval.developments=self.index; retrieval.client=Mock();retrieval.tokenizer=Mock();retrieval.store=Mock()
        retrieval.client.embed_query.return_value=[1.,0.]
        def query(**kwargs):
            r=faq if 'content_type' in kwargs['where'] else row
            return {'ids':[[r['chunk_id']]],'distances':[[.2]]}
        retrieval.store.collection.query.side_effect=query
        selected=retrieval.retrieve('What is this company?', 'general')
        self.assertEqual({r['source'] for r in selected},{'darglobal','wasalt'})
        self.assertTrue(all(not r['content_type'].startswith('property_') for r in selected))

    def test_prompt_has_natural_style_and_factual_major_market_guards(self):
        self.assertIn('Answer directly',SYSTEM_PROMPT)
        self.assertIn('revenue, sales or pipeline',SYSTEM_PROMPT)
        self.assertIn('Never infer importance',SYSTEM_PROMPT)
        self.assertIn('not live availability',SYSTEM_PROMPT)
        self.assertIn('Arabic',SYSTEM_PROMPT)
        self.assertIn('Do not emit URLs',SYSTEM_PROMPT)

    def test_welcome_and_new_chat_do_not_construct_a_backend(self):
        with patch('app.chatbot.Chatbot') as factory:
            app=AppTest.from_file(str(REPO_ROOT/'app/streamlit_app.py')).run(timeout=30)
            self.assertFalse(app.exception)
            self.assertEqual(app.title[0].value,'RealtyAI')
            self.assertTrue(any('Your AI-powered guide' in c.value for c in app.caption))
            suggestions=[b for b in app.button if b.label in ('Explore DarGlobal developments','What is the AIDA project?','Find villas for rent in Riyadh','How does Wasalt work?')]
            self.assertEqual(len(suggestions),4)
            self.assertEqual(len(app.chat_input),1)
            self.assertFalse(any(b.label=='New chat' for b in app.sidebar.button))
            next(b for b in app.button if b.label=='New chat').click().run(timeout=30)
            factory.assert_not_called()

    def test_conversation_new_chat_preserves_cached_service_without_new_requests(self):
        backend=Mock();backend.answer.return_value={'answer':'A concise answer','properties':None,'sources':[],'error':''}
        with patch('app.chatbot.Chatbot',return_value=backend) as factory:
            app=AppTest.from_file(str(REPO_ROOT/'app/streamlit_app.py')).run(timeout=30)
            app.chat_input[0].set_value('A factual question').run(timeout=30)
            self.assertFalse(app.exception)
            self.assertEqual(len(app.session_state.conversation),2)
            next(b for b in app.button if b.label=='New chat').click().run(timeout=30)
            self.assertFalse(app.session_state.conversation)
            self.assertEqual(backend.answer.call_count,1)
            app.chat_input[0].set_value('Another question').run(timeout=30)
            self.assertEqual(factory.call_count,1)
            self.assertEqual(backend.answer.call_count,2)


if __name__=='__main__':unittest.main()
