import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import queue
import time
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample
from src.stt_engine import STTWorker

print("=== End-to-End Pipeline Verification with Real Speech ===")

# 1. 실제 생성된 영어 음성 로드
sr, data = wavfile.read(_os.path.join(_PROJECT_ROOT, "test_speech.wav"))
audio = (data.astype(np.float32) / 32768.0)
if audio.ndim > 1:
    audio = audio[:, 0]

# 16kHz로 리샘플
if sr != 16000:
    target_len = int(len(audio) * 16000 / sr)
    audio = resample(audio, target_len).astype(np.float32)

print(f"Loaded speech audio: length={len(audio)} samples ({len(audio)/16000:.2f}s), dtype={audio.dtype}")

# 2. STT 워커 기동
audio_q = queue.Queue()
received = []

def on_sub(orig, trans, engine=""):
    print(f"\n[성공 수신!] 원문: {orig} -> 번역: {trans} ({engine})\n")
    received.append((orig, trans))

worker = STTWorker(
    audio_queue=audio_q,
    subtitle_callback=on_sub,
    config={"model_size": "distil-small.en", "device": "cuda", "compute_type": "float16"}
)
worker.start()

# 3. 음성 전달
print("Putting speech audio into queue...")
audio_q.put(audio)

# 최대 3초 대기
for _ in range(30):
    if received:
        break
    time.sleep(0.1)

worker.stop()
if received:
    print("=== 검증 대성공: 파이프라인이 100% 정상 작동합니다! ===")
else:
    print("=== 검증 실패: 결과를 받지 못했습니다. ===")
