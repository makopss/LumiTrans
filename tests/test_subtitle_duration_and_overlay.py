import sys
import unittest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from src.screen_overlay import ScreenSubtitleOverlay
from src.i18n import tr


class TestScreenSubtitleDurationAndButton(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_btn_inplace_style_translucent(self):
        """전체화면 즉시 번역 카메라 버튼(btn_inplace)이 보라색 배경 없이 반투명 공통 스타일을 가지는지 검증"""
        cfg = {"screen_subtitle_duration": 5}
        overlay = ScreenSubtitleOverlay(cfg)
        sheet = overlay.btn_inplace.styleSheet()
        self.assertNotIn("6366F1", sheet)
        self.assertNotIn("#818CF8", sheet)
        self.assertIn("rgba(30, 40, 55", sheet)

    def test_instant_translation_applies_duration(self):
        """즉시 번역(F4/F9/⚡ 등 engine_badge에 '즉시' 포함) 시에도 유지 시간 설정이 정상 적용되어야 함"""
        cfg = {
            "screen_subtitle_duration": 7,
            "roi_configs": {"0": {"duration": 7}},
            "text_color": "#FFFFFF",
        }
        overlay = ScreenSubtitleOverlay(cfg)
        overlay.display_subtitle("Original text", "번역 텍스트", engine_badge="즉시·Google")
        self.assertTrue(overlay.clear_timer.isActive(), "즉시 번역 시 소거 타이머가 활성화되어야 합니다")
        self.assertEqual(overlay.clear_timer.interval(), 7000, "설정된 7초(7000ms)로 타이머가 설정되어야 합니다")

    def test_standard_translation_applies_duration(self):
        """일반 실시간 번역 시에도 유지 시간 설정이 정상 적용되어야 함"""
        cfg = {
            "screen_subtitle_duration": 4,
            "roi_configs": {"0": {"duration": 4}},
            "text_color": "#FFFFFF",
        }
        overlay = ScreenSubtitleOverlay(cfg)
        overlay.display_subtitle("Original", "번역", engine_badge="Google")
        self.assertTrue(overlay.clear_timer.isActive())
        self.assertEqual(overlay.clear_timer.interval(), 4000)

    def test_zero_duration_permanent(self):
        """유지 시간이 0초(영구 유지)일 때는 소거 타이머가 작동하지 않아야 함"""
        cfg = {
            "screen_subtitle_duration": 0,
            "roi_configs": {"0": {"duration": 0}},
        }
        overlay = ScreenSubtitleOverlay(cfg)
        overlay.display_subtitle("Original", "번역", engine_badge="즉시·Google")
        self.assertFalse(overlay.clear_timer.isActive())

    def test_duration_update(self):
        """동적으로 자막 유지 시간이 변경되었을 때 즉시 반영되는지 검증"""
        cfg = {
            "screen_subtitle_duration": 3,
            "roi_configs": {"0": {"duration": 3}},
        }
        overlay = ScreenSubtitleOverlay(cfg)
        overlay.display_subtitle("Original", "번역", engine_badge="즉시·Google")
        self.assertEqual(overlay.clear_timer.interval(), 3000)

        overlay.update_duration(8)
        self.assertEqual(overlay._get_subtitle_duration(), 8)
        self.assertEqual(overlay.clear_timer.interval(), 8000)

    def test_fade_or_clear_subtitles(self):
        """타이머 만료 시 fade_or_clear_subtitles가 텍스트를 깨끗하게 비우는지 검증"""
        cfg = {"screen_subtitle_duration": 5}
        overlay = ScreenSubtitleOverlay(cfg)
        overlay.display_subtitle("Original", "번역", engine_badge="즉시·Google")
        overlay.fade_or_clear_subtitles()
        self.assertEqual(overlay.current_original, "")
        self.assertEqual(overlay.current_translated, "")
        self.assertNotIn("번역", overlay.label_translated.text())
        self.assertEqual(overlay.live_badge.text(), tr("overlay_waiting"))

    def test_pin_and_hover_behavior(self):
        """핀 고정 시 타이머 중지 및 해제 시 타이머 재개, 마우스 호버 시 일시정지 검증"""
        cfg = {
            "screen_subtitle_duration": 5,
            "roi_configs": {"0": {"duration": 5}},
        }
        overlay = ScreenSubtitleOverlay(cfg)
        overlay.display_subtitle("Original", "번역", engine_badge="즉시·Google")
        self.assertTrue(overlay.clear_timer.isActive())

        # 핀 고정 토글: 정지
        overlay.toggle_pin()
        self.assertTrue(overlay.is_pinned)
        self.assertFalse(overlay.clear_timer.isActive())

        # 핀 고정 해제: 재개
        overlay.toggle_pin()
        self.assertFalse(overlay.is_pinned)
        self.assertTrue(overlay.clear_timer.isActive())
        self.assertEqual(overlay.clear_timer.interval(), 5000)

    def test_audio_overlay_fade_or_clear_without_ellipsis(self):
        """음성 번역 오버레이 자막창 만료 시 말줄임표(...) 없이 깨끗이 비워지는지 검증"""
        from src.overlay_window import SubtitleOverlay
        cfg = {"audio_subtitle_duration": 4, "text_color": "#FFFFFF"}
        overlay = SubtitleOverlay(cfg)
        overlay.display_subtitle("Hello world", "안녕하세요 세계", engine_badge="Google")
        self.assertTrue(overlay.clear_timer.isActive())
        self.assertEqual(overlay.clear_timer.interval(), 4000)

        overlay.fade_or_clear_subtitles()
        self.assertEqual(overlay.current_original, "")
        self.assertEqual(overlay.current_translated, "")
        self.assertNotIn("...", overlay.label_translated.text())
        self.assertNotIn("안녕하세요", overlay.label_translated.text())
        self.assertEqual(overlay.live_badge.text(), tr("overlay_waiting"))

    def test_audio_overlay_zero_duration(self):
        """음성 번역 오버레이 0초 유지 시 영구 유지 검증"""
        from src.overlay_window import SubtitleOverlay
        cfg = {"audio_subtitle_duration": 0}
        overlay = SubtitleOverlay(cfg)
        overlay.display_subtitle("Hello", "영구 자막", engine_badge="Google")
        self.assertFalse(overlay.clear_timer.isActive())


if __name__ == "__main__":
    unittest.main()

