"""Offline context resolution: mocked prose is not an answer-quality benchmark."""
import unittest
from unittest.mock import Mock, patch
from app.chatbot import Chatbot
from app.config import REPO_ROOT
from app.property_search import load_properties
from app.answer_prompt import SYSTEM_PROMPT


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.net = patch('socket.socket.connect', side_effect=AssertionError('No network'))
        self.net.start(); self.addCleanup(self.net.stop)
        self.retrieval = Mock()
        self.retrieval.retrieve.return_value = [{'chunk_id':'fixture','title':'Project',
            'source':'darglobal','content_type':'developments','text':'Verified project facts.',
            'source_url':'https://darglobal.co.uk/aida'}]
        self.generator = Mock()
        self.generator.generate.return_value = {'response_text':'Verified project facts. [S1]'}
        self.bot = Chatbot(self.retrieval,self.generator,load_properties(REPO_ROOT/'data/wasalt/listings.jsonl'))

    def history(self, question):
        result=self.bot.answer(question)
        return [{'role':'user','content':question},{'role':'assistant','content':result['answer'],'result':result}]

    def test_overview_villa_followup(self):
        h=self.history('What does DarGlobal Developments do?')
        r=self.bot.answer('Tell me more about the villas.',h)
        self.assertEqual(r['route'],'darglobal');self.assertIsNone(r['properties'])
        self.assertIn('DarGlobal',self.retrieval.retrieve.call_args.args[0])
        self.assertIn('https://darglobal.co.uk/aida',r['answer'])

    def test_named_development_followups(self):
        for initial,follow,name in [('What is the AIDA development in Oman?','What amenities does it have?','aida'),
                                   ('Tell me about Tierra Viva.','What are the prices?','tierra viva')]:
            with self.subTest(name=name):
                r=self.bot.answer(follow,self.history(initial))
                self.assertEqual(r['route'],'darglobal')
                self.assertIn(name,self.retrieval.retrieve.call_args.args[0].lower())
                self.assertIsNone(r['properties'])
                self.assertIn('QUESTION\nDarGlobal',self.generator.generate.call_args.args[0][-1]['content'])

    def test_structured_narrowing_zero_apis(self):
        with patch('app.chatbot.Retrieval',side_effect=AssertionError('No retrieval')), \
             patch('app.chatbot.EmbeddingClient.embed_query',side_effect=AssertionError('No embedding')), \
             patch('requests.Session.send',side_effect=AssertionError('No HTTP')):
            for initial,follow in [('Show me villas for rent in Riyadh.','Only those under SAR 100,000 per year.'),
                                  ('فلل للايجار بالرياض','فقط اقل من ١٠٠٠٠٠ سنويا')]:
                self.generator.reset_mock();self.retrieval.reset_mock()
                r=self.bot.answer(follow,self.history(initial))
                self.assertEqual(r['properties']['total_matches'],8)
                self.assertEqual(r['filters']['city'],'Riyadh')
                self.assertEqual(r['filters']['purpose'],'rent')
                self.assertEqual(r['filters']['property_type'],'villa')
                self.assertTrue(r['disclaimer'])
                self.generator.generate.assert_not_called();self.retrieval.retrieve.assert_not_called()

    def test_explicit_switches_and_ids(self):
        dar=self.history('What is the AIDA project?')
        for query,route in [('Villas for rent in Riyadh','properties'),('Wasalt services','wasalt'),
                            ('Show listing 5891036','properties'),('Show listing 99999999','properties')]:
            r=self.bot.answer(query,dar);self.assertEqual(r['route'],route)
            if '99999999' in query:self.assertFalse(r['sources'])
        h=self.history('Villas for rent in Riyadh')
        self.assertEqual(self.bot.answer('Tell me about Tierra Viva',h)['route'],'darglobal')
        self.assertEqual(self.bot.answer('What is the AIDA project?',h)['route'],'darglobal')

    def test_ambiguous_or_reset_context_clarifies_without_calls(self):
        self.generator.reset_mock();self.retrieval.reset_mock()
        for history in [[], [{'role':'user','content':'Compare DarGlobal and Wasalt services'},
                            {'role':'assistant','content':'Both companies.'}]]:
            r=self.bot.answer('Where is it located?',history)
            self.assertEqual(r['route'],'clarify');self.assertFalse(r['sources'])
        self.retrieval.retrieve.assert_not_called();self.generator.generate.assert_not_called()

    def test_bounded_context_ignores_old_subject_and_chains(self):
        old=[{'role':'user','content':'What is the AIDA project?'}]*100
        recent=self.history('Tell me about Tierra Viva')
        r=self.bot.answer('What about the amenities?',old+recent)
        self.assertIn('tierra viva',r['context_question']);self.assertNotIn('AIDA',r['context_question'])
        next_history=recent+[{'role':'user','content':'What about the amenities?'},
                             {'role':'assistant','content':r['answer'],'result':r}]
        r=self.bot.answer('Where is it located?',next_history)
        self.assertIn('tierra viva',r['context_question'])
        self.assertLess(len(r['context_question']),200)

    def test_budget_period_and_unsupported_filters_still_clarify(self):
        h=self.history('Villas for rent in Riyadh')
        for q in ['Only those under SAR 100000','Only those with a pool']:
            r=self.bot.answer(q,h);self.assertTrue(r['answer']);self.assertIsNone(r['properties'])

    def test_explicit_company_and_form_override_previous_scope(self):
        h=self.history('Villas for rent in Riyadh')
        self.assertEqual(self.bot.answer('Tell me about DarGlobal villas',h)['route'],'darglobal')
        r=self.bot.answer('Only those under SAR 100000 per year',h,
                          explicit_filters={'listing_id':'5891036'})
        self.assertEqual(r['filters'],{'listing_id':'5891036'})
        self.assertEqual(r['properties']['total_matches'],1)

    def test_multiple_developments_do_not_guess_a_referent(self):
        h=self.history('Compare the AIDA project and Tierra Viva')
        self.retrieval.reset_mock();self.generator.reset_mock()
        self.assertEqual(self.bot.answer('Where is it located?',h)['route'],'clarify')
        self.retrieval.retrieve.assert_not_called();self.generator.generate.assert_not_called()

    def test_consecutive_structured_filters_keep_period_and_location(self):
        h=self.history('Villas for rent in Riyadh under SAR 100000/year')
        r=self.bot.answer('Only those with at least 5 bedrooms',h)
        self.assertEqual(r['filters']['price_period'],'year')
        self.assertEqual(r['filters']['max_price'],100000)
        self.assertEqual(r['filters']['min_bedrooms'],5)
        self.assertEqual(r['filters']['city'],'Riyadh')
        self.assertIsNone(r['generation'])

    def test_prompt_remains_grounded_and_targeted(self):
        for phrase in ['Use ONLY','taxation','pricing','detailed questions','[S1]','historical']:
            self.assertIn(phrase,SYSTEM_PROMPT)


if __name__=='__main__':unittest.main()
