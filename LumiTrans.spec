# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import wordninja
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None
ROOT_DIR = os.path.abspath(SPECPATH)

EDITION = os.environ.get("WISE_EDITION", "full").strip().lower()
PRODUCT = os.environ.get("WISE_PRODUCT", "kr").strip().lower()
if PRODUCT not in ("kr", "global"):
    PRODUCT = "kr"
print(f"[Spec] ========================================")
print(f"[Spec] Target Build Edition: {EDITION.upper()} | Product: {PRODUCT}")
print(f"[Spec] ========================================")

# Record edition metadata into assets/edition.json
try:
    import json
    os.makedirs(os.path.join(ROOT_DIR, 'assets'), exist_ok=True)
    product_name = "LumiTrans Global" if PRODUCT == "global" else f"LumiTrans {EDITION.capitalize()}"
    with open(os.path.join(ROOT_DIR, 'assets', 'edition.json'), 'w', encoding='utf-8') as f:
        json.dump({"edition": EDITION, "product": PRODUCT, "name": product_name}, f, indent=2)
except Exception as e:
    print(f"[Spec] Warning creating edition metadata: {e}")

datas = [
    (os.path.join(ROOT_DIR, 'assets'), 'assets'),
    (os.path.join(ROOT_DIR, 'config.example.json'), '.'),
    (os.path.join(ROOT_DIR, 'src', 'tts_voice_embeddings.npy'), 'src'),
    (os.path.join(os.path.dirname(os.path.abspath(wordninja.__file__)), 'wordninja', 'wordninja_words.txt.gz'), 'wordninja'),
]

# 기본 내장 STT 모델 디렉토리 번들링 (Full 에디션만 포함, Lite 에디션은 첫 실행 시 인앱 다운로드)
if EDITION != "lite" and os.path.isdir(os.path.join(ROOT_DIR, 'models')):
    datas.append((os.path.join(ROOT_DIR, 'models'), 'models'))
    print(f"[Spec] Bundled models directory included: {os.path.join(ROOT_DIR, 'models')}")
else:
    print(f"[Spec] [Lite Edition] Bundled models directory excluded (in-app download on first run)")

for pkg in ['rapidocr_onnxruntime', 'sherpa_onnx', 'ctranslate2', 'proctap', 'soundcard', 'onnxruntime', 'winrt', 'faster_whisper']:
    try:
        datas.extend(collect_data_files(pkg))
    except Exception as e:
        print(f"[Spec] Warning collecting data for {pkg}: {e}")

# llama_cpp 의 기본 lib 폴더에는 NVIDIA 참조가 없는 CPU 전용 DLL 을 넣는다.
# (CUDA 빌드는 ggml.dll 이 ggml-cuda.dll -> nvcuda.dll 을 정적으로 참조해 NVIDIA 가 없는 PC 에서 로드 자체가 실패한다.)
# Full 에디션은 설치된 CUDA 빌드를 llama_cuda/ 에 따로 넣고, 앱이 LLAMA_CPP_LIB_PATH 로 골라 쓴다.
import importlib.util
LLAMA_PKG_DIR = os.path.dirname(os.path.abspath(importlib.util.find_spec('llama_cpp').origin))
LLAMA_SRC_LIB = os.path.normcase(os.path.join(LLAMA_PKG_DIR, 'lib'))
LLAMA_CPU_DIR = os.environ.get("WISE_LLAMA_CPU_DIR", "")
if not LLAMA_CPU_DIR or not os.path.isfile(os.path.join(LLAMA_CPU_DIR, 'llama.dll')):
    raise SystemExit("[Spec] CPU 전용 llama.cpp 라이브러리가 없습니다. scripts/build_windows_installer.py 로 빌드하세요.")

def is_llama_src_lib(path):
    p = os.path.normcase(os.path.abspath(str(path)))
    return p == LLAMA_SRC_LIB or p.startswith(LLAMA_SRC_LIB + os.sep)

