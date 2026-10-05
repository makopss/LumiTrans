import os
import re
import json
import time
import requests
import threading
from typing import List, Dict, Optional, Tuple, Any
from PyQt6.QtCore import pyqtSignal, QObject
from src.i18n import tr

OLLAMA_API_BASE = "http://127.0.0.1:11434"
_CUDA_ARCH_CACHE = {}


def parse_cuda_arch_tokens(blob: bytes):
    """ggml-cuda.dll에 박혀 있는 sm_XX / compute_XX 토큰을 (major, minor)로 해석한다."""
    found = set()
    if not blob:
        return found
    for token in (b"sm_", b"compute_"):
        start = 0
        while True:
            index = blob.find(token, start)
            if index < 0:
                break
            cursor = index + len(token)
            digits = bytearray()
            while cursor < len(blob) and 48 <= blob[cursor] <= 57 and len(digits) < 3:
                digits.append(blob[cursor])
                cursor += 1
            if len(digits) >= 2 and (cursor >= len(blob) or not (48 <= blob[cursor] <= 57)):
                number = int(digits)
                found.add((number // 10, number % 10))
            start = index + len(token)
    return found


def parse_ggml_archs_literal(blob: bytes):
    """ggml-cuda.dll 의 system_info 용 "ARCHS" 문자열(예: 600,610,...,890,900)을 (major, minor)로 해석한다.
    fatbin 안의 sm_XX 토큰은 일부 아키텍처만 문자열로 남아 있어(예: sm_90 만 검출) 이 목록을 우선한다."""
    index = blob.find(b"ARCHS\x00")
    if index < 0:
        return set()
    match = re.search(rb"[0-9]{2,4}(?:,[0-9]{2,4})*", blob[index + 6:index + 6 + 128])
    if not match:
        return set()
    found = set()
    for token in match.group(0).split(b","):
        value = int(token)
        if 300 <= value <= 1500:
            found.add((value // 100, (value // 10) % 10))
    return found


def scan_cuda_binary_architectures(dll_path: str):
    """대용량 DLL을 통째로 문자열로 바꾸지 않고 ARCHS 목록과 sm_/compute_ 주변만 읽는다."""
    try:
        stat = os.stat(dll_path)
    except OSError:
        return set()
    key = (os.path.abspath(dll_path), stat.st_size, getattr(stat, "st_mtime_ns", stat.st_mtime))
    cached = _CUDA_ARCH_CACHE.get(key)
    if cached is not None:
        return set(cached)

    archs = set()
    listed = set()
    overlap = b""
    try:
        with open(dll_path, "rb") as handle:
            while True:
                chunk = handle.read(4 * 1024 * 1024)
                if not chunk:
                    break
                window = overlap + chunk
                archs.update(parse_cuda_arch_tokens(window))
                if not listed:
                    listed = parse_ggml_archs_literal(window)
                overlap = chunk[-160:]
    except OSError:
        return set()
    result = listed or archs
    _CUDA_ARCH_CACHE[key] = frozenset(result)
    return result


def format_cuda_arch(capability):
    major, minor = capability
    return f"sm_{major}{minor}"


def decide_n_gpu_layers(device, cuda_binary, supports_offload, capability, architectures):
    """GPU 오프로딩 레이어 수 결정.

    NVIDIA 드라이버는 PTX JIT 컴파일러를 통해 상위 아키텍처(예: Blackwell 연산 능력 12.0 등)에서도
    하위 PTX(sm_90 등) 커널을 실시간 최적화하여 100% 정상 구동합니다.
    """
    if str(device or "").lower() == "cpu" or not cuda_binary or not supports_offload:
        return 0, ""
    if capability is None or not architectures:
        return -1, ""
    if capability in architectures:
        return -1, ""
    min_arch = min(architectures)
    if capability >= min_arch:
        return -1, ""
    supported = ", ".join(format_cuda_arch(item) for item in sorted(architectures))
    cap_label = f"{capability[0]}.{capability[1]}"
    return 0, (
        f"GPU 연산 능력 {cap_label} 용 CUDA 커널이 없습니다 (포함된 아키텍처: {supported}). "
        "호환성을 위해 CPU로 로드합니다."
    )

RECOMMENDED_OLLAMA_MODELS = [
    {
        "tag": "translategemma:4b",
        "name": "Google TranslateGemma (4B)",
        "size_mb": 3300,
        "vram_mb": 3800,
        "desc": "로컬 최고 품질 | 원작 뉘앙스/문맥 번역 종결자"
    },
    {
        "tag": "exaone3.5:2.4b",
        "name": "LG EXAONE 3.5 (2.4B)",
        "size_mb": 1600,
        "vram_mb": 2200,
        "desc": "로컬 균형형 | LG 한국어 특화 자연스러운 문체"
    },
    {
        "tag": "exaone3.5:7.8b",
        "name": "LG EXAONE 3.5 (7.8B)",
        "size_mb": 5100,
        "vram_mb": 5800,
        "desc": "로컬 최고 지능 | LG 국산 7.8B 고품질 심층 번역 및 문맥 추론"
    },
    {
        "tag": "tencent/hy-mt2:1.8b",
        "name": "Tencent Hy-MT2 (1.8B)",
        "size_mb": 1130,
        "vram_mb": 1400,
        "desc": "초경량 번역 특화 | VRAM 1.4GB 텐센트 차세대 IFMT 전문 번역"
    },
]

RECOMMENDED_GGUF_MODELS = [
    {
        "id": "translategemma-4b",
        "name": "Google TranslateGemma (4B Q4_K_M)",
        "repo_id": "mradermacher/translategemma-4b-it-GGUF",
        "filename": "translategemma-4b-it.Q4_K_M.gguf",
        "size_mb": 2500,
        "vram_mb": 3500,
        "desc": "로컬 최고 품질 | 원작 뉘앙스/문맥 번역 종결자 (GGUF)"
    },
    {
        "id": "exaone-3.5-2.4b",
        "name": "LG EXAONE 3.5 (2.4B Q4_K_M)",
        "repo_id": "LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct-GGUF",
        "filename": "EXAONE-3.5-2.4B-Instruct-Q4_K_M.gguf",
        "size_mb": 1600,
        "vram_mb": 2200,
        "desc": "로컬 균형형 | LG 한국어 특화 자연스러운 문체 (GGUF)"
    },
    {
        "id": "exaone-3.5-7.8b",
        "name": "LG EXAONE 3.5 (7.8B Q4_K_M)",
        "repo_id": "LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF",
        "filename": "EXAONE-3.5-7.8B-Instruct-Q4_K_M.gguf",
        "size_mb": 4550,
        "vram_mb": 5500,
        "desc": "로컬 최고 지능 | LG 국산 7.8B 고품질 심층 번역 (GGUF)"
    },
    {
        "id": "hymt-2-1.8b",
        "name": "Tencent Hy-MT2 (1.8B Q4_K_M)",
        "repo_id": "tencent/Hy-MT2-1.8B-GGUF",
        "filename": "Hy-MT2-1.8B-Q4_K_M.gguf",
        "size_mb": 1130,
        "vram_mb": 1400,
        "desc": "초경량 번역 특화 | 텐센트 공식 GGUF 차세대 IFMT 전문 번역 (GGUF)"
    },
]


class OllamaPullSignals(QObject):
    progress_signal = pyqtSignal(str, int, str)   # tag, percent, status
    finished_signal = pyqtSignal(str, bool, str)  # tag, success, msg


class OllamaPullWorker(threading.Thread):
    """Ollama API 모델 다운로드 스트리밍 스레드 (순수 Python 데몬 스레드)"""
    def __init__(self, model_tag: str, parent=None):
        super().__init__(daemon=True, name="OllamaPullWorker")
        self.signals = OllamaPullSignals()
        self.progress_signal = self.signals.progress_signal
        self.finished_signal = self.signals.finished_signal

        self.model_tag = model_tag
        self._is_cancelled = False
        self._resp = None

    def isRunning(self):
        return self.is_alive()

    def wait(self, timeout_ms=None):
        if self.is_alive() and self is not threading.current_thread():
            self.join(timeout=timeout_ms / 1000.0 if timeout_ms else None)

    def cancel(self):
        self._is_cancelled = True
        try:
            if self._resp:
                self._resp.close()
        except Exception:
            pass

    def stop(self):
        self.cancel()

    def run(self):
        url = f"{OLLAMA_API_BASE}/api/pull"
        LLMModelManager.register_ollama_worker(self.model_tag, self)
        conn_msg = tr("ollama_connecting", tag=self.model_tag)
        LLMModelManager.set_last_ollama_progress(self.model_tag, 0, conn_msg)
        self.progress_signal.emit(self.model_tag, 0, conn_msg)
        try:
            resp = requests.post(url, json={"name": self.model_tag, "stream": True}, stream=True, timeout=10)
            self._resp = resp
            if resp.status_code != 200:
                self.finished_signal.emit(self.model_tag, False, tr("ollama_resp_error", code=resp.status_code))
                return

            max_pct = 0
            for line in resp.iter_lines():
                if self._is_cancelled:
                    self.finished_signal.emit(self.model_tag, False, tr("model_download_cancelled"))
                    return
                if line:
                    try:
                        data = json.loads(line.decode("utf-8"))
                        status = data.get("status", "")
                        completed = data.get("completed", 0)
                        total = data.get("total", 0)
                        if total > 0:
                            calc_pct = int((completed / total) * 100)
                            pct = max(max_pct, min(99, calc_pct))
                            max_pct = pct
                            mb_done = completed / (1024 * 1024)
                            mb_tot = total / (1024 * 1024)
                            msg = f"{status} ({mb_done:.0f}/{mb_tot:.0f} MB, {pct}%)"
                            LLMModelManager.set_last_ollama_progress(self.model_tag, pct, msg)
                            self.progress_signal.emit(self.model_tag, pct, msg)
                        else:
                            LLMModelManager.set_last_ollama_progress(self.model_tag, max_pct, status)
                            self.progress_signal.emit(self.model_tag, max_pct, status)
                    except Exception:
                        pass

            self.progress_signal.emit(self.model_tag, 100, tr("ollama_model_ready"))
            LLMModelManager.get_installed_ollama_models(force_refresh=True)
            self.finished_signal.emit(self.model_tag, True, tr("ollama_installed_success", name=self.model_tag))
        except Exception as e:
            if self._is_cancelled:
                self.finished_signal.emit(self.model_tag, False, tr("model_download_cancelled"))
            else:
                self.finished_signal.emit(self.model_tag, False, tr("ollama_comm_failed", error=str(e)))
        finally:
            LLMModelManager.unregister_ollama_worker(self.model_tag)


def get_custom_model_dir() -> Optional[str]:
    """설정 파일(config.json) 또는 기본 경로에서 지정된 공용 모델 폴더 반환"""
    try:
        from src.config import CONFIG_FILE
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                custom = cfg.get("custom_model_dir")
                if custom and os.path.exists(custom):
                    return custom
    except Exception:
        pass
    if os.path.exists(r"D:\AI_Models"):
        return r"D:\AI_Models"
    return None


class GGUFDownloadSignals(QObject):
    progress_signal = pyqtSignal(str, int, str)   # model_id, percent, status
    finished_signal = pyqtSignal(str, bool, str)  # model_id, success, msg


class GGUFDownloadWorker(threading.Thread):
    """HuggingFace Hub 내장 GGUF 모델 다운로드 스레드 (순수 Python 데몬 스레드)"""
    def __init__(self, model_info: dict, parent=None):
        super().__init__(daemon=True, name="GGUFDownloadWorker")
        self.signals = GGUFDownloadSignals()
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
        repo_id = self.model_info["repo_id"]
        filename = self.model_info["filename"]
        LLMModelManager.register_gguf_worker(m_id, self)
        conn_msg = tr("hf_connecting", filename=filename)
        LLMModelManager.set_last_gguf_progress(m_id, 0, conn_msg)
        self.progress_signal.emit(m_id, 0, conn_msg)

        try:
            import time
            from tqdm.auto import tqdm
            from huggingface_hub import hf_hub_download

            worker_self = self

            class GGUFProgressTqdm(tqdm):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self._last_time = time.time()
                    self._last_bytes = self.n
                    self._last_pct = -1
                    self._max_pct = 0

                def update(self, n=1):
                    super().update(n)
                    if worker_self._is_cancelled:
                        try:
                            from huggingface_hub.utils._xet import abort_xet_session
                            abort_xet_session()
                        except Exception:
                            pass
                        return
                    now = time.time()
                    if self.total and self.total > 0:
                        raw_pct = int((self.n / self.total) * 100)
                        pct = max(self._max_pct, min(99, raw_pct))
                        self._max_pct = pct
                        elapsed = now - self._last_time
                        if pct != self._last_pct or elapsed >= 0.25:
                            speed_str = ""
                            if elapsed > 0 and self.n >= self._last_bytes:
                                speed = (self.n - self._last_bytes) / elapsed
                                speed_mb = speed / (1024 * 1024)
                                speed_str = f" · {speed_mb:.1f} MB/s"
                                self._last_time = now
                                self._last_bytes = self.n

                            cur_mb = self.n / (1024 * 1024)
                            total_mb = self.total / (1024 * 1024)
                            if total_mb >= 1024:
                                size_str = f"{cur_mb / 1024:.2f} GB / {total_mb / 1024:.2f} GB"
                            else:
                                size_str = f"{cur_mb:.1f} MB / {total_mb:.1f} MB"

                            msg = f"다운로드 중... {size_str} ({pct}%){speed_str}"
                            self._last_pct = pct
                            LLMModelManager.set_last_gguf_progress(m_id, pct, msg)
                            worker_self.progress_signal.emit(m_id, pct, msg)

            c_dir = get_custom_model_dir()
            cache_dir = os.path.join(c_dir, "huggingface") if c_dir else None
            if self._is_cancelled:
                LLMModelManager.delete_gguf_model(self.model_info)
                self.finished_signal.emit(m_id, False, "다운로드가 취소되었습니다.")
                return
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                cache_dir=cache_dir,
                tqdm_class=GGUFProgressTqdm
            )

            # 다운로드 도중 취소된 경우 공유 폴더에 복사/등록하지 않고 즉시 파일 삭제 정리
            if self._is_cancelled:
                LLMModelManager.delete_gguf_model(self.model_info)
                self.finished_signal.emit(m_id, False, "다운로드가 취소되었습니다.")
                return

            real_path = os.path.realpath(path)

            # 지정 폴더(D:\AI_Models\GGUF)가 존재하면 타 프로그램 공유를 위해 하드링크/복사 배치
            if c_dir and os.path.exists(os.path.join(c_dir, "GGUF")):
                target_shared = os.path.join(c_dir, "GGUF", filename)
                if os.path.lexists(target_shared) and not os.path.exists(target_shared):
                    try:
                        os.remove(target_shared)
                    except Exception:
                        pass
                if not os.path.exists(target_shared):
                    try:
                        os.link(real_path, target_shared)
                    except Exception:
                        try:
                            import shutil
                            shutil.copyfile(real_path, target_shared)
                        except Exception:
                            pass

            if self._is_cancelled:
                LLMModelManager.delete_gguf_model(self.model_info)
                self.finished_signal.emit(m_id, False, tr("model_download_cancelled"))
                return

            self.progress_signal.emit(m_id, 100, tr("model_download_done"))
            self.finished_signal.emit(m_id, True, tr("gguf_download_done", path=path))
        except (InterruptedError, RuntimeError) as e:
            if self._is_cancelled or "cancel" in str(e).lower():
                LLMModelManager.delete_gguf_model(self.model_info)
                self.finished_signal.emit(m_id, False, tr("model_download_cancelled"))
            else:
                self.finished_signal.emit(m_id, False, str(e))
        except Exception as e:
            if self._is_cancelled or "cancel" in str(e).lower():
                LLMModelManager.delete_gguf_model(self.model_info)
                self.finished_signal.emit(m_id, False, tr("model_download_cancelled"))
            else:
                self.finished_signal.emit(m_id, False, str(e))
        finally:
            LLMModelManager.unregister_gguf_worker(m_id)


class CUDAPackDownloadSignals(QObject):
    progress_signal = pyqtSignal(int, str)      # percent, status
    finished_signal = pyqtSignal(bool, str)     # success, message


class CUDAPackDownloadWorker(threading.Thread):
    """NVIDIA CUDA/cuBLAS 가속 라이브러리(STT cuBLAS + LLM ggml-cuda) 온디맨드 다운로드 스레드"""
    CUBLAS_WHL_URL = "https://files.pythonhosted.org/packages/e2/2a/4f27ca96232e8b5269074a72e03b4e0d43aa68c9b965058b1684d07c6ff8/nvidia_cublas_cu12-12.4.5.8-py3-none-win_amd64.whl"
    CUDART_WHL_URL = "https://files.pythonhosted.org/packages/59/df/e7c3a360be4f7b93cee39271b792669baeb3846c58a4df6dfcf187a7ffab/nvidia_cuda_runtime_cu12-12.9.79-py3-none-win_amd64.whl"
    # CUDA 13 휠의 llama.dll 과 ggml-cuda.dll 은 한 세트다.
    # ggml-cuda.dll 만 끼우면 GPU 오프로드가 꺼지고, 맞지 않는 DLL 은 0xC000001D 로 죽는다.
    LLAMA_WHL_URL = "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.35-cu130/llama_cpp_python-0.3.35-py3-none-win_amd64.whl"
    CUBLAS13_WHL_URL = "https://files.pythonhosted.org/packages/a3/df/f1246959833e2c437db8be3e5b477f66b87f8817821ed40de6c7561c9a36/nvidia_cublas-13.8.0.4-py3-none-win_amd64.whl"
    CUDART13_WHL_URL = "https://files.pythonhosted.org/packages/86/00/d5436004268f049214193659ebc36550b5ef3925c3d13b4cc980e13be6f5/nvidia_cuda_runtime-13.4.92-py3-none-win_amd64.whl"

    def __init__(self, parent=None):
        super().__init__(daemon=True, name="CUDAPackDownloadWorker")
        self.signals = CUDAPackDownloadSignals()
        self.progress_signal = self.signals.progress_signal
        self.finished_signal = self.signals.finished_signal
        self._is_cancelled = False

    def isRunning(self):
        return self.is_alive()

    def wait(self, timeout_ms=None):
        if self.is_alive() and self is not threading.current_thread():
            self.join(timeout=timeout_ms / 1000.0 if timeout_ms else None)

    def cancel(self):
        self._is_cancelled = True

    def stop(self):
        self._is_cancelled = True

    @staticmethod
    def _finalize_llama_pack(staging: str, final: str, pack_id: str):
        """다 받은 임시 폴더를 최종 폴더로 바꾼다. 로드 중인 DLL 을 덮어쓰지 않도록 항상 새 폴더로 교체한다."""
        import shutil
        from src.cuda_utils import get_default_llama_lib_dir
        # 공식 CUDA wheel 의 ggml-cpu.dll 은 AVX-512 전용이라 앱에 내장된 같은 버전 CPU 전용(AVX2) 판으로 바꾼다.
        cpu_ggml = os.path.join(get_default_llama_lib_dir() or "", "ggml-cpu.dll")
        if not os.path.isfile(cpu_ggml):
            raise RuntimeError(f"앱에 내장된 CPU 전용 ggml-cpu.dll 을 찾지 못했습니다: {cpu_ggml}")
        shutil.copy2(cpu_ggml, os.path.join(staging, "ggml-cpu.dll"))
        with open(os.path.join(staging, "wise_cuda_pack.txt"), "w", encoding="utf-8") as handle:
            handle.write(pack_id)
        if os.path.isdir(final):
            shutil.rmtree(final)
        os.replace(staging, final)
        # 이전 버전 팩 폴더 정리 (현재 프로세스가 쓰는 중이면 다음 실행 때 다시 시도)
        parent = os.path.dirname(final)
        for name in os.listdir(parent):
            old = os.path.join(parent, name)
            if old != final and os.path.isdir(old):
                shutil.rmtree(old, ignore_errors=True)

    def _download_and_extract(self, url: str, target_dir: str, dll_patterns: list, label: str,
                              start_pct: int, end_pct: int, path_contains: str = None) -> list:
        """단일 패키지 다운로드 및 지정 DLL 추출 헬퍼 (진행률 start_pct ~ end_pct 분할 반영)"""
        import requests
        import zipfile
        import shutil

        temp_path = os.path.join(target_dir, f"_temp_{int(time.time()*1000)}.whl")
        extracted_files = []
        try:
            status_msg = tr("model_download_prep_label", label=label)
            LLMModelManager.set_last_cuda_progress(start_pct, status_msg)
            self.progress_signal.emit(start_pct, status_msg)

            resp = requests.get(url, stream=True, timeout=30, headers={"User-Agent": "LumiTrans"})
            if resp.status_code != 200:
                raise RuntimeError(f"다운로드 서버 응답 오류 (HTTP {resp.status_code})")

            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB
            pct_span = max(1, end_pct - start_pct - 5)

            with open(temp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if self._is_cancelled:
                        raise RuntimeError("다운로드가 취소되었습니다.")
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            ratio = downloaded / total_size
                            current_pct = int(start_pct + ratio * pct_span)
                            mb_done = downloaded / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024)
                            msg = f"{label} 다운로드 중 ({mb_done:.1f}/{mb_total:.1f} MB, {int(ratio*100)}%)"
                            LLMModelManager.set_last_cuda_progress(current_pct, msg)
                            self.progress_signal.emit(current_pct, msg)

            if self._is_cancelled:
                raise RuntimeError("다운로드가 취소되었습니다.")

            ext_msg = f"{label} 설치 및 무결성 검증 중..."
            ext_pct = end_pct - 2
            LLMModelManager.set_last_cuda_progress(ext_pct, ext_msg)
            self.progress_signal.emit(ext_pct, ext_msg)

            with zipfile.ZipFile(temp_path, "r") as z:
                for item in z.namelist():
                    item_lower = item.lower()
                    item_norm = item.replace("\\", "/").lower()
                    if path_contains and path_contains.lower() not in item_norm:
                        continue
                    for pattern in dll_patterns:
                        if item_lower.endswith(pattern.lower()) and not item_lower.endswith(".lib"):
                            out_name = os.path.basename(item)
                            dst_file = os.path.join(target_dir, out_name)
                            with z.open(item) as src_f, open(dst_file, "wb") as dst_f:
                                shutil.copyfileobj(src_f, dst_f)
                            extracted_files.append(dst_file)

        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

        return extracted_files

    def run(self):
        LLMModelManager.register_cuda_worker(self)
        conn_msg = tr("cuda_pack_connecting")
        LLMModelManager.set_last_cuda_progress(0, conn_msg)
        self.progress_signal.emit(0, conn_msg)

        try:
            import shutil
            from src.cuda_utils import (
                LLAMA_CUDA_PACK_ID,
                get_cuda_target_install_dir,
                get_llama_cuda_pack_dir,
                is_cublas_installed,
                is_ggml_cuda_available,
                is_nvidia_gpu_present,
                llama_cuda_issue,
                find_cuda_dll,
                register_cuda_dll_directories,
            )

            if not is_nvidia_gpu_present():
                self.finished_signal.emit(False, tr("cuda_no_nvidia_error"))
                return

            target_dir = get_cuda_target_install_dir()
            llama_dir = get_llama_cuda_pack_dir()
            llama_staging = llama_dir + ".partial"
            llm_issue = llama_cuda_issue("cu13")

            needs_cublas = not is_cublas_installed()
            needs_cudart = find_cuda_dll("cudart64_12.dll", min_size_mb=0.1) is None
            # Full 내장 CUDA 12 라이브러리를 이미 쓸 수 있으면 CUDA 13 팩은 받지 않는다.
            needs_llama = llm_issue is None and not is_ggml_cuda_available()

            if not any((needs_cublas, needs_cudart, needs_llama)):
                register_cuda_dll_directories()
                done_msg = tr("cuda_already_installed")
                if llm_issue:
                    done_msg += f"\n\n{tr('cuda_llm_cpu_fallback', issue=llm_issue)}"
                self.progress_signal.emit(100, tr("cuda_already_installed_short"))
                self.finished_signal.emit(True, done_msg)
                return

            if needs_llama:
                shutil.rmtree(llama_staging, ignore_errors=True)
                os.makedirs(llama_staging, exist_ok=True)

            # (label, url, patterns, weight, dest, path_contains)
            tasks = []
            if needs_cublas:
                tasks.append((tr("cublas_12_stt"), self.CUBLAS_WHL_URL, ["cublas64_12.dll", "cublasLt64_12.dll"], 20, target_dir, None))
            if needs_cudart:
                tasks.append((tr("cuda_12_runtime"), self.CUDART_WHL_URL, ["cudart64_12.dll"], 5, target_dir, None))
            if needs_llama:
                tasks.append((tr("cublas_13_llm"), self.CUBLAS13_WHL_URL, ["cublas64_13.dll", "cublaslt64_13.dll"], 35, llama_staging, None))
                tasks.append((tr("cuda_13_runtime"), self.CUDART13_WHL_URL, ["cudart64_13.dll"], 5, llama_staging, None))
                tasks.append((tr("local_llm_cuda_lib"), self.LLAMA_WHL_URL, [".dll"], 35, llama_staging, "llama_cpp/lib/"))

            total_weight = sum(t[3] for t in tasks) or 1
            cur_start = 0
            installed_all = []

            for label, url, patterns, weight, dest, path_contains in tasks:
                if self._is_cancelled:
                    raise RuntimeError(tr("model_download_cancelled"))
                step_end = int(cur_start + (weight / total_weight) * 98)
                extracted = self._download_and_extract(
                    url, dest, patterns, label, cur_start, step_end, path_contains=path_contains)
                if path_contains and not extracted:
                    raise RuntimeError(tr("cuda_dll_not_found", label=label))
                installed_all.extend(extracted)
                cur_start = step_end

            if needs_llama:
                self._finalize_llama_pack(llama_staging, llama_dir, LLAMA_CUDA_PACK_ID)

            from src.cuda_utils import register_cuda_dll_directories, preload_cuda_dlls, configure_llama_backend
            register_cuda_dll_directories(force=True)
            preload_cuda_dlls()
            llama_state = configure_llama_backend()

            if llama_state["backend"] == "cuda":
                llm_line = tr("cuda_llm_gpu_next")
            elif llama_state.get("restart_required"):
                llm_line = tr("cuda_llm_restart_req")
            else:
                llm_line = tr("cuda_llm_cpu_fallback", issue=llm_issue or llama_state.get('issue') or 'CUDA check failed')

            self.progress_signal.emit(100, tr("cuda_pack_all_done"))
            self.finished_signal.emit(
                True,
                tr("cuda_pack_installed_msg", dir=target_dir, count=len(installed_all), llm=llm_line)
            )
        except Exception as e:
            try:
                import shutil
                from src.cuda_utils import get_llama_cuda_pack_dir
                shutil.rmtree(get_llama_cuda_pack_dir() + ".partial", ignore_errors=True)
            except Exception:
                pass
            msg = str(e)
            if "취소" in msg:
                self.finished_signal.emit(False, "다운로드가 취소되었습니다.")
            else:
                self.finished_signal.emit(False, f"CUDA 가속 팩 설치 실패: {e}")
        finally:
            LLMModelManager.unregister_cuda_worker()


class LLMModelManager:
    """Ollama API 및 내장 GGUF 모델 통합 관리 클래스"""

    # 활성 다운로드 워커(Worker) 전역 관리 (창을 닫아도 다운로드 유지 및 재연결)
    _active_gguf_workers: Dict[str, Any] = {}
    _last_gguf_progress: Dict[str, Tuple[int, str]] = {}
    _active_ollama_workers: Dict[str, Any] = {}
    _last_ollama_progress: Dict[str, Tuple[int, str]] = {}
    _active_cuda_worker: Optional[Any] = None
    _last_cuda_progress: Optional[Tuple[int, str]] = None

    @classmethod
    def get_active_gguf_worker(cls, model_id: str) -> Optional[Any]:
        """현재 백그라운드에서 다운로드 중인 GGUFWorker 반환"""
        w = cls._active_gguf_workers.get(model_id)
        if w and w.is_alive():
            return w
        return None

    @classmethod
    def register_gguf_worker(cls, model_id: str, worker: Any):
        cls._active_gguf_workers[model_id] = worker

    @classmethod
    def unregister_gguf_worker(cls, model_id: str):
        cls._active_gguf_workers.pop(model_id, None)
        cls._last_gguf_progress.pop(model_id, None)

    @classmethod
    def set_last_gguf_progress(cls, model_id: str, pct: int, msg: str):
        cls._last_gguf_progress[model_id] = (pct, msg)

    @classmethod
    def get_last_gguf_progress(cls, model_id: str) -> Tuple[int, str]:
        return cls._last_gguf_progress.get(model_id, (0, "다운로드 진행 중..."))

    @classmethod
    def get_active_ollama_worker(cls, tag: str) -> Optional[Any]:
        """현재 백그라운드에서 다운로드 중인 OllamaWorker 반환"""
        w = cls._active_ollama_workers.get(tag)
        if w and w.is_alive():
            return w
        return None

    @classmethod
    def register_ollama_worker(cls, tag: str, worker: Any):
        cls._active_ollama_workers[tag] = worker

    @classmethod
    def unregister_ollama_worker(cls, tag: str):
        cls._active_ollama_workers.pop(tag, None)
        cls._last_ollama_progress.pop(tag, None)

    @classmethod
    def set_last_ollama_progress(cls, tag: str, pct: int, msg: str):
        cls._last_ollama_progress[tag] = (pct, msg)

    @classmethod
    def get_last_ollama_progress(cls, tag: str) -> Tuple[int, str]:
        return cls._last_ollama_progress.get(tag, (0, "다운로드 진행 중..."))

    @classmethod
    def get_active_cuda_worker(cls) -> Optional[Any]:
        """현재 백그라운드에서 다운로드 중인 CUDA Worker 반환"""
        if cls._active_cuda_worker and cls._active_cuda_worker.is_alive():
            return cls._active_cuda_worker
        return None

    @classmethod
    def register_cuda_worker(cls, worker: Any):
        cls._active_cuda_worker = worker

    @classmethod
    def unregister_cuda_worker(cls):
        cls._active_cuda_worker = None
        cls._last_cuda_progress = None

    @classmethod
    def set_last_cuda_progress(cls, pct: int, msg: str):
        cls._last_cuda_progress = (pct, msg)

    @classmethod
    def get_last_cuda_progress(cls) -> Tuple[int, str]:
        return cls._last_cuda_progress or (0, "CUDA 가속 팩 다운로드 중...")

    _cached_alive_result: Optional[Tuple[bool, str]] = None
    _cached_alive_time: float = 0.0
    _cached_models: Optional[List[Dict]] = None
    _cached_models_time: float = 0.0

    # -------------------------------------------------------------
    # 1. Ollama 모드 관련 메서드
    # -------------------------------------------------------------
    _ollama_installed: Optional[bool] = None
    _ollama_install_checked_at: float = 0.0

    @classmethod
    def is_ollama_installed(cls, force_refresh: bool = False) -> bool:
        """Ollama 설치 또는 서비스 상태를 짧게 캐시하고 재확인한다."""
        if not force_refresh and cls._ollama_installed is True:
            return cls._ollama_installed
        if (not force_refresh and cls._ollama_installed is False and
                time.time() - cls._ollama_install_checked_at < 5.0):
            return False
        cls._ollama_install_checked_at = time.time()

        import shutil
        # 1. PATH 환경변수 검색
        if shutil.which("ollama"):
            cls._ollama_installed = True
            return True

        # 2. Windows 기본 사용자 설치 경로 검사
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            common_path = os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe")
            if os.path.exists(common_path):
                cls._ollama_installed = True
                return True

        # 3. 이미 11434 포트로 백그라운드 서비스가 켜져 있는지 1회 초고속(150ms) 핑
        try:
            r = requests.get(f"{OLLAMA_API_BASE}/api/version", timeout=0.5)
            if r.status_code == 200:
                cls._ollama_installed = True
                return True
        except Exception:
            pass

        cls._ollama_installed = False
        return False

    @classmethod
    def check_ollama_alive(cls, force_refresh: bool = False) -> Tuple[bool, str]:
        """Ollama 서비스 실행 여부 및 버전 확인"""
        if not cls.is_ollama_installed(force_refresh=force_refresh):
            return False, "미설치"

        now = time.time()
        if not force_refresh and cls._cached_alive_result is not None and (now - cls._cached_alive_time < 5.0):
            return cls._cached_alive_result
        try:
            ver_resp = requests.get(f"{OLLAMA_API_BASE}/api/version", timeout=0.25)
            if ver_resp.status_code == 200:
                ver = ver_resp.json().get("version", "Active")
                cls._cached_alive_result = (True, ver)
                cls._cached_alive_time = now
                return True, ver
        except Exception:
            pass
        cls._cached_alive_result = (False, "미실행")
        cls._cached_alive_time = now
        return False, "미실행"

    @classmethod
    def get_installed_ollama_models(cls, force_refresh: bool = False) -> List[Dict]:
        """Ollama에 설치된 모델 목록 조회 (5초 캐싱)"""
        now = time.time()
        if not force_refresh and cls._cached_models is not None and (now - cls._cached_models_time < 5.0):
            return cls._cached_models
        try:
            resp = requests.get(f"{OLLAMA_API_BASE}/api/tags", timeout=0.5)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                result = []
                for m in models:
                    size_bytes = m.get("size", 0)
                    size_mb = round(size_bytes / (1024 * 1024), 1)
                    result.append({
                        "name": m.get("name", ""),
                        "tag": m.get("model", m.get("name", "")),
                        "size_mb": size_mb,
                        "modified_at": m.get("modified_at", ""),
                        "details": m.get("details", {})
                    })
                cls._cached_models = result
                cls._cached_models_time = now
                return result
        except Exception:
            pass
        cls._cached_models = []
        cls._cached_models_time = now
        return []

    @classmethod
    def is_ollama_model_installed(cls, model_tag: str, installed_models: Optional[List[Dict]] = None) -> bool:
        """특정 태그의 모델이 Ollama에 설치되어 있는지 여부"""
        installed = installed_models if installed_models is not None else cls.get_installed_ollama_models()
        for m in installed:
            # 태그 일치 검사 (예: exaone3.5:2.4b 또는 exaone3.5:latest)
            if m["tag"] == model_tag or m["name"] == model_tag:
                return True
            if ":" not in model_tag and m["tag"].startswith(model_tag + ":"):
                return True
        return False

    @classmethod
    def delete_ollama_model(cls, model_tag: str) -> bool:
        """Ollama 모델 삭제"""
        try:
            resp = requests.delete(
                f"{OLLAMA_API_BASE}/api/delete",
                json={"name": model_tag},
                timeout=5.0
            )
            cls.get_installed_ollama_models(force_refresh=True)
            return resp.status_code == 200
        except Exception as e:
            print(f"[LLMModelManager] Ollama 모델 삭제 실패: {e}")
            return False

    # -------------------------------------------------------------
    # 2. 내장 Standalone GGUF 모드 관련 메서드 (지정 폴더 & 캐시 폴더 이중 지원)
    # -------------------------------------------------------------
    @classmethod
    def get_gguf_file_path(cls, model_info: dict, custom_dir: Optional[str] = None) -> Optional[str]:
        r"""지정 폴더(D:\AI_Models 등) 및 캐시 폴더에서 GGUF 파일 경로 탐색"""
        filename = model_info.get("filename", "")
        c_dir = custom_dir or get_custom_model_dir()

        # 1. 지정 폴더 하위 GGUF 디렉터리 및 직하위 우선 탐색
        if c_dir and os.path.exists(c_dir):
            candidate_paths = [
                os.path.join(c_dir, "GGUF", filename),
                os.path.join(c_dir, filename),
            ]
            for cp in candidate_paths:
                if os.path.exists(cp):
                    real_p = os.path.realpath(cp)
                    if os.path.exists(real_p):
                        return os.path.normpath(real_p)

            # 2. 지정 폴더 내 huggingface 캐시 탐색 (hf_sub 및 hf_sub/hub 둘 다 탐색)
            hf_sub = os.path.join(c_dir, "huggingface")
            if os.path.exists(hf_sub):
                try:
                    from huggingface_hub import try_to_load_from_cache
                    for cache_candidate in [hf_sub, os.path.join(hf_sub, "hub")]:
                        if os.path.exists(cache_candidate):
                            p = try_to_load_from_cache(
                                repo_id=model_info["repo_id"],
                                filename=filename,
                                cache_dir=cache_candidate
                            )
                            if p and os.path.exists(p):
                                real_p = os.path.realpath(p)
                                if os.path.exists(real_p):
                                    # 깨진 링크가 존재할 경우 D:\AI_Models\GGUF 하위 자동 복구
                                    gguf_dir = os.path.join(c_dir, "GGUF")
                                    if os.path.exists(gguf_dir):
                                        target_shared = os.path.join(gguf_dir, filename)
                                        if os.path.lexists(target_shared) and not os.path.exists(target_shared):
                                            try:
                                                os.remove(target_shared)
                                                os.link(real_p, target_shared)
                                            except Exception:
                                                pass
                                    return os.path.normpath(real_p)
                except Exception:
                    pass

        # 3. 기본 HF_HOME / ~/.cache/huggingface 캐시 탐색 (폴백)
        try:
            from huggingface_hub import try_to_load_from_cache
            p = try_to_load_from_cache(
                repo_id=model_info["repo_id"],
                filename=filename
            )
            if p and os.path.exists(p):
                real_p = os.path.realpath(p)
                if os.path.exists(real_p):
                    return os.path.normpath(real_p)
        except Exception:
            pass

        return None

    @classmethod
    def is_gguf_model_installed(cls, model_info: dict, custom_dir: Optional[str] = None) -> bool:
        """내장 GGUF 모델이 지정 폴더 또는 캐시에 설치되어 있는지 여부"""
        path = cls.get_gguf_file_path(model_info, custom_dir=custom_dir)
        return path is not None and os.path.exists(path)

    @classmethod
    def delete_gguf_model(cls, model_info: dict) -> bool:
        """지정 폴더 및 캐시된 GGUF 파일 및 HuggingFace 캐시 디렉터리 완전 삭제 (단 1회 클릭으로 완전 제거)"""
        import shutil
        filename = model_info.get("filename", "")
        repo_id = model_info.get("repo_id", "")
        c_dir = get_custom_model_dir()
        deleted = False

        # 1. 개별 GGUF 파일 탐색 및 삭제 (지정 폴더 D:\AI_Models\GGUF 및 직하위 등)
        target_files = set()
        filepath = cls.get_gguf_file_path(model_info)
        if filepath:
            target_files.add(filepath)
            try:
                target_files.add(os.path.realpath(filepath))
            except Exception:
                pass

        base_dirs = []
        if c_dir:
            base_dirs.append(c_dir)
        if os.path.exists(r"D:\AI_Models") and r"D:\AI_Models" not in base_dirs:
            base_dirs.append(r"D:\AI_Models")

        for b in base_dirs:
            if filename:
                target_files.add(os.path.join(b, "GGUF", filename))
                target_files.add(os.path.join(b, filename))

        for f in target_files:
            if os.path.lexists(f) or os.path.exists(f):
                try:
                    os.remove(f)
                    deleted = True
                except Exception as e:
                    print(f"[LLMModelManager] GGUF 파일 삭제 오류 ({f}): {e}")

        # 2. HuggingFace 캐시 허브 디렉터리 (models--<repo_id>) 완전 삭제
        if repo_id:
            folder_name = "models--" + repo_id.replace("/", "--")
            cache_candidates = []
            for b in base_dirs:
                cache_candidates.append(os.path.join(b, "huggingface", "hub", folder_name))
                cache_candidates.append(os.path.join(b, "huggingface", folder_name))

            env_hub = os.environ.get("HF_HUB_CACHE")
            if env_hub:
                cache_candidates.append(os.path.join(env_hub, folder_name))

            env_home = os.environ.get("HF_HOME")
            if env_home:
                cache_candidates.append(os.path.join(env_home, "hub", folder_name))
                cache_candidates.append(os.path.join(env_home, folder_name))

            default_hub = os.path.expanduser("~/.cache/huggingface/hub")
            cache_candidates.append(os.path.join(default_hub, folder_name))
            default_hf = os.path.expanduser("~/.cache/huggingface")
            cache_candidates.append(os.path.join(default_hf, folder_name))

            for repo_dir in cache_candidates:
                if os.path.exists(repo_dir):
                    try:
                        shutil.rmtree(repo_dir, ignore_errors=True)
                        deleted = True
                    except Exception as e:
                        print(f"[LLMModelManager] GGUF HF 캐시 삭제 오류 ({repo_dir}): {e}")

        # 3. try_to_load_from_cache로 남아있는 캐시 파일이 있는지 최종 점검 및 삭제
        if repo_id and filename:
            try:
                from huggingface_hub import try_to_load_from_cache
                check_dirs = [None]
                if c_dir:
                    check_dirs.extend([os.path.join(c_dir, "huggingface"), os.path.join(c_dir, "huggingface", "hub")])
                for cache_candidate in check_dirs:
                    try:
                        p = try_to_load_from_cache(repo_id=repo_id, filename=filename, cache_dir=cache_candidate)
                        if p and (os.path.lexists(p) or os.path.exists(p)):
                            real_p = os.path.realpath(p)
                            if os.path.exists(real_p):
                                os.remove(real_p)
                            if os.path.lexists(p):
                                os.remove(p)
                            deleted = True
                    except Exception:
                        pass
            except Exception:
                pass

        return deleted or (not cls.is_gguf_model_installed(model_info))

    # -------------------------------------------------------------
    # 3. 에디션(Full/Lite) 및 NVIDIA CUDA 가속 바이너리 관리 메서드
    # -------------------------------------------------------------
    @classmethod
    def get_app_edition(cls) -> str:
        """현재 실행 중인 애플리케이션의 에디션 반환 ('full' 또는 'lite')"""
        try:
            import sys
            # 번들/실행 환경에서 assets/edition.json 확인
            candidate_files = []
            if getattr(sys, "frozen", False):
                if hasattr(sys, "_MEIPASS"):
                    candidate_files.append(os.path.join(sys._MEIPASS, "assets", "edition.json"))
                candidate_files.append(os.path.join(os.path.dirname(sys.executable), "assets", "edition.json"))
            from src.config import BASE_DIR
            candidate_files.append(os.path.join(BASE_DIR, "assets", "edition.json"))

            for f_path in candidate_files:
                if os.path.exists(f_path):
                    with open(f_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        ed = data.get("edition", "").strip().lower()
                        if ed in ("lite", "full"):
                            return ed
        except Exception:
            pass

        # 파일이 없을 경우 바이너리 유무로 감지
        return "full" if cls.is_cuda_binary_available() else "lite"

    @classmethod
    def get_cuda_library_paths(cls) -> List[str]:
        """현재 프로세스가 쓰는(또는 쓸 예정인) ggml-cuda.dll 경로. CPU 백엔드면 빈 목록."""
        from src.cuda_utils import get_active_ggml_cuda_path
        path = get_active_ggml_cuda_path()
        return [path] if path else []

    @classmethod
    def is_cuda_binary_available(cls) -> bool:
        """이 PC에서 쓸 수 있는 로컬 LLM CUDA 라이브러리가 설치되어 있는지 여부 (재시작 대기 포함)"""
        from src.cuda_utils import is_ggml_cuda_available
        return is_ggml_cuda_available()

    @classmethod
    def can_install_llm_cuda(cls) -> bool:
        """가속 팩을 설치하면 로컬 LLM GPU 가속이 가능해지는 PC인지 (NVIDIA + 드라이버/GPU 세대 충족)"""
        from src.cuda_utils import llama_cuda_issue
        return llama_cuda_issue("cu13") is None

    @classmethod
    def llm_gpu_unavailable_reason(cls) -> str:
        from src.cuda_utils import llama_cuda_issue
        from src.i18n import tr
        return llama_cuda_issue("cu13") or tr("msg_no_cuda_lib")

    @classmethod
    def query_nvidia_compute_capability(cls):
        from src.cuda_utils import get_nvidia_driver_info
        return get_nvidia_driver_info()[1]

    @classmethod
    def bundled_cuda_architectures(cls):
        for path in cls.get_cuda_library_paths():
            try:
                if os.path.exists(path) and os.path.getsize(path) > 10 * 1024 * 1024:
                    return scan_cuda_binary_architectures(path)
            except OSError:
                continue
        return set()

    @classmethod
    def resolve_n_gpu_layers(cls, config=None):
        """(-1, "")이면 GPU 전체 오프로딩, (0, 안내문)이면 CPU로 안전 로드."""
        from src.cuda_utils import configure_llama_backend
        config = config or {}
        device = config.get("device", "")
        if str(device).lower() == "cpu":
            return decide_n_gpu_layers(device, False, False, None, set())
        state = configure_llama_backend()
        if state["backend"] != "cuda":
            if state.get("restart_required"):
                return 0, ("CUDA 가속 팩이 설치되었지만 이번 실행에서는 로컬 LLM이 이미 CPU 라이브러리로 로드되어 있습니다. "
                           "프로그램을 다시 시작하면 GPU로 동작합니다.")
            return 0, f"{state.get('issue') or cls.llm_gpu_unavailable_reason()} CPU로 로드합니다."
        supports = False
        try:
            import llama_cpp
            supports = bool(llama_cpp.llama_supports_gpu_offload())
        except Exception:
            supports = False
        if not supports:
            return 0, "llama.cpp CUDA 라이브러리가 GPU 오프로드를 지원하지 않아 CPU로 로드합니다."
        return decide_n_gpu_layers(
            device,
            True,
            supports,
            cls.query_nvidia_compute_capability(),
            cls.bundled_cuda_architectures() if supports else set(),
        )

    @classmethod
    def get_cuda_target_install_dir(cls) -> str:
        """온디맨드 다운로드 시 가속 라이브러리를 배치할 타겟 디렉터리 경로 반환"""
        from src.cuda_utils import get_cuda_target_install_dir
        return get_cuda_target_install_dir()

    @classmethod
    def is_nvidia_gpu_present(cls) -> bool:
        """시스템에 사용 가능한 NVIDIA GPU가 있는지 감지"""
        from src.cuda_utils import is_nvidia_gpu_present
        return is_nvidia_gpu_present()

    @classmethod
    def is_stt_cuda_available(cls) -> bool:
        """STT(faster-whisper) cuBLAS GPU 가속 가능 여부"""
        from src.cuda_utils import is_stt_cuda_available
        return is_stt_cuda_available()

    @classmethod
    def is_full_cuda_pack_available(cls) -> bool:
        """STT cuBLAS 및 로컬 LLM ggml-cuda 가속 라이브러리가 모두 완비되었는지 여부"""
        from src.cuda_utils import is_cublas_installed, is_ggml_cuda_available
        return is_cublas_installed() and is_ggml_cuda_available()

    @classmethod
    def delete_cuda_pack(cls) -> bool:
        """온디맨드로 받은 CUDA 가속 팩만 제거 (Full 내장 라이브러리와 시스템 CUDA 는 건드리지 않는다)"""
        import shutil
        from src.cuda_utils import get_cuda_target_install_dir
        deleted = False
        pack_dir = get_cuda_target_install_dir()
        for name in ["cublas64_12.dll", "cublasLt64_12.dll", "nvblas64_12.dll", "cudart64_12.dll"]:
            p = os.path.join(pack_dir, name)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                    deleted = True
                except Exception as e:
                    print(f"[LLMModelManager] CUDA 라이브러리 삭제 실패 ({p}): {e}")
        llama_root = os.path.join(pack_dir, "llama")
        if os.path.isdir(llama_root):
            try:
                shutil.rmtree(llama_root)
                deleted = True
            except Exception as e:
                print(f"[LLMModelManager] 로컬 LLM CUDA 라이브러리 삭제 실패 (사용 중이면 재시작 후 다시 시도): {e}")
        return deleted

