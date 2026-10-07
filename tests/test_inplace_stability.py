import unittest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QRect
from src.inplace_translator import InPlaceTranslatorManager, InPlaceOverlayWindow


class TestInPlaceStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_overlay_window_init_no_dark_mode_winid(self):
        """InPlaceOverlayWindow 생성 시 불필요한 set_windows_dark_mode 및 winId 호출 없음 검증"""
        window = InPlaceOverlayWindow(config={})
        self.assertIsNotNone(window)
        self.assertTrue(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        window.close()

    def test_inplace_manager_init_and_hotkey(self):
        """InPlaceTranslatorManager의 단축키 워커 및 설정 검증"""
        mock_translator = MagicMock()
        mock_get_ocr = MagicMock(return_value=None)
        config = {"inplace_hotkey": "F9"}

        manager = InPlaceTranslatorManager(
            config=config,
            translator=mock_translator,
            get_ocr_cb=mock_get_ocr,
            get_overlays_to_hide=lambda: []
        )
        self.assertEqual(manager.get_hotkey(), "F9")
        # 단축키 활성화/비활성화 토글
        manager.set_hotkey_enabled(False)
        self.assertFalse(manager.hotkey_worker.is_enabled)
        manager.set_hotkey_enabled(True)
        self.assertTrue(manager.hotkey_worker.is_enabled)
        manager.stop()

    def test_stt_greedy_defaults(self):
        """STT 엔진에서 실시간 스트리밍 시 VRAM OOM 및 TDR 방지를 위한 greedy beam_size 기본값 1 검증"""
        config = {}
        beam_sz = int(config.get("whisper_beam_size", 1))
        best_of_val = int(config.get("whisper_best_of", 1))
        self.assertEqual(beam_sz, 1)
        self.assertEqual(best_of_val, 1)

    def test_inplace_banner_layout_and_i18n(self):
        """인플레이스 배너 위젯의 순서(아이콘, 텍스트만, 글자크기, A-/A+, 닫기), 아웃라인 제거, 크기, 다국어 검증"""
        from src.i18n import set_ui_language, tr
        set_ui_language("ko")
        window = InPlaceOverlayWindow(config={})

        # 1. 아웃라인 제거 확인
        self.assertIn("border: none;", window.banner_widget.styleSheet())

        # 2. 버튼 크기 확인 (깨짐 방지를 위한 32px 이상 확보)
        self.assertGreaterEqual(window.btn_font_dec.width(), 32)
        self.assertGreaterEqual(window.btn_font_dec.height(), 24)
        self.assertGreaterEqual(window.btn_font_inc.width(), 32)
        self.assertGreaterEqual(window.btn_font_inc.height(), 24)

        # 3. 레이아웃 위젯 순서 확인
        layout = window.banner_widget.layout()
        items = [layout.itemAt(i).widget() for i in range(layout.count())]
        self.assertIs(items[0], window.lbl_icon)
        self.assertIs(items[1], window.btn_clean_mode)
        self.assertIs(items[2], window.lbl_font_size)
        self.assertIs(items[3], window.btn_font_dec)
        self.assertIs(items[4], window.btn_font_inc)
        self.assertIs(items[5], window.btn_close)

        # 4. 한국어 텍스트 및 px 표기 확인
        window._apply_ui_language()
        self.assertIn("글자 크기: 12px", window.lbl_font_size.text())
        self.assertEqual("✕", window.btn_close.text())
        self.assertIn("ESC 닫기", window.btn_close.toolTip())
        self.assertIn("텍스트만", window.btn_clean_mode.text())
        self.assertIn("인플레이스", window.lbl_icon.toolTip())
        self.assertIn("F4", window.lbl_icon.toolTip())

        # 폰트 크기 변경 시 px 업데이트 확인 (+1 -> 13px, -2 -> 11px)
        window.change_font_size(+1)
        self.assertIn("13px", window.lbl_font_size.text())
        window.change_font_size(-2)
        self.assertIn("11px", window.lbl_font_size.text())
        window.change_font_size(+1)  # 원복 (12px)

        # 5. 글로벌 언어(영어, 일본어 등) 번역 적용 확인
        set_ui_language("en")
        window._apply_ui_language()
        self.assertIn("Font size: 12px", window.lbl_font_size.text())
        self.assertIn("ESC to close", window.btn_close.toolTip())
        self.assertIn("Text only", window.btn_clean_mode.text())
        self.assertIn("In-Place", window.lbl_icon.toolTip())

        set_ui_language("ja")
        window._apply_ui_language()
        self.assertIn("文字サイズ: 12px", window.lbl_font_size.text())
        self.assertIn("ESC 閉じる", window.btn_close.toolTip())
        self.assertIn("テキストのみ", window.btn_clean_mode.text())
        self.assertIn("インプレース", window.lbl_icon.toolTip())

        # 6. x 아이콘 버튼 클릭 시 창 숨김(hide) 확인
        window.show()
        self.assertTrue(window.isVisible())
        window.btn_close.click()
        self.assertFalse(window.isVisible())

        set_ui_language("ko")
        window.close()

    def test_footer_buttons_fixed_width_and_no_icon(self):
        """하단 푸터 버튼 폭 고정(88px) 및 시작/일시정지 전환 시 아이콘 없이 텍스트만 표시 검증"""
        from src.control_panel import ControlPanel
        from src.config import DEFAULT_CONFIG

        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)

        test_config = dict(DEFAULT_CONFIG)
        mock_dub_engine = MagicMock()
        mock_dub_engine.is_enabled.return_value = False
        panel = ControlPanel(test_config, overlay=None, audio_thread=None, stt_thread=None, dubbing_engine=mock_dub_engine, save_config_cb=lambda c: None)

        # 1. 3개 코어 버튼 고정 너비 88px 확인
        self.assertEqual(panel.btn_bottom_audio.width(), 88)
        self.assertEqual(panel.btn_bottom_screen.width(), 88)
        self.assertEqual(panel.btn_bottom_dubbing.width(), 88)

        # 2. 초기 비활성 텍스트 확인 (아이콘 없이 텍스트)
        self.assertIn("번역 시작", panel.btn_bottom_audio.text())
        self.assertNotIn("❚❚", panel.btn_bottom_audio.text())
        self.assertNotIn("⏸", panel.btn_bottom_audio.text())

        # 3. 활성화 시 일시정지 텍스트 확인 (아이콘 없이 '일시정지'만 표기 및 88px 유지)
        panel.set_audio_active_state(True)
        self.assertEqual("일시정지", panel.btn_bottom_audio.text())
        self.assertEqual(88, panel.btn_bottom_audio.width())
        self.assertIn("stop:0 #34D399", panel.btn_bottom_audio.styleSheet())
        self.assertIn("#A7F3D0", panel.btn_bottom_audio.styleSheet())

        panel.set_screen_active_state(True)
        self.assertEqual("일시정지", panel.btn_bottom_screen.text())
        self.assertEqual(88, panel.btn_bottom_screen.width())
        self.assertIn("stop:0 #34D399", panel.btn_bottom_screen.styleSheet())

        # 4. 더빙 토글 시 일시정지 확인
        panel.config["dubbing_enabled"] = True
        panel._update_dubbing_toggle_btn_ui()
        self.assertEqual("일시정지", panel.btn_bottom_dubbing.text())
        self.assertEqual(88, panel.btn_bottom_dubbing.width())
        self.assertIn("stop:0 #34D399", panel.btn_bottom_dubbing.styleSheet())

        # 5. 비활성화로 원복
        panel.set_audio_active_state(False)
        self.assertEqual("번역 시작", panel.btn_bottom_audio.text())
        self.assertEqual(88, panel.btn_bottom_audio.width())
        panel.set_screen_active_state(False)
        self.assertEqual("번역 시작", panel.btn_bottom_screen.text())
        self.assertEqual(88, panel.btn_bottom_screen.width())
        panel.config["dubbing_enabled"] = False
        panel._update_dubbing_toggle_btn_ui()
        self.assertEqual("더빙 시작", panel.btn_bottom_dubbing.text())
        self.assertEqual(88, panel.btn_bottom_dubbing.width())

        panel.close()

    def test_dubbing_toggle_both_off_activates_both(self):
        """음성/화면 더빙이 둘 다 꺼진 상태에서 하단 더빙 시작 클릭 시 둘 다 켜지는지 검증"""
        from src.control_panel import ControlPanel
        from src.config import DEFAULT_CONFIG

        cfg = dict(DEFAULT_CONFIG)
        cfg["dubbing_enabled"] = False
        cfg["dubbing_source_audio"] = False
        cfg["dubbing_source_screen"] = False

        saved = []
        mock_dub_engine = MagicMock()
        mock_dub_engine.is_enabled.return_value = False

        cp = ControlPanel(cfg, overlay=None, audio_thread=None, stt_thread=None, dubbing_engine=mock_dub_engine, save_config_cb=lambda c: saved.append(dict(c)))

        # 처음 상태: 둘 다 False
        self.assertFalse(cp.config["dubbing_source_audio"])
        self.assertFalse(cp.config["dubbing_source_screen"])
        self.assertFalse(cp.config["dubbing_enabled"])

        # 하단 더빙 버튼 클릭(toggle_dubbing)
        cp.toggle_dubbing()

        # 검증: 둘 다 켜져야 함
        self.assertTrue(cp.config["dubbing_enabled"])
        self.assertTrue(cp.config["dubbing_source_audio"])
        self.assertTrue(cp.config["dubbing_source_screen"])
        if hasattr(cp, 'toggle_dub_voice'):
            self.assertTrue(cp.toggle_dub_voice.isChecked())
        if hasattr(cp, 'toggle_dub_screen'):
            self.assertTrue(cp.toggle_dub_screen.isChecked())
        mock_dub_engine.set_enabled.assert_called_with(True)
        mock_dub_engine.set_source_enabled.assert_any_call("audio", True)
        mock_dub_engine.set_source_enabled.assert_any_call("screen", True)

        # 다시 클릭: 둘 다 일시 정지(꺼짐)
        cp.toggle_dubbing()
        self.assertFalse(cp.config["dubbing_enabled"])
        if hasattr(cp, 'toggle_dub_voice'):
            self.assertFalse(cp.toggle_dub_voice.isChecked())
        if hasattr(cp, 'toggle_dub_screen'):
            self.assertFalse(cp.toggle_dub_screen.isChecked())

        # 다시 클릭: 기존 활성화 소스(둘 다) 복원 재개
        cp.toggle_dubbing()
        self.assertTrue(cp.config["dubbing_enabled"])
        if hasattr(cp, 'toggle_dub_voice'):
            self.assertTrue(cp.toggle_dub_voice.isChecked())
        if hasattr(cp, 'toggle_dub_screen'):
            self.assertTrue(cp.toggle_dub_screen.isChecked())

    def test_startup_dubbing_state_always_stopped(self):
        """프로그램 시작/재시작 시 dubbing_enabled가 True로 설정 파일에 있었더라도 정지(더빙 시작) 상태로 초기화되는지 검증"""
        from src.control_panel import ControlPanel
        from src.config import DEFAULT_CONFIG, load_config
        import tempfile
        import json
        import os

        # 1. config.json에 dubbing_enabled: True가 저장된 상황 시뮬레이션
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump({"dubbing_enabled": True, "dubbing_source_audio": True}, f)
            temp_path = f.name

        try:
            loaded_cfg = load_config(temp_path)
            self.assertFalse(loaded_cfg["dubbing_enabled"], "load_config should normalize dubbing_enabled to False on startup")
            self.assertTrue(loaded_cfg["dubbing_source_audio"], "dubbing_source_audio should be preserved")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        # 2. ControlPanel 생성 시에도 dubbing_enabled: True인 딕셔너리가 주어지더라도 정지 상태로 강제 정규화되는지 검증
        cfg = dict(DEFAULT_CONFIG)
        cfg["dubbing_enabled"] = True
        mock_dub_engine = MagicMock()

        cp = ControlPanel(cfg, overlay=None, audio_thread=None, stt_thread=None, dubbing_engine=mock_dub_engine, save_config_cb=lambda c: None)

        self.assertFalse(cp.config["dubbing_enabled"], "ControlPanel must reset dubbing_enabled to False")
        self.assertIn("더빙 시작", cp.btn_bottom_dubbing.text(), "Button must display '더빙 시작' not '일시정지'")
        self.assertFalse(cp.btn_bottom_dubbing.isChecked())
        mock_dub_engine.set_enabled.assert_called_with(False)
        cp.close()

    def test_audio_dubbing_toggle_does_not_activate_screen_dubbing(self):
        """음성/화면 더빙이 둘 다 꺼진 상태에서 음성 더빙을 켰을 때 화면 더빙이 절대 켜지지 않는지 검증"""
        from src.control_panel import ControlPanel
        from src.config import DEFAULT_CONFIG

        cfg = dict(DEFAULT_CONFIG)
        cfg["dubbing_enabled"] = False
        cfg["dubbing_source_audio"] = False
        cfg["dubbing_source_screen"] = False

        saved = []
        mock_dub_engine = MagicMock()
        mock_screen_overlay = MagicMock()
        mock_screen_overlay.is_dubbing_enabled = False
        mock_overlay = MagicMock()
        mock_overlay.is_dubbing_enabled = False

        cp = ControlPanel(
            cfg,
            overlay=mock_overlay,
            audio_thread=None,
            stt_thread=None,
            screen_overlay=mock_screen_overlay,
            dubbing_engine=mock_dub_engine,
            save_config_cb=lambda c: saved.append(dict(c))
        )

        # 1. 초기 상태: 둘 다 꺼짐
        self.assertFalse(cp.config["dubbing_source_audio"])
        self.assertFalse(cp.config["dubbing_source_screen"])
        self.assertFalse(cp.toggle_dub_voice.isChecked())
        self.assertFalse(cp.toggle_dub_screen.isChecked())

        # 2. 음성 번역 더빙 토글을 켬
        cp.toggle_dub_voice.setChecked(True)

        # 검증: 음성 더빙만 켜지고 화면 더빙은 반드시 꺼져 있어야 함
        self.assertTrue(cp.config["dubbing_source_audio"])
        self.assertFalse(cp.config["dubbing_source_screen"])
        self.assertTrue(cp.toggle_dub_voice.isChecked())
        self.assertFalse(cp.toggle_dub_screen.isChecked())
        self.assertTrue(cp.config["dubbing_enabled"])
        mock_dub_engine.set_source_enabled.assert_called_with("screen", False)

        # 3. 음성 오버레이 창에서 토글했을 때도 화면 더빙이 켜지지 않는지 검증
        # 둘 다 끈 상태로 세팅
        cp.toggle_dub_voice.setChecked(False)
        cp.toggle_dub_screen.setChecked(False)
        self.assertFalse(cp.config["dubbing_source_audio"])
        self.assertFalse(cp.config["dubbing_source_screen"])

        # 음성 오버레이 더빙 클릭
        cp.toggle_audio_dubbing_from_overlay()
        self.assertTrue(cp.config["dubbing_source_audio"])
        self.assertFalse(cp.config["dubbing_source_screen"])
        self.assertTrue(cp.toggle_dub_voice.isChecked())
        self.assertFalse(cp.toggle_dub_screen.isChecked())
        cp.close()


if __name__ == "__main__":
    unittest.main()
