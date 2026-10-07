import os
import sys
import unittest
from PyQt6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QApplication.instance() or QApplication(sys.argv)

from src.config import DEFAULT_CONFIG
from src.control_panel import ControlPanel
from src.dubbing_engine import DubbingEngine


class TestDubbingSyncAndVoices(unittest.TestCase):
    def setUp(self):
        self.config = DEFAULT_CONFIG.copy()
        self.config["dubbing_enabled"] = False
        self.config["dubbing_source_audio"] = True
        self.config["dubbing_source_screen"] = True
        self.config["dubbing_voice_audio"] = "auto"
        self.config["dubbing_voice_screen"] = "auto"

        self.cp = ControlPanel(
            config=self.config,
            overlay=None,
            audio_thread=None,
            stt_thread=None,
            save_config_cb=lambda c: None
        )

    def tearDown(self):
        if hasattr(self.cp, '_cleanup_on_close'):
            self.cp._cleanup_on_close()
        self.cp.close()

    def test_dubbing_voice_combos_population(self):
        """음성/화면 더빙 목소리 콤보박스 생성 및 타겟 언어 변경 연동 검증"""
        self.assertTrue(hasattr(self.cp, 'combo_dub_voice_audio'))
        self.assertTrue(hasattr(self.cp, 'combo_dub_voice_screen'))

        # 초기에는 한국어(ko) 기준으로 음성 목록이 로드되어 있어야 함
        self.assertGreater(self.cp.combo_dub_voice_audio.count(), 1)
        self.assertGreater(self.cp.combo_dub_voice_screen.count(), 1)

        # 목소리 변경 테스트
        self.cp.combo_dub_voice_audio.setCurrentIndex(1)
        chosen_audio_v = self.cp.combo_dub_voice_audio.itemData(1)
        self.assertEqual(self.cp.config.get("dubbing_voice_audio"), chosen_audio_v)

        self.cp.combo_dub_voice_screen.setCurrentIndex(1)
        chosen_screen_v = self.cp.combo_dub_voice_screen.itemData(1)
        self.assertEqual(self.cp.config.get("dubbing_voice_screen"), chosen_screen_v)

        # 타겟 언어를 영어(en)로 변경 시 목소리 콤보박스 자동 재구성 검증
        self.cp._apply_target_lang("en")
        en_items = [self.cp.combo_dub_voice_audio.itemData(i) for i in range(self.cp.combo_dub_voice_audio.count())]
        self.assertTrue(any("en-" in item for item in en_items if item != "auto"))

    def test_dubbing_toggle_and_overlay_bidirectional_sync(self):
        """컨트롤 패널 ↔ 오버레이 더빙 버튼 양방향 동기화 검증"""
        self.assertTrue(hasattr(self.cp, 'toggle_dub_voice'))
        self.assertTrue(hasattr(self.cp, 'toggle_dub_screen'))

        # 1. 컨트롤 패널에서 음성 더빙 ON
        self.cp.toggle_dub_voice.setChecked(True)
        self.assertTrue(self.cp.config.get("dubbing_source_audio"))
        self.assertTrue(self.cp.config.get("dubbing_enabled"))
        if hasattr(self.cp, 'overlay') and hasattr(self.cp.overlay, 'btn_dubbing'):
            self.assertTrue(self.cp.overlay.btn_dubbing.isChecked())

        # 2. 오버레이에서 음성 더빙 클릭하여 OFF
        if hasattr(self.cp, 'overlay') and hasattr(self.cp.overlay, 'btn_dubbing'):
            self.cp.overlay.btn_dubbing.setChecked(False)
            self.cp.overlay.btn_dubbing.clicked.emit(False)
            self.assertFalse(self.cp.config.get("dubbing_source_audio"))
            self.assertFalse(self.cp.toggle_dub_voice.isChecked())

        # 3. 화면 번역 오버레이 더빙 버튼 클릭하여 ON
        if hasattr(self.cp, 'screen_overlay') and hasattr(self.cp.screen_overlay, 'btn_dubbing'):
            self.cp.screen_overlay.btn_dubbing.setChecked(True)
            self.cp.screen_overlay.btn_dubbing.clicked.emit(True)
            self.assertTrue(self.cp.config.get("dubbing_source_screen"))
            self.assertTrue(self.cp.config.get("dubbing_enabled"))
            self.assertTrue(self.cp.toggle_dub_screen.isChecked())

    def test_subtitle_history_dubbing_flow(self):
        """자막 수신(대기 상태) -> 더빙 재생(완료 상태) 전체 파이프라인 자막 탐색기 기록 검증"""
        # 더빙 활성화 설정
        self.cp.config["dubbing_enabled"] = True
        self.cp.config["dubbing_source_audio"] = True
        self.cp.is_active = True

        # 1. 음성 자막 수신 -> 'waiting' 상태로 자막 탐색기 등록 확인
        self.cp._on_audio_subtitle_received("Hello world", "안녕하세요 세계", "Whisper + Google")
        entries = self.cp.subtitle_history.entries
        last_entry = entries[-1]
        self.assertEqual(last_entry.clean_trans, "안녕하세요 세계")
        self.assertEqual(last_entry.dub_status, "waiting")

        # 2. 더빙 재생 완료 콜백 수신 -> 해당 자막 항목의 dub_status가 'done'으로 갱신 확인
        self.cp._on_dubbing_playback_received(
            text="안녕하세요 세계",
            speaker="화자 1",
            orig_text="Hello world",
            source="audio",
            voice="ko-KR-InJoonNeural",
            speed="+0%"
        )
        self.assertEqual(last_entry.dub_status, "done")
        self.assertEqual(last_entry.dub_text, "안녕하세요 세계")
        self.assertEqual(last_entry.voice, "ko-KR-InJoonNeural")

    def test_save_all_settings_includes_dubbing(self):
        """종료 시 더빙 관련 설정(채널별 활성화, 목소리)이 정상 저장되는지 검증"""
        self.cp.toggle_dub_voice.setChecked(True)
        self.cp.toggle_dub_voice.setChecked(False)
        self.cp.toggle_dub_screen.setChecked(True)
        self.cp.combo_dub_voice_audio.setCurrentIndex(1)
        self.cp.combo_dub_voice_screen.setCurrentIndex(1)

        saved = {}
        self.cp.save_config_cb = lambda c: saved.update(c)
        self.cp.save_all_settings_before_exit()

        self.assertIn("dubbing_source_audio", saved)
        self.assertFalse(saved["dubbing_source_audio"])
        self.assertTrue(saved["dubbing_source_screen"])
        self.assertIn("dubbing_voice_audio", saved)
        self.assertIn("dubbing_voice_screen", saved)


if __name__ == "__main__":
    unittest.main()