for root, _dirs, files in os.walk(LLAMA_PKG_DIR):
    if is_llama_src_lib(root) or '__pycache__' in root:
        continue
    rel = os.path.relpath(root, os.path.dirname(LLAMA_PKG_DIR))
    for fname in files:
        datas.append((os.path.join(root, fname), rel))
for fname in os.listdir(LLAMA_CPU_DIR):
    if fname.lower().endswith('.dll'):
        datas.append((os.path.join(LLAMA_CPU_DIR, fname), os.path.join('llama_cpp', 'lib')))
# 설치된 llama-cpp-python 은 빌드 PC 의 CPU 명령어(AVX-512 등)로 컴파일되었을 수 있어 쓰지 않는다.
LLAMA_CUDA_DIR = os.environ.get("WISE_LLAMA_CUDA_DIR", "")
if EDITION != "lite":
    if not LLAMA_CUDA_DIR or not os.path.isfile(os.path.join(LLAMA_CUDA_DIR, 'ggml-cuda.dll')):
        raise SystemExit("[Spec] 공식 CUDA llama.cpp 라이브러리가 없습니다. scripts/build_windows_installer.py 로 빌드하세요.")
    for fname in os.listdir(LLAMA_CUDA_DIR):
        if fname.lower().endswith('.dll'):
            datas.append((os.path.join(LLAMA_CUDA_DIR, fname), 'llama_cuda'))
print(f"[Spec] llama.cpp: llama_cpp/lib <- CPU 전용 ({LLAMA_CPU_DIR})"
      + ("" if EDITION == "lite" else f", llama_cuda <- CUDA ({LLAMA_CUDA_DIR})"))

# 번역 엔진 및 로컬 LLM 필수 패키지 트리 전체 번들링 (모듈 누락 및 네임스페이스 섀도잉 원천 차단)
for pkg in ['diskcache', 'jinja2', 'markupsafe', 'hanja']:
    try:
        mod = __import__(pkg)
        p = os.path.dirname(os.path.abspath(mod.__file__))
        datas.append((p, pkg))
        print(f"[Spec] Collected full package tree for {pkg}: {p}")
    except Exception as e:
        print(f"[Spec] Warning collecting package tree for {pkg}: {e}")

try:
    import typing_extensions
    datas.append((os.path.abspath(typing_extensions.__file__), '.'))
except Exception as e:
    print(f"[Spec] Warning collecting typing_extensions: {e}")

try:
    import numpy
    np_dir = os.path.dirname(os.path.abspath(numpy.__file__))
    for sub in ['typing', '_typing']:
        sub_p = os.path.join(np_dir, sub)
        if os.path.isdir(sub_p):
            datas.append((sub_p, os.path.join('numpy', sub)))
            print(f"[Spec] Collected numpy {sub}: {sub_p}")
except Exception as e:
    print(f"[Spec] Warning collecting numpy typing: {e}")

binaries = []
for pkg in ['sherpa_onnx', 'ctranslate2', 'proctap', 'soundcard', 'onnxruntime', 'winrt']:
    try:
        binaries.extend(collect_dynamic_libs(pkg))
    except Exception as e:
        print(f"[Spec] Warning collecting binaries for {pkg}: {e}")

# GPU 기반 STT (faster-whisper / ctranslate2) 필수 CUDA 라이브러리 명시적 수집
def find_cuda_toolkit_dlls():
    cuda_bins = []
    candidates = [
        os.environ.get("CUDA_PATH_V12_4"),
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4",
        os.environ.get("CUDA_PATH"),
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9",
        os.path.join(ROOT_DIR, "dist", "LumiTrans", "_internal"),
        os.path.join(ROOT_DIR, "dist", "LumiTrans"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "LumiTrans", "cuda"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "WiseEinstein", "cuda"),  # 이전 이름
    ]
    cuda_root = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    if os.path.isdir(cuda_root):
        for entry in os.listdir(cuda_root):
            candidates.append(os.path.join(cuda_root, entry, "bin"))
            candidates.append(os.path.join(cuda_root, entry))

    for c in candidates:
        if c and os.path.isdir(os.path.join(c, "bin")):
            cuda_bins.append(os.path.join(c, "bin"))
        elif c and os.path.isdir(c):
            cuda_bins.append(c)

    needed_dlls = ["cublas64_12.dll", "cublasLt64_12.dll", "cudart64_12.dll"]
    collected = []
    for dll_name in needed_dlls:
        found_path = None
        for b_dir in cuda_bins:
            p = os.path.join(b_dir, dll_name)
            if os.path.exists(p):
                found_path = p
                break
        if not found_path:
            for p_dir in os.environ.get("PATH", "").split(";"):
                p = os.path.join(p_dir.strip(), dll_name)
                if os.path.exists(p):
                    found_path = p
                    break
        if found_path:
            collected.append((found_path, "."))
            print(f"[Spec] Found CUDA dependency for STT: {found_path}")
        else:
            print(f"[Spec] Warning: Could not find {dll_name}")
    return collected

