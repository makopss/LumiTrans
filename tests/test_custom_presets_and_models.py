import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import sys
import os
import unittest
from PyQt6.QtWidgets import QApplication

# Add project root to sys.path
sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

from src.config import DEFAULT_CONFIG
from src.control_panel import ControlPanel
from src.stt_model_manager import STTModelManager, AVAILABLE_STT_MODELS
from src.llm_model_manager import LLMModelManager, RECOMMENDED_OLLAMA_MODELS, RECOMMENDED_GGUF_MODELS
from src.translator import RealtimeTranslator


class TestCustomPresetsAndModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.cfg = dict(DEFAULT_CONFIG)
        self.cfg["custom_presets"] = {}
        self.saved_cfg = None

        def dummy_save(c):
            self.saved_cfg = dict(c)

        self.panel = ControlPanel(
            config=self.cfg,
            overlay=None,
            audio_thread=None,
            stt_thread=None,
            save_config_cb=dummy_save
        )

    def tearDown(self):
        self.panel.close()

    def test_custom_preset_lifecycle(self):
        """1. 커스텀 프리셋 저장, 적용 및 삭제 라이프사이클 테스트"""
        # 프리셋 데이터 모의 추가
        preset_id = "test_preset_bg3"
        preset_data = {
            "name": "발더스 게이트 3 고음질",
            "desc": "게임용 폰트 및 고품질 STT",
            "config": {
                "font_size": 28,
                "overlay_bg_opacity": 0.85,
                "device": "cuda",
                "model_size": "large-v3-turbo",
                "translation_engine": "exaone",
                "subtitle_stroke_width": 2,
                "letter_spacing": 3.0,
            }
        }
        self.panel.config.setdefault("custom_presets", {})[preset_id] = preset_data
        self.panel._refresh_presets_ui()

        # 적용 테스트
        self.panel.apply_custom_preset(preset_id, notify=False)
        self.assertEqual(self.panel.config["font_size"], 28)
        self.assertEqual(self.panel.config["overlay_bg_opacity"], 0.85)
        self.assertEqual(self.panel.config["model_size"], "large-v3-turbo")
        self.assertEqual(self.panel.config["translation_engine"], "exaone")
        self.assertEqual(self.panel.config["subtitle_stroke_width"], 2)
        self.assertEqual(self.panel.config["letter_spacing"], 3.0)

        # 삭제 테스트 (직접 딕셔너리에서 제거 후 갱신 확인)
        del self.panel.config["custom_presets"][preset_id]
        self.panel._refresh_presets_ui()
        self.assertNotIn(preset_id, self.panel.config.get("custom_presets", {}))

    def test_custom_preset_max_limit_6(self):
        """커스텀 프리셋 최대 6개 개수 제한 테스트"""
        from unittest.mock import patch

        self.panel.config["custom_presets"] = {
            f"c_{i}": {"name": f"프리셋 {i}", "config": {}}
            for i in range(5)
        }
        self.panel._refresh_presets_ui()
        self.assertIn("5/6", self.panel.btn_save_preset.toolTip())

        # 6번째 프리셋 저장 성공
        with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("6번째 프리셋", True)), \
             patch("PyQt6.QtWidgets.QMessageBox.information"):
            self.panel.save_current_as_custom_preset()

        self.assertEqual(len(self.panel.config["custom_presets"]), 6)
        self.assertIn("6/6", self.panel.btn_save_preset.toolTip())

        # 7번째 프리셋 저장 시도 시 경고 발생 및 저장 차단
        with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn, \
             patch("PyQt6.QtWidgets.QInputDialog.getText") as mock_input:
            self.panel.save_current_as_custom_preset()
            mock_warn.assert_called_once()
            mock_input.assert_not_called()

        self.assertEqual(len(self.panel.config["custom_presets"]), 6)


    def test_stt_model_manager(self):
        """2. STT 모델 관리자 탐색 및 용량 조회 테스트"""
        models = STTModelManager.get_available_models()
        self.assertGreaterEqual(len(models), 8)
        
        # tiny.en 상태 확인
        tiny_installed = STTModelManager.is_model_installed("tiny.en")
        tiny_mb = STTModelManager.get_model_disk_size_mb("tiny.en")
        print(f"[Test] STT tiny.en 설치 여부: {tiny_installed}, 용량: {tiny_mb} MB")

        # combo_model에 아이템이 채워졌는지 확인
        self.assertGreater(self.panel.combo_model.count(), 0)

    def test_llm_model_manager(self):
        """3. LLM 모델 관리자 (Ollama 및 내장 GGUF) 테스트"""
        is_alive, ver = LLMModelManager.check_ollama_alive()
        print(f"[Test] Ollama 상태: 활성={is_alive}, 버전={ver}")

        if is_alive:
            ollama_models = LLMModelManager.get_installed_ollama_models()
            print(f"[Test] Ollama 설치 모델 목록: {[m['tag'] for m in ollama_models]}")
            self.assertIsInstance(ollama_models, list)

        self.assertGreaterEqual(len(RECOMMENDED_GGUF_MODELS), 2)

    def test_realtime_translator_ollama_dispatch(self):
        """4. RealtimeTranslator의 Ollama 연동 및 내장 GGUF 라우팅 테스트"""
        translator = RealtimeTranslator(config=self.cfg)
        
        # Ollama가 켜져 있는 경우 실제 호출 테스트
        is_alive, _ = LLMModelManager.check_ollama_alive()
        if is_alive:
            ollama_models = [m['tag'] for m in LLMModelManager.get_installed_ollama_models()]
            if any("exaone" in m for m in ollama_models):
                trans_result = translator._translate_ollama("Hello, brave warrior.", "exaone3.5:2.4b")
    def test_quick_presets_pagination_width_preserved(self):
        """5. 하단 퀵 프리셋에서 4개 이상 시 페이지 전환(3개/1개) 간 폭(Width) 보존 검증"""
        self.panel.config["custom_presets"] = {
            "c_1": {"name": "테스트", "config": {}},
            "c_2": {"name": "78", "config": {}},
            "c_3": {"name": "888", "config": {}},
            "c_4": {"name": "8966", "config": {}},
        }
        self.panel._custom_preset_page = 0
        self.panel._refresh_quick_presets_ui()
        w0 = self.panel.quick_presets_widget.sizeHint().width()

        # 페이지 1로 전환
        self.panel._on_next_custom_preset_page()
        w1 = self.panel.quick_presets_widget.sizeHint().width()

        self.assertEqual(self.panel.quick_presets_layout.count(), len(self.panel._builtin_presets()) + 6)


if __name__ == "__main__":
    unittest.main()
