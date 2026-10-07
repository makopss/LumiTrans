import os
import sys
import unittest
from PyQt6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QApplication.instance() or QApplication(sys.argv)

from src.config import DEFAULT_CONFIG
from src.dubbing_engine import DubbingEngine


class TestDubbingNoSkip(unittest.TestCase):
    def setUp(self):
        self.config = DEFAULT_CONFIG.copy()
        self.config["dubbing_enabled"] = True
        self.config["dubbing_source_audio"] = True
        self.config["dubbing_source_screen"] = True
        self.engine = DubbingEngine(self.config)

    def tearDown(self):
        self.engine.stop()

    def test_duplicate_check_does_not_drop_extended_sentences(self):
        """앞선 대사의 짧은 어휘/어절이 포함되어 있어도 다음 긴 대사가 스킵되지 않는지 검증"""
        # 1. 짧은 확인 어구
        self.assertFalse(self.engine.is_duplicate_or_similar("알겠습니다", "알겠습니다 그럼 다음 페이지로 넘어가겠습니다."))
        self.assertFalse(self.engine.is_duplicate_or_similar("알겠습니다 그럼 다음 페이지로 넘어가겠습니다.", "알겠습니다"))

        # 2. 공통 인사말 포함 문장
        self.assertFalse(self.engine.is_duplicate_or_similar("안녕하세요", "안녕하세요 오늘 날씨가 참 좋습니다."))
        self.assertFalse(self.engine.is_duplicate_or_similar("감사합니다", "감사합니다 발표를 시작하겠습니다."))

        # 3. 실질적 90% 이상 동일 중복은 여전히 차단
        self.assertTrue(self.engine.is_duplicate_or_similar("안녕하세요 오늘 날씨가 참 좋습니다.", "안녕하세요! 오늘 날씨가 참 좋습니다."))
        self.assertTrue(self.engine.is_duplicate_or_similar("네, 알겠습니다.", "네 알겠습니다"))

    def test_enqueue_sequential_dialogues_not_skipped(self):
        """연속으로 유입되는 일상 대화 문장들이 enqueue에서 탈락하지 않고 큐에 적재되는지 검증"""
        d1 = "알겠습니다."
        d2 = "알겠습니다. 그럼 화면을 공유해 주시겠습니까?"
        d3 = "감사합니다. 잘 보입니다."

        self.engine.enqueue(d1, source="audio")
        self.assertEqual(self.engine.audio_text_queue.qsize(), 1)

        # d1의 '알겠습니다'가 포함되어 있어도 d2가 버려지지 않고 정상 큐잉되어야 함
        self.engine.enqueue(d2, source="audio")
        self.assertEqual(self.engine.audio_text_queue.qsize(), 2)

        self.engine.enqueue(d3, source="audio")
        self.assertEqual(self.engine.audio_text_queue.qsize(), 3)

    def test_bracket_only_dialogue_preserved(self):
        """괄호로만 감싸여 번역된 대사도 빈 문자열로 날아가지 않고 정상 대사로 보존되는지 검증"""
        cleaned1 = self.engine._clean_dialogue_text("(네, 잘 알겠습니다.)")
        self.assertIn("잘 알겠습니다", cleaned1)
        self.assertGreaterEqual(len(cleaned1), 2)

        cleaned2 = self.engine._clean_dialogue_text("[화자 1]: (회의를 시작합니다)")
        self.assertIn("회의를 시작합니다", cleaned2)


if __name__ == "__main__":
    unittest.main()
