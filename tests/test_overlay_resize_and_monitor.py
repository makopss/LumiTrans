import unittest
from unittest.mock import Mock
from PyQt6.QtCore import QPoint, QRect, QSize, QEvent, Qt, QCoreApplication
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QApplication

app = QApplication.instance()
if not app:
    app = QApplication([])

from src.overlay_window import (
    SubtitleOverlay, EDGE_NONE, EDGE_LEFT, EDGE_RIGHT, EDGE_TOP, EDGE_BOTTOM
)
from src.screen_overlay import ScreenSubtitleOverlay


class TestOverlayResizeAndMultiMonitor(unittest.TestCase):
    def setUp(self):
        self.config = {
            "window_geometry": [100, 200, 800, 150],
            "screen_overlay_geometry": [100, 200, 800, 150],
            "overlay_bg_opacity": 0.75,
            "font_size": 22
        }
        self.audio_overlay = SubtitleOverlay(self.config)
        self.screen_overlay = ScreenSubtitleOverlay(self.config)

    def tearDown(self):
        self.audio_overlay.is_moving = False
        self.audio_overlay._size_locked = False
        self.screen_overlay.is_moving = False
        self.screen_overlay._size_locked = False
        self.audio_overlay.close()
        self.screen_overlay.close()

    def test_audio_overlay_edge_detection_corners(self):
        w = self.audio_overlay.width()
        h = self.audio_overlay.height()

        self.assertEqual(
            self.audio_overlay._get_resize_edges(QPoint(5, h - 5)),
            EDGE_LEFT | EDGE_BOTTOM
        )
        self.assertEqual(
            self.audio_overlay._get_resize_edges(QPoint(w - 5, h - 5)),
            EDGE_RIGHT | EDGE_BOTTOM
        )

    def test_audio_overlay_edge_detection_borders(self):
        w = self.audio_overlay.width()
        h = self.audio_overlay.height()

        self.assertEqual(
            self.audio_overlay._get_resize_edges(QPoint(3, h // 2)),
            EDGE_LEFT
        )
        self.assertEqual(
            self.audio_overlay._get_resize_edges(QPoint(w - 3, h // 2)),
            EDGE_RIGHT
        )
        self.assertEqual(
            self.audio_overlay._get_resize_edges(QPoint(w // 2, 3)),
            EDGE_TOP
        )
        self.assertEqual(
            self.audio_overlay._get_resize_edges(QPoint(w // 2, h - 3)),
            EDGE_BOTTOM
        )
        self.assertEqual(
            self.audio_overlay._get_resize_edges(QPoint(w // 2, h // 2)),
            EDGE_NONE
        )

    def test_screen_overlay_edge_detection(self):
        w = self.screen_overlay.width()
        h = self.screen_overlay.height()

        self.assertEqual(
            self.screen_overlay._get_resize_edges(QPoint(4, h - 4)),
            EDGE_LEFT | EDGE_BOTTOM
        )
        self.assertEqual(
            self.screen_overlay._get_resize_edges(QPoint(w - 4, h - 4)),
            EDGE_RIGHT | EDGE_BOTTOM
        )
        self.assertEqual(
            self.screen_overlay._get_resize_edges(QPoint(w // 2, h - 2)),
            EDGE_BOTTOM
        )
        self.assertEqual(
            self.screen_overlay._get_resize_edges(QPoint(w // 2, h // 2)),
            EDGE_NONE
        )

    def test_resize_event_ignores_when_is_moving(self):
        self.audio_overlay.base_geometry = [100, 200, 800, 150]
        self.audio_overlay.is_moving = True

        event = QResizeEvent(QSize(1920, 1080), QSize(800, 150))
        self.audio_overlay.resizeEvent(event)

        self.assertEqual(self.audio_overlay.base_geometry, [100, 200, 800, 150])

    def test_handle_screen_changed_preserves_user_dimensions(self):
        min_h = self.audio_overlay.minimumHeight()
        test_w = max(850, self.audio_overlay.minimumWidth())
        self.audio_overlay.base_geometry = [50, 100, test_w, min_h]
        self.audio_overlay._geometry_ready = True

        mock_screen = Mock()
        mock_screen.availableGeometry.return_value = QRect(1920, 0, 1920, 1080)

        self.audio_overlay._handle_screen_changed(mock_screen)
        QCoreApplication.processEvents()

        self.assertEqual(self.audio_overlay.width(), test_w)
        self.assertEqual(self.audio_overlay.height(), min_h)

    def test_screen_overlay_handle_screen_changed(self):
        min_h = self.screen_overlay.minimumHeight()
        test_w = max(950, self.screen_overlay.minimumWidth())
        self.screen_overlay.base_geometry = [50, 100, test_w, min_h]
        self.screen_overlay._geometry_ready = True

        mock_screen = Mock()
        mock_screen.availableGeometry.return_value = QRect(2560, 0, 2560, 1440)

        self.screen_overlay._handle_screen_changed(mock_screen)
        QCoreApplication.processEvents()

        self.assertEqual(self.screen_overlay.width(), test_w)
        self.assertEqual(self.screen_overlay.height(), min_h)

    def test_change_event_recovers_from_maximized_aero_snap(self):
        """When Aero snap tries to maximize window, changeEvent resets window state and restores base_geometry."""
        self.audio_overlay.base_geometry = [100, 200, 800, 150]
        self.audio_overlay.setWindowState = Mock()

        event = QEvent(QEvent.Type.WindowStateChange)
        self.audio_overlay.windowState = Mock(return_value=Qt.WindowState.WindowMaximized)
        self.audio_overlay.changeEvent(event)
        QCoreApplication.processEvents()

        self.audio_overlay.setWindowState.assert_called_with(Qt.WindowState.WindowNoState)

    def test_resize_during_move_restores_locked_size(self):
        ov = self.audio_overlay
        h = max(150, ov.minimumHeight())
        ov.resize(800, h)
        ov.base_geometry = [100, 200, 800, h]
        ov.is_moving = True
        ov._begin_user_move()
        ov.resize(1920, 1080)
        ov._enforce_locked_size()
        QCoreApplication.processEvents()
        self.assertEqual(ov.width(), ov._locked_w)
        self.assertEqual(ov.height(), ov._locked_h)
        self.assertEqual(ov.base_geometry[2:], [800, h])
        ov.is_moving = False
        ov._size_locked = False

    def test_screen_overlay_resize_during_move_restores_locked_size(self):
        ov = self.screen_overlay
        h = max(130, ov.minimumHeight())
        ov.resize(700, h)
        ov.base_geometry = [50, 100, 700, h]
        ov.is_moving = True
        ov._begin_user_move()
        ov.resize(2560, 1440)
        ov._enforce_locked_size()
        QCoreApplication.processEvents()
        self.assertEqual(ov.width(), ov._locked_w)
        self.assertEqual(ov.height(), ov._locked_h)
        ov.is_moving = False
        ov._size_locked = False

    def test_quarter_screen_size_is_treated_as_snap(self):
        ov = self.audio_overlay
        ov.base_geometry = [100, 200, 800, 150]
        mock_screen = Mock()
        mock_screen.availableGeometry.return_value = QRect(0, 0, 1920, 1080)
        mock_screen.geometry.return_value = QRect(0, 0, 1920, 1080)
        ov.screen = Mock(return_value=mock_screen)
        self.assertTrue(ov._looks_like_snap_size(960, 540))
        self.assertTrue(ov._looks_like_snap_size(1920, 1080))
        self.assertFalse(ov._looks_like_snap_size(800, 150))

    def test_overlay_opacity_normalizes_percent_scale(self):
        ov = self.audio_overlay
        ov.update_opacity(90)
        self.assertAlmostEqual(ov.config["overlay_bg_opacity"], 0.9, places=2)
        ov._decrease_opacity()
        self.assertAlmostEqual(ov.config["overlay_bg_opacity"], 0.8, places=2)
        self.screen_overlay.update_opacity(40)
        self.assertAlmostEqual(self.screen_overlay.config["overlay_bg_opacity"], 0.4, places=2)

    def test_overlay_header_buttons_are_large_enough(self):
        for ov in (self.audio_overlay, self.screen_overlay):
            self.assertGreaterEqual(ov.header_widget.height(), 32)
            self.assertGreaterEqual(ov.btn_op_dec.width(), 36)
            self.assertGreaterEqual(ov.btn_op_dec.height(), 26)
            self.assertGreaterEqual(ov.btn_font_inc.width(), 36)

    def test_header_opacity_effect_disables_when_fully_visible(self):
        ov = self.audio_overlay
        ov._set_header_chrome_opacity(1.0)
        self.assertFalse(ov.header_opacity_effect.isEnabled())
        ov._set_header_chrome_opacity(0.4)
        self.assertTrue(ov.header_opacity_effect.isEnabled())

    def test_force_size_ignores_windows_mintrack_jitter(self):
        ov = self.audio_overlay
        h = max(242, ov.minimumHeight())
        ov.resize(800, h)
        QCoreApplication.processEvents()
        self.assertFalse(ov._force_size(800, h - 14))
        self.assertEqual(ov.height(), h)

    def test_overlay_show_with_click_through_does_not_crash(self):
        """click_through=True 상태에서 show() 시 nativeEvent SIP 변환 오류로 프로세스가 다운되지 않는지 검증"""
        cfg = {"click_through": True, "screen_click_through": True}
        from src.overlay_window import SubtitleOverlay
        from src.screen_overlay import ScreenSubtitleOverlay
        ov = SubtitleOverlay(cfg)
        ov.show()
        sov = ScreenSubtitleOverlay(cfg)
        sov.show()
        QCoreApplication.processEvents()
        self.assertTrue(ov.is_click_through)
        self.assertTrue(sov.is_click_through)
        ov.hide()
        sov.hide()

    def test_click_through_toggle_button_unlocks(self):
        """마우스 관통 모드에서 btn_lock 클릭 시 관통이 해제되는지 검증"""
        for ov in [self.audio_overlay, self.screen_overlay]:
            ov.show()
            ov.set_click_through(True)
            self.assertTrue(ov.is_click_through)
            self.assertEqual(ov.btn_lock.text(), "🔓")

            # btn_lock 클릭 시 관통 해제
            ov.btn_lock.click()
            self.assertFalse(ov.is_click_through)
            self.assertEqual(ov.btn_lock.text(), "🔒")
            ov.hide()

    def test_click_through_dpi_hit_test(self):
        """175% 등 High-DPI 환경에서도 헤더 영역은 HTCLIENT(1), 자막 영역은 HTTRANSPARENT(-1) 반환 검증"""
        import struct, ctypes
        for ov in [self.audio_overlay, self.screen_overlay]:
            ov.move(100, 100)
            ov.show()
            ov.set_click_through(True)

            dpr = ov.devicePixelRatio() or 1.75
            btn_local = ov.btn_lock.parentWidget().mapTo(ov, ov.btn_lock.pos()) + QPoint(8, 8)
            btn_global = ov.mapToGlobal(btn_local)
            screen_x = int(round(btn_global.x() * dpr))
            screen_y = int(round(btn_global.y() * dpr))
            lparam = (screen_x & 0xFFFF) | ((screen_y & 0xFFFF) << 16)

            msg_bytes = struct.pack('QIIQQIII', int(ov.winId()), 0x0084, 0, 0, lparam, 0, 0, 0)
            ptr = ctypes.cast(ctypes.c_char_p(msg_bytes), ctypes.c_void_p).value

            res = ov.nativeEvent(b'windows_generic_MSG', ptr)
            self.assertEqual(res, (True, 1), f"Header should return (True, 1), got {res}")

            # 자막 영역 테스트 (HTTRANSPARENT)
            sub_local = QPoint(ov.width() // 2, ov.height() - 20)
            sub_global = ov.mapToGlobal(sub_local)
            sub_x = int(round(sub_global.x() * dpr))
            sub_y = int(round(sub_global.y() * dpr))
            sub_lparam = (sub_x & 0xFFFF) | ((sub_y & 0xFFFF) << 16)

            sub_msg = struct.pack('QIIQQIII', int(ov.winId()), 0x0084, 0, 0, sub_lparam, 0, 0, 0)
            sub_ptr = ctypes.cast(ctypes.c_char_p(sub_msg), ctypes.c_void_p).value
            sub_res = ov.nativeEvent(b'windows_generic_MSG', sub_ptr)
            self.assertEqual(sub_res, (True, -1), f"Subtitle area should return (True, -1), got {sub_res}")
            ov.hide()

    def test_click_through_idle_opacity_and_wake_up(self):
        """관통 모드에서 idle 시 은은한 불투명도(0.25) 유지 및 호버 시 1.0 복원 검증"""
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QPointF
        for ov in [self.audio_overlay, self.screen_overlay]:
            ov.show()
            ov.set_click_through(True)

            ov._on_idle_timeout()
            self.assertTrue(ov.is_idle)
            op = ov.header_opacity_effect.opacity() if hasattr(ov, 'header_opacity_effect') else 0.0
            self.assertAlmostEqual(op, 0.25, delta=0.05)

            btn_local = ov.btn_lock.parentWidget().mapTo(ov, ov.btn_lock.pos()) + QPoint(8, 8)
            btn_local_f = QPointF(float(btn_local.x()), float(btn_local.y()))
            btn_global_f = QPointF(float(ov.mapToGlobal(btn_local).x()), float(ov.mapToGlobal(btn_local).y()))
            evt = QMouseEvent(QMouseEvent.Type.MouseMove, btn_local_f, btn_global_f, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
            ov.mouseMoveEvent(evt)
            self.assertGreaterEqual(ov.header_opacity_effect.opacity(), 0.99)
            ov.hide()


if __name__ == '__main__':
    unittest.main()


