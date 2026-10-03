import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import (
    DEFAULT_CONFIG,
    CONTENT_TEMPO_PRESETS,
    uses_local_tempo_vad,
    tempo_scope_caption,
    tempo_preset_desc,
)
from src.stt_engine import STTWorker


class TestTempoPresets(unittest.TestCase):
    def test_presets_structure(self):
        """프리셋 기본 구조 및 6대 프리셋 정의 검증"""
        self.assertIn("content_tempo_preset", DEFAULT_CONFIG)
        self.assertEqual(DEFAULT_CONFIG["content_tempo_preset"], "smart")

        required_presets = ["smart", "youtube", "news", "interview", "movie", "documentary"]
        for p in required_presets:
            self.assertIn(p, CONTENT_TEMPO_PRESETS)
            data = CONTENT_TEMPO_PRESETS[p]
            self.assertIn("name", data)
            self.assertIn("silence_duration_sec", data)
            self.assertIn("max_buffer_sec", data)
            self.assertIn("vad_threshold", data)
            self.assertNotIn("max_clause_words", data)
            self.assertIn("dubbing_speed", data)

    def test_local_scope_helpers(self):
        """Deepgram이면 로컬 VAD 범위에서 제외하고 문구가 갈라진다."""
        local = {"stt_provider": "local"}
        groq = {"stt_provider": "groq"}
        deepgram = {"stt_provider": "deepgram"}
        self.assertTrue(uses_local_tempo_vad(local))
        self.assertTrue(uses_local_tempo_vad(groq))
        self.assertFalse(uses_local_tempo_vad(deepgram))
        self.assertIn("로컬", tempo_scope_caption(local))
        self.assertIn("Deepgram 분절", tempo_scope_caption(deepgram))
        self.assertNotIn("독립", tempo_preset_desc("news", local))
        self.assertIn("독립", tempo_preset_desc("news", deepgram))

    def test_tempo_does_not_retune_speech_segmenter(self):
        """템포 프리셋은 로컬 VAD/더빙 속도만 바꾸고 Deepgram 분절 상한은 고정이다."""
        worker = STTWorker(MagicMock(), config=dict(DEFAULT_CONFIG))
        before = (worker._segmenter.short_wait, worker._segmenter.soft_seconds,
                  worker._segmenter.hard_seconds, worker._segmenter.target_words,
                  worker._segmenter.max_words)
        worker._apply_fixed_preset("youtube")
        worker._apply_fixed_preset("documentary")
        self.assertEqual(before, (worker._segmenter.short_wait, worker._segmenter.soft_seconds,
                                  worker._segmenter.hard_seconds, worker._segmenter.target_words,
                                  worker._segmenter.max_words))
        self.assertFalse(hasattr(worker, "max_clause_words"))

    def test_stt_worker_fixed_preset_application(self):
        """로컬 STT에서는 고정 프리셋이 캡처 VAD와 더빙 속도에 반영된다."""
        mock_queue = MagicMock()
        worker = STTWorker(mock_queue, config=dict(DEFAULT_CONFIG))
        mock_audio = MagicMock()
        mock_dubbing = MagicMock()
        worker.set_audio_capture(mock_audio)
        worker.set_dubbing_engine(mock_dubbing)

        worker._apply_fixed_preset("youtube")
        self.assertEqual(worker.silence_duration_sec, CONTENT_TEMPO_PRESETS["youtube"]["silence_duration_sec"])
        mock_audio.set_tempo_params.assert_called_with(
            silence_sec=CONTENT_TEMPO_PRESETS["youtube"]["silence_duration_sec"],
            max_buffer_sec=CONTENT_TEMPO_PRESETS["youtube"]["max_buffer_sec"],
            vad_threshold=CONTENT_TEMPO_PRESETS["youtube"]["vad_threshold"]
        )
        mock_dubbing.set_smart_speed.assert_called_with(CONTENT_TEMPO_PRESETS["youtube"]["dubbing_speed"])

        worker._apply_fixed_preset("documentary")
        self.assertEqual(worker.silence_duration_sec, CONTENT_TEMPO_PRESETS["documentary"]["silence_duration_sec"])
        mock_audio.set_tempo_params.assert_called_with(
            silence_sec=CONTENT_TEMPO_PRESETS["documentary"]["silence_duration_sec"],
            max_buffer_sec=CONTENT_TEMPO_PRESETS["documentary"]["max_buffer_sec"],
            vad_threshold=CONTENT_TEMPO_PRESETS["documentary"]["vad_threshold"]
        )
        mock_dubbing.set_smart_speed.assert_called_with(CONTENT_TEMPO_PRESETS["documentary"]["dubbing_speed"])

    def test_stt_worker_smart_adaptation(self):
        """STTWorker 스마트 자동 적응 (WPM 측정 및 단계적 파라미터 변환) 검증"""
        mock_queue = MagicMock()
        worker = STTWorker(mock_queue, config=dict(DEFAULT_CONFIG))
        mock_audio = MagicMock()
        mock_dubbing = MagicMock()
        callback_mock = MagicMock()
        worker.set_audio_capture(mock_audio)
        worker.set_dubbing_engine(mock_dubbing)
        worker.tempo_callback = callback_mock

        for _ in range(5):
            worker._update_speech_tempo(210.0, 2.0)

        self.assertGreater(worker.estimated_wpm, 170.0)
        self.assertLessEqual(worker.silence_duration_sec, 0.35)
        mock_dubbing.set_smart_speed.assert_called_with("+25%")
        self.assertTrue(callback_mock.called)
        last_status = callback_mock.call_args[0][0]
        self.assertIn("빠른 템포", last_status)

        for _ in range(15):
            worker._update_speech_tempo(80.0, 3.0)

        self.assertLess(worker.estimated_wpm, 115.0)
        self.assertGreaterEqual(worker.silence_duration_sec, 0.65)
        mock_dubbing.set_smart_speed.assert_called_with("+0%")
        last_status = callback_mock.call_args[0][0]
        self.assertIn("차분한 템포", last_status)

    def test_deepgram_skips_local_vad_but_keeps_dubbing(self):
        """Deepgram 경로에서는 캡처 VAD를 건드리지 않고 더빙 속도만 적용한다."""
        guards = [
            patch.object(STTWorker, '_load_model'),
            patch('src.deepgram_streamer.DeepgramLiveStreamer.start'),
            patch('src.speaker_identifier.SpeakerIdentifier._ensure_model_loaded', return_value=False),
        ]
        for guard in guards:
            guard.start()
            self.addCleanup(guard.stop)

        config = dict(DEFAULT_CONFIG)
        config["stt_provider"] = "deepgram"
        config["deepgram_api_key"] = "test_dg_key"
        worker = STTWorker(MagicMock(), config=config)
        mock_audio = MagicMock()
        mock_dubbing = MagicMock()
        worker.set_audio_capture(mock_audio)
        worker.set_dubbing_engine(mock_dubbing)
        mock_audio.set_tempo_params.reset_mock()
        callback = MagicMock()
        worker.tempo_callback = callback

        worker._apply_fixed_preset("youtube")
        mock_audio.set_tempo_params.assert_not_called()
        mock_dubbing.set_smart_speed.assert_called_with(CONTENT_TEMPO_PRESETS["youtube"]["dubbing_speed"])
        status = callback.call_args[0][0]
        self.assertIn("Deepgram 분절은 독립", status)
        self.assertNotIn("침묵", status)
        self.assertEqual(
            (worker._segmenter.short_wait, worker._segmenter.hard_seconds, worker._segmenter.max_words),
            (0.35, 5.0, 28),
        )

        config["stt_provider"] = "local"
        worker.update_config(config)
        mock_audio.set_tempo_params.assert_called()


if __name__ == '__main__':
    unittest.main()
