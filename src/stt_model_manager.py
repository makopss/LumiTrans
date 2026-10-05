import os
import time
import shutil
import threading
import logging
from typing import List, Dict, Optional, Tuple, Any
from PyQt6.QtCore import pyqtSignal, QObject
from src.i18n import tr

logger = logging.getLogger("STTModelManager")

AVAILABLE_STT_MODELS = [
    # ─── OpenAI Whisper 공식 라인업 ───
    {
        "id": "tiny.en",
        "name": "Whisper Tiny (English)",
        "category": "whisper",
        "category_name": "OpenAI Whisper 공식 라인업",
        "hf_id": "Systran/faster-whisper-tiny.en",
        "size_mb": 75,
        "vram_mb": 300,
        "cpu_usable": True,
        "cpu_tag": "CPU 쾌적",
        "desc": "초경량 테스트/저사양용, 초저지연 (영어 전용)"
    },
    {
        "id": "tiny",
        "name": "Whisper Tiny (Multilingual)",
        "category": "whisper",
        "category_name": "OpenAI Whisper 공식 라인업",
        "hf_id": "Systran/faster-whisper-tiny",
        "size_mb": 75,
        "vram_mb": 300,
        "cpu_usable": True,
        "cpu_tag": "CPU 쾌적",
        "desc": "초경량 다국어(한국어 포함) 지원 모델"
    },
    {
        "id": "base.en",
        "name": "Whisper Base (English)",
        "category": "whisper",
        "category_name": "OpenAI Whisper 공식 라인업",
        "hf_id": "Systran/faster-whisper-base.en",
        "size_mb": 145,
        "vram_mb": 500,
        "cpu_usable": True,
        "cpu_tag": "CPU 쾌적",
        "desc": "경량 기본 모델, 빠른 반응 (영어 전용)"
    },
    {
        "id": "base",
        "name": "Whisper Base (Multilingual)",
        "category": "whisper",
        "category_name": "OpenAI Whisper 공식 라인업",
        "hf_id": "Systran/faster-whisper-base",
        "size_mb": 145,
        "vram_mb": 500,
        "cpu_usable": True,
        "cpu_tag": "CPU 쾌적",
        "desc": "경량 다국어(한국어 포함) 기본 모델"
    },
    {
        "id": "small.en",
        "name": "Whisper Small (English)",
        "category": "whisper",
        "category_name": "OpenAI Whisper 공식 라인업",
        "hf_id": "Systran/faster-whisper-small.en",
        "size_mb": 480,
        "vram_mb": 1000,
        "cpu_usable": True,
        "cpu_tag": "CPU 원활",
        "desc": "가성비 및 속도-정확도 균형 표준 (영어 전용)"
    },
    {
        "id": "small",
        "name": "Whisper Small (Multilingual)",
        "category": "whisper",
        "category_name": "OpenAI Whisper 공식 라인업",
        "hf_id": "Systran/faster-whisper-small",
        "size_mb": 480,
        "vram_mb": 1000,
        "cpu_usable": True,
        "cpu_tag": "CPU 원활",
        "desc": "가성비 및 속도-정확도 균형 표준 (다국어/한국어 지원)"
    },
    {
        "id": "medium.en",
        "name": "Whisper Medium (English)",
        "category": "whisper",
        "category_name": "OpenAI Whisper 공식 라인업",
        "hf_id": "Systran/faster-whisper-medium.en",
        "size_mb": 1500,
        "vram_mb": 2600,
        "cpu_usable": False,
        "cpu_tag": "GPU 권장 (CPU 지연)",
        "desc": "고품질 영어 전사 (권장 VRAM 4GB+ · GPU 권장)"
    },
    {
        "id": "medium",
        "name": "Whisper Medium (Multilingual)",
        "category": "whisper",
        "category_name": "OpenAI Whisper 공식 라인업",
        "hf_id": "Systran/faster-whisper-medium",
        "size_mb": 1500,
        "vram_mb": 2600,
        "cpu_usable": False,
        "cpu_tag": "GPU 권장 (CPU 지연)",
        "desc": "고품질 다국어(한국어 포함) 전사 (권장 VRAM 4GB+ · GPU 권장)"
    },
    {
        "id": "large-v2",
        "name": "Whisper Large-v2",
        "category": "whisper",
        "category_name": "OpenAI Whisper 공식 라인업",
        "hf_id": "Systran/faster-whisper-large-v2",
        "size_mb": 3100,
        "vram_mb": 4500,
        "cpu_usable": False,
        "cpu_tag": "GPU 전용 (지연 누적)",
        "desc": "검증된 대규모 다국어 플래그십 (CUDA GPU 필수)"
    },
    {
        "id": "large-v3",
        "name": "Whisper Large-v3",
        "category": "whisper",
        "category_name": "OpenAI Whisper 공식 라인업",
        "hf_id": "Systran/faster-whisper-large-v3",
        "size_mb": 3100,
        "vram_mb": 4500,
        "cpu_usable": False,
        "cpu_tag": "GPU 전용 (지연 누적)",
        "desc": "최고의 음성 인식 정확도 (한국어/다국어 · CUDA GPU 필수)"
    },
    {
        "id": "large-v3-turbo",
        "name": "Whisper Large-v3 Turbo",
        "category": "whisper",
        "category_name": "OpenAI Whisper 공식 라인업",
        "hf_id": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "size_mb": 1600,
        "vram_mb": 2500,
        "cpu_usable": False,
        "cpu_tag": "GPU 권장 (고사양 최적)",
        "desc": "최신 공식 Turbo 8배 가속 모델 (CUDA GPU 권장)"
    },

    # ─── 증류(Distilled) 모델 라인업 ───
    {
        "id": "distil-small.en",
        "name": "Distil-Whisper Small (English)",
        "category": "distil",
        "category_name": "증류(Distilled) 모델 라인업",
        "hf_id": "Systran/faster-distil-whisper-small.en",
        "size_mb": 320,
        "vram_mb": 800,
        "cpu_usable": True,
        "cpu_tag": "CPU 쾌적 (기본내장)",
        "desc": "★ 기본 내장 번들 모델 · 5배 가속 초경량 증류 모델 (CPU 최적화)"
    },
    {
        "id": "distil-medium.en",
        "name": "Distil-Whisper Medium (English)",
        "category": "distil",
        "category_name": "증류(Distilled) 모델 라인업",
        "hf_id": "Systran/faster-distil-whisper-medium.en",
        "size_mb": 780,
        "vram_mb": 1500,
        "cpu_usable": True,
        "cpu_tag": "CPU 원활",
        "desc": "고속 중간 크기 증류 모델 (CPU 원활 / 지연시간 단축)"
    },
    {
        "id": "distil-large-v2",
        "name": "Distil-Whisper Large-v2",
        "category": "distil",
        "category_name": "증류(Distilled) 모델 라인업",
        "hf_id": "Systran/faster-distil-whisper-large-v2",
        "size_mb": 1500,
        "vram_mb": 2000,
        "cpu_usable": False,
        "cpu_tag": "GPU 권장 (지연 누적)",
        "desc": "대규모 영어 데이터 증류 모델 (CUDA GPU 권장)"
    },
    {
        "id": "distil-large-v3",
        "name": "Distil-Whisper Large-v3",
        "category": "distil",
        "category_name": "증류(Distilled) 모델 라인업",
        "hf_id": "Systran/faster-distil-whisper-large-v3",
        "size_mb": 1500,
        "vram_mb": 2000,
        "cpu_usable": False,
        "cpu_tag": "GPU 권장 (지연 누적)",
        "desc": "지연시간을 50% 단축한 고속 대형 증류 모델 (CUDA GPU 권장)"
    },
    {
        "id": "distil-large-v3.5",
        "name": "Distil-Whisper Large-v3.5",
        "category": "distil",
        "category_name": "증류(Distilled) 모델 라인업",
        "hf_id": "distil-whisper/distil-large-v3.5-ct2",
        "size_mb": 1550,
        "vram_mb": 2000,
        "cpu_usable": False,
        "cpu_tag": "GPU 권장 (지연 누적)",
        "desc": "최신 고정밀 증류 모델 (영어 전용 · CUDA GPU 권장)"
    },
]

