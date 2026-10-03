import unittest
from unittest.mock import patch
from src.config import DEFAULT_CONFIG, _apply_hardware_and_model_detection, load_config
from src.stt_model_manager import STTModelManager, AVAILABLE_STT_MODELS


class TestSTTInitialRecognition(unittest.TestCase):
    def test_apply_hardware_and_model_detection_with_cuda_and_installed_turbo(self):
        """CUDA 지원 및 large-v3-turbo 기설치 환경에서도 최초 실행 설정은 저사양 호환 (CPU) 프리셋 유지 검증"""
        cfg = DEFAULT_CONFIG.copy()
        with patch("src.stt_engine.is_cuda_available", return_value=True), \
             patch("src.stt_model_manager.STTModelManager.is_model_installed", side_effect=lambda m: m == "large-v3-turbo"):
            _apply_hardware_and_model_detection(cfg)

        self.assertEqual(cfg["device"], "cpu")
        self.assertEqual(cfg["compute_type"], "int8")
        self.assertEqual(cfg["model_size"], "distil-small.en")
        self.assertEqual(cfg["stt_language"], "en")
        self.assertEqual(cfg["translation_engine"], "google")

    def test_apply_hardware_and_model_detection_cpu_only(self):
        """CUDA 미지원(CPU 전용) 환경에서도 안전하게 저사양 호환 (CPU) 프리셋 유지 검증"""
        cfg = DEFAULT_CONFIG.copy()
        with patch("src.stt_engine.is_cuda_available", return_value=False), \
             patch("src.stt_model_manager.STTModelManager.is_model_installed", return_value=False):
            _apply_hardware_and_model_detection(cfg)

        self.assertEqual(cfg["device"], "cpu")
        self.assertEqual(cfg["compute_type"], "int8")
        self.assertEqual(cfg["model_size"], "distil-small.en")
        self.assertEqual(cfg["stt_language"], "en")
        self.assertEqual(cfg["translation_engine"], "google")

    def test_installed_model_dot_is_always_green_even_on_cpu(self):
        """설치된 모델은 CPU 모드에서도 빨간점이 아닌 녹색점(🟢)으로 정확히 인식 및 표시되어야 함"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from src.control_panel import ControlPanel
        cfg = DEFAULT_CONFIG.copy()
        cfg["device"] = "cpu"
        panel = ControlPanel(cfg, overlay=None, audio_thread=None, stt_thread=None, save_config_cb=lambda c: None)

        menu_instance = None
        def mock_popup(menu, widget):
            nonlocal menu_instance
            menu_instance = menu

        # large-v3-turbo 모델이 로컬에 설치되어 있는 상황 모의
        with patch.object(panel, '_popup_menu_above', side_effect=mock_popup), \
             patch("src.stt_model_manager.STTModelManager.is_model_installed", side_effect=lambda m: m == "large-v3-turbo"):
            panel._show_pipe_stt_model_menu()

        self.assertIsNotNone(menu_instance)
        actions = menu_instance.actions()
        turbo_act = next((a for a in actions if "large-v3-turbo" in a.text()), None)
        self.assertIsNotNone(turbo_act)
        # 물리적 설치 상태를 반영하므로 녹색점(🟢)이어야 함
        self.assertTrue(turbo_act.text().endswith("\t🟢"))

        panel.close()
        panel.deleteLater()

    def test_model_quick_selection_auto_promotes_cuda_and_auto_language(self):
        """CPU 상태에서 GPU 모델 선택 시 CUDA 자동 승격 및 다국어 auto 언어 전환 검증"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from src.control_panel import ControlPanel
        cfg = DEFAULT_CONFIG.copy()
        cfg["device"] = "cpu"
        cfg["model_size"] = "distil-small.en"
        cfg["stt_language"] = "en"
        panel = ControlPanel(cfg, overlay=None, audio_thread=None, stt_thread=None, save_config_cb=lambda c: None)

        with patch("src.stt_engine.is_cuda_available", return_value=True):
            panel._on_stt_model_quick_selected("large-v3-turbo")

        self.assertEqual(panel.config["device"], "cuda")
        self.assertEqual(panel.config["compute_type"], "float16")
        self.assertEqual(panel.config["model_size"], "large-v3-turbo")
        self.assertEqual(panel.config["stt_language"], "auto")

        panel.close()
        panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
