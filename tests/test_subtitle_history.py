import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import os
import sys
import time
import tempfile

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# GUI 백엔드 오프스크린 설정 (CI/무인 환경 안전)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QApplication.instance() or QApplication(sys.argv)

from src.config import DEFAULT_CONFIG
from src.subtitle_manager import SubtitleHistoryManager, SubtitleEntry, format_srt_time, format_display_time
from src.control_panel import ControlPanel
from src.i18n import tr


def test_time_formatters():
    print("[1] 타임코드 포맷터(format_srt_time, format_display_time) 단위 테스트...")
    assert format_srt_time(0.0) == "00:00:00,000"
    assert format_srt_time(65.5) == "00:01:05,500"
    assert format_srt_time(3661.123) == "01:01:01,123"
    
    t_str = format_display_time(time.time())
    assert len(t_str.split(":")) == 3
    print("  -> 타임코드 변환 정확도 100% 통과!")


def test_manager_core_operations():
    print("[2] SubtitleHistoryManager 자막 누적 및 필터링 테스트...")
    mgr = SubtitleHistoryManager()
    mgr.reset_session_timer()

    # 1) 오디오 통역 엔트리 추가
    e1 = mgr.add_entry(
        source="audio",
        trans_text="<span style='color: #00E5FF;'>[화자 1]</span> 이쪽으로 따라와 주세요.",
        orig_text="Please follow me this way.",
        engine="distil-large + Google"
    )
    assert e1.id == 1
    assert e1.source == "audio"
    assert e1.speaker == "화자 1"
    assert e1.clean_trans == "[화자 1] 이쪽으로 따라와 주세요."
    assert e1.clean_orig == "Please follow me this way."

    # 2) 화면 번역 엔트리 추가
    time.sleep(0.05)
    e2 = mgr.add_entry(
        source="screen",
        trans_text="자료를 모으면 다음 단계가 열립니다.",
        orig_text="The next step will open when the files are gathered.",
        engine="RapidOCR + Google",
        region_idx=1
    )
    assert e2.id == 2
    assert e2.source == "screen"
    assert e2.region_idx == 1

    # 3) AI 더빙 엔트리 추가
    time.sleep(0.05)
    e3 = mgr.add_entry(
        source="dubbing",
        trans_text="자료를 모으면 다음 단계가 열립니다.",
        orig_text="The next step will open when the files are gathered.",
        speaker="인준",
        voice="ko-KR-InJoonNeural",
        speed="+10%"
    )
    assert e3.id == 3
    assert e3.source == "dubbing"
    assert e3.speaker == "인준"

    # 4) 오디오 항목에 더빙이 결합된 일반적인 실시간 파이프라인 시뮬레이션
    e4 = mgr.add_entry(
        source="audio",
        trans_text="[화자 1] 시스템을 활성화합니다.",
        orig_text="Activating system.",
        dub_status="waiting"
    )
    assert mgr.count() == 4
    # 더빙 합성 완료 콜백 시뮬레이션 (update_or_add_dubbing)
    mgr.update_or_add_dubbing(
        dub_text="시스템을 활성화합니다.",
        speaker="화자 1",
        orig_text="Activating system.",
        voice="ko-KR-SunHiNeural",
        speed="+15%"
    )
    assert e4.dub_status == "done"
    assert e4.clean_dub == "시스템을 활성화합니다."

    # 필터링 검증: 소스별 및 컬럼별 필터
    audio_only = mgr.get_entries(source_filter="audio")
    assert len(audio_only) == 2  # e1, e4

    screen_only = mgr.get_entries(source_filter="screen")
    assert len(screen_only) == 1 and screen_only[0].id == 2

    # 더빙 필터링: e3(source=dubbing) 및 e4(source=audio이지만 dubbing 완료) 모두 포함
    dubbing_entries = mgr.get_entries(source_filter="dubbing")
    assert len(dubbing_entries) == 2
    assert any(e.id == 3 for e in dubbing_entries)
    assert any(e.id == 4 for e in dubbing_entries)

    # 컬럼별 필터링
    orig_entries = mgr.get_entries(source_filter="orig_only")
    assert len(orig_entries) == 4

    trans_entries = mgr.get_entries(source_filter="trans_only")
    assert len(trans_entries) == 4

    dub_entries = mgr.get_entries(source_filter="dub_only")
    assert len(dub_entries) == 2

    # 키워드 검색 검증
    kw_follow = mgr.get_entries(keyword="follow")
    assert len(kw_follow) == 1 and kw_follow[0].id == 1

    kw_files = mgr.get_entries(keyword="자료")
    assert len(kw_files) == 2  # screen + dubbing

    kw_system = mgr.get_entries(keyword="시스템")
    assert len(kw_system) == 1 and kw_system[0].id == 4

    print("  -> 자막 누적, 소스별/컬럼별 필터링, 키워드 검색 검증 100% 통과!")


