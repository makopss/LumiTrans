import unittest
import sys
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication

from src.llm_model_manager import RECOMMENDED_OLLAMA_MODELS, RECOMMENDED_GGUF_MODELS
from src.translator import RealtimeTranslator
from src.overlay_window import SubtitleOverlay
from src.config import DEFAULT_CONFIG

app = QApplication.instance() or QApplication(sys.argv)

class TestHYMTIntegration(unittest.TestCase):

    def test_model_registry_entries(self):
        """Ollama 및 GGUF 모델 레지스트리에 Hy-MT2-1.8B가 올바르게 등록되어 있는지 검증"""
        ollama_entry = next((m for m in RECOMMENDED_OLLAMA_MODELS if "hy-mt" in m["tag"].lower() or "hymt" in m["tag"].lower()), None)
        self.assertIsNotNone(ollama_entry, "Ollama 추천 목록에 Hy-MT2가 등록되어 있어야 합니다.")
        self.assertEqual(ollama_entry["tag"], "tencent/hy-mt2:1.8b")
        self.assertIn("1.8B", ollama_entry["name"])

        gguf_entry = next((m for m in RECOMMENDED_GGUF_MODELS if "hymt" in m["id"].lower() or "hy-mt" in m["id"].lower()), None)
        self.assertIsNotNone(gguf_entry, "GGUF 추천 목록에 Hy-MT2가 등록되어 있어야 합니다.")
        self.assertEqual(gguf_entry["id"], "hymt-2-1.8b")
        self.assertEqual(gguf_entry["repo_id"], "tencent/Hy-MT2-1.8B-GGUF")
        self.assertEqual(gguf_entry["filename"], "Hy-MT2-1.8B-Q4_K_M.gguf")

    def test_translator_routing_and_prompt_formatting(self):
        """RealtimeTranslator에서 hymt 내장 GGUF 엔진 선택 시 공식 번역 프롬프트 적용 및 라우팅 검증"""
        cfg = DEFAULT_CONFIG.copy()
        cfg["translation_engine"] = "hymt"
        cfg["llm_backend"] = "embedded"
        translator = RealtimeTranslator(cfg)

        mock_llm = MagicMock()
        mock_llm.return_value = {
            "choices": [{"text": "안녕하세요 세계."}]
        }

        with patch.object(translator, "_get_hymt", return_value=mock_llm):
            result, used_eng = translator.translate("Hello world.")
            self.assertEqual(result, "안녕하세요 세계.")
            self.assertIn("Hy-MT2", used_eng)

            # 프롬프트 형식 검증
            call_args, call_kwargs = mock_llm.call_args
            prompt_used = call_args[0]
            self.assertIn("Translate the following text into Korean. Note that you should only output the translated result without any additional explanation:", prompt_used)
            self.assertIn("Hello world.", prompt_used)
            # Stop tokens 검증
            stop_tokens = call_kwargs.get("stop", [])
            self.assertIn("<｜hy_place·holder·no·3｜>", stop_tokens)
            self.assertIn("<｜hy_User｜>", stop_tokens)

    def test_translator_ollama_prompt_formatting(self):
        """Ollama 백엔드에서 Hy-MT2 선택 시 특화 프롬프트 및 파라미터 전송 검증"""
        cfg = DEFAULT_CONFIG.copy()
        cfg["translation_engine"] = "hymt"
        cfg["llm_backend"] = "ollama"
        translator = RealtimeTranslator(cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "좋은 아침입니다.", "done_reason": "stop"}

        with patch.object(translator.session, "post", return_value=mock_resp) as mock_post:
            res = translator._translate_ollama("Good morning.", "tencent/hy-mt2:1.8b")
            self.assertEqual(res, "좋은 아침입니다.")
            
            call_kwargs = mock_post.call_args.kwargs
            payload = call_kwargs.get("json", {})
            self.assertIn("Translate the following text into Korean. Note that you should only output the translated result without any additional explanation: Good morning.", payload.get("prompt", ""))
            self.assertIn("<｜hy_place·holder·no·3｜>", payload.get("options", {}).get("stop", []))

    def test_translator_fallback(self):
        """Hy-MT2 모델 로드 또는 추론 실패 시 Google 폴백 작동 검증"""
        cfg = DEFAULT_CONFIG.copy()
        cfg["translation_engine"] = "hymt"
        translator = RealtimeTranslator(cfg)

        with patch.object(translator, "_get_hymt", side_effect=RuntimeError("GGUF not found")):
            with patch.object(translator, "_translate_google_mobile", return_value="구글 번역 결과"):
                result, used_eng = translator.translate("Test sentence.")
                self.assertEqual(result, "구글 번역 결과")
                self.assertIn("Google", used_eng)
                self.assertIn("폴백", used_eng)

    def test_overlay_window_integration(self):
        """OverlayWindow의 드롭다운, 인덱스 맵, 실시간 뱃지 연동 검증"""
        cfg = DEFAULT_CONFIG.copy()
        cfg["translation_engine"] = "hymt"
        overlay = SubtitleOverlay(cfg)

        # 콤보 박스 아이템 확인
        items = [overlay.combo_engine.itemText(i) for i in range(overlay.combo_engine.count())]
        self.assertIn("Hy-MT2", items)
        self.assertEqual(overlay.combo_engine.currentIndex(), 6)

        # set_engine_by_key 호출 동기화
        overlay.set_engine_by_key("hymt")
        self.assertEqual(overlay.combo_engine.currentIndex(), 6)

        overlay.set_engine_by_key("google")
        self.assertEqual(overlay.combo_engine.currentIndex(), 1)

        overlay.set_engine_by_key("hymt")
        self.assertEqual(overlay.combo_engine.currentIndex(), 6)

if __name__ == "__main__":
    unittest.main()
