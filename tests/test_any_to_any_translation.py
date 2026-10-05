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


class TestMultilingualDubbing(unittest.TestCase):

    def test_language_voice_matrix_coverage(self):
        """15개 전 언어 Edge-TTS 음성 매트릭스 등록 및 필수 키 무결성 검증"""
        from src.dubbing_engine import LANGUAGE_VOICE_MATRIX, get_voice_matrix_for_target, get_available_voices

        expected_langs = ["ko", "en", "ja", "zh", "es", "fr", "de", "pt", "ru", "it", "vi", "th", "id", "ar", "hi"]
        for lang in expected_langs:
            self.assertIn(lang, LANGUAGE_VOICE_MATRIX)
            entry = LANGUAGE_VOICE_MATRIX[lang]
            self.assertIn("male_default", entry)
            self.assertIn("female_default", entry)
            self.assertIn("male_alt", entry)
            self.assertIn("female_alt", entry)
            self.assertIn("names", entry)
            self.assertGreaterEqual(len(entry["names"]), 2)

        # get_voice_matrix_for_target
        en_matrix = get_voice_matrix_for_target("en")
        self.assertEqual(en_matrix["male_default"], "en-US-GuyNeural")
        self.assertEqual(en_matrix["female_default"], "en-US-JennyNeural")

        ja_matrix = get_voice_matrix_for_target("ja")
        self.assertEqual(ja_matrix["male_default"], "ja-JP-KeitaNeural")
        self.assertEqual(ja_matrix["female_default"], "ja-JP-NanamiNeural")

        # Unknown fallback
        fallback = get_voice_matrix_for_target("unknown_lang")
        self.assertEqual(fallback["male_default"], "ko-KR-InJoonNeural")

        # get_available_voices
        voices_es = get_available_voices("es")
        self.assertTrue(any(v[0] == "auto" for v in voices_es))
        self.assertTrue(any("Alvaro" in v[1] for v in voices_es))

    def test_dubbing_engine_dynamic_voice_resolution(self):
        """도착 언어(Target Language)별 화자 성별 및 번호 기반 보이스/피치 라우팅 검증"""
        from src.dubbing_engine import DubbingEngine

        engine = DubbingEngine({"dubbing_enabled": False, "target_lang": "en"})

        # English routing:
        # Speaker 1 -> male default GuyNeural, pitch offset -10Hz
        v1, p1 = engine.resolve_voice_and_pitch("Speaker 1", "Speaker 1", "Hello there")
        self.assertEqual(v1, "en-US-GuyNeural")
        self.assertEqual(p1, "-10Hz")

        # Speaker 2 -> female default JennyNeural, pitch offset +0Hz
        v2, p2 = engine.resolve_voice_and_pitch("Speaker 2", "Speaker 2", "Nice to meet you")
        self.assertEqual(v2, "en-US-JennyNeural")
        self.assertEqual(p2, "+0Hz")

        # Speaker 3 -> male alt ChristopherNeural, pitch offset +8Hz
        v3, p3 = engine.resolve_voice_and_pitch("Speaker 3", "Speaker 3", "Look out!")
        self.assertEqual(v3, "en-US-ChristopherNeural")
        self.assertEqual(p3, "+8Hz")

        # Speaker 4 -> female alt AriaNeural, pitch offset -5Hz
        v4, p4 = engine.resolve_voice_and_pitch("Speaker 4", "Speaker 4", "I understand")
        self.assertEqual(v4, "en-US-AriaNeural")
        self.assertEqual(p4, "-5Hz")

        # Context heuristics: female keyword in text
        v_fem, _ = engine.resolve_voice_and_pitch("Speaker 1", "Speaker 1", "She is a young lady")
        self.assertEqual(v_fem, "en-US-JennyNeural")

        # Dynamic language change to Japanese
        engine.update_config({"target_lang": "ja"})
        v_ja1, _ = engine.resolve_voice_and_pitch("Speaker 1", "Speaker 1", "こんにちは")
        self.assertEqual(v_ja1, "ja-JP-KeitaNeural")
        v_ja2, _ = engine.resolve_voice_and_pitch("Speaker 2", "Speaker 2", "はじめまして")
        self.assertEqual(v_ja2, "ja-JP-NanamiNeural")

        # Dynamic language change to Spanish
        engine.update_config({"target_lang": "es"})
        v_es1, _ = engine.resolve_voice_and_pitch("Speaker 1", "Speaker 1", "Hola amigo")
        self.assertEqual(v_es1, "es-ES-AlvaroNeural")

        # Manual voice override matching vs mismatching target_lang
        engine.update_config({
            "target_lang": "ja",
            "speaker_voices": {"Speaker 1": "ja-JP-DaichiNeural", "Speaker 2": "ko-KR-SunHiNeural"}
        })
        # Matching locale prefix ("ja") -> used directly
        v_override_match, _ = engine.resolve_voice_and_pitch("Speaker 1", "Speaker 1", "こんにちは")
        self.assertEqual(v_override_match, "ja-JP-DaichiNeural")
        # Mismatched locale prefix ("ko" when target is "ja") -> auto adapts to Japanese native voice
        v_override_mismatch, _ = engine.resolve_voice_and_pitch("Speaker 2", "Speaker 2", "はい")
        self.assertEqual(v_override_mismatch, "ja-JP-NanamiNeural")

        engine.stop()

    def test_dubbing_dialogue_cleaning_multilingual(self):
        """다국어 화자명 접두사 및 자막 노이즈 정제 검증"""
        from src.dubbing_engine import DubbingEngine

        engine = DubbingEngine({"dubbing_enabled": False})

        # Multi-script prefixes
        self.assertEqual(engine._clean_dialogue_text("Alex: Welcome everyone"), "Welcome everyone")
        self.assertEqual(engine._clean_dialogue_text("알렉스: 어서오세요"), "어서오세요")
        self.assertEqual(engine._clean_dialogue_text("田中: こんにちは"), "こんにちは")
        self.assertEqual(engine._clean_dialogue_text("Алекс: Здравствуйте"), "Здравствуйте")
        self.assertEqual(engine._clean_dialogue_text("<b>Bold text</b> [gasp] (whisper)"), "Bold text")

        engine.stop()

    def test_control_panel_target_lang_dubbing_sync(self):
        """제어 패널에서 도착 언어 변경 시 더빙 엔진 설정 갱신 및 큐 플러시 검증"""
        import os
        from PyQt6.QtWidgets import QApplication
        from src.control_panel import ControlPanel

        app = QApplication.instance() or QApplication([])

        mock_dubbing = MagicMock()
        mock_save = MagicMock()
        cfg = {"source_lang": "auto", "target_lang": "ko", "ui_lang": "ko"}

        with patch.dict(os.environ, {"WISE_PRODUCT": "global", "QT_QPA_PLATFORM": "offscreen"}), \
             patch("src.audio_capture.AudioLoopbackCapture.get_available_capture_sources", return_value=[]), \
             patch("soundcard.all_speakers", return_value=[]), \
             patch("src.process_volume.AudioDuckingManager", autospec=True):
            cp = ControlPanel(
                cfg,
                overlay=None,
                audio_thread=None,
                stt_thread=None,
                save_config_cb=mock_save,
                dubbing_engine=mock_dubbing
            )

            # Trigger target language change to 'ja'
            idx = cp.combo_target_lang.findData("ja")
            self.assertGreaterEqual(idx, 0)
            cp.combo_target_lang.setCurrentIndex(idx)
            self.assertEqual(cp.config["target_lang"], "ja")
            mock_dubbing.update_config.assert_called()
            mock_dubbing.clear_queue.assert_called()

            cp.close()


