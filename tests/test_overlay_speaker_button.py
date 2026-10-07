"""Unit tests for overlay speaker button decoupling from dubbing and diarization."""
import os
import sys
import unittest
from PyQt6.QtWidgets import QApplication

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.overlay_window import SubtitleOverlay
from src.screen_overlay import ScreenSubtitleOverlay


class OverlaySpeakerButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_audio_overlay_speaker_button_independent_of_dubbing_and_diarization(self):
        """음성 오버레이: 더빙/화자분리 끔 상태에서도 btn_speaker 상시 표시 및 정상 토글 동작 검증"""
        config = {
            "dubbing_enabled": False,
            "dubbing_source_audio": False,
            "speaker_diarization_enabled": False,
            "show_speaker": True,
            "window_geometry": [100, 100, 800, 150],
        }
        overlay = SubtitleOverlay(config)
        overlay.show()

        # 1. 더빙이 꺼져 있어도 숨겨지지 않고 항상 노출 & 클릭 가능
        self.assertFalse(overlay.btn_speaker.isHidden())
        self.assertTrue(overlay.btn_speaker.isEnabled())
        self.assertTrue(overlay.show_speaker)

        # 2. 클릭(토글) 시 show_speaker가 즉시 반전됨 (화자 분리 설정 여부 무관)
        overlay.toggle_show_speaker()
        self.assertFalse(overlay.show_speaker)
        self.assertFalse(config["show_speaker"])

        # 3. show_speaker=False 시 화자명 필터링 검증
        formatted = overlay._format_speaker_text("[Speaker 1] 안녕하세요 친구들!")
        self.assertEqual(formatted, "안녕하세요 친구들!")

        # 4. 다시 토글 시 show_speaker=True로 복원
        overlay.toggle_show_speaker()
        self.assertTrue(overlay.show_speaker)
        self.assertTrue(config["show_speaker"])

        # 5. 더빙 상태가 켜져도/꺼져도 btn_speaker는 항상 표시 상태 유지
        overlay.update_dubbing_state(True)
        self.assertFalse(overlay.btn_speaker.isHidden())
        overlay.update_dubbing_state(False)
        self.assertFalse(overlay.btn_speaker.isHidden())

        overlay.close()

    def test_screen_overlay_speaker_button_independent_of_dubbing_and_diarization(self):
        """화면 오버레이: 더빙/화자분리 끔 상태에서도 btn_speaker 상시 표시 및 정상 토글 동작 검증"""
        config = {
            "dubbing_enabled": False,
            "dubbing_source_screen": False,
            "speaker_diarization_enabled": False,
            "show_speaker": True,
            "screen_overlay_geometry": [100, 100, 800, 150],
            "screen_rois": [[0, 0, 400, 200]],
        }
        overlay = ScreenSubtitleOverlay(config)
        overlay.show()

        # 1. 더빙이 꺼져 있어도 항상 노출 & 활성화
        self.assertFalse(overlay.btn_speaker.isHidden())
        self.assertTrue(overlay.btn_speaker.isEnabled())
        self.assertTrue(overlay.show_speaker)

        # 2. 토글 동작 검증
        overlay.toggle_show_speaker()
        self.assertFalse(overlay.show_speaker)
        self.assertFalse(config["show_speaker"])

        # 3. 다시 토글 시 True로 복원
        overlay.toggle_show_speaker()
        self.assertTrue(overlay.show_speaker)
        self.assertTrue(config["show_speaker"])

        # 4. 더빙 토글 시에도 btn_speaker 숨김 없이 상시 유지
        overlay.update_dubbing_state(True)
        self.assertFalse(overlay.btn_speaker.isHidden())
        overlay.update_dubbing_state(False)
        self.assertFalse(overlay.btn_speaker.isHidden())

        overlay.close()


if __name__ == "__main__":
    unittest.main()
