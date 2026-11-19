"""Streamlit interaction tests with mocked services: no generation requests."""
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest
from app.config import REPO_ROOT


class ChatbotUITests(unittest.TestCase):
    def setUp(self):
        self.network = patch('socket.socket.connect', side_effect=AssertionError('No network in UI tests'))
        self.network.start(); self.addCleanup(self.network.stop)

    def test_initial_screen_and_conversation(self):
        bot = Mock()
        bot.answer.return_value = {'answer': 'Please specify DarGlobal or Wasalt.', 'sources': [], 'properties': None, 'error': ''}
        with patch('app.chatbot.Chatbot', return_value=bot):
            app = AppTest.from_file(str(REPO_ROOT / 'app/streamlit_app.py')).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.title[0].value, 'RealtyAI')
            app.chat_input[0].set_value('hello').run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.session_state.conversation), 2)
            self.assertIn('Please specify', app.markdown[-1].value)
            next(b for b in app.button if b.label == 'New chat').click().run()
            self.assertFalse(app.session_state.conversation)

    def test_saved_listing_cards_render_on_rate_limit(self):
        # Saved live results are reused only for UI rendering, never generation.
        import json
        path = REPO_ROOT / 'artifacts/checkpoint_20/q04.json'
        if not path.exists():
            self.skipTest('Live validation artifact not present')
        result = json.loads(path.read_text())
        app = AppTest.from_file(str(REPO_ROOT / 'app/streamlit_app.py'))
        app.session_state.conversation = [{'role': 'assistant', 'content': result['answer'], 'result': result}]
        app.run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any('Historical dataset' in item.value for item in app.info))
        self.assertTrue(any('Rate limit' in item.value for item in app.warning))
        self.assertEqual(sum('Listing ' in item.value for item in app.markdown), 8)


if __name__ == '__main__':
    unittest.main()
