"""
LumiTrans Windows Installer Automated Build Script (Full & Lite Editions)
------------------------------------------------------------------------------
Automates:
1. App icon generation (.ico)
2. PyInstaller packaging (onedir standalone bundle, Full/Lite edition)
3. Inno Setup installer compilation (Setup.exe for Full/Lite)
4. Integrity and output verification
"""

import os
import sys
import shutil
import subprocess
import time
import argparse
from pathlib import Path
from PIL import Image

# Windows 콘솔 UTF-8 출력 보장
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[1]
os.chdir(ROOT_DIR)

def print_step(step: str):
    print(f"\n{'=' * 60}\n>> {step}\n{'=' * 60}")

def find_iscc() -> str:
    # Check PATH
    iscc_path = shutil.which("iscc") or shutil.which("ISCC.exe")
    if iscc_path and os.path.exists(iscc_path):
        return iscc_path

    # Common installation paths
    user_appdata = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")

    candidates = [
        os.path.join(user_appdata, "Programs", "Inno Setup 6", "ISCC.exe"),
        os.path.join(user_appdata, "Programs", "Inno Setup 7", "ISCC.exe"),
        os.path.join(program_files, "Inno Setup 6", "ISCC.exe"),
        os.path.join(program_files_x86, "Inno Setup 6", "ISCC.exe"),
        os.path.join(program_files, "Inno Setup 7", "ISCC.exe"),
        os.path.join(program_files_x86, "Inno Setup 7", "ISCC.exe"),
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return ""

def patch_scipy_python312_bug():
    """Python 3.12.0 + SciPy + PyInstaller frozen bug (NameError: name 'obj' is not defined) 자동 패치"""
    try:
        import scipy.stats._distn_infrastructure as distn
        p = getattr(distn, "__file__", "")
        if p and os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            target = "del obj"
            if target in content and "try:\n    del obj\nexcept NameError:\n    pass" not in content:
                print("[Patch] SciPy Python 3.12.0 NameError('obj') 버그 패치 적용 중...")
                patched = content.replace("del obj", "try:\n    del obj\nexcept NameError:\n    pass", 1)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(patched)
                print("[Patch] SciPy 패치 완료!")
    except Exception as e:
        print(f"[Patch] SciPy 패치 확인 중 오류 (무시 가능): {e}")

def patch_pyinstaller_sentencepiece_bug():
    """Python 3.12 + PyInstaller isolated process crash on sentencepiece import (0xC0000005) 자동 패치"""
    try:
        import PyInstaller.building.build_main as bm
        p = getattr(bm, "__file__", "")
        if p and os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            target = "suppressed_imports += ['PySimpleGUI']"
            patch = "suppressed_imports += ['PySimpleGUI']\n        suppressed_imports += ['sentencepiece']"
            if target in content and "suppressed_imports += ['sentencepiece']" not in content:
                print("[Patch] PyInstaller sentencepiece 크래시 방지 패치 적용 중...")
                patched = content.replace(target, patch, 1)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(patched)
                print("[Patch] PyInstaller sentencepiece 패치 완료!")
    except Exception as e:
        print(f"[Patch] PyInstaller 패치 확인 중 오류 (무시 가능): {e}")

def generate_icon():
    ico_path = ROOT_DIR / "assets" / "app_icon.ico"
    splash_path = ROOT_DIR / "assets" / "splash.png"

    if ico_path.exists():
        print(f"[Icon] 이미 아이콘이 존재합니다: {ico_path} ({ico_path.stat().st_size:,} bytes)")
        return

    print("[Icon] splash.png로부터 app_icon.ico 생성 중...")
    if not splash_path.exists():
        raise FileNotFoundError(f"splash.png가 없습니다: {splash_path}")

    img = Image.open(splash_path)
    w, h = img.size
    min_dim = min(w, h)
    left = (w - min_dim) // 2
    top = (h - min_dim) // 2
    cropped = img.crop((left, top, left + min_dim, top + min_dim))
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    cropped.save(ico_path, sizes=icon_sizes)
    print(f"[Icon] 아이콘 생성 완료: {ico_path} ({ico_path.stat().st_size:,} bytes)")

def ensure_bundled_stt_model():
    """빌드 전 필수 기본 내장 번들 STT 모델(distil-small.en) 존재 여부 검사 및 자동 준비"""
    bundled_target = ROOT_DIR / "models" / "huggingface" / "hub" / "models--Systran--faster-distil-whisper-small.en"
    if (bundled_target / "snapshots").exists():
        print(f"[Model Bundle] 기본 내장 distil-small.en 모델 확인됨: {bundled_target}")
        return

    print("[Model Bundle] distil-small.en 번들 모델 준비 중...")
    candidate_sources = [
        Path(r"D:\AI_Models\huggingface\hub\models--Systran--faster-distil-whisper-small.en"),
        Path(os.path.expanduser(r"~/.cache/huggingface/hub/models--Systran--faster-distil-whisper-small.en")),
    ]
    for src in candidate_sources:
        if src.exists() and (src / "snapshots").exists():
            print(f"[Model Bundle] 로컬 소스({src})로부터 모델 복사 중...")
            bundled_target.mkdir(parents=True, exist_ok=True)
            for sub in ['refs', 'snapshots']:
                s_sub = src / sub
                d_sub = bundled_target / sub
                if s_sub.exists():
                    shutil.copytree(str(s_sub), str(d_sub), dirs_exist_ok=True)
            for f in src.iterdir():
                if f.is_file():
                    shutil.copy2(str(f), str(bundled_target / f.name))
            print("[Model Bundle] 복사 완료!")
            return

    # 로컬에 없을 시 faster-whisper로 직접 다운로드
    print("[Model Bundle] 로컬 캐시 없음. Hugging Face에서 distil-small.en 다운로드 중...")
    from faster_whisper import download_model
    download_model("Systran/faster-distil-whisper-small.en", output_directory=str(ROOT_DIR / "models" / "huggingface" / "hub"))
    print("[Model Bundle] 다운로드 완료!")

# 로컬에서 빌드한 llama-cpp-python 은 빌드 PC 의 CPU 명령어(AVX-512 등)로 컴파일되어 다른 PC 에서
# 0xC000001D 로 죽는다. 번들에는 항상 공식 배포 wheel 의 DLL 만 넣는다.
LLAMA_WHEEL_URL = "https://github.com/abetlen/llama-cpp-python/releases/download/v{tag}/llama_cpp_python-{ver}-py3-none-win_amd64.whl"
LLAMA_CUDA_FLAVOR = "cu124"   # Full 에 함께 넣는 cuBLAS/cudart 12.4 와 짝


def _ensure_official_llama_libs(flavor: str, required: list) -> Path:
    import importlib.metadata
    import zipfile
    import urllib.request
    ver = importlib.metadata.version("llama_cpp_python")
    target = ROOT_DIR / "vendor" / f"llama_cpp_{flavor}" / ver
    if all((target / n).exists() for n in required):
        print(f"[llama {flavor}] 공식 llama.cpp 라이브러리 확인됨: {target}")
        return target

    tag = ver if flavor == "cpu" else f"{ver}-{flavor}"
    url = LLAMA_WHEEL_URL.format(tag=tag, ver=ver)
    print(f"[llama {flavor}] 공식 llama.cpp {ver} 라이브러리 다운로드 중: {url}")
    target.mkdir(parents=True, exist_ok=True)
    whl = target / "_download.whl"
    urllib.request.urlretrieve(url, str(whl))
    with zipfile.ZipFile(str(whl)) as z:
        for item in z.namelist():
            if item.startswith("llama_cpp/lib/") and item.lower().endswith(".dll"):
                with z.open(item) as src, open(target / os.path.basename(item), "wb") as dst:
                    shutil.copyfileobj(src, dst)
    whl.unlink()
    missing = [n for n in required if not (target / n).exists()]
    if missing:
        raise RuntimeError(f"공식 llama.cpp {flavor} 라이브러리 구성이 올바르지 않습니다 (누락: {missing})")
    print(f"[llama {flavor}] 준비 완료: {sorted(p.name for p in target.iterdir())}")
    return target


def ensure_llama_cpu_libs() -> Path:
    """두 에디션의 기본 llama_cpp/lib 에 넣는 CPU 전용 DLL (NVIDIA 가 없는 PC 에서도 로드된다)."""
    target = _ensure_official_llama_libs("cpu", ["llama.dll", "ggml.dll", "ggml-base.dll", "ggml-cpu.dll"])
    if (target / "ggml-cuda.dll").exists():
        raise RuntimeError("CPU 전용 llama.cpp 라이브러리에 ggml-cuda.dll 이 들어 있습니다.")
    return target


def ensure_llama_cuda_libs() -> Path:
    """Full 에디션의 llama_cuda/ 에 넣는 공식 CUDA 12.4 빌드 DLL.
    공식 CUDA wheel 의 ggml-cpu.dll 은 AVX-512 로 빌드되어 있어 같은 버전 CPU 전용 wheel 의 AVX2 판으로 바꾼다.
    (AVX-512 코드는 ggml-cpu.dll 에만 있고, 두 ggml-cpu.dll 의 export/import 는 동일하다.)"""
    target = _ensure_official_llama_libs(LLAMA_CUDA_FLAVOR, ["llama.dll", "ggml.dll", "ggml-base.dll", "ggml-cpu.dll", "ggml-cuda.dll"])
    shutil.copy2(ensure_llama_cpu_libs() / "ggml-cpu.dll", target / "ggml-cpu.dll")
    return target


def verify_llama_cpu_isa(folders: list):
    """번들 DLL 이 AVX2 까지만 쓰는지 별도 프로세스에서 확인한다 (AVX-512 등이 있으면 다른 PC 에서 0xC000001D)."""
    checker = ROOT_DIR / "scripts" / "llama_isa_check.py"
    res = subprocess.run([sys.executable, str(checker)] + [str(f) for f in folders],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(res.stdout.strip())
    if res.returncode != 0:
        raise RuntimeError(f"llama.cpp DLL 이 AVX2 를 넘는 CPU 명령어로 빌드되었습니다. 다른 PC 에서 0xC000001D 로 실패합니다.\n{res.stderr}")
    # 컴파일 설정 플래그와 별개로 실제 기계어에 AVX-512 명령어가 섞였는지 디스어셈블해 확인한다.
    scanner = ROOT_DIR / "scripts" / "scan_avx512.py"
    res = subprocess.run([sys.executable, str(scanner)] + [str(f) for f in folders],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(res.stdout.strip())
    if res.returncode == 2:
        raise RuntimeError("llama.cpp DLL 기계어에 AVX-512 명령어가 있습니다. AVX-512 가 없는 CPU 에서 0xC000001D 로 실패합니다.")
    if res.returncode != 0:
        raise RuntimeError(f"AVX-512 기계어 검사를 실행하지 못했습니다 (pip install capstone pefile):\n{res.stderr[-800:]}")


def verify_llama_layout(edition: str):
    """번들의 llama_cpp/lib 가 CPU 전용인지, Full 에는 CUDA 라이브러리가 별도 폴더에 있는지 확인한다."""
    internal = ROOT_DIR / "dist" / "LumiTrans" / "_internal"
    cpu_lib = internal / "llama_cpp" / "lib"
    if not (cpu_lib / "llama.dll").exists():
        raise RuntimeError(f"llama_cpp/lib/llama.dll 이 번들에 없습니다: {cpu_lib}")
    if (cpu_lib / "ggml-cuda.dll").exists():
        raise RuntimeError("llama_cpp/lib 에 ggml-cuda.dll 이 들어갔습니다. NVIDIA 가 없는 PC 에서 로컬 LLM 이 로드되지 않습니다.")
    root_copies = [n for n in ("llama.dll", "ggml.dll", "ggml-base.dll", "ggml-cpu.dll", "ggml-cuda.dll", "mtmd.dll")
                   if (internal / n).exists()]
    if root_copies:
        raise RuntimeError(f"_internal 루트에 llama.cpp DLL 이 복사되었습니다 (CUDA 라이브러리와 섞임): {root_copies}")
    cuda_lib = internal / "llama_cuda" / "ggml-cuda.dll"
    if edition == "full" and not cuda_lib.exists():
        raise RuntimeError(f"Full 에디션에 CUDA llama.cpp 라이브러리가 없습니다: {cuda_lib}")
    if edition == "lite" and (internal / "llama_cuda").exists():
        raise RuntimeError("Lite 에디션에 llama_cuda 폴더가 포함되었습니다.")
    verify_llama_cpu_isa([cpu_lib] + ([internal / "llama_cuda"] if edition == "full" else []))
    print(f"[Verify] llama.cpp 라이브러리 구성 정상 (기본: CPU 전용{', CUDA: llama_cuda/' if edition == 'full' else ''})")


def run_pyinstaller(edition: str = "full"):
    edition_label = "라이트(Lite) 에디션" if edition == "lite" else "풀(Full) 에디션"
    print_step(f"1단계: PyInstaller를 통한 [{edition_label}] 번들 패키징 시작")
    spec_path = ROOT_DIR / "LumiTrans.spec"
    if not spec_path.exists():
        raise FileNotFoundError(f"Spec 파일이 없습니다: {spec_path}")

    env = os.environ.copy()
    env["WISE_EDITION"] = edition
    env["WISE_LLAMA_CPU_DIR"] = str(ensure_llama_cpu_libs())
    if edition != "lite":
        env["WISE_LLAMA_CUDA_DIR"] = str(ensure_llama_cuda_libs())
    dist_target = ROOT_DIR / "dist" / "LumiTrans"
    if dist_target.exists():
        print(f"[PyInstaller] 이전 dist 디렉터리 정리 중: {dist_target}")
        shutil.rmtree(str(dist_target), ignore_errors=True)
    build_target = ROOT_DIR / "build" / "LumiTrans"
    if build_target.exists():
        print(f"[PyInstaller] 이전 build 디렉터리 정리 중: {build_target}")
        shutil.rmtree(str(build_target), ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_path)
    ]
    print(f"빌드 에디션: {edition.upper()} | 실행 명령: {' '.join(cmd)}")
    start_t = time.time()
    res = subprocess.run(cmd, cwd=str(ROOT_DIR), env=env)
    elapsed = time.time() - start_t

    if res.returncode != 0:
        raise RuntimeError(f"PyInstaller 빌드 실패 (코드: {res.returncode})")

    # 번들 무결성 확인
    exe_path = ROOT_DIR / "dist" / "LumiTrans" / "LumiTrans.exe"
    if not exe_path.exists():
        raise FileNotFoundError(f"생성된 실행 파일이 없습니다: {exe_path}")

    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"[PyInstaller] [{edition_label}] 번들 빌드 성공! ({elapsed:.1f}초 소요)")
    print(f"[PyInstaller] 실행 파일: {exe_path} ({size_mb:.2f} MB)")

    # 에디션별 사후 번들 파일 정리 및 검증
    dist_dir = ROOT_DIR / "dist" / "LumiTrans"
    if edition == "lite":
        # 1. Lite 에디션: STT 번들 모델 디렉토리 완전 제외 (첫 실행 시 인앱 자동 다운로드)
        for cand_models in [dist_dir / "models", dist_dir / "_internal" / "models"]:
            if cand_models.exists():
                print(f"[Lite Cleanup] STT 번들 모델 제외 처리: {cand_models}")
                shutil.rmtree(str(cand_models), ignore_errors=True)

        # 2. Lite 에디션: 모든 CUDA 가속 라이브러리 및 불필요한 .lib 파일 정리
        def should_clean_lite(file_name, file_path=""):
            fn = file_name.lower()
            if any(k in fn for k in [
                'cublas64_12', 'cublaslt64_12', 'cudart64_12', 'cudnn64_9',
                'ggml-cuda', 'curand', 'cusparse', 'cufft', 'cusolver', 'npp', 'nvrtc'
            ]) or fn.endswith(".lib"):
                return True
            return False

        cleaned_size = 0
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                if should_clean_lite(file, root):
                    p = os.path.join(root, file)
                    try:
                        sz = os.path.getsize(p)
                        os.remove(p)
                        cleaned_size += sz
                        print(f"[Lite Cleanup] CUDA/lib 파일 제외 확인: {file} ({sz / (1024*1024):.1f} MB)")
                    except Exception as e:
                        print(f"[Lite Cleanup] 제거 실패 ({file}): {e}")
        if cleaned_size > 0:
            print(f"[Lite Cleanup] 총 {cleaned_size / (1024*1024):.1f} MB가 Lite 번들에서 정상 제외되었습니다.")
    else:
        # Full 에디션: 번들 모델 중복 복사 방지 및 단일화 검증
        internal_models = dist_dir / "_internal" / "models"
        root_models = dist_dir / "models"
        has_internal = (internal_models / "huggingface" / "hub" / "models--Systran--faster-distil-whisper-small.en").exists()
        has_root = (root_models / "huggingface" / "hub" / "models--Systran--faster-distil-whisper-small.en").exists()

        if has_internal and has_root:
            # 중복 제거: PyInstaller datas(_internal/models)에 이미 존재하므로 dist_dir/models 삭제
            print(f"[Full Bundle] 중복 모델 감지: {root_models} 제거 (설치 패키지 320MB 중복 절감)")
            shutil.rmtree(str(root_models), ignore_errors=True)
        elif not has_internal and not has_root:
            models_src = ROOT_DIR / "models"
            if models_src.exists():
                print(f"[Full Bundle] 번들 STT 모델을 {root_models}에 동기화합니다...")
                shutil.copytree(str(models_src), str(root_models), dirs_exist_ok=True)
                print("[Full Bundle] 번들 STT 모델 복사 완료!")

    verify_llama_layout(edition)

    # 전체 번들 크기 측정 및 출력
    total_bundle_bytes = sum(
        os.path.getsize(os.path.join(r, f))
        for r, d, files in os.walk(dist_dir)
        for f in files
    )
    print(f"[PyInstaller] 최종 압축 전 번들 크기: {total_bundle_bytes / (1024 * 1024):.1f} MB")

def run_innosetup(edition: str = "full") -> Path:
    edition_cap = edition.capitalize()
    edition_label = "라이트(Lite) 에디션" if edition == "lite" else "풀(Full) 에디션"
    print_step(f"2단계: Inno Setup을 통한 [{edition_label}] 단일 설치 파일 컴파일")
    iscc = find_iscc()
    if not iscc:
        raise RuntimeError("Inno Setup 컴파일러(ISCC.exe)를 찾을 수 없습니다. 설치 상태를 확인하세요.")

    print(f"Inno Setup 컴파일러: {iscc}")
    iss_path = ROOT_DIR / "installer.iss"
    if not iss_path.exists():
        raise FileNotFoundError(f"Installer 스크립트가 없습니다: {iss_path}")

    output_dir = ROOT_DIR / "installer_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [iscc, f"/DEdition={edition_cap}", str(iss_path)]
    print(f"실행 명령: {' '.join(cmd)}")
    start_t = time.time()
    res = subprocess.run(cmd, cwd=str(ROOT_DIR))
    elapsed = time.time() - start_t

    if res.returncode != 0:
        raise RuntimeError(f"Inno Setup 컴파일 실패 (코드: {res.returncode})")

    # 결과 검증
    setup_path = output_dir / f"LumiTrans_{edition_cap}_Setup_v1.0.0.exe"
    if not setup_path.exists():
        raise FileNotFoundError(f"생성된 설치 파일이 없습니다: {setup_path}")

    size_mb = setup_path.stat().st_size / (1024 * 1024)
    print(f"[Inno Setup] [{edition_label}] 설치 파일 빌드 완료! ({elapsed:.1f}초 소요)")
    print(f"[결과] 설치 파일 위치: {setup_path}")
    print(f"[결과] 최종 설치 파일 용량: {size_mb:.2f} MB")
    return setup_path

def build_single_edition(edition: str) -> Path:
    edition_label = "라이트(Lite - 약 190~220MB)" if edition == "lite" else "풀(Full - 약 750~800MB)"
    print("\n" + "#" * 60)
    print(f"### [LumiTrans] {edition_label} 빌드 파이프라인 가동")
    print("#" * 60)
    start_t = time.time()
    run_pyinstaller(edition=edition)
    out_file = run_innosetup(edition=edition)
    elapsed = time.time() - start_t
    print(f"\n>> [{edition.upper()}] 에디션 완료 (소요: {elapsed:.1f}초)")
    return out_file

def main():
    parser = argparse.ArgumentParser(description="LumiTrans Windows Installer Automated Builder")
    parser.add_argument(
        "--edition",
        choices=["lite", "full", "all"],
        default="all",
        help="빌드할 에디션 선택 (lite: 라이트 버전, full: 풀 버전, all: 둘 다 빌드, 기본값: lite)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"[BUILD] 루미트랜스 (LumiTrans) - 윈도우 설치 버전 빌드 시작")
    print(f"[TARGET] 선택된 빌드 대상: {args.edition.upper()}")
    print("=" * 60)

    total_start = time.time()
    patch_scipy_python312_bug()
    patch_pyinstaller_sentencepiece_bug()
    generate_icon()
    ensure_bundled_stt_model()

    built_files = []
    if args.edition in ("lite", "all"):
        f = build_single_edition("lite")
        built_files.append(("Lite", f))

    if args.edition in ("full", "all"):
        f = build_single_edition("full")
        built_files.append(("Full", f))

    total_elapsed = time.time() - total_start

    print("\n" + "=" * 60)
    print(f"[SUCCESS] 모든 빌드 파이프라인이 성공적으로 완료되었습니다! (총 {total_elapsed:.1f}초 소요)")
    for label, path in built_files:
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f" - [{label} 버전]: {path.name} ({size_mb:.2f} MB) -> {path}")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] 빌드 중 오류 발생: {e}", file=sys.stderr)
        sys.exit(1)