def test_export_srt_and_txt():
    print("[3] SRT 표준 자막 및 TXT 대본 파일 필터별 맞춤 내보내기 테스트...")
    mgr = SubtitleHistoryManager()
    e1 = mgr.add_entry(
        source="audio",
        trans_text="[화자 1] 안녕하세요, 반갑습니다.",
        orig_text="Hello, nice to meet you.",
        engine="Whisper + Google"
    )
    e2 = mgr.add_entry(
        source="screen",
        trans_text="[영역 1] 새로운 안건이 시작되었습니다.",
        orig_text="New agenda has started.",
        region_idx=1
    )
    # 더빙 업데이트
    mgr.update_or_add_dubbing(
        dub_text="안녕하세요, 반갑습니다.",
        speaker="화자 1",
        orig_text="Hello, nice to meet you.",
        voice="ko-KR-InJoonNeural",
        speed="+10%"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1) 전체 SRT 저장 (이중 자막: 번역문 + 원문)
        srt_path_all = os.path.join(tmpdir, "test_all.srt")
        ok_srt = mgr.export_to_srt(srt_path_all, include_original=True, source_filter="all")
        assert ok_srt and os.path.exists(srt_path_all)
        with open(srt_path_all, "r", encoding="utf-8-sig") as f:
            content_all = f.read()
        assert "안녕하세요, 반갑습니다." in content_all
        assert "Hello, nice to meet you." in content_all
        assert "새로운 안건이 시작되었습니다." in content_all

        # 2) 영문 원문만 SRT 저장
        srt_path_orig = os.path.join(tmpdir, "test_orig.srt")
        mgr.export_to_srt(srt_path_orig, source_filter="orig_only")
        with open(srt_path_orig, "r", encoding="utf-8-sig") as f:
            content_orig = f.read()
        assert "Hello, nice to meet you." in content_orig
        assert "New agenda has started." in content_orig
        assert "안녕하세요" not in content_orig

        # 3) 한국어 번역문만 SRT 저장
        srt_path_trans = os.path.join(tmpdir, "test_trans.srt")
        mgr.export_to_srt(srt_path_trans, source_filter="trans_only")
        with open(srt_path_trans, "r", encoding="utf-8-sig") as f:
            content_trans = f.read()
        assert "안녕하세요, 반갑습니다." in content_trans
        assert "새로운 안건이 시작되었습니다." in content_trans
        assert "Hello" not in content_trans

        # 4) 더빙문만 SRT 저장
        srt_path_dub = os.path.join(tmpdir, "test_dub.srt")
        mgr.export_to_srt(srt_path_dub, source_filter="dub_only")
        with open(srt_path_dub, "r", encoding="utf-8-sig") as f:
            content_dub = f.read()
        assert "안녕하세요, 반갑습니다." in content_dub
        assert "새로운 안건이 시작되었습니다." not in content_dub  # e2는 더빙 안 됨

        # 5) TXT 저장 검증 (전체 vs 개별 필터)
        txt_path_all = os.path.join(tmpdir, "test_all.txt")
        mgr.export_to_txt(txt_path_all, include_timestamps=True, source_filter="all")
        with open(txt_path_all, "r", encoding="utf-8-sig") as f:
            c_txt_all = f.read()
        orig_tag = tr("history_col_orig")
        trans_tag = tr("history_col_trans")
        dub_tag = tr("history_col_dub")
        assert f"[{orig_tag}]    Hello, nice to meet you." in c_txt_all or "[원문]    Hello, nice to meet you." in c_txt_all
        assert f"[{trans_tag}]    [화자 1] 안녕하세요, 반갑습니다." in c_txt_all or "[번역]    [화자 1] 안녕하세요, 반갑습니다." in c_txt_all
        assert f"[{dub_tag}] [ko-KR-InJoonNeural +10%] 안녕하세요, 반갑습니다." in c_txt_all or "[AI 더빙 발화] [ko-KR-InJoonNeural +10%] 안녕하세요, 반갑습니다." in c_txt_all

        txt_path_orig = os.path.join(tmpdir, "test_orig.txt")
        mgr.export_to_txt(txt_path_orig, include_timestamps=True, source_filter="orig_only")
        with open(txt_path_orig, "r", encoding="utf-8-sig") as f:
            c_txt_orig = f.read()
        assert "Hello, nice to meet you." in c_txt_orig
        assert "New agenda has started." in c_txt_orig
        assert f"[{trans_tag}]" not in c_txt_orig and "[번역]" not in c_txt_orig

        txt_path_dub = os.path.join(tmpdir, "test_dub.txt")
        mgr.export_to_txt(txt_path_dub, include_timestamps=True, source_filter="dub_only")
        with open(txt_path_dub, "r", encoding="utf-8-sig") as f:
            c_txt_dub = f.read()
        assert "안녕하세요, 반갑습니다." in c_txt_dub
        assert "New agenda" not in c_txt_dub

    print("  -> SRT 및 TXT 필터별 맞춤 내보내기 검증 100% 통과!")


