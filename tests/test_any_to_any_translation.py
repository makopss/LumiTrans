# -*- coding: utf-8 -*-
"""
test_any_to_any_translation.py - 다국어 Any-to-Any 상호 번역 엔진 및 제어 패널 단위 테스트
1. concrete_language 및 get_language_name 함수 검증 (auto 처리 포함)
2. RealtimeTranslator 다국어 설정 초기화 및 동적 갱신 (source_lang, target_lang)
3. DeepL Any-to-Any 정규화 (EN->EN-US, PT->PT-BR, auto 시 source_lang 파라미터 생략)
4. Gemini, Groq, Ollama, Hy-MT2, TranslateGemma 동적 언어 프롬프트 검증
5. 동일 언어 바이패스(원문 반환) 및 auto 시 우회 금지 검증
6. ControlPanel 다국어 콤보박스 (combo_source_lang, combo_target_lang) 동기화 검증
"""

import unittest
from unittest.mock import MagicMock, patch
from src.translator import RealtimeTranslator, concrete_language, get_language_name, LANGUAGE_NAMES


class TestAnyToAnyTranslation(unittest.TestCase):

    def test_concrete_language_and_get_language_name(self):
        """언어 코드 정규화 및 언어 명칭 반환 검증"""
        # concrete_language: 'auto' is treated as fallback
        self.assertEqual(concrete_language("en", "ko"), "en")
        self.assertEqual(concrete_language("ja", "en"), "ja")
        self.assertEqual(concrete_language("", "en"), "en")
        self.assertEqual(concrete_language(None, "en"), "en")
        self.assertEqual(concrete_language("auto", "en"), "en")
        self.assertEqual(concrete_language("AUTO", "en"), "en")

        # get_language_name
        self.assertEqual(get_language_name("en"), "English")
        self.assertEqual(get_language_name("ja"), "Japanese")
        self.assertEqual(get_language_name("ko", native=True), "한국어")
        self.assertEqual(get_language_name("ja", native=True), "일본어")
        self.assertEqual(get_language_name("auto"), "Auto-detected")
        self.assertEqual(get_language_name("auto", native=True), "자동 감지")

    def test_translator_init_and_update_config(self):
        """RealtimeTranslator의 Any-to-Any 초기화 및 update_config 검증"""
        cfg = {"source_lang": "auto", "target_lang": "es"}
        t = RealtimeTranslator(config=cfg, source="en")
        self.assertTrue(t.is_auto_source)
        self.assertEqual(t.source, "en")
        self.assertEqual(t.target, "es")

        # Specific source and target update
        t.update_config({"source_lang": "ja", "target_lang": "fr"})
        self.assertFalse(t.is_auto_source)
        self.assertEqual(t.source, "ja")
        self.assertEqual(t.target, "fr")

        # Switch back to auto: preserves current detected language ja, but is_auto_source is True
        t.update_config({"source_lang": "auto", "target_lang": "de"})
        self.assertTrue(t.is_auto_source)
        self.assertEqual(t.source, "ja")
        self.assertEqual(t.target, "de")

    def test_deepl_payload_normalization(self):
        """DeepL API 대상/출발 언어 정규화 검증"""
        t = RealtimeTranslator(config={"source_lang": "auto", "target_lang": "en"})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"translations": [{"text": "Hello world"}]}

        with patch.object(t.session, "post", return_value=mock_resp) as mock_post:
            res = t._translate_deepl("Bonjour le monde", "fake-api-key:fx")
            self.assertEqual(res, "Hello world")
            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            payload = kwargs["json"]
            # 1. Target "en" must be normalized to "EN-US"
            self.assertEqual(payload["target_lang"], "EN-US")
            # 2. Source "auto" must be omitted from payload
            self.assertNotIn("source_lang", payload)

        # Target "pt" normalized to "PT-BR" and explicit source "ja"
        t.update_config({"source_lang": "ja", "target_lang": "pt"})
        with patch.object(t.session, "post", return_value=mock_resp) as mock_post:
            res = t._translate_deepl("こんにちは", "fake-api-key")
            self.assertEqual(res, "Hello world")
            _, kwargs = mock_post.call_args
            payload = kwargs["json"]
            self.assertEqual(payload["target_lang"], "PT-BR")
            self.assertEqual(payload["source_lang"], "JA")

    def test_gemini_dynamic_prompt(self):
        """Gemini Any-to-Any 프롬프트 생성 검증"""
        t = RealtimeTranslator(config={"source_lang": "auto", "target_lang": "es"})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Hola mundo"}]}}]
        }

        # Case 1: source == "auto"
        with patch.object(t.session, "post", return_value=mock_resp) as mock_post:
            res = t._translate_gemini("Hello world", "fake-key")
            self.assertEqual(res, "Hola mundo")
            _, kwargs = mock_post.call_args
            sys_inst = kwargs["json"]["system_instruction"]["parts"][0]["text"]
            self.assertIn("Spanish subtitle translator", sys_inst)
            self.assertIn("given input speech directly into a single concise Spanish subtitle", sys_inst)

        # Case 2: source == "ja", target == "de"
        t.update_config({"source_lang": "ja", "target_lang": "de"})
        with patch.object(t.session, "post", return_value=mock_resp) as mock_post:
            t._translate_gemini("こんにちは", "fake-key")
            _, kwargs = mock_post.call_args
            sys_inst = kwargs["json"]["system_instruction"]["parts"][0]["text"]
            self.assertIn("German subtitle translator", sys_inst)
            self.assertIn("given Japanese speech directly into a single concise German subtitle", sys_inst)

    def test_groq_dynamic_prompt(self):
        """Groq Any-to-Any 프롬프트 생성 검증"""
        t = RealtimeTranslator(config={"source_lang": "auto", "target_lang": "fr"})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Bonjour"}}]
        }

        # Case 1: source == "auto"
        with patch.object(t.session, "post", return_value=mock_resp) as mock_post:
            res = t._translate_groq("Hello", "fake-key")
            self.assertEqual(res, "Bonjour")
            _, kwargs = mock_post.call_args
            sys_content = kwargs["json"]["messages"][0]["content"]
            self.assertIn("Translate the current speech segment into natural French subtitles", sys_content)

        # Case 2: source == "es", target == "ja"
        t.update_config({"source_lang": "es", "target_lang": "ja"})
        with patch.object(t.session, "post", return_value=mock_resp) as mock_post:
            t._translate_groq("Hola", "fake-key")
            _, kwargs = mock_post.call_args
            sys_content = kwargs["json"]["messages"][0]["content"]
            self.assertIn("Translate the current Spanish speech segment into natural Japanese subtitles", sys_content)

    def test_ollama_and_hymt_direction(self):
        """Ollama 및 Hy-MT 모델 번역 방향(from X into Y / into Y) 검증"""
        t = RealtimeTranslator(config={"source_lang": "auto", "target_lang": "it"})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "Ciao"}

        with patch("src.llm_model_manager.LLMModelManager.is_ollama_installed", return_value=True):
            # Hy-MT model under Ollama with auto source
            with patch.object(t.session, "post", return_value=mock_resp) as mock_post:
                res = t._translate_ollama("Hello", "hy-mt:latest")
                self.assertEqual(res, "Ciao")
                _, kwargs = mock_post.call_args
                prompt = kwargs["json"]["prompt"]
                self.assertIn("Translate the following text into Italian", prompt)

            # Hy-MT with explicit source ja -> it
            t.update_config({"source_lang": "ja", "target_lang": "it"})
            with patch.object(t.session, "post", return_value=mock_resp) as mock_post:
                t._translate_ollama("こんにちは", "hy-mt:latest")
                _, kwargs = mock_post.call_args
                prompt = kwargs["json"]["prompt"]
                self.assertIn("Translate the following text from Japanese into Italian", prompt)

    def test_same_language_bypass_vs_auto(self):
        """동일 언어 번역 생략(원문 반환) 및 auto 소스 처리 검증"""
        # 1. source == "ko", target == "ko": bypasses translation
        t_same = RealtimeTranslator(config={"source_lang": "ko", "target_lang": "ko"})
        text, engine = t_same.translate("안녕하세요")
        self.assertEqual(text, "안녕하세요")
        self.assertEqual(engine, "원문")

        # 2. source == "auto", target == "en": must NOT bypass
        t_auto = RealtimeTranslator(config={"source_lang": "auto", "target_lang": "en"})
        with patch.object(t_auto, "_translate_google_mobile", return_value="Hello"):
            text, engine = t_auto.translate("안녕하세요")
            self.assertEqual(text, "Hello")
            self.assertIn("Google", engine)