AVAILABLE_GROQ_STT_MODELS = [
    {
        "id": "whisper-large-v3-turbo",
        "name": "Whisper Large-v3 Turbo (Groq LPU)",
        "desc": "Groq LPU 초고속 전사 (한국어/다국어 지원, $0.04/h)",
        "speed": "약 0.04초 (극초저지연)",
    },
    {
        "id": "whisper-large-v3",
        "name": "Whisper Large-v3 (Groq LPU)",
        "desc": "Groq LPU 고정밀 전사 (한국어/다국어 지원, $0.111/h)",
        "speed": "약 0.10초 (고정밀)",
    },
]

AVAILABLE_DEEPGRAM_STT_MODELS = [
    {
        "id": "nova-3",
        "name": "Nova-3 (Deepgram 최신)",
        "desc": "Deepgram 차세대 플래그십 (최고 정확도 · 0.15s 초저지연)",
        "speed": "약 0.15초 (최고 품질)",
    },
    {
        "id": "nova-2",
        "name": "Nova-2 (Deepgram 고정밀)",
        "desc": "검증된 고정밀 글로벌 음향 모델",
        "speed": "약 0.20초",
    },
    {
        "id": "nova-2-general",
        "name": "Nova-2 General",
        "desc": "다양한 억양 및 소음 환경 최적화",
        "speed": "약 0.20초",
    },
]


