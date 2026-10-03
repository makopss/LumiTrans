import os
import shutil
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QScrollArea, QWidget, QMessageBox, QFrame,
    QFileDialog, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6 import sip

from .ui_theme import (
    COLOR_BG_DARK, COLOR_CARD_BG, COLOR_CARD_INNER, COLOR_BORDER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_ACCENT_PURPLE,
    COLOR_ACCENT_CYAN, COLOR_ACCENT_PINK, COLOR_ACCENT_MINT, CardWidget
)
from .llm_model_manager import (
    LLMModelManager, OllamaPullWorker, GGUFDownloadWorker, CUDAPackDownloadWorker,
    RECOMMENDED_OLLAMA_MODELS, RECOMMENDED_GGUF_MODELS,
    get_custom_model_dir
)


class UnifiedLLMModelCard(QFrame):
    """스마트 단일화 LLM 모델 관리 카드 (Ollama/내장 자동 처리)"""
    model_selected_signal = pyqtSignal(str, str) # backend, model_id
    model_status_changed_signal = pyqtSignal()

    def __init__(self, ollama_info: dict, gguf_info: dict, current_active: str, is_alive: bool = None, installed_models: list = None, parent=None):
        super().__init__(parent)
        self.ollama_info = ollama_info
        self.gguf_info = gguf_info
        self.current_active = current_active
        self.is_alive = is_alive
        self.installed_models = installed_models
        self.worker = None

        self.setObjectName("UnifiedLLMModelCard")
        self.setStyleSheet(f"""
            #UnifiedLLMModelCard {{
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
        self.refresh_state(is_alive=is_alive, installed_models=installed_models)

    def _init_ui(self):
        self.setMinimumHeight(62)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 8, 16, 8)
        main_layout.setSpacing(6)

        main_layout.addStretch(1)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.lbl_name = QLabel(self.ollama_info["name"])
        self.lbl_name.setStyleSheet("font-size: 13.5px; font-weight: bold; color: #FFFFFF;")

        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: bold;")

        desc_text = f"{self.ollama_info['desc']} · 다운로드 크기: 약 {self.gguf_info['size_mb']}MB"
        self.setToolTip(desc_text)
        self.lbl_name.setToolTip(desc_text)
        self.lbl_desc = QLabel(desc_text)
        self.lbl_desc.setVisible(False)

        title_row.addWidget(self.lbl_name)
        title_row.addWidget(self.lbl_status)
        title_row.addStretch(1)

        top_row.addLayout(title_row, stretch=1)

        # 액션 버튼
        btn_box = QHBoxLayout()
        btn_box.setSpacing(6)
        btn_box.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.btn_select = QPushButton("선택 적용")
        self.btn_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ACCENT_PURPLE};
                color: #FFFFFF;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 14px;
                border-radius: 5px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #7C3AED;
            }}
        """)
        self.btn_select.clicked.connect(self._on_select_clicked)

        self.btn_download = QPushButton("⬇️ 다운로드")
        self.btn_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download.setStyleSheet("""
            QPushButton {{
                background-color: #10B981;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 14px;
                border-radius: 5px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #059669;
            }}
        """)
        self.btn_download.clicked.connect(self._on_download_clicked)

        self.btn_delete = QPushButton("🗑️ 삭제")
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

        self.btn_cancel = QPushButton("다운로드 취소")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: rgba(239, 68, 68, 0.15);
                color: #EF4444;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 14px;
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

        # 프로그레스 바
        self.progress_container = QWidget()
        p_layout = QVBoxLayout(self.progress_container)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(3)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
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
        main_layout.addStretch(1)

    def refresh_state(self, active_engine: str = None, is_alive: bool = None, installed_models: list = None):
        if sip.isdeleted(self) or not hasattr(self, 'lbl_status') or sip.isdeleted(self.lbl_status):
            return

        if active_engine:
            self.current_active = active_engine

        if is_alive is None:
            is_alive, _ = LLMModelManager.check_ollama_alive()
        self.is_alive = is_alive

        if is_alive:
            installed = LLMModelManager.is_ollama_model_installed(self.ollama_info["tag"], installed_models=installed_models)
            if "translategemma" in self.ollama_info["tag"]:
                engine_key = "gemma"
            elif "7.8b" in self.ollama_info["tag"] or "7b" in self.ollama_info["tag"]:
                engine_key = "exaone7b"
            elif "hy-mt" in self.ollama_info["tag"] or "hymt" in self.ollama_info["tag"]:
                engine_key = "hymt"
            else:
                engine_key = "exaone"
            is_current = (self.current_active in [engine_key, f"ollama:{self.ollama_info['tag']}", self.ollama_info['tag']])
            label_text = "✓ Ollama 설치됨"
        else:
            installed = LLMModelManager.is_gguf_model_installed(self.gguf_info)
            if "translategemma" in self.gguf_info["id"]:
                engine_key = "gemma"
            elif "7.8b" in self.gguf_info["id"] or "7b" in self.gguf_info["id"]:
                engine_key = "exaone7b"
            elif "hymt" in self.gguf_info["id"] or "hy-mt" in self.gguf_info["id"]:
                engine_key = "hymt"
            else:
                engine_key = "exaone"
            is_current = (self.current_active in [engine_key, self.gguf_info["id"]])
            label_text = "✓ 내장 준비됨"

        if installed:
            if is_current:
                self.lbl_status.setText("● 현재 번역 엔진으로 사용 중")
                self.lbl_status.setStyleSheet("background-color: rgba(99,102,241,0.25); color: #818CF8;")
            else:
                self.lbl_status.setText(label_text)
                self.lbl_status.setStyleSheet("background-color: rgba(16,185,129,0.2); color: #34D399;")
            self.btn_select.setVisible(not is_current)
            self.btn_download.setVisible(False)
            self.btn_cancel.setVisible(False)
            self.btn_delete.setVisible(not is_current)
            self.progress_container.setVisible(False)
        else:
            active_worker = None
            last_pct = 0
            last_msg = ""
            if is_alive:
                active_worker = LLMModelManager.get_active_ollama_worker(self.ollama_info["tag"])
                if active_worker:
                    last_pct, last_msg = LLMModelManager.get_last_ollama_progress(self.ollama_info["tag"])
            else:
                active_worker = LLMModelManager.get_active_gguf_worker(self.gguf_info["id"])
                if active_worker:
                    last_pct, last_msg = LLMModelManager.get_last_gguf_progress(self.gguf_info["id"])

            if active_worker:
                self.worker = active_worker
                self.lbl_status.setText("다운로드 중...")
                self.lbl_status.setStyleSheet("background-color: rgba(245,158,11,0.2); color: #F59E0B;")
                self.btn_select.setVisible(False)
                self.btn_download.setVisible(False)
                self.btn_cancel.setVisible(True)
                self.btn_cancel.setEnabled(True)
                self.btn_cancel.setText("다운로드 취소")
                self.btn_delete.setVisible(False)

                self.progress_bar.setValue(last_pct)
                self.lbl_progress_status.setText(last_msg)
                self.progress_container.setVisible(True)

                try:
                    self.worker.progress_signal.disconnect(self._on_progress)
                except Exception:
                    pass
                try:
                    self.worker.finished_signal.disconnect(self._on_finished)
                except Exception:
                    pass
                self.worker.progress_signal.connect(self._on_progress)
                self.worker.finished_signal.connect(self._on_finished)
            else:
                self.lbl_status.setText("미설치")
                self.lbl_status.setStyleSheet("background-color: rgba(148,163,184,0.15); color: #94A3B8;")
                self.btn_select.setVisible(False)
                self.btn_download.setVisible(True)
                self.btn_download.setEnabled(True)
                self.btn_download.setText("⬇️ 다운로드")
                self.btn_cancel.setVisible(False)
                self.btn_delete.setVisible(False)
                self.progress_container.setVisible(False)

    def _on_select_clicked(self):
        is_alive, _ = LLMModelManager.check_ollama_alive()
        if is_alive:
            self.model_selected_signal.emit("ollama", self.ollama_info["tag"])
        else:
            if not LLMModelManager.is_cuda_binary_available():
                if LLMModelManager.can_install_llm_cuda():
                    ret = QMessageBox.question(
                        self,
                        "⚡ GPU 가속 팩 설치 필요",
                        f"'{self.gguf_info['name']}' 모델은 CPU 모드로 실행 시 속도가 매우 느려(문장당 수초~수십초 지연) 정상적인 실시간 동시통역이 어렵습니다.\n\n"
                        "원활한 실시간 통역을 위해 NVIDIA GPU 가속 팩(약 460MB)을 먼저 설치하신 후 사용하실 수 있습니다.\n\n"
                        "지금 GPU 가속 팩을 다운로드하시겠습니까?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if ret == QMessageBox.StandardButton.Yes:
                        dlg = self.window()
                        if hasattr(dlg, 'request_cuda_and_download_model'):
                            dlg.request_cuda_and_download_model(self.gguf_info, self)
                        elif hasattr(dlg, '_execute_cuda_pack_download'):
                            dlg._execute_cuda_pack_download()
                    return
                else:
                    ret = QMessageBox.question(
                        self,
                        "⚠️ 로컬 LLM GPU 가속 불가 안내",
                        f"{LLMModelManager.llm_gpu_unavailable_reason()}\n\n"
                        f"CPU 모드로 '{self.gguf_info['name']}' 모델을 실행하면 번역 속도가 매우 느려 실시간 동시통역에 지연이 발생할 수 있습니다.\n"
                        "• 권장: 클라우드 번역 엔진(Google 무료, DeepL, Groq 등) 사용\n\n"
                        "그래도 CPU 모드로 이 모델을 선택하시겠습니까?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if ret != QMessageBox.StandardButton.Yes:
                        return
            self.model_selected_signal.emit("embedded", self.gguf_info["id"])

    def _on_download_clicked(self):
        is_alive, _ = LLMModelManager.check_ollama_alive()
        if is_alive:
            worker = LLMModelManager.get_active_ollama_worker(self.ollama_info["tag"])
            if worker:
                self.worker = worker
            else:
                self.worker = OllamaPullWorker(self.ollama_info["tag"])
                self.worker.start()

            self.lbl_status.setText("다운로드 중...")
            self.lbl_status.setStyleSheet("background-color: rgba(245,158,11,0.2); color: #F59E0B;")
            self.btn_select.setVisible(False)
            self.btn_download.setVisible(False)
            self.btn_cancel.setVisible(True)
            self.btn_cancel.setEnabled(True)
            self.btn_cancel.setText("다운로드 취소")
            self.btn_delete.setVisible(False)
            self.progress_container.setVisible(True)
            last_pct, last_msg = LLMModelManager.get_last_ollama_progress(self.ollama_info["tag"])
            self.progress_bar.setValue(last_pct)
            self.lbl_progress_status.setText(last_msg if last_pct > 0 else "Ollama 서버에 다운로드를 요청합니다...")
            try:
                self.worker.progress_signal.disconnect(self._on_progress)
            except Exception:
                pass
            try:
                self.worker.finished_signal.disconnect(self._on_finished)
            except Exception:
                pass
            self.worker.progress_signal.connect(self._on_progress)
            self.worker.finished_signal.connect(self._on_finished)
        else:
            # GGUF 로컬 모델 다운로드 시 GPU 가속 팩 선행 설치 확인
            if not LLMModelManager.is_cuda_binary_available():
                if LLMModelManager.can_install_llm_cuda():
                    ret = QMessageBox.question(
                        self,
                        "⚡ GPU 가속 팩 선행 설치 필요",
                        f"'{self.gguf_info['name']}' 모델을 원활하게 사용하려면 NVIDIA GPU 가속 팩(약 460MB)이 먼저 필요합니다.\n\n"
                        "CPU 모드로 로컬 LLM을 실행할 경우 번역 속도가 매우 느려(문장당 수초~수십초 지연) 정상적인 실시간 동시통역이 불가능합니다.\n\n"
                        "먼저 GPU 가속 팩을 다운로드하시겠습니까?\n"
                        f"(가속 팩 설치 완료 후 '{self.gguf_info['name']}' 모델 다운로드가 자동으로 시작됩니다.)",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if ret == QMessageBox.StandardButton.Yes:
                        dlg = self.window()
                        if hasattr(dlg, 'request_cuda_and_download_model'):
                            dlg.request_cuda_and_download_model(self.gguf_info, self)
                        elif hasattr(dlg, '_execute_cuda_pack_download'):
                            dlg._execute_cuda_pack_download()
                    return
                else:
                    ret = QMessageBox.question(
                        self,
                        "⚠️ 로컬 LLM GPU 가속 불가 안내",
                        f"{LLMModelManager.llm_gpu_unavailable_reason()}\n\n"
                        "CPU 모드로 로컬 LLM을 구동하면 번역 속도가 매우 느려(문장당 수십 초) 실시간 자막 통역에 부적합할 수 있습니다.\n"
                        "• 권장: 클라우드 번역 엔진(Google 웹 무료, DeepL, Groq 등) 사용\n\n"
                        f"그래도 CPU 모드로 '{self.gguf_info['name']}' 모델을 다운로드하시겠습니까?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if ret != QMessageBox.StandardButton.Yes:
                        return

            self.start_download()

    def start_download(self):
        """실제 GGUF 다운로드 작업 시작"""
        worker = LLMModelManager.get_active_gguf_worker(self.gguf_info["id"])
        if worker:
            self.worker = worker
        else:
            self.worker = GGUFDownloadWorker(self.gguf_info)
            self.worker.start()

        self.lbl_status.setText("다운로드 중...")
        self.lbl_status.setStyleSheet("background-color: rgba(245,158,11,0.2); color: #F59E0B;")
        self.btn_select.setVisible(False)
        self.btn_download.setVisible(False)
        self.btn_cancel.setVisible(True)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("다운로드 취소")
        self.btn_delete.setVisible(False)
        self.progress_container.setVisible(True)
        last_pct, last_msg = LLMModelManager.get_last_gguf_progress(self.gguf_info["id"])
        self.progress_bar.setValue(last_pct)
        self.lbl_progress_status.setText(last_msg if last_pct > 0 else "HuggingFace에서 내장 GGUF 가중치를 다운로드합니다...")
        try:
            self.worker.progress_signal.disconnect(self._on_progress)
        except Exception:
            pass
        try:
            self.worker.finished_signal.disconnect(self._on_finished)
        except Exception:
            pass
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.finished_signal.connect(self._on_finished)

    def _on_cancel_clicked(self):
        worker = None
        if self.is_alive:
            worker = LLMModelManager.get_active_ollama_worker(self.ollama_info["tag"])
        else:
            worker = LLMModelManager.get_active_gguf_worker(self.gguf_info["id"])

        target_worker = worker or self.worker
        if target_worker:
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("취소 중...")
            self.lbl_progress_status.setText("다운로드 취소 요청 중...")
            target_worker.cancel()

    def _on_progress(self, tag, percent, msg):
        if sip.isdeleted(self) or not hasattr(self, 'progress_bar') or sip.isdeleted(self.progress_bar):
            return
        self.progress_bar.setValue(percent)
        self.lbl_progress_status.setText(msg)

    def _on_finished(self, tag, success, msg):
        if sip.isdeleted(self) or not hasattr(self, 'progress_container') or sip.isdeleted(self.progress_container):
            return
        self.progress_container.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("다운로드 취소")
        self.btn_download.setEnabled(True)
        self.btn_download.setText("⬇️ 다운로드")
        if success:
            self.refresh_state()
            if sip.isdeleted(self):
                return
            self.model_status_changed_signal.emit()
            ret = QMessageBox.question(
                self,
                "다운로드 완료",
                f"'{self.ollama_info['name']}' 모델 다운로드가 완료되었습니다.\n\n이 모델을 지금 바로 번역 엔진으로 적용하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ret == QMessageBox.StandardButton.Yes and not sip.isdeleted(self):
                self._on_select_clicked()
        else:
            self.refresh_state()
            if not sip.isdeleted(self):
                self.model_status_changed_signal.emit()
                if "취소" not in msg:
                    QMessageBox.warning(self, "다운로드 실패", f"오류가 발생했습니다:\n{msg}")

    def _on_delete_clicked(self):
        ret = QMessageBox.question(
            self,
            "모델 삭제 확인",
            f"'{self.ollama_info['name']}' 모델을 디스크에서 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            is_alive, _ = LLMModelManager.check_ollama_alive()
            if is_alive:
                ok = LLMModelManager.delete_ollama_model(self.ollama_info["tag"])
            else:
                ok = LLMModelManager.delete_gguf_model(self.gguf_info)

            if ok:
                QMessageBox.information(self, "삭제 완료", "모델이 삭제되었습니다.")
                self.refresh_state()
                self.model_status_changed_signal.emit()
            else:
                QMessageBox.warning(self, "삭제 실패", "모델 파일을 삭제하지 못했습니다.")

class LLMModelDialog(QDialog):
    """로컬 AI 번역 모델 통합 관리자 (생성형 LLM)"""
    llm_selected_signal = pyqtSignal(str, str)

    def __init__(self, current_backend: str, current_model: str, current_engine: str = None, target_model_id: str = None, parent=None):
        super().__init__(parent)
        self.current_backend = current_backend
        self.current_model = current_model
        self.current_engine = current_engine or current_model
        self.target_model_id = target_model_id if isinstance(target_model_id, str) else None
        self.cards = []
        self._pending_model_download = None

        self.setWindowTitle("로컬 AI 번역 모델 통합 관리자")
        self.resize(780, 700)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLOR_BG_DARK};
                color: {COLOR_TEXT_PRIMARY};
            }}
        """)

        self._init_ui()
        self._refresh_storage_info()
        self._refresh_cuda_accel_info()

    @staticmethod
    def _is_matching_card(card: UnifiedLLMModelCard, target_id: str) -> bool:
        """지정된 target_id(엔진 키, 태그, 모델명 등)가 해당 카드와 일치하는지 정밀 판별"""
        if not target_id or not card:
            return False
        t = str(target_id).strip().lower()
        for prefix in ("ollama:", "embedded:"):
            if t.startswith(prefix):
                t = t[len(prefix):].strip()

        o_tag = card.ollama_info.get("tag", "").lower()
        o_name = card.ollama_info.get("name", "").lower()
        g_id = card.gguf_info.get("id", "").lower()
        g_name = card.gguf_info.get("name", "").lower()

        # 1. EXAONE 7.8B / 7B (우선순위: 7b / 7.8b / masterpiece)
        if ("7.8b" in t or "78b" in t or "7b" in t or "masterpiece" in t) and ("exaone" in t or "lg" in t or "masterpiece" in t):
            return ("7.8b" in o_tag or "7.8b" in g_id)

        # 2. EXAONE 2.4B (7b가 아닌 exaone 또는 2.4b)
        if "exaone" in t or "2.4b" in t or "24b" in t:
            if not ("7.8b" in t or "78b" in t or "7b" in t):
                return ("2.4b" in o_tag or "2.4b" in g_id)

        # 3. TranslateGemma
        if "gemma" in t or "translategemma" in t:
            return ("translategemma" in o_tag or "translategemma" in g_id)

        # 4. Tencent Hy-MT2
        if "hymt" in t or "hy-mt" in t or "tencent" in t:
            return ("hy-mt" in o_tag or "hymt" in g_id)

        # 5. 일반 텍스트 포함 검사 (Cleaned alphanumeric substring)
        clean_t = "".join(c for c in t if c.isalnum())
        if not clean_t:
            return False
        for tag_str in (o_tag, o_name, g_id, g_name):
            clean_tag = "".join(c for c in tag_str if c.isalnum())
            if clean_t in clean_tag or clean_tag in clean_t:
                return True

        return False

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # 1. 헤더 카드
        head_card = CardWidget()
        h_layout = QHBoxLayout(head_card)
        h_layout.setContentsMargins(16, 12, 16, 12)

        title = QLabel("🌐 로컬 AI 번역 모델 통합 관리")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #ECEFF1;")
        h_layout.addWidget(title)
        h_layout.addStretch(1)
        layout.addWidget(head_card)

        # 1-2. 공용 저장소 및 환경변수 정보 카드 (폴더 지정 기능 탑재)
        self.storage_card = CardWidget()
        s_layout = QVBoxLayout(self.storage_card)
        s_layout.setContentsMargins(16, 12, 16, 12)
        s_layout.setSpacing(8)

        s_top = QHBoxLayout()
        s_title = QLabel("📁 공용 모델 저장소 & 환경변수 정보")
        s_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        s_top.addWidget(s_title)
        s_top.addStretch(1)

        btn_open_folder = QPushButton("📂 탐색기로 열기")
        btn_open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_folder.setStyleSheet(f"""
            QPushButton {{
                background-color: #1E293B;
                color: #ECEFF1;
                border: 1px solid {COLOR_BORDER};
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #334155;
            }}
        """)
        btn_open_folder.clicked.connect(self._on_open_folder_clicked)

        btn_change_folder = QPushButton("📁 폴더 지정/변경")
        btn_change_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_change_folder.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ACCENT_PURPLE};
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #7C3AED;
            }}
        """)
        btn_change_folder.clicked.connect(self._on_change_folder_clicked)

        s_top.addWidget(btn_open_folder)
        s_top.addWidget(btn_change_folder)
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
        grid.setContentsMargins(12, 9, 12, 9)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(7)

        # 1행: 공용 지정 폴더 & 디스크 여유 공간
        grid.addWidget(QLabel("📍 공용 모델 지정 폴더:"), 0, 0)
        self.lbl_custom_dir = QLabel("-")
        self.lbl_custom_dir.setStyleSheet("font-weight: bold; color: #38BDF8; font-size: 11px;")
        grid.addWidget(self.lbl_custom_dir, 0, 1)

        grid.addWidget(QLabel("💾 디스크 여유 공간:"), 0, 2)
        self.lbl_free_space = QLabel("-")
        self.lbl_free_space.setStyleSheet("font-weight: bold; color: #34D399; font-size: 11px;")
        grid.addWidget(self.lbl_free_space, 0, 3)

        # 2행: HF_HOME 환경변수 & GGUF 공용 폴더
        grid.addWidget(QLabel("🌐 HF_HOME (환경변수):"), 1, 0)
        self.lbl_hf_home = QLabel("-")
        self.lbl_hf_home.setStyleSheet("color: #E2E8F0; font-size: 11px;")
        grid.addWidget(self.lbl_hf_home, 1, 1)

        grid.addWidget(QLabel("📦 GGUF 단일 공유 폴더:"), 1, 2)
        self.lbl_gguf_dir = QLabel("-")
        self.lbl_gguf_dir.setStyleSheet("color: #E2E8F0; font-size: 11px;")
        grid.addWidget(self.lbl_gguf_dir, 1, 3)

        # 3행: C: 드라이브 연동 상태
        grid.addWidget(QLabel("🔗 C: 드라이브 연동:"), 2, 0)
        self.lbl_junction_status = QLabel("-")
        self.lbl_junction_status.setStyleSheet("color: #A78BFA; font-size: 11px;")
        grid.addWidget(self.lbl_junction_status, 2, 1, 1, 3)

        s_layout.addWidget(grid_frame)
        layout.addWidget(self.storage_card)

        # 1-3. 에디션 및 GPU 가속 상태 카드 (Lite 버전 CUDA 온디맨드 다운로드 지원)
        self.cuda_card = CardWidget()
        self.cuda_card.setObjectName("CudaCard")
        self.cuda_card.setMinimumHeight(62)
        c_gpu_layout = QVBoxLayout(self.cuda_card)
        c_gpu_layout.setContentsMargins(16, 8, 16, 8)
        c_gpu_layout.setSpacing(6)

        c_gpu_layout.addStretch(1)

        c_top = QHBoxLayout()
        c_top.setSpacing(10)
        c_top.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.lbl_cuda_title = QLabel("⚡ 번역 가속 엔진 (NVIDIA CUDA)")
        self.lbl_cuda_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1; border: none; outline: none; background: transparent;")
        self.lbl_edition_badge = QLabel("풀 에디션 (Full)")
        self.lbl_edition_badge.setStyleSheet("font-size: 10px; font-weight: bold; color: #A78BFA; background: rgba(167, 139, 250, 0.15); border: 1px solid rgba(167, 139, 250, 0.4); border-radius: 4px; padding: 2px 6px;")
        self.lbl_edition_badge.setVisible(False)
        
        c_top.addWidget(self.lbl_cuda_title)
        c_top.addWidget(self.lbl_edition_badge)
        c_top.addStretch(1)

        self.btn_cuda_action = QPushButton("⚡ CUDA 가속 팩 다운로드")
        self.btn_cuda_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cuda_action.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        self.btn_cuda_action.clicked.connect(self._on_cuda_action_clicked)
        c_top.addWidget(self.btn_cuda_action)
        c_gpu_layout.addLayout(c_top)

        self.lbl_cuda_status = QLabel("가속 상태 확인 중...")
        self.lbl_cuda_status.setStyleSheet("font-size: 11px; color: #94A3B8; border: none; outline: none; background: transparent;")
        self.lbl_cuda_status.setVisible(False)
        c_gpu_layout.addWidget(self.lbl_cuda_status)

        # 프로그레스 컨테이너
        self.cuda_progress_container = QWidget()
        cp_layout = QVBoxLayout(self.cuda_progress_container)
        cp_layout.setContentsMargins(0, 0, 0, 0)
        cp_layout.setSpacing(3)
        self.cuda_progress_bar = QProgressBar()
        self.cuda_progress_bar.setRange(0, 100)
        self.cuda_progress_bar.setStyleSheet(f"""
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
                background-color: #10B981;
                border-radius: 3px;
            }}
        """)
        self.lbl_cuda_progress = QLabel("")
        self.lbl_cuda_progress.setStyleSheet("font-size: 10px; color: #94A3B8;")
        cp_layout.addWidget(self.cuda_progress_bar)
        cp_layout.addWidget(self.lbl_cuda_progress)
        self.cuda_progress_container.setVisible(False)
        c_gpu_layout.addWidget(self.cuda_progress_container)

        c_gpu_layout.addStretch(1)

        layout.addWidget(self.cuda_card)

        # 2. 모델 리스트 스크롤
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 4, 0)
        c_layout.setSpacing(10)

        # 섹션 1: 로컬 생성형 LLM
        sec1_lbl = QLabel("🤖 로컬 생성형 LLM 번역 모델 (GGUF / Ollama)")
        sec1_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {COLOR_ACCENT_PURPLE}; margin-top: 4px;")
        c_layout.addWidget(sec1_lbl)

        is_alive, ver = LLMModelManager.check_ollama_alive()
        installed_models = LLMModelManager.get_installed_ollama_models() if is_alive else []

        model_pairs = list(zip(RECOMMENDED_OLLAMA_MODELS, RECOMMENDED_GGUF_MODELS))
        for o_info, g_info in model_pairs:
            card = UnifiedLLMModelCard(
                o_info, g_info, self.current_engine,
                is_alive=is_alive,
                installed_models=installed_models
            )
            card.model_selected_signal.connect(self._on_model_selected)
            card.model_status_changed_signal.connect(self._on_status_changed)
            c_layout.addWidget(card)
            self.cards.append(card)

        c_layout.addStretch(1)
        self.scroll.setWidget(container)
        layout.addWidget(self.scroll, stretch=1)

        # 타겟 모델 지정 시 해당 카드로 스크롤 이동 및 테두리 하이라이트
        if self.target_model_id:
            from PyQt6.QtCore import QTimer
            for card in self.cards:
                if self._is_matching_card(card, self.target_model_id):
                    QTimer.singleShot(150, lambda c=card: self.scroll.ensureWidgetVisible(c))
                    card.setStyleSheet(f"""
                        #UnifiedLLMModelCard {{
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

        # 3. 하단 안내 및 닫기
        bot_bar = QHBoxLayout()
        info_tip = "💡 로컬 LLM 모델은 원작의 맥락 이해와 한국어 특화 자연스러운 번역을 제공합니다."
        lbl_tip = QLabel(info_tip)
        lbl_tip.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SECONDARY};")
        bot_bar.addWidget(lbl_tip)
        bot_bar.addStretch(1)

        btn_close = QPushButton("닫기")
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

    def _on_model_selected(self, backend: str, model_id: str):
        self.current_backend = backend
        self.current_model = model_id
        self.current_engine = model_id
        for c in self.cards:
            c.refresh_state(model_id)
        self.llm_selected_signal.emit(backend, model_id)

        if "7.8b" in model_id.lower() or "7b" in model_id.lower():
            m_name = "LG EXAONE 3.5 (7.8B)"
        elif "translategemma" in model_id.lower():
            m_name = "Google TranslateGemma 4B"
        elif "hy-mt" in model_id.lower() or "hymt" in model_id.lower():
            m_name = "Tencent Hy-MT2 1.8B"
        else:
            m_name = "LG EXAONE 3.5 (2.4B)"

        QMessageBox.information(self, "번역 엔진 지정", f"로컬 번역 엔진이 '{m_name}'(으)로 지정되었습니다.")
        self.accept()

    def _on_status_changed(self):
        if sip.isdeleted(self):
            return
        is_alive, ver = LLMModelManager.check_ollama_alive(force_refresh=True)
        installed_models = LLMModelManager.get_installed_ollama_models(force_refresh=True) if is_alive else []
        for c in self.cards:
            if not sip.isdeleted(c):
                c.refresh_state(self.current_engine, is_alive=is_alive, installed_models=installed_models)
        if not sip.isdeleted(self):
            self._refresh_storage_info()
            self._refresh_cuda_accel_info()

    def _refresh_storage_info(self):
        """공용 모델 디렉터리, 디스크 여유 공간, 환경변수, C: 드라이브 연동 상태 갱신"""
        if sip.isdeleted(self) or not hasattr(self, 'lbl_custom_dir') or sip.isdeleted(self.lbl_custom_dir):
            return
        c_dir = get_custom_model_dir()

        # 1. 지정 폴더 표시
        if c_dir and os.path.exists(c_dir):
            self.lbl_custom_dir.setText(c_dir)
            self.lbl_custom_dir.setStyleSheet("font-weight: bold; color: #38BDF8; font-size: 11px;")
            try:
                total, used, free = shutil.disk_usage(c_dir)
                free_gb = free / (1024 ** 3)
                total_gb = total / (1024 ** 3)
                self.lbl_free_space.setText(f"여유 {free_gb:.1f} GB / 전체 {total_gb:.1f} GB")
                col = "#F59E0B" if free_gb < 20 else "#34D399"
                self.lbl_free_space.setStyleSheet(f"font-weight: bold; color: {col}; font-size: 11px;")
            except Exception:
                self.lbl_free_space.setText("용량 확인 불가")
        else:
            self.lbl_custom_dir.setText("미지정 (기본 C: 캐시)")
            self.lbl_custom_dir.setStyleSheet("font-weight: bold; color: #94A3B8; font-size: 11px;")
            self.lbl_free_space.setText("-")

        # 2. HF_HOME 환경변수 확인
        hf_home = os.environ.get("HF_HOME")
        if not hf_home:
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                    hf_home, _ = winreg.QueryValueEx(key, "HF_HOME")
            except Exception:
                pass

        if hf_home:
            if not os.environ.get("HF_HOME"):
                os.environ["HF_HOME"] = hf_home
            self.lbl_hf_home.setText(f"{hf_home} (활성)")
            self.lbl_hf_home.setStyleSheet("color: #38BDF8; font-size: 11px;")
        else:
            self.lbl_hf_home.setText("미설정 (C: 기본 캐시 사용)")
            self.lbl_hf_home.setStyleSheet("color: #94A3B8; font-size: 11px;")

        # 3. GGUF 단일 공유 폴더 확인
        gguf_dir = os.path.join(c_dir, "GGUF") if c_dir else None
        if gguf_dir and os.path.exists(gguf_dir):
            try:
                files = [f for f in os.listdir(gguf_dir) if f.lower().endswith(".gguf")]
                self.lbl_gguf_dir.setText(f"{gguf_dir} ({len(files)}개 보관)")
                self.lbl_gguf_dir.setStyleSheet("color: #E2E8F0; font-size: 11px;")
            except Exception:
                self.lbl_gguf_dir.setText(gguf_dir)
        else:
            self.lbl_gguf_dir.setText("미생성")
            self.lbl_gguf_dir.setStyleSheet("color: #94A3B8; font-size: 11px;")

        # 4. C: 드라이브 연동 (Junction / Reparse point 검사)
        default_cache = os.path.expanduser("~/.cache/huggingface")
        is_linked = False
        link_target = ""
        if os.path.exists(default_cache):
            try:
                target = os.readlink(default_cache)
                target_clean = target.replace("\\\\?\\", "")
                is_linked = True
                link_target = target_clean
            except OSError:
                is_linked = False

        if is_linked:
            self.lbl_junction_status.setText(f"✓ C: 캐시 정션 연동 활성 (-> {link_target})")
            self.lbl_junction_status.setStyleSheet("color: #34D399; font-weight: bold; font-size: 11px;")
        else:
            self.lbl_junction_status.setText("C: 기본 로컬 디렉터리 (심볼릭 미연결)")
            self.lbl_junction_status.setStyleSheet("color: #94A3B8; font-size: 11px;")

    def _on_change_folder_clicked(self):
        """공용 모델 디렉터리 사용자 선택 및 config.json 반영"""
        from .config import load_config, save_config
        current_dir = get_custom_model_dir() or r"D:\AI_Models"
        start_dir = current_dir if os.path.exists(current_dir) else "D:\\"
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "로컬 AI 공용 모델 저장 폴더 선택",
            start_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        if not selected_dir:
            return

        selected_dir = os.path.normpath(selected_dir)
        if selected_dir == current_dir:
            return

        # GGUF 하위 폴더 자동 생성 준비
        gguf_dir = os.path.join(selected_dir, "GGUF")
        try:
            os.makedirs(gguf_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "폴더 생성 오류", f"폴더 권한을 확인해주세요:\n{e}")
            return

        # config.json 업데이트
        cfg = load_config()
        cfg["custom_model_dir"] = selected_dir
        save_config(cfg)

        self._refresh_storage_info()
        self._on_status_changed()

        QMessageBox.information(
            self,
            "공용 모델 폴더 지정 완료",
            f"공용 모델 저장 폴더가 다음으로 변경되었습니다:\n\n{selected_dir}\n\n"
            f"• 내장 GGUF 모델 탐색 시 이 폴더를 최우선으로 검사합니다.\n"
            f"• 하위 공유 폴더: {gguf_dir}"
        )

    def _on_open_folder_clicked(self):
        """지정된 공용 모델 폴더를 윈도우 파일 탐색기로 열기"""
        c_dir = get_custom_model_dir() or os.path.expanduser("~/.cache/huggingface")
        if os.path.exists(c_dir):
            try:
                os.startfile(c_dir)
            except Exception as e:
                QMessageBox.warning(self, "탐색기 열기 실패", f"폴더를 열 수 없습니다:\n{e}")
        else:
            QMessageBox.warning(self, "폴더 없음", f"폴더가 존재하지 않습니다:\n{c_dir}")

    def _refresh_cuda_accel_info(self):
        """에디션 정보 및 CUDA GPU 가속(STT cuBLAS 및 LLM ggml-cuda) 상태 갱신"""
        if sip.isdeleted(self) or not hasattr(self, 'lbl_cuda_status') or sip.isdeleted(self.lbl_cuda_status):
            return
        from src.cuda_utils import get_cuda_pack_status
        status = get_cuda_pack_status()
        edition = LLMModelManager.get_app_edition()
        has_gpu = status["has_gpu"]
        has_cublas = status["has_cublas"]
        has_ggml = status["has_ggml_cuda"]
        is_fully_ready = status["is_fully_ready"]

        if edition == "full":
            self.lbl_edition_badge.setText("풀 에디션 (Full - CUDA 전체 내장)")
            self.lbl_edition_badge.setStyleSheet("font-size: 10px; font-weight: bold; color: #818CF8; background: rgba(99, 102, 241, 0.15); border: 1px solid rgba(99, 102, 241, 0.4); border-radius: 4px; padding: 2px 6px;")
        else:
            self.lbl_edition_badge.setText("라이트 에디션 (Lite - 경량 설치)")
            self.lbl_edition_badge.setStyleSheet("font-size: 10px; font-weight: bold; color: #38BDF8; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 4px; padding: 2px 6px;")

        # 드라이버/GPU 세대 때문에 로컬 LLM CUDA 는 설치로 해결되지 않는 경우
        llm_blocked = has_gpu and has_cublas and not has_ggml and bool(status.get("llm_issue"))
        if (is_fully_ready or llm_blocked) and not LLMModelManager.get_active_cuda_worker():
            if llm_blocked:
                status_desc = f"● 음성인식 GPU 가속 활성화됨 · 로컬 LLM은 CPU로 동작 ({status['llm_issue']})"
            elif status.get("llm_restart_required"):
                status_desc = "● GPU 가속 팩 설치됨 · 음성인식은 즉시 GPU 사용 가능, 로컬 LLM은 프로그램 재시작 후 GPU로 전환"
            else:
                status_desc = "● NVIDIA CUDA GPU 가속 활성화됨 (음성인식 STT & 로컬 LLM 실시간 GPU 구동)"
            self.lbl_cuda_status.setText(status_desc)
            self.lbl_cuda_title.setToolTip(status_desc)
            self.cuda_card.setToolTip(status_desc)
            self.lbl_cuda_status.setStyleSheet("color: #34D399; font-weight: bold; font-size: 11px; border: none; outline: none; background: transparent;")
            self.btn_cuda_action.setText("✓ 가속 팩 설치됨")
            self.btn_cuda_action.setEnabled(False)
            self.btn_cuda_action.setStyleSheet("background-color: rgba(16, 185, 129, 0.2); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 5px; padding: 6px 14px; font-size: 11px; font-weight: bold;")
            self.cuda_card.setStyleSheet(f"""
                QFrame#CudaCard {{
                    background-color: #111827;
                    border: 1px solid {COLOR_BORDER};
                    border-radius: 8px;
                }}
                QLabel {{
                    background: transparent;
                    border: none;
                    outline: none;
                }}
            """)
        else:
            active_cuda = LLMModelManager.get_active_cuda_worker()
            if active_cuda:
                self.cuda_worker = active_cuda
                status_desc = "⚡ NVIDIA CUDA 가속 라이브러리 다운로드 진행 중..."
                self.lbl_cuda_status.setText(status_desc)
                self.lbl_cuda_status.setStyleSheet("color: #F59E0B; font-weight: bold; font-size: 11px; border: none; outline: none; background: transparent;")
                self.btn_cuda_action.setText("다운로드 중...")
                self.btn_cuda_action.setEnabled(False)
                self.btn_cuda_action.setStyleSheet("background-color: #1E293B; color: #94A3B8; border: 1px solid #334155; border-radius: 5px; padding: 6px 14px; font-size: 11px; font-weight: bold;")
                self.cuda_progress_container.setVisible(True)
                last_pct, last_msg = LLMModelManager.get_last_cuda_progress()
                self.cuda_progress_bar.setValue(last_pct)
                self.lbl_cuda_progress.setText(last_msg)
                try:
                    self.cuda_worker.progress_signal.disconnect(self._on_cuda_download_progress)
                except Exception:
                    pass
                try:
                    self.cuda_worker.finished_signal.disconnect(self._on_cuda_download_finished)
                except Exception:
                    pass
                self.cuda_worker.progress_signal.connect(self._on_cuda_download_progress)
                self.cuda_worker.finished_signal.connect(self._on_cuda_download_finished)
            else:
                self.cuda_progress_container.setVisible(False)
                missing_parts = []
                if not has_cublas:
                    missing_parts.append("STT cuBLAS")
                if not has_ggml:
                    missing_parts.append("로컬 LLM 가속기")
                missing_str = ", ".join(missing_parts)

                if has_gpu:
                    status_desc = f"💡 NVIDIA GPU 감지됨 · 가속 팩 미설치({missing_str}) (초고속 실시간 통역 필수 권장)"
                    self.lbl_cuda_status.setText(status_desc)
                    self.lbl_cuda_title.setToolTip(status_desc)
                    self.cuda_card.setToolTip(status_desc)
                    self.lbl_cuda_status.setStyleSheet("color: #FBBF24; font-weight: bold; font-size: 11px; border: none; outline: none; background: transparent;")
                    self.btn_cuda_action.setText("⚡ GPU 가속 팩 다운로드 (필수)")
                    self.btn_cuda_action.setEnabled(True)
                    self.btn_cuda_action.setStyleSheet("background-color: #10B981; color: #FFFFFF; border: none; border-radius: 5px; padding: 6px 14px; font-size: 11px; font-weight: bold;")
                    self.cuda_card.setStyleSheet(f"""
                        QFrame#CudaCard {{
                            background-color: #111827;
                            border: 1.5px solid rgba(245, 158, 11, 0.7);
                            border-radius: 8px;
                        }}
                        QLabel {{
                            background: transparent;
                            border: none;
                            outline: none;
                        }}
                    """)
                else:
                    status_desc = "○ CPU 전용 모드로 작동 중 (NVIDIA 그래픽 카드가 없어 GPU 가속을 사용할 수 없습니다)"
                    self.lbl_cuda_status.setText(status_desc)
                    self.lbl_cuda_title.setToolTip(status_desc)
                    self.cuda_card.setToolTip(status_desc)
                    self.lbl_cuda_status.setStyleSheet("color: #94A3B8; font-size: 11px; border: none; outline: none; background: transparent;")
                    self.btn_cuda_action.setText("NVIDIA GPU 없음")
                    self.btn_cuda_action.setEnabled(False)
                    self.btn_cuda_action.setStyleSheet("background-color: #334155; color: #E2E8F0; border: 1px solid #475569; border-radius: 5px; padding: 6px 14px; font-size: 11px; font-weight: bold;")
                    self.cuda_card.setStyleSheet(f"""
                        QFrame#CudaCard {{
                            background-color: #111827;
                            border: 1px solid {COLOR_BORDER};
                            border-radius: 8px;
                        }}
                        QLabel {{
                            background: transparent;
                            border: none;
                            outline: none;
                        }}
                    """)

    def request_cuda_and_download_model(self, model_info: dict, card=None):
        """가속 팩 다운로드 후 해당 GGUF 모델 다운로드를 연계 진행"""
        self._pending_model_download = (model_info, card)
        self._execute_cuda_pack_download()

    def _execute_cuda_pack_download(self):
        """CUDA 가속 팩 다운로드 작업 시작"""
        worker = LLMModelManager.get_active_cuda_worker()
        if worker:
            self.cuda_worker = worker
        else:
            self.cuda_worker = CUDAPackDownloadWorker(parent=None)
            self.cuda_worker.start()

        self.btn_cuda_action.setEnabled(False)
        self.btn_cuda_action.setText("다운로드 중...")
        self.cuda_progress_container.setVisible(True)
        last_pct, last_msg = LLMModelManager.get_last_cuda_progress()
        self.cuda_progress_bar.setValue(last_pct)
        self.lbl_cuda_progress.setText(last_msg if last_pct > 0 else "CUDA 가속 팩 서버 연결 중...")

        try:
            self.cuda_worker.progress_signal.disconnect(self._on_cuda_download_progress)
        except Exception:
            pass
        try:
            self.cuda_worker.finished_signal.disconnect(self._on_cuda_download_finished)
        except Exception:
            pass
        self.cuda_worker.progress_signal.connect(self._on_cuda_download_progress)
        self.cuda_worker.finished_signal.connect(self._on_cuda_download_finished)

    def _on_cuda_action_clicked(self):
        """CUDA 가속 팩 온디맨드 다운로드 실행"""
        ret = QMessageBox.question(
            self,
            "NVIDIA CUDA GPU 가속 팩 다운로드",
            "NVIDIA CUDA 가속 라이브러리(STT cuBLAS 및 로컬 LLM 가속 바이너리)를 다운로드하여 설치하시겠습니까?\n\n"
            "• 구성: cuBLAS 12(음성인식) + CUDA 13용 llama.cpp 라이브러리 한 세트(번역)\n"
            "• 음성인식은 설치 직후 재시작 없이 GPU로 전환할 수 있습니다.\n"
            "• 로컬 번역은 이번 실행에서 아직 쓰지 않았다면 바로, 이미 썼다면 재시작 후 GPU로 동작합니다.\n"
            "• 효과: 음성인식 지연시간 최소화 및 GPU 실시간 초고속 동시통역 활성화\n"
            "• 다운로드 중에도 기존 번역은 중단 없이 계속 사용하실 수 있습니다.\n\n"
            "계속 진행하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._execute_cuda_pack_download()

    def _on_cuda_download_progress(self, pct: int, msg: str):
        if sip.isdeleted(self) or not hasattr(self, 'cuda_progress_bar') or sip.isdeleted(self.cuda_progress_bar):
            return
        self.cuda_progress_bar.setValue(pct)
        self.lbl_cuda_progress.setText(msg)

    def _on_cuda_download_finished(self, success: bool, msg: str):
        if sip.isdeleted(self) or not hasattr(self, 'cuda_progress_container') or sip.isdeleted(self.cuda_progress_container):
            return
        self.cuda_progress_container.setVisible(False)

        # 다운로드된 DLL 경로 즉시 등록 및 프로세스 선행 매핑
        try:
            from src.cuda_utils import register_cuda_dll_directories, preload_cuda_dlls
            register_cuda_dll_directories(force=True)
            preload_cuda_dlls()
        except Exception:
            pass

        self._refresh_cuda_accel_info()
        for card in self.cards:
            if not sip.isdeleted(card):
                card.refresh_state()

        if success:
            # 부모 창(ControlPanel) 상태 및 배지 즉각 동기화
            parent = self.parent()
            if parent and hasattr(parent, '_refresh_all_status_badges'):
                try:
                    parent._refresh_all_status_badges()
                    parent._sync_all_pipeline_status()
                except Exception:
                    pass

            cfg = getattr(parent, 'config', None) or getattr(self, 'config', None) or {}
            cur_dev = cfg.get("device", "cpu")
            # GPU 설정인데 팩이 없어 CPU 로 로드돼 있던 STT 를 GPU 로 다시 로드
            stt_thread = getattr(parent, 'stt_thread', None)
            if cur_dev == "cuda" and stt_thread is not None and hasattr(stt_thread, 'update_config'):
                try:
                    stt_thread.update_config(cfg)
                except Exception:
                    pass

            if hasattr(self, '_pending_model_download') and self._pending_model_download:
                m_info, card = self._pending_model_download
                self._pending_model_download = None
                if not sip.isdeleted(self):
                    QMessageBox.information(
                        self,
                        "✨ GPU 가속 팩 설치 완료",
                        f"{msg}\n\n이어서 '{m_info['name']}' 모델 다운로드를 시작합니다!"
                    )
                if card and not sip.isdeleted(card):
                    card.start_download()
            else:
                if not sip.isdeleted(self):
                    # 사용자에게 GPU 모드로 자동 전환할지 안내
                    if cur_dev == "cpu" and parent and hasattr(parent, '_on_stt_dev_selected'):
                        q_switch = QMessageBox.question(
                            self,
                            "✨ CUDA 가속 팩 설치 완료",
                            f"{msg}\n\n현재 STT 음성인식 장치가 CPU로 설정되어 있습니다.\n"
                            "지금 NVIDIA CUDA GPU 가속 모드로 전환하시겠습니까?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                        )
                        if q_switch == QMessageBox.StandardButton.Yes:
                            try:
                                parent._on_stt_dev_selected("cuda")
                            except Exception:
                                pass
                    else:
                        QMessageBox.information(self, "✨ CUDA 가속 팩 설치 완료", msg)
        else:
            self._pending_model_download = None
            if not sip.isdeleted(self):
                QMessageBox.warning(self, "CUDA 가속 팩 설치 실패", msg)
