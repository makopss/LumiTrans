# -*- coding: utf-8 -*-
"""
test_global_multilingual_pipeline.py - 6대 프리셋 '글로벌 다국어' 및 STT 99개 언어 자동감지 파이프라인 단위 테스트
1. BUILTIN_PRESETS 6종 무결성 및 기본값 검증 (en 5종 + global auto 1종)
2. STTWorker stt_language 설정 연동 (en vs auto)
3. Groq / Deepgram / Whisper 모델별 언어 파라미터 분기
4. Whisper 음향 감지 언어(info.language) -> 번역기 source 언어 실시간 동적 피드백 검증
"""

import unittest
import queue
import numpy as np
from unittest.mock import MagicMock, patch
from src.config import BUILTIN_PRESETS, DEFAULT_CONFIG
from src.stt_engine import STTWorker


class TestGlobalMultilingualPipeline(unittest.TestCase):

    def test_builtin_presets_and_default_config_integrity(self):
        """기본 설정 및 6대 빌트인 프리셋 언어 속성 무결성 검증"""
        # 1. DEFAULT_CONFIG 검증
        self.assertIn("stt_language", DEFAULT_CONFIG)
        self.assertEqual(DEFAULT_CONFIG["stt_language"], "en")

        # 2. 6종 프리셋 순서 및 키 검증
        preset_keys = list(BUILTIN_PRESETS.keys())
        expected_keys = ["low_spec", "live", "balance", "cinema", "masterpiece", "global"]
        self.assertEqual(preset_keys, expected_keys)

        # 3. 영문 전용 5종 프리셋의 stt_language 검증
        for key in ["low_spec", "live", "balance", "cinema", "masterpiece"]:
            self.assertEqual(
                BUILTIN_PRESETS[key].get("stt_language"),
                "en",
                f"Preset '{key}' must have stt_language='en' for zero-latency English decoding"
            )

        # 4. 글로벌 다국어 프리셋 세부 사양 검증
        g = BUILTIN_PRESETS["global"]
        self.assertIn("글로벌 다국어", g["name"])
        self.assertEqual(g["icon"], "🌐")
        self.assertEqual(g["stt_language"], "auto")
        self.assertEqual(g["model_size"], "large-v3-turbo")
        self.assertEqual(g["translation_engine"], "hymt")
        self.assertEqual(g["content_tempo_preset"], "smart")

    def test_stt_worker_language_init_and_update(self):
        """STTWorker 인스턴스 생성 및 update_config 시 stt_language 반영 검증"""
        cfg = {"stt_language": "auto", "device": "cpu", "model_size": "distil-small.en"}
        with patch.object(STTWorker, "_load_model"):
            worker = STTWorker(audio_queue=queue.Queue(), config=cfg)
        self.assertEqual(worker.stt_language, "auto")

        # config 갱신 검증
        worker.update_config({"stt_language": "en"})
        self.assertEqual(worker.stt_language, "en")

    def test_whisper_en_model_forced_english(self):
        """distil-small.en 등 .en 모델은 stt_language='auto'여도 'en'으로 강제 디코딩"""
        cfg = {"stt_language": "auto", "device": "cpu", "model_size": "distil-small.en"}
        with patch.object(STTWorker, "_load_model"):
            worker = STTWorker(audio_queue=queue.Queue(), config=cfg)

        mock_translator = MagicMock()
        mock_translator.source = "en"
        worker.translator = mock_translator

        # FasterWhisper mock
        mock_whisper = MagicMock()
        mock_seg = MagicMock()
        mock_seg.text = "Hello world"
        mock_seg.words = []
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_whisper.transcribe.return_value = ([mock_seg], mock_info)
        worker.model = mock_whisper

        dummy_audio = np.zeros(1600, dtype=np.float32)
        text, _ = worker._transcribe_audio_chunk(dummy_audio)

        # verify transcribe was called with language="en"
        called_kwargs = mock_whisper.transcribe.call_args[1]
        self.assertEqual(called_kwargs.get("language"), "en")
        self.assertEqual(text, "Hello world")

    def test_whisper_multilingual_auto_detect_and_feedback_loop(self):
        """large-v3-turbo 등 다국어 모델에서 auto 모드 시 language=None 전달 및 translator.source 동적 갱신"""
        cfg = {"stt_language": "auto", "device": "cuda", "model_size": "large-v3-turbo"}
        with patch.object(STTWorker, "_load_model"):
            worker = STTWorker(audio_queue=queue.Queue(), config=cfg)

        mock_translator = MagicMock()
        mock_translator.source = "en"  # 초기 영문 상태
        worker.translator = mock_translator

        mock_whisper = MagicMock()
        mock_seg = MagicMock()
        mock_seg.text = "こんにちは"
        mock_seg.words = []
        mock_info = MagicMock()
        mock_info.language = "ja"  # 음향 분석 결과 일본어로 자동 판별됨
        mock_whisper.transcribe.return_value = ([mock_seg], mock_info)
        worker.model = mock_whisper

        dummy_audio = np.zeros(1600, dtype=np.float32)
        text, _ = worker._transcribe_audio_chunk(dummy_audio)

        # 1. Whisper.transcribe에 language=None이 전달되었는지 확인 (99개 언어 자동감지 모드)
        called_kwargs = mock_whisper.transcribe.call_args[1]
        self.assertIsNone(called_kwargs.get("language"))

        # 2. 감지된 언어(ja)가 번역기(translator.source)로 즉각 피드백되었는지 확인
        self.assertEqual(mock_translator.source, "ja")
        self.assertEqual(text, "こんにちは")

    def test_groq_and_deepgram_stt_language_auto_dispatch(self):
        """Groq 및 Deepgram API 호출 시 stt_language='auto' 분기 처리 검증"""
        # 1. Groq: stt_language == 'auto' -> data 딕셔너리에 language 키 미포함
        cfg_groq = {"stt_language": "auto", "groq_api_key": "dummy_key"}
        with patch.object(STTWorker, "_load_model"):
            worker_groq = STTWorker(audio_queue=queue.Queue(), config=cfg_groq)

        dummy_audio = np.zeros(1600, dtype=np.float32)
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"text": "Bonjour", "words": []}
            res = worker_groq._transcribe_groq(dummy_audio, "dummy_key")
            self.assertIsNotNone(res)
            post_data = mock_post.call_args[1].get("data", {})
            self.assertNotIn("language", post_data)

        # 2. Deepgram: stt_language == 'auto' -> params 리스트에 ('language', 'multi') 전달
        cfg_dg = {"stt_language": "auto", "deepgram_api_key": "dummy_key"}
        with patch.object(STTWorker, "_load_model"):
            worker_dg = STTWorker(audio_queue=queue.Queue(), config=cfg_dg)

        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "results": {"channels": [{"alternatives": [{"transcript": "Hola", "words": []}]}]}
            }
            res = worker_dg._transcribe_deepgram(dummy_audio, "dummy_key")
            self.assertIsNotNone(res)
            post_params = mock_post.call_args[1].get("params", [])
            param_dict = dict(post_params)
            self.assertEqual(param_dict.get("language"), "multi")

    def test_translator_identical_source_and_target_bypass(self):
        """다국어 모드에서 한국어 음성이 유입되어 source='ko', target='ko'가 되었을 때 불필요한 번역 우회 및 원문 반환 검증"""
        from src.translator import RealtimeTranslator
        translator = RealtimeTranslator(source="ko", target="ko")
        result, engine = translator.translate("안녕하세요. 반갑습니다.")
        self.assertEqual(result, "안녕하세요. 반갑습니다.")
        self.assertEqual(engine, "원문")

    def test_is_multilingual_model_matrix(self):
        """STTModelManager.is_multilingual_model 판별 매트릭스 검증"""
        from src.stt_model_manager import STTModelManager
        # English-only models
        self.assertFalse(STTModelManager.is_multilingual_model("distil-small.en", "local"))
        self.assertFalse(STTModelManager.is_multilingual_model("small.en", "local"))
        self.assertFalse(STTModelManager.is_multilingual_model("medium.en", "local"))
        self.assertFalse(STTModelManager.is_multilingual_model("distil-large-v2", "local"))
        self.assertFalse(STTModelManager.is_multilingual_model("distil-large-v3", "local"))
        self.assertFalse(STTModelManager.is_multilingual_model("distil-large-v3.5", "local"))

        # Multilingual models
        self.assertTrue(STTModelManager.is_multilingual_model("large-v3-turbo", "local"))
        self.assertTrue(STTModelManager.is_multilingual_model("large-v3", "local"))
        self.assertTrue(STTModelManager.is_multilingual_model("large-v2", "local"))
        self.assertTrue(STTModelManager.is_multilingual_model("medium", "local"))
        self.assertTrue(STTModelManager.is_multilingual_model("small", "local"))
        self.assertTrue(STTModelManager.is_multilingual_model("base", "local"))
        self.assertTrue(STTModelManager.is_multilingual_model("tiny", "local"))

        # Cloud providers
        self.assertTrue(STTModelManager.is_multilingual_model("whisper-large-v3-turbo", "groq"))
        self.assertTrue(STTModelManager.is_multilingual_model("nova-3", "deepgram"))

    def test_whisper_distil_large_v35_forces_english(self):
        """distil-large-v3.5는 .en 접미사가 없더라도 영문 전용 모델이므로 language='en' 강제 검증"""
        cfg = {"stt_language": "ja", "device": "cuda", "model_size": "distil-large-v3.5"}
        with patch.object(STTWorker, "_load_model"):
            worker = STTWorker(audio_queue=queue.Queue(), config=cfg)

        mock_translator = MagicMock()
        mock_translator.source = "en"
        worker.translator = mock_translator

        mock_whisper = MagicMock()
        mock_seg = MagicMock()
        mock_seg.text = "Testing audio"
        mock_seg.words = []
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_whisper.transcribe.return_value = ([mock_seg], mock_info)
        worker.model = mock_whisper

        dummy_audio = np.zeros(1600, dtype=np.float32)
        text, _ = worker._transcribe_audio_chunk(dummy_audio)

        called_kwargs = mock_whisper.transcribe.call_args[1]
        self.assertEqual(called_kwargs.get("language"), "en")


if __name__ == "__main__":
    unittest.main()

