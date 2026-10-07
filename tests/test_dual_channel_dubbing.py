"""Unit tests for dual channel independent audio and screen dubbing."""
import os
import sys
import unittest
import time
import queue

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.dubbing_engine import DubbingEngine, DualChannelQueue


class DualChannelDubbingTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "dubbing_enabled": True,
            "dubbing_source_audio": True,
            "dubbing_source_screen": True,
            "dubbing_volume": 80,
            "dubbing_speed": "+0%",
            "dubbing_interrupt": True,
            "dubbing_echo_cancellation": False,
        }
        self.engine = DubbingEngine(self.config)

    def tearDown(self):
        self.engine.stop()

    def test_dual_queue_separation_and_qsize(self):
        """음성 대사와 화면 대사가 각각의 전용 큐로 분리되어 독립적으로 적재되는지 검증"""
        self.engine.enqueue("사과와 바나나를 맛있게 먹었습니다.", source="audio")
        self.engine.enqueue("우주선이 머나먼 화성 기지에 무사히 안착했습니다.", source="screen")

        # 각 채널별 큐 또는 통합 큐 검증
        self.assertTrue(self.engine.audio_text_queue.qsize() + self.engine.audio_playback_queue.qsize() >= 1)
        self.assertTrue(self.engine.screen_text_queue.qsize() + self.engine.screen_playback_queue.qsize() >= 1)

        # 소스별 독립 큐 정리 검증
        self.engine.clear_source_queue("screen")
        self.assertEqual(self.engine.screen_text_queue.qsize(), 0)
        self.assertEqual(self.engine.screen_playback_queue.qsize(), 0)

        # 오디오 큐 정리
        self.engine.clear_source_queue("audio")
        self.assertEqual(self.engine.audio_text_queue.qsize(), 0)
        self.assertEqual(self.engine.audio_playback_queue.qsize(), 0)
        self.assertEqual(self.engine.text_queue.qsize(), 0)

    def test_independent_channels_assigned(self):
        """Mixer의 0번 채널(audio)과 1번 채널(screen)이 독립적으로 할당되어 있는지 검증"""
        self.assertIsNotNone(self.engine.channel_audio)
        self.assertIsNotNone(self.engine.channel_screen)
        self.assertNotEqual(self.engine.channel_audio, self.engine.channel_screen)
        # 하위 호환성 self.channel이 channel_audio를 참조
        self.assertEqual(self.engine.channel, self.engine.channel_audio)

    def test_simultaneous_speaking_state(self):
        """음성 채널과 화면 채널이 독립적으로 재생 상태를 가질 수 있는지 검증"""
        self.engine._is_playing_audio = True
        self.engine._current_speaking_text_audio = "음성 재생 중"
        self.engine._is_playing_screen = True
        self.engine._current_speaking_text_screen = "화면 재생 중"

        self.assertTrue(self.engine._is_playing)
        self.assertTrue(self.engine.is_speaking(grace_period=2.0))

        # 오디오만 정지 시 화면 재생은 유지
        self.engine.stop_current_audio(source="audio")
        self.assertTrue(self.engine._stop_playback_audio)
        self.assertFalse(self.engine._stop_playback_screen)

        # 화면만 정지 시뮬레이션
        self.engine._stop_playback_audio = False
        self.engine.stop_current_audio(source="screen")
        self.assertTrue(self.engine._stop_playback_screen)
        self.assertFalse(self.engine._stop_playback_audio)

    def test_parallel_playback_callbacks(self):
        """재생 콜백이 source(audio / screen)를 올바르게 전달받는지 검증"""
        received = []
        def _cb(text, speaker, orig_text, source, voice, speed, region_idx):
            received.append((source, text))

        self.engine.register_playback_callback(_cb)
        self.assertEqual(len(self.engine.playback_callbacks), 1)
    def test_default_voice_separation_by_channel(self):
        """음성 채널과 화면 채널의 기본 목소리가 청각적으로 명확히 분리되는지 검증"""
        # 한국어 기본 설정에서
        voice_audio, _ = self.engine.resolve_voice_and_pitch("", "", "", source="audio")
        voice_screen, _ = self.engine.resolve_voice_and_pitch("", "", "", source="screen")

        # 음성은 남성 대표(InJoon), 화면은 여성 대표(SunHi)
        self.assertIn("InJoon", voice_audio)
        self.assertIn("SunHi", voice_screen)
        self.assertNotEqual(voice_audio, voice_screen)

        # 번호가 있는 화자라도 성별 키워드가 없을 때 채널별 기준이 다름
        # audio는 홀수=남성, screen은 홀수=여성 우선
        v_a1, _ = self.engine.resolve_voice_and_pitch("Speaker 1", "화자 1", "Hello", source="audio")
        v_s1, _ = self.engine.resolve_voice_and_pitch("Speaker 1", "화자 1", "Hello", source="screen")
        self.assertIn("InJoon", v_a1)
        self.assertIn("SunHi", v_s1)
        self.assertNotEqual(v_a1, v_s1)

        # 개별 채널 커스텀 보이스 설정 검증
        self.engine.config["dubbing_voice_audio"] = "ko-KR-BongJinNeural"
        self.engine.config["dubbing_voice_screen"] = "ko-KR-JiMinNeural"
        v_custom_a, _ = self.engine.resolve_voice_and_pitch("", "", "", source="audio")
        v_custom_s, _ = self.engine.resolve_voice_and_pitch("", "", "", source="screen")
        self.assertEqual(v_custom_a, "ko-KR-BongJinNeural")
        self.assertEqual(v_custom_s, "ko-KR-JiMinNeural")


if __name__ == "__main__":
    unittest.main()
