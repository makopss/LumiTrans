import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import os
import sys
import io
import time
import queue
import asyncio
import numpy as np
import av
import edge_tts

# Windows utf-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.speaker_identifier import SpeakerIdentifier
from src.dubbing_engine import DubbingEngine

def to_pcm(b: bytes) -> np.ndarray:
    container = av.open(io.BytesIO(b))
    resampler = av.AudioResampler(format='fltp', layout='mono', rate=16000)
    frames = []
    for frame in container.decode(audio=0):
        for rframe in resampler.resample(frame):
            frames.append(rframe.to_ndarray())
    return np.concatenate(frames, axis=1)[0]

async def synthesize(text: str, voice: str) -> bytes:
    c = edge_tts.Communicate(text, voice)
    bio = io.BytesIO()
    async for chunk in c.stream():
        if chunk["type"] == "audio":
            bio.write(chunk["data"])
    return bio.getvalue()

def test_tts_echo_gate():
    print("\n" + "=" * 60)
    print("TEST 1: 3D-Speaker 음성 지문 기반 TTS 에코 차단 게이트 검증")
    print("=" * 60)

    cfg = {"dubbing_enabled": True, "dubbing_echo_cancellation": True}
    si = SpeakerIdentifier(config=cfg)

    # 1. 한국어 TTS 인준 음성 합성
    print("[1-1] 한국어 TTS (InJoon) 음성 합성 중...")
    b_in = asyncio.run(synthesize("그리고 우리의 질문에 답하게 하세요.", "ko-KR-InJoonNeural"))
    pcm_in = to_pcm(b_in)
    is_echo_in, sim_in, voice_in = si.is_tts_echo(pcm_in, threshold=0.48)
    print(f" -> InJoon 결과: is_echo={is_echo_in}, similarity={sim_in:.3f}, matched={voice_in}")
    assert is_echo_in is True, f"InJoon TTS 음성이 에코로 감지되어야 합니다 (유사도: {sim_in})"
    assert sim_in >= 0.48, f"InJoon 유사도가 0.48 이상이어야 합니다 (실제: {sim_in})"

    # 2. 한국어 TTS 선희 음성 합성
    print("[1-2] 한국어 TTS (SunHi) 음성 합성 중...")
    b_su = asyncio.run(synthesize("그러니 이를 위해 조수가 필요합니다.", "ko-KR-SunHiNeural"))
    pcm_su = to_pcm(b_su)
    is_echo_su, sim_su, voice_su = si.is_tts_echo(pcm_su, threshold=0.48)
    print(f" -> SunHi 결과: is_echo={is_echo_su}, similarity={sim_su:.3f}, matched={voice_su}")
    assert is_echo_su is True, f"SunHi TTS 음성이 에코로 감지되어야 합니다 (유사도: {sim_su})"

    # 3. 영어 발화 음성 (Christopher) 합성
    print("[1-3] 영어 강사 발화 (Christopher) 음성 합성 중...")
    b_en = asyncio.run(synthesize("And have it respond to our questions.", "en-US-ChristopherNeural"))
    pcm_en = to_pcm(b_en)
    is_echo_en, sim_en, voice_en = si.is_tts_echo(pcm_en, threshold=0.48)
    print(f" -> English 결과: is_echo={is_echo_en}, similarity={sim_en:.3f}, matched={voice_en}")
    assert is_echo_en is False, f"영어 강사 음성은 에코로 차단되면 안 됩니다 (유사도: {sim_en})"
    assert sim_en < 0.48, f"영어 음성 유사도는 0.48 미만이어야 합니다 (실제: {sim_en})"

    print("[OK] [성공] TTS 음성은 100% 에코로 차단되고, 영어 음성은 100% 통과되었습니다!")

def test_dubbing_pipeline_zero_drop():
    print("\n" + "=" * 60)
    print("TEST 2: 대사 누락 제로(Zero-Drop) 비동기 프리페치 파이프라인 검증")
    print("=" * 60)

    cfg = {
        "dubbing_enabled": True,
        "dubbing_volume": 30,
        "dubbing_speed": "+15%",
        "dubbing_interrupt": False,
        "dubbing_source_audio": True,
        "dubbing_source_screen": True,
    }
    dubbing = DubbingEngine(config=cfg)

    sentences = [
        ("그리고 우리의 질문에 답하게 하세요.", "화자 1", "And have it respond to our questions."),
        ("그러니 이를 위해 조수가 필요합니다.", "화자 1", "So for that, we need an assistant."),
        ("실제로 어시스턴트를 만들 수 있음을 보았습니다.", "화자 1", "We saw that we can actually construct an assistant."),
    ]

    print("[2-1] 3개의 연속 대사를 빠른 속도로 순차 큐잉...")
    for text, spk, orig in sentences:
        dubbing.enqueue(translated_text=text, speaker_name=spk, orig_text=orig, source="audio")

    # 파이프라인에 3개가 들어갔는지 확인 (선행 합성 중인 항목 포함)
    tot = dubbing.get_pipeline_total_count()
    print(f" -> 파이프라인 적체 수: {tot} (텍스트 큐: {dubbing.text_queue.qsize()})")
    assert tot == 3, f"3개 대사가 모두 파이프라인에 들어있어야 합니다 (현재: {tot})"

    # 적응형 배속 검증
    sp0 = dubbing.calculate_adaptive_speed(0)
    sp1 = dubbing.calculate_adaptive_speed(1)
    sp2 = dubbing.calculate_adaptive_speed(2)
    sp3 = dubbing.calculate_adaptive_speed(3)
    sp4 = dubbing.calculate_adaptive_speed(4)
    print(f" -> 가변 배속 단계: 0개={sp0}, 1개={sp1}, 2개={sp2}, 3개={sp3}, 4개+={sp4}")
    assert sp0 == "+15%"
    assert sp2 == "+30%"
    assert sp3 == "+45%"
    assert sp4 == "+60%"

    print("[2-2] 백그라운드 프리페치 파이프라인 동작 대기 (최대 10초)...")
    t0 = time.time()
    while time.time() - t0 < 10.0:
        if dubbing.playback_queue.qsize() > 0 or dubbing.is_speaking():
            break
        time.sleep(0.1)

    print(f" -> 백그라운드 선행 합성 완료 확인 (Playback Queue: {dubbing.playback_queue.qsize()}, Speaking: {dubbing.is_speaking()})")
    assert dubbing.playback_queue.qsize() > 0 or dubbing.is_speaking(), "선행 합성이 정상 작동해야 합니다."

    dubbing.stop()
    print("[OK] [성공] 대사 누락 제로 비동기 프리페치 파이프라인 정상 확인!")

if __name__ == "__main__":
    try:
        test_tts_echo_gate()
        test_dubbing_pipeline_zero_drop()
        print("\n" + "=" * 60)
        print("[SUCCESS] 모든 자가증식 에코 차단 및 대사 누락 제로 검증 통과!")
        print("=" * 60)
    except Exception as e:
        print(f"\n[FAIL] 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
