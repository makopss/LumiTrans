import sys
import unittest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from src.control_panel import ControlPanel
from src.config import DEFAULT_CONFIG


class TestSubtitleStyleSeparation(unittest.TestCase):
    def setUp(self):
        self.config = dict(DEFAULT_CONFIG)
        self.config.update({
            "audio_font_size": 22,
            "screen_font_size": 26,
            "audio_overlay_bg_opacity": 0.50,
            "screen_overlay_bg_opacity": 0.85,
            "audio_subtitle_stroke_width": 1,
            "screen_subtitle_stroke_width": 3,
            "audio_letter_spacing": 0.5,
            "screen_letter_spacing": 2.0,
            "screen_subtitle_duration": 4,
            "audio_show_original": True,
            "screen_show_original": False,
            "audio_click_through": False,
            "screen_click_through": True,
            "audio_clean_text_mode": False,
            "screen_clean_text_mode": True,
            "audio_clean_box": True,
            "screen_clean_box": False,
            "audio_show_speaker": True,
            "screen_show_speaker": False,
            "roi_configs": {
                "0": {
                    "name": "영역 1",
                    "font_size": 26,
                    "opacity": 85,
                    "duration": 4
                }
            }
        })
        self.saved_configs = []

    def _save_cb(self, cfg):
        self.saved_configs.append(dict(cfg))

    def _create_mock_panel(self):
        mock_audio_overlay = MagicMock()
        mock_screen_overlay = MagicMock()

        from PyQt6.QtWidgets import QWidget
        panel = ControlPanel.__new__(ControlPanel)
        QWidget.__init__(panel)
        panel.config = dict(self.config)
        panel.save_config_cb = self._save_cb
        panel.overlay = mock_audio_overlay
        panel.screen_overlay = mock_screen_overlay
        panel.roi_border_manager = MagicMock()
        panel.inplace_manager = MagicMock()

        # Build Tab 4 and retain container reference
        panel.tab_subtitles = panel._build_tab_subtitles()
        return panel, mock_audio_overlay, mock_screen_overlay

    def test_tab4_subtab_structure(self):
        """자막 설정 탭 내 서브탭 버튼 및 독립 스택 패널 구조 검증"""
        panel, _, _ = self._create_mock_panel()
        self.assertTrue(hasattr(panel, "btn_subtab_audio"))
        self.assertTrue(hasattr(panel, "btn_subtab_screen"))
        self.assertTrue(hasattr(panel, "sub_stack"))
        self.assertEqual(panel.sub_stack.count(), 2)

        # 기본은 음성 자막 서브탭 선택 상태
        self.assertEqual(panel._current_subtab, "audio")
        self.assertTrue(panel.btn_subtab_audio.isChecked())
        self.assertFalse(panel.btn_subtab_screen.isChecked())

        # 화면 자막 서브탭으로 전환
        panel._on_subtab_switched("screen")
        self.assertEqual(panel._current_subtab, "screen")
        self.assertFalse(panel.btn_subtab_audio.isChecked())
        self.assertTrue(panel.btn_subtab_screen.isChecked())
        self.assertEqual(panel.sub_stack.currentIndex(), 1)

    def test_audio_font_isolation(self):
        """음성 폰트 조작 시 음성 오버레이에만 반영되고 화면 오버레이는 간섭받지 않아야 함"""
        panel, mock_audio, mock_screen = self._create_mock_panel()

        # 음성 폰트 슬라이더 변경 (22 -> 30)
        panel.on_audio_font_slider_changed(30)
        self.assertEqual(panel.config["audio_font_size"], 30)
        self.assertEqual(panel.audio_font_slider.value(), 30)
        mock_audio.update_font_size.assert_called_with(30)
        mock_screen.update_font_size.assert_not_called()

        # 화면 폰트는 여전히 26 유지
        self.assertEqual(panel.config["screen_font_size"], 26)

    def test_screen_font_isolation(self):
        """화면 폰트 조작 시 화면 오버레이에만 반영되고 음성 오버레이는 간섭받지 않아야 함"""
        panel, mock_audio, mock_screen = self._create_mock_panel()

        # 화면 폰트 슬라이더 변경 (26 -> 36)
        panel.on_screen_font_slider_changed(36)
        self.assertEqual(panel.config["screen_font_size"], 36)
        self.assertEqual(panel.screen_font_slider.value(), 36)
        self.assertEqual(panel.config["roi_configs"]["0"]["font_size"], 36)
        mock_screen.update_font_size.assert_called_with(36)
        mock_audio.update_font_size.assert_not_called()

        # 음성 폰트는 여전히 22 유지
        self.assertEqual(panel.config["audio_font_size"], 22)

    def test_audio_opacity_isolation(self):
        """음성 투명도 조작 시 음성 오버레이에만 반영되고 화면 오버레이는 불변"""
        panel, mock_audio, mock_screen = self._create_mock_panel()

        panel.on_audio_opacity_slider_changed(40)
        self.assertAlmostEqual(panel.config["audio_overlay_bg_opacity"], 0.40, places=2)
        mock_audio.update_opacity.assert_called_with(0.40)
        mock_screen.update_opacity.assert_not_called()

        self.assertAlmostEqual(panel.config["screen_overlay_bg_opacity"], 0.85, places=2)

    def test_screen_opacity_isolation(self):
        """화면 투명도 조작 시 화면 오버레이에만 반영되고 음성 오버레이는 불변"""
        panel, mock_audio, mock_screen = self._create_mock_panel()

        panel.on_screen_opacity_slider_changed(95)
        self.assertAlmostEqual(panel.config["screen_overlay_bg_opacity"], 0.95, places=2)
        self.assertEqual(panel.config["roi_configs"]["0"]["opacity"], 95)
        mock_screen.update_opacity.assert_called_with(0.95)
        mock_audio.update_opacity.assert_not_called()

        self.assertAlmostEqual(panel.config["audio_overlay_bg_opacity"], 0.50, places=2)

    def test_overlay_to_panel_sync_isolation(self):
        """오버레이 창에서 버튼 클릭 시 제어판 슬라이더 동기화 격리 검증"""
        panel, mock_audio, mock_screen = self._create_mock_panel()

        # 1. 음성 오버레이 창에서 A- 눌러 폰트 20으로 동기화 요청
        panel.sync_audio_font_from_overlay(20)
        self.assertEqual(panel.config["audio_font_size"], 20)
        self.assertEqual(panel.audio_font_slider.value(), 20)
        self.assertEqual(panel.config["screen_font_size"], 26)  # 화면 폰트는 변경 없음

        # 2. 화면 오버레이 창에서 A+ 눌러 폰트 32로 동기화 요청
        panel.sync_screen_font_from_overlay(32)
        self.assertEqual(panel.config["screen_font_size"], 32)
        self.assertEqual(panel.screen_font_slider.value(), 32)
        self.assertEqual(panel.config["roi_configs"]["0"]["font_size"], 32)
        self.assertEqual(panel.config["audio_font_size"], 20)  # 음성 폰트는 변경 없음

        # 3. 음성 오버레이 창에서 투명도 30%로 변경
        panel.sync_audio_opacity_from_overlay(30)
        self.assertAlmostEqual(panel.config["audio_overlay_bg_opacity"], 0.30, places=2)
        self.assertAlmostEqual(panel.config["screen_overlay_bg_opacity"], 0.85, places=2)

        # 4. 화면 오버레이 창에서 투명도 70%로 변경
        panel.sync_screen_opacity_from_overlay(70)
        self.assertAlmostEqual(panel.config["screen_overlay_bg_opacity"], 0.70, places=2)
        self.assertAlmostEqual(panel.config["audio_overlay_bg_opacity"], 0.30, places=2)

    def test_toggle_options_isolation(self):
        """원문/화자/클린텍스트/마우스관통 토글 옵션 독립 동작 검증"""
        panel, mock_audio, mock_screen = self._create_mock_panel()

        # 음성 원문 끄기
        panel.on_audio_show_original_toggled(False)
        self.assertFalse(panel.config["audio_show_original"])
        mock_audio.set_show_original.assert_called_with(False)
        mock_screen.set_show_original.assert_not_called()

        # 화면 원문 켜기
        panel.on_screen_show_original_toggled(True)
        self.assertTrue(panel.config["screen_show_original"])
        mock_screen.set_show_original.assert_called_with(True)

        # 음성 마우스 관통 켜기
        panel.on_audio_click_through_toggled(True)
        self.assertTrue(panel.config["audio_click_through"])
        mock_audio.set_click_through.assert_called_with(True)
        mock_screen.set_click_through.assert_not_called()

        # 화면 클린 텍스트 끄기
        panel.on_screen_clean_text_toggled(False)
        self.assertFalse(panel.config["screen_clean_text_mode"])
        mock_screen.set_clean_mode.assert_called_with(False)

    def test_duration_defaults(self):
        """음성 및 화면 기본 자막 유지 시간이 5초로 설정되어 있는지 검증"""
        self.assertEqual(DEFAULT_CONFIG.get("audio_subtitle_duration"), 5)
        self.assertEqual(DEFAULT_CONFIG.get("screen_subtitle_duration"), 5)
        self.assertEqual(DEFAULT_CONFIG.get("subtitle_duration"), 5)

    def test_duration_isolation(self):
        """음성/화면 자막 유지 시간 독립 제어 및 슬라이더 연동 검증"""
        panel, mock_audio, mock_screen = self._create_mock_panel()

        # 음성 유지 시간 UI 존재 및 조작 확인
        self.assertTrue(hasattr(panel, "audio_slider_duration"))
        self.assertTrue(hasattr(panel, "audio_lbl_duration"))
        panel.on_audio_duration_slider_changed(8)
        self.assertEqual(panel.config["audio_subtitle_duration"], 8)
        self.assertEqual(panel.config["subtitle_duration"], 8)
        self.assertEqual(panel.audio_slider_duration.value(), 8)
        self.assertIn("8", panel.audio_lbl_duration.text())
        mock_audio.set_subtitle_duration.assert_called_with(8)
        mock_screen.set_subtitle_duration.assert_not_called()

        # 화면 유지 시간은 여전히 기존 값 유지
        self.assertEqual(panel.config["screen_subtitle_duration"], 4)

        # 화면 유지 시간 조작 확인
        panel.on_screen_duration_slider_changed(15)
        self.assertEqual(panel.config["screen_subtitle_duration"], 15)
        self.assertEqual(panel.config["roi_configs"]["0"]["duration"], 15)
        self.assertEqual(panel.screen_slider_duration.value(), 15)
        self.assertIn("15", panel.screen_lbl_duration.text())
        mock_screen.set_subtitle_duration.assert_called_with(15)
        # 음성 유지 시간은 8로 유지
        self.assertEqual(panel.config["audio_subtitle_duration"], 8)


if __name__ == "__main__":
    unittest.main()

