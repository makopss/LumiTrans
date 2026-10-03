import unittest

from PyQt6.QtWidgets import QApplication

from src.control_panel import (
    BRAND_SLOGAN,
    BRAND_TITLE,
    CONTROL_PANEL_MIN_HEIGHT,
    NAV_TAB_SPECS,
    control_panel_min_width,
    nav_tab_width,
)

app = QApplication.instance()
if not app:
    app = QApplication([])


class TestNavTabSizes(unittest.TestCase):
    def test_tabs_keep_full_labels(self):
        labels = [spec[0] for spec in NAV_TAB_SPECS]
        self.assertEqual(len(NAV_TAB_SPECS), 5)
        self.assertEqual(len({spec[1] for spec in NAV_TAB_SPECS}), 5)
        self.assertTrue(any("음성 번역" in text for text in labels))
        self.assertTrue(any("화면 번역" in text for text in labels))
        self.assertTrue(any("자막 탐색기" in text for text in labels))
        self.assertTrue(any("자막 설정" in text for text in labels))
        self.assertTrue(any("설정" in text for text in labels))

    def test_tab_widths_fit_text(self):
        for text, _ in NAV_TAB_SPECS:
            self.assertGreaterEqual(nav_tab_width(text), 80, text)

    def test_window_min_width_covers_brand_and_tabs(self):
        min_w = control_panel_min_width()
        tab_total = sum(nav_tab_width(text) for text, _ in NAV_TAB_SPECS)
        self.assertGreater(min_w, tab_total)
        self.assertGreater(min_w, 700)
        self.assertEqual(CONTROL_PANEL_MIN_HEIGHT, 800)
        self.assertIn("루미", BRAND_TITLE)
        self.assertTrue(len(BRAND_SLOGAN) > 8)

    def test_tab_palette_matches_tabs(self):
        from src.control_panel import NAV_TAB_PALETTE, nav_tab_stylesheet
        self.assertEqual(len(NAV_TAB_PALETTE), len(NAV_TAB_SPECS))
        sheet = nav_tab_stylesheet(NAV_TAB_PALETTE[0])
        self.assertIn("background-color:", sheet)
        self.assertIn("QPushButton:checked", sheet)
        self.assertNotIn("transparent", sheet)


if __name__ == "__main__":
    unittest.main()
