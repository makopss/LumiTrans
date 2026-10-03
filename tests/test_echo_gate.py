import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import time
import queue
import numpy as np
from src.dubbing_engine import DubbingEngine
from src.audio_capture import AudioLoopbackCapture

def test_dubbing_echo_gate():
    config = {
        "dubbing_enabled": True,
        "dubbing_echo_cancellation": True,
        "dubbing_volume": 80,
        "dubbing_source_audio": True,
        "dubbing_source_screen": True,
        "dubbing_interrupt": True,
        "speaker_diarization_enabled": False
    }

    engine = DubbingEngine(config)
    
    # 1. 초기 상태: 발화 중이 아님
    assert not engine.is_speaking(), "초기 상태는 is_speaking() == False 여야 합니다."

    # 2. _is_playing 플래그 활성화 시 is_speaking() == True
    engine._is_playing = True
    assert engine.is_speaking(), "재생 중일 때는 is_speaking() == True 여야 합니다."

    # 3. 재생 종료 직후 (잔향 버퍼 0.25초 이내)
    engine._is_playing = False
    engine.last_playback_end_time = time.time()
    assert engine.is_speaking(), "재생 종료 직후 잔향 버퍼 시간 동안은 is_speaking() == True 여야 합니다."

    # 4. 잔향 시간 경과 후
    engine.last_playback_end_time = time.time() - 2.5
    assert not engine.is_speaking(), "2.0초 경과 후에는 is_speaking() == False 여야 합니다."

    # 5. 중복 대사 방지 (Deduplication)
    engine.recent_dubbed_history = []
    engine.enqueue("안녕하세요 반갑습니다", source="audio")
    q_size_after_first = engine.queue.qsize()
    assert q_size_after_first == 1, f"첫 대사는 큐에 들어가야 합니다 (현재: {q_size_after_first})"

    # 동일 대사 즉시 재유입 (OCR과 STT가 1.8초 내 동시 감지한 상황)
    engine.enqueue("안녕하세요 반갑습니다", source="screen")
    assert engine.queue.qsize() == 1, "완전 동일 대사는 1.8초 내 중복 인입 방지 필터로 스킵되어야 합니다."

    # 다른 대사는 정상 인입되어야 함 (누락 제로 보장)
    engine.enqueue("안녕하세요 다음 이야기입니다", source="screen")
    assert engine.queue.qsize() == 2, "부분 일치하더라도 다른 대사는 누락 없이 정상 큐잉되어야 합니다."

    print("SUCCESS: DubbingEngine echo state and deduplication test passed!")

    # 6. AudioLoopbackCapture 에코 게이트 반응 검증
    audio_q = queue.Queue()
    capture = AudioLoopbackCapture(audio_q, config=config, dubbing_engine=engine)
    assert capture.dubbing_engine is engine, "dubbing_engine이 정상 주입되어야 합니다."

    # engine이 말하고 있을 때
    engine._is_playing = True
    assert capture.dubbing_engine.is_speaking(), "게이트가 활성화 상태여야 합니다."

    # config 토글 검증
    config["dubbing_echo_cancellation"] = False
    capture.update_config(config)
    assert capture.config["dubbing_echo_cancellation"] is False, "설정 변경이 반영되어야 합니다."

    engine.stop()
    print("SUCCESS: AudioLoopbackCapture echo gate integration passed!")

if __name__ == "__main__":
    test_dubbing_echo_gate()
