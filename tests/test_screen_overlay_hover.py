import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtWidgets import QApplication

from src.config import DEFAULT_CONFIG
from src.screen_overlay import ScreenSubtitleOverlay


app = QApplication.instance() or QApplication([])


class ScreenOverlayHoverTests(unittest.TestCase):
    def test_controls_remain_visible_over_window_and_hide_after_exit(self):
        overlay = ScreenSubtitleOverlay(copy.deepcopy(DEFAULT_CONFIG))
        overlay.show()
        try:
            enter = QEnterEvent(QPointF(20, 20), QPointF(20, 20), QPointF(20, 20))
            leave = QEvent(QEvent.Type.Leave)
            with patch.object(overlay, "_cursor_over_window", return_value=True):
                overlay.enterEvent(enter)
                self.assertFalse(overlay.idle_timer.isActive())
                overlay._on_idle_timeout()
                self.assertFalse(overlay.is_idle)
                self.assertEqual(overlay.header_opacity_effect.opacity(), 1.0)

                # 자식 버튼 진입으로 온 leave 이벤트는 창 퇴장으로 취급하지 않는다.
                overlay.leaveEvent(leave)
                self.assertTrue(overlay.is_mouse_hovered)
                self.assertFalse(overlay.idle_timer.isActive())

            with patch.object(overlay, "_cursor_over_window", return_value=False):
                overlay.leaveEvent(leave)
                self.assertTrue(overlay.idle_timer.isActive())
                overlay._on_idle_timeout()
                self.assertTrue(overlay.is_idle)
                self.assertEqual(overlay.header_opacity_effect.opacity(), 0.0)
        finally:
            overlay.close()

    def test_inplace_button_in_overlay_header(self):
        overlay = ScreenSubtitleOverlay(copy.deepcopy(DEFAULT_CONFIG))
        try:
            self.assertTrue(hasattr(overlay, 'btn_inplace'))
            self.assertEqual(overlay.btn_inplace.text(), "⚡")
            self.assertIn("전체 화면 번역 실행", overlay.btn_inplace.toolTip())

            called = []
            overlay.set_external_handlers(on_trigger_inplace=lambda: called.append(True))
            overlay.btn_inplace.click()
            self.assertEqual(len(called), 1)

            overlay.update_inplace_hotkey_tooltip("Ctrl+F4")
            self.assertIn("Ctrl+F4", overlay.btn_inplace.toolTip())
        finally:
            overlay.close()


if __name__ == "__main__":
    unittest.main()
