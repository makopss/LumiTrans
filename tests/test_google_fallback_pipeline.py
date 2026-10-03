import unittest
from unittest.mock import Mock, patch
import json
import time

from src.translator import RealtimeTranslator


class TestGoogleFallbackPipeline(unittest.TestCase):
    def test_tier1_dict_chrome_ex_success(self):
        translator = RealtimeTranslator({"translation_engine": "google"})
        mock_resp = Mock(status_code=200, text=json.dumps(["테스트 번역 성공"]))
        translator.session.post = Mock(return_value=mock_resp)

        result, engine = translator.translate("Test sentence")
        self.assertEqual(result, "테스트 번역 성공")
        self.assertEqual(engine, "Google")
        translator.session.post.assert_called_once()
        self.assertIn("dict-chrome-ex", translator.session.post.call_args[1]["data"]["client"])
        self.assertNotIn("Test sentence", translator.session.post.call_args[0][0])

    def test_tier1_sorry_block_page_jumps_to_tier3_clients5(self):
        translator = RealtimeTranslator({"translation_engine": "google"})
        sorry_html = "<html><head><title>Sorry...</title></head><body>Our systems have detected unusual traffic</body></html>"
        mock_block = Mock(status_code=200, text=sorry_html)
        mock_tier2 = Mock(status_code=429, text="error")
        mock_tier3 = Mock(status_code=200, text=json.dumps(["우회 도메인 번역 성공"]))

        translator.session.post = Mock(side_effect=[mock_block, mock_tier2, mock_tier3])

        result, engine = translator.translate("Blocked sentence")
        self.assertEqual(result, "우회 도메인 번역 성공")
        self.assertEqual(engine, "Google")
        # 3 calls: Tier 1 (sorry), Tier 2 (429), Tier 3 (clients5 success)
        self.assertEqual(translator.session.post.call_count, 3)
        # Verify 3rd call targeted clients5.google.com
        called_url = translator.session.post.call_args_list[2][0][0]
        self.assertIn("clients5.google.com", called_url)

    def test_concurrency_lock_drops_overlapping_call(self):
        translator = RealtimeTranslator({"translation_engine": "google"})
        # Acquire the lock manually to simulate an active in-flight request
        translator._google_lock.acquire()
        try:
            # Should not block and immediately return empty string
            res = translator._translate_google_mobile("Overlapping text")
            self.assertEqual(res, "")
        finally:
            translator._google_lock.release()

    def test_cloud_translation_api_v2_preferred_when_key_set(self):
        translator = RealtimeTranslator({
            "translation_engine": "google",
            "google_api_key": "AIzaSyFakeKey123"
        })
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = {
            "data": {
                "translations": [{"translatedText": "공식 클라우드 API 번역"}]
            }
        }
        translator.session.post = Mock(return_value=mock_resp)

        result, engine = translator.translate("Official API test")
        self.assertEqual(result, "공식 클라우드 API 번역")
        translator.session.post.assert_called_once()
        self.assertIn("translation.googleapis.com", translator.session.post.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
