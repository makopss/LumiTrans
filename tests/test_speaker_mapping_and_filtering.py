import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import os
import sys
import time
import queue
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np
from PyQt6.QtWidgets import QApplication, QMessageBox, QLineEdit, QCheckBox
from src.config import DEFAULT_CONFIG
from src.speaker_identifier import SpeakerIdentifier, SPEAKER_COLORS
from src.stt_engine import STTWorker
from src.screen_ocr_worker import ScreenOCRWorker
from src.overlay_window import SubtitleOverlay
from src.control_panel import ControlPanel

app = QApplication.instance() or QApplication(sys.argv)

def test_speaker_alias_and_mute_core():
    print("\n[1] SpeakerIdentifier 실명 매핑(Alias) 및 번역 제외(Mute) 코어 로직 테스트...")
    cfg = DEFAULT_CONFIG.copy()
    cfg["speaker_diarization_enabled"] = True
    spk_id = SpeakerIdentifier(config=cfg)

    # 1. 초기 상태 확인
    assert spk_id.get_display_name("화자 1") == "화자 1"
    assert not spk_id.is_speaker_muted("화자 1")

    # 2. 실명(Alias) 설정
    spk_id.set_speaker_alias("화자 1", "진행자")
    assert spk_id.get_display_name("화자 1") == "진행자"
    assert spk_id.speaker_aliases["화자 1"] == "진행자"

    # 3. 화자 번역 제외(Mute) 설정
    spk_id.set_speaker_muted("화자 1", True)
    assert spk_id.is_speaker_muted("화자 1") == True
    # 실명(진행자)으로 조회해도 뮤트 여부 감지
    assert spk_id.is_speaker_muted("진행자") == True

    # 4. 다른 화자(화자 2: 게스트) 설정
    spk_id.set_speaker_alias("화자 2", "게스트")
    spk_id.set_speaker_muted("화자 2", False)
    assert spk_id.get_display_name("화자 2") == "게스트"
    assert spk_id.is_speaker_muted("화자 2") == False

    # 5. 전체 목록 반환 검증
    known = spk_id.get_all_known_speakers()
    assert len(known) >= 2
    raw_names = [k["raw_name"] for k in known]
    assert "화자 1" in raw_names and "화자 2" in raw_names
    print("  -> 실명 매핑 및 뮤트 코어 로직 검증 통과!")

def test_screen_ocr_auto_linking():
    print("\n[2] 화면 OCR 대화명-음성 화자 지능형 자동 연동 테스트...")
    cfg = DEFAULT_CONFIG.copy()
    cfg["speaker_diarization_enabled"] = True
    cfg["speaker_ocr_auto_mapping"] = True

    q = queue.Queue()
    stt_worker = STTWorker(audio_queue=q, config=cfg)
    spk_id = stt_worker.speaker_identifier
    assert spk_id is not None

    # 화자 2가 방금 발화했다고 시뮬레이션
    spk_id.last_active_speaker = "화자 2"
    spk_id.last_active_time = time.time()

    # 화면 OCR 워커 생성
    ocr_worker = ScreenOCRWorker(config=cfg, translator=None, stt_worker=stt_worker)

    # 화면에 "Alex Chen: Welcome to the meeting." 감지 시뮬레이션
    ocr_worker._check_and_link_speaker_name("Alex Chen: Welcome to the meeting.")

    # 화자 2가 Alex Chen으로 자동 매핑되었는지 검증!
    assert spk_id.get_display_name("화자 2") == "Alex Chen", f"매핑 실패: {spk_id.get_display_name('화자 2')}"
    print(f"  -> 화면 OCR 대화명 자동 연동 성공: '화자 2' -> '{spk_id.get_display_name('화자 2')}'")

def test_stt_translation_loop_mute_filtering():
    print("\n[3] STT 비동기 번역 큐에서 뮤트된 화자 필터링(자막 생략) 테스트...")
    cfg = DEFAULT_CONFIG.copy()
    cfg["speaker_diarization_enabled"] = True

    delivered_subtitles = []
    def mock_subtitle_cb(orig, trans, tag):
        delivered_subtitles.append((orig, trans, tag))

    q = queue.Queue()
    stt_worker = STTWorker(audio_queue=q, subtitle_callback=mock_subtitle_cb, config=cfg)
    spk_id = stt_worker.speaker_identifier

    # 화자 1(진행자)은 뮤트, 화자 2(게스트)는 번역 활성화
    spk_id.set_speaker_alias("화자 1", "진행자")
    spk_id.set_speaker_muted("화자 1", True)

    spk_id.set_speaker_alias("화자 2", "게스트")
    spk_id.set_speaker_muted("화자 2", False)

    # 번역 큐에 두 화자의 발화 투입
    # 1. 진행자 발화 (뮤트 대상)
    stt_worker.trans_queue.put(("Hello guys thank you for watching", "GPU", (1, "진행자", "#00E5FF")))
    # 2. 게스트 발화 (번역 대상)
    stt_worker.trans_queue.put(("Please follow me this way", "GPU", (2, "게스트", "#FFD54F")))

    stt_worker.running = True
    trans_thread = stt_worker.trans_worker
    trans_thread.start()

    # 번역 처리 대기 (최대 15초까지 비동기 완료 대기)
    start_t = time.time()
    while time.time() - start_t < 15.0:
        if len(delivered_subtitles) >= 1:
            break
        time.sleep(0.1)
    stt_worker.running = False

    # 진행자 발화는 필터링되어 자막으로 나가지 않고, 게스트 발화만 자막으로 출력되었는지 검증!
    assert len(delivered_subtitles) == 1, f"자막 개수가 1이어야 합니다 (실제: {len(delivered_subtitles)})"
    orig, trans, tag = delivered_subtitles[0]
    assert "[게스트]" in orig and "[게스트]" in trans, f"게스트 자막이어야 합니다: {orig}"
    assert "[진행자]" not in orig and "[진행자]" not in trans, "진행자 자막은 필터링되어 없어야 합니다"
    print("  -> 뮤트 화자 번역 필터링 및 게스트 선택 자막 출력 성공!")

