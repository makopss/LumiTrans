"""DLL 실행 코드(.text 등)를 디스어셈블해 AVX-512 명령어(zmm 레지스터, k 마스크 레지스터) 사용 수를 센다.

ggml_cpu_has_avx512() 는 ggml-cpu.dll 의 컴파일 설정만 알려 주므로, 다른 DLL 에 AVX-512 코드가 섞였는지는
이 스캐너로 확인한다. 결과가 0 이 아니면 AVX-512 가 없는 CPU 에서 해당 코드가 실행될 때 0xC000001D 가 날 수 있다.

사용법: python scripts/scan_avx512.py <dll 또는 폴더> [...]
"""
import glob
import os
import re
import sys

import pefile
from capstone import CS_ARCH_X86, CS_MODE_64, Cs

AVX512_OPERAND = re.compile(r"\bzmm\d+\b|\{k[1-7]\}|\bk[0-7]\b")


def scan(path):
    pe = pefile.PE(path, fast_load=True)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.skipdata = True
    hits = 0
    for sec in pe.sections:
        if not sec.Characteristics & 0x20000000:   # IMAGE_SCN_MEM_EXECUTE
            continue
        data = sec.get_data()
        for _addr, _size, mnemonic, op_str in md.disasm_lite(data, sec.VirtualAddress):
            if mnemonic.startswith("k") and mnemonic[1:4] in ("mov", "and", "or", "xor", "not", "tes", "shi", "unp", "add", "ort"):
                hits += 1
            elif AVX512_OPERAND.search(op_str):
                hits += 1
    return hits


if __name__ == "__main__":
    total = 0
    for arg in sys.argv[1:]:
        files = sorted(glob.glob(os.path.join(arg, "*.dll"))) if os.path.isdir(arg) else [arg]
        for f in files:
            n = scan(f)
            total += n
            print(f"{n:8d}  {f}")
    sys.exit(0 if total == 0 else 2)