if EDITION != "lite":
    binaries.extend(find_cuda_toolkit_dlls())
else:
    print(f"[Spec] [Lite Edition] CUDA Toolkit DLLs excluded from packaging.")

hiddenimports = [
    'winocr',
    'winrt',
    'winrt.system',
    'winrt.windows.foundation',
    'winrt.windows.foundation.collections',
    'winrt.windows.globalization',
    'winrt.windows.graphics.imaging',
    'winrt.windows.media.ocr',
    'winrt.windows.storage.streams',
    'scipy.signal',
    'scipy.special',
    'scipy.spatial.transform._rotation_groups',
    'pygame',
    'psutil',
    'edge_tts',
    'hanja',
    'jinja2',
    'markupsafe',
    'diskcache',
    'typing_extensions',
    'numpy.typing',
    'numpy._typing',
    'transformers',
    'huggingface_hub',
    'aiohttp',
    'requests',
    'deep_translator',
    'llama_cpp',
    'llama_cpp.llama',
    'llama_cpp.llama_types',
    'llama_cpp.llama_cpp',
    'llama_cpp.llama_chat_format',
    'llama_cpp._internals',
    'llama_cpp._ctypes_extensions',
    'llama_cpp._logger',
    'llama_cpp._utils',
]

for pkg in ['proctap', 'soundcard', 'rapidocr_onnxruntime', 'faster_whisper', 'sherpa_onnx', 'deep_translator', 'llama_cpp', 'ctranslate2', 'diskcache', 'jinja2', 'markupsafe']:
    try:
        hiddenimports.extend(collect_submodules(pkg))
    except Exception as e:
        print(f"[Spec] Warning collecting submodules for {pkg}: {e}")

seen_datas = set()
unique_datas = []
for item in datas:
    key = (str(item[0]), str(item[1]))
    if key not in seen_datas:
        seen_datas.add(key)
        unique_datas.append(item)
datas = unique_datas

seen_binaries = set()
unique_binaries = []
for item in binaries:
    key = (str(item[0]), str(item[1]))
    if key not in seen_binaries:
        seen_binaries.add(key)
        unique_binaries.append(item)
binaries = unique_binaries

def is_lite_excluded(path_or_name):
    s = str(path_or_name).lower()
    # 0. STT 모델 디렉토리 제외 (Lite 에디션은 첫 실행 시 인앱 자동 다운로드)
    if 'models--systran' in s or ('models' in s and 'huggingface' in s):
        return True
    # 1. 모든 CUDA 가속 라이브러리 제외 (Lite는 CPU 및 가벼운 Onnxruntime 엔진 사용, 용량 초경량화)
    if any(k in s for k in [
        'cublas64_12', 'cublaslt64_12', 'cudart64_12', 'cudnn64_9',
        'ggml-cuda', 'curand', 'cusparse', 'cufft', 'cusolver', 'npp', 'nvrtc'
    ]):
        return True
    # 2. 개발용 .lib 파일 제외
    if s.endswith('.lib'):
        return True
    return False

