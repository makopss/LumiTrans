import unittest
from src.dubbing_engine import DubbingEngine


class TestDubbingJitterAndCrossSource(unittest.TestCase):
    def setUp(self):
        self.config = {
            "dubbing_enabled": True,
            "dubbing_source_audio": True,
            "dubbing_source_screen": True,
        }
        self.engine = DubbingEngine(config=self.config)

    def tearDown(self):
        if hasattr(self.engine, "stop"):
            self.engine.stop()

    def test_text_similarity_helper(self):
        # Exact match
        self.assertTrue(DubbingEngine.is_duplicate_or_similar("안녕하세요", "안녕하세요"))
        # OCR jitter
        s1 = "Fig Fornow 교수, 당신의 문제에 집중하고 주의를 기울이십시오."
        s2 = "Figg Fornow 교수, 당신의 문제에 집중하고 주의를 기울이십시오."
        self.assertTrue(DubbingEngine.is_duplicate_or_similar(s1, s2))
        # Paraphrased / minor variation
        p1 = "당신은 Oliva nder 씨입니다. 그는 뛰어난 장인이자 좋은 친구입니다."
        p2 = "당신은 Oliva 씨를 좋아할 것입니다. 그는 뛰어난 장인이자 좋은 친구입니다."
        self.assertTrue(DubbingEngine.is_duplicate_or_similar(p1, p2, threshold=0.68))
        # Completely distinct sentences
        d1 = "안녕하세요 오늘 날씨가 좋네요"
        d2 = "수업에 늦지 않도록 서둘러야 합니다"
        self.assertFalse(DubbingEngine.is_duplicate_or_similar(d1, d2))

    def test_cross_source_deduplication(self):
        # Audio line enqueued
        self.engine.enqueue(
            "이 벽 안에서 수업에 갈 생각에 너무 신난다 친구.",
            orig_text="Within these walls. I am so excited to go to class, dude.",
            source="audio",
        )
        self.assertEqual(len(self.engine.recent_enqueued_items), 1)

        # Screen line with similar content arrives right after
        self.engine.enqueue(
            "이 벽 안에서. 수업에 갈 생각에 너무 흥분돼 친구.",
            orig_text="Within these walls. I am so excited to go to class dude.",
            source="screen",
        )
        # Should be dropped as duplicate
        self.assertEqual(len(self.engine.recent_enqueued_items), 1)

        # Next distinct sentence arrives
        self.engine.enqueue(
            "안녕하세요 호노라입니다. 제가 지금 조금 정신이 산만해 보인다면 죄송합니다.",
            orig_text="Hello, I am Honora. Pardon me if I seem a little distracted.",
            source="audio",
        )
        self.assertEqual(len(self.engine.recent_enqueued_items), 2)


if __name__ == "__main__":
    unittest.main()
