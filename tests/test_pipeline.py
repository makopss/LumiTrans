import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import queue
import time
import numpy as np
from src.stt_engine import STTWorker
from src.translator import RealtimeTranslator

print("=== 1. 번역 모듈 단독 테스트 ===")
trans = RealtimeTranslator()
test_sentences = [
    "Hello everyone, welcome back to my channel.",
    "Today we are going to explore deep learning in Python.",
    "This is completely free and running on your local RTX GPU."
]
for s in test_sentences:
    ko = trans.translate(s)
    print(f"EN: {s}\nKO: {ko}\n")

print("=== 2. Faster-Whisper + Translator 파이프라인 테스트 ===")
audio_q = queue.Queue()
results = []

def on_subtitle(orig, trans):
    print(f"[Callback 수신] EN: {orig} -> KO: {trans}")
    results.append((orig, trans))

worker = STTWorker(
    audio_queue=audio_q,
    subtitle_callback=on_subtitle,
    config={"model_size": "base.en", "device": "cuda", "compute_type": "float16"}
)
worker.start()

# 1초 분량의 무음/테스트 신호 주입 (환각 필터링 확인)
dummy_silence = np.zeros(16000, dtype=np.float32)
audio_q.put(dummy_silence)
time.sleep(1)

worker.stop()
print("=== 파이프라인 테스트 완료 ===")
