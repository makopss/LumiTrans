"""llama.cpp lib 폴더의 ggml-cpu.dll 이 어떤 CPU 명령어 집합으로 컴파일되었는지 확인한다.

AVX-512 / AVX-VNNI / AMX 로 빌드된 DLL 은 그 명령어가 없는 CPU 에서 모델을 올리는 순간
0xC000001D(STATUS_ILLEGAL_INSTRUCTION) 로 실패한다. 배포용 DLL 은 AVX2 까지만 허용한다.
CUDA 런타임 없이도 확인할 수 있도록 ggml-base.dll, ggml-cpu.dll 만 로드한다. 별도 프로세스에서 실행할 것.

사용법: python scripts/llama_isa_check.py <lib 폴더> [...]
"""
import ctypes
import json
import os
import sys

FEATURES = ["avx", "avx2", "fma", "f16c", "avx_vnni", "avx512", "avx512_vbmi", "avx512_vnni", "avx512_bf16", "amx_int8"]
FORBIDDEN = {"avx_vnni", "avx512", "avx512_vbmi", "avx512_vnni", "avx512_bf16", "amx_int8"}


def check(folder):
    folder = os.path.abspath(folder)
    os.add_dll_directory(folder)
    ctypes.CDLL(os.path.join(folder, "ggml-base.dll"))
    cpu = ctypes.CDLL(os.path.join(folder, "ggml-cpu.dll"))
    flags = {}
    for name in FEATURES:
        fn = getattr(cpu, f"ggml_cpu_has_{name}", None)
        if fn is not None:
            fn.restype = ctypes.c_int
            flags[name] = bool(fn())
    return flags


if __name__ == "__main__":
    ok = True
    for folder in sys.argv[1:]:
        flags = check(folder)
        bad = sorted(k for k, v in flags.items() if v and k in FORBIDDEN)
        print(json.dumps({"folder": folder, "flags": flags, "forbidden": bad}, ensure_ascii=False))
        ok &= not bad
    sys.exit(0 if ok else 2)