def get_bundled_hub_dir() -> Optional[str]:
    """프로그램 설치 패키지에 내장 번들된 모델 허브 폴더 반환 (우선 탐색용)"""
    import sys
    candidates = []
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(app_dir, "models", "huggingface", "hub"))
        candidates.append(os.path.join(app_dir, "_internal", "models", "huggingface", "hub"))
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "models", "huggingface", "hub"))
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates.append(os.path.join(app_dir, "models", "huggingface", "hub"))

    for c in candidates:
        if os.path.isdir(c):
            return c
    return None



def get_hf_hub_cache_dir() -> str:
    """HuggingFace Hub 캐시 기본 경로 반환 (지정 폴더 및 환경변수/기본 캐시 이중 감지)"""
    # 1. 설정 파일(config.json)의 custom_model_dir 하위 hub 우선 검사
    try:
        from .llm_model_manager import get_custom_model_dir
        c_dir = get_custom_model_dir()
        if c_dir and os.path.isdir(c_dir):
            p = os.path.join(c_dir, "huggingface", "hub")
            os.makedirs(p, exist_ok=True)
            return p
    except Exception:
        pass

    # 2. D:\AI_Models\huggingface\hub 기본 검사
    custom_d = r"D:\AI_Models\huggingface\hub"
    if os.path.exists(custom_d):
        return custom_d

    # 3. HF_HUB_CACHE 환경변수
    if os.environ.get("HF_HUB_CACHE") and os.path.exists(os.environ.get("HF_HUB_CACHE")):
        return os.environ.get("HF_HUB_CACHE")

    # 4. HF_HOME 환경변수
    if os.environ.get("HF_HOME"):
        hf_home_hub = os.path.join(os.environ.get("HF_HOME"), "hub")
        if os.path.exists(hf_home_hub):
            return hf_home_hub

    # 5. 기본 폴백 (~/.cache/huggingface/hub)
    default_dir = os.path.expanduser("~/.cache/huggingface/hub")
    return default_dir


class STTDownloadSignals(QObject):
    progress_signal = pyqtSignal(str, int, str)   # model_id, percent (0-100), status_msg
    finished_signal = pyqtSignal(str, bool, str)  # model_id, success, msg


