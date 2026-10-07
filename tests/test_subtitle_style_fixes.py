import unittest
import os
import sys

# Headless Qt setup
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QCloseEvent
from src.config import DEFAULT_CONFIG
from src.overlay_window import SubtitleOverlay
from src.screen_overlay import ScreenSubtitleOverlay
from src.screen_overlay_manager import ScreenOverlayManager
from src.control_panel import ControlPanel, SubtitlePreviewWidget

app = QApplication.instance() or QApplication(sys.argv)

class TestSubtitleStyleFixes(unittest.TestCase):
    def setUp(self):
        self.config = DEFAULT_CONFIG.copy()

    def test_close_event_no_popup(self):
        """윈도우 닫기 이벤트 발생 시 확인 팝업 없이 즉시 종료되는지 검증"""
        saved = []
        cp = ControlPanel(self.config, overlay=None, audio_thread=None, stt_thread=None, save_config_cb=lambda c: saved.append(c))
        event = QCloseEvent()
        cp.closeEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertTrue(getattr(cp, "_is_closing", False))

    def test_audio_clean_box_and_show_translated(self):
        """음성 번역 자막: 반투명 배경 박스 및 번역문 함께 표시 설정 독립 동작 검증"""
        overlay = SubtitleOverlay(self.config)
        self.assertTrue(overlay._get_clean_box())
        self.assertTrue(overlay._get_show_translated())

        # clean_box toggle
        overlay.set_clean_box(False)
        self.assertFalse(overlay._get_clean_box())
        self.assertFalse(overlay.config.get("audio_clean_box"))
        self.assertFalse(overlay.config.get("clean_box"))

        # show_translated toggle
        overlay.set_show_translated(False)
        self.assertFalse(overlay._get_show_translated())
        self.assertFalse(overlay.config.get("audio_show_translated"))
        self.assertTrue(overlay.label_translated.isHidden())

        overlay.set_show_translated(True)
        self.assertTrue(overlay._get_show_translated())
        self.assertFalse(overlay.label_translated.isHidden())

    def test_screen_clean_box_and_show_translated(self):
        """화면 번역 자막: 반투명 배경 박스 및 번역문 함께 표시 설정 독립 동작 검증"""
        overlay = ScreenSubtitleOverlay(self.config)
        self.assertTrue(overlay._get_clean_box())
        self.assertTrue(overlay._get_show_translated())

        # clean_box toggle
        overlay.set_clean_box(False)
        self.assertFalse(overlay._get_clean_box())
        self.assertFalse(overlay.config.get("screen_clean_box"))

        # show_translated toggle
        overlay.set_show_translated(False)
        self.assertFalse(overlay._get_show_translated())
        self.assertFalse(overlay.config.get("screen_show_translated"))
        self.assertTrue(overlay.label_translated.isHidden())

        overlay.set_show_translated(True)
        self.assertTrue(overlay._get_show_translated())
        self.assertFalse(overlay.label_translated.isHidden())

    def test_screen_overlay_bg_opacity_reflected(self):
        """화면 번역 자막: screen_overlay_bg_opacity가 _get_bg_opacity()에 즉시 반영되는지 검증"""
        overlay = ScreenSubtitleOverlay(self.config)
        self.config["screen_overlay_bg_opacity"] = 0.42
        self.assertEqual(overlay._get_bg_opacity(), 0.42)

        overlay.update_opacity(0.85)
        self.assertEqual(overlay._get_bg_opacity(), 0.85)
        self.assertEqual(self.config["screen_overlay_bg_opacity"], 0.85)

    def test_screen_overlay_manager_show_translated(self):
        """ScreenOverlayManager에서 set_show_translated 호출 시 하위 오버레이 전체에 전파되는지 검증"""
        manager = ScreenOverlayManager(self.config)
        manager.set_show_translated(False)
        self.assertFalse(self.config.get("screen_show_translated"))
        for o in manager.overlays:
            self.assertFalse(o._get_show_translated())

        manager.set_show_translated(True)
        self.assertTrue(self.config.get("screen_show_translated"))
        for o in manager.overlays:
            self.assertTrue(o._get_show_translated())

    def test_control_panel_sync_and_preview(self):
        """컨트롤 패널 토글 및 프리뷰 캔버스 파라미터 전달 검증"""
        saved = []
        cp = ControlPanel(self.config, overlay=None, audio_thread=None, stt_thread=None, save_config_cb=lambda c: saved.append(c))

        self.assertTrue(hasattr(cp, "audio_cb_show_translated"))
        self.assertTrue(hasattr(cp, "screen_cb_show_translated"))

        # 음성 번역 번역문 토글
        cp.on_audio_show_translated_toggled(False)
        self.assertFalse(cp.config["audio_show_translated"])
        self.assertFalse(cp.audio_cb_show_translated.isChecked())

        # 화면 번역 번역문 토글
        cp.on_screen_show_translated_toggled(False)
        self.assertFalse(cp.config["screen_show_translated"])
        self.assertFalse(cp.screen_cb_show_translated.isChecked())

        # 프리뷰 캔버스 상태 확인
        self.assertFalse(cp.preview_canvas.show_translated)
        self.assertFalse(cp.preview_canvas.screen_show_translated)

    def test_clean_box_only_affects_text_line_boxes_not_window_frame(self):
        """반투명 배경 박스(clean_box)는 자막 각 줄 뒤의 검은 막대만을 제어하며 창 프레임 배경을 없애지 않는지 검증"""
        from PyQt6.QtGui import QImage, QColor

        # 1. 음성 오버레이 검증
        cfg = self.config.copy()
        cfg["overlay_bg_opacity"] = 0.60
        cfg["audio_clean_box"] = True
        overlay = SubtitleOverlay(cfg)
        overlay.resize(600, 150)
        overlay.display_subtitle("We should leave before sunset.", "해가 지기 전에 떠나야 해요.", "Google")

        # clean_box = True 일 때 자막 라인별 밀착 박스 목록 계산 검증
        boxes_on = overlay._calc_subtitle_box_rects()
        self.assertTrue(len(boxes_on) > 0)

        # clean_box = False 로 꺼도 창 프레임 배경(opacity 60%)은 정상 렌더링되어야 함
        overlay.set_clean_box(False)
        self.assertFalse(overlay._get_clean_box())

        img = QImage(overlay.width(), overlay.height(), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        overlay.render(img)
        # 창 중앙(자막 텍스트 밖 또는 모서리 안쪽) 픽셀의 알파가 0이 아니어야 함 (창 배경 렌더링 유지)
        pixel_color = QColor(img.pixel(10, 10))
        self.assertGreater(pixel_color.alpha(), 0, "clean_box가 꺼져도 창 프레임 배경은 렌더링되어야 합니다.")

        # 2. 화면 오버레이 검증
        cfg_s = self.config.copy()
        cfg_s["screen_overlay_bg_opacity"] = 0.50
        cfg_s["screen_clean_box"] = True
        s_overlay = ScreenSubtitleOverlay(cfg_s)
        s_overlay.resize(600, 150)
        s_overlay.display_subtitle("We should leave before sunset.", "해가 지기 전에 떠나야 해요.", "Google")

        boxes_s_on = s_overlay._calc_subtitle_box_rects()
        self.assertTrue(len(boxes_s_on) > 0)

        s_overlay.set_clean_box(False)
        self.assertFalse(s_overlay._get_clean_box())

        img_s = QImage(s_overlay.width(), s_overlay.height(), QImage.Format.Format_ARGB32_Premultiplied)
        img_s.fill(0)
        s_overlay.render(img_s)
        pixel_s_color = QColor(img_s.pixel(10, 10))
        self.assertGreater(pixel_s_color.alpha(), 0, "화면 자막 clean_box가 꺼져도 창 프레임 배경은 렌더링되어야 합니다.")

    def test_idle_hide_does_not_desync_subtitle_boxes(self):
        """아이콘 및 컨트롤 숨김(idle) 시 자막 위치와 배경 박스 좌표가 어긋나지 않는지 검증"""
        cfg = self.config.copy()
        cfg["audio_clean_box"] = True
        overlay = SubtitleOverlay(cfg)
        overlay.resize(600, 150)
        overlay.show()
        overlay.display_subtitle("Hello world", "안녕하세요 세계", "Google")

        # 1. size_grip의 retainSizeWhenHidden 속성 검증
        self.assertTrue(overlay.size_grip.sizePolicy().retainSizeWhenHidden(),
                        "size_grip 숨김 시 레이아웃 점프를 막기 위해 retainSizeWhenHidden이 True여야 합니다.")

        y_before = overlay.label_translated.y()
        boxes_before = overlay._calc_subtitle_box_rects()

        # 2. idle 타임아웃 발생 (컨트롤 숨김)
        overlay._on_idle_timeout()

        y_after = overlay.label_translated.y()
        boxes_after = overlay._calc_subtitle_box_rects()

        # 라벨 Y좌표가 점프하지 않고 동일해야 함
        self.assertEqual(y_before, y_after, "idle 상태 전환 시 라벨 위치가 점프하지 않아야 합니다.")
        # 박스 좌표 또한 라벨과 정확히 일치해야 함
        self.assertEqual(len(boxes_before), len(boxes_after))
        if boxes_before and boxes_after:
            self.assertEqual(boxes_before[-1].y(), boxes_after[-1].y(),
                             "idle 전후로 계산된 배경 박스 Y좌표가 일치해야 합니다.")

    def test_two_line_subtitle_boxes_do_not_overlap_and_have_min_gap(self):
        """2줄 이상의 자막 표시 시 배경 박스 간 최소 간격이 확보되고 겹치지 않는지 검증"""
        cfg = self.config.copy()
        cfg["audio_clean_box"] = True
        overlay = SubtitleOverlay(cfg)
        overlay.resize(600, 180)
        overlay.show()

        # 2줄 자막
        overlay.display_subtitle("Line 1\nLine 2", "첫 번째 줄 자막입니다.<br>두 번째 줄 자막입니다.", "Google")
        boxes = overlay._calc_subtitle_box_rects()
        self.assertGreaterEqual(len(boxes), 2, "2줄 자막이므로 최소 2개 이상의 박스가 생성되어야 합니다.")

        for i in range(1, len(boxes)):
            prev = boxes[i - 1]
            curr = boxes[i]
            gap = curr.top() - prev.bottom()
            self.assertGreaterEqual(gap, 5, f"박스 {i-1}과 {i} 사이에 최소 5px 이상의 여백이 있어야 합니다 (현재 gap={gap}px).")

        # 화면 오버레이에서도 2줄 박스 겹침 방지 검증
        cfg_s = self.config.copy()
        cfg_s["screen_clean_box"] = True
        s_overlay = ScreenSubtitleOverlay(cfg_s)
        s_overlay.resize(600, 180)
        s_overlay.show()
        s_overlay.display_subtitle("Original Line 1", "첫 번째 줄 번역문<br>두 번째 줄 번역문", "Google")
        s_boxes = s_overlay._calc_subtitle_box_rects()
        self.assertGreaterEqual(len(s_boxes), 2)
        for i in range(1, len(s_boxes)):
            prev = s_boxes[i - 1]
            curr = s_boxes[i]
            gap = curr.top() - prev.bottom()
            self.assertGreaterEqual(gap, 5, f"화면 자막 박스 간 최소 5px 이상 간격 확보 (현재 gap={gap}px).")


if __name__ == "__main__":
    unittest.main()