class TestControlPanelAnyToAny(unittest.TestCase):

    def test_global_control_panel_source_and_target_combo(self):
        """Global 에디션에서 출발어 및 도착어 콤보박스 동작 검증"""
        import os
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])

        with patch.dict(os.environ, {"WISE_PRODUCT": "global", "QT_QPA_PLATFORM": "offscreen"}), \
             patch("src.audio_capture.AudioLoopbackCapture.get_available_capture_sources", return_value=[]), \
             patch("soundcard.all_speakers", return_value=[]), \
             patch("src.process_volume.AudioDuckingManager", autospec=True):
            from src.control_panel import ControlPanel

            cfg = {
                "source_lang": "auto",
                "target_lang": "en",
                "stt_language": "auto",
                "ui_lang": "en"
            }
            cp = ControlPanel(
                cfg,
                overlay=None,
                audio_thread=None,
                stt_thread=None,
                save_config_cb=lambda c: None,
            )

            # 1. Verify combo_source_lang and combo_target_lang exist
            self.assertTrue(hasattr(cp, "combo_source_lang"))
            self.assertTrue(hasattr(cp, "combo_target_lang"))

            # 2. Verify combo items
            source_items = [cp.combo_source_lang.itemData(i) for i in range(cp.combo_source_lang.count())]
            self.assertIn("auto", source_items)
            for code in LANGUAGE_NAMES:
                self.assertIn(code, source_items)

            # Current selection should be auto
            self.assertEqual(cp.combo_source_lang.currentData(), "auto")

            # 3. Simulate changing source language to 'ja'
            ja_idx = cp.combo_source_lang.findData("ja")
            self.assertGreaterEqual(ja_idx, 0)
            cp.combo_source_lang.setCurrentIndex(ja_idx)

            self.assertEqual(cp.config.get("source_lang"), "ja")
            self.assertEqual(cp.config.get("stt_language"), "ja")

            # 4. Quick select STT language updates combo_source_lang
            cp._on_stt_language_quick_selected("es")
            self.assertEqual(cp.config.get("source_lang"), "es")
            self.assertEqual(cp.config.get("stt_language"), "es")
            self.assertEqual(cp.combo_source_lang.currentData(), "es")

            cp.close()

    def test_screen_ocr_multilingual_filter(self):
        """화면 OCR 다국어 텍스트 필터링 및 정제 검증"""
        from src.screen_ocr_worker import is_valid_ocr_text, clean_ocr_text

        # 1. 다국어 유효 텍스트 판별 (일본어, 중국어, 한국어, 러시아어, 태국어, 아랍어 등)
        self.assertTrue(is_valid_ocr_text("こんにちは、元気ですか？"))
        self.assertTrue(is_valid_ocr_text("敵")) # 단일 CJK 문자
        self.assertTrue(is_valid_ocr_text("はい"))
        self.assertTrue(is_valid_ocr_text("这是一个游戏字幕"))
        self.assertTrue(is_valid_ocr_text("전투를 시작합니다"))
        self.assertTrue(is_valid_ocr_text("Привет, мир!"))
        self.assertTrue(is_valid_ocr_text("สวัสดีครับ"))
        self.assertTrue(is_valid_ocr_text("Hello there"))

        # 2. 노이즈 및 단순 기호 필터링
        self.assertFalse(is_valid_ocr_text(""))
        self.assertFalse(is_valid_ocr_text("..."))
        self.assertFalse(is_valid_ocr_text("!#?"))
        self.assertFalse(is_valid_ocr_text("12345"))
        self.assertFalse(is_valid_ocr_text("a"))

        # 3. clean_ocr_text 정제 검증
        self.assertEqual(clean_ocr_text("Maya:Hello"), "Maya: Hello")
        self.assertEqual(clean_ocr_text("Wait!Come here"), "Wait! Come here")

    def test_exaone_bilingual_guard_and_smart_cascade(self):
        """EXAONE 한-영 전용 모델의 다국어 언어쌍 요청 시 지능형 캐스케이드 검증"""
        from src.llm_model_manager import LLMModelManager

        # 1. 모델 언어쌍 지원 여부
        self.assertTrue(LLMModelManager.is_bilingual_only("exaone"))
        self.assertTrue(LLMModelManager.is_bilingual_only("exaone7b"))
        self.assertFalse(LLMModelManager.is_bilingual_only("hymt"))
        self.assertFalse(LLMModelManager.is_bilingual_only("gemma"))

        self.assertTrue(LLMModelManager.is_language_pair_supported("exaone", "en", "ko"))
        self.assertTrue(LLMModelManager.is_language_pair_supported("exaone", "ko", "en"))
        self.assertTrue(LLMModelManager.is_language_pair_supported("exaone", "auto", "ko"))
        self.assertFalse(LLMModelManager.is_language_pair_supported("exaone", "ja", "ko"))
        self.assertFalse(LLMModelManager.is_language_pair_supported("exaone", "en", "es"))
        self.assertFalse(LLMModelManager.is_language_pair_supported("exaone", "fr", "de"))

        # 2. RealtimeTranslator에서 EXAONE 선택 상태에서 ja -> ko 번역 시 Hy-MT2로 자동 전환
        t = RealtimeTranslator(config={"translation_engine": "exaone", "source_lang": "ja", "target_lang": "ko"})
        
        with patch.object(LLMModelManager, "is_multilingual_model_installed", return_value="hymt"), \
             patch.object(t, "_translate_hymt", return_value="안녕하세요") as mock_hymt:
            translated, engine = t.translate("こんにちは")
            self.assertEqual(translated, "안녕하세요")
            self.assertIn("Hy-MT2", engine)
            self.assertIn("EXAONE 다국어 대체", engine)
            mock_hymt.assert_called_once_with("こんにちは")

        # 3. 로컬 다국어 모델이 없을 경우 Google로 자동 폴백
        t.cache.clear()
        with patch.object(LLMModelManager, "is_multilingual_model_installed", return_value=None), \
             patch.object(t, "_translate_google_mobile", return_value="구글 번역 결과") as mock_google:
            translated, engine = t.translate("さようなら")
            self.assertEqual(translated, "구글 번역 결과")
            self.assertIn("Google", engine)
            self.assertIn("EXAONE 다국어 대체", engine)
            mock_google.assert_called_once()

    def test_stt_script_heuristics(self):
        """STT 결과 텍스트 문자 체계(Script) 기반 정밀 언어 감지 검증"""
        import re

        def detect_script(chunk_text: str, default_lang: str = None) -> str:
            detected_lang = default_lang
            if chunk_text:
                if re.search(r'[\u3040-\u30ff]', chunk_text):
                    detected_lang = "ja"
                elif re.search(r'[\uac00-\ud7af\u1100-\u11ff]', chunk_text):
                    detected_lang = "ko"
                elif re.search(r'[\u0400-\u04ff]', chunk_text):
                    detected_lang = detected_lang if detected_lang in ("ru", "uk", "bg", "be", "sr") else "ru"
                elif re.search(r'[\u0600-\u06ff]', chunk_text):
                    detected_lang = detected_lang if detected_lang in ("ar", "fa", "ur") else "ar"
                elif re.search(r'[\u0e00-\u0e7f]', chunk_text):
                    detected_lang = "th"
                elif re.search(r'[\u0900-\u097f]', chunk_text):
                    detected_lang = "hi"
                elif re.search(r'[\u4e00-\u9fff]', chunk_text) and detected_lang in ("zh", "yue", "en", None):
                    detected_lang = "zh"
            return detected_lang

        self.assertEqual(detect_script("こんにちは", default_lang="en"), "ja")
        self.assertEqual(detect_script("안녕하세요", default_lang="en"), "ko")
        self.assertEqual(detect_script("Привет мир", default_lang="en"), "ru")
        self.assertEqual(detect_script("สวัสดีครับ", default_lang="en"), "th")
        self.assertEqual(detect_script("مرحبا", default_lang="en"), "ar")
        self.assertEqual(detect_script("नमस्ते", default_lang="en"), "hi")
        self.assertEqual(detect_script("你好世界", default_lang="en"), "zh")


if __name__ == "__main__":
    unittest.main()
