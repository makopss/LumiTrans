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
            self.assertTrue(
                "전체 화면 번역 실행" in overlay.btn_inplace.toolTip() or
                "Translate entire screen" in overlay.btn_inplace.toolTip()
            )

            called = []
            overlay.set_external_handlers(on_trigger_inplace=lambda: called.append(True))
            overlay.btn_inplace.click()
            self.assertEqual(len(called), 1)

            overlay.update_inplace_hotkey_tooltip("Ctrl+F4")
            self.assertIn("Ctrl+F4", overlay.btn_inplace.toolTip())
        finally:
            overlay.close()

    def test_live_badge_width_restricted(self):
        overlay = ScreenSubtitleOverlay(copy.deepcopy(DEFAULT_CONFIG))
        overlay.show()
        try:
            self.assertEqual(overlay.live_badge.width(), 56)
            overlay.display_subtitle("Deputy Headmistress", "교무부장", engine_badge="즉시·Hy-MT2")
            self.assertEqual(overlay.live_badge.width(), 56)
            self.assertIn("Hy-MT2", overlay.live_badge.text())
        finally:
            overlay.close()

    def test_idle_timeout_preserves_label_original_visibility(self):
        overlay = ScreenSubtitleOverlay(copy.deepcopy(DEFAULT_CONFIG))
        overlay.show()
        try:
            overlay.display_subtitle("Deputy Headmistress", "교무부장", engine_badge="즉시·Hy-MT2")
            self.assertTrue(overlay.label_original.isVisible())
            overlay._on_idle_timeout()
            # Idle 시 label_original이 hide되면 수직 디싱크 및 유령 박스가 발생하므로 반드시 표시 유지되어야 함
            self.assertTrue(overlay.label_original.isVisible())
        finally:
            overlay.close()

    def test_subtitle_boxes_clear_synchronously_on_fade(self):
        overlay = ScreenSubtitleOverlay(copy.deepcopy(DEFAULT_CONFIG))
        overlay.show()
        try:
            overlay.display_subtitle("Deputy Headmistress", "교무부장", engine_badge="즉시·Hy-MT2")
            boxes = overlay._calc_subtitle_box_rects()
            self.assertTrue(len(boxes) > 0, "자막 표시 중에는 배경 박스가 생성되어야 함")

            # 자막 만료 소거
            overlay.fade_or_clear_subtitles()
            empty_boxes = overlay._calc_subtitle_box_rects()
            self.assertEqual(len(empty_boxes), 0, "자막 소거 시 배경 박스도 즉시 완전히 소거되어야 함 (잔류 유령 박스 방지)")
        finally:
            overlay.close()


if __name__ == "__main__":
    unittest.main()