class STTDownloadWorker(threading.Thread):
    """비동기 STT 모델 다운로드 스레드 (순수 Python 데몬 스레드)"""
    def __init__(self, model_info: dict, parent=None):
        super().__init__(daemon=True, name="STTDownloadWorker")
        self.signals = STTDownloadSignals()
        self.progress_signal = self.signals.progress_signal
        self.finished_signal = self.signals.finished_signal

        self.model_info = model_info
        self._is_cancelled = False

    def isRunning(self):
        return self.is_alive()

    def wait(self, timeout_ms=None):
        if self.is_alive() and self is not threading.current_thread():
            self.join(timeout=timeout_ms / 1000.0 if timeout_ms else None)

    def cancel(self):
        self._is_cancelled = True
        try:
            from huggingface_hub.utils._xet import abort_xet_session
            abort_xet_session()
        except Exception:
            pass

    def stop(self):
        self.cancel()

    def run(self):
        m_id = self.model_info["id"]
        hf_id = self.model_info["hf_id"]
        STTModelManager.register_worker(m_id, self)
        prep_msg = tr("model_download_preparing", repo=hf_id)
        STTModelManager.set_last_progress(m_id, 0, prep_msg)
        self.progress_signal.emit(m_id, 0, prep_msg)

        output_dir = get_hf_hub_cache_dir()
        total_expected_mb = float(self.model_info.get("size_mb", 500))
        total_expected_bytes = int(total_expected_mb * 1024 * 1024)

        worker_self = self
        shared_state = {
            "total_bytes": total_expected_bytes,
            "last_time": time.time(),
            "last_bytes": 0,
            "last_pct": -1,
            "max_pct": 0,
        }

        try:
            from tqdm.auto import tqdm
            import huggingface_hub

            class STTProgressTqdm(tqdm):
                def __init__(self, *args, **kwargs):
                    kwargs.pop("name", None)
                    super().__init__(*args, **kwargs)

                def update(self, n=1):
                    super().update(n)
                    if worker_self._is_cancelled:
                        try:
                            from huggingface_hub.utils._xet import abort_xet_session
                            abort_xet_session()
                        except Exception:
                            pass
                        return

                    if getattr(self, "unit", "") == "B":
                        if self.total and self.total > shared_state["total_bytes"] * 0.3:
                            shared_state["total_bytes"] = self.total

                        desc_lower = (getattr(self, "desc", "") or "").lower()
                        is_download_bar = "download" in desc_lower
                        is_reconstruct_bar = "reconstruct" in desc_lower

                        if is_download_bar or (is_reconstruct_bar and shared_state["last_bytes"] == 0):
                            cur_bytes = self.n
                            tot_bytes = shared_state["total_bytes"]
                            now = time.time()
                            elapsed = now - shared_state["last_time"]

                            raw_pct = int((cur_bytes / tot_bytes) * 100) if tot_bytes > 0 else 0
                            pct = max(shared_state["max_pct"], min(99, raw_pct))
                            shared_state["max_pct"] = pct

                            if pct != shared_state["last_pct"] or elapsed >= 0.25:
                                speed_str = ""
                                if elapsed > 0 and cur_bytes >= shared_state["last_bytes"]:
                                    speed = (cur_bytes - shared_state["last_bytes"]) / elapsed
                                    speed_mb = speed / (1024 * 1024)
                                    speed_str = f" · {speed_mb:.1f} MB/s"
                                    shared_state["last_bytes"] = cur_bytes
                                    shared_state["last_time"] = now

                                cur_mb = cur_bytes / (1024 * 1024)
                                tot_mb = tot_bytes / (1024 * 1024)
                                if tot_mb >= 1024:
                                    size_str = f"{cur_mb / 1024:.2f} GB / {tot_mb / 1024:.2f} GB"
                                else:
                                    size_str = f"{cur_mb:.1f} MB / {tot_mb:.1f} MB"

                                msg = tr("model_download_weights", size=size_str, pct=pct, speed=speed_str)
                                shared_state["last_pct"] = pct
                                STTModelManager.set_last_progress(m_id, pct, msg)
                                worker_self.progress_signal.emit(m_id, pct, msg)

            allow_patterns = [
                "config.json",
                "preprocessor_config.json",
                "model.bin*",
                "tokenizer.json",
                "vocabulary.*",
            ]

            if self._is_cancelled:
                STTModelManager.delete_model(m_id)
                self.finished_signal.emit(m_id, False, tr("model_download_cancelled"))
                return

            model_path = huggingface_hub.snapshot_download(
                repo_id=hf_id,
                cache_dir=output_dir,
                allow_patterns=allow_patterns,
                tqdm_class=STTProgressTqdm
            )

            if self._is_cancelled:
                STTModelManager.delete_model(m_id)
                self.finished_signal.emit(m_id, False, tr("model_download_cancelled"))
                return

            if model_path and os.path.isdir(model_path):
                STTModelManager.heal_snapshot_symlinks(model_path)

            if self._is_cancelled:
                STTModelManager.delete_model(m_id)
                self.finished_signal.emit(m_id, False, tr("model_download_cancelled"))
                return

            self.progress_signal.emit(m_id, 100, tr("model_download_verified"))
            self.finished_signal.emit(m_id, True, tr("model_install_success"))
        except (InterruptedError, RuntimeError) as e:
            if self._is_cancelled or "cancel" in str(e).lower():
                STTModelManager.delete_model(m_id)
                self.finished_signal.emit(m_id, False, tr("model_download_cancelled"))
            else:
                self.finished_signal.emit(m_id, False, str(e))
        except Exception as e:
            if self._is_cancelled or "cancel" in str(e).lower():
                STTModelManager.delete_model(m_id)
                self.finished_signal.emit(m_id, False, tr("model_download_cancelled"))
            else:
                self.finished_signal.emit(m_id, False, str(e))
        finally:
            STTModelManager.unregister_worker(m_id)


