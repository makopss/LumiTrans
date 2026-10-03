import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import time
import queue
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
from src.dubbing_engine import DubbingEngine
from src.screen_ocr_worker import extract_speaker_and_dialogue

def test_speaker_separation_and_filtering():
    print("=" * 60)
    print("[TEST] [테스트] 더빙 텍스트 화자 분리 및 소스별 필터링 검증")
    print("=" * 60)

    # 1. extract_speaker_and_dialogue 테스트
    test_cases = [
        ("Alex: Hello there!", "Alex", "Hello there!"),
        ("알렉스: 어떻게 지내?", "알렉스", "어떻게 지내?"),
        ("알렉스 : 어디로 가야 하나요?", "알렉스", "어디로 가야 하나요?"),
        ("Professor Kim: Welcome to class.", "Professor Kim", "Welcome to class."),
        ("김 교수: 수업에 온 것을 환영합니다.", "김 교수", "수업에 온 것을 환영합니다."),
        ("[Host] Watch out.", "Host", "Watch out."),
        ("[진행자] 조심해.", "진행자", "조심해."),
        ("Alex Chen - Let us proceed.", "Alex Chen", "Let us proceed."),
        ("안녕하세요! 일반 문장입니다.", "", "안녕하세요! 일반 문장입니다.")
    ]

    for raw, exp_spk, exp_body in test_cases:
        spk, body = DubbingEngine.extract_speaker_and_dialogue(raw)
        assert spk == exp_spk, f"[{raw}] 화자 불일치: 기대값 '{exp_spk}', 결과값 '{spk}'"
        assert body == exp_body, f"[{raw}] 대사 불일치: 기대값 '{exp_body}', 결과값 '{body}'"

        spk_ocr, body_ocr = extract_speaker_and_dialogue(raw)
        assert spk_ocr == exp_spk, f"[OCR: {raw}] 화자 불일치: '{spk_ocr}' vs '{exp_spk}'"
        assert body_ocr == exp_body, f"[OCR: {raw}] 대사 불일치: '{body_ocr}' vs '{exp_body}'"

    print("[OK] 1. 화자 이름 vs 순수 대사 본문 분리 정규식 100% 통과!")

    # 2. DubbingEngine enqueue 화자명 제거 검증
    config = {
        "dubbing_enabled": True,
        "dubbing_source_audio": False,  # 사용자 설정: 오디오 통역 더빙 OFF
        "dubbing_source_screen": True,  # 사용자 설정: 화면 번역 더빙 ON
        "dubbing_volume": 80,
        "dubbing_speed": "+0%",
        "dubbing_interrupt": False
    }
    engine = DubbingEngine(config)

    # 2-1. 오디오 소스 인입 시도 -> 거부되어야 함 (큐 크기 0 유지)
    engine.enqueue("오디오로 말한 내용입니다", source="audio")
    assert engine.queue.qsize() == 0, "dubbing_source_audio가 False일 때는 큐에 들어가지 않아야 합니다."

    # 2-2. 화면 소스 인입 시도 -> 허용되어야 하며, '알렉스:'가 대사에서 제거되어야 함
    engine.enqueue(
        translated_text="알렉스: 다음 회의실을 찾았습니다.",
        speaker_name="",  # 화자명을 비워두어도 번역문에서 자동 추출되어야 함
        orig_text="Alex: I found the next room.",
        source="screen",
        region_idx=1
    )
    assert engine.queue.qsize() == 1, "dubbing_source_screen이 True일 때는 큐에 추가되어야 합니다."
    item = engine.queue.get_nowait()
    assert item["speaker_name"] == "알렉스", f"화자명이 '알렉스'로 추출되어야 합니다 (현재: {item['speaker_name']})"
    assert item["text"] == "다음 회의실을 찾았습니다.", f"'알렉스:' 접두사가 완전히 제거되어야 합니다 (현재: {item['text']})"
    assert item["region_idx"] == 1, "영역 번호가 보존되어야 합니다."

    # 보이스 매핑 검증: 번호 없는 남성 화자는 대표 보이스(InJoon)로 자동 라우팅되어야 함
    voice, pitch = engine.resolve_voice_and_pitch(item["speaker_name"], item["speaker_display"], item["orig_text"])
    assert "InJoon" in voice, f"알렉스는 남성 보이스 InJoon으로 라우팅되어야 합니다 (현재: {voice})"
    assert pitch == "-10Hz", f"기본 화자 번호는 -10Hz 피치여야 합니다 (현재: {pitch})"
    print(f"[OK] 2. 더빙 대사 '알렉스:' 제거 및 남성 보이스 자동 라우팅 검증 완료! ('{voice}', {pitch})")

    # 3. clear_source_queue 검증
    # screen 2개 넣고 clear_source_queue("screen") 호출
    engine.enqueue("화면 대사 1", source="screen")
    engine.enqueue("화면 대사 2", source="screen")
    assert engine.queue.qsize() == 2
    engine.clear_source_queue("screen")
    assert engine.queue.qsize() == 0, "clear_source_queue('screen') 호출 후 큐가 비워져야 합니다."
    print("[OK] 3. 소스별 큐 선택적 즉시 비우기(clear_source_queue) 검증 완료!")

    engine.stop()
    print("\n[SUCCESS] 모든 화자 분리 및 옵션 분리 전달 테스트 100% 통과!")

if __name__ == "__main__":
    test_speaker_separation_and_filtering()
