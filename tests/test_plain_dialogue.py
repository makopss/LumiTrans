"""실시간 대화창: HTML 화자 태그를 걷어내고 화자·대사만 남긴다."""
import unittest

from src.subtitle_manager import (
    SubtitleEntry, dialogue_speaker_name, plain_dialogue_text,
    recent_screen_dialogues,
)


SPAN_SPEAKER = "<span style='color: #69F0AE; font-weight: bold;'>[화자 3]</span>"
ORIG = (
    f"{SPAN_SPEAKER} the sort of vicarious impact that thinking and ideas "
    "have sometimes poorly applied."
)
TRANS = f"{SPAN_SPEAKER} 때로 잘못 적용되기도 하는, 생각과 아이디어가 미치는 간접적인 영향력 같은 것이죠."


class PlainDialogueTests(unittest.TestCase):
    def test_strips_html_and_duplicate_speaker(self):
        speaker = dialogue_speaker_name("화자 3", ORIG, TRANS)
        self.assertEqual(speaker, "화자 3")
        self.assertEqual(
            plain_dialogue_text(ORIG, speaker),
            "the sort of vicarious impact that thinking and ideas have sometimes poorly applied.",
        )
        self.assertEqual(
            plain_dialogue_text(TRANS, speaker),
            "때로 잘못 적용되기도 하는, 생각과 아이디어가 미치는 간접적인 영향력 같은 것이죠.",
        )

    def test_extracts_speaker_from_markup_when_field_empty(self):
        self.assertEqual(dialogue_speaker_name("", ORIG, TRANS), "화자 3")
        self.assertEqual(dialogue_speaker_name("ROI 1", ORIG, TRANS), "화자 3")

    def test_plain_text_without_markup_is_unchanged(self):
        self.assertEqual(plain_dialogue_text("Hello there.", "화자 1"), "Hello there.")
        self.assertEqual(dialogue_speaker_name("화자 1", "Hello there."), "화자 1")

    def test_recent_screen_dialogues_excludes_audio_and_keeps_two_pairs(self):
        def entry(identifier, source, original, translated, speaker=""):
            return SubtitleEntry(
                id=identifier, timestamp=0, start_sec=0, end_sec=1,
                source=source, orig_text=original, trans_text=translated,
                speaker=speaker,
            )

        entries = [
            entry(1, "screen", "Old screen line", "오래된 대사", "ROI 1"),
            entry(2, "audio", "Audio line", "음성 대사", "화자 1"),
            entry(3, "screen", "[Andy] Hello.", "[Andy] 안녕하세요.", "ROI 1"),
            entry(4, "screen", "Next line", "다음 대사", "ROI 2"),
        ]
        self.assertEqual(
            recent_screen_dialogues(entries),
            [("Andy", "Hello.", "안녕하세요."), ("", "Next line", "다음 대사")],
        )
        self.assertEqual(recent_screen_dialogues(entries, limit=0), [])


if __name__ == "__main__":
    unittest.main()
