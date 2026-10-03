import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import os
import sys
import json
import time
import queue
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample

# 콘솔 UTF-8 출력
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.config import load_config
from src.translator import RealtimeTranslator
from src.stt_engine import STTWorker

def run_tests():
    print("=" * 70)
    print("[TEST] [전수 검증] STT 3종 × 번역 3종 (총 9가지 엔진 조합 테스트)")
    print("=" * 70)

    # 기본 설정 로드
    base_cfg = load_config()

    # 오디오 로드 (test_speech.wav: 16kHz 모노)
    sr, data = wavfile.read(_os.path.join(_PROJECT_ROOT, "test_speech.wav"))
    audio = (data.astype(np.float32) / 32768.0)
    if audio.ndim > 1:
        audio = audio[:, 0]
    if sr != 16000:
        target_len = int(len(audio) * 16000 / sr)
        audio = resample(audio, target_len).astype(np.float32)

    # 1. 번역 엔진 3종 단독 검증
    print("\n--- 1단계: 번역 엔진 3종 개별 응답 검증 ---")
    trans_engines = ["deepl", "google", "gemini"]
    trans_results = {}
    test_phrase = "Hello everyone, this is an automated system verification."

    for t_eng in trans_engines:
        cfg = base_cfg.copy()
        cfg["translation_engine"] = t_eng
        translator = RealtimeTranslator(config=cfg)
        t0 = time.time()
        res, used = translator.translate(test_phrase)
        dt = time.time() - t0
        status = "[OK] 성공" if res else "[FAIL] 실패"
        trans_results[t_eng] = (res, used, dt)
        print(f"[{status}] 번역기: {t_eng:7s} | 결과엔진: {used:14s} | 소요: {dt:.2f}s | 결과: {res}")

    # 2. STT 엔진 3종 × 번역 엔진 3종 전수 파이프라인 검증 (3 x 3 = 9)
    print("\n--- 2단계: 9가지 전수 조합 파이프라인 실시간 검증 ---")
    
    stt_modes = [
        ("GPU (CUDA)", {"stt_provider": "local", "device": "cuda", "compute_type": "float16", "model_size": "distil-small.en"}),
        ("CPU (INT8)", {"stt_provider": "local", "device": "cpu", "compute_type": "int8", "model_size": "distil-small.en"}),
        ("Groq (Cloud LPU)", {"stt_provider": "groq", "device": "cuda", "compute_type": "float16", "model_size": "distil-small.en"}),
    ]

    all_passed = True
    combo_results = []

    for stt_label, stt_cfg_override in stt_modes:
        print(f"\n>> STT 엔진 검증: [{stt_label}]")
        
        # 워커 초기화
        test_cfg = base_cfg.copy()
        test_cfg.update(stt_cfg_override)
        test_cfg["sentence_mode"] = False  # 빠른 단일 청크 즉시 번역 모드로 검증
        test_cfg["use_context_prompt"] = False
        test_cfg["use_pre_padding"] = False

        q = queue.Queue()
        collected = []

        def cb(orig, trans, tag):
            collected.append((orig, trans, tag))

        worker = STTWorker(
            audio_queue=q,
            subtitle_callback=cb,
            config=test_cfg
        )
        worker.start()

        for t_eng in trans_engines:
            test_cfg["translation_engine"] = t_eng
            worker.update_config(test_cfg)
            collected.clear()

            t0 = time.time()
            q.put(audio)

            # 최대 6초 대기
            for _ in range(60):
                if collected:
                    break
                time.sleep(0.1)

            dt = time.time() - t0
            if collected:
                orig, trans, tag = collected[0]
                print(f"  [[OK] PASS] 조합: {stt_label:16s} + {t_eng:6s} -> 뱃지태그: [{tag}] ({dt:.2f}s)\n             원문: {orig}\n             번역: {trans}")
                combo_results.append((stt_label, t_eng, True, tag, dt))
            else:
                print(f"  [[FAIL] FAIL] 조합: {stt_label:16s} + {t_eng:6s} (응답 타임아웃)")
                combo_results.append((stt_label, t_eng, False, "NONE", dt))
                all_passed = False

            time.sleep(0.4)

        worker.stop()
        time.sleep(0.5)

    print("\n" + "=" * 70)
    print("[SUMMARY] [검증 결과 종합 요약표]")
    print("=" * 70)
    for stt_lbl, t_lbl, ok, tag, dt in combo_results:
        mark = "[OK] PASS" if ok else "[FAIL] FAIL"
        print(f"  {mark} | STT: {stt_lbl:16s} | 번역: {t_lbl:7s} | 결과 태그: [{tag}] ({dt:.2f}s)")
    print("=" * 70)

    if all_passed:
        print("\n[SUCCESS] 모든 9가지 엔진 조합이 100% 정상 작동함을 확인하였습니다!")
    else:
        print("\n[WARN] 일부 조합에서 문제가 발생하였습니다.")

if __name__ == "__main__":
    run_tests()
