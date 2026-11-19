"""Pure JSONL requests must not touch either API, even with credentials configured."""
import unittest
from unittest.mock import Mock,patch
from app.chatbot import Chatbot
from app.property_search import load_properties
from app.config import REPO_ROOT


class PureStructuredTests(unittest.TestCase):
    def test_pure_filters_and_ids_never_initialize_retrieval_or_call_either_api(self):
        records=load_properties(REPO_ROOT/'data/wasalt/listings.jsonl')
        with patch('requests.Session.send', side_effect=AssertionError('No HTTP')) as http, \
             patch('app.chatbot.Retrieval') as retrieval, \
             patch('app.chatbot.EmbeddingClient.embed_query') as embed, \
             patch('app.chatbot.Generator.generate') as generate:
            bot=Chatbot(records=records)
            for question,count in [('Show listing 5891036',1),('Show listing 99999999',0),
                                   ('Villas for rent in Riyadh under SAR 100000/year',8),
                                   ('أخبرني عن عقار رقم 5891036',1),
                                   ('Show listing 5872251 with exactly 6 bathrooms',0),
                                   ('Show listing 5891036 in Jeddah',0)]:
                with self.subTest(question=question):
                    stages=[];r=bot.answer(question,on_status=stages.append)
                    self.assertEqual(r['properties']['total_matches'],count)
                    self.assertIsNone(r['generation']);self.assertFalse(r['error'])
                    self.assertEqual(r['properties']['evidence_count'],0)
                    self.assertEqual(stages,['Checking Wasalt listings...'])
                    self.assertTrue(r['disclaimer'])
                    if count:
                        self.assertTrue(all(p['source_url'].startswith('https://wasalt.sa/') for p in r['properties']['matches']))
            r=bot.answer('Property search',explicit_filters={'city':'Riyadh','purpose':'rent','property_type':'villa','max_price':100000,'price_period':'year','min_area_sqm':200,'min_bedrooms':3})
            self.assertIsNotNone(r['properties'])
            http.assert_not_called();retrieval.assert_not_called();embed.assert_not_called();generate.assert_not_called()

    def test_explanation_and_knowledge_generation_paths_remain(self):
        retrieval=Mock();generator=Mock()
        generator.generate.return_value={'response_text':'Historical record. [S1]'}
        records=load_properties(REPO_ROOT/'data/wasalt/listings.jsonl')
        bot=Chatbot(retrieval,generator,records)
        bot.answer('Explain listing 5891036')
        generator.generate.assert_called_once();retrieval.retrieve.assert_not_called()
        generator.reset_mock()
        bot.answer('Show listing 5891036',explain_properties=True)
        generator.generate.assert_called_once()
        retrieval.retrieve.return_value=[{'chunk_id':'fixture','title':'Wasalt FAQ','source':'wasalt',
                                         'content_type':'informational_faq','source_url':'https://wasalt.sa/en','text':'Create an account to list a property.'}]
        generator.reset_mock()
        bot.answer('How can I list my property on Wasalt?')
        retrieval.retrieve.assert_called_once();generator.generate.assert_called_once()


if __name__=='__main__':unittest.main()