def test_control_panel_tab_integration():
    print("[4] ControlPanel 자막 기록 탭 및 실시간 시그널 연동 테스트...")
    cfg = dict(DEFAULT_CONFIG)
    cp = ControlPanel(
        config=cfg,
        overlay=None,
        audio_thread=None,
        stt_thread=None,
        save_config_cb=lambda c: None
    )

    # 탭 위젯 검증 (총 5개 탭)
    assert cp.tab_widget.count() == 5
    assert "자막 탐색기" in cp.tab_widget.tabText(2) or "실시간 자막" in cp.tab_widget.tabText(2)

    # 자막 탭 요소 및 필터 옵션 확인
    assert hasattr(cp, 'combo_sub_filter')
    assert cp.combo_sub_filter.count() == 7
    filter_keys = [cp.combo_sub_filter.itemData(i) for i in range(cp.combo_sub_filter.count())]
    assert filter_keys == ["all", "audio", "screen", "dubbing", "orig_only", "trans_only", "dub_only"]

    cp.set_audio_active_state(True)
    cp.set_screen_active_state(True)

    # 이벤트 수신 및 시그널 전달 시뮬레이션
    cp._on_audio_subtitle_received(
        orig="Please follow me this way",
        trans="이쪽으로 따라와 주세요",
        engine="GPU + Google"
    )
    app.processEvents()

    cp._on_screen_subtitle_received(
        orig="The next step will open",
        trans="다음 단계가 열립니다",
        engine="RapidOCR",
        roi_idx=0
    )
    app.processEvents()

    # 더빙 재생 완료 시 기존 번역 행에 매칭 업데이트 검증 (3단 가로 비교 테이블)
    cp._on_dubbing_playback_received(
        text="다음 단계가 열립니다",
        speaker="인준",
        orig_text="The next step will open",
        source="screen",
        voice="ko-KR-InJoonNeural",
        speed="+10%",
        region_idx=1
    )
    app.processEvents()

    # 기존 행에 병합 업데이트되었으므로 총 2개 행 유지
    assert cp.subtitle_history.count() == 2
    assert cp.lbl_sub_count.text() == "총 2개"
    html = cp.text_sub_history.toHtml()
    assert "원문" in html
    assert "번역" in html
    assert ("실제 더빙" in html or "AI 음성 더빙" in html)

    # 1) 필터: 영문 원문만
    idx_orig = filter_keys.index("orig_only")
    cp.combo_sub_filter.setCurrentIndex(idx_orig)
    app.processEvents()
    html_orig = cp.text_sub_history.toHtml()
    assert "STT / OCR 원문" in html_orig
    assert "Please follow me this way" in html_orig
    assert cp.lbl_sub_count.text() == "2/2개"

    # 2) 필터: 한국어 번역만
    idx_trans = filter_keys.index("trans_only")
    cp.combo_sub_filter.setCurrentIndex(idx_trans)
    app.processEvents()
    html_trans = cp.text_sub_history.toHtml()
    assert "번역문" in html_trans
    assert "이쪽으로 따라와 주세요" in html_trans

    # 3) 필터: 더빙 발화만
    idx_dub = filter_keys.index("dub_only")
    cp.combo_sub_filter.setCurrentIndex(idx_dub)
    app.processEvents()
    html_dub = cp.text_sub_history.toHtml()
    assert "AI 음성 더빙 발화문" in html_dub
    assert "다음 단계가 열립니다" in html_dub
    assert cp.lbl_sub_count.text() == "1/2개"  # 더빙된 것은 1건

    # 4) 필터: 다시 전체 보기 복귀
    cp.combo_sub_filter.setCurrentIndex(0)
    app.processEvents()
    assert cp.lbl_sub_count.text() == "총 2개"

    # 초기화 동작 검증
    cp.subtitle_history.clear()
    cp.refresh_subtitle_view()
    app.processEvents()
    assert cp.subtitle_history.count() == 0

    print("  -> ControlPanel 자막 탭 및 실시간 시그널 연동 검증 100% 통과!")


