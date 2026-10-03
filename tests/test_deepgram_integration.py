import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import DEFAULT_CONFIG
from src.stt_model_manager import AVAILABLE_DEEPGRAM_STT_MODELS
from src.stt_engine import STTWorker


class TestDeepgramIntegration(unittest.TestCase):
    def setUp(self):
        guards = [patch('src.deepgram_streamer.DeepgramLiveStreamer.start'),
                  patch('src.speaker_identifier.SpeakerIdentifier._ensure_model_loaded', return_value=False)]
        for guard in guards:
            guard.start()
            self.addCleanup(guard.stop)

    def test_deepgram_config_and_models(self):
        """Deepgram 설정 키 및 모델 목록 구조 검증"""
        self.assertIn("deepgram_api_key", DEFAULT_CONFIG)
        self.assertIn("deepgram_model", DEFAULT_CONFIG)
        self.assertEqual(DEFAULT_CONFIG["deepgram_model"], "nova-3")
        self.assertIn("deepgram_keywords", DEFAULT_CONFIG)

        model_ids = [m["id"] for m in AVAILABLE_DEEPGRAM_STT_MODELS]
        self.assertIn("nova-3", model_ids)
        self.assertIn("nova-2", model_ids)
        self.assertIn("nova-2-general", model_ids)

    @patch("requests.post")
    def test_transcribe_deepgram_success(self, mock_post):
        """Deepgram API 호출 정상 성공 및 응답 파싱 검증"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": {
                "channels": [
                    {
                        "alternatives": [
                            {
                                "transcript": "Hello and welcome to the conference talk.",
                                "confidence": 0.99
                            }
                        ]
                    }
                ]
            }
        }
        mock_post.return_value = mock_resp

        mock_queue = MagicMock()
        config = dict(DEFAULT_CONFIG)
        config["stt_provider"] = "deepgram"
        config["deepgram_api_key"] = "test_dg_key_1234"
        config["deepgram_model"] = "nova-3"
        config["deepgram_keywords"] = "Kubernetes:2.0, PostgreSQL:2.0"

        worker = STTWorker(mock_queue, config=config)
        fake_audio = np.zeros(16000, dtype=np.float32)

        res = worker._transcribe_deepgram(fake_audio, "test_dg_key_1234")
        self.assertIsNotNone(res)
        text, model = res
        self.assertEqual(text, "Hello and welcome to the conference talk.")
        self.assertEqual(model, "nova-3")

        # requests.post 호출 인자 검증
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.deepgram.com/v1/listen")
        self.assertIn("Authorization", kwargs["headers"])
        self.assertEqual(kwargs["headers"]["Authorization"], "Token test_dg_key_1234")
        self.assertIn("audio/wav", kwargs["headers"]["Content-Type"])

        # 파라미터에 keywords 주입되었는지 확인
        params = dict(kwargs["params"])
        self.assertEqual(params.get("model"), "nova-3")
        self.assertEqual(params.get("smart_format"), "true")

    @patch("requests.post")
    def test_deepgram_fallback_to_groq(self, mock_post):
        """Deepgram 에러 시 Groq로 클라우드 상호 폴백 검증"""
        def side_effect(url, **kwargs):
            m = MagicMock()
            if "deepgram.com" in url:
                m.status_code = 500
                m.text = "Internal Server Error"
            elif "groq.com" in url:
                m.status_code = 200
                m.json.return_value = {"text": "Transcribed via Groq fallback"}
            return m

        mock_post.side_effect = side_effect

        mock_queue = MagicMock()
        config = dict(DEFAULT_CONFIG)
        config["stt_provider"] = "deepgram"
        config["deepgram_api_key"] = "test_dg_key"
        config["groq_api_key"] = "test_groq_key"
        config["groq_model"] = "whisper-large-v3-turbo"

        worker = STTWorker(mock_queue, config=config)
        fake_audio = np.zeros(16000, dtype=np.float32)

        text, stt_name = worker._transcribe_audio_chunk(fake_audio)
        self.assertEqual(text, "Transcribed via Groq fallback")
        self.assertIn("Groq (폴백", stt_name)

    @patch("requests.post")
    def test_groq_fallback_to_deepgram(self, mock_post):
        """Groq 429 한도 초과 시 Deepgram으로 상호 폴백 검증"""
        def side_effect(url, **kwargs):
            m = MagicMock()
            if "groq.com" in url:
                m.status_code = 429
                m.text = "Rate Limit Exceeded"
            elif "deepgram.com" in url:
                m.status_code = 200
                m.json.return_value = {
                    "results": {
                        "channels": [{"alternatives": [{"transcript": "Transcribed via Deepgram fallback"}]}]
                    }
                }
            return m

        mock_post.side_effect = side_effect

        mock_queue = MagicMock()
        config = dict(DEFAULT_CONFIG)
        config["stt_provider"] = "groq"
        config["groq_api_key"] = "test_groq_key"
        config["deepgram_api_key"] = "test_dg_key"
        config["deepgram_model"] = "nova-3"

        worker = STTWorker(mock_queue, config=config)
        fake_audio = np.zeros(16000, dtype=np.float32)

        text, stt_name = worker._transcribe_audio_chunk(fake_audio)
        self.assertEqual(text, "Transcribed via Deepgram fallback")
        self.assertIn("Deepgram (폴백", stt_name)


if __name__ == '__main__':
    unittest.main()
