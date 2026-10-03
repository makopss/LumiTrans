import unittest
import sys
import re
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from src.overlay_window import SubtitleOverlay
from src.config import DEFAULT_CONFIG

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)


def plain(html):
    return re.sub(r'<[^>]+>', '', html)


class TestTypewriterOverlay(unittest.TestCase):
    def test_overlay_alignment_and_clean_text_no_cursor(self):
        cfg = dict(DEFAULT_CONFIG)
        cfg["subtitle_alignment"] = "left"
        cfg["typewriter_effect"] = True
        overlay = SubtitleOverlay(cfg)

        self.assertEqual(overlay.label_original.alignment(), Qt.AlignmentFlag.AlignCenter)
        self.assertEqual(overlay.label_translated.alignment(), Qt.AlignmentFlag.AlignCenter)

        overlay.display_preview("Why not? Because I")
        self.assertNotIn("▌", overlay.label_original.text())
        self.assertEqual(plain(overlay.label_original.text()), "Why not? Because I")
        self.assertIn("text-align:center", overlay.label_original.text())

        overlay.display_subtitle("Why not? Because I came up with it.", "제가 고안했기 때문입니다.")
        self.assertNotIn("▌", overlay.label_original.text())
        self.assertEqual(plain(overlay.label_original.text()), "Why not? Because I came up with it.")
        self.assertEqual(plain(overlay.label_translated.text()), "제가 고안했기 때문입니다.")
        self.assertIn("text-align:center", overlay.label_translated.text())
        self.assertFalse(hasattr(overlay, "_typewriter_timer") and overlay._typewriter_timer.isActive())

        cfg["font_size"] = 22
        overlay.config["font_size"] = 22
        overlay._auto_fit_text(
            "This is an extremely long subtitle that would normally cause aggressive font shrinking down to twelve pixels.",
            "이것은 일반적으로 폰트가 12픽셀까지 과도하게 줄어들게 만들 매우 긴 자막 테스트 문장입니다."
        )
        ko_font = overlay.label_translated.font()
        ko_size = ko_font.pointSize() if ko_font.pointSize() > 0 else ko_font.pixelSize()
        self.assertEqual(ko_size, 22)

        overlay.resize(320, overlay.minimumHeight())
        overlay._auto_fit_text(overlay.current_original or "Hello", overlay.current_translated or "안녕하세요", adjust_window=False)
        ko_font = overlay.label_translated.font()
        ko_size = ko_font.pointSize() if ko_font.pointSize() > 0 else ko_font.pixelSize()
        self.assertEqual(ko_size, 22)

    def test_speaker_html_color_is_not_overridden_by_stylesheet(self):
        cfg = dict(DEFAULT_CONFIG)
        cfg["typewriter_effect"] = False
        cfg["speaker_diarization_enabled"] = True
        overlay = SubtitleOverlay(cfg)
        html = "<span style='color: #00E5FF; font-weight: bold;'>[화자 1]</span> Hello there"
        overlay.display_subtitle(html, html)
        self.assertNotRegex(overlay.label_translated.styleSheet(), r'(^|;)\s*color\s*:')
        self.assertNotRegex(overlay.label_original.styleSheet(), r'(^|;)\s*color\s*:')
        self.assertIn("#00E5FF", overlay.label_translated.text())
        self.assertIn("#00E5FF", overlay.label_original.text())
        self.assertIn("[화자 1]", overlay.label_translated.text())
        self.assertIn(cfg["text_color"], overlay.label_translated.text())

    def test_two_line_height_scales_with_font(self):
        cfg = dict(DEFAULT_CONFIG)
        cfg["font_size"] = 18
        cfg["show_original"] = True
        overlay = SubtitleOverlay(cfg)
        h18 = overlay.height()
        preferred18 = overlay._preferred_two_line_overlay_height()
        self.assertGreaterEqual(h18, preferred18 - 2)
        self.assertGreaterEqual(
            overlay.label_translated.minimumHeight(),
            overlay.label_translated.fontMetrics().lineSpacing() * 2,
        )
        self.assertGreaterEqual(
            overlay.label_original.minimumHeight(),
            overlay.label_original.fontMetrics().lineSpacing() * 2,
        )

        overlay.update_font_size(30)
        self.assertGreaterEqual(overlay.height(), overlay._preferred_two_line_overlay_height() - 2)
        self.assertGreater(overlay.height(), h18)


if __name__ == "__main__":
    unittest.main()