def is_full_excluded(path_or_name):
    s = str(path_or_name).lower()
    # Full 에디션에서도 런타임에 필요 없는 개발용 .lib 파일만 제외
    if s.endswith('.lib'):
        return True
    if PRODUCT == "global" and "models--systran--faster-distil-whisper-small.en" in s:
        return True
    if PRODUCT == "kr" and "models--systran--faster-whisper-small" in s and "distil" not in s:
        return True
    return False

if EDITION == "lite":
    filtered_datas = [d for d in datas if not is_lite_excluded(d[0])]
    datas = filtered_datas

    filtered_binaries = [b for b in binaries if not is_lite_excluded(b[0])]
    binaries = filtered_binaries
    print(f"[Spec] [Lite Edition] Pre-Analysis: Total datas: {len(datas)}, Total binaries: {len(binaries)} (Models & CUDA excluded for ultra-lightweight)")
else:
    filtered_datas = [d for d in datas if not is_full_excluded(d[0])]
    datas = filtered_datas

    filtered_binaries = [b for b in binaries if not is_full_excluded(b[0])]
    binaries = filtered_binaries
    print(f"[Spec] [Full Edition] Pre-Analysis: Total datas: {len(datas)}, Total binaries: {len(binaries)} (All CUDA included)")

hiddenimports = list(set(hiddenimports))

a = Analysis(
    ['run.py'],
    pathex=[ROOT_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'IPython', 'jupyter', 'sentencepiece'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# PyInstaller hook 이 설치된 CUDA 빌드 llama_cpp/lib 를 다시 끌어오지 않도록 제거 (llama_cuda/ 로 넣은 것만 유지).
# 의존성 분석이 _internal 루트에 복사하는 llama/ggml DLL 도 제거한다: 부트로더가 _internal 을 DLL 경로로 걸어
# 다른 폴더의 llama.dll 이 루트의 같은 이름 ggml.dll 을 잡게 된다.
_LLAMA_ROOT_NAMES = {'llama.dll', 'llama-common.dll', 'mtmd.dll', 'ggml.dll', 'ggml-base.dll', 'ggml-cpu.dll', 'ggml-cuda.dll'}
def _keep_llama_entry(entry):
    dest = str(entry[0]).replace('\\', '/').lower()
    if '/' not in dest and dest in _LLAMA_ROOT_NAMES:
        return False
    return not is_llama_src_lib(entry[1])
_orig_b, _orig_d = len(a.binaries), len(a.datas)
a.binaries = [b for b in a.binaries if _keep_llama_entry(b)]
a.datas = [d for d in a.datas if _keep_llama_entry(d)]
print(f"[Spec] llama_cpp CUDA lib 재수집 제거: binaries {_orig_b} -> {len(a.binaries)}, datas {_orig_d} -> {len(a.datas)}")

if EDITION == "lite":
    print("[Spec] [Lite Edition] Post-Analysis filtering of a.binaries and a.datas...")
    orig_b = len(a.binaries)
    a.binaries = [
        b for b in a.binaries
        if not is_lite_excluded(b[0]) and not is_lite_excluded(b[1])
    ]
    orig_d = len(a.datas)
    a.datas = [
        d for d in a.datas
        if not is_lite_excluded(d[0]) and not is_lite_excluded(d[1])
    ]
    print(f"[Spec] [Lite Edition] Post-Analysis a.binaries: {orig_b} -> {len(a.binaries)}, a.datas: {orig_d} -> {len(a.datas)}")
else:
    orig_b = len(a.binaries)
    a.binaries = [
        b for b in a.binaries
        if not is_full_excluded(b[0]) and not is_full_excluded(b[1])
    ]
    orig_d = len(a.datas)
    a.datas = [
        d for d in a.datas
        if not is_full_excluded(d[0]) and not is_full_excluded(d[1])
    ]
    print(f"[Spec] [Full Edition] Post-Analysis a.binaries: {orig_b} -> {len(a.binaries)}, a.datas: {orig_d} -> {len(a.datas)}")

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LumiTrans',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 배포판은 콘솔 창 없이 실행. 실시간 로그는 '디버그 모드' 바로가기(--console)로 확인
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT_DIR, 'assets', 'app_icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='LumiTrans',
)
