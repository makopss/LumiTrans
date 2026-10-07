import unittest
from unittest.mock import MagicMock
from src.screen_ocr_worker import clean_ocr_text, is_valid_ocr_text, ScreenOCRWorker
from src.config import DEFAULT_CONFIG


class TestScreenOCRNoiseFilter(unittest.TestCase):
    def test_strange_symbols_filtered(self):
        """기호, 박스 드로잉, 기하학 도형 등 비정상 글리프 필터링 검증"""
        # 1. 텍스트 내 장식성 기호 정제
        self.assertEqual(clean_ocr_text("─── Subtitle ───"), "Subtitle")
        self.assertEqual(clean_ocr_text("■ Quest Started ■"), "Quest Started")
        self.assertEqual(clean_ocr_text("◆ Warning! ◆"), "Warning!")
        self.assertEqual(clean_ocr_text("★ Item Acquired ★"), "Item Acquired")

        # 2. 기호만 있는 텍스트는 유효하지 않음으로 판정
        self.assertFalse(is_valid_ocr_text("───"))
        self.assertFalse(is_valid_ocr_text("■ ▲ ◆"))
        self.assertFalse(is_valid_ocr_text("---===---"))
        self.assertFalse(is_valid_ocr_text("/// \\\\ |||"))
        self.assertFalse(is_valid_ocr_text("~`^|"))
        self.assertFalse(is_valid_ocr_text("......"))
        self.assertFalse(is_valid_ocr_text("!#?"))
        self.assertFalse(is_valid_ocr_text("12345"))

    def test_hanzi_hallucination_in_english_mode(self):
        """영어(또는 비CJK) 번역 모드에서 한자 오인식 글리프 완벽 차단 검증"""
        # 영어 텍스트 뒤에 붙은 한자 오인식 아이콘 정제
        self.assertEqual(clean_ocr_text("Press E to interact 冂", source_lang="en"), "Press E to interact")
        self.assertEqual(clean_ocr_text("Talk to Elder 囗", source_lang="en"), "Talk to Elder")

        # 영어 모드에서 한자만 있는 경우 유효하지 않음으로 거부
        self.assertFalse(is_valid_ocr_text("一", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("口", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("冂 囗", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("一十", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("卜", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("丨", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("你好", source_lang="en"))

    def test_suspicious_geometric_hanzi_in_auto_mode(self):
        """자동 감지(auto) 모드에서도 테두리/체력바 모양의 기하학적 한자 파편 차단 검증"""
        self.assertFalse(is_valid_ocr_text("一", source_lang="auto"))
        self.assertFalse(is_valid_ocr_text("口", source_lang="auto"))
        self.assertFalse(is_valid_ocr_text("冂", source_lang="auto"))
        self.assertFalse(is_valid_ocr_text("囗", source_lang="auto"))
        self.assertFalse(is_valid_ocr_text("一十", source_lang="auto"))
        self.assertFalse(is_valid_ocr_text("卜", source_lang="auto"))
        self.assertFalse(is_valid_ocr_text("丨", source_lang="auto"))
        self.assertFalse(is_valid_ocr_text("一一一一", source_lang="auto"))
        self.assertFalse(is_valid_ocr_text("口口", source_lang="auto"))

    def test_legitimate_cjk_and_multilingual_texts(self):
        """정상적인 CJK 및 다국어 텍스트는 정상 승인 검증"""
        self.assertTrue(is_valid_ocr_text("你好", source_lang="auto"))
        self.assertTrue(is_valid_ocr_text("任务开始", source_lang="auto"))
        self.assertTrue(is_valid_ocr_text("敵", source_lang="auto"))
        self.assertTrue(is_valid_ocr_text("こんにちは", source_lang="auto"))
        self.assertTrue(is_valid_ocr_text("전투를 시작합니다", source_lang="auto"))
        self.assertTrue(is_valid_ocr_text("네", source_lang="ko"))
        self.assertTrue(is_valid_ocr_text("응", source_lang="ko"))
        # 한국어 모드에서 한글 없이 고립된 한자는 거부
        self.assertFalse(is_valid_ocr_text("一十", source_lang="ko"))

    def test_latin_consonant_salad_and_single_letters(self):
        """영문 모음 없는 무의미한 자음 나열 및 단일 알파벳 노이즈 차단 검증"""
        self.assertFalse(is_valid_ocr_text("xzkj", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("fghj", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("lll", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("qwp", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("x", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("c", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("v", source_lang="en"))
        self.assertFalse(is_valid_ocr_text("a", source_lang="en"))

        # 정상 영어 문장 및 허용 단어는 통과
        self.assertTrue(is_valid_ocr_text("No.", source_lang="en"))
        self.assertTrue(is_valid_ocr_text("OK", source_lang="en"))
        self.assertTrue(is_valid_ocr_text("Hello there", source_lang="en"))
        self.assertTrue(is_valid_ocr_text("Wait! Come here", source_lang="en"))

    def test_screen_ocr_worker_confidence_filtering(self):
        """ScreenOCRWorker가 신뢰도 미달(0.45 미만) 노이즈 박스를 걸러내는지 검증"""
        config = dict(DEFAULT_CONFIG)
        config.update({
            "source_lang": "en",
            "screen_rois": [[0, 0, 300, 100]],
            "screen_ocr_min_confidence": 0.45
        })
        translator = MagicMock()
        translator.translate.return_value = ("안녕 세상", "Google")
        worker = ScreenOCRWorker(config, translator=translator)

        # Mock OCR 결과: 저신뢰도 노이즈 한자("一", score=0.25)와 고신뢰도 정상 텍스트("Hello world", score=0.95)
        mock_ocr = MagicMock(return_value=([
            ([[0, 0], [10, 0], [10, 10], [0, 10]], "一", 0.25),
            ([[15, 0], [100, 0], [100, 20], [15, 20]], "Hello world", 0.95),
            ([[105, 0], [120, 0], [120, 10], [105, 10]], "口", 0.30),
        ], 0.05))

        # instant 캡처 실행 (capture_screen_area 모킹)
        from unittest.mock import patch
        with patch("src.screen_ocr_worker.capture_screen_area", return_value=MagicMock()):
            with patch.object(worker, "_is_current", return_value=True):
                worker._process_region(((0, 0, 300, 100),), 0, mock_ocr, instant=True)

        # 번역기에는 저신뢰도 "一", "口"가 제거된 "Hello world"만 전달되어야 함
        translator.translate.assert_called_once_with("Hello world")

    def test_speaker_name_extraction_and_protection(self):
        """OCR에서 화자 이름(Nora Treadwell 등)과 콜론이 보존되고 정확히 분리되는지 검증"""
        from src.screen_ocr_worker import extract_speaker_and_dialogue

        # 1. clean_ocr_text가 화자 이름의 콜론과 성씨를 wordninja 오분할로부터 보존하는지 검증
        raw_text = "Nora Treadwell: I believe he created them as a diversion for his fellow Slytherins."
        cleaned = clean_ocr_text(raw_text)
        self.assertIn("Nora Treadwell:", cleaned)
        self.assertNotIn("Tread well", cleaned)
        self.assertIn("Slytherins.", cleaned)

        # 2. extract_speaker_and_dialogue 화자 분리 검증
        spk, body = extract_speaker_and_dialogue(cleaned)
        self.assertEqual(spk, "Nora Treadwell")
        self.assertEqual(body, "I believe he created them as a diversion for his fellow Slytherins.")

        # 3. 다양한 화자 표기 형태 검증 (약어 마침표, 대괄호, 다단어 직함, 한글)
        cases = [
            ("Prof. Fig: We must make haste.", "Prof. Fig", "We must make haste."),
            ("[Nora Treadwell]: Hello world", "Nora Treadwell", "Hello world"),
            ("Headmaster Phineas Nigellus Black: Silence!", "Headmaster Phineas Nigellus Black", "Silence!"),
            ("노라 트레드웰: 시험을 시작합니다.", "노라 트레드웰", "시험을 시작합니다."),
            ("Officer O'Malley: Stop right there!", "Officer O'Malley", "Stop right there!"),
            ("Mary-Jane: Peter, wait!", "Mary-Jane", "Peter, wait!"),
        ]
        for text_in, expected_spk, expected_body in cases:
            s, b = extract_speaker_and_dialogue(text_in)
            self.assertEqual(s, expected_spk, f"Speaker mismatch for '{text_in}'")
            self.assertEqual(b, expected_body, f"Body mismatch for '{text_in}'")

        # 4. 화면 오버레이 format_original_text 및 format_korean_dialogue에서 화자 하이라이트 검증
        from src.screen_overlay import ScreenSubtitleOverlay
        from PyQt6.QtWidgets import QApplication
        import sys

        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)

        cfg = dict(DEFAULT_CONFIG)
        cfg["show_speaker"] = True
        overlay = ScreenSubtitleOverlay(cfg, roi_idx=0)

        formatted_en = overlay.format_original_text("Nora Treadwell: I believe he created them.")
        self.assertIn("Nora Treadwell:", formatted_en)
        self.assertIn("<b style='color: #64B5F6;'>Nora Treadwell:</b>", formatted_en)

        formatted_ko = overlay.format_korean_dialogue("노라 트레드웰: 그가 그것들을 만들었다고 믿어요.")
        self.assertIn("노라 트레드웰:", formatted_ko)
        self.assertIn("<b style='color: #64B5F6;'>노라 트레드웰:</b>", formatted_ko)

        overlay.close()


if __name__ == "__main__":
    unittest.main()