class STTModelManager:
    """STT 모델 탐색, 다운로드 상태 조회 및 캐시 관리 클래스"""

    _active_workers: Dict[str, Any] = {}
    _last_progress: Dict[str, Tuple[int, str]] = {}

    @classmethod
    def get_active_worker(cls, model_id: str) -> Optional[Any]:
        """현재 백그라운드에서 다운로드 중인 STTWorker 인스턴스 반환"""
        w = cls._active_workers.get(model_id)
        if w and w.is_alive():
            return w
        return None

    @classmethod
    def register_worker(cls, model_id: str, worker: Any):
        """다운로드 시작 시 활성 워커 등록"""
        cls._active_workers[model_id] = worker

    @classmethod
    def unregister_worker(cls, model_id: str):
        """다운로드 종료 시 활성 워커 해제"""
        cls._active_workers.pop(model_id, None)
        cls._last_progress.pop(model_id, None)

    @classmethod
    def set_last_progress(cls, model_id: str, pct: int, msg: str):
        """실시간 진행률 캐시 갱신 (창 재오픈 시 즉각 복원용)"""
        cls._last_progress[model_id] = (pct, msg)

    @classmethod
    def get_last_progress(cls, model_id: str) -> Tuple[int, str]:
        """마지막 수신된 진행률 (percent, msg) 반환"""
        return cls._last_progress.get(model_id, (0, tr("download_in_progress")))

    @classmethod
    def heal_snapshot_symlinks(cls, snapshot_dir: str) -> int:
        """
        Windows 환경에서 HuggingFace Hub의 상대/절대 심볼릭 링크를
        동일 볼륨 내 HardLink(용량 소모 0B, 즉각 처리) 또는 실제 파일 복사본으로 자동 변환.
        CTranslate2가 CreateFile/fopen 시 'Unable to open file model.bin'을 내뿜는 문제를 원천 차단.
        """
        import os
        import shutil
        from pathlib import Path

        snap_p = Path(snapshot_dir)
        if not snap_p.is_dir():
            return 0

        healed_count = 0
        try:
            for item in list(snap_p.iterdir()):
                try:
                    if item.is_symlink():
                        target = item.resolve()
                        if not target.exists():
                            continue

                        temp_link = snap_p / f".tmp_{item.name}"
                        if temp_link.exists():
                            try:
                                temp_link.unlink()
                            except Exception:
                                pass

                        success = False
                        # 1순위: 하드링크 시도 (동일 볼륨 디스크 용량 0B, 0.001초 완료)
                        try:
                            os.link(target, temp_link)
                            item.unlink()
                            temp_link.rename(item)
                            success = True
                        except Exception:
                            # 2순위: 하드링크 불가 시 복사본 생성
                            try:
                                shutil.copy2(target, temp_link)
                                item.unlink()
                                temp_link.rename(item)
                                success = True
                            except Exception:
                                pass

                        if success:
                            healed_count += 1
                except Exception:
                    pass
        except Exception:
            pass

        if healed_count > 0:
            logger.info(f"심볼릭 링크 {healed_count}개를 하드링크/실제 파일로 안전 변환(Auto-Healed) 완료: {snap_p.name}")
        return healed_count

    @staticmethod
    def get_available_models() -> List[Dict]:
        return AVAILABLE_STT_MODELS

    @classmethod
    def is_cpu_usable(cls, model_id: str) -> bool:
        """해당 모델이 CPU 모드에서 실시간 스트리밍 처리가 가능한지(CPU 원활 사용 가능 이하) 여부 확인"""
        for m in AVAILABLE_STT_MODELS:
            if m["id"] == model_id or m.get("hf_id") == model_id:
                return m.get("cpu_usable", False)
        return False

    @classmethod
    def get_models_for_device(cls, device: str = "cpu") -> List[Dict]:
        """디바이스(cpu/cuda)에 적합한 STT 모델 목록 반환"""
        if str(device).lower() == "cpu":
            return [m for m in AVAILABLE_STT_MODELS if m.get("cpu_usable", False)]
        return AVAILABLE_STT_MODELS

    @classmethod
    def _is_valid_model_folder(cls, folder: str) -> bool:
        """폴더 내에 유효한 모델 가중치(snapshots/<hash>/model.bin 또는 model.bin 등)가 존재하는지 무결성 검사"""
        if not folder or not os.path.isdir(folder):
            return False
        snap_dir = os.path.join(folder, "snapshots")
        try:
            if os.path.isdir(snap_dir) and os.listdir(snap_dir):
                for snap_name in sorted(os.listdir(snap_dir), reverse=True):
                    chosen_snap = os.path.join(snap_dir, snap_name)
                    if os.path.isdir(chosen_snap):
                        m_bin = os.path.join(chosen_snap, "model.bin")
                        if os.path.isfile(m_bin):
                            try:
                                if os.path.getsize(m_bin) > 10 * 1024 * 1024:
                                    return True
                            except OSError:
                                pass
                        try:
                            if any((f.endswith((".bin", ".onnx")) and os.path.getsize(os.path.join(chosen_snap, f)) > 10 * 1024 * 1024) for f in os.listdir(chosen_snap)):
                                return True
                        except Exception:
                            pass
        except Exception:
            pass

        m_bin_direct = os.path.join(folder, "model.bin")
        if os.path.isfile(m_bin_direct):
            try:
                if os.path.getsize(m_bin_direct) > 10 * 1024 * 1024:
                    return True
            except OSError:
                pass
        return False

    @classmethod
    def get_search_hub_dirs(cls) -> List[str]:
        """STT 모델 탐색 대상 허브 폴더 후보 목록을 우선순위 순으로 반환"""
        dirs = []
        # 0. 프로그램 번들 허브 폴더
        bundled = get_bundled_hub_dir()
        if bundled and bundled not in dirs:
            dirs.append(bundled)

        # 1. custom_model_dir 하위 hub
        try:
            from .llm_model_manager import get_custom_model_dir
            c_dir = get_custom_model_dir()
            if c_dir:
                p = os.path.join(c_dir, "huggingface", "hub")
                if os.path.isdir(p) and p not in dirs:
                    dirs.append(p)
        except Exception:
            pass

        # 2. D:\AI_Models\huggingface\hub
        custom_d = r"D:\AI_Models\huggingface\hub"
        if os.path.isdir(custom_d) and custom_d not in dirs:
            dirs.append(custom_d)

        # 3. HF_HUB_CACHE 환경변수
        env_hub = os.environ.get("HF_HUB_CACHE")
        if env_hub and os.path.isdir(env_hub) and env_hub not in dirs:
            dirs.append(env_hub)

        # 4. HF_HOME 환경변수
        env_home = os.environ.get("HF_HOME")
        if env_home:
            p_home = os.path.join(env_home, "hub")
            if os.path.isdir(p_home) and p_home not in dirs:
                dirs.append(p_home)

        # 5. ~/.cache/huggingface/hub 기본 경로
        default_dir = os.path.expanduser("~/.cache/huggingface/hub")
        if os.path.isdir(default_dir) and default_dir not in dirs:
            dirs.append(default_dir)

        return dirs

    @classmethod
    def get_model_folder_path(cls, hf_id: str) -> Optional[str]:
        folder_name = "models--" + hf_id.replace("/", "--")
        candidate_dirs = cls.get_search_hub_dirs()

        # 1차 탐색: 실제 유효한 모델 가중치가 존재하는 폴더 우선 반환
        for hub_dir in candidate_dirs:
            full_path = os.path.join(hub_dir, folder_name)
            if cls._is_valid_model_folder(full_path):
                return full_path

        # 2차 탐색: 가중치가 아직 다운로드 중이거나 비어있더라도 디렉터리가 존재하는 경우 폴백
        for hub_dir in candidate_dirs:
            full_path = os.path.join(hub_dir, folder_name)
            if os.path.isdir(full_path):
                return full_path

        return None

    @classmethod
    def is_bundled_model(cls, model_id: str) -> bool:
        """해당 모델이 앱 설치 패키지에 기본 내장 번들된 모델인지 확인"""
        target = None
        for m in AVAILABLE_STT_MODELS:
            if m["id"] == model_id or m.get("hf_id") == model_id:
                target = m
                break
        if not target:
            return False

        bundled_hub = get_bundled_hub_dir()
        if not bundled_hub:
            return False

        folder_name = "models--" + target["hf_id"].replace("/", "--")
        folder = os.path.join(bundled_hub, folder_name)
        if not os.path.isdir(folder):
            return False

        snapshots_dir = os.path.join(folder, "snapshots")
        return bool(os.path.isdir(snapshots_dir) and os.listdir(snapshots_dir))

    @classmethod
    def is_model_installed(cls, model_id: str) -> bool:
        """특정 STT 모델이 로컬 디스크에 완전히 설치되어 있는지 여부 확인"""
        target = None
        for m in AVAILABLE_STT_MODELS:
            if m["id"] == model_id or m.get("hf_id") == model_id:
                target = m
                break
        if not target:
            return False

        folder = cls.get_model_folder_path(target["hf_id"])
        if not folder:
            return False

        return cls._is_valid_model_folder(folder)

    @classmethod
    def get_model_disk_size_mb(cls, model_id: str) -> float:
        """설치된 모델의 실제 디스크 점유 크기(MB) 반환"""
        for m in AVAILABLE_STT_MODELS:
            if m["id"] == model_id or m.get("hf_id") == model_id:
                folder = cls.get_model_folder_path(m["hf_id"])
                if folder and os.path.exists(folder):
                    total_bytes = 0
                    for root, _, files in os.walk(folder):
                        for f in files:
                            fp = os.path.join(root, f)
                            try:
                                total_bytes += os.path.getsize(fp)
                            except OSError:
                                pass
                    return round(total_bytes / (1024 * 1024), 1)
        return 0.0

    @classmethod
    def delete_model(cls, model_id: str) -> bool:
        """특정 모델 캐시 폴더 완전 삭제 (기본 내장 번들 모델은 삭제 보호)"""
        if cls.is_bundled_model(model_id):
            print(f"[STTModelManager] '{model_id}' 모델은 프로그램 기본 내장 번들이므로 삭제할 수 없습니다.")
            return False

        target = None
        for m in AVAILABLE_STT_MODELS:
            if m["id"] == model_id or m.get("hf_id") == model_id:
                target = m
                break
        if not target:
            return False

        folder_name = "models--" + target["hf_id"].replace("/", "--")
        bundled_hub = get_bundled_hub_dir()
        deleted_any = False

        for hub_dir in cls.get_search_hub_dirs():
            if bundled_hub and os.path.normpath(hub_dir) == os.path.normpath(bundled_hub):
                continue
            full_path = os.path.join(hub_dir, folder_name)
            if os.path.exists(full_path):
                try:
                    shutil.rmtree(full_path, ignore_errors=True)
                    deleted_any = True
                except Exception as e:
                    print(f"[STTModelManager] 모델 캐시 삭제 실패 ({full_path}): {e}")

        return deleted_any or (not cls.is_model_installed(model_id))

    @classmethod
    def is_multilingual_model(cls, model_id: str, provider: str = "local") -> bool:
        """해당 STT 모델이 다국어(99개 언어, 일본어, 중국어, 한국어 등)를 지원하는지 판별"""
        if provider in ("groq", "deepgram"):
            return True
        if not model_id:
            return False
        mid = str(model_id).lower()
        if mid.endswith(".en"):
            return False
        if mid in ("distil-large-v2", "distil-large-v3", "distil-large-v3.5"):
            return False
        return True
