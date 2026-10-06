"""
CUDA 및 cuBLAS 가속 라이브러리 경로 탐색, 시스템 등록 및 가용성 검증 유틸리티
----------------------------------------------------------------------
LumiTrans의 로컬 LLM(llama_cpp) 및 STT(faster-whisper/ctranslate2)에 필요한
NVIDIA CUDA/cuBLAS 런타임 DLL 탐색 및 프로세스 등록을 전담 관리합니다.
"""

import os
import sys
import ctypes
import logging
from typing import List, Optional, Dict, Any, Tuple

logger = logging.getLogger("CUDALoader")

_REGISTERED_DIRS = set()
_GPU_PRESENT_CACHE = {"checked": False, "present": False}


def is_nvidia_gpu_present() -> bool:
    """시스템에 NVIDIA 외장/내장 GPU가 물리적으로 장착되어 있는지 감지.
    절전 상태인 랩톱 dGPU(D3 Cold), Windows 11의 wmic 제거, PATH 미등록 환경에서도
    레지스트리, 드라이버 핵심 DLL, nvidia-smi 다단계 검사로 100% 신뢰성 있게 즉시 감지합니다.
    """
    if _GPU_PRESENT_CACHE["checked"]:
        return _GPU_PRESENT_CACHE["present"]

    present = False

    # 1. Windows 레지스트리 초고속 감지 (<1ms, 프로세스 미생성, 랩톱 dGPU 슬립 영향 없음)
    if sys.platform == "win32":
        try:
            import winreg
            key_path = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
                for i in range(128):
                    try:
                        sub = winreg.EnumKey(k, i)
                        if sub.isdigit():
                            with winreg.OpenKey(k, sub) as sk:
                                try:
                                    desc, _ = winreg.QueryValueEx(sk, "DriverDesc")
                                    if "nvidia" in str(desc).lower():
                                        present = True
                                        break
                                except Exception:
                                    pass
                    except OSError:
                        break
        except Exception:
            pass

    # 2. NVIDIA 드라이버 핵심 DLL 감지 (System32\nvcuda.dll / nvapi64.dll)
    if not present and sys.platform == "win32":
        try:
            sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
            if os.path.isfile(os.path.join(sys32, "nvcuda.dll")) or os.path.isfile(os.path.join(sys32, "nvapi64.dll")):
                present = True
        except Exception:
            pass

    # 3. nvidia-smi 명령행 감지 (표준 경로 포함, 타임아웃 4초로 랩톱 절전 복귀 보장)
    if not present:
        import subprocess
        smi_paths = ["nvidia-smi"]
        if sys.platform == "win32":
            sys32_smi = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
            nvsmi_smi = r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
            for p in (sys32_smi, nvsmi_smi):
                if os.path.isfile(p) and p not in smi_paths:
                    smi_paths.append(p)

        for smi in smi_paths:
            try:
                res = subprocess.run(
                    [smi, "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=4,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if res.returncode == 0 and res.stdout.strip():
                    present = True
                    break
            except Exception:
                pass

    # 4. Windows 11 PowerShell CIM 대체 감지 (wmic 제거 대응)
    if not present and sys.platform == "win32":
        try:
            import subprocess
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                   "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"]
            res = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if res.returncode == 0 and "nvidia" in res.stdout.lower():
                present = True
        except Exception:
            pass

    _GPU_PRESENT_CACHE["checked"] = True
    _GPU_PRESENT_CACHE["present"] = present
    return present


def get_cuda_target_install_dir() -> str:
    """온디맨드 가속 팩 저장 위치. 설치 폴더(Program Files 등)는 쓰기 권한이 없을 수 있어 항상 사용자 폴더를 쓴다.
    한국어 버전(LumiTrans)과 글로벌 버전(LumiTrans Global) 간 대용량 가속 팩 중복 다운로드를 방지하기 위해
    기존 설치 폴더가 있으면 이를 공유/재사용합니다."""
    local_app = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    # 기존 LumiTrans/cuda 폴더가 이미 있으면 우선 공유
    shared_kr = os.path.join(local_app, "LumiTrans", "cuda")
    if os.path.isdir(shared_kr):
        return shared_kr
    from src.app_paths import local_data_dir
    target = os.path.join(local_data_dir(), "cuda")
    os.makedirs(target, exist_ok=True)
    return target


# ---------------------------------------------------------------------------
# 로컬 LLM(llama_cpp) 백엔드 선택
# 번들 기본 llama_cpp/lib 는 NVIDIA 참조가 없는 CPU 전용 빌드다.
# CUDA 빌드는 별도 폴더에 두고, llama_cpp 가 처음 import 되기 전에 LLAMA_CPP_LIB_PATH 로 지정한다.
# 한 프로세스에 같은 이름(ggml.dll 등)의 DLL 은 하나만 올라가므로, 한 번 로드된 뒤에는 재시작 전까지 바꿀 수 없다.
# ---------------------------------------------------------------------------
# "-avx2": 공식 CUDA wheel 의 ggml-cpu.dll 은 AVX-512 로 빌드되어 AVX-512 가 없는 CPU 에서 0xC000001D 로 죽는다.
# 설치 시 앱에 내장된 같은 버전 CPU 전용 ggml-cpu.dll(AVX2)로 바꾼다. 교체 전 팩은 ID 가 달라 다시 받는다.
LLAMA_CUDA_PACK_ID = "cu130-0.3.35-avx2"
_LLAMA_CUDA_MIN_DRIVER = {"cu12": (525, 60), "cu13": (580, 0)}
_LLAMA_CUDA_MIN_CC = {"cu12": (5, 0), "cu13": (7, 5)}
_NVIDIA_INFO_CACHE: Dict[str, Any] = {}
_LLAMA_STATE: Dict[str, Any] = {
    "configured": False, "backend": "cpu", "path": None, "kind": None,
    "issue": None, "restart_required": False,
}


def _run_nvidia_smi(query: str) -> Optional[str]:
    import subprocess
    smi_paths = ["nvidia-smi"]
    if sys.platform == "win32":
        sys32_smi = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
        nvsmi_smi = r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
        for p in (sys32_smi, nvsmi_smi):
            if os.path.isfile(p) and p not in smi_paths:
                smi_paths.append(p)

    for smi in smi_paths:
        try:
            res = subprocess.run(
                [smi, f"--query-gpu={query}", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip().splitlines()[0]
        except Exception:
            pass
    return None


def get_nvidia_driver_info() -> Tuple[Optional[Tuple[int, int]], Optional[Tuple[int, int]]]:
    """(드라이버 버전, GPU 연산 능력)을 (major, minor) 튜플로 반환. 알 수 없으면 None."""
    if "value" in _NVIDIA_INFO_CACHE:
        return _NVIDIA_INFO_CACHE["value"]

    def _pair(text):
        try:
            parts = text.strip().split(".")
            return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        except Exception:
            return None

    driver, cc = None, None
    line = _run_nvidia_smi("driver_version,compute_cap")
    if line and "," in line:
        d, c = line.split(",", 1)
        driver, cc = _pair(d), _pair(c)
    else:
        # compute_cap 필드를 모르는 구형 드라이버
        line = _run_nvidia_smi("driver_version")
        if line:
            driver = _pair(line)
    _NVIDIA_INFO_CACHE["value"] = (driver, cc)
    return driver, cc


def llama_cuda_issue(kind: str = "cu13") -> Optional[str]:
    """해당 CUDA 빌드(cu12/cu13)를 이 PC에서 쓸 수 없는 이유. 쓸 수 있으면 None."""
    from src.i18n import tr
    if not is_nvidia_gpu_present():
        return tr("msg_no_nvidia_short")
    driver, cc = get_nvidia_driver_info()
    need_driver = _LLAMA_CUDA_MIN_DRIVER[kind]
    if driver is not None and driver < need_driver:
        return tr(
            "msg_driver_old",
            driver=f"{driver[0]}.{driver[1]:02d}",
            need=f"{need_driver[0]}.{need_driver[1]:02d}",
        )
    need_cc = _LLAMA_CUDA_MIN_CC[kind]
    if cc is not None and cc < need_cc:
        return tr(
            "msg_gpu_old",
            cc=f"{cc[0]}.{cc[1]}",
            need=f"{need_cc[0]}.{need_cc[1]}",
        )
    return None


def get_default_llama_lib_dir() -> Optional[str]:
    """llama_cpp 가 LLAMA_CPP_LIB_PATH 없이 로드하는 기본 lib 폴더 (import 하지 않고 계산)."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None) or os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "_internal")
        return os.path.join(base, "llama_cpp", "lib")
    try:
        import importlib.util
        spec = importlib.util.find_spec("llama_cpp")
        if spec and spec.origin:
            return os.path.join(os.path.dirname(os.path.abspath(spec.origin)), "lib")
    except Exception:
        pass
    return None


def get_bundled_llama_cuda_dir() -> Optional[str]:
    """Full 에디션에 내장된 CUDA 12 llama.cpp 라이브러리 폴더."""
    if not getattr(sys, "frozen", False):
        return None
    base = getattr(sys, "_MEIPASS", None) or os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "_internal")
    return os.path.join(base, "llama_cuda")


def is_llama_cuda_dir(path: Optional[str]) -> bool:
    if not path:
        return False
    try:
        cuda_dll = os.path.join(path, "ggml-cuda.dll")
        return (os.path.isfile(os.path.join(path, "llama.dll"))
                and os.path.isfile(cuda_dll)
                and os.path.getsize(cuda_dll) > 50 * 1024 * 1024)
    except OSError:
        return False


def get_llama_cuda_pack_dir() -> str:
    """가속 팩으로 받은 CUDA 13 llama.cpp 라이브러리 폴더 (버전별로 분리해 로드 중인 파일을 덮어쓰지 않는다)."""
    # 1. 대상 설치 폴더 확인 (is_llama_cuda_dir 검사 전에 존재 여부 체크)
    target = os.path.join(get_cuda_target_install_dir(), "llama", LLAMA_CUDA_PACK_ID)
    if is_llama_cuda_dir(target):
        return target
    # 2. 한국어/글로벌/레거시 폴더 간 기설치된 가속 팩 탐색
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        for name in ("LumiTrans", "LumiTrans Global", "WiseEinstein"):
            candidate = os.path.join(local_app, name, "cuda", "llama", LLAMA_CUDA_PACK_ID)
            if is_llama_cuda_dir(candidate):
                return candidate
    return target


def is_llama_cuda_pack_installed() -> bool:
    pack = get_llama_cuda_pack_dir()
    marker = os.path.join(pack, "wise_cuda_pack.txt")
    try:
        with open(marker, "r", encoding="utf-8") as handle:
            return handle.read().strip() == LLAMA_CUDA_PACK_ID and is_llama_cuda_dir(pack)
    except OSError:
        return False


def select_llama_backend() -> Dict[str, Any]:
    """지금 PC에서 로드해야 할 llama.cpp 라이브러리 결정 (로드는 하지 않는다)."""
    candidates = []
    if is_llama_cuda_pack_installed():
        candidates.append((get_llama_cuda_pack_dir(), "cu13"))
    bundled = get_bundled_llama_cuda_dir()
    if is_llama_cuda_dir(bundled):
        candidates.append((bundled, "cu12"))
    default_dir = get_default_llama_lib_dir()
    if not getattr(sys, "frozen", False) and is_llama_cuda_dir(default_dir):
        # 소스 실행 환경에 CUDA 빌드 llama-cpp-python 이 설치된 경우
        candidates.append((default_dir, "cu12"))

    first_issue = None
    for path, kind in candidates:
        issue = llama_cuda_issue(kind)
        if issue is None:
            return {"backend": "cuda", "path": path, "kind": kind, "issue": None}
        first_issue = first_issue or issue
    return {"backend": "cpu", "path": None, "kind": None, "issue": first_issue}


def is_llama_loaded() -> bool:
    return "llama_cpp.llama_cpp" in sys.modules


def configure_llama_backend() -> Dict[str, Any]:
    """llama_cpp import 전에 호출하면 사용할 라이브러리 폴더를 LLAMA_CPP_LIB_PATH 로 지정한다.
    이미 로드된 뒤라면 교체하지 않고, CUDA 로 바꿀 수 있게 되었으면 restart_required 를 표시한다."""
    if is_llama_loaded():
        if not _LLAMA_STATE["configured"]:
            actual = os.environ.get("LLAMA_CPP_LIB_PATH") or get_default_llama_lib_dir()
            is_cuda = is_llama_cuda_dir(actual)
            _LLAMA_STATE.update({"configured": True, "backend": "cuda" if is_cuda else "cpu",
                                 "path": actual if is_cuda else None, "kind": None, "issue": None})
        if _LLAMA_STATE["backend"] != "cuda":
            _LLAMA_STATE["restart_required"] = select_llama_backend()["backend"] == "cuda"
        return dict(_LLAMA_STATE)

    sel = select_llama_backend()
    default_dir = get_default_llama_lib_dir()
    if sel["path"] and os.path.normcase(os.path.abspath(sel["path"])) != os.path.normcase(os.path.abspath(default_dir or "")):
        os.environ["LLAMA_CPP_LIB_PATH"] = sel["path"]
    else:
        os.environ.pop("LLAMA_CPP_LIB_PATH", None)
    _LLAMA_STATE.update(sel)
    _LLAMA_STATE["configured"] = True
    _LLAMA_STATE["restart_required"] = False
    if sel["backend"] == "cuda":
        logger.info(f"[CUDALoader] 로컬 LLM: CUDA 라이브러리 사용 ({sel['kind']}): {sel['path']}")
    else:
        logger.info(f"[CUDALoader] 로컬 LLM: CPU 전용 라이브러리 사용{(' - ' + sel['issue']) if sel['issue'] else ''}")
    return dict(_LLAMA_STATE)


_LLAMA_PRELOADED: List[Any] = []


def preload_llama_backend():
    """CUDA 백엔드를 쓸 때 llama_cpp import 직전에 같은 폴더의 ggml DLL 세트를 전체 경로로 먼저 올린다.
    llama_cpp 는 표준 검색 순서로 llama.dll 의존성을 찾아서, PyInstaller 가 DLL 경로로 거는 _internal 에
    같은 이름의 CPU 빌드가 있으면 그쪽이 잡힌다. 이름이 같은 DLL 이 이미 올라가 있으면 Windows 는 그것을 재사용한다."""
    state = get_llama_backend_state()
    if sys.platform != "win32" or state["backend"] != "cuda" or is_llama_loaded() or _LLAMA_PRELOADED:
        return
    folder = state["path"]
    try:
        os.add_dll_directory(folder)
    except Exception:
        pass
    for name in ("cudart64_13.dll", "cublasLt64_13.dll", "cublas64_13.dll",
                 "ggml-base.dll", "ggml-cpu.dll", "ggml-cuda.dll", "ggml.dll"):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        try:
            _LLAMA_PRELOADED.append(ctypes.CDLL(path))
        except OSError as e:
            logger.warning(f"[CUDALoader] 로컬 LLM CUDA 라이브러리 선행 로드 실패 ({path}): {e}")
            return


def get_llama_backend_state() -> Dict[str, Any]:
    if not _LLAMA_STATE["configured"]:
        return configure_llama_backend()
    return dict(_LLAMA_STATE)


def get_active_ggml_cuda_path() -> Optional[str]:
    """현재 프로세스가 로드(또는 로드 예정)하는 ggml-cuda.dll 경로. CPU 백엔드면 None."""
    state = get_llama_backend_state()
    if state["backend"] != "cuda" or not state["path"]:
        return None
    return os.path.join(state["path"], "ggml-cuda.dll")


def get_cuda_search_paths() -> List[str]:
    """CUDA / cuBLAS DLL이 위치할 수 있는 모든 유효 검색 디렉터리 목록 반환"""
    paths = []

    def _add(p):
        if p and isinstance(p, str):
            norm = os.path.abspath(p)
            if os.path.isdir(norm) and norm not in paths:
                paths.append(norm)

    # 1. PyInstaller 번들 디렉터리
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(os.path.abspath(sys.executable))
        _add(base_dir)
        _add(os.path.join(base_dir, "_internal"))
        _add(os.path.join(base_dir, "_internal", "llama_cpp", "lib"))
        _add(os.path.join(base_dir, "_internal", "llama_cpp"))
        _add(os.path.join(base_dir, "llama_cpp", "lib"))
        _add(os.path.join(base_dir, "llama_cpp"))

    if hasattr(sys, "_MEIPASS"):
        meipass = getattr(sys, "_MEIPASS")
        _add(meipass)
        _add(os.path.join(meipass, "llama_cpp", "lib"))
        _add(os.path.join(meipass, "llama_cpp"))

    # 2. 온디맨드 설치 기본 타겟 디렉터리
    try:
        _add(get_cuda_target_install_dir())
    except Exception:
        pass

    # 3. 사용자 LocalAppData / AppData cuda 폴더 (업그레이드 설치는 이전 이름 폴더를 그대로 쓸 수 있음)
    from src.app_paths import APP_NAME, GLOBAL_APP_NAME, LEGACY_APP_NAMES
    local_app = os.environ.get("LOCALAPPDATA")
    app_data = os.environ.get("APPDATA")
    for name in (APP_NAME, GLOBAL_APP_NAME) + LEGACY_APP_NAMES:
        if local_app:
            _add(os.path.join(local_app, name, "cuda"))
            _add(os.path.join(local_app, name, "cuda", "llama", LLAMA_CUDA_PACK_ID))
            _add(os.path.join(local_app, "Programs", name))
            _add(os.path.join(local_app, "Programs", name, "_internal"))
        if app_data:
            _add(os.path.join(app_data, name, "cuda"))

    # 4. 공용 모델 폴더 하위 cuda 디렉터리
    try:
        from src.config import load_config
        cfg = load_config()
        c_dir = cfg.get("custom_model_dir")
        if c_dir:
            _add(os.path.join(c_dir, "cuda"))
            _add(c_dir)
    except Exception:
        pass

    # 5. 시스템 NVIDIA CUDA Toolkit bin 디렉터리
    if sys.platform == "win32":
        for k, v in list(os.environ.items()):
            if k.upper().startswith("CUDA_PATH") and v:
                _add(os.path.join(v, "bin"))
                _add(v)

        cuda_root = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
        if os.path.isdir(cuda_root):
            try:
                for entry in sorted(os.listdir(cuda_root), reverse=True):
                    _add(os.path.join(cuda_root, entry, "bin"))
            except Exception:
                pass

    # 6. Python 패키지 환경 (pip 설치 라이브러리들)
    # llama_cpp 는 import 하는 순간 DLL 이 로드되어 백엔드를 바꿀 수 없게 되므로 여기서 import 하지 않는다.
    for pkg_name, sub in [
        ("nvidia.cublas", "bin"),
        ("nvidia.cuda_runtime", "bin"),
        ("ctranslate2", ""),
        ("torch", "lib"),
    ]:
        try:
            mod = __import__(pkg_name, fromlist=["__file__"])
            p = os.path.dirname(os.path.abspath(mod.__file__))
            _add(os.path.join(p, sub) if sub else p)
        except Exception:
            pass

    # 7. 현재 환경변수 PATH 중 cuda 관련 폴더
    for p in os.environ.get("PATH", "").split(os.pathsep):
        p_strip = p.strip()
        if p_strip and "cuda" in p_strip.lower() and os.path.isdir(p_strip):
            _add(p_strip)

    return paths


_LOADED_DLL_HANDLES = {}


def register_cuda_dll_directories(force: bool = False):
    """모든 CUDA/cuBLAS 검색 디렉터리를 Windows DLL 탐색 경로 및 PATH에 안전하게 등록"""
    if sys.platform != "win32":
        return

    if force:
        _REGISTERED_DIRS.clear()

    search_dirs = get_cuda_search_paths()
    for d in search_dirs:
        if d in _REGISTERED_DIRS:
            continue
        try:
            # Python 3.8+ Windows DLL 전용 디렉터리 추가
            os.add_dll_directory(d)
        except Exception:
            pass

        # 환경변수 PATH 최상단에 prepend (하위 프로세스 및 호환성 보장)
        current_path = os.environ.get("PATH", "")
        if d not in current_path:
            os.environ["PATH"] = d + os.pathsep + current_path

        _REGISTERED_DIRS.add(d)


def preload_cuda_dlls() -> List[str]:
    """
    다운로드된 CUDA/cuBLAS DLL을 현재 프로세스 메모리에 명시적으로 선행 로드(Pre-load)합니다.
    이를 통해 CTranslate2 및 llama_cpp C++ 바이너리가 별도의 프로그램 재시작 없이도
    방금 설치된 가속 라이브러리를 즉시 인식하고 사용할 수 있도록 보장합니다.
    """
    if sys.platform != "win32":
        return []

    register_cuda_dll_directories(force=True)

    if not is_nvidia_gpu_present():
        return []

    loaded = []
    # STT(ctranslate2)용 CUDA 12 런타임만 로드한다.
    # ggml-cuda.dll 은 이름이 같은 다른 빌드가 먼저 올라가면 llama.dll 과 짝이 어긋나 죽으므로 선행 로드하지 않는다.
    dll_sequence = [
        ("cudart64_12.dll", 0.1),
        ("cublasLt64_12.dll", 20.0),
        ("cublas64_12.dll", 20.0),
    ]

    for dll_name, min_mb in dll_sequence:
        if dll_name in _LOADED_DLL_HANDLES:
            loaded.append(dll_name)
            continue
        p = find_cuda_dll(dll_name, min_size_mb=min_mb)
        if p and os.path.isfile(p):
            try:
                # Windows 커널 로더에 DLL을 즉시 매핑하여 HMODULE을 유지
                h = ctypes.CDLL(p)
                _LOADED_DLL_HANDLES[dll_name] = h
                loaded.append(dll_name)
                logger.info(f"[CUDALoader] {dll_name} 프로세스 즉시 매핑 성공: {p}")
            except Exception as e:
                logger.warning(f"[CUDALoader] {dll_name} 선행 로드 실패 ({p}): {e}")

    return loaded


def find_cuda_dll(dll_name: str, min_size_mb: float = 1.0) -> Optional[str]:
    """지정된 이름의 CUDA 관련 DLL이 유효하게 존재하는지 탐색하여 첫 번째 절대경로 반환"""
    dll_name_lower = dll_name.lower()
    for base in get_cuda_search_paths():
        candidate = os.path.join(base, dll_name)
        if os.path.isfile(candidate):
            try:
                sz_mb = os.path.getsize(candidate) / (1024 * 1024)
                if sz_mb >= min_size_mb:
                    return candidate
            except Exception:
                continue

        # 대소문자 불일치 대응
        try:
            for fname in os.listdir(base):
                if fname.lower() == dll_name_lower:
                    full_p = os.path.join(base, fname)
                    if os.path.isfile(full_p):
                        sz_mb = os.path.getsize(full_p) / (1024 * 1024)
                        if sz_mb >= min_size_mb:
                            return full_p
        except Exception:
            pass

    return None


def is_cublas_available() -> bool:
    """STT(faster-whisper/ctranslate2)에 필수적인 cuBLAS 12 라이브러리가 사용 가능한지 검증"""
    register_cuda_dll_directories()
    cublas_path = find_cuda_dll("cublas64_12.dll", min_size_mb=20.0)
    if not cublas_path:
        return False

    # 선행 로드(preload)로 cuBLAS 바인딩 검증 및 보장
    preload_cuda_dlls()
    return "cublas64_12.dll" in _LOADED_DLL_HANDLES


def is_cublas_installed() -> bool:
    """화면 표시·설치 판단용: cuBLAS 12 파일이 시스템 또는 가속 팩 폴더에 존재하는지 검사.
    is_cublas_available() 처럼 DLL 을 프로세스에 매핑하지 않아 메모리를 차지하지 않습니다."""
    register_cuda_dll_directories()
    return (find_cuda_dll("cublas64_12.dll", min_size_mb=20.0) is not None
            and find_cuda_dll("cublasLt64_12.dll", min_size_mb=20.0) is not None)


def is_ggml_cuda_available() -> bool:
    """이 PC에서 쓸 수 있는 로컬 LLM CUDA 라이브러리(가속 팩 또는 Full 내장)가 있는지 여부"""
    return select_llama_backend()["backend"] == "cuda"


def is_stt_cuda_available() -> bool:
    """STT faster-whisper가 CUDA 12로 실시간 구동 가능한지 종합 검증"""
    if not is_nvidia_gpu_present():
        return False
    register_cuda_dll_directories()

    # 1. cuBLAS 12 바이너리 필수
    if not is_cublas_available():
        return False

    # 2. ctranslate2 또는 torch의 CUDA 디바이스 감지
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return True
    except Exception:
        pass

    try:
        import torch
        if torch.cuda.is_available():
            return True
    except Exception:
        pass

    return False


def get_cuda_pack_status() -> Dict[str, Any]:
    """CUDA 가속 팩의 종합 설치 상태 딕셔너리 반환"""
    register_cuda_dll_directories()
    has_gpu = is_nvidia_gpu_present()
    has_cublas = is_cublas_installed()
    has_ggml = is_ggml_cuda_available()
    cudart = find_cuda_dll("cudart64_12.dll", min_size_mb=0.1) is not None
    llm_issue = None if has_ggml else llama_cuda_issue("cu13")
    llama_state = configure_llama_backend()

    return {
        "has_gpu": has_gpu,
        "has_cublas": has_cublas,
        "has_ggml_cuda": has_ggml,
        "has_cudart": cudart,
        "is_stt_ready": has_gpu and has_cublas,
        "is_llm_ready": has_ggml and has_gpu,
        "is_fully_ready": has_cublas and has_ggml,
        # 로컬 LLM CUDA 를 이 PC 에서 쓸 수 없는 이유 (드라이버/GPU 세대). 설치로 해결되지 않는다.
        "llm_issue": llm_issue,
        "llm_restart_required": bool(llama_state.get("restart_required")),
        "target_dir": get_cuda_target_install_dir(),
    }