class TestPhase4GlobalUXAndI18n(unittest.TestCase):

    def test_multilingual_smart_line_breaking(self):
        """다국어 자막(일·중·유럽어 등) 문장 분절 및 스마트 줄바꿈 검증"""
        from src.subtitle_manager import smart_break_sentences, break_subtitle_text

        # 1. 일본어: 공백이 없어도 마침표(。) 뒤에서 자연스럽게 2줄 분할
        ja_text = "こんにちは。よろしくお願いします。"
        ja_res = smart_break_sentences(ja_text, linebreak="<br>")
        self.assertEqual(ja_res, "こんにちは。<br>よろしくお願いします。")

        # 2. 중국어: 공백이 없어도 마침표(。) 뒤에서 자연스럽게 2줄 분할 (실질적 복수 문장)
        zh_text = "今天天气很好。明天也会很晴朗。"
        zh_res = smart_break_sentences(zh_text, linebreak="<br>")
        self.assertEqual(zh_res, "今天天气很好。<br>明天也会很晴朗。")

        # 3. 스페인어: 실질적 복수 문장 분할
        es_text = "El clima está muy agradable hoy. Mañana también estará soleado."
        es_res = smart_break_sentences(es_text, linebreak="<br>")
        self.assertEqual(es_res, "El clima está muy agradable hoy.<br>Mañana también estará soleado.")

        # 4. 러시아어: 실질적 복수 문장 분할
        ru_text = "Сегодня прекрасная погода. Завтра тоже будет солнечно."
        ru_res = smart_break_sentences(ru_text, linebreak="<br>")
        self.assertEqual(ru_res, "Сегодня прекрасная погода.<br>Завтра тоже будет солнечно.")

        # 5. 독일어: 인사말 뒤 분할
        de_text = "Guten Tag! Wie geht es Ihnen?"
        de_res = smart_break_sentences(de_text, linebreak="<br>")
        self.assertEqual(de_res, "Guten Tag!<br>Wie geht es Ihnen?")

        # 6. 짧은 맞장구/인사말 1줄 보존
        self.assertNotIn("<br>", smart_break_sentences("はい。そうです。", linebreak="<br>"))
        self.assertNotIn("<br>", smart_break_sentences("你好。很高兴认识你。", linebreak="<br>"))
        self.assertNotIn("<br>", smart_break_sentences("¡Hola! ¿Cómo estás hoy?", linebreak="<br>"))
        self.assertNotIn("<br>", smart_break_sentences("Привет! Как ваши дела?", linebreak="<br>"))
        self.assertNotIn("<br>", smart_break_sentences("Oui. C'est vrai.", linebreak="<br>"))

        # 7. 단일 장문 쉼표 기준 균형 분할 (CJK 22자 초과 / 영문 48자 초과 시)
        ja_long = "明日の朝までにこの仕事を絶対に終わらせなければならない、準備を急ごう。"
        ja_long_res = smart_break_sentences(ja_long, linebreak="<br>")
        self.assertIn("<br>", ja_long_res)
        self.assertTrue(ja_long_res.startswith("明日の朝までにこの仕事を絶対に終わらせなければならない、<br>"))

        en_long = "We need to finish this urgent report before the meeting starts, so please hurry up."
        en_long_res = smart_break_sentences(en_long, linebreak="<br>")
        self.assertIn("<br>", en_long_res)

        # 8. break_subtitle_text 다국어 일원화 호출 검증
        self.assertEqual(break_subtitle_text(ja_text, target_lang="ja", linebreak="<br>"), ja_res)

    def test_15_ui_languages_activated(self):
        """15개 언어 UI 카탈로그 및 셀렉터 등록 무결성 검증"""
        from src.i18n import SUPPORTED_UI_LANGUAGES, UI_LANGUAGE_NAMES, supported_ui_languages
        from src.ui_strings import CATALOGS, UI_LANGS

        expected = ["ko", "en", "ja", "zh", "es", "fr", "de", "pt", "ru", "it", "vi", "th", "id", "ar", "hi"]

        # 1. 15개 언어 모두 등록되어 있는지 확인
        self.assertEqual(len(SUPPORTED_UI_LANGUAGES), 15)
        for code in expected:
            self.assertIn(code, SUPPORTED_UI_LANGUAGES)
            self.assertIn(code, UI_LANGUAGE_NAMES)
            self.assertIn(code, supported_ui_languages())
            self.assertIn(code, CATALOGS)

        # 2. 모든 언어 카탈로그가 영어 카탈로그와 동일한 수의 키를 갖는지 확인
        en_keys = set(CATALOGS["en"].keys())
        for code in expected:
            self.assertEqual(set(CATALOGS[code].keys()), en_keys, f"언어 '{code}'의 키 누락 또는 불일치")

    def test_detect_system_ui_language(self):
        """Windows OS 로케일 감지 및 다국어 반환 검증"""
        from src.i18n import detect_system_ui_language

        # Mocking Windows GetUserDefaultLocaleName
        mock_buf = MagicMock()
        with patch("ctypes.windll.kernel32.GetUserDefaultLocaleName", return_value=1), \
             patch("ctypes.create_unicode_buffer") as mock_create:

            def set_mock_loc(loc_str):
                m = MagicMock()
                m.value = loc_str
                mock_create.return_value = m

            # 일본어 OS
            set_mock_loc("ja-JP")
            self.assertEqual(detect_system_ui_language(), "ja")

            # 스페인어 OS
            set_mock_loc("es-ES")
            self.assertEqual(detect_system_ui_language(), "es")

            # 독일어 OS
            set_mock_loc("de-DE")
            self.assertEqual(detect_system_ui_language(), "de")

            # 프랑스어 OS
            set_mock_loc("fr-FR")
            self.assertEqual(detect_system_ui_language(), "fr")

            # 한국어 OS
            set_mock_loc("ko-KR")
            self.assertEqual(detect_system_ui_language(), "ko")

            # 중국어 OS
            set_mock_loc("zh-CN")
            self.assertEqual(detect_system_ui_language(), "zh")

            # 알 수 없는 언어 (글로벌 모드 기본값: en)
            set_mock_loc("xx-YY")
            with patch("src.product.is_global", return_value=True):
                self.assertEqual(detect_system_ui_language(), "en")

    def test_control_panel_15_ui_language_combo(self):
        """글로벌 에디션 제어 패널 상단에 15개 UI 언어가 모두 표시되는지 검증"""
        import os
        from PyQt6.QtWidgets import QApplication
        from src.control_panel import ControlPanel
        from src.i18n import UI_LANGUAGE_NAMES

        app = QApplication.instance() or QApplication([])
        cfg = {"ui_lang": "en", "source_lang": "auto", "target_lang": "en"}

        with patch.dict(os.environ, {"WISE_PRODUCT": "global", "QT_QPA_PLATFORM": "offscreen"}), \
             patch("src.audio_capture.AudioLoopbackCapture.get_available_capture_sources", return_value=[]), \
             patch("soundcard.all_speakers", return_value=[]), \
             patch("src.process_volume.AudioDuckingManager", autospec=True):
            cp = ControlPanel(
                cfg,
                overlay=None,
                audio_thread=None,
                stt_thread=None,
                save_config_cb=lambda c: None,
            )

            self.assertTrue(hasattr(cp, "combo_ui_lang"))
            self.assertEqual(cp.combo_ui_lang.count(), 15)

            items = [cp.combo_ui_lang.itemData(i) for i in range(cp.combo_ui_lang.count())]
            for code in UI_LANGUAGE_NAMES:
                self.assertIn(code, items)

            # Switch UI to Japanese
            ja_idx = cp.combo_ui_lang.findData("ja")
            self.assertGreaterEqual(ja_idx, 0)
            cp.combo_ui_lang.setCurrentIndex(ja_idx)
            cp.close()

    def test_pre_processor_multilingual_formatting(self):
        """번역 엔진별 다국어 프롬프트 포맷팅 (도착 언어에 따른 헤더 현지화) 검증"""
        from src.pre_processor import PreProcessingContext

        ctx = PreProcessingContext(
            source_summary="Space Exploration and Gravitational Waves",
            tone_and_style="Informative and clear",
            glossary={"quantum": "quantum", "singularity": "singularity"}
        )

        # 1. Gemini: 한국어 도착 vs 글로벌 도착
        gemini_ko = ctx.format_for_gemini(source_lang="en", target_lang="ko")
        self.assertIn("[영상 배경 요약]", gemini_ko)
        self.assertIn("[도메인 전문 용어 번역 규칙]:", gemini_ko)

        gemini_en = ctx.format_for_gemini(source_lang="en", target_lang="es")
        self.assertIn("[Video Context Summary]", gemini_en)
        self.assertIn("[Mandatory Domain Terminology Rules]:", gemini_en)

        # 2. EXAONE: 한국어 도착 vs 글로벌 도착
        exaone_ko = ctx.format_for_exaone(source_lang="en", target_lang="ko")
        self.assertIn("[필수 준수 용어집 (Glossary)]:", exaone_ko)
        self.assertIn("원문 용어 (영어)", exaone_ko)
        self.assertIn("공식 한국어 번역", exaone_ko)

        exaone_en = ctx.format_for_exaone(source_lang="en", target_lang="en")
        self.assertIn("[Mandatory Domain Glossary]:", exaone_en)
        self.assertIn("Source Term (English)", exaone_en)
        self.assertIn("Official EN Translation", exaone_en)

    def test_dubbing_adaptive_speed_sps_phonetic_compensation(self):
        """음절 밀도(SPS) 기반 다국어 더빙 배속 자동 보정 검증"""
        from src.dubbing_engine import DubbingEngine

        engine = DubbingEngine({"dubbing_speed": "+10%"})

        # 일반 언어 (한국어, 영어): 기본 +10%
        self.assertEqual(engine.calculate_adaptive_speed(0, target_lang="ko"), "+10%")
        self.assertEqual(engine.calculate_adaptive_speed(1, target_lang="en"), "+10%")

        # 고음절 언어 (스페인어 7.82 SPS, 일본어 7.84 SPS, 프랑스어 7.18 SPS 등): +5% 자동 보정 -> +15%
        self.assertEqual(engine.calculate_adaptive_speed(0, target_lang="es"), "+15%")
        self.assertEqual(engine.calculate_adaptive_speed(1, target_lang="ja"), "+15%")
        self.assertEqual(engine.calculate_adaptive_speed(0, target_lang="fr"), "+15%")
        self.assertEqual(engine.calculate_adaptive_speed(0, target_lang="it"), "+15%")
        self.assertEqual(engine.calculate_adaptive_speed(0, target_lang="pt"), "+15%")

        # 적체 발생 시 지능형 추격 가속도 정상 동작
        self.assertEqual(engine.calculate_adaptive_speed(2, target_lang="ja"), "+20%")
        self.assertEqual(engine.calculate_adaptive_speed(3, target_lang="ja"), "+25%")
        self.assertEqual(engine.calculate_adaptive_speed(5, target_lang="ja"), "+30%")

    def test_gemini_preprocessor_multilingual_prompts(self):
        """Gemini 사전 분석기 다국어 프롬프트 생성 검증"""
        from src.pre_processor import GeminiPreProcessor

        prep = GeminiPreProcessor(api_key="test_dummy_key")
        captured_prompts = []

        def mock_call(prompt, sys_inst):
            captured_prompts.append((prompt, sys_inst))
            return {
                "source_summary": "Test Summary",
                "tone_and_style": "Test Style",
                "whisper_initial_prompt": "term1, term2",
                "phonetic_fix_map": {"err": "fix"},
                "glossary": {"Term": "Translation"}
            }

        prep._call_gemini_json = mock_call

        # 1. 한국어 타겟 -> 한국어 시스템 프롬프트
        prep.analyze_metadata("Title", "Topic", source_lang="en", target_lang="ko")
        self.assertEqual(len(captured_prompts), 1)
        prompt_ko, sys_ko = captured_prompts[-1]
        self.assertIn("언어 분석 전문가", sys_ko)
        self.assertIn("한국어", prompt_ko)

        # 2. 스페인어 타겟 -> 영문 국제 표준 시스템 프롬프트
        prep.analyze_metadata("Title", "Topic", source_lang="en", target_lang="es")
        self.assertEqual(len(captured_prompts), 2)
        prompt_es, sys_es = captured_prompts[-1]
        self.assertIn("expert audio-visual language engineer", sys_es)
        self.assertIn("Spanish", prompt_es)


if __name__ == "__main__":
    unittest.main()


