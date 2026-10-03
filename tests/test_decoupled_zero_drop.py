import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import time
import queue
from src.dubbing_engine import DubbingEngine

def test_decoupled_zero_drop():
    print("=" * 60)
    print("[TEST] [테스트] 자막·보이스 완전 이원화 및 누락 제로(Zero-Drop) 가변 배속 검증")
    print("=" * 60)

    config = {
        "dubbing_enabled": True,
        "dubbing_source_audio": True,
        "dubbing_source_screen": True,
        "dubbing_volume": 80,
        "dubbing_speed": "+0%",
        "dubbing_interrupt": False
    }

    engine = DubbingEngine(config)

    # 1. 적응형 가변 배속(Adaptive Speed Pacing) 계산 검증
    assert engine.calculate_adaptive_speed(0) == "+0%", f"대기 0개는 기본 +0%여야 합니다 (현재: {engine.calculate_adaptive_speed(0)})"
    assert engine.calculate_adaptive_speed(1) == "+15%", f"대기 1개는 가속 +15%여야 합니다 (현재: {engine.calculate_adaptive_speed(1)})"
    assert engine.calculate_adaptive_speed(2) == "+30%", f"대기 2개는 가속 +30%여야 합니다 (현재: {engine.calculate_adaptive_speed(2)})"
    assert engine.calculate_adaptive_speed(3) == "+45%", f"대기 3개는 가속 +45%여야 합니다 (현재: {engine.calculate_adaptive_speed(3)})"
    assert engine.calculate_adaptive_speed(5) == "+60%", f"대기 4개 이상은 가속 +60%여야 합니다 (현재: {engine.calculate_adaptive_speed(5)})"
    print("[OK] 1. 큐 적체 기반 지능형 가변 배속(+0% -> +15% -> +30% -> +45% -> +60%) 계산 검증 100% 통과!")

    # 2. 누락 제로(Zero-Drop) 연속 5문장 큐잉 검증
    test_dialogues = [
        "첫 번째 대사입니다. 상황을 보고하십시오.",
        "두 번째 대사입니다. 적들이 접근 중입니다.",
        "세 번째 대사입니다. 지원군을 요청합니다.",
        "네 번째 대사입니다. 엄호 사격을 개시합니다.",
        "다섯 번째 대사입니다. 퇴각로를 확보했습니다."
    ]

    for d in test_dialogues:
        engine.enqueue(d, source="screen")

    total_in_pipeline = engine.get_pipeline_total_count()
    assert total_in_pipeline == 5, f"5개 대사가 1개도 누락 없이 파이프라인에 보관되어야 합니다 (현재: {total_in_pipeline})"
    print("[OK] 2. 대사 연속 유입 시 1건도 스킵 없이 100% 파이프라인 누적 보관(Zero-Drop) 검증 완료!")

    # 3. 에코(자기회귀) 지능형 대조 검증
    # 현재 재생 중인 대사 설정
    engine._is_playing = True
    engine._current_speaking_text = "퇴각로를 확보했습니다."
    
    # 성우 자신의 목소리가 다시 유입된 경우 -> 에코로 감지되어 재더빙 차단
    assert engine.is_echo_of_dubbing("퇴각로를 확보했습니다."), "동일 대사는 에코로 감지되어야 합니다."
    assert engine.is_echo_of_dubbing("퇴각로를 확보했습니다"), "문장부호 차이도 에코로 감지되어야 합니다."
    
    # 게임의 새로운 영문 대사가 번역되어 들어온 경우 -> 에코가 아님 (정상 더빙 허용)
    assert not engine.is_echo_of_dubbing("새로운 임무가 시작되었습니다."), "새로운 게임 대사는 에코로 오인되지 않아야 합니다."
    print("[OK] 3. 성우 음성 루프백 에코 지능형 핀포인트 판별 검증 완료!")

    engine.stop()
    print("\n[SUCCESS] 모든 자막·보이스 이원화 및 누락 제로 검증 100% 통과!")

if __name__ == "__main__":
    test_decoupled_zero_drop()