def test_control_panel_speaker_mgmt_ui():
    print("\n[4] ControlPanel 화자 실명 매핑 및 필터 관리 UI 연동 테스트...")
    saved_config = {}
    def mock_save(c):
        saved_config.clear()
        saved_config.update(c)

    test_cfg = DEFAULT_CONFIG.copy()
    test_cfg["speaker_diarization_enabled"] = True
    test_cfg["speaker_aliases"] = {"화자 1": "진행자"}
    test_cfg["speaker_mutes"] = {"화자 1": True}

    q = queue.Queue()
    stt_worker = STTWorker(audio_queue=q, config=test_cfg)
    audio_ov = SubtitleOverlay(test_cfg)

    cp = ControlPanel(
        config=test_cfg,
        overlay=audio_ov,
        audio_thread=None,
        stt_thread=stt_worker,
        save_config_cb=mock_save
    )

    # 1. UI에 화자 1 행이 생성되었는지 확인
    assert cp.speaker_list_layout.count() >= 1, "화자 행이 생성되어야 합니다."
    first_row = cp.speaker_list_layout.itemAt(0).widget()
    line_edits = first_row.findChildren(QLineEdit)
    check_boxes = first_row.findChildren(QCheckBox)
    assert len(line_edits) == 1, "실명 입력창이 있어야 합니다."
    assert line_edits[0].text() == "진행자", "화자 1 별칭이 진행자여야 합니다."
    assert len(check_boxes) == 2, f"번역 및 더빙 체크박스 2개가 있어야 합니다 (실제: {len(check_boxes)}개)."
    cb_trans = [c for c in check_boxes if c.text() == "번역"][0]
    assert not cb_trans.isChecked(), "뮤트 상태이므로 번역 체크가 해제되어 있어야 합니다."

    # 2. 신규 화자 2 등록 시뮬레이션
    stt_worker.speaker_identifier.set_speaker_alias("화자 2", "민수")
    cp.refresh_speaker_mgmt_ui()
    assert cp.speaker_list_layout.count() == 2, "화자 1과 화자 2 두 개의 행이 있어야 합니다."

    # 3. 모두 번역 버튼 클릭 동작 확인
    cp.on_unmute_all_speakers()
    assert not stt_worker.speaker_identifier.is_speaker_muted("화자 1")
    assert not stt_worker.speaker_identifier.is_speaker_muted("화자 2")

    # 4. 종료 전 설정 보존 검증
    cp.save_all_settings_before_exit()
    assert saved_config["speaker_aliases"]["화자 2"] == "민수"
    assert saved_config["speaker_ocr_auto_mapping"] == True

    # 5. 화자 기억 초기화 버튼 클릭 시 리스트 및 설정 완전 초기화 검증
    orig_info = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *args, **kwargs: None)
    try:
        cp.on_reset_speakers_clicked()
        assert stt_worker.speaker_identifier.get_all_known_speakers() == [], "초기화 후 등록된 화자 목록이 완전히 비어있어야 합니다."
        assert test_cfg["speaker_aliases"] == {}, "설정의 speaker_aliases가 비워져야 합니다."
        assert test_cfg["speaker_mutes"] == {}, "설정의 speaker_mutes가 비워져야 합니다."
        # UI 레이아웃에는 안내 라벨 1개만 존재해야 함
        assert cp.speaker_list_layout.count() == 1
        assert "대화 음성이 유입되면" in cp.speaker_list_layout.itemAt(0).widget().text()
        print("  -> 화자 기억 초기화 시 UI 목록 및 설정값 완전 비움 검증 통과!")
    finally:
        QMessageBox.information = orig_info

    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    try:
        cp.close()
        audio_ov.close()
    finally:
        QMessageBox.question = orig_q

    print("  -> ControlPanel 화자 실명 매핑 및 필터 관리 UI 연동 검증 통과!")

if __name__ == "__main__":
    print("=" * 65)
    print("[TEST] 실시간 화자 실명 매핑 & 번역 필터링(Mute/Solo) 단위 테스트 시작")
    print("=" * 65)
    test_speaker_alias_and_mute_core()
    test_screen_ocr_auto_linking()
    test_stt_translation_loop_mute_filtering()
    test_control_panel_speaker_mgmt_ui()
    print("\n[SUCCESS] 모든 실명 매핑 & 번역 필터링 단위 테스트 성공적으로 통과!")
