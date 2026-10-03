import unittest
from unittest.mock import Mock, patch
from src.translator import RealtimeTranslator


class TestOllamaFallbackRule(unittest.TestCase):
    def test_uninstalled_ollama_unconditionally_uses_embedded(self):
        """올라마가 설치되어 있지 않은 시스템에서는 llm_backend가 ollama로 설정되어 있어도 무조건 내장 GGUF로 동작"""
        with patch("src.llm_model_manager.LLMModelManager.is_ollama_installed", return_value=False):
            translator = RealtimeTranslator({
                "translation_engine": "hymt",
                "llm_backend": "ollama",
                "selected_llm_model": "tencent/hy-mt2:1.8b"
            })
            # Mock embedded translator
            translator._translate_hymt = Mock(return_value="내장 GGUF 번역 성공")
            # Ensure _translate_ollama is not mocked so we verify it's never called or never attempts connection
            res, engine = translator.translate("Test sentence without Ollama.")

            self.assertEqual(res, "내장 GGUF 번역 성공")
            self.assertEqual(engine, "Hy-MT2 1.8B (내장 GGUF)")
            translator._translate_hymt.assert_called_once()
            # llm_backend should be normalized to embedded
            self.assertEqual(translator.config.get("llm_backend"), "embedded")


if __name__ == "__main__":
    unittest.main()
