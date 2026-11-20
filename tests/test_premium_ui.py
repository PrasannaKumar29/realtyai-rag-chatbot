"""Offline native UI presentation and accessibility regressions."""
import tomllib
import unittest
from unittest.mock import Mock, patch
import streamlit as st
from streamlit.testing.v1 import AppTest
from app.config import REPO_ROOT
from app.chatbot import SNAPSHOT


class PremiumUITests(unittest.TestCase):
    def setUp(self):
        self.net = patch('socket.socket.connect', side_effect=AssertionError('No network'))
        self.net.start(); self.addCleanup(self.net.stop)
        st.cache_resource.clear(); self.addCleanup(st.cache_resource.clear)

    def test_every_starter_submits_the_original_question_and_new_chat_resets(self):
        for question in ('Explore DarGlobal developments','What is the AIDA project?',
                         'Find villas for rent in Riyadh','How does Wasalt work?'):
            st.cache_resource.clear()
            bot=Mock();bot.answer.return_value={'answer':'Offline answer','sources':[], 'properties':None,'error':''}
            with self.subTest(question=question),patch('app.chatbot.Chatbot',return_value=bot):
                app=AppTest.from_file(str(REPO_ROOT/'app/streamlit_app.py')).run()
                self.assertFalse(app.exception)
                self.assertEqual(app.title[0].value,'RealtyAI')
                self.assertEqual(len(app.chat_input),1)
                next(b for b in app.button if b.label==question).click().run()
                self.assertFalse(app.exception)
                self.assertEqual(bot.answer.call_args.args[0],question)
                self.assertEqual(app.session_state.conversation[0]['content'],question)
                next(b for b in app.button if b.label=='New chat').click().run()
                self.assertFalse(app.session_state.conversation)
                self.assertEqual(len(app.chat_input),1)
                self.assertEqual(bot.answer.call_count,1)

    def test_sources_visible_in_original_order_with_unchanged_labels_and_urls(self):
        sources=[{'source_id':'S1','title':'A long original development title — تفاصيل المشروع',
                  'source_url':'https://darglobal.co.uk/aida'},
                 {'source_id':'S2','title':'Wasalt services','source_url':'https://wasalt.sa/en'}]
        result={'answer':'A verified answer.','sources':sources,'properties':None,'error':''}
        app=AppTest.from_file(str(REPO_ROOT/'app/streamlit_app.py'))
        app.session_state.conversation=[{'role':'assistant','content':result['answer'],'result':result}]
        app.run()
        self.assertFalse(app.exception)
        links=app.get('link_button')
        self.assertEqual([b.url for b in links],[s['source_url'] for s in sources])
        self.assertEqual([b.label for b in links],[f"{s['source_id']} · {s['title']}" for s in sources])
        self.assertFalse(any(e.label=='Cited sources' for e in app.expander))
        self.assertTrue(any('Sources' in c.value for c in app.caption))
        self.assertIn('A verified answer.',[m.value for m in app.markdown])

    def test_arabic_card_keeps_unknowns_quality_history_and_original_link(self):
        record={'listing_id':'fixture','title':'فيلا في الرياض','property_type':'villa','purpose':'rent',
                'district':None,'city':'الرياض','price_sar':None,'price_period':None,'area_sqm':None,
                'bedrooms':None,'bathrooms':None,'source_url':'https://wasalt.sa/en/property/5891036',
                'scraped_at':'2026-11-18T12:00:00Z','quality_flags':['missing_price']}
        props={'total_matches':1,'matches':[record],'unknown_count':0,'filters':{}}
        result={'answer':'سجل تاريخي','sources':[],'properties':props,'error':'','disclaimer':SNAPSHOT}
        app=AppTest.from_file(str(REPO_ROOT/'app/streamlit_app.py'))
        app.session_state.conversation=[{'role':'assistant','content':result['answer'],'result':result}]
        app.run()
        self.assertFalse(app.exception)
        text='\n'.join(m.value for m in app.markdown)
        self.assertIn('Price: Unknown',text);self.assertIn('Bathrooms: Unknown',text)
        self.assertIn('فيلا في الرياض',[c.value for c in app.caption])
        self.assertTrue(any('recorded warnings' in c.value for c in app.caption))
        self.assertEqual(app.get('link_button')[0].url,record['source_url'])
        self.assertTrue(any(SNAPSHOT in i.value for i in app.info))
        self.assertTrue(any(e.label=='Technical details' and not e.proto.expanded for e in app.expander))
        self.assertTrue(any(e.label=='Advanced property search' and not e.proto.expanded for e in app.expander))

    def test_theme_text_contrast_and_supported_local_fonts(self):
        theme=tomllib.loads((REPO_ROOT/'.streamlit/config.toml').read_text())['theme']
        def luminance(value):
            channels=[int(value[i:i+2],16)/255 for i in (1,3,5)]
            channels=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in channels]
            return sum(c*w for c,w in zip(channels,(.2126,.7152,.0722)))
        for scope in (theme,theme['sidebar']):
            for background in ('backgroundColor','secondaryBackgroundColor'):
                ratio=(luminance(scope['textColor'])+.05)/(luminance(scope[background])+.05)
                self.assertGreaterEqual(ratio,4.5)
        self.assertEqual(theme['font'],'sans-serif')
        self.assertNotIn('fontFaces',theme)


if __name__=='__main__':unittest.main()
