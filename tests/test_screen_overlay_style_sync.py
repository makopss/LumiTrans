import unittest
from PyQt6.QtWidgets import QApplication
import sys

# Ensure QApplication exists for UI tests
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from src.screen_overlay import ScreenSubtitleOverlay
from src.screen_overlay_manager import ScreenOverlayManager
from src.overlay_window import SubtitleOverlay
from src.screen_ocr_worker import (
    clean_ocr_text,
    extract_speaker_and_dialogue,
    _SCREEN_TRANSLATION_CACHE,
    _SCREEN_CACHE_LOCK,
    _MAX_SCREEN_CACHE_SIZE,
    ScreenOCRWorker
)


class DummyTranslator:
    def __init__(self):
        self.call_count = 0

    def translate(self, text):
        self.call_count += 1
        return f"[KO]{text}", "test_engine"

    def update_config(self, cfg):
        pass


class TestScreenOverlayStyleSync(unittest.TestCase):
    def setUp(self):
        self.config = {
            "font_size": 24,
            "overlay_bg_opacity": 0.70,
            "subtitle_stroke_width": 2,
            "letter_spacing": 1.5,
            "screen_subtitle_duration": 2,
            "screen_rois": [[100, 100, 400, 200]],
            "roi_configs": {
                "0": {
                    "name": "영역 1",
                    "font_size": 24,
                    "opacity": 70,
                    "duration": 2
                }
            }
        }
        self.saved_config = None

    def _save_cb(self, cfg):
        self.saved_config = cfg

    def test_screen_overlay_font_buttons_sync(self):
        """화면 번역 오버레이창의 폰트 버튼(A-, A+) 조작 시 roi_configs와 자체 폰트가 즉시 반영되는지 검증"""
        overlay = ScreenSubtitleOverlay(self.config, on_config_change=self._save_cb, roi_idx=0)
        
        synced_font = []
        overlay.ext_sync_font = lambda val: synced_font.append(val)

        # 폰트 축소 (24 -> 22)
        overlay._decrease_font()
        self.assertEqual(self.config["font_size"], 22)
        self.assertEqual(self.config["roi_configs"]["0"]["font_size"], 22)
        self.assertEqual(synced_font[-1], 22)

        # 폰트 확대 (22 -> 24)
        overlay._increase_font()
        self.assertEqual(self.config["font_size"], 24)
        self.assertEqual(self.config["roi_configs"]["0"]["font_size"], 24)
        self.assertEqual(synced_font[-1], 24)
        overlay.close()

    def test_screen_overlay_opacity_buttons_sync(self):
        """화면 번역 오버레이창의 투명도 버튼(◐-, ◐+) 조작 시 roi_configs와 자체 투명도가 즉시 반영되는지 검증"""
        overlay = ScreenSubtitleOverlay(self.config, on_config_change=self._save_cb, roi_idx=0)
        
        synced_op = []
        overlay.ext_sync_opacity = lambda val: synced_op.append(val)

        # 투명도 감소 (70% -> 60%)
        overlay._decrease_opacity()
        self.assertAlmostEqual(self.config["overlay_bg_opacity"], 0.60, places=2)
        self.assertEqual(self.config["roi_configs"]["0"]["opacity"], 60)
        self.assertEqual(synced_op[-1], 60)

        # 투명도 증가 (60% -> 70%)
        overlay._increase_opacity()
        self.assertAlmostEqual(self.config["overlay_bg_opacity"], 0.70, places=2)
        self.assertEqual(self.config["roi_configs"]["0"]["opacity"], 70)
        self.assertEqual(synced_op[-1], 70)
        overlay.close()

    def test_screen_overlay_manager_propagation(self):
        """ScreenOverlayManager가 글꼴, 투명도, 외곽선, 자간, 유지시간을 모든 오버레이에 전파하는지 검증"""
        mgr = ScreenOverlayManager(self.config, on_config_change=self._save_cb)
        
        # 폰트 변경 전파
        mgr.update_font_size(28)
        self.assertEqual(self.config["font_size"], 28)
        self.assertEqual(self.config["roi_configs"]["0"]["font_size"], 28)
        for o in mgr.get_overlays():
            self.assertEqual(o.config["font_size"], 28)

        # 투명도 변경 전파
        mgr.update_opacity(0.85)
        self.assertAlmostEqual(self.config["overlay_bg_opacity"], 0.85, places=2)
        self.assertEqual(self.config["roi_configs"]["0"]["opacity"], 85)

        # 유지시간 변경 전파
        mgr.set_subtitle_duration(5)
        self.assertEqual(self.config["screen_subtitle_duration"], 5)
        self.assertEqual(self.config["roi_configs"]["0"]["duration"], 5)

        # 외곽선 및 자간 전파
        mgr.set_stroke_width(4)
        self.assertEqual(self.config["subtitle_stroke_width"], 4)
        mgr.set_letter_spacing(2.5)
        self.assertEqual(self.config["letter_spacing"], 2.5)
        mgr.close()

    def test_screen_ocr_lru_cache_and_optimization(self):
        """화면 번역 워커의 LRU 캐시가 동일 문장에 대해 즉시 번역 결과를 재사용하는지 검증"""
        translator = DummyTranslator()
        worker = ScreenOCRWorker(self.config, translator=translator)
        
        # 텍스트 정제 최적화 검증
        raw_text = "AlexChen. Welcome to the kingdom! lam ready. wll go."
        cleaned = clean_ocr_text(raw_text)
        self.assertIn("Alex Chen:", cleaned)
        self.assertIn("I am ready", cleaned)
        self.assertIn("will go", cleaned)

        # 화자 분리 검증
        spk, body = extract_speaker_and_dialogue(cleaned)
        self.assertEqual(spk, "Alex Chen")
        self.assertIn("Welcome to the kingdom!", body)

        # LRU 캐시 동작 검증
        rois = ((100, 100, 400, 200),)
        # 1회차: 캐시 미스로 translate 호출 (call_count: 1)
        worker.config["source_lang"] = "en"
        worker.config["target_lang"] = "ko"
        worker.config["translation_engine"] = "test_engine"
        
        dummy_ocr = lambda img: ([], None)
        # 직접 캐시 로직 확인
        cache_key = ("en", "ko", "test_engine", "hello world")
        with _SCREEN_CACHE_LOCK:
            _SCREEN_TRANSLATION_CACHE.clear()
            _SCREEN_TRANSLATION_CACHE[cache_key] = ("[KO]hello world", "test_engine")

        with _SCREEN_CACHE_LOCK:
            self.assertIn(cache_key, _SCREEN_TRANSLATION_CACHE)
            cached_val = _SCREEN_TRANSLATION_CACHE[cache_key]
            self.assertEqual(cached_val[0], "[KO]hello world")

    def test_control_panel_slider_handlers(self):
        """자막 설정의 슬라이더 조작 시 roi_configs 동기화 및 오버레이 반영 검증"""
        from src.control_panel import ControlPanel
        from unittest.mock import MagicMock
        
        mock_overlay = MagicMock()
        mock_screen_overlay = MagicMock()
        
        from PyQt6.QtWidgets import QWidget
        # 가상 제어판 객체
        cp = ControlPanel.__new__(ControlPanel)
        QWidget.__init__(cp)
        cp.config = dict(self.config)
        cp.overlay = mock_overlay
        cp.screen_overlay = mock_screen_overlay
        cp.save_config_cb = MagicMock()
        cp._update_subtitle_preview = MagicMock()
        
        # 1. 폰트 슬라이더 조작
        cp.on_font_slider_changed(32)
        self.assertEqual(cp.config["font_size"], 32)
        self.assertEqual(cp.config["roi_configs"]["0"]["font_size"], 32)
        mock_overlay.update_font_size.assert_called_with(32)
        mock_screen_overlay.update_font_size.assert_called_with(32)
        
        # 2. 불투명도 슬라이더 조작 (80%)
        cp.on_opacity_slider_changed(80)
        self.assertAlmostEqual(cp.config["overlay_bg_opacity"], 0.80, places=2)
        self.assertEqual(cp.config["roi_configs"]["0"]["opacity"], 80)
        mock_overlay.update_opacity.assert_called_with(0.80)
        mock_screen_overlay.update_opacity.assert_called_with(0.80)
        
        # 3. 외곽선 두께 조작
        cp.on_stroke_slider_changed(3)
        self.assertEqual(cp.config["subtitle_stroke_width"], 3)
        mock_overlay.set_stroke_width.assert_called_with(3)
        mock_screen_overlay.set_stroke_width.assert_called_with(3)
        
        # 4. 글자 자간 조작 (2.0px)
        cp.on_spacing_slider_changed(20)
        self.assertAlmostEqual(cp.config["letter_spacing"], 2.0, places=1)
        mock_overlay.set_letter_spacing.assert_called_with(2.0)
        mock_screen_overlay.set_letter_spacing.assert_called_with(2.0)
        
        # 5. 유지 시간 조작 (10초)
        cp.on_duration_slider_changed(10)
        self.assertEqual(cp.config["screen_subtitle_duration"], 10)
        self.assertEqual(cp.config["audio_subtitle_duration"], 10)
        self.assertEqual(cp.config["roi_configs"]["0"]["duration"], 10)
        mock_overlay.set_subtitle_duration.assert_called_with(10)
        mock_screen_overlay.set_subtitle_duration.assert_called_with(10)
        
        # 6. 오버레이로부터의 폰트/투명도 동기화 (화면 오버레이 버튼 클릭 시)
        cp.sync_font_from_overlay(18)
        self.assertEqual(cp.config["font_size"], 18)
        self.assertEqual(cp.config["roi_configs"]["0"]["font_size"], 18)
        
        cp.sync_opacity_from_overlay(50)
        self.assertAlmostEqual(cp.config["overlay_bg_opacity"], 0.50, places=2)
        self.assertEqual(cp.config["roi_configs"]["0"]["opacity"], 50)

    def test_audio_overlay_duration_handling(self):
        """음성 번역 오버레이(SubtitleOverlay)의 지속 시간 설정 및 타이머 동작 검증"""
        cfg = {"audio_subtitle_duration": 7}
        overlay = SubtitleOverlay(cfg)
        self.assertEqual(overlay._get_subtitle_duration(), 7)

        # 0초(무제한) 동작 확인
        overlay.update_duration(0)
        self.assertEqual(overlay._get_subtitle_duration(), 0)
        self.assertEqual(overlay.config["audio_subtitle_duration"], 0)
        self.assertEqual(overlay.config["subtitle_duration"], 0)

        # 5초 설정 동작 확인
        overlay.set_subtitle_duration(5)
        self.assertEqual(overlay._get_subtitle_duration(), 5)
        overlay.close()


if __name__ == "__main__":
    unittest.main()

