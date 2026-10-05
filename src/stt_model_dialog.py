import os
import shutil
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QScrollArea, QWidget, QMessageBox, QFrame,
    QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont
from PyQt6 import sip

from .ui_theme import (
    COLOR_BG_DARK, COLOR_CARD_BG, COLOR_CARD_INNER, COLOR_BORDER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_ACCENT_PURPLE,
    COLOR_ACCENT_CYAN, COLOR_ACCENT_PINK, CardWidget
)
from src.i18n import ask, is_cancel_message, tell, tr
from .stt_model_manager import STTModelManager, STTDownloadWorker, AVAILABLE_STT_MODELS, get_hf_hub_cache_dir


class STTModelCard(QFrame):
    """STT 모델 개별 관리 행 카드"""
    model_selected_signal = pyqtSignal(str)
    model_status_changed_signal = pyqtSignal()

    def __init__(self, model_info: dict, current_active_id: str, device: str = "cpu", parent=None):
        super().__init__(parent)
        self.model_info = model_info
        self.current_active_id = current_active_id
        self.device = str(device).lower()
        self.worker = None

        self.setObjectName("STTModelCard")
        self.setStyleSheet(f"""
            #STTModelCard {{
                background-color: {COLOR_CARD_INNER};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
            }}
            QLabel {{
                background-color: transparent;
                border: none;
            }}
        """)

        self._init_ui()
        self.refresh_state()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 8, 14, 8)
        main_layout.setSpacing(6)

        # 상단 행: 모델 이름, 배지, 용량, 액션 버튼
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # 툴팁으로 상세 사양 제공 (마우스 호버 시 확인 가능)
        self.setToolTip(f"{self.model_info['desc']} · 다운로드: 약 {self.model_info['size_mb']}MB · 권장 VRAM: {self.model_info['vram_mb']}MB")

        # 모델 정보 영역 (모델 이름(ID) + 설치 상태만 심플하게 표시)
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.lbl_name = QLabel(self.model_info["id"])
        self.lbl_name.setStyleSheet("font-size: 13px; font-weight: bold; color: #FFFFFF;")

        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: bold;")

        title_row.addWidget(self.lbl_name)
        title_row.addWidget(self.lbl_status)
        title_row.addStretch(1)

        top_row.addLayout(title_row, stretch=1)

        # 버튼 영역
        btn_box = QHBoxLayout()
        btn_box.setSpacing(6)

        self.btn_select = QPushButton(tr("btn_apply"))
        self.btn_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ACCENT_PURPLE};
                color: #FFFFFF;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 12px;
                border-radius: 5px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #7C3AED;
            }}
        """)
        self.btn_select.clicked.connect(self._on_select_clicked)

        self.btn_download = QPushButton("⬇️ " + tr("btn_download"))
        self.btn_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download.setStyleSheet("""
            QPushButton {{
                background-color: #10B981;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 12px;
                border-radius: 5px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #059669;
            }}
        """)
        self.btn_download.clicked.connect(self._on_download_clicked)

        self.btn_delete = QPushButton("🗑️ " + tr("btn_delete"))
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setStyleSheet("""
            QPushButton {{
                background-color: rgba(239, 68, 68, 0.15);
                color: #EF4444;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 10px;
                border-radius: 5px;
                border: 1px solid rgba(239, 68, 68, 0.4);
            }}
            QPushButton:hover {{
                background-color: rgba(239, 68, 68, 0.3);
            }}
        """)
        self.btn_delete.clicked.connect(self._on_delete_clicked)

        self.btn_cancel = QPushButton(tr("btn_cancel_download"))
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: rgba(239, 68, 68, 0.15);
                color: #EF4444;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 12px;
                border-radius: 5px;
                border: 1px solid rgba(239, 68, 68, 0.4);
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.3);
            }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        self.btn_cancel.setVisible(False)

        btn_box.addWidget(self.btn_select)
        btn_box.addWidget(self.btn_download)
        btn_box.addWidget(self.btn_cancel)
        btn_box.addWidget(self.btn_delete)
        top_row.addLayout(btn_box)

        main_layout.addLayout(top_row)

        # 다운로드 진행 바 (평소 숨김)
        self.progress_container = QWidget()
        p_layout = QVBoxLayout(self.progress_container)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(3)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #0B1120;
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                height: 14px;
                text-align: center;
                font-size: 10px;
                color: #ECEFF1;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_ACCENT_PURPLE};
                border-radius: 3px;
            }}
        """)
        self.lbl_progress_status = QLabel("")
        self.lbl_progress_status.setStyleSheet("font-size: 10px; color: #94A3B8;")
        p_layout.addWidget(self.progress_bar)
        p_layout.addWidget(self.lbl_progress_status)
        self.progress_container.setVisible(False)
        main_layout.addWidget(self.progress_container)

    def refresh_state(self, active_id: str = None):
        if sip.isdeleted(self) or not hasattr(self, 'lbl_status') or sip.isdeleted(self.lbl_status):
            return
        if active_id:
            self.current_active_id = active_id
        is_installed = STTModelManager.is_model_installed(self.model_info["id"])
        is_bundled = STTModelManager.is_bundled_model(self.model_info["id"])
        is_current = (self.model_info["id"] == self.current_active_id)

        if is_installed:
            size_mb = STTModelManager.get_model_disk_size_mb(self.model_info["id"])
            if is_current:
                suffix = " (기본 내장)" if is_bundled else ""
                self.lbl_status.setText(f"● 현재 사용 중{suffix}")
                self.lbl_status.setStyleSheet("background: transparent; border: none; padding: 0px; color: #818CF8; font-weight: bold; font-size: 11px;")
            else:
                if is_bundled:
                    self.lbl_status.setText(f"★ 기본 내장 ({size_mb} MB)")
                    self.lbl_status.setStyleSheet("background: transparent; border: none; padding: 0px; color: #F59E0B; font-weight: bold; font-size: 11px;")
                else:
                    self.lbl_status.setText(f"✓ 설치됨 ({size_mb} MB)")
                    self.lbl_status.setStyleSheet("background: transparent; border: none; padding: 0px; color: #34D399; font-weight: bold; font-size: 11px;")

            try:
                from src.stt_engine import is_cuda_installed
                has_cuda = is_cuda_installed()
            except Exception:
                has_cuda = False
            can_select = (self.device != "cpu") or self.model_info.get("cpu_usable", False) or has_cuda
            self.btn_select.setEnabled(can_select)
            self.btn_select.setText(tr("btn_apply"))
            if self.device == "cpu" and not self.model_info.get("cpu_usable", False) and has_cuda:
                self.btn_select.setToolTip("이 모델을 선택하면 CUDA GPU 가속으로 자동 전환되어 최적 속도로 구동됩니다.")
            else:
                self.btn_select.setToolTip("이 모델을 현재 음성 인식 모델로 적용합니다.")
            self.btn_select.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_ACCENT_PURPLE};
                    color: #FFFFFF;
                    font-weight: bold;
                    font-size: 11px;
                    padding: 6px 12px;
                    border-radius: 5px;
                    border: none;
                }}
                QPushButton:hover {{
                    background-color: #7C3AED;
                }}
            """)
            self.btn_select.setVisible(not is_current and can_select)
            self.btn_download.setVisible(False)
            self.btn_cancel.setVisible(False)
            self.btn_delete.setVisible(not is_current and not is_bundled) # 기본 내장 모델 및 현재 모델은 삭제 방지
        else:
            active_worker = STTModelManager.get_active_worker(self.model_info["id"])
            if active_worker:
                self.worker = active_worker
                self.lbl_status.setText(tr("downloading"))
                self.lbl_status.setStyleSheet("background: transparent; border: none; padding: 0px; color: #F59E0B; font-weight: bold; font-size: 11px;")
                self.btn_select.setVisible(False)
                self.btn_download.setVisible(False)
                self.btn_cancel.setVisible(True)
                self.btn_cancel.setEnabled(True)
                self.btn_cancel.setText(tr("btn_cancel_download"))
                self.btn_delete.setVisible(False)

                last_pct, last_msg = STTModelManager.get_last_progress(self.model_info["id"])
                self.progress_bar.setValue(last_pct)
                self.lbl_progress_status.setText(last_msg)
                self.progress_container.setVisible(True)

                try:
                    self.worker.progress_signal.disconnect(self._on_download_progress)
                except Exception:
                    pass
                try:
                    self.worker.finished_signal.disconnect(self._on_download_finished)
                except Exception:
                    pass
                self.worker.progress_signal.connect(self._on_download_progress)
                self.worker.finished_signal.connect(self._on_download_finished)
            else:
                self.lbl_status.setText(tr("not_installed"))
                self.lbl_status.setStyleSheet("background: transparent; border: none; padding: 0px; color: #94A3B8; font-weight: bold; font-size: 11px;")
                self.btn_select.setVisible(False)
                self.btn_download.setVisible(True)
                self.btn_download.setEnabled(True)
                self.btn_download.setText("⬇️ " + tr("btn_download"))
                self.btn_cancel.setVisible(False)
                self.btn_delete.setVisible(False)
                self.progress_container.setVisible(False)

    def _on_select_clicked(self):
        try:
            from src.stt_engine import is_cuda_installed
            has_cuda = is_cuda_installed()
        except Exception:
            has_cuda = False

        if self.device == "cpu" and not self.model_info.get("cpu_usable", False) and not has_cuda:
            tell(self, "msg_cannot_select_title", "msg_cannot_select_cpu", kind="warn", name=self.model_info["id"])
            return
        self.model_selected_signal.emit(self.model_info["id"])

    def _on_download_clicked(self):
        worker = STTModelManager.get_active_worker(self.model_info["id"])
        if worker:
            self.worker = worker
        else:
            self.worker = STTDownloadWorker(self.model_info)
            self.worker.start()

        self.lbl_status.setText(tr("downloading"))
        self.lbl_status.setStyleSheet("background: transparent; border: none; padding: 0px; color: #F59E0B; font-weight: bold; font-size: 11px;")
        self.btn_select.setVisible(False)
        self.btn_download.setVisible(False)
        self.btn_cancel.setVisible(True)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText(tr("btn_cancel_download"))
        self.btn_delete.setVisible(False)
        self.progress_container.setVisible(True)
        last_pct, last_msg = STTModelManager.get_last_progress(self.model_info["id"])
        self.progress_bar.setValue(last_pct)
        self.lbl_progress_status.setText(last_msg if last_pct > 0 else "다운로드를 시작합니다...")

        try:
            self.worker.progress_signal.disconnect(self._on_download_progress)
        except Exception:
            pass
        try:
            self.worker.finished_signal.disconnect(self._on_download_finished)
        except Exception:
            pass
        self.worker.progress_signal.connect(self._on_download_progress)
        self.worker.finished_signal.connect(self._on_download_finished)

    def _on_cancel_clicked(self):
        worker = STTModelManager.get_active_worker(self.model_info["id"])
        target_worker = worker or self.worker
        if target_worker:
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText(tr("canceling"))
            self.lbl_progress_status.setText(tr("cancel_requested"))
            target_worker.cancel()

    def _on_download_progress(self, model_id, percent, msg):
        if sip.isdeleted(self) or not hasattr(self, 'progress_bar') or sip.isdeleted(self.progress_bar):
            return
        if model_id == self.model_info["id"]:
            self.progress_bar.setValue(percent)
            self.lbl_progress_status.setText(msg)

    def _on_download_finished(self, model_id, success, msg):
        if sip.isdeleted(self) or not hasattr(self, 'progress_container') or sip.isdeleted(self.progress_container):
            return
        if model_id == self.model_info["id"]:
            self.progress_container.setVisible(False)
            self.btn_cancel.setVisible(False)
            self.btn_cancel.setEnabled(True)
            self.btn_cancel.setText(tr("btn_cancel_download"))
            self.btn_download.setEnabled(True)
            self.btn_download.setText("⬇️ " + tr("btn_download"))
            if success:
                self.refresh_state()
                if not sip.isdeleted(self):
                    self.model_status_changed_signal.emit()
                    ret = ask(self, "msg_download_switched_title", "msg_use_now", name=self.model_info["id"])
                    if ret == QMessageBox.StandardButton.Yes and not sip.isdeleted(self):
                        self._on_select_clicked()
            else:
                self.refresh_state()
                if not sip.isdeleted(self):
                    self.model_status_changed_signal.emit()
                    if not is_cancel_message(msg):
                        tell(self, "msg_download_switched_title", "msg_download_fail", kind="warn", error=msg)

    def _on_delete_clicked(self):
        if STTModelManager.is_bundled_model(self.model_info["id"]):
            tell(self, "msg_cannot_delete_title", "msg_cannot_delete")
            return

        ret = ask(self, "msg_delete_title", "msg_delete_body", name=self.model_info["id"])
        if ret == QMessageBox.StandardButton.Yes:
            ok = STTModelManager.delete_model(self.model_info["id"])
            if ok:
                tell(self, "msg_saved_title", "msg_deleted", name=self.model_info["id"])
                self.refresh_state()
                self.model_status_changed_signal.emit()
            else:
                tell(self, "msg_save_failed_title", "msg_delete_fail", kind="warn")


class STTModelDialog(QDialog):
    """STT 모델 탐색 및 다운로드/삭제 관리 다이얼로그"""
    model_chosen = pyqtSignal(str)

    def __init__(self, current_model_id: str, device: str = "cpu", target_model_id: str = None, parent=None):
        super().__init__(parent)
        self.current_model_id = current_model_id
        self.device = str(device).lower()
        self.target_model_id = target_model_id
        self.cards = []

        self.setWindowTitle(tr("dlg_stt_window"))
        self.resize(780, 640)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLOR_BG_DARK};
                color: {COLOR_TEXT_PRIMARY};
            }}
        """)

        self._init_ui()
        self._refresh_storage_info()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # 헤더 카드
        header_card = CardWidget()
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(16, 12, 16, 12)
        h_layout.setSpacing(4)

        title = QLabel("🎙️ " + tr("dlg_stt_heading"))
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #ECEFF1;")
        h_layout.addWidget(title)
        layout.addWidget(header_card)

        # 공용 저장소 및 환경변수 연동 정보 카드
        self.storage_card = CardWidget()
        s_layout = QVBoxLayout(self.storage_card)
        s_layout.setContentsMargins(16, 12, 16, 12)
        s_layout.setSpacing(8)

        s_top = QHBoxLayout()
        s_title = QLabel("📁 " + tr("dlg_stt_store"))
        s_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        s_top.addWidget(s_title)
        s_top.addStretch(1)

        btn_open = QPushButton("📂 " + tr("dlg_open_stt"))
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.setStyleSheet(f"""
            QPushButton {{
                background-color: #1E293B;
                color: #ECEFF1;
                border: 1px solid {COLOR_BORDER};
                border-radius: 5px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #334155;
            }}
        """)
        btn_open.clicked.connect(self._on_open_folder_clicked)
        s_top.addWidget(btn_open)
        s_layout.addLayout(s_top)

        grid_frame = QFrame()
        grid_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #0B1120;
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        grid = QGridLayout(grid_frame)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)

        # 1행: STT 저장 위치 & 디스크 여유 공간
        grid.addWidget(QLabel("📍 " + tr("dlg_stt_path")), 0, 0)
        self.lbl_stt_path = QLabel("-")
        self.lbl_stt_path.setStyleSheet("font-weight: bold; color: #38BDF8; font-size: 11px;")
        grid.addWidget(self.lbl_stt_path, 0, 1)

        grid.addWidget(QLabel("💾 " + tr("dlg_free_space")), 0, 2)
        self.lbl_stt_free = QLabel("-")
        self.lbl_stt_free.setStyleSheet("font-weight: bold; color: #34D399; font-size: 11px;")
        grid.addWidget(self.lbl_stt_free, 0, 3)

        # 2행: C: 캐시 정션 상태
        grid.addWidget(QLabel("🔗 " + tr("dlg_junction")), 1, 0)
        self.lbl_stt_junction = QLabel("-")
        self.lbl_stt_junction.setStyleSheet("color: #A78BFA; font-size: 11px;")
        grid.addWidget(self.lbl_stt_junction, 1, 1, 1, 3)

        s_layout.addWidget(grid_frame)
        layout.addWidget(self.storage_card)

        # 모델 스크롤 영역
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 4, 0)
        c_layout.setSpacing(8)

        def make_section_header(title_text: str) -> QFrame:
            f = QFrame()
            f.setStyleSheet("QFrame { background: transparent; border: none; padding-top: 8px; padding-bottom: 2px; }")
            ly = QVBoxLayout(f)
            ly.setContentsMargins(4, 2, 4, 2)
            lbl1 = QLabel(title_text)
            lbl1.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLOR_ACCENT_CYAN};")
            ly.addWidget(lbl1)
            return f

        whisper_models = [m for m in AVAILABLE_STT_MODELS if m.get("category") == "whisper"]
        distil_models = [m for m in AVAILABLE_STT_MODELS if m.get("category") == "distil"]

        # 1. OpenAI Whisper 공식 라인업
        c_layout.addWidget(make_section_header("🏷️ OpenAI Whisper 공식 라인업"))
        for m in whisper_models:
            card = STTModelCard(m, self.current_model_id, device=self.device)
            card.model_selected_signal.connect(self._on_model_selected)
            card.model_status_changed_signal.connect(self._on_status_changed)
            c_layout.addWidget(card)
            self.cards.append(card)

        # 2. 증류(Distilled) Whisper 모델 라인업
        c_layout.addWidget(make_section_header("⚡ 증류(Distilled) Whisper 모델 라인업"))
        for m in distil_models:
            card = STTModelCard(m, self.current_model_id, device=self.device)
            card.model_selected_signal.connect(self._on_model_selected)
            card.model_status_changed_signal.connect(self._on_status_changed)
            c_layout.addWidget(card)
            self.cards.append(card)

        c_layout.addStretch(1)
        self.scroll.setWidget(container)
        layout.addWidget(self.scroll, stretch=1)

        # 타겟 모델 지정 시 해당 카드로 스크롤 이동 및 테두리 하이라이트
        if self.target_model_id:
            for card in self.cards:
                if card.model_info.get("id") == self.target_model_id:
                    QTimer.singleShot(150, lambda c=card: self.scroll.ensureWidgetVisible(c))
                    card.setStyleSheet(f"""
                        #STTModelCard {{
                            background-color: {COLOR_CARD_INNER};
                            border: 2px solid {COLOR_ACCENT_CYAN};
                            border-radius: 8px;
                        }}
                        QLabel {{
                            background-color: transparent;
                            border: none;
                        }}
                    """)
                    break

        # 하단 닫기 바
        bot_bar = QHBoxLayout()
        self.lbl_summary = QLabel()
        self.lbl_summary.setStyleSheet(f"font-size: 11.5px; color: {COLOR_ACCENT_CYAN}; font-weight: bold;")
        self._update_summary()
        bot_bar.addWidget(self.lbl_summary)
        bot_bar.addStretch(1)

        btn_close = QPushButton(tr("dlg_close"))
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {{
                background-color: #1E293B;
                color: #FFFFFF;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #334155;
            }}
        """)
        btn_close.clicked.connect(self.accept)
        bot_bar.addWidget(btn_close)

        layout.addLayout(bot_bar)

    def _refresh_storage_info(self):
        """STT 저장 폴더, 디스크 여유 공간, 정션 상태 갱신"""
        cache_dir = get_hf_hub_cache_dir()
        self.lbl_stt_path.setText(cache_dir)
        try:
            total, used, free = shutil.disk_usage(cache_dir)
            free_gb = free / (1024 ** 3)
            total_gb = total / (1024 ** 3)
            col = "#F59E0B" if free_gb < 20 else "#34D399"
            self.lbl_stt_free.setText(f"여유 {free_gb:.1f} GB / 전체 {total_gb:.1f} GB")
            self.lbl_stt_free.setStyleSheet(f"font-weight: bold; color: {col}; font-size: 11px;")
        except Exception:
            self.lbl_stt_free.setText(tr("unknown_space"))

        default_cache = os.path.expanduser("~/.cache/huggingface")
        try:
            target = os.readlink(default_cache)
            target_clean = target.replace("\\\\?\\", "")
            self.lbl_stt_junction.setText(f"✓ C: 캐시 정션 연동 활성 (-> {target_clean})")
            self.lbl_stt_junction.setStyleSheet("color: #34D399; font-weight: bold; font-size: 11px;")
        except OSError:
            self.lbl_stt_junction.setText("C: 기본 로컬 디렉터리 (심볼릭 미연결)")
            self.lbl_stt_junction.setStyleSheet("color: #94A3B8; font-size: 11px;")

    def _on_open_folder_clicked(self):
        """STT 모델 저장 폴더를 파일 탐색기로 열기"""
        cache_dir = get_hf_hub_cache_dir()
        if os.path.exists(cache_dir):
            try:
                os.startfile(cache_dir)
            except Exception as e:
                tell(self, "msg_explorer_fail_title", "msg_explorer_fail", kind="warn", error=e)
        else:
            tell(self, "msg_folder_missing_title", "msg_folder_missing", kind="warn", path=cache_dir)

    def _update_summary(self):
        installed_count = 0
        total_mb = 0.0
        for m in AVAILABLE_STT_MODELS:
            if STTModelManager.is_model_installed(m["id"]):
                installed_count += 1
                total_mb += STTModelManager.get_model_disk_size_mb(m["id"])
        self.lbl_summary.setText(f"설치된 모델: {installed_count}개 / 전체 점유 디스크: {total_mb:,.1f} MB")

    def _on_model_selected(self, model_id: str):
        self.current_model_id = model_id
        for c in self.cards:
            c.refresh_state(model_id)
        self.model_chosen.emit(model_id)
        tell(self, "msg_stt_applied_title", "msg_stt_applied", name=model_id)
        self.accept()

    def _on_status_changed(self):
        self._update_summary()
        self._refresh_storage_info()
        self._update_summary()
