import copy
import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication, QSizePolicy, QLabel

app = QApplication.instance()
if not app:
    app = QApplication([])

from src.config import DEFAULT_CONFIG
from src.control_panel import ControlPanel
from src.screen_overlay_manager import ScreenOverlayManager


class TestControlPanelLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._ducking = patch("src.process_volume.AudioDuckingManager", autospec=True)
        cls._ducking.start()

    @classmethod
    def tearDownClass(cls):
        cls._ducking.stop()

    def setUp(self):
        self._src = patch(
            "src.audio_capture.AudioLoopbackCapture.get_available_capture_sources",
            return_value=[{"id": "default", "type": "device", "name": "default"}],
        )
        self._speakers = patch("soundcard.all_speakers", return_value=[])
        self._src.start()
        self._speakers.start()
        self.addCleanup(self._src.stop)
        self.addCleanup(self._speakers.stop)
        self.panel = ControlPanel(
            copy.deepcopy(DEFAULT_CONFIG),
            overlay=None,
            audio_thread=None,
            stt_thread=None,
            save_config_cb=lambda c: None,
        )

    def tearDown(self):
        self.panel.close()

    def test_open_log_folder_button_opens_user_data_dir(self):
        from PyQt6.QtGui import QDesktopServices
        self.assertEqual(self.panel.btn_open_logs.text(), "📂 로그 폴더 열기")
        with patch("src.app_paths.roaming_data_dir", return_value=r"C:\fake\LumiTrans"), \
             patch.object(QDesktopServices, "openUrl", return_value=True) as open_url:
            self.panel.btn_open_logs.click()
        open_url.assert_called_once()
        self.assertEqual(open_url.call_args[0][0].toLocalFile().replace("/", "\\"), r"C:\fake\LumiTrans")
        self.panel.deleteLater()

    def test_minimum_size_is_stable_across_tabs(self):
        mins = []
        for index in range(self.panel.tab_stack.count()):
            self.panel._switch_tab(index)
            self.panel.tab_stack.updateGeometry()
            self.panel.updateGeometry()
            mins.append((
                self.panel.minimumWidth(),
                self.panel.minimumHeight(),
                self.panel.tab_stack.minimumSizeHint().width(),
                self.panel.tab_stack.minimumSizeHint().height(),
            ))
        self.assertTrue(all(item == mins[0] for item in mins), mins)
        self.assertEqual(mins[0][0], self.panel.minimumWidth())
        self.assertGreaterEqual(mins[0][0], 700)
        self.assertEqual(mins[0][1], 800)
        self.assertEqual(mins[0][2], 0)
        self.assertEqual(mins[0][3], 0)

    def test_minimum_width_keeps_speaker_controls_and_actions_visible(self):
        self.panel.show()
        self.panel._switch_tab(0)
        self.panel.resize(self.panel.minimumWidth(), self.panel.minimumHeight())
        QApplication.processEvents()
        self.assertGreaterEqual(self.panel.minimumWidth(), self.panel._required_content_width)
        self.assertGreaterEqual(self.panel.speaker_management_card.width(),
                                self.panel._audio_speaker_min_width)
        self.assertGreaterEqual(self.panel.dubbing_settings_card.width(),
                                self.panel._audio_dubbing_min_width)
        self.assertGreaterEqual(self.panel.speaker_controls_layout.geometry().width(),
                                self.panel.speaker_controls_layout.sizeHint().width())
        self.assertGreaterEqual(self.panel.speaker_actions_layout.geometry().width(),
                                self.panel.speaker_actions_layout.sizeHint().width())

    def test_dubbing_card_layout_aligned_top_with_stretch(self):
        dub_card = self.panel.dubbing_settings_card
        layout = dub_card.layout()
        last_item = layout.itemAt(layout.count() - 1)
        self.assertIsNotNone(last_item.spacerItem())
        self.assertEqual(layout.spacing(), 8)

    def test_tab_pages_do_not_dictate_window_minimum(self):
        for index in range(self.panel.tab_stack.count()):
            page = self.panel.tab_stack.widget(index)
            self.assertEqual(page.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Expanding)
            self.assertEqual(page.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Expanding)

    def test_monitor_preview_preserves_selected_screen_ratio(self):
        canvas = self.panel.screen_canvas
        canvas.resize(600, 300)
        canvas.set_monitor(QRect(-1920, 0, 1920, 1080))
        view = canvas._monitor_rect()
        self.assertAlmostEqual(view.width() / view.height(), 1920 / 1080)
        self.assertAlmostEqual(view.x(), (600 - view.width()) / 2)
        self.assertAlmostEqual(view.y(), 0)

    def test_roi_preview_uses_selected_monitor_global_coordinates(self):
        canvas = self.panel.screen_canvas
        canvas.resize(600, 300)
        canvas.set_monitor(QRect(-1920, 0, 1920, 1080))
        view = canvas._monitor_rect()
        roi = canvas._roi_preview_rect([-1824, 108, 384, 216])
        self.assertAlmostEqual(roi.x(), view.x() + view.width() * 0.05)
        self.assertAlmostEqual(roi.y(), view.y() + view.height() * 0.1)
        self.assertAlmostEqual(roi.width(), view.width() * 0.2)
        self.assertIsNone(canvas._roi_preview_rect([100, 100, 200, 100]))

    def test_speaker_status_names_the_active_diarization_solution(self):
        self.assertEqual(self.panel._speaker_status_text(), '화자 분리 꺼짐')
        self.panel.config['speaker_diarization_enabled'] = True
        original_thread = self.panel.stt_thread
        try:
            self.panel.stt_thread = SimpleNamespace(
                deepgram_streamer=SimpleNamespace(is_connected=lambda: True),
                speaker_identifier=SimpleNamespace(is_enabled=True, get_status=lambda: '화자 교대 분석 작동 중'))
            self.panel.config['stt_provider'] = 'deepgram'
            self.assertIn('Deepgram 화자 분리 작동 중', self.panel._speaker_status_text())
            self.panel.config['stt_provider'] = 'local'
            self.assertEqual(self.panel._speaker_status_text(), '로컬 · 화자 교대 분석 작동 중')
        finally:
            self.panel.stt_thread = original_thread

    def test_screen_translation_buttons_call_current_worker_apis(self):
        with patch.object(self.panel, 'screen_worker', Mock()) as screen_worker, \
                patch.object(self.panel, 'inplace_manager', Mock()) as inplace_manager:
            self.panel.trigger_instant_screen_ocr()
            self.panel.trigger_inplace_translate(from_button=True)
            screen_worker.trigger_instant_capture.assert_called_once_with()
            inplace_manager.trigger_snapshot.assert_called_once_with(from_button=True)

    def test_screen_dialogue_table_shows_only_recent_ocr_pairs(self):
        history = self.panel.subtitle_history
        history.add_entry(source="screen", orig_text="Older OCR", trans_text="오래된 OCR")
        history.add_entry(source="audio", orig_text="Audio only", trans_text="음성 전용")
        history.add_entry(source="screen", orig_text="[Andy] Hello", trans_text="[Andy] 안녕하세요", speaker="ROI 1")
        history.add_entry(source="screen", orig_text="Goodbye", trans_text="안녕히 가세요", speaker="ROI 2")

        self.panel._update_mini_chat()
        table = self.panel.screen_dialogue_table
        self.assertEqual((table.rowCount(), table.columnCount()), (2, 2))
        self.assertEqual(table.horizontalHeaderItem(0).text(), "원문")
        self.assertEqual(table.horizontalHeaderItem(1).text(), "번역")
        self.assertEqual(table.item(0, 0).text(), "[Andy] Hello")
        self.assertEqual(table.item(0, 1).text(), "[Andy] 안녕하세요")
        self.assertEqual(table.item(1, 0).text(), "Goodbye")
        self.assertEqual(table.item(1, 1).text(), "안녕히 가세요")

    def test_history_tab_title_label(self):
        titles = [l.text() for l in self.panel.tab_history.findChildren(QLabel) if l.text() in ("자막 기록", "실시간 자막 기록")]
        self.assertIn("자막 기록", titles)
        self.assertNotIn("실시간 자막 기록", titles)

    def test_screen_subtitle_visibility_switch_controls_actual_windows(self):
        overlay = Mock()
        self.panel.screen_overlay = overlay
        self.assertTrue(self.panel.toggle_screen_overlay_vis.isChecked())

        self.panel.toggle_screen_overlay_vis.setChecked(False)
        self.assertFalse(self.panel.config["screen_overlay_visible"])
        overlay.set_visible.assert_called_with(False)

        self.panel.toggle_screen_overlay_vis.setChecked(True)
        self.assertTrue(self.panel.config["screen_overlay_visible"])
        overlay.set_visible.assert_called_with(True)

    def test_screen_overlay_recovers_from_saved_geometry_on_another_monitor(self):
        screen = QApplication.primaryScreen().geometry()
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["screen_rois"] = [[screen.x() + 50, screen.y() + 50, 300, 100]]
        cfg["screen_overlay_geometries"] = {"0": [100000, 100000, 500, 180]}
        manager = ScreenOverlayManager(cfg)
        try:
            self.assertTrue(screen.contains(manager.overlays[0].geometry().center()))
        finally:
            manager.close()

    def test_footer_status_strips_subtitle_markup_before_eliding(self):
        detail = (
            "음성 감지: <span style='color: #FFD54F; font-weight: bold;'>[화자 1]</span> "
            "This is a long preview sentence that should fit within the footer."
        )
        self.panel._do_update_engine_status("recognizing", detail)
        label = self.panel.lbl_status_detail
        self.assertNotIn("<span", label.text())
        self.assertTrue(label.text().startswith("음성 감지: [화자 1]"))
        self.assertIn("This is a long preview sentence", label.toolTip())

    def test_youtube_auto_detect_toggle_controls_config(self):
        self.assertTrue(hasattr(self.panel, 'toggle_auto_youtube'))
        # 기본 옵션: 초기 설치 후 상태에서는 False(OFF)
        self.assertFalse(self.panel.toggle_auto_youtube.isChecked())
        self.assertFalse(self.panel.config.get("auto_youtube_detect", False))

        # 1. Gemini API 키 없이 ON 시도 시: 대화상자에서 No 선택 시 OFF 상태 유지
        from PyQt6.QtWidgets import QMessageBox
        with patch("PyQt6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.No) as mock_q:
            self.panel.toggle_auto_youtube.setChecked(True)
            mock_q.assert_called_once()
            self.assertFalse(self.panel.toggle_auto_youtube.isChecked())
            self.assertFalse(self.panel.config.get("auto_youtube_detect", False))

        # 2. Gemini API 키가 설정된 경우: 정상적으로 ON 활성화
        self.panel.config["gemini_api_key"] = "test-gemini-key"
        self.panel.toggle_auto_youtube.setChecked(True)
        self.assertTrue(self.panel.toggle_auto_youtube.isChecked())
        self.assertTrue(self.panel.config.get("auto_youtube_detect", False))

        # 3. 토글 끄기
        self.panel.toggle_auto_youtube.setChecked(False)
        self.assertFalse(self.panel.toggle_auto_youtube.isChecked())
        self.assertFalse(self.panel.config.get("auto_youtube_detect", False))

    def test_gpu_warmup_toggle_and_manual_youtube_ui(self):
        # 1. GPU 예열 토글 검증
        self.assertTrue(hasattr(self.panel, 'toggle_gpu_warmup'))
        self.assertTrue(self.panel.toggle_gpu_warmup.isChecked())
        self.assertTrue(self.panel.config.get("gpu_warmup_on_startup", True))

        self.panel.toggle_gpu_warmup.setChecked(False)
        self.assertFalse(self.panel.config.get("gpu_warmup_on_startup"))

        self.panel.toggle_gpu_warmup.setChecked(True)
        self.assertTrue(self.panel.config.get("gpu_warmup_on_startup"))

        # 2. 수동 유튜브 URL 입력 UI 요소 검증
        self.assertTrue(hasattr(self.panel, 'edit_youtube_url'))
        self.assertTrue(hasattr(self.panel, 'btn_apply_youtube_url'))
        self.assertTrue(hasattr(self.panel, 'lbl_youtube_status'))

        # 빈 입력 시 상태 안내
        self.panel.edit_youtube_url.setText("")
        self.panel.on_apply_youtube_url_clicked()
        self.assertFalse(self.panel.lbl_youtube_status.isHidden())
        self.assertIn("입력하세요", self.panel.lbl_youtube_status.text())

        # 잘못된 형식 입력 시
        self.panel.edit_youtube_url.setText("https://not-youtube.com/test")
        self.panel.on_apply_youtube_url_clicked()
        self.assertIn("형식이 아닙니다", self.panel.lbl_youtube_status.text())

    def test_instant_screen_translation_ui_and_hotkey_settings(self):
        # 1. 화면 번역 탭의 버튼 이름 검증 ('⚡ 전체 화면 번역')
        self.assertEqual(self.panel.btn_inplace_translate.text(), "⚡ 전체 화면 번역")
        # 단축키 설정 버튼이 화면 번역 탭에서 제거되었는지 확인
        self.assertFalse(hasattr(self.panel, 'btn_screen_hotkey'))

        # 2. 유튜브 URL 입력 컨테이너 조건부 표시 검증 (기본 상태는 OFF이므로 isHidden() == True)
        self.assertTrue(hasattr(self.panel, 'yt_input_container'))
        self.assertTrue(self.panel.yt_input_container.isHidden())
        self.panel.config["gemini_api_key"] = "test-key"
        self.panel.toggle_auto_youtube.setChecked(True)
        self.assertFalse(self.panel.yt_input_container.isHidden())
        self.panel.toggle_auto_youtube.setChecked(False)
        self.assertTrue(self.panel.yt_input_container.isHidden())

        # 3. 설정 탭의 전체 화면 번역 단축키 위젯 검증
        self.assertTrue(hasattr(self.panel, 'btn_settings_hotkey'))
        self.assertTrue(hasattr(self.panel, 'btn_reset_hotkey'))
        self.assertTrue(hasattr(self.panel, 'lbl_hotkey_status'))
        self.assertEqual(self.panel.btn_settings_hotkey.get_hotkey(), "F4")
        self.assertEqual(self.panel.btn_settings_hotkey.text(), "⌨️ 단축키 설정")
        self.assertIn("기본값", self.panel.btn_reset_hotkey.text())
        self.assertNotIn("(F4)", self.panel.btn_reset_hotkey.text())
        self.assertEqual(self.panel.lbl_hotkey_status.text(), "현재 단축키 : F4")

        # 단축키 변경 시 버튼 텍스트는 '⚡ 전체 화면 번역' 유지, 상태 라벨 및 config 갱신
        self.panel._on_inplace_hotkey_changed("Ctrl+F4")
        self.assertEqual(self.panel.btn_inplace_translate.text(), "⚡ 전체 화면 번역")
        self.assertEqual(self.panel.config["inplace_hotkey"], "Ctrl+F4")
        self.assertEqual(self.panel.btn_settings_hotkey.text(), "⌨️ 단축키 설정")
        self.assertEqual(self.panel.lbl_hotkey_status.text(), "현재 단축키 : Ctrl+F4")

        # 리셋 버튼 클릭 시 F4 복원
        self.panel._on_reset_hotkey_clicked()
        self.assertEqual(self.panel.btn_inplace_translate.text(), "⚡ 전체 화면 번역")
        self.assertEqual(self.panel.config["inplace_hotkey"], "F4")
        self.assertEqual(self.panel.lbl_hotkey_status.text(), "현재 단축키 : F4")

        # 단축키 녹음 모드 진입/해제 시 inplace_manager 전역 핫키 비활성화/활성화 검증
        mock_inplace = Mock()
        self.panel.inplace_manager = mock_inplace
        self.panel._on_hotkey_recording_state_changed(True)
        mock_inplace.set_hotkey_enabled.assert_called_with(False)
        self.panel._on_hotkey_recording_state_changed(False)
        mock_inplace.set_hotkey_enabled.assert_called_with(True)

    def test_audio_ducking_toggle_and_attenuation_slider(self):
        # 1. 덕킹 토글 및 감쇄 슬라이더 위젯 존재 확인
        self.assertTrue(hasattr(self.panel, 'toggle_audio_ducking'))
        self.assertTrue(hasattr(self.panel, 'slider_ducking_vol'))
        self.assertTrue(hasattr(self.panel, 'lbl_att_title'))
        self.assertTrue(hasattr(self.panel, 'lbl_att_val'))

        # 2. 초기 상태 검증
        self.assertTrue(self.panel.toggle_audio_ducking.isChecked())
        self.assertTrue(self.panel.slider_ducking_vol.isEnabled())
        self.assertTrue(self.panel.lbl_att_title.isEnabled())
        self.assertTrue(self.panel.lbl_att_val.isEnabled())
        self.assertTrue(self.panel.lbl_att_val.text().endswith("%"))

        # 3. 토글 비활성화 시 슬라이더 및 라벨 비활성화
        self.panel.toggle_audio_ducking.setChecked(False)
        self.assertFalse(self.panel.config.get("audio_ducking_enabled"))
        self.assertFalse(self.panel.slider_ducking_vol.isEnabled())
        self.assertFalse(self.panel.lbl_att_title.isEnabled())
        self.assertFalse(self.panel.lbl_att_val.isEnabled())

        # 4. 토글 재활성화 시 복원
        self.panel.toggle_audio_ducking.setChecked(True)
        self.assertTrue(self.panel.config.get("audio_ducking_enabled"))
        self.assertTrue(self.panel.slider_ducking_vol.isEnabled())
        self.assertTrue(self.panel.lbl_att_title.isEnabled())
        self.assertTrue(self.panel.lbl_att_val.isEnabled())

        # 5. 슬라이더 변경 시 퍼센트 표시 갱신
        self.panel.slider_ducking_vol.setValue(35)
        self.assertEqual(self.panel.lbl_att_val.text(), "35%")
        self.assertEqual(self.panel.config.get("audio_ducking_volume"), 35)

    def test_quick_presets_builtin_icons_and_click(self):
        """하단 영구 바 퀵 프리셋 기본 5종 아이콘 및 클릭 동작 검증"""
        self.assertTrue(hasattr(self.panel, 'quick_presets_widget'))
        self.assertTrue(hasattr(self.panel, 'quick_presets_layout'))

        # 기본 빌트인 프리셋 5개 확인
        btns = [
            self.panel.quick_presets_layout.itemAt(i).widget()
            for i in range(self.panel.quick_presets_layout.count())
            if self.panel.quick_presets_layout.itemAt(i).widget() and hasattr(self.panel.quick_presets_layout.itemAt(i).widget(), 'text')
        ]
        self.assertGreaterEqual(len(btns), 6)
        icons = [b.text() for b in btns[:6]]
        self.assertEqual(icons, ["🌱", "⚡", "⚖️", "🎬", "🔮", "🌐"])

        # 저사양 프리셋 클릭 적용
        with patch.object(self.panel, '_check_model_ready', return_value=True):
            self.panel._on_quick_preset_clicked("low_spec")
        self.assertEqual(self.panel.config.get("translation_engine"), "google")
        self.assertEqual(self.panel.config.get("model_size"), "distil-small.en")
        self.assertEqual(self.panel.config.get("device"), "cpu")
        self.assertEqual(self.panel._active_preset_id, "low_spec")

        # 레거시 cloud 키 클릭 시 low_spec 호환 적용 검증
        with patch.object(self.panel, '_check_model_ready', return_value=True):
            self.panel._on_quick_preset_clicked("cloud")
        self.assertEqual(self.panel._active_preset_id, "low_spec")

    def test_quick_presets_custom_pagination(self):
        """커스텀 프리셋 3개 초과 시 ◀ ▶ 페이징 네비게이션 동작 검증"""
        # 5개 커스텀 프리셋 등록
        self.panel.config["custom_presets"] = {
            f"c_{i}": {
                "name": f"프리셋_{i}",
                "desc": f"설명_{i}",
                "config": {"translation_engine": "google", "content_tempo_preset": "smart"}
            } for i in range(5)
        }
        self.panel._custom_preset_page = 0
        self.panel._refresh_quick_presets_ui()

        # 위젯 파싱: 5개 빌트인 + 1개 구분선 + 1개 이전버튼(◀) + 3개 커스텀 버튼 + 1개 다음버튼(▶)
        all_widgets = [
            self.panel.quick_presets_layout.itemAt(i).widget()
            for i in range(self.panel.quick_presets_layout.count())
            if self.panel.quick_presets_layout.itemAt(i).widget()
        ]
        button_texts = [w.text() for w in all_widgets if hasattr(w, 'text')]
        self.assertIn("◀", button_texts)
        self.assertIn("▶", button_texts)

        # 페이지 0: ◀ 비활성화, ▶ 활성화
        btn_prev = next(w for w in all_widgets if getattr(w, 'text', None) and w.text() == "◀")
        btn_next = next(w for w in all_widgets if getattr(w, 'text', None) and w.text() == "▶")
        self.assertFalse(btn_prev.isEnabled())
        self.assertTrue(btn_next.isEnabled())

        # 다음 페이지 클릭
        self.panel._on_next_custom_preset_page()
        self.assertEqual(self.panel._custom_preset_page, 1)

        # 페이지 1: ◀ 활성화, ▶ 비활성화 (총 5개이므로 2페이지가 끝)
        all_widgets_p1 = [
            self.panel.quick_presets_layout.itemAt(i).widget()
            for i in range(self.panel.quick_presets_layout.count())
            if self.panel.quick_presets_layout.itemAt(i).widget()
        ]
        btn_prev_p1 = next(w for w in all_widgets_p1 if getattr(w, 'text', None) and w.text() == "◀")
        btn_next_p1 = next(w for w in all_widgets_p1 if getattr(w, 'text', None) and w.text() == "▶")
        self.assertTrue(btn_prev_p1.isEnabled())
        self.assertFalse(btn_next_p1.isEnabled())

        # 이전 페이지 클릭
        self.panel._on_prev_custom_preset_page()
        self.assertEqual(self.panel._custom_preset_page, 0)

    def test_quick_custom_preset_click_activates(self):
        """커스텀 프리셋 클릭 시 설정 즉시 반영 및 활성 상태 감지 검증"""
        self.panel.config["custom_presets"] = {
            "custom_game": {
                "name": "🎮 게임용 프리셋",
                "desc": "게임 최적화",
                "config": {
                    "device": "cuda",
                    "stt_provider": "local",
                    "model_size": "distil-small.en",
                    "translation_engine": "google",
                    "content_tempo_preset": "short_form"
                }
            }
        }
        self.panel._refresh_quick_presets_ui()
        self.panel._on_quick_custom_preset_clicked("custom_game")

        self.assertEqual(self.panel.config.get("content_tempo_preset"), "short_form")
        self.assertEqual(self.panel.config.get("translation_engine"), "google")
        self.assertEqual(self.panel._detect_active_preset_id(), "custom_game")

    def test_custom_presets_list_ui_button_and_delete_layout(self):
        """설정 탭 프리셋 목록에서 커스텀 프리셋이 버튼 방식 + 상태 표시 + 별도 삭제 버튼으로 렌더링되는지 검증"""
        self.panel.config["custom_presets"] = {
            "c_ready": {
                "name": "준비된 프리셋",
                "desc": "구글 번역 즉시 실행",
                "config": {"translation_engine": "google", "stt_provider": "local"}
            },
            "c_need_key": {
                "name": "Groq 프리셋",
                "desc": "키 필요 프리셋",
                "config": {"translation_engine": "groq", "stt_provider": "local"}
            }
        }
        self.panel.config["groq_api_key"] = ""
        self.panel._refresh_presets_ui()

        # preset_list_layout 항목 순회
        items = [
            self.panel.preset_list_layout.itemAt(i).widget()
            for i in range(self.panel.preset_list_layout.count())
            if self.panel.preset_list_layout.itemAt(i).widget()
        ]

        # 기본 빌트인 5개 다음 타이틀 1개 다음 커스텀 row_widget 2개
        titles = [w for w in items if isinstance(w, QLabel) and "커스텀 프리셋" in w.text()]
        self.assertEqual(len(titles), 1)
        self.assertEqual(titles[0].text(), "⭐ 커스텀 프리셋")

        custom_rows = [w for w in items if w.layout() and w.layout().count() == 2]
        self.assertEqual(len(custom_rows), 2)

        # 첫 번째 커스텀 행 검증: [프리셋 선택 버튼] [삭제 버튼]
        row0_layout = custom_rows[0].layout()
        btn_preset_0 = row0_layout.itemAt(0).widget()
        btn_del_0 = row0_layout.itemAt(1).widget()

        self.assertIsNotNone(btn_preset_0)
        self.assertIsNotNone(btn_del_0)
        self.assertFalse(btn_del_0.icon().isNull())
        self.assertEqual(btn_del_0.width(), 30)

        # 프리셋 버튼 내부 라벨 및 상태 뱃지 검증
        preset_inner_widgets = [
            btn_preset_0.layout().itemAt(j).widget()
            for j in range(btn_preset_0.layout().count())
            if btn_preset_0.layout().itemAt(j).widget()
        ]
        lbl_name = preset_inner_widgets[0]
        badge = preset_inner_widgets[1]
        self.assertIn("준비된 프리셋", lbl_name.text())
        self.assertIsNotNone(badge.pixmap())
        self.assertEqual(badge.toolTip(), "즉시 실행")

        # 두 번째 커스텀 행 검증 (Groq 키 미입력 상태 -> 키 필요)
        row1_layout = custom_rows[1].layout()
        btn_preset_1 = row1_layout.itemAt(0).widget()
        preset_inner_1 = [
            btn_preset_1.layout().itemAt(j).widget()
            for j in range(btn_preset_1.layout().count())
            if btn_preset_1.layout().itemAt(j).widget()
        ]
        badge_1 = preset_inner_1[1]
        self.assertEqual(badge_1.toolTip(), "키 필요")

        # 프리셋 클릭 시 적용 동작 검증 (QMessageBox 모달 모킹)
        with patch("PyQt6.QtWidgets.QMessageBox.information"):
            btn_preset_0.click()
        self.assertEqual(self.panel.config.get("translation_engine"), "google")
        self.assertEqual(self.panel._active_preset_id, "c_ready")

    def test_tab4_api_card_info_at_bottom(self):
        """설정 탭(Tab 4)의 API 키 관리 카드에서 안내 문구가 stretch 뒤(맨 아래)에 위치하는지 검증"""
        api_card = self.panel.input_card_deepgram.parentWidget()
        layout = api_card.layout()
        total_items = layout.count()
        last_item = layout.itemAt(total_items - 1)
        prev_item = layout.itemAt(total_items - 2)

        # 맨 마지막 아이템은 안내 레이블
        last_widget = last_item.widget()
        self.assertIsNotNone(last_widget)
        self.assertIn("API 키는 로컬에 안전하게 저장되며", last_widget.text())

        # 그 직전 아이템은 stretch
        self.assertIsNotNone(prev_item.spacerItem())

    def test_pipeline_chips_fixed_widths(self):
        """하단 상태바의 파이프라인 구성 컨테이너 및 칩 버튼들의 고정 폭 검증"""
        self.assertEqual(self.panel.pipe_container.width(), 633)
        self.assertEqual(self.panel.pipe_container.maximumWidth(), 633)
        self.assertEqual(self.panel.pipe_container.minimumWidth(), 633)

        self.assertEqual(self.panel.chip_stt_dev.maximumWidth(), 108)
        self.assertEqual(self.panel.chip_stt_dev.minimumWidth(), 108)

        self.assertEqual(self.panel.chip_stt_model.maximumWidth(), 190)
        self.assertEqual(self.panel.chip_stt_model.minimumWidth(), 190)

        self.assertEqual(self.panel.chip_trans.maximumWidth(), 130)
        self.assertEqual(self.panel.chip_trans.minimumWidth(), 130)

        self.assertEqual(self.panel.chip_tempo.maximumWidth(), 127)
        self.assertEqual(self.panel.chip_tempo.minimumWidth(), 127)

        # 여러 프리셋 모킹 후 뱃지 및 파이프라인 텍스트 갱신 시에도 폭이 일정하게 유지되는지 검증
        self.panel.config["device"] = "cuda"
        self.panel.config["stt_provider"] = "deepgram"
        self.panel.config["deepgram_model"] = "nova-3"
        self.panel.config["model_size"] = "distil-large-v3.5"
        self.panel.config["translation_engine"] = "gemini"
        self.panel.config["content_tempo_preset"] = "movie"
        self.panel._sync_all_pipeline_status()
        self.panel._refresh_all_status_badges()

        self.assertEqual(self.panel.pipe_container.width(), 633)
        self.assertEqual(self.panel.chip_stt_dev.width(), 108)
        self.assertEqual(self.panel.chip_stt_model.width(), 190)
        self.assertEqual(self.panel.chip_trans.width(), 130)
        self.assertEqual(self.panel.chip_tempo.width(), 127)

        # Exaone 설정으로 변경 시에도 검증
        self.panel.config["stt_provider"] = "local"
        self.panel.config["device"] = "cuda"
        self.panel.config["model_size"] = "distil-large-v3.5"
        self.panel.config["translation_engine"] = "exaone"
        self.panel.config["content_tempo_preset"] = "smart"
        self.panel._sync_all_pipeline_status()
        self.panel._refresh_all_status_badges()

        self.assertEqual(self.panel.pipe_container.width(), 633)
        self.assertEqual(self.panel.chip_stt_dev.width(), 108)
        self.assertEqual(self.panel.chip_stt_model.width(), 190)
        self.assertEqual(self.panel.chip_trans.width(), 130)
        self.assertEqual(self.panel.chip_tempo.width(), 127)

    def test_pipeline_stt_model_button_text_formatting(self):
        """STT 모델 칩 버튼의 텍스트가 메뉴 목록 명칭(아이콘 제거, 한글 명칭)과 일치하는지 검증"""
        self.panel.config["stt_provider"] = "local"
        self.panel.config["device"] = "cuda"
        self.panel.config["model_size"] = "large-v3-turbo"

        # 다국어 모델: 각 언어별 표시 검증 (아이콘 없이 정확한 명칭)
        expected_mappings = {
            "auto": "🤖 large-v3-turbo (자동감지) ▾",
            "ja": "🤖 large-v3-turbo (일본어) ▾",
            "en": "🤖 large-v3-turbo (영어) ▾",
            "zh": "🤖 large-v3-turbo (중국어) ▾",
            "ko": "🤖 large-v3-turbo (한국어) ▾",
        }
        for lang_code, expected_text in expected_mappings.items():
            self.panel.config["stt_language"] = lang_code
            self.panel._sync_all_pipeline_status()
            self.assertEqual(self.panel.chip_stt_model.text(), expected_text)
            self.assertNotIn("🌐", self.panel.chip_stt_model.text())
            self.assertNotIn("(JA)", self.panel.chip_stt_model.text())
            self.assertNotIn("(KO)", self.panel.chip_stt_model.text())
            self.assertNotIn("(ZH)", self.panel.chip_stt_model.text())

        # 영문 전용 모델(distil-small.en): 언어 태그 없이 모델명만 표시
        self.panel.config["model_size"] = "distil-small.en"
        self.panel.config["stt_language"] = "en"
        self.panel._sync_all_pipeline_status()
        self.assertEqual(self.panel.chip_stt_model.text(), "🤖 distil-small.en ▾")

    def test_preset_scroll_fixed_size_and_scrollable(self):
        """커스텀 프리셋이 추가되어도 창 높이가 늘어나지 않고 스크롤 처리되는지 검증"""
        # 초기 창 높이 확인
        initial_min_h = self.panel.minimumHeight()
        self.assertEqual(initial_min_h, 800)

        # 6개 커스텀 프리셋 추가
        self.panel.config["custom_presets"] = {
            f"c_{i}": {"name": f"커스텀 프리셋 {i}", "config": {}}
            for i in range(6)
        }
        self.panel.show()
        self.panel.resize(1100, 800)
        self.panel._switch_tab(4)
        self.panel._refresh_presets_ui()
        QApplication.processEvents()

        # 스크롤 영역의 sizeHint가 창을 밀어올리지 않도록 240으로 고정되었는지 확인
        self.assertEqual(self.panel.preset_scroll.sizeHint().height(), 240)

        # 창의 최소 높이가 여전히 800으로 안정 유지되는지 확인
        self.assertEqual(self.panel.minimumHeight(), 800)

        # 내부 위젯이 충분한 크기를 갖고 스크롤 가능 상태(maximum > 0)인지 확인
        self.assertGreater(self.panel.preset_container_widget.sizeHint().height(), self.panel.preset_scroll.height())
        self.assertGreater(self.panel.preset_scroll.verticalScrollBar().maximum(), 0)

    def test_builtin_presets_ssot_and_hymt(self):
        """BUILTIN_PRESETS SSOT 단일화 및 Hy-MT2/저사양(CPU)/글로벌 다국어 연동 검증"""
        from src.config import BUILTIN_PRESETS, DEFAULT_CONFIG

        # 1. 6종 프리셋 존재 및 키/아이콘 검증 (저사양, 초저지연, 스마트 밸런스, 영화 드라마, 로컬 마스터피스, 글로벌 다국어)
        expected_keys = ["low_spec", "live", "balance", "cinema", "masterpiece", "global"]
        self.assertEqual(list(BUILTIN_PRESETS.keys()), expected_keys)
        self.assertEqual(BUILTIN_PRESETS["low_spec"]["icon"], "🌱")
        self.assertEqual(BUILTIN_PRESETS["live"]["icon"], "⚡")
        self.assertEqual(BUILTIN_PRESETS["balance"]["icon"], "⚖️")
        self.assertEqual(BUILTIN_PRESETS["cinema"]["icon"], "🎬")
        self.assertEqual(BUILTIN_PRESETS["masterpiece"]["icon"], "🔮")
        self.assertEqual(BUILTIN_PRESETS["global"]["icon"], "🌐")

        # 2. 초기 기본 설정(DEFAULT_CONFIG) 상태에서 low_spec이 자동 활성으로 감지되는지 확인
        self.panel.config["device"] = "cpu"
        self.panel.config["translation_engine"] = "google"
        self.panel.config["model_size"] = "distil-small.en"
        self.panel.config["content_tempo_preset"] = "smart"
        self.panel._active_preset_id = None
        detected = self.panel._detect_active_preset_id()
        self.assertEqual(detected, "low_spec")

        # 3. 초저지연 라이브 적용 시 distil-small.en, Tencent Hy-MT2 1.8B(hymt), 유튜브 템포 확인
        with patch.object(self.panel, '_check_model_ready', return_value=True):
            self.panel.apply_preset("live", notify=False)
        self.assertEqual(self.panel.config["translation_engine"], "hymt")
        self.assertEqual(self.panel.config["model_size"], "distil-small.en")
        self.assertEqual(self.panel.config["content_tempo_preset"], "youtube")
        self.assertEqual(self.panel.config["device"], "cuda")
        self.assertEqual(self.panel._active_preset_id, "live")

        # 4. 스마트 밸런스 적용 시 distil-small.en, LG EXAONE 3.5 2.4B(exaone), 스마트 템포 확인
        with patch.object(self.panel, '_check_model_ready', return_value=True):
            self.panel.apply_preset("balance", notify=False)
        self.assertEqual(self.panel.config["translation_engine"], "exaone")
        self.assertEqual(self.panel.config["model_size"], "distil-small.en")
        self.assertEqual(self.panel.config["content_tempo_preset"], "smart")
        self.assertEqual(self.panel._active_preset_id, "balance")

        # 5. 로컬 마스터피스 적용 시 distil-large-v3.5, LG EXAONE 3.5 7.8B(exaone7b), 인터뷰 템포 확인
        with patch.object(self.panel, '_check_model_ready', return_value=True):
            self.panel.apply_preset("masterpiece", notify=False)
        self.assertEqual(self.panel.config["translation_engine"], "exaone7b")
        self.assertEqual(self.panel.config["model_size"], "distil-large-v3.5")
        self.assertEqual(self.panel.config["content_tempo_preset"], "interview")
        self.assertEqual(self.panel._active_preset_id, "masterpiece")

        # 6. 영화 드라마 적용 시 distil-large-v3.5, TranslateGemma 4B(gemma), 영화 템포 확인
        with patch.object(self.panel, '_check_model_ready', return_value=True):
            self.panel.apply_preset("cinema", notify=False)
        self.assertEqual(self.panel.config["translation_engine"], "gemma")
        self.assertEqual(self.panel.config["model_size"], "distil-large-v3.5")
        self.assertEqual(self.panel.config["content_tempo_preset"], "movie")
        self.assertEqual(self.panel._active_preset_id, "cinema")

        # 7. 저사양 호환 적용 시 Google 번역, CPU, int8, distil-small.en 적용 확인
        self.panel.apply_preset("low_spec", notify=False)
        self.assertEqual(self.panel.config["translation_engine"], "google")
        self.assertEqual(self.panel.config["device"], "cpu")
        self.assertEqual(self.panel.config["compute_type"], "int8")
        self.assertEqual(self.panel.config["model_size"], "distil-small.en")
        self.assertEqual(self.panel.config["content_tempo_preset"], "smart")
        self.assertEqual(self.panel._active_preset_id, "low_spec")

        # 8. 글로벌 다국어 적용 시 large-v3-turbo, Tencent Hy-MT2 1.8B(hymt), stt_language="auto", 스마트 템포 확인
        with patch.object(self.panel, '_check_model_ready', return_value=True):
            self.panel.apply_preset("global", notify=False)
        self.assertEqual(self.panel.config["translation_engine"], "hymt")
        self.assertEqual(self.panel.config["model_size"], "large-v3-turbo")
        self.assertEqual(self.panel.config["stt_language"], "auto")
        self.assertEqual(self.panel.config["content_tempo_preset"], "smart")
        self.assertEqual(self.panel.config["device"], "cuda")
        self.assertEqual(self.panel._active_preset_id, "global")

    def test_stt_language_menu_options_and_gating(self):
        """STT 언어 메뉴에서 '🇯🇵 일본어 전용' 표기 및 다국어 모델 여부에 따른 활성화/비활성화 검증"""
        # 1. 영문 전용 모델(distil-small.en)인 경우
        self.panel.config["stt_provider"] = "local"
        self.panel.config["model_size"] = "distil-small.en"
        self.panel.config["stt_language"] = "en"

        menu_instance = None
        def mock_popup(menu, widget):
            nonlocal menu_instance
            menu_instance = menu

        with patch.object(self.panel, '_popup_menu_above', side_effect=mock_popup):
            self.panel._show_pipe_stt_model_menu()

        self.assertIsNotNone(menu_instance)
        actions = menu_instance.actions()

        # Verify header has no icon
        header_act = next((a for a in actions if "STT 인식 언어 선택" in a.text()), None)
        self.assertIsNotNone(header_act)
        self.assertEqual(header_act.text(), "STT 인식 언어 선택")

        # Verify exact Japanese label without front icons, and trailing red dot
        ja_action = next((a for a in actions if "일본어" in a.text()), None)
        self.assertIsNotNone(ja_action)
        self.assertNotIn("🇯🇵", ja_action.text())
        self.assertNotIn("🔒", ja_action.text())
        self.assertNotIn("전용", ja_action.text())
        self.assertTrue(ja_action.text().endswith("\t🔴"))
        self.assertFalse(ja_action.isEnabled())

        # For English-only model: Auto option MUST have red dot and be disabled
        auto_action = next((a for a in actions if "자동감지" in a.text()), None)
        self.assertIsNotNone(auto_action)
        self.assertNotIn("🌐", auto_action.text())
        self.assertNotIn("🔒", auto_action.text())
        self.assertTrue(auto_action.text().endswith("\t🔴"))
        self.assertFalse(auto_action.isEnabled())

        # English option MUST have green dot and be enabled
        en_action = next((a for a in actions if "영어" in a.text()), None)
        self.assertIsNotNone(en_action)
        self.assertNotIn("🇺🇸", en_action.text())
        self.assertTrue(en_action.text().endswith("\t🟢"))
        self.assertTrue(en_action.isEnabled())

        # Verify no lock icons anywhere in STT menu actions on CPU
        for a in actions:
            self.assertNotIn("🔒", a.text())
        medium_act = next((a for a in actions if "medium.en" in a.text()), None)
        if medium_act:
            self.assertFalse(medium_act.isEnabled())
            self.assertTrue(medium_act.text().startswith("   "))


        # 2. 다국어 모델(large-v3-turbo)인 경우: 모든 언어가 녹색 동그라미(🟢)와 활성화
        self.panel.config["model_size"] = "large-v3-turbo"
        with patch.object(self.panel, '_popup_menu_above', side_effect=mock_popup):
            self.panel._show_pipe_stt_model_menu()

        actions_multi = menu_instance.actions()
        ja_multi = next((a for a in actions_multi if "일본어" in a.text()), None)
        self.assertIsNotNone(ja_multi)
        self.assertTrue(ja_multi.text().endswith("\t🟢"))
        self.assertTrue(ja_multi.isEnabled())

        auto_multi = next((a for a in actions_multi if "자동감지" in a.text()), None)
        self.assertIsNotNone(auto_multi)
        self.assertTrue(auto_multi.text().endswith("\t🟢"))
        self.assertTrue(auto_multi.isEnabled())

        # 3. 모델 변경 시 영문 전용 모델로 바뀌면 stt_language가 en으로 자동 리셋되는지 검증
        self.panel.config["stt_language"] = "ja"
        self.panel._on_stt_model_quick_selected("distil-small.en")
        self.assertEqual(self.panel.config["stt_language"], "en")

        # 4. STT 버튼 토글 닫기 검증: 메뉴 닫힌 직후(<0.25s) 다시 클릭 시 메뉴가 재오픈되지 않고 닫힌 상태 유지
        import time
        self.panel._last_menu_closed_widget = self.panel.chip_stt_model
        self.panel._last_pipe_menu_closed_time = time.time()
        with patch.object(self.panel, '_popup_menu_above') as mock_popup_call:
            self.panel._show_pipe_stt_model_menu(force=False)
            mock_popup_call.assert_not_called()

        # 5. 다국어 모델 퀵메뉴 액션의 _keep_open 속성 및 인플레이스 상태 갱신 검증 (깜빡임 없는 무닫힘 갱신)
        self.panel.config["device"] = "cuda"
        self.panel.config["model_size"] = "distil-small.en"
        menu_ref = None
        def mock_popup_cap(menu, widget):
            nonlocal menu_ref
            menu_ref = menu
        with patch.object(self.panel, '_popup_menu_above', side_effect=mock_popup_cap):
            self.panel._show_pipe_stt_model_menu(force=True)

        self.assertIsNotNone(menu_ref)
        actions = menu_ref.actions()
        act_turbo = next((a for a in actions if "large-v3-turbo" in a.text()), None)
        self.assertIsNotNone(act_turbo)
        self.assertTrue(getattr(act_turbo, "_keep_open", False))

        act_distil = next((a for a in actions if "distil-small.en" in a.text()), None)
        self.assertIsNotNone(act_distil)
        self.assertFalse(getattr(act_distil, "_keep_open", False))

        # 다국어 모델 클릭 시그널 발생 시 인플레이스로 언어 옵션들이 🟢 활성화로 즉시 갱신되는지 확인
        act_turbo.trigger()
        act_ja = next((a for a in actions if "일본어" in a.text()), None)
        self.assertIsNotNone(act_ja)
        self.assertTrue(act_ja.text().endswith("\t🟢"))
        self.assertTrue(act_ja.isEnabled())

    def test_api_key_dialog_clean_labels_and_tips(self):
        """API 키 관리 팝업 다이얼로그의 라벨에 중복 링크가 제거되고 하단에 서비스명과 링크만 깔끔하게 남았는지 검증"""
        from src.control_panel import ApiKeyDialog
        from PyQt6.QtWidgets import QFormLayout, QLabel
        dlg = ApiKeyDialog(self.panel.config, self.panel)

        # 폼 레이아웃 찾기
        form_layout = dlg.findChild(QFormLayout)
        self.assertIsNotNone(form_layout)

        # 1. 폼 라벨 검증: ↗ 및 URL 링크가 제거되고 순수 라벨명만 남았는지 확인
        expected_labels = ["DeepL API Key:", "Gemini Flash Key:", "Groq LPU Key:", "Deepgram Key:"]
        actual_labels = []
        for row in range(form_layout.rowCount()):
            item = form_layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if item and item.widget():
                w = item.widget()
                actual_labels.append(w.text())
                self.assertNotIn("↗", w.text())
                self.assertNotIn("http", w.text())
                self.assertNotIn("deepl.com", w.text())
                self.assertNotIn("aistudio.google.com", w.text())
        self.assertEqual(actual_labels, expected_labels)

        # 2. 하단 팁 라벨 검증: 서비스명과 링크만 남고 부가 설명(Developer 100만 자..., 초고속... 등)이 제거되었는지 확인
        all_labels = dlg.findChildren(QLabel)
        tips_lbl = next((l for l in all_labels if "• DeepL:" in l.text()), None)
        self.assertIsNotNone(tips_lbl)
        self.assertNotIn("Developer 100만 자", tips_lbl.text())
        self.assertNotIn("초고속 초월번역", tips_lbl.text())
        self.assertNotIn("초저지연 LPU", tips_lbl.text())
        self.assertNotIn("200 무료 크레딧", tips_lbl.text())
        self.assertIn("deepl.com/pro-api", tips_lbl.text())
        self.assertIn("aistudio.google.com", tips_lbl.text())
        self.assertIn("console.groq.com", tips_lbl.text())
        self.assertIn("console.deepgram.com", tips_lbl.text())

        dlg.close()


if __name__ == "__main__":
    unittest.main()


