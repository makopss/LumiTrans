"""Gemini 키가 주소에 남지 않고, 화면 캡처는 UI 스레드에서 실행되는지 확인한다."""
import os
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication

import queue

from src.audio_chunk import offer_queue
from src.screen_capture import _ensure_gui_bridge, run_on_gui_thread
from src.translator import RealtimeTranslator
from src.youtube_helper import transcript_language_order

app = QApplication.instance() or QApplication([])
_ensure_gui_bridge()


class SecurityStabilityFixTests(unittest.TestCase):
    def test_gemini_key_stays_in_the_header(self):
        translator = RealtimeTranslator({"translation_engine": "gemini"})
        captured = {}

        class Response:
            status_code = 200

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": "안녕"}]}}]}

        def post(url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers
            return Response()

        translator.session.post = post
        self.assertEqual(translator._translate_gemini("hello", "secret-key"), "안녕")
        self.assertNotIn("secret-key", captured["url"])
        self.assertNotIn("key=", captured["url"])
        self.assertEqual(captured["headers"]["x-goog-api-key"], "secret-key")

    def test_background_callable_runs_on_the_gui_thread(self):
        seen = {}

        def mark():
            seen["thread"] = QThread.currentThread()
            return "ok"

        result = {}

        def worker():
            result["value"] = run_on_gui_thread(mark)

        thread = threading.Thread(target=worker)
        thread.start()
        deadline = time.monotonic() + 2.0
        while thread.is_alive() and time.monotonic() < deadline:
            app.processEvents()
            thread.join(0.02)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["value"], "ok")
        self.assertIs(seen["thread"], app.thread())

    def test_full_queue_drops_the_oldest_item(self):
        pending = queue.Queue(maxsize=2)
        self.assertTrue(offer_queue(pending, "a"))
        self.assertTrue(offer_queue(pending, "b"))
        self.assertTrue(offer_queue(pending, "c"))
        self.assertEqual(pending.get_nowait(), "b")
        self.assertEqual(pending.get_nowait(), "c")

    def test_transcript_languages_follow_the_source_language(self):
        self.assertEqual(transcript_language_order("ja"), ["ja", "en", "en-US", "en-GB"])
        self.assertEqual(transcript_language_order("en"), ["en", "en-US", "en-GB"])


if __name__ == "__main__":
    unittest.main()
