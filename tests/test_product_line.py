# -*- coding: utf-8 -*-
"""한국어 제품 기본값 회귀와 글로벌 제품 라인 단위 테스트."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.app_paths as app_paths
from src.config import (
    BUILTIN_PRESETS,
    DEFAULT_CONFIG,
    GLOBAL_PRESETS,
    _apply_hardware_and_model_detection,
    active_builtin_presets,
    get_config_file_path,
)
from src.i18n import GLOBAL_PRESET_COPY, set_ui_language, tr
from src.ui_strings import CATALOGS, UI_LANGS
from src.product import get_product, is_global
from src.subtitle_manager import break_subtitle_text, subtitle_export_filename
from src.translator import RealtimeTranslator


class TestKoreanProductDefaults(unittest.TestCase):
    def test_builtin_presets_and_default_config_stay_korean(self):
        self.assertEqual(DEFAULT_CONFIG["stt_language"], "en")
        self.assertEqual(DEFAULT_CONFIG["model_size"], "distil-small.en")
        self.assertEqual(DEFAULT_CONFIG["target_lang"], "ko")
        self.assertEqual(DEFAULT_CONFIG["source_lang"], "en")
        self.assertEqual(
            list(BUILTIN_PRESETS.keys()),
            ["low_spec", "live", "balance", "cinema", "masterpiece", "global"],
        )
        self.assertIn("글로벌 다국어", BUILTIN_PRESETS["global"]["name"])

    def test_korean_export_names_stay_fixed(self):
        self.assertEqual(subtitle_export_filename("orig_only", "srt"), "english_subtitles.srt")
        self.assertEqual(subtitle_export_filename("trans_only", "srt"), "korean_subtitles.srt")
        self.assertEqual(subtitle_export_filename("orig_only", "txt"), "english_transcript.txt")
        self.assertEqual(subtitle_export_filename("trans_only", "txt"), "korean_transcript.txt")

    def test_fresh_korean_config_uses_english_stt(self):
        cfg = DEFAULT_CONFIG.copy()
        with patch.dict(os.environ, {"WISE_PRODUCT": "kr"}, clear=False):
            _apply_hardware_and_model_detection(cfg)
        self.assertEqual(cfg["model_size"], "distil-small.en")
        self.assertEqual(cfg["stt_language"], "en")
        self.assertEqual(cfg["target_lang"], "ko")
        self.assertEqual(cfg["ui_lang"], "ko")
        self.assertEqual(cfg["translation_engine"], "google")


class TestGlobalProductLine(unittest.TestCase):
    def test_env_overrides_edition_file(self):
        with patch.dict(os.environ, {"WISE_PRODUCT": "global"}, clear=False):
            self.assertEqual(get_product(), "global")
            self.assertTrue(is_global())
        with patch.dict(os.environ, {"WISE_PRODUCT": "kr"}, clear=False):
            self.assertEqual(get_product(), "kr")
            self.assertFalse(is_global())

    def test_global_presets_are_multilingual_and_not_exaone(self):
        self.assertEqual(list(GLOBAL_PRESETS.keys()), ["low_spec", "live", "balance", "cinema"])
        low = GLOBAL_PRESETS["low_spec"]
        self.assertEqual(low["model_size"], "small")
        self.assertEqual(low["stt_language"], "auto")
        self.assertEqual(low["translation_engine"], "google")
        self.assertEqual(low["name"], GLOBAL_PRESET_COPY["low_spec"]["name"])
        live = GLOBAL_PRESETS["live"]
        self.assertEqual(live["model_size"], "small")
        self.assertEqual(live["translation_engine"], "hymt")
        balance = GLOBAL_PRESETS["balance"]
        self.assertEqual(balance["model_size"], "small")
        self.assertEqual(balance["translation_engine"], "hymt")
        cinema = GLOBAL_PRESETS["cinema"]
        self.assertEqual(cinema["model_size"], "large-v3-turbo")
        self.assertEqual(cinema["translation_engine"], "gemma")
        for item in GLOBAL_PRESETS.values():
            self.assertEqual(item["stt_language"], "auto")
            self.assertNotIn(".en", item["model_size"])
            self.assertNotIn("exaone", item["translation_engine"])

    def test_active_presets_follow_product(self):
        with patch.dict(os.environ, {"WISE_PRODUCT": "kr"}, clear=False):
            self.assertIs(active_builtin_presets(), BUILTIN_PRESETS)
        with patch.dict(os.environ, {"WISE_PRODUCT": "global"}, clear=False):
            self.assertIs(active_builtin_presets(), GLOBAL_PRESETS)

    def test_fresh_global_defaults(self):
        cfg = DEFAULT_CONFIG.copy()
        with patch.dict(os.environ, {"WISE_PRODUCT": "global"}, clear=False):
            _apply_hardware_and_model_detection(cfg)
        self.assertEqual(cfg["model_size"], "small")
        self.assertEqual(cfg["stt_language"], "auto")
        self.assertEqual(cfg["source_lang"], "auto")
        self.assertEqual(cfg["target_lang"], "en")
        self.assertEqual(cfg["ui_lang"], "en")
        self.assertEqual(cfg["translation_engine"], "google")
        self.assertEqual(cfg["device"], "cpu")

    def test_dev_config_path_and_data_dir_are_separate(self):
        with tempfile.TemporaryDirectory() as base:
            with patch.dict(os.environ, {"WISE_PRODUCT": "global", "APPDATA": base, "LOCALAPPDATA": base}, clear=False):
                app_paths._migrated.clear()
                self.assertTrue(get_config_file_path().endswith("config.global.json"))
                self.assertEqual(os.path.basename(app_paths.roaming_data_dir()), "LumiTrans Global")
                self.assertEqual(os.path.basename(app_paths.local_data_dir()), "LumiTrans Global")
                self.assertFalse(os.path.isdir(os.path.join(base, "LumiTrans")))
            with patch.dict(os.environ, {"WISE_PRODUCT": "kr", "APPDATA": base}, clear=False):
                app_paths._migrated.clear()
                self.assertTrue(get_config_file_path().endswith("config.json"))
                self.assertFalse(get_config_file_path().endswith("config.global.json"))
                self.assertEqual(os.path.basename(app_paths.roaming_data_dir()), "LumiTrans")

    def test_shell_strings_switch_with_product(self):
        set_ui_language(None)
        with patch.dict(os.environ, {"WISE_PRODUCT": "kr"}, clear=False):
            self.assertIn("루미", tr("brand_title"))
            self.assertIn("종료", tr("quit_message"))
        with patch.dict(os.environ, {"WISE_PRODUCT": "global"}, clear=False):
            self.assertEqual(tr("brand_title"), "LumiTrans")
            self.assertEqual(tr("quit_message"), "Quit LumiTrans?")
            self.assertEqual(tr("target_lang_label"), "Subtitle language")

    def test_global_ui_languages_cover_the_same_keys(self):
        english = set(CATALOGS["en"])
        self.assertGreaterEqual(len(UI_LANGS), 15)
        for code in UI_LANGS:
            self.assertEqual(set(CATALOGS[code]), english, code)
        with patch.dict(os.environ, {"WISE_PRODUCT": "global"}, clear=False):
            set_ui_language("ja")
            self.assertIn("音声", tr("nav_audio"))
            self.assertNotIn("음성", tr("nav_audio"))
            set_ui_language("ar")
            self.assertIn("الصوت", tr("nav_audio"))
            self.assertEqual(tr("count_total", total=3), "المجموع 3")
            set_ui_language(None)
            self.assertEqual(tr("nav_settings"), "⚙️ Settings")
            set_ui_language("de")
            self.assertEqual(tr("msg_need_key_title"), "API-Schlüssel nötig")
            self.assertIn("Gehört", tr("status_heard", text="Hallo"))
            set_ui_language(None)

    def test_global_export_uses_language_codes(self):
        self.assertEqual(
            subtitle_export_filename("orig_only", "srt", source_lang="ja", product="global"),
            "ja_subtitles.srt",
        )
        self.assertEqual(
            subtitle_export_filename("trans_only", "txt", target_lang="de", product="global"),
            "de_transcript.txt",
        )
        self.assertEqual(
            subtitle_export_filename("orig_only", "srt", source_lang="auto", product="global"),
            "source_subtitles.srt",
        )

    def test_line_break_uses_korean_path_only_for_korean(self):
        with patch("src.subtitle_manager.break_korean_sentences", return_value="ko-break") as korean:
            self.assertEqual(break_subtitle_text("Hello. World.", "en"), "Hello.<br>World.")
            korean.assert_not_called()
            self.assertEqual(break_subtitle_text("안녕. 반가워요.", "ko"), "ko-break")
            korean.assert_called_once()

    def test_auto_source_does_not_overwrite_detected_language(self):
        translator = RealtimeTranslator(
            config={"source_lang": "auto", "target_lang": "en", "translation_engine": "google"},
            source="en",
            target="ko",
        )
        self.assertEqual(translator.source, "en")
        self.assertEqual(translator.target, "en")
        translator.source = "ja"
        translator.update_config({"source_lang": "auto", "target_lang": "de", "translation_engine": "google"})
        self.assertEqual(translator.source, "ja")
        self.assertEqual(translator.target, "de")

    def test_english_target_skips_korean_postprocess(self):
        translator = RealtimeTranslator(source="ja", target="en")
        translator.config["translation_engine"] = "google"
        with patch.object(translator, "_translate_google_mobile", return_value="Hello 漢字") as translate, \
             patch.object(translator, "_post_process_korean", wraps=translator._post_process_korean) as post:
            result, _engine = translator.translate("こんにちは")
        translate.assert_called_once()
        post.assert_not_called()
        self.assertIn("漢字", result)

    def test_korean_target_still_postprocesses(self):
        translator = RealtimeTranslator(source="en", target="ko")
        translator.config["translation_engine"] = "google"
        with patch.object(translator, "_translate_google_mobile", return_value="안녕하세요"), \
             patch.object(translator, "_post_process_korean", wraps=translator._post_process_korean) as post:
            translator.translate("Hello there")
        post.assert_called_once()

    def test_installer_exposes_product_switch(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        with open(os.path.join(root, "installer.iss"), encoding="utf-8") as handle:
            installer = handle.read()
        with open(os.path.join(root, "scripts", "build_windows_installer.py"), encoding="utf-8") as handle:
            builder = handle.read()
        self.assertIn('#define MyAppId "{{A7E3C1D4-6B29-4F18-9C55-2D8E0B7A41F6}"', installer)
        self.assertIn("LumiTrans_Global_", installer)
        self.assertIn('--product', builder)
        self.assertIn('default="kr"', builder)
        self.assertIn("LumiTrans_Global_", builder)


if __name__ == "__main__":
    unittest.main()
