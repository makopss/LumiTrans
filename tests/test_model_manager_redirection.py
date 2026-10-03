import os
import sys
import unittest
from unittest.mock import patch, MagicMock

from PyQt6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from src.control_panel import ControlPanel
from src.stt_model_manager import STTModelManager, STTDownloadWorker
from src.llm_model_manager import LLMModelManager


class TestModelManagerRedirection(unittest.TestCase):
    def setUp(self):
        self.config = {
            "device": "cuda",
            "model_size": "large-v3-turbo",
            "stt_provider": "local",
            "stt_language": "auto",
            "translation_engine": "google",
            "content_tempo_preset": "smart",
            "deepgram_api_key": "",
            "groq_api_key": "",
            "custom_model_dir": "",
        }
        self.panel = ControlPanel(
            self.config,
            overlay=None,
            audio_thread=None,
            stt_thread=None,
            save_config_cb=lambda c: None,
        )

    def tearDown(self):
        self.panel.close()

    def test_stt_download_worker_uses_cache_dir_not_output_directory(self):
        """STTDownloadWorker가 huggingface_hub.snapshot_download 호출 시 올바른 cache_dir 매개변수를 사용하는지 검증"""
        worker = STTDownloadWorker({"id": "tiny", "hf_id": "Systran/faster-whisper-tiny"})
        with patch("huggingface_hub.snapshot_download") as mock_dl:
            mock_dl.return_value = "/fake/model/path"
            with patch.object(STTModelManager, "heal_snapshot_symlinks"):
                worker.run()
                mock_dl.assert_called_once()
                args, kwargs = mock_dl.call_args
                self.assertIn("cache_dir", kwargs)
                self.assertNotIn("output_directory", kwargs)

    def test_uninstalled_stt_quick_select_prompts_to_open_manager(self):
        """퀵메뉴에서 미설치 STT 모델 클릭 시 백그라운드 다운로드가 아닌 모델 관리창으로 유도하는지 검증"""
        with patch.object(STTModelManager, "is_model_installed", return_value=False), \
             patch.object(STTModelManager, "is_bundled_model", return_value=False), \
             patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as mock_q, \
             patch.object(self.panel, "open_stt_model_manager") as mock_open:

            orig_model = self.panel.config["model_size"]
            self.panel._on_stt_model_quick_selected("large-v3")

            # QMessageBox가 호출되었는지 확인
            mock_q.assert_called_once()
            # open_stt_model_manager가 target_model_id와 함께 호출되었는지 확인
            mock_open.assert_called_once_with(target_model_id="large-v3")
            # config["model_size"]가 미설치 모델로 무단 변경되지 않았는지 확인
            self.assertEqual(self.panel.config["model_size"], orig_model)

    def test_uninstalled_stt_combo_changed_prompts_to_open_manager(self):
        """설정 탭 콤보박스에서 미설치 STT 모델 선택 시 모델 관리창으로 유도 및 콤보 롤백 검증"""
        with patch.object(STTModelManager, "is_model_installed", return_value=False), \
             patch.object(STTModelManager, "is_bundled_model", return_value=False), \
             patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as mock_q, \
             patch.object(self.panel, "open_stt_model_manager") as mock_open:

            idx = self.panel.combo_model.findText("distil-large-v3")
            if idx >= 0:
                self.panel.on_model_changed(idx)
                mock_q.assert_called_once()
                mock_open.assert_called_once_with(target_model_id="distil-large-v3")

    def test_preset_preflight_prompts_to_open_llm_manager(self):
        """프리셋 클릭 시 미설치 LLM 모델이 필요한 경우 모델 관리창 열기로 유도되는지 검증"""
        with patch.object(self.panel, "open_llm_model_manager") as mock_open:
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as mock_q:
                ret = self.panel._handle_preset_model_preflight("EXAONE 2.4B", "exaone", "pro_kr", notify=False)
                self.assertFalse(ret)
                mock_open.assert_called_once_with(target_model_id="exaone")
                mock_q.assert_called_once()
                args, _ = mock_q.call_args
                self.assertIn("EXAONE 2.4B", args[2])
                self.assertIn("모델 관리창을 열어 모델을 다운로드하시겠습니까?", args[2])

    def test_uninstalled_llm_engine_selection_routes_to_llm_manager(self):
        """번역 엔진으로 미설치 LLM 선택 시 모델 관리창으로 target_model_id와 함께 유도되는지 검증"""
        with patch.object(LLMModelManager, "is_cuda_binary_available", return_value=True), \
             patch.object(LLMModelManager, "is_gguf_model_installed", return_value=False), \
             patch.object(LLMModelManager, "check_ollama_alive", return_value=(False, "")), \
             patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as mock_q, \
             patch.object(self.panel, "open_llm_model_manager") as mock_open:

            self.panel.set_engine_by_key("exaone")

            mock_q.assert_called_once()
            mock_open.assert_called_once_with(target_model_id="exaone")

    def test_preset_preflight_prompts_to_open_stt_manager_when_stt_uninstalled(self):
        """프리셋 적용 시 LLM은 설치되어 있으나 STT 모델이 미설치된 경우 STT 모델 관리창으로 유도되는지 검증"""
        with patch.object(self.panel, "_check_model_ready", return_value=True), \
             patch.object(STTModelManager, "is_model_installed", return_value=False), \
             patch.object(STTModelManager, "is_bundled_model", return_value=False), \
             patch.object(self.panel, "open_stt_model_manager") as mock_open_stt, \
             patch.object(self.panel, "open_llm_model_manager") as mock_open_llm, \
             patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as mock_q:

            orig_model = self.panel.config["model_size"]
            self.panel.apply_preset("masterpiece", notify=False)

            # STT 모델 관리창이 target_model_id="distil-large-v3.5"로 열렸는지 확인
            mock_open_stt.assert_called_once_with(target_model_id="distil-large-v3.5")
            mock_open_llm.assert_not_called()
            mock_q.assert_called_once()
            # 미설치 STT 모델로 변경되지 않고 기존 설정 유지되었는지 확인
            self.assertEqual(self.panel.config["model_size"], orig_model)

    def test_preset_preflight_dual_dialog_when_both_uninstalled(self):
        """프리셋 적용 시 LLM과 STT 모델이 둘 다 미설치된 경우 번역 모델 관리창부터 유도 검증"""
        with patch.object(self.panel, "_check_model_ready", return_value=False), \
             patch.object(STTModelManager, "is_model_installed", return_value=False), \
             patch.object(STTModelManager, "is_bundled_model", return_value=False), \
             patch.object(self.panel, "open_llm_model_manager") as mock_open_llm, \
             patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):

            self.panel.apply_preset("masterpiece", notify=False)
            mock_open_llm.assert_called_once_with(target_model_id="exaone7b")

    def test_stt_model_manager_matches_both_id_and_hfid(self):
        """STTModelManager.is_model_installed가 friendly ID와 HF ID 둘 다 올바르게 조회하는지 검증"""
        with patch.object(STTModelManager, "get_model_folder_path", return_value="/dummy/path"), \
             patch.object(STTModelManager, "_is_valid_model_folder", return_value=True):

            self.assertTrue(STTModelManager.is_model_installed("distil-large-v3.5"))
            self.assertTrue(STTModelManager.is_model_installed("distil-whisper/distil-large-v3.5-ct2"))

    def test_stt_uninstalled_popup_message_format_is_concise_and_uses_model_id(self):
        """STT 미설치 팝업 안내 문구가 중복 이름 없이 모델 ID로 간결하게 표시되는지 검증"""
        with patch.object(STTModelManager, "is_model_installed", return_value=False), \
             patch.object(STTModelManager, "is_bundled_model", return_value=False), \
             patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as mock_q:

            self.panel._on_stt_model_quick_selected("small.en")
            mock_q.assert_called_once()
            args, _ = mock_q.call_args
            # Title
            self.assertEqual(args[1], "📦 STT 모델 다운로드 필요")
            msg_text = args[2]
            # Should have model id 'small.en'
            self.assertIn("'small.en'", msg_text)
            # Should NOT have verbose friendly name or estimated size
            self.assertNotIn("Whisper Small (English)", msg_text)
            self.assertNotIn("예상 다운로드 크기", msg_text)
            self.assertNotIn("바로 사용할 수 없습니다", msg_text)
            self.assertIn("선택하신 'small.en' 모델이 아직 설치되지 않았습니다.\n\nSTT 모델 관리창을 열어 모델을 다운로드하시겠습니까?", msg_text)

    def test_llm_model_dialog_target_highlight_exaone7b(self):
        """로컬 마스터피스 등에서 전달되는 'exaone7b' 타겟이 EXAONE 7.8B 카드를 정확히 하이라이트(외곽선) 처리하는지 검증"""
        from src.llm_model_dialog import LLMModelDialog, COLOR_ACCENT_CYAN
        dlg = LLMModelDialog(current_backend="embedded", current_model="exaone-3.5-2.4b", target_model_id="exaone7b")
        highlighted = [i for i, c in enumerate(dlg.cards) if COLOR_ACCENT_CYAN in c.styleSheet()]
        self.assertEqual(len(highlighted), 1)
        self.assertEqual(highlighted[0], 2) # Card 2: EXAONE 7.8B
        card = dlg.cards[2]
        self.assertIn("7.8b", card.ollama_info.get("tag", "").lower())
        dlg.close()

    def test_llm_model_dialog_target_highlight_all_models(self):
        """각종 엔진 키/타겟 ID별로 적절한 LLM 모델 카드가 하이라이트되는지 검증"""
        from src.llm_model_dialog import LLMModelDialog, COLOR_ACCENT_CYAN
        cases = [
            ("translategemma", 0),
            ("gemma", 0),
            ("exaone", 1),
            ("exaone-2.4b", 1),
            ("exaone7b", 2),
            ("exaone-7b", 2),
            ("masterpiece", 2),
            ("hymt", 3),
            ("hy-mt", 3),
            ("tencent/hy-mt2:1.8b", 3),
        ]
        for target, expected_idx in cases:
            dlg = LLMModelDialog(current_backend="embedded", current_model="exaone-3.5-2.4b", target_model_id=target)
            highlighted = [i for i, c in enumerate(dlg.cards) if COLOR_ACCENT_CYAN in c.styleSheet()]
            self.assertEqual(highlighted, [expected_idx], f"Failed target: {target}")
            dlg.close()

    def test_stt_model_download_worker_and_ui_update(self):
        """STT 모델 다운로드 클릭 시 비동기 Worker 실행 및 완료 후 UI 상태(배지/버튼) 자동 갱신 검증"""
        import tempfile
        from src.stt_model_dialog import STTModelDialog
        import src.stt_model_dialog
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(STTModelManager, "is_model_installed", return_value=False):
                dlg = STTModelDialog(current_model_id="distil-small.en")
                card = next((c for c in dlg.cards if c.model_info["id"] == "distil-large-v3"), None)
                self.assertIsNotNone(card)
                self.assertFalse(card.btn_download.isHidden())

                with patch("huggingface_hub.snapshot_download", return_value=tmpdir), \
                     patch.object(STTModelManager, "heal_snapshot_symlinks") as mock_heal, \
                     patch.object(STTModelManager, "is_model_installed", return_value=True), \
                     patch.object(src.stt_model_dialog.QMessageBox, "question", return_value=src.stt_model_dialog.QMessageBox.StandardButton.No):
                    card._on_download_clicked()
                    self.assertIsNotNone(card.worker)
                    card.worker.join(timeout=3)
                    app.processEvents()
                    self.assertFalse(card.worker.is_alive())
                    mock_heal.assert_called_once()
                    self.assertFalse(card.progress_container.isVisible())
                    self.assertTrue(card.btn_download.isHidden())
                    self.assertFalse(card.btn_select.isHidden())
                dlg.close()

    def test_llm_model_download_worker_and_ui_update(self):
        """LLM 모델 다운로드 클릭 시 비동기 GGUF Worker 실행 및 완료 후 UI 상태 자동 갱신 검증"""
        import tempfile
        from src.llm_model_dialog import LLMModelDialog
        import src.llm_model_dialog
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_file = os.path.join(tmpdir, "dummy.gguf")
            with open(dummy_file, "w") as f:
                f.write("dummy")

            with patch("src.llm_model_manager.get_custom_model_dir", return_value=None), \
                 patch.object(LLMModelManager, "check_ollama_alive", return_value=(False, "")), \
                 patch.object(LLMModelManager, "is_gguf_model_installed", return_value=False):
                dlg = LLMModelDialog(current_backend="embedded", current_model="exaone-3.5-2.4b")
                card = dlg.cards[2] # EXAONE 7.8B
                self.assertFalse(card.btn_download.isHidden())

                with patch("huggingface_hub.hf_hub_download", return_value=dummy_file), \
                     patch.object(LLMModelManager, "is_gguf_model_installed", return_value=True), \
                     patch.object(src.llm_model_dialog.QMessageBox, "question", return_value=src.llm_model_dialog.QMessageBox.StandardButton.No):
                    card._on_download_clicked()
                    self.assertIsNotNone(card.worker)
                    card.worker.join(timeout=3)
                    app.processEvents()
                    self.assertFalse(card.worker.is_alive())
                    self.assertFalse(card.progress_container.isVisible())
                    self.assertTrue(card.btn_download.isHidden())
                    self.assertFalse(card.btn_select.isHidden())
                dlg.close()

    def test_llm_delete_gguf_model_single_click(self):
        """LLM GGUF 모델 삭제 시 단 1회 호출로 지정 파일과 HF 캐시 폴더가 모두 완전 삭제되는지 검증"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            gguf_dir = os.path.join(tmpdir, "GGUF")
            os.makedirs(gguf_dir, exist_ok=True)
            shared_file = os.path.join(gguf_dir, "test-model.gguf")
            with open(shared_file, "w") as f:
                f.write("model-data")

            repo_cache_dir = os.path.join(tmpdir, "huggingface", "hub", "models--test--test-model")
            snap_dir = os.path.join(repo_cache_dir, "snapshots", "hash123")
            os.makedirs(snap_dir, exist_ok=True)
            cached_file = os.path.join(snap_dir, "test-model.gguf")
            with open(cached_file, "w") as f:
                f.write("model-data")

            model_info = {
                "id": "test-model",
                "repo_id": "test/test-model",
                "filename": "test-model.gguf",
            }

            with patch("src.llm_model_manager.get_custom_model_dir", return_value=tmpdir):
                self.assertTrue(LLMModelManager.is_gguf_model_installed(model_info))

                # 1회 삭제 호출
                res = LLMModelManager.delete_gguf_model(model_info)
                self.assertTrue(res)

                # 파일 및 허브 디렉터리가 모두 삭제되었는지 확인
                self.assertFalse(os.path.exists(shared_file))
                self.assertFalse(os.path.exists(repo_cache_dir))
                # 2번째 클릭 없이 단 1회만에 즉시 미설치 상태로 전환되는지 확인
                self.assertFalse(LLMModelManager.is_gguf_model_installed(model_info))

    def test_stt_delete_model_across_multiple_hub_dirs(self):
        """STT 모델 삭제 시 여러 허브 디렉터리에 분산된 캐시가 1회 호출로 모두 삭제되는지 검증"""
        import tempfile
        with tempfile.TemporaryDirectory() as hub1, tempfile.TemporaryDirectory() as hub2:
            model_info = {"id": "distil-large-v3", "hf_id": "Systran/faster-distil-whisper-large-v3"}
            folder_name = "models--" + model_info["hf_id"].replace("/", "--")

            m_dir1 = os.path.join(hub1, folder_name, "snapshots", "rev1")
            m_dir2 = os.path.join(hub2, folder_name, "snapshots", "rev2")
            os.makedirs(m_dir1, exist_ok=True)
            os.makedirs(m_dir2, exist_ok=True)
            with open(os.path.join(m_dir1, "model.bin"), "wb") as f:
                f.write(b"0" * (11 * 1024 * 1024))
            with open(os.path.join(m_dir2, "model.bin"), "wb") as f:
                f.write(b"0" * (11 * 1024 * 1024))

            with patch.object(STTModelManager, "get_search_hub_dirs", return_value=[hub1, hub2]), \
                 patch.object(STTModelManager, "is_bundled_model", return_value=False):
                self.assertTrue(STTModelManager.is_model_installed("distil-large-v3"))

                # 1회 삭제 호출
                res = STTModelManager.delete_model("distil-large-v3")
                self.assertTrue(res)

                # 양쪽 허브 디렉터리 모두 깔끔히 삭제되었는지 확인
                self.assertFalse(os.path.exists(os.path.join(hub1, folder_name)))
                self.assertFalse(os.path.exists(os.path.join(hub2, folder_name)))
                self.assertFalse(STTModelManager.is_model_installed("distil-large-v3"))

    def test_download_worker_initial_and_monotonic_progress(self):
        """다운로드 시작 시 진행률이 0%로 초기화되고, 절대 뒤로 감소(역행)하지 않는 단조 증가성 검증"""
        from src.llm_model_manager import GGUFDownloadWorker
        from src.stt_model_manager import STTDownloadWorker

        # 1. GGUFDownloadWorker 초기 progress_signal이 0인지 검증
        emitted_gguf = []
        gguf_worker = GGUFDownloadWorker({
            "id": "test-gguf",
            "repo_id": "test/repo",
            "filename": "model.gguf"
        })
        gguf_worker.progress_signal.connect(lambda mid, pct, msg: emitted_gguf.append(pct))
        with patch("huggingface_hub.hf_hub_download", side_effect=Exception("stop")):
            try:
                gguf_worker.run()
            except Exception:
                pass
        self.assertTrue(len(emitted_gguf) > 0)
        self.assertEqual(emitted_gguf[0], 0, "GGUF 최초 연결 시 진행률은 0%여야 합니다.")

        # 2. STTDownloadWorker 초기 progress_signal이 0인지 검증
        emitted_stt = []
        stt_worker = STTDownloadWorker({
            "id": "test-stt",
            "hf_id": "test/stt-repo",
            "size_mb": 100
        })
        stt_worker.progress_signal.connect(lambda mid, pct, msg: emitted_stt.append(pct))
        with patch("huggingface_hub.snapshot_download", side_effect=Exception("stop")):
            try:
                stt_worker.run()
            except Exception:
                pass
        self.assertTrue(len(emitted_stt) > 0)
        self.assertEqual(emitted_stt[0], 0, "STT 최초 다운로드 준비 시 진행률은 0%여야 합니다.")

    def test_stt_download_worker_streaming_progress_with_tqdm(self):
        """STT 모델 다운로드 시 STTProgressTqdm을 통해 실시간 진행률과 속도가 정상 전달되는지 검증"""
        from src.stt_model_manager import STTDownloadWorker

        emitted_signals = []
        finished_results = []
        worker = STTDownloadWorker({
            "id": "tiny",
            "hf_id": "Systran/faster-whisper-tiny",
            "size_mb": 75
        })
        worker.progress_signal.connect(lambda mid, pct, msg: emitted_signals.append((pct, msg)))
        worker.finished_signal.connect(lambda mid, ok, msg: finished_results.append((ok, msg)))

        def fake_snapshot_download(repo_id, cache_dir, allow_patterns, tqdm_class):
            bar = tqdm_class(desc="Downloading bytes", unit="B", total=75 * 1024 * 1024)
            bar.update(25 * 1024 * 1024)
            bar.update(25 * 1024 * 1024)
            bar.close()
            return "/dummy/snapshot/path"

        with patch("huggingface_hub.snapshot_download", side_effect=fake_snapshot_download), \
             patch.object(STTModelManager, "heal_snapshot_symlinks"):
            worker.run()

        # 0% 준비 -> 스트리밍 진행률 -> 최종 100% 완료
        self.assertTrue(len(emitted_signals) >= 3)
        self.assertEqual(emitted_signals[0][0], 0)
        self.assertTrue(any(sig[0] > 0 and "가중치 다운로드 중" in sig[1] for sig in emitted_signals))
        self.assertEqual(emitted_signals[-1][0], 100)
        self.assertTrue(finished_results[0][0])

    def test_stt_dialog_reconnects_to_active_download_worker(self):
        """STT 모델 다운로드 도중 창을 닫았다가 다시 열었을 때 진행 상태바가 유지/재연결되는지 검증"""
        from src.stt_model_dialog import STTModelDialog
        from src.stt_model_manager import STTDownloadSignals

        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = True
        mock_worker.isRunning.return_value = True
        mock_signals = STTDownloadSignals()
        mock_worker.progress_signal = mock_signals.progress_signal
        mock_worker.finished_signal = mock_signals.finished_signal

        m_id = "distil-large-v3"
        STTModelManager.register_worker(m_id, mock_worker)
        STTModelManager.set_last_progress(m_id, 45, "가중치 다운로드 중... 45%")

        try:
            with patch.object(STTModelManager, "is_model_installed", return_value=False):
                dlg = STTModelDialog(current_model_id="distil-small.en")
                card = next((c for c in dlg.cards if c.model_info["id"] == m_id), None)
                self.assertIsNotNone(card)

                # 창을 다시 열었을 때 프로그레스 바가 45%로 유지/노출되는지 확인
                self.assertFalse(card.progress_container.isHidden())
                self.assertEqual(card.progress_bar.value(), 45)
                self.assertEqual(card.lbl_progress_status.text(), "가중치 다운로드 중... 45%")
                self.assertTrue(card.btn_download.isHidden())
                self.assertFalse(card.btn_cancel.isHidden())
                self.assertTrue(card.btn_cancel.isEnabled())

                # 백그라운드 워커가 새로운 진행률(70%)을 방출했을 때 실시간 UI 동기화 검증
                mock_worker.progress_signal.emit(m_id, 70, "가중치 다운로드 중... 70%")
                app.processEvents()
                self.assertEqual(card.progress_bar.value(), 70)
                self.assertEqual(card.lbl_progress_status.text(), "가중치 다운로드 중... 70%")

                # 다운로드 취소 버튼 클릭 동작 검증
                card.btn_cancel.click()
                mock_worker.cancel.assert_called_once()
                self.assertFalse(card.btn_cancel.isEnabled())
                self.assertEqual(card.btn_cancel.text(), "취소 중...")

                dlg.close()
        finally:
            STTModelManager.unregister_worker(m_id)

    def test_llm_dialog_reconnects_to_active_download_worker(self):
        """LLM GGUF 모델 다운로드 도중 창을 닫았다가 다시 열었을 때 진행 상태바가 유지/재연결되는지 검증"""
        from src.llm_model_dialog import LLMModelDialog
        from src.llm_model_manager import GGUFDownloadSignals

        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = True
        mock_worker.isRunning.return_value = True
        mock_signals = GGUFDownloadSignals()
        mock_worker.progress_signal = mock_signals.progress_signal
        mock_worker.finished_signal = mock_signals.finished_signal

        m_id = "exaone-3.5-7.8b"
        LLMModelManager.register_gguf_worker(m_id, mock_worker)
        LLMModelManager.set_last_gguf_progress(m_id, 55, "다운로드 중... 55%")

        try:
            with patch.object(LLMModelManager, "check_ollama_alive", return_value=(False, "")), \
                 patch.object(LLMModelManager, "is_gguf_model_installed", return_value=False):
                dlg = LLMModelDialog(current_backend="embedded", current_model="exaone-3.5-2.4b")
                card = dlg.cards[2] # EXAONE 7.8B
                self.assertEqual(card.gguf_info["id"], m_id)

                # 창을 다시 열었을 때 프로그레스 바가 55%로 유지/노출되는지 확인
                self.assertFalse(card.progress_container.isHidden())
                self.assertEqual(card.progress_bar.value(), 55)
                self.assertEqual(card.lbl_progress_status.text(), "다운로드 중... 55%")
                self.assertTrue(card.btn_download.isHidden())
                self.assertFalse(card.btn_cancel.isHidden())
                self.assertTrue(card.btn_cancel.isEnabled())

                # 백그라운드 워커가 새로운 진행률(80%)을 방출했을 때 실시간 UI 동기화 검증
                mock_worker.progress_signal.emit(m_id, 80, "다운로드 중... 80%")
                app.processEvents()
                self.assertEqual(card.progress_bar.value(), 80)
                self.assertEqual(card.lbl_progress_status.text(), "다운로드 중... 80%")

                # 다운로드 취소 버튼 클릭 동작 검증
                card.btn_cancel.click()
                mock_worker.cancel.assert_called_once()
                self.assertFalse(card.btn_cancel.isEnabled())
                self.assertEqual(card.btn_cancel.text(), "취소 중...")

                dlg.close()
        finally:
            LLMModelManager.unregister_gguf_worker(m_id)

    def test_cuda_pack_dialog_reconnects_to_active_download_worker(self):
        """CUDA 가속 팩 다운로드 도중 창을 닫았다가 다시 열었을 때 CUDA 진행 상태바가 유지/재연결되는지 검증"""
        from src.llm_model_dialog import LLMModelDialog
        from src.llm_model_manager import CUDAPackDownloadSignals

        mock_worker = MagicMock()
        mock_worker.is_alive.return_value = True
        mock_worker.isRunning.return_value = True
        mock_signals = CUDAPackDownloadSignals()
        mock_worker.progress_signal = mock_signals.progress_signal
        mock_worker.finished_signal = mock_signals.finished_signal

        LLMModelManager.register_cuda_worker(mock_worker)
        LLMModelManager.set_last_cuda_progress(65, "CUDA 가속 팩 다운로드 중 (300MB/460MB, 65%)")

        try:
            with patch.object(LLMModelManager, "check_ollama_alive", return_value=(False, "")), \
                 patch.object(LLMModelManager, "is_cuda_binary_available", return_value=False), \
                 patch.object(LLMModelManager, "is_nvidia_gpu_present", return_value=True):
                dlg = LLMModelDialog(current_backend="embedded", current_model="exaone-3.5-2.4b")

                # CUDA 프로그레스 바가 65%로 유지/노출되는지 확인
                self.assertFalse(dlg.cuda_progress_container.isHidden())
                self.assertEqual(dlg.cuda_progress_bar.value(), 65)
                self.assertEqual(dlg.lbl_cuda_progress.text(), "CUDA 가속 팩 다운로드 중 (300MB/460MB, 65%)")
                self.assertFalse(dlg.btn_cuda_action.isEnabled())

                # 백그라운드 워커가 85% 방출 시 실시간 갱신 확인
                mock_worker.progress_signal.emit(85, "CUDA 가속 팩 다운로드 중 (390MB/460MB, 85%)")
                app.processEvents()
                self.assertEqual(dlg.cuda_progress_bar.value(), 85)

                dlg.close()
        finally:
            LLMModelManager.unregister_cuda_worker()

    def test_set_engine_by_key_exaone7b_installed_no_popup(self):
        """EXAONE 7.8B (exaone7b) 모델이 이미 설치되어 있을 때 안내 팝업 없이 즉시 엔진이 전환되는지 검증"""
        with patch.object(LLMModelManager, "is_cuda_binary_available", return_value=True), \
             patch.object(LLMModelManager, "is_gguf_model_installed", return_value=True), \
             patch.object(QMessageBox, "question") as mock_q:
            self.panel.set_engine_by_key("exaone7b")
            mock_q.assert_not_called()
            self.assertEqual(self.panel.config["translation_engine"], "exaone7b")
            self.assertEqual(self.panel.config["selected_llm_model"], "exaone-3.5-7.8b")

    def test_gguf_download_cancel_aborts_xet_and_purges_model(self):
        """GGUF 다운로드 취소 시 xet 세션을 즉각 중단하고 불완전 파일을 정리하는지 검증"""
        from src.llm_model_manager import GGUFDownloadWorker
        worker = GGUFDownloadWorker({
            "id": "hy-mt",
            "repo_id": "Tencent/Hy-MT2-1.8B-GGUF",
            "filename": "Hy-MT2-1.8B-Q4_K_M.gguf"
        })
        finished = []
        worker.finished_signal.connect(lambda mid, ok, msg: finished.append((mid, ok, msg)))

        with patch("huggingface_hub.utils._xet.abort_xet_session") as mock_abort, \
             patch.object(LLMModelManager, "delete_gguf_model") as mock_del, \
             patch("huggingface_hub.hf_hub_download", side_effect=RuntimeError("Operation cancelled: Task cancelled")):
            worker.cancel()
            mock_abort.assert_called_once()
            worker.run()

        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0][1])
        self.assertIn("취소", finished[0][2])
        mock_del.assert_called()

    def test_stt_download_cancel_aborts_xet_and_purges_model(self):
        """STT 다운로드 취소 시 xet 세션을 즉각 중단하고 모델을 정리하는지 검증"""
        from src.stt_model_manager import STTDownloadWorker
        worker = STTDownloadWorker({
            "id": "distil-large-v3",
            "hf_id": "Systran/faster-distil-whisper-large-v3",
            "size_mb": 1500
        })
        finished = []
        worker.finished_signal.connect(lambda mid, ok, msg: finished.append((mid, ok, msg)))

        with patch("huggingface_hub.utils._xet.abort_xet_session") as mock_abort, \
             patch.object(STTModelManager, "delete_model") as mock_del, \
             patch("huggingface_hub.snapshot_download", side_effect=RuntimeError("Operation cancelled: Task cancelled")):
            worker.cancel()
            mock_abort.assert_called_once()
            worker.run()

        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0][1])
        self.assertIn("취소", finished[0][2])
        mock_del.assert_called()


if __name__ == "__main__":
    unittest.main()


