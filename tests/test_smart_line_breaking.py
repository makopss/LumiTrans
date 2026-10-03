import unittest
import sys
import re
from PyQt6.QtWidgets import QApplication
from src.subtitle_manager import smart_break_sentences, break_korean_sentences
from src.overlay_window import SubtitleOverlay
from src.screen_overlay import ScreenSubtitleOverlay
from src.config import DEFAULT_CONFIG

# Ensure single QApplication instance
app = QApplication.instance() or QApplication(sys.argv)

class TestSmartLineBreaking(unittest.TestCase):

    def test_korean_short_interjections_no_break(self):
        """짧은 맞장구 및 단문은 1줄로 유지"""
        cases = [
            "응. 응. 응.",
            "네. 알겠습니다.",
            "네. 맞아요.",
            "아. 그렇군요.",
            "음. 글쎄요."
        ]
        for text in cases:
            res = smart_break_sentences(text, linebreak="<br>")
            self.assertNotIn("<br>", res, f"Expected no break for '{text}', got '{res}'")

    def test_english_short_interjections_no_break(self):
        """영어 짧은 맞장구 및 단문도 1줄로 유지"""
        cases = [
            "Yes. Yes. Yes.",
            "Yeah. Right.",
            "Okay. Understood.",
            "No. Not really.",
            "Oh. I see."
        ]
        for text in cases:
            res = smart_break_sentences(text, linebreak="<br>")
            self.assertNotIn("<br>", res, f"Expected no break for '{text}', got '{res}'")

    def test_korean_substantial_sentences_break_to_two_lines(self):
        """의미 있는 분량의 한국어 복수 문장은 최대 2줄로 줄바꿈"""
        text = "오늘 날씨가 정말 좋습니다. 내일도 맑을 예정입니다."
        res = smart_break_sentences(text, linebreak="<br>")
        self.assertEqual(res, "오늘 날씨가 정말 좋습니다.<br>내일도 맑을 예정입니다.")

    def test_english_substantial_sentences_break_to_two_lines(self):
        """의미 있는 분량의 영어 복수 문장은 최대 2줄로 줄바꿈"""
        text = "The weather is really nice today. It will be sunny tomorrow as well."
        res = smart_break_sentences(text, linebreak="<br>")
        self.assertEqual(res, "The weather is really nice today.<br>It will be sunny tomorrow as well.")

    def test_max_lines_clamping(self):
        """3개 이상의 장문이 들어와도 max_lines=2 에 의해 2줄로 제한"""
        ko_text = "첫 번째 문장입니다. 두 번째 긴 문장입니다. 세 번째 문장도 있습니다."
        ko_res = smart_break_sentences(ko_text, linebreak="<br>", max_lines=2)
        self.assertEqual(ko_res.count("<br>"), 1, f"Expected 1 break (2 lines), got '{ko_res}'")

        en_text = "This is the first sentence. This is the second sentence. Here is the third sentence."
        en_res = smart_break_sentences(en_text, linebreak="<br>", max_lines=2)
        self.assertEqual(en_res.count("<br>"), 1, f"Expected 1 break (2 lines), got '{en_res}'")

    def test_abbreviations_and_decimals_protection(self):
        """영어 약어(Dr., Mr., U.S., etc.) 및 소수점 분할 방지"""
        text = "Dr. Smith arrived from the U.S. yesterday. He brought 3.14 meters of cable."
        res = smart_break_sentences(text, linebreak="<br>")
        # Should split at "yesterday." only
        self.assertEqual(res.count("<br>"), 1)
        self.assertTrue(res.startswith("Dr. Smith arrived from the U.S. yesterday.<br>"))

    def test_html_tag_preservation(self):
        """HTML 태그 보존 및 스마트 줄바꿈"""
        text = "<span style='color:red;'>[화자]</span> 반갑습니다. 날씨가 참 좋습니다."
        res = smart_break_sentences(text, linebreak="<br>")
        self.assertIn("<span style='color:red;'>[화자]</span>", res)
        self.assertIn("<br>", res)

    def test_overlay_window_display_subtitle_formatting(self):
        """SubtitleOverlay.display_subtitle 에서 영문/한글 모두 스마트 줄바꿈 적용 확인"""
        cfg = DEFAULT_CONFIG.copy()
        cfg["show_original"] = True
        cfg["auto_start_audio"] = True
        overlay = SubtitleOverlay(cfg)

        orig = "The weather is really nice today. It will be sunny tomorrow as well."
        trans = "오늘 날씨가 정말 좋습니다. 내일도 맑을 예정입니다."

        overlay.display_subtitle(orig, trans)

        # label_original should contain <br>
        self.assertIn("<br>", overlay.label_original.text())
        # label_translated should contain <br>
        self.assertIn("<br>", overlay.label_translated.text())

        # Test short interjections
        overlay.display_subtitle("Yes. Yes. Yes.", "응. 응. 응.")
        self.assertNotIn("<br>", overlay.label_original.text())
        self.assertNotIn("<br>", overlay.label_translated.text())

    def test_screen_overlay_format_methods(self):
        """ScreenSubtitleOverlay 의 format_original_text 및 format_korean_dialogue 검증"""
        cfg = DEFAULT_CONFIG.copy()
        overlay = ScreenSubtitleOverlay(cfg)

        orig_short = "Yes. Yes. Yes."
        self.assertNotIn("<br>", overlay.format_original_text(orig_short))

        orig_long = "The weather is really nice today. It will be sunny tomorrow as well."
        self.assertIn("<br>", overlay.format_original_text(orig_long))

        ko_short = "응. 응. 응."
        self.assertNotIn("<br>", overlay.format_korean_dialogue(ko_short))

        ko_long = "오늘 날씨가 정말 좋습니다. 내일도 맑을 예정입니다."
        self.assertIn("<br>", overlay.format_korean_dialogue(ko_long))


if __name__ == "__main__":
    unittest.main()
