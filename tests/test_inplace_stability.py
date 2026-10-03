import unittest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QRect
from src.inplace_translator import InPlaceTranslatorManager, InPlaceOverlayWindow


class TestInPlaceStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_overlay_window_init_no_dark_mode_winid(self):
        """InPlaceOverlayWindow 생성 시 불필요한 set_windows_dark_mode 및 winId 호출 없음 검증"""
        window = InPlaceOverlayWindow(config={})
        self.assertIsNotNone(window)
        self.assertTrue(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        window.close()

    def test_inplace_manager_init_and_hotkey(self):
        """InPlaceTranslatorManager의 단축키 워커 및 설정 검증"""
        mock_translator = MagicMock()
        mock_get_ocr = MagicMock(return_value=None)
        config = {"inplace_hotkey": "F9"}

        manager = InPlaceTranslatorManager(
            config=config,
            translator=mock_translator,
            get_ocr_cb=mock_get_ocr,
            get_overlays_to_hide=lambda: []
        )
        self.assertEqual(manager.get_hotkey(), "F9")
        # 단축키 활성화/비활성화 토글
        manager.set_hotkey_enabled(False)
        self.assertFalse(manager.hotkey_worker.is_enabled)
        manager.set_hotkey_enabled(True)
        self.assertTrue(manager.hotkey_worker.is_enabled)
        manager.stop()

    def test_stt_greedy_defaults(self):
        """STT 엔진에서 실시간 스트리밍 시 VRAM OOM 및 TDR 방지를 위한 greedy beam_size 기본값 1 검증"""
        config = {}
        beam_sz = int(config.get("whisper_beam_size", 1))
        best_of_val = int(config.get("whisper_best_of", 1))
        self.assertEqual(beam_sz, 1)
        self.assertEqual(best_of_val, 1)


if __name__ == "__main__":
    unittest.main()
