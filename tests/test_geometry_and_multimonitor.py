# -*- coding: utf-8 -*-
import copy
import os
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("WISE_PRODUCT", "kr")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QRect, QPoint, QSize

app = QApplication.instance()
if not app:
    app = QApplication([])

from src.config import DEFAULT_CONFIG
from src.control_panel import ControlPanel, CONTROL_PANEL_MIN_HEIGHT


class TestGeometryAndMultiMonitor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._ducking = patch("src.process_volume.AudioDuckingManager", autospec=True)
        cls._ducking.start()

    @classmethod
    def tearDownClass(cls):
        cls._ducking.stop()

    def setUp(self):
        self._src = patch(
            "src.audio_capture.AudioLoopbackCapture.get_available_capture_sources",
            return_value=[{"id": "default", "type": "device", "name": "default"}],
        )
        self._speakers = patch("soundcard.all_speakers", return_value=[])
        self._src.start()
        self._speakers.start()
        self.addCleanup(self._src.stop)
        self.addCleanup(self._speakers.stop)

    def test_multi_monitor_screen_at_preserved_on_startup(self):
        """다중 모니터 환경(보조 모니터 좌표)에서 실행 시 primaryScreen으로 강제 축소/이동되지 않고 해당 화면에 보존되는지 검증"""
        # 가상의 보조 모니터 Screen 2 (x=1920, y=0, w=1920, h=1080)
        mock_screen2 = MagicMock()
        mock_screen2.availableGeometry.return_value = QRect(1920, 0, 1920, 1080)

        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["control_panel_geometry"] = [2000, 100, 1280, 750]

        with patch.object(QApplication, "screenAt", side_effect=lambda pt: mock_screen2 if pt.x() >= 1920 else None):
            panel = ControlPanel(cfg, None, None, None, lambda c: None)
            try:
                geo = panel.geometry()
                self.assertGreaterEqual(geo.x(), 1920)
                self.assertEqual(geo.width(), 1280)
            finally:
                panel.close()

    def test_disconnected_monitor_fallback_to_primary_center(self):
        """연결 해제된 모니터의 좌표(엉뚱한 화면 밖 좌표)가 저장되어 있던 경우 주 모니터 화면으로 안전 복원되는지 검증"""
        primary_screen = QApplication.primaryScreen()
        avail = primary_screen.availableGeometry()

        cfg = copy.deepcopy(DEFAULT_CONFIG)
        # 존재하지 않는 좌표 (x=9999, y=9999)
        cfg["control_panel_geometry"] = [9999, 9999, 1280, 750]

        with patch.object(QApplication, "screenAt", return_value=None):
            panel = ControlPanel(cfg, None, None, None, lambda c: None)
            try:
                geo = panel.geometry()
                # 9999, 9999에 머무르지 않고 주 화면 영역 내(좌표 시작점이 avail 내)로 안전 복원되어야 함
                self.assertGreaterEqual(geo.x(), avail.left() - 20)
                self.assertLessEqual(geo.x(), avail.right())
                self.assertGreaterEqual(geo.y(), avail.top() - 10)
                self.assertLessEqual(geo.y(), avail.bottom())
            finally:
                panel.close()

    def test_maximized_window_closing_saves_normal_geometry(self):
        """창이 최대화된 상태에서 종료될 때 화면 전체 크기가 아닌 원래 창 크기(normalGeometry)가 저장되어
        다음 실행 시 비정상적으로 거대해지는 현상을 방지하는지 검증"""
        saved_config = {}
        def save_cb(c):
            saved_config.update(c)

        panel = ControlPanel(copy.deepcopy(DEFAULT_CONFIG), None, None, None, save_cb)
        try:
            panel._is_simple_mode = False
            panel.normalGeometry = MagicMock(return_value=QRect(100, 100, 1150, 700))
            panel.isMaximized = MagicMock(return_value=True)
            panel.geometry = MagicMock(return_value=QRect(0, 0, 1920, 1080))

            panel.save_all_settings_before_exit()

            saved_geo = panel.config.get("control_panel_geometry")
            self.assertIsNotNone(saved_geo)
            # 최대화 크기(1920, 1080)가 아니라 normalGeometry(1150, 700)가 저장되어야 함
            self.assertEqual(saved_geo[2], 1150)
            self.assertEqual(saved_geo[3], 700)
            self.assertEqual(saved_geo[0], 100)
            self.assertEqual(saved_geo[1], 100)
        finally:
            panel.close()

    def test_apply_ui_language_in_simple_mode_does_not_break_min_width(self):
        """미니(심플) 모드 활성화 상태에서 언어 변경/적용이 발생해도 창 최소 폭이 1000px 이상으로 폭주하지 않는지 검증"""
        panel = ControlPanel(copy.deepcopy(DEFAULT_CONFIG), None, None, None, lambda c: None)
        try:
            panel.set_simple_mode(True)
            self.assertTrue(panel._is_simple_mode)
            self.assertEqual(panel.minimumWidth(), 360)
            self.assertEqual(panel.maximumWidth(), 520)

            # 언어 적용 함수 호출
            panel._apply_ui_language()

            # 여전히 미니 모드 규격(최소 폭 360, 최대 폭 520)을 유지해야 함
            self.assertEqual(panel.minimumWidth(), 360)
            self.assertEqual(panel.maximumWidth(), 520)
        finally:
            panel.close()

    def test_switch_from_simple_mode_restores_and_clamps_geometry(self):
        """미니 모드에서 기본 모드로 복귀 시 저장된 geometry가 가용 화면 범위를 벗어나지 않도록 안전 보정되는지 검증"""
        mock_screen = MagicMock()
        mock_screen.availableGeometry.return_value = QRect(0, 0, 1400, 900)

        panel = ControlPanel(copy.deepcopy(DEFAULT_CONFIG), None, None, None, lambda c: None)
        try:
            panel.set_simple_mode(True)
            # 이전 풀모드 크기가 가용 화면보다 거대하게 잡혀 있었던 경우 가정
            panel._full_geometry = QRect(0, 0, 2500, 1600)

            with patch.object(QApplication, "screenAt", return_value=mock_screen):
                panel.set_simple_mode(False)
                geo = panel.geometry()
                # 1400x900 화면 크기 내로 안전하게 클램핑되어야 함
                self.assertLessEqual(geo.width(), 1400)
                self.assertLessEqual(geo.height(), 900)
        finally:
            panel.close()


    def test_voice_overlay_disconnected_monitor_fallback(self):
        """음성 자막창이 연결 해제된 모니터의 좌표(화면 밖)에 저장되어 있던 경우 주 화면 내로 안전 복원되는지 검증"""
        primary_screen = QApplication.primaryScreen()
        avail = primary_screen.availableGeometry()

        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["window_geometry"] = [9999, 9999, 900, 140]

        from src.overlay_window import SubtitleOverlay
        with patch.object(QApplication, "screenAt", return_value=None):
            overlay = SubtitleOverlay(cfg)
            try:
                geo = overlay.geometry()
                self.assertGreaterEqual(geo.x(), avail.left() - 20)
                self.assertLessEqual(geo.x(), avail.right())
                self.assertGreaterEqual(geo.y(), avail.top() - 10)
                self.assertLessEqual(geo.y(), avail.bottom())
            finally:
                overlay.close()

    def test_voice_overlay_reset_geometry(self):
        """음성 자막창 위치 초기화 시 안전하게 가용 화면 내에 배치되는지 검증"""
        primary_screen = QApplication.primaryScreen()
        avail = primary_screen.availableGeometry()

        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["window_geometry"] = [100, 100, 800, 140]

        from src.overlay_window import SubtitleOverlay
        overlay = SubtitleOverlay(cfg)
        try:
            overlay.move(9999, 9999)
            overlay.reset_geometry()
            geo = overlay.geometry()
            self.assertGreaterEqual(geo.x(), avail.left() - 20)
            self.assertLessEqual(geo.x(), avail.right())
            self.assertGreaterEqual(geo.y(), avail.top() - 10)
            self.assertLessEqual(geo.y(), avail.bottom())
        finally:
            overlay.close()

    def test_screen_overlay_disconnected_monitor_fallback(self):
        """화면 번역 자막창이 연결 해제된 모니터의 좌표(화면 밖)에 저장되어 있던 경우 주 화면 내로 안전 복원되는지 검증"""
        primary_screen = QApplication.primaryScreen()
        avail = primary_screen.availableGeometry()

        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["screen_overlay_geometry"] = [9999, 9999, 850, 130]

        from src.screen_overlay import ScreenSubtitleOverlay
        with patch.object(QApplication, "screenAt", return_value=None):
            overlay = ScreenSubtitleOverlay(cfg)
            try:
                geo = overlay.geometry()
                self.assertGreaterEqual(geo.x(), avail.left() - 20)
                self.assertLessEqual(geo.x(), avail.right())
                self.assertGreaterEqual(geo.y(), avail.top() - 10)
                self.assertLessEqual(geo.y(), avail.bottom())
            finally:
                overlay.close()

    def test_screen_overlay_reset_geometry(self):
        """화면 번역 자막창 위치 초기화 시 안전하게 가용 화면 내에 배치되는지 검증"""
        primary_screen = QApplication.primaryScreen()
        avail = primary_screen.availableGeometry()

        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["screen_overlay_geometry"] = [100, 100, 850, 130]

        from src.screen_overlay import ScreenSubtitleOverlay
        overlay = ScreenSubtitleOverlay(cfg)
        try:
            overlay.move(9999, 9999)
            overlay.reset_geometry()
            geo = overlay.geometry()
            self.assertGreaterEqual(geo.x(), avail.left() - 20)
            self.assertLessEqual(geo.x(), avail.right())
            self.assertGreaterEqual(geo.y(), avail.top() - 10)
            self.assertLessEqual(geo.y(), avail.bottom())
        finally:
            overlay.close()

    def test_overlays_maximized_exit_saves_normal_geometry(self):
        """자막창이 최대화된 상태에서 종료되더라도 normalGeometry가 저장되는지 검증"""
        saved_config = {}
        def save_cb(c):
            saved_config.update(c)

        panel = ControlPanel(copy.deepcopy(DEFAULT_CONFIG), None, None, None, save_cb)
        try:
            mock_overlay = MagicMock()
            mock_overlay.isMaximized.return_value = True
            mock_overlay.geometry.return_value = QRect(0, 0, 1920, 1080)
            mock_overlay.normalGeometry.return_value = QRect(200, 600, 800, 140)
            mock_overlay.isVisible.return_value = True

            panel.overlay = mock_overlay
            panel.screen_overlay = None

            panel.save_all_settings_before_exit()

            saved_og = panel.config.get("window_geometry")
            self.assertIsNotNone(saved_og)
            self.assertEqual(saved_og[0], 200)
            self.assertEqual(saved_og[1], 600)
            self.assertEqual(saved_og[2], 800)
            self.assertEqual(saved_og[3], 140)
        finally:
            panel.close()

    def test_control_panel_reset_overlay_position_coordinates_center_and_no_overlap(self):
        """컨트롤 패널이 위치한 모니터를 감지하여 화면 중앙 영역에 음성/화면 자막창이
        서로 겹치지 않고 작업표시줄과도 충돌 없이 안전 배치되는지 검증"""
        mock_screen2 = MagicMock()
        mock_screen2.name.return_value = "Screen2"
        mock_screen2.availableGeometry.return_value = QRect(1920, 0, 1920, 1040)
        mock_screen2.geometry.return_value = QRect(1920, 0, 1920, 1080)

        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["control_panel_geometry"] = [2100, 100, 1000, 650]

        from src.overlay_window import SubtitleOverlay
        from src.screen_overlay import ScreenSubtitleOverlay

        voice_overlay = SubtitleOverlay(cfg)
        screen_overlay = ScreenSubtitleOverlay(cfg)
        panel = ControlPanel(cfg, voice_overlay, None, None, lambda c: None, screen_overlay=screen_overlay)
        try:
            # 컨트롤 패널을 Screen2에 배치
            panel.setGeometry(2100, 100, 1000, 650)

            with patch.object(QApplication, "screenAt", side_effect=lambda pt: mock_screen2 if pt.x() >= 1920 else None):
                panel.reset_overlay_position()

                v_geo = voice_overlay.geometry()
                s_geo = screen_overlay.geometry()

                # 1. 두 자막창 모두 컨트롤 패널이 위치한 보조 모니터(x >= 1920)로 이동했는지 확인
                self.assertGreaterEqual(v_geo.x(), 1920)
                self.assertGreaterEqual(s_geo.x(), 1920)

                # 2. 두 자막창이 서로 겹치지 않는지(비교 사각형 intersection이 빈 사각형인지) 확인
                self.assertFalse(v_geo.intersects(s_geo), f"Voice ({v_geo}) and Screen ({s_geo}) overlays overlap!")

                # 3. 화면 번역 자막창이 상단, 음성 번역 자막창이 하단에 정렬되었는지 확인
                self.assertLess(s_geo.bottom(), v_geo.top())

                # 4. 화면 중앙 영역에 배치되어 윈도우 하단 작업표시줄(y=1040)과 최소 100px 이상 여유가 있는지 확인
                self.assertLess(v_geo.bottom(), 1040 - 100)
                self.assertGreater(s_geo.top(), 50)
        finally:
            panel.close()
            voice_overlay.close()
            screen_overlay.close()

    def test_screen_overlay_manager_reset_geometry_stacks_cleanly(self):
        """다중 화면 자막창 관리자(ScreenOverlayManager)에서 reset_geometry 호출 시
        모니터 가용 영역 중앙에 겹치지 않고 스택되는지 검증"""
        from src.screen_overlay_manager import ScreenOverlayManager
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["screen_rois"] = [[100, 100, 300, 200], [500, 100, 300, 200]]

        mgr = ScreenOverlayManager(cfg)
        try:
            self.assertGreaterEqual(len(mgr.overlays), 2)
            mgr.reset_geometry()

            o0_geo = mgr.overlays[0].geometry()
            o1_geo = mgr.overlays[1].geometry()

            # 두 오버레이가 겹치지 않는지 검증
            self.assertFalse(o0_geo.intersects(o1_geo))
            self.assertLess(o0_geo.bottom(), o1_geo.top())
        finally:
            for o in mgr.overlays:
                o.close()


if __name__ == "__main__":
    unittest.main()
