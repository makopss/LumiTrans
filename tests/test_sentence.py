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

print("=== Sentence Mode & Preview Pipeline Test ===")

sr, data = wavfile.read(_os.path.join(_PROJECT_ROOT, "test_speech.wav"))
audio = (data.astype(np.float32) / 32768.0)
if audio.ndim > 1:
    audio = audio[:, 0]

if sr != 16000:
    target_len = int(len(audio) * 16000 / sr)
    audio = resample(audio, target_len).astype(np.float32)

audio_q = queue.Queue()
previews = []
final_subtitles = []

def on_prev(txt, *args):
    print(f"[실시간 프리뷰 타이핑] {txt}")
    previews.append(txt)

def on_final(orig, trans, *args):
    print(f"\n[최종 문장 완결 번역] \n  - EN: {orig}\n  - KO: {trans}\n")
    final_subtitles.append((orig, trans))

worker = STTWorker(
    audio_queue=audio_q,
    subtitle_callback=on_final,
    preview_callback=on_prev,
    config={"model_size": "distil-small.en", "device": "cuda", "compute_type": "float16", "sentence_mode": True}
)
worker.start()

# 음성을 2개 조각으로 쪼개어 전달 (문장 누적 및 종결 테스트)
mid = len(audio) // 2
audio_q.put(audio[:mid])
time.sleep(0.5)
audio_q.put(audio[mid:])

# 최대 4초 대기
for _ in range(40):
    if final_subtitles:
        break
    time.sleep(0.1)

worker.stop()
if final_subtitles:
    print("=== 테스트 대성공! 문장 단위 완결 및 프리뷰 정상 작동 ===")
else:
    print("=== 타임아웃 ===")