def test_export_edge_cases_and_clean_formatting():
    print("[5] SRT 및 TXT 화자 중복 방지, HTML 언이스케이프, 키워드 연동 테스트...")
    mgr = SubtitleHistoryManager()
    mgr.add_entry(
        source="screen",
        trans_text="[Andy] 안녕하세요! &lt;환영합니다&gt;<br>좋은 하루 되세요.",
        orig_text="[Andy] Hello! &quot;Welcome&quot;<br>Have a nice day.",
        speaker="Andy"
    )
    mgr.add_entry(
        source="screen",
        trans_text="공지사항 내용입니다.",
        orig_text="This is an announcement.",
        speaker="ROI 1"
    )

    # 1. 화자 중복 방지 검증 ([Andy] [Andy] 방지 및 이중 자막 2행 불필요한 화자 반복 제거)
    srt_out = mgr.export_to_srt(source_filter="all")
    assert "[Andy] [Andy]" not in srt_out
    assert "[Andy] 안녕하세요! <환영합니다> 좋은 하루 되세요." in srt_out
    assert 'Hello! "Welcome" Have a nice day.' in srt_out

    # 2. ROI 1 화자 접두어 SRT 생략 검증 (실제 영상 자막에 [ROI 1] 노출 방지)
    assert "[ROI 1]" not in srt_out
    assert "공지사항 내용입니다." in srt_out

    # 3. 키워드 필터링 내보내기 검증
    srt_filtered = mgr.export_to_srt(source_filter="all", keyword="환영")
    assert "안녕하세요" in srt_filtered
    assert "공지사항" not in srt_filtered

    txt_filtered = mgr.export_to_txt(source_filter="all", keyword="공지사항")
    assert "공지사항" in txt_filtered
    assert "안녕하세요" not in txt_filtered
    assert "총 대사 수: 1개" in txt_filtered

    print("  -> 화자 중복 방지, HTML 엔티티 언이스케이프, 키워드 연동 검증 100% 통과!")


if __name__ == "__main__":
    print("=" * 60)
    print("[TEST] 실시간 자막 기록 모니터링 & 내보내기 단위 테스트 시작")
    print("=" * 60)
    test_time_formatters()
    test_manager_core_operations()
    test_export_srt_and_txt()
    test_control_panel_tab_integration()
    test_export_edge_cases_and_clean_formatting()
    print("\n[SUCCESS] 모든 자막 기록 및 내보내기 단위 테스트 100% 성공!")
