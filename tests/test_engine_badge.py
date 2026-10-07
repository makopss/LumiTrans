"""자막 오버레이 상태 배지가 실제로 동작한 엔진을 표시하는지 검증한다."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.i18n import tr
from src.engine_badge import (configured_stt_label, configured_translation_label,  # noqa: E402
                              stt_badge, translation_badge)

DEEPGRAM = {"stt_provider": "deepgram", "device": "cuda", "model_size": "sensevoice-small", "translation_engine": "exaone7b"}


class SttBadge(unittest.TestCase):
    def test_deepgram_is_not_shown_as_gpu(self):
        # Deepgram 을 고르면 device 가 cuda 로 남아 이전에는 "GPU" 로 보였다
        self.assertEqual(configured_stt_label(DEEPGRAM), "Deepgram")
        self.assertEqual(stt_badge("Deepgram (nova-3)", DEEPGRAM), ("Deepgram", False))
        self.assertEqual(stt_badge("", DEEPGRAM), ("Deepgram", False))

    def test_cloud_provider_wins_over_local_model_name(self):
        self.assertEqual(configured_stt_label({"stt_provider": "groq", "model_size": "parakeet-tdt-0.6b"}), "Groq")

    def test_fallbacks_are_marked(self):
        self.assertEqual(stt_badge("GPU (로컬 폴백)", DEEPGRAM), ("GPU", True))
        self.assertEqual(stt_badge("Groq (폴백 - Turbo)", DEEPGRAM), ("Groq", True))
        self.assertEqual(stt_badge("Deepgram (폴백 - nova-3)", {"stt_provider": "groq"}), ("Deepgram", True))

    def test_local_labels(self):
        self.assertEqual(stt_badge("CPU", {"device": "cuda"}), ("CPU", False))
        self.assertEqual(configured_stt_label({"stt_provider": "local", "device": "cpu"}), "CPU")
        self.assertEqual(configured_stt_label({"stt_provider": "local", "model_size": "moonshine-tiny"}), "Moonshine")


class TranslationBadge(unittest.TestCase):
    def test_selected_engine_is_not_fallback(self):
        cfg = {"translation_engine": "exaone7b"}
        self.assertEqual(translation_badge("EXAONE 3.5 7.8B (내장 GGUF)", cfg), ("EXAONE", False))
        self.assertEqual(translation_badge("Groq Qwen", {"translation_engine": "groq"}), ("Groq", False))
        self.assertEqual(translation_badge("Hy-MT2 1.8B (내장 GGUF)", {"translation_engine": "hymt"}), ("Hy-MT2", False))

    def test_other_engine_is_fallback(self):
        cfg = {"translation_engine": "exaone7b"}
        self.assertEqual(translation_badge("Google (exaone7b 폴백)", cfg), ("Google", True))
        # 다른 PC 로그: "GPU + MyMemory" 가 이전에는 선택 엔진(EXAONE)으로 표시되었다
        self.assertEqual(translation_badge("MyMemory", cfg), ("MyMemory", True))
        self.assertEqual(translation_badge("원문 유지", cfg), (tr("original"), True))
        self.assertEqual(translation_badge("Groq Qwen (Google 폴백)", {"translation_engine": "google"}), ("Groq", True))

    def test_ollama(self):
        cfg = {"translation_engine": "ollama:exaone3.5:7.8b"}
        self.assertEqual(configured_translation_label(cfg), "EXAONE")
        self.assertEqual(translation_badge("Ollama (exaone3.5:7.8b)", cfg), ("EXAONE", False))
        self.assertEqual(translation_badge("Ollama (tencent/hy-mt2:1.8b)", {"translation_engine": "hymt"}), ("Hy-MT2", False))

    def test_unknown_or_empty_uses_selected_engine(self):
        self.assertEqual(translation_badge("", {"translation_engine": "hymt"}), ("Hy-MT2", False))


if __name__ == "__main__":
    unittest.main()
