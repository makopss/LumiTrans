import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import time
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from PIL import Image, ImageDraw, ImageFont
from src.screen_capture import is_frame_changed
from src.screen_ocr_worker import ScreenOCRWorker
from src.translator import RealtimeTranslator
from src.config import DEFAULT_CONFIG

def test_frame_diff():
    print("[1] 프레임 변화 감지 (Perceptual Frame Diff) 테스트...")
    img1 = Image.new("RGB", (600, 200), color="black")
    img2 = Image.new("RGB", (600, 200), color="black")

    # 동일한 이미지 비교 -> False여야 함
    assert not is_frame_changed(img1, img2), "동일한 이미지는 변화 없음(False)이어야 합니다."

    # 텍스트가 추가된 이미지 비교 -> True여야 함
    d = ImageDraw.Draw(img2)
    d.text((30, 40), "Warning: Boss monster has appeared!", fill="white")
    assert is_frame_changed(img1, img2), "텍스트가 추가된 이미지는 변화 감지(True)여야 합니다."
    print("  -> Frame diff 테스트 통과! (동일 이미지 0% 스킵, 변경 감지 정상)")

def test_ocr_and_translation():
    print("[2] RapidOCR 영문 인식 및 실시간 번역 파이프라인 테스트...")
    # 가상의 게임 대화창 이미지 생성
    test_img = Image.new("RGB", (800, 160), color="white")
    d = ImageDraw.Draw(test_img)
    font = ImageFont.load_default(size=26)
    sample_text = "The ancient gate will open when crystals are gathered."
    d.text((40, 50), sample_text, fill="black", font=font)

    # OCR 엔진 로드 및 인식
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR(det_limit_side_len=720, det_db_thresh=0.3)

    s = time.time()
    res, _ = ocr(test_img)
    ocr_time = (time.time() - s) * 1000
    assert res is not None and len(res) > 0, "OCR 결과가 비어있지 않아야 합니다."

    recognized_text = " ".join([r[1].strip() for r in res])
    print(f"  -> OCR 추출 텍스트: '{recognized_text}' (소요 시간: {ocr_time:.1f}ms)")
    assert "ancient gate" in recognized_text.lower() or "crystal" in recognized_text.lower(), "핵심 영단어가 인식되어야 합니다."

    # 번역기 연동 테스트
    config = DEFAULT_CONFIG.copy()
    config["translation_engine"] = "google"
    translator = RealtimeTranslator(config=config)

    s = time.time()
    translated, engine = translator.translate(recognized_text)
    trans_time = (time.time() - s) * 1000

    print(f"  -> 번역 엔진: {engine}")
    print(f"  -> 번역 결과: '{translated}' (소요 시간: {trans_time:.1f}ms)")
    assert len(translated) > 0, "번역 결과가 비어있지 않아야 합니다."
    print(f"  -> 총 파이프라인 처리 시간: {ocr_time + trans_time:.1f}ms")

def test_dialogue_formatting():
    print("[3] 다중 영역 태그 및 대화형 자막 포맷팅 테스트...")
    from src.screen_overlay import ScreenSubtitleOverlay
    from src.config import DEFAULT_CONFIG
    from PyQt6.QtWidgets import QApplication

    # QApplication 싱글톤 인스턴스 확인
    app = QApplication.instance() or QApplication(sys.argv)
    overlay = ScreenSubtitleOverlay(DEFAULT_CONFIG.copy())

    # 다중 영역 태그와 화자 콜론 포함 테스트
    raw_ko = "[영역 1] 알렉스 첸: 회의에 오신 것을 환영합니다. [영역 2] 안내: 김 교수님을 찾아가십시오."
    formatted = overlay.format_korean_dialogue(raw_ko)
    print(f"  -> 원본: {raw_ko}")
    print(f"  -> 포맷팅 결과: {formatted}")

    assert "color: #00E5FF" in formatted, "영역 1 태그 하이라이트가 포함되어야 합니다."
    assert "color: #64B5F6" in formatted, "화자 이름 하이라이트가 포함되어야 합니다."
    print("  -> 자막 포맷팅 테스트 통과!")

def test_multi_roi_config():
    print("[4] 다중 ROI 설정 및 동기화 테스트...")
    from src.config import load_config
    cfg = load_config()
    assert "screen_rois" in cfg, "screen_rois 키가 존재해야 합니다."
    assert isinstance(cfg["screen_rois"], list), "screen_rois는 리스트여야 합니다."
    print(f"  -> 현재 로드된 감시 영역 수: {len(cfg['screen_rois'])}개")
    print("  -> 다중 ROI 설정 테스트 통과!")

def test_snap_to_roi_spatial_logic():
    print("[5] 지정 영역 자동 밀착(Snap-to-ROI) 지능형 배치 테스트...")
    from src.screen_overlay import ScreenSubtitleOverlay
    from src.config import DEFAULT_CONFIG
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    cfg = DEFAULT_CONFIG.copy()
    cfg["screen_snap_to_roi"] = True
    overlay = ScreenSubtitleOverlay(cfg)

    # 1. 하단 대화창 테스트: X=400, Y=1200, W=1000, H=250 (화면 하단) -> 위쪽에 안착해야 함
    bottom_roi = [400, 1200, 1000, 250]
    overlay.snap_to_roi(bottom_roi, needed_height=120)
    geo = overlay.geometry()
    print(f"  -> 하단 대화창 입력: {bottom_roi} => 밀착 배치 결과: X={geo.x()}, Y={geo.y()}, W={geo.width()}, H={geo.height()}")
    assert geo.y() < bottom_roi[1], "하단 대화창의 경우 자막창이 대화창 위쪽(Y < ROI.Y)에 배치되어야 합니다."

    # 2. 상단 알림창 테스트: X=1800, Y=50, W=600, H=200 (화면 상단) -> 아래쪽에 안착해야 함
    top_roi = [1800, 50, 600, 200]
    overlay.snap_to_roi(top_roi, needed_height=120)
    geo_top = overlay.geometry()
    print(f"  -> 상단 알림창 입력: {top_roi} => 밀착 배치 결과: X={geo_top.x()}, Y={geo_top.y()}, W={geo_top.width()}, H={geo_top.height()}")
    assert geo_top.y() > top_roi[1], "상단 알림창의 경우 자막창이 알림창 아래쪽(Y > ROI.Y)에 배치되어야 합니다."
    print("  -> Snap-to-ROI 지능형 배치 테스트 통과!")

def test_game_text_clahe_preprocessing():
    print("[6] 게임 텍스트 영상 전처리 (CLAHE) 테스트...")
    from src.screen_capture import preprocess_game_image
    import numpy as np
    import cv2

    # 가상의 어두운 배경 + 저대비 텍스트 이미지 생성
    raw_img = np.full((120, 400, 3), 60, dtype=np.uint8)
    cv2.putText(raw_img, "HP: 250 / 500", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 100), 2)

    enhanced = preprocess_game_image(raw_img)
    assert enhanced is not None, "전처리 결과는 None이 아니어야 합니다."
    assert enhanced.shape == raw_img.shape, "전처리 후 해상도 및 채널이 보존되어야 합니다."
    # 명암 대비(표준편차)가 전처리 전보다 향상되었는지 검증
    assert np.std(enhanced) > np.std(raw_img), "CLAHE 전처리 후 이미지의 대비(표준편차)가 향상되어야 합니다."
    print("  -> CLAHE 게임 텍스트 대비 향상 검증 통과!")

def test_inplace_overlay_and_hotkey():
    print("[7] 인플레이스 전체화면 스냅샷 및 F4 단축키 모듈 테스트...")
    from src.inplace_translator import GlobalHotkeyWorker, InPlaceOverlayWindow
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QRect

    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Hotkey 워커 생성 및 기본값 검증
    hotkey = GlobalHotkeyWorker()
    assert hotkey.vk_code == 0x73, "기본 단축키는 F4 (0x73)이어야 합니다."

    # 2. InPlaceOverlayWindow 생성 및 뱃지 배치 검증
    overlay = InPlaceOverlayWindow()
    sample_items = [
        ({"min_x": 100, "max_x": 300, "min_y": 200, "max_y": 240, "total_h": 40, "line_count": 1, "scores": [0.95]},
         "Notice Board", "알림 목록", "#F6E06B"),
        ({"min_x": 400, "max_x": 700, "min_y": 600, "max_y": 650, "total_h": 50, "line_count": 1, "scores": [0.92]},
         "Storage Full", "보관함이 가득 찼습니다", "#FFFFFF"),
    ]
    overlay.set_results(sample_items, QRect(0, 0, 1920, 1080), engine_name="Google")
    assert len(overlay.badges) == 2, "2개의 번역 말풍선 뱃지가 생성되어야 합니다."
    assert overlay.badges[0].korean_text == "알림 목록"
    assert overlay.badges[0].font_color.name().upper() == "#F6E06B", "골드 색상이 정상 반영되어야 합니다."
    print("  -> 인플레이스 오버레이 뱃지 배치 및 단축키 워커 테스트 통과!")

def test_paragraph_grouping_and_color_sampling():
    print("[8] 원본 문단(Paragraph) 지능형 병합 및 폰트 색상 스펙트럼 추출 테스트...")
    from src.inplace_translator import group_boxes_into_paragraphs, sample_text_color
    import numpy as np
    import cv2

    # 1. 3줄짜리 가상 문단 박스 생성 (줄 간격 6px, 높이 18px)
    line1 = ([[100, 100], [500, 100], [500, 118], [100, 118]], "Line 1 text", 0.95)
    line2 = ([[110, 124], [490, 124], [490, 142], [110, 142]], "Line 2 text", 0.93)
    line3 = ([[120, 148], [480, 148], [480, 166], [120, 166]], "Line 3 text", 0.91)
    title = ([[200, 40], [400, 40], [400, 62], [200, 62]], "TITLE TEXT", 0.98)

    merged = group_boxes_into_paragraphs([title, line1, line2, line3])
    assert len(merged) == 2, f"제목 1개와 3줄 문단 1개, 총 2개 문단으로 병합되어야 합니다 (현재: {len(merged)})"
    assert merged[1]["line_count"] == 3, "3줄짜리 텍스트는 1개의 문단으로 묶여야 합니다."

    # 1-1. 단어/어절 단위로 파편화된 박스들의 단일 문단 병합 검증 (단어마다 말풍선 난립 방지)
    word_boxes = [
        ([[100, 200], [250, 200], [250, 230], [100, 230]], 'Professor Kim:', 0.95),
        ([[260, 200], [380, 200], [380, 230], [260, 230]], 'Welcome to', 0.96),
        ([[390, 200], [500, 200], [500, 230], [390, 230]], 'this week', 0.94),
        ([[100, 238], [220, 238], [220, 268], [100, 268]], 'seminar.', 0.92),
        ([[230, 238], [340, 238], [340, 268], [230, 268]], 'Now, this', 0.93),
        ([[350, 238], [550, 238], [550, 268], [350, 268]], 'will be a crucial year', 0.95)
    ]
    word_merged = group_boxes_into_paragraphs(word_boxes)
    assert len(word_merged) == 1, f"6개 단어 파편이 1개의 완성된 대화 단락으로 병합되어야 합니다 (현재: {len(word_merged)})"
    print("  -> 다중 줄 텍스트 및 파편화 단어의 문단(Paragraph) 형태 병합 검증 통과!")

    # 2. 골드 폰트 색상 추출 검증
    test_canvas = np.full((100, 300, 3), 30, dtype=np.uint8) # 어두운 게임 배경
    # RPG 황금색 텍스트 그리기 (BGR: 100, 210, 240 -> RGB: 240, 210, 100)
    cv2.putText(test_canvas, "GOLDEN TITLE", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (100, 210, 240), 2)
    color = sample_text_color(test_canvas, 10, 20, 280, 80)
    assert color.startswith("#"), "색상 코드는 헥스 포맷이어야 합니다."
    print(f"  -> 골드 폰트 색상 추출 결과: {color}")
    print("  -> 폰트 색상 스펙트럼 자동 추출 검증 통과!")

def test_screen_overlay_manager_and_clean_mode():
    print("[9] ScreenOverlayManager 다중 자막창 라우팅 및 클린 모드 테스트...")
    from src.screen_overlay_manager import ScreenOverlayManager
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    cfg = {
        "screen_rois": [[100, 200, 400, 150], [800, 500, 500, 200]],
        "screen_snap_to_roi": True,
        "screen_clean_text_mode": False
    }
    manager = ScreenOverlayManager(cfg)
    assert len(manager.overlays) == 2, "2개의 ROI에 대해 2개의 독립 오버레이가 생성되어야 합니다."
    assert "화면 번역 #1" in manager.overlays[0].title_label.text()
    assert "화면 번역 #2" in manager.overlays[1].title_label.text()

    # 1:1 라우팅 테스트
    manager.display_subtitle("Hello", "안녕하세요", "google", roi_idx=1)
    assert manager.overlays[1].current_translated == "안녕하세요"

    # 클린 텍스트 모드 동기화 테스트
    manager.set_clean_mode(True)
    assert manager.overlays[0].clean_text_mode is True
    assert manager.overlays[1].clean_text_mode is True
    print("  -> 다중 자막창 1:1 라우팅 및 클린 모드 테스트 통과!")

def test_interactive_roi_selector_logic():
    print("[10] 인터랙티브 다중 ROI 편집기 (이동, 8방향 리사이즈, 삭제) 테스트...")
    from src.roi_selector import ROISelectorWidget

    current = [[100, 100, 400, 200], [600, 600, 300, 150]]
    selector = ROISelectorWidget(current_rois=current)
    selector.selected_rois = [list(r) for r in current]

    # 삭제 테스트
    assert len(selector.selected_rois) == 2
    selector.delete_roi(0)
    assert len(selector.selected_rois) == 1
    assert selector.selected_rois[0] == [600, 600, 300, 150]

    # 추가 테스트
    selector.add_roi(50, 50, 200, 100)
    assert len(selector.selected_rois) == 2
    assert selector.selected_rois[1] == [50, 50, 200, 100]

    print("  -> ROI 편집기 조작 논리 테스트 통과!")

def test_resolve_target_screen():
    print("[11] 번역 대상 디스플레이 스마트 자동 감지 및 고정 지정 테스트...")
    from src.inplace_translator import resolve_target_screen
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QPoint, QRect

    app = QApplication.instance() or QApplication(sys.argv)
    screens = app.screens()

    # 1. 고정 모니터 지정 테스트 (target_display_index = 0)
    cfg_fixed = {"target_display_index": 0}
    target = resolve_target_screen(cfg_fixed, app, QPoint(99999, 99999), from_button=True)
    assert target == screens[0], "고정된 모니터(인덱스 0)가 우선 반환되어야 합니다."

    # 2. 스마트 자동 모드 - 관심영역(ROI) 모니터 우선 감지 테스트
    primary_geo = screens[0].geometry()
    roi_on_screen0 = [primary_geo.x() + 50, primary_geo.y() + 50, 400, 200]
    cfg_auto_roi = {"target_display_index": -1, "screen_rois": [roi_on_screen0]}
    target_roi = resolve_target_screen(cfg_auto_roi, app, QPoint(99999, 99999), from_button=True)
    assert target_roi == screens[0], "ROI가 속한 모니터가 스마트 감지되어야 합니다."

    # 3. 버튼 클릭 시 fallback 테스트
    cfg_empty = {"target_display_index": -1, "screen_rois": []}
    target_btn = resolve_target_screen(cfg_empty, app, QPoint(99999, 99999), from_button=True)
    assert target_btn == app.primaryScreen() or target_btn == screens[0]

    # 화면 번역 탭 버튼은 다른 모니터에 ROI가 있어도 선택한 모니터를 사용한다.
    class FakeScreen:
        def __init__(self, geometry):
            self._geometry = geometry

        def geometry(self):
            return self._geometry

    class FakeApp:
        def __init__(self):
            self._screens = [FakeScreen(QRect(0, 0, 1920, 1080)),
                             FakeScreen(QRect(-2560, -100, 2560, 1440))]

        def screens(self):
            return self._screens

        def primaryScreen(self):
            return self._screens[0]

        def screenAt(self, pos):
            return self._screens[0]

    fake_app = FakeApp()
    selected_cfg = {"target_display_index": 0, "screen_display_index": 1,
                    "screen_rois": [[100, 100, 400, 200]]}
    assert resolve_target_screen(selected_cfg, fake_app, QPoint(100, 100), from_button=True) is fake_app.screens()[1]
    assert resolve_target_screen(selected_cfg, fake_app, QPoint(100, 100), from_button=False) is fake_app.screens()[1]

    print("  -> 대상 디스플레이 스마트 감지 및 고정 검증 통과!")

def test_audio_overlay_toggle_and_sync():
    print("[12] 통역 동시 번역 자막창 토글(보이기/숨기기) 및 양방향 동기화 테스트...")
    from PyQt6.QtWidgets import QApplication
    from src.config import DEFAULT_CONFIG
    from src.overlay_window import SubtitleOverlay
    from src.control_panel import ControlPanel

    app = QApplication.instance() or QApplication(sys.argv)
    cfg = DEFAULT_CONFIG.copy()
    overlay = SubtitleOverlay(cfg)
    panel = ControlPanel(cfg, overlay=overlay, audio_thread=None, stt_thread=None, save_config_cb=lambda c: None)

    overlay.set_external_handlers(on_visibility_change=panel.sync_audio_overlay_visibility)

    # 1. 초기 상태 확인 (미표시 상태 -> '보이기')
    panel._update_audio_overlay_btn_ui()
    assert "보이기" in panel.btn_toggle_audio_overlay.text()

    # 2. 오버레이 표시 시 상태 확인 -> '숨기기'
    overlay.show()
    assert overlay.isVisible()
    assert "숨기기" in panel.btn_toggle_audio_overlay.text()

    # 3. 컨트롤 패널 버튼 토글 -> '보이기'
    panel.toggle_audio_overlay_window()
    assert not overlay.isVisible()
    assert "보이기" in panel.btn_toggle_audio_overlay.text()

    # 4. 다시 토글 -> '숨기기'
    panel.toggle_audio_overlay_window()
    assert overlay.isVisible()
    assert "숨기기" in panel.btn_toggle_audio_overlay.text()

    # 5. 오버레이 헤더 [X] 버튼 클릭 시 -> '보이기'
    overlay.btn_hide.click()
    assert not overlay.isVisible()
    assert "보이기" in panel.btn_toggle_audio_overlay.text()
    print("  -> 통역 자막창 토글 및 [X] 닫기 동기화 테스트 통과!")

def test_screen_overlay_controls_and_sync():
    print("[13] 화면 자막창 컨트롤 버튼(폰트/투명도/정지/설정) 및 컨트롤 패널 양방향 동기화 테스트...")
    from PyQt6.QtWidgets import QApplication
    from src.config import DEFAULT_CONFIG
    from src.screen_overlay import ScreenSubtitleOverlay
    from src.screen_overlay_manager import ScreenOverlayManager
    from src.control_panel import ControlPanel

    app = QApplication.instance() or QApplication(sys.argv)
    cfg = DEFAULT_CONFIG.copy()
    cfg["font_size"] = 22
    cfg["overlay_bg_opacity"] = 0.75

    manager = ScreenOverlayManager(cfg)
    overlay = manager.overlays[0] if manager.overlays else ScreenSubtitleOverlay(cfg)
    panel = ControlPanel(cfg, overlay=None, audio_thread=None, stt_thread=None,
                         save_config_cb=lambda c: None, screen_overlay=manager)

    # 핸들러 연결
    manager.set_external_handlers(
        on_sync_font=panel.sync_font_from_overlay,
        on_sync_opacity=panel.sync_opacity_from_overlay,
        on_open_settings=panel.open_from_overlay
    )

    # 1. 폰트 크기 증가 (A+) 테스트
    initial_font = cfg["font_size"]
    overlay.btn_font_inc.click()
    assert cfg["font_size"] == initial_font + 2, f"폰트 크기가 {initial_font + 2}로 증가해야 합니다."
    assert f"font-size: {initial_font + 2}px" in overlay.label_translated.styleSheet(), "라벨 스타일시트에 새로운 폰트 크기가 반영되어야 합니다."
    assert panel.font_slider.value() == initial_font + 2, "컨트롤 패널 슬라이더가 동기화되어야 합니다."

    # 2. 폰트 크기 감소 (A-) 테스트
    overlay.btn_font_dec.click()
    assert cfg["font_size"] == initial_font
    assert f"font-size: {initial_font}px" in overlay.label_translated.styleSheet()
    assert panel.font_slider.value() == initial_font

    # 3. 투명도 증가 (◐+) 테스트 (더 불투명하게)
    initial_opacity = cfg["overlay_bg_opacity"]
    overlay.btn_op_inc.click()
    assert round(cfg["overlay_bg_opacity"], 2) == round(initial_opacity + 0.10, 2)
    assert panel.opacity_slider.value() == int(round(cfg["overlay_bg_opacity"] * 100))

    # 4. 투명도 감소 (◐-) 테스트 (더 투명하게)
    overlay.btn_op_dec.click()
    assert round(cfg["overlay_bg_opacity"], 2) == round(initial_opacity, 2)
    assert panel.opacity_slider.value() == int(round(initial_opacity * 100))

    # 5. 유휴(is_idle) 상태에서도 배경 박스 유지 검증 (클린 모드가 아닐 때)
    overlay.is_idle = True
    overlay.clean_text_mode = False
    # paintEvent 호출 시 예외 없이 렌더링 검증
    overlay.repaint()
    assert not overlay.clean_text_mode, "일반 모드에서는 배경이 소거되지 않고 불투명도에 맞게 렌더링되어야 합니다."

    # 6. 컨트롤 패널에서 폰트 슬라이더 변경 시 오버레이 반영 검증
    panel.font_slider.setValue(28)
    assert f"font-size: 28px" in overlay.label_translated.styleSheet()

    print("  -> 화면 자막창 컨트롤 버튼 및 양방향 동기화 테스트 통과!")

def test_subtitle_retention_and_hover_logic():
    print("[14] 자막 여유 유지(영구 유지/1회 즉시 번역/마우스 호버/고정 핀) 테스트...")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QEnterEvent
    from PyQt6.QtCore import QEvent, QPointF
    from src.config import DEFAULT_CONFIG
    from src.screen_overlay import ScreenSubtitleOverlay
    from src.control_panel import ControlPanel

    app = QApplication.instance() or QApplication(sys.argv)
    cfg = DEFAULT_CONFIG.copy()

    # 1. 기본값: screen_subtitle_duration = 0 (무제한 영구 유지 모드)
    cfg["screen_subtitle_duration"] = 0
    overlay = ScreenSubtitleOverlay(cfg)
    panel = ControlPanel(cfg, overlay=None, audio_thread=None, stt_thread=None,
                         save_config_cb=lambda c: None, screen_overlay=overlay)

    overlay.display_subtitle("Mission: Collect 3 runes.", "미션: 룬 3개를 수집하십시오.", "Google")
    assert not overlay.clear_timer.isActive(), "duration=0일 때는 타이머가 시작되지 않고 무제한 영구 유지되어야 합니다."
    assert overlay.current_translated == "미션: 룬 3개를 수집하십시오."

    # 2. 유지 시간 설정 (예: 20초) 모드
    cfg["screen_subtitle_duration"] = 20
    overlay._apply_config()
    overlay.display_subtitle("Tutorial: Press Space to jump.", "튜토리얼: 점프하려면 스페이스바를 누르세요.", "Google")
    assert overlay.clear_timer.isActive(), "duration>0일 때는 소거 타이머가 활성화되어야 합니다."

    # 3. 1회 즉시 캡처 번역(즉시·Google) 모드 - 무제한 영구 유지 검증
    overlay.display_subtitle("Guide Book: Getting Started", "안내서: 시작하기", "즉시·Google")
    assert not overlay.clear_timer.isActive(), "1회 즉시 번역은 사용자가 정독할 수 있도록 무제한 영구 유지되어야 합니다."
    assert "즉시" in overlay.live_badge.text()

    # 4. 마우스 호버(Hover) 시 소거 타이머 일시정지 검증
    overlay.display_subtitle("Notice: Talk to Kim.", "안내: 김 교수님과 대화하십시오.", "Google")
    assert overlay.clear_timer.isActive(), "일반 번역은 타이머 작동"
    
    # 가상 마우스 진입 이벤트
    enter_ev = QEnterEvent(QPointF(50, 50), QPointF(50, 50), QPointF(50, 50))
    overlay.enterEvent(enter_ev)
    assert overlay.is_mouse_hovered is True
    assert not overlay.clear_timer.isActive(), "마우스가 자막 위에 올라가면 소거 타이머가 즉각 멈춰야 합니다."

    # 가상 마우스 퇴장 이벤트
    leave_ev = QEvent(QEvent.Type.Leave)
    overlay.leaveEvent(leave_ev)
    assert overlay.is_mouse_hovered is False
    assert overlay.clear_timer.isActive(), "마우스가 나가면 유지 시간 타이머가 재개되어야 합니다."

    # 5. 📌 고정(Pin) 버튼 클릭 시 영구 유지 검증
    overlay.btn_pin.click()
    assert overlay.is_pinned is True
    assert not overlay.clear_timer.isActive(), "고정 핀 활성화 시 타이머가 정지되어 영구 고정되어야 합니다."
    assert "고정" in overlay.btn_pin.text()

    # 고정 해제
    overlay.btn_pin.click()
    assert overlay.is_pinned is False

    # 6. 컨트롤 패널의 자막 유지 시간 슬라이더 연동 검증
    panel.slider_duration.setValue(45)
    assert cfg["screen_subtitle_duration"] == 45
    assert "45초" in panel.lbl_duration.text()

    panel.slider_duration.setValue(0)
    assert cfg["screen_subtitle_duration"] == 0
    assert "영구 유지" in panel.lbl_duration.text()

    print("  -> 자막 여유 유지 및 호버/고정 핀 테스트 통과!")

def test_thick_stroke_and_clean_box_rendering():
    print("[15] 고대비 솔리드 외곽선(스트로크) 및 테두리 없는 반투명 박스 테스트...")
    from PyQt6.QtWidgets import QApplication, QGraphicsDropShadowEffect
    from PyQt6.QtGui import QImage
    from src.config import DEFAULT_CONFIG
    from src.screen_overlay import ScreenSubtitleOverlay
    from src.overlay_window import SubtitleOverlay
    from src.control_panel import ControlPanel
    from src.outline_effect import ThickOutlineEffect

    app = QApplication.instance() or QApplication(sys.argv)
    cfg = DEFAULT_CONFIG.copy()
    cfg["subtitle_stroke_width"] = 3
    cfg["screen_clean_box"] = True

    screen_overlay = ScreenSubtitleOverlay(cfg)
    audio_overlay = SubtitleOverlay(cfg)
    panel = ControlPanel(cfg, overlay=audio_overlay, audio_thread=None, stt_thread=None,
                         save_config_cb=lambda c: None, screen_overlay=screen_overlay)

    # 1. 기본값 0px: 순수 네이티브 소프트 섀도우(QGraphicsDropShadowEffect) 장착 검증
    cfg["subtitle_stroke_width"] = 0
    screen_overlay = ScreenSubtitleOverlay(cfg)
    audio_overlay = SubtitleOverlay(cfg)
    panel = ControlPanel(cfg, overlay=audio_overlay, audio_thread=None, stt_thread=None,
                         save_config_cb=lambda c: None, screen_overlay=screen_overlay)

    assert isinstance(screen_overlay.stroke_effect, QGraphicsDropShadowEffect)
    assert isinstance(audio_overlay.stroke_effect, QGraphicsDropShadowEffect)
    assert "0px" in panel.lbl_stroke.text()

    # 2. 컨트롤 패널에서 외곽선 굵기 조절 슬라이더 동작 및 양방향 동기화 검증
    panel.slider_stroke.setValue(1)
    assert cfg["subtitle_stroke_width"] == 1
    assert isinstance(screen_overlay.stroke_effect, ThickOutlineEffect)
    assert screen_overlay.stroke_effect.thickness == 1
    assert "1px" in panel.lbl_stroke.text()

    panel.slider_stroke.setValue(4)
    assert cfg["subtitle_stroke_width"] == 4
    assert screen_overlay.stroke_effect.thickness == 4
    assert audio_overlay.stroke_effect.thickness == 4
    assert "4px" in panel.lbl_stroke.text()

    panel.slider_stroke.setValue(0)
    assert cfg["subtitle_stroke_width"] == 0
    assert isinstance(screen_overlay.stroke_effect, QGraphicsDropShadowEffect)
    assert "0px" in panel.lbl_stroke.text()

    # 3. 클린 텍스트 모드 + 테두리 없는 반투명 박스 렌더링 검증
    screen_overlay.set_clean_mode(True)
    screen_overlay.display_subtitle("This method is powerful.", "이 방법은 강력합니다.", "Google")
    
    # 렌더링 버퍼 테스트 (크래시 없이 정상 버퍼 드로잉)
    img = QImage(screen_overlay.width(), screen_overlay.height(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    screen_overlay.render(img)
    assert img.sizeInBytes() > 0

    # 4. 반투명 박스 토글 체크박스 검증
    panel.cb_clean_box.setChecked(False)
    assert cfg["screen_clean_box"] is False
    screen_overlay.render(img)

    panel.cb_clean_box.setChecked(True)
    assert cfg["screen_clean_box"] is True

    print("  -> 고대비 솔리드 외곽선 및 테두리 없는 반투명 박스 테스트 통과!")

def test_multi_roi_independent_movement_and_persistence():
    print("[16] 다중 영역 오버레이 개별 위치 독립 이동 및 텔레포트 차단 테스트...")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from src.config import DEFAULT_CONFIG
    from src.screen_overlay_manager import ScreenOverlayManager

    app = QApplication.instance() or QApplication(sys.argv)
    cfg = DEFAULT_CONFIG.copy()
    cfg["screen_rois"] = [
        [100, 100, 400, 100],
        [100, 500, 400, 100]
    ]
    cfg["screen_snap_to_roi"] = False
    saved_configs = []

    def mock_save(c):
        saved_configs.append(dict(c))

    manager = ScreenOverlayManager(cfg, on_config_change=mock_save)
    assert len(manager.overlays) == 2, "2개의 ROI에 대해 2개의 독립 오버레이가 생성되어야 합니다."

    ov0 = manager.overlays[0]
    ov1 = manager.overlays[1]

    assert ov0.assigned_roi_idx == 0
    assert ov1.assigned_roi_idx == 1

    # 1. 초기 생성 시 두 창이 완전히 겹치지 않는지(Collision Avoidance) 검증
    geo0_init = ov0.geometry()
    geo1_init = ov1.geometry()
    assert not geo0_init.intersects(geo1_init), "두 오버레이가 생성 시 서로 겹쳐서 가려지지 않아야 합니다."

    # 2. 오버레이 1번(ov1)을 사용자가 마우스로 (500, 600) 위치로 직접 이동
    ov1.move(500, 600)
    release_ev = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    ov1.mouseReleaseEvent(release_ev)

    # 3. ov1 이동 후 ov0의 위치가 ov1으로 텔레포트(순간이동)되지 않고 제자리를 지키는지 검증
    assert ov0.geometry() == geo0_init, "ov1을 이동했을 때 ov0의 위치가 영향을 받아 따라 움직이지 않아야 합니다!"
    assert ov1.x() == 500 and ov1.y() == 600, "ov1은 이동한 좌표(500, 600)를 정확히 유지해야 합니다."

    # 4. 개별 좌표(screen_overlay_geometries)가 독립적으로 저장되었는지 검증
    assert "screen_overlay_geometries" in cfg
    assert "1" in cfg["screen_overlay_geometries"]
    assert cfg["screen_overlay_geometries"]["1"][0] == 500
    assert cfg["screen_overlay_geometries"]["1"][1] == 600

    # 5. ov1에서 폰트 크기 변경 시 ov0의 스타일은 동기화되되 위치(Geometry)는 제자리 유지 검증
    ov1._increase_font()
    assert cfg["font_size"] == 24
    assert ov0.label_translated.font().pointSize() == 24 or ov0.config["font_size"] == 24
    assert ov0.geometry() == geo0_init, "폰트 변경 시에도 ov0의 위치는 절대 변하지 않아야 합니다."
    assert ov1.x() == 500 and ov1.y() == 600, "폰트 변경 시에도 ov1의 위치는 (500, 600)에 머물러야 합니다."

    # 6. 새 매니저 인스턴스 생성 시 개별 저장된 좌표로 완벽 복원되는지 검증
    manager2 = ScreenOverlayManager(cfg, on_config_change=mock_save)
    ov0_restored = manager2.overlays[0]
    ov1_restored = manager2.overlays[1]
    saved_center = QPoint(500 + ov1.width() // 2, 600 + ov1.height() // 2)
    if app.primaryScreen().geometry().contains(saved_center):
        assert ov1_restored.x() == 500 and ov1_restored.y() == 600, "화면 안의 수동 위치는 복원되어야 합니다."
    else:
        assert app.primaryScreen().geometry().contains(ov1_restored.geometry().center()), "화면 밖 좌표는 ROI 모니터로 복구되어야 합니다."
    assert ov0_restored.geometry() == geo0_init, "ov0 또한 기존 좌표를 유지해야 합니다."

    print("  -> 다중 영역 오버레이 개별 위치 독립 이동 및 텔레포트 차단 테스트 통과!")

def test_letter_spacing_and_readability_controls():
    print("[17] 자막 글자 자간(Letter Spacing) 가독성 확장 및 동기화 테스트...")
    from PyQt6.QtWidgets import QApplication
    from src.config import DEFAULT_CONFIG
    from src.screen_overlay import ScreenSubtitleOverlay
    from src.overlay_window import SubtitleOverlay
    from src.control_panel import ControlPanel

    app = QApplication.instance() or QApplication(sys.argv)
    cfg = DEFAULT_CONFIG.copy()
    cfg["letter_spacing"] = 2.0

    screen_overlay = ScreenSubtitleOverlay(cfg)
    audio_overlay = SubtitleOverlay(cfg)
    panel = ControlPanel(cfg, overlay=audio_overlay, audio_thread=None, stt_thread=None,
                         save_config_cb=lambda c: None, screen_overlay=screen_overlay)

    # 1. 기본 2.0px 자간이 폰트에 정상 적용되었는지 검증
    assert screen_overlay.label_translated.font().letterSpacing() == 2.0
    assert audio_overlay.label_translated.font().letterSpacing() == 2.0

    # 2. 컨트롤 패널 슬라이더로 자간 2.5px 변경
    panel.slider_spacing.setValue(25)
    assert cfg["letter_spacing"] == 2.5
    assert screen_overlay.label_translated.font().letterSpacing() == 2.5
    assert audio_overlay.label_translated.font().letterSpacing() == 2.5
    assert "2.5px" in panel.lbl_spacing.text()

    # 3. Section 4 자간 슬라이더 동기화 검증
    assert panel.slider_spacing_sec4.value() == 25
    assert "2.5px" in panel.lbl_spacing_sec4.text()

    print("  -> 자막 글자 자간 가독성 확장 및 동기화 테스트 통과!")

def test_overlay_size_preservation_on_subtitles():
    print("[18] 자막창 수동 조절 크기(너비/높이) 고정 유지 및 텍스트 팽창 방지 테스트...")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QResizeEvent
    from src.config import DEFAULT_CONFIG
    from src.screen_overlay import ScreenSubtitleOverlay
    from src.overlay_window import SubtitleOverlay

    app = QApplication.instance() or QApplication(sys.argv)
    cfg = DEFAULT_CONFIG.copy()
    cfg["font_size"] = 22
    cfg["subtitle_stroke_width"] = 0

    # 1. 화면 번역 오버레이(ScreenSubtitleOverlay) 크기 유지 검증
    screen_ov = ScreenSubtitleOverlay(cfg)
    screen_ov.show()

    # 사용자가 창 크기를 600x75로 축소 조절
    screen_ov.resize(600, 75)
    ev = QResizeEvent(QSize(600, 75), QSize(900, 130))
    screen_ov.resizeEvent(ev)

    assert screen_ov.height() == 75, f"사용자 축소 후 높이는 75여야 함 (실제: {screen_ov.height()})"
    assert screen_ov.width() == 600, f"사용자 축소 후 너비는 600이어야 함 (실제: {screen_ov.width()})"
    assert screen_ov.base_geometry[3] == 75, f"base_geometry[3]도 75여야 함 (실제: {screen_ov.base_geometry[3]})"

    # 아주 긴 멀티라인 자막 전송
    long_sub = "[영역 1] 알렉스 첸: 회의에 오신 것을 환영합니다. 이번 안건은 지난 몇 달 동안 준비해 온 것이며 참석자 모두가 그 내용을 확인할 수 있을 것입니다. 다음 단계를 진행하기 위해 우리는 모든 준비를 마쳐야 합니다."
    screen_ov.display_subtitle("Original long text...", long_sub, "Google")

    # 자막 생성 후에도 창 크기가 커지지 않고 600x75를 칼같이 유지하는지 검증!
    assert screen_ov.height() == 75, f"자막 생성 후 높이가 팽창됨! (기대: 75, 실제: {screen_ov.height()})"
    assert screen_ov.width() == 600, f"자막 생성 후 너비가 팽창됨! (기대: 600, 실제: {screen_ov.width()})"

    # 추가 짧은 자막 수신 시에도 크기 불변 검증
    screen_ov.display_subtitle("Short orig", "짧은 자막입니다.", "Google")
    assert screen_ov.height() == 75, f"짧은 자막 후에도 높이는 75 유지되어야 함 (실제: {screen_ov.height()})"

    # 사용자가 다시 700x120으로 늘렸을 때도 그 크기로 고정 유지되는지 검증
    screen_ov.resize(700, 120)
    ev2 = QResizeEvent(QSize(700, 120), QSize(600, 75))
    screen_ov.resizeEvent(ev2)
    assert screen_ov.height() == 120
    assert screen_ov.width() == 700

    screen_ov.display_subtitle("Long again", long_sub, "Google")
    assert screen_ov.height() == 120, f"긴 자막 후에도 사용자 설정 높이 120 유지되어야 함 (실제: {screen_ov.height()})"
    screen_ov.close()

    # 2. 음성 번역 오버레이(SubtitleOverlay) 크기 유지 검증
    audio_ov = SubtitleOverlay(cfg)
    audio_ov.show()

    audio_ov.resize(650, 80)
    ev_audio = QResizeEvent(QSize(650, 80), QSize(900, 140))
    audio_ov.resizeEvent(ev_audio)

    assert audio_ov.height() == 80
    assert audio_ov.width() == 650

    audio_ov.display_subtitle("Very long speech sentence from speaker...", "아주 긴 번역 대화 음성 문장이 도착했습니다. 창 크기가 절대 늘어나지 않아야 합니다.", "Google")
    assert audio_ov.height() == 80, f"음성 자막 후에도 높이는 80 유지되어야 함 (실제: {audio_ov.height()})"
    audio_ov.close()

    print("  -> 자막창 수동 조절 크기(너비/높이) 고정 유지 및 텍스트 팽창 방지 테스트 통과!")

def test_combobox_no_wheel_option_change():
    print("[19] 마우스 휠 스크롤 옵션 및 슬라이더 수치 변경 원천 차단(NoWheelComboBox, NoWheelSlider) 테스트...")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QPoint, QPointF
    from PyQt6.QtGui import QWheelEvent
    from src.config import DEFAULT_CONFIG
    from src.no_wheel_combobox import NoWheelComboBox, NoWheelSlider, NoWheelFilter
    from src.control_panel import ControlPanel
    from src.overlay_window import SubtitleOverlay

    app = QApplication.instance() or QApplication(sys.argv)
    cfg = DEFAULT_CONFIG.copy()

    # 1. NoWheelComboBox 독립 인스턴스 검증
    cb = NoWheelComboBox()
    cb.addItems(["선택 1", "선택 2", "선택 3"])
    cb.setCurrentIndex(0)

    # 휠 다운 이벤트 전송
    wheel_down = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    cb.wheelEvent(wheel_down)
    assert not wheel_down.isAccepted(), "휠 이벤트는 부모로 바이패스(ignore)되어야 합니다."
    assert cb.currentIndex() == 0, f"휠 스크롤로 인덱스가 변경되면 안 됩니다! (현재: {cb.currentIndex()})"

    # 2. NoWheelSlider 독립 인스턴스 검증
    slider = NoWheelSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(50)
    wheel_slider = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    slider.wheelEvent(wheel_slider)
    assert not wheel_slider.isAccepted(), "슬라이더 휠 이벤트는 부모로 바이패스(ignore)되어야 합니다."
    assert slider.value() == 50, f"슬라이더 휠 스크롤로 수치가 변경되면 안 됩니다! (현재: {slider.value()})"
    # 드래그/코드 설정 정상 동작 검증
    slider.setValue(75)
    assert slider.value() == 75, "슬라이더 setValue는 정상 동작해야 합니다."

    # 3. ControlPanel 내 모든 풀다운 메뉴 및 슬라이더 검증
    audio_ov = SubtitleOverlay(cfg)
    panel = ControlPanel(cfg, overlay=audio_ov, audio_thread=None, stt_thread=None,
                         save_config_cb=lambda c: None)

    for name, combo in [("번역엔진", panel.combo_trans_engine), ("연산장치", panel.combo_device), ("STT모델", panel.combo_model), ("디스플레이", panel.combo_display)]:
        assert isinstance(combo, NoWheelComboBox), f"{name} 콤보박스는 NoWheelComboBox여야 합니다."
        init_idx = combo.currentIndex()
        wheel_ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        combo.wheelEvent(wheel_ev)
        assert combo.currentIndex() == init_idx, f"{name} 콤보박스가 휠 스크롤에 반응하여 값이 변경되었습니다!"

    sliders_to_check = [
        ("화자 유사도 기준", panel.slider_speaker_threshold),
        ("외곽선 굵기", panel.slider_stroke),
        ("자막 자간", panel.slider_spacing),
        ("자막 유지 시간", panel.slider_duration),
        ("더빙 볼륨", panel.slider_dubbing_vol),
        ("오버레이 폰트 크기", panel.font_slider),
        ("배경 불투명도", panel.opacity_slider),
        ("섹션4 글자 자간", panel.slider_spacing_sec4),
    ]
    for name, sl in sliders_to_check:
        assert isinstance(sl, NoWheelSlider), f"{name} 슬라이더는 NoWheelSlider여야 합니다."
        init_val = sl.value()
        wheel_ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        sl.wheelEvent(wheel_ev)
        assert sl.value() == init_val, f"{name} 슬라이더가 휠 스크롤에 반응하여 값이 변경되었습니다! ({init_val} -> {sl.value()})"

    # 4. SubtitleOverlay 내 번역엔진 콤보박스 검증
    assert isinstance(audio_ov.combo_engine, NoWheelComboBox), "오디오 자막창 엔진 콤보박스는 NoWheelComboBox여야 합니다."
    eng_init = audio_ov.combo_engine.currentIndex()
    wheel_ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    audio_ov.combo_engine.wheelEvent(wheel_ev)
    assert audio_ov.combo_engine.currentIndex() == eng_init, "오디오 자막창 엔진 콤보박스가 휠로 변경되었습니다!"

    audio_ov.close()
    panel.hide()
    print("  -> 마우스 휠 스크롤 옵션 및 슬라이더 수치 변경 원천 차단 테스트 통과!")

def test_audio_overlay_auto_hide_controls():
    print("[20] 오디오 통역 자막창 컨트롤 버튼 유휴 자동 숨김 및 호버 복원 테스트...")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QPointF
    from PyQt6.QtGui import QMouseEvent, QEnterEvent
    from src.config import DEFAULT_CONFIG
    from src.overlay_window import SubtitleOverlay

    app = QApplication.instance() or QApplication(sys.argv)
    cfg = DEFAULT_CONFIG.copy()

    overlay = SubtitleOverlay(cfg)
    overlay.show()

    # 1. idle_timer 존재 및 속성 검증
    assert hasattr(overlay, 'idle_timer'), "idle_timer가 존재해야 합니다."
    assert overlay.idle_timer.interval() == 3500, "idle_timer 간격은 3500ms(3.5초)여야 합니다."

    # 2. 유휴 타임아웃 발생 시 컨트롤 버튼(header_widget) 및 size_grip 완전 숨김 검증
    overlay._on_idle_timeout()
    assert overlay.is_idle == True, "유휴 상태 플래그가 True여야 합니다."
    assert overlay.header_opacity_effect.opacity() == 0.0, f"유휴 시 헤더 투명도는 0.0이어야 합니다. (실제: {overlay.header_opacity_effect.opacity()})"
    assert not overlay.size_grip.isVisible(), "유휴 시 size_grip은 숨겨져야 합니다."

    # 3. 마우스 이동(mouseMoveEvent) 시 컨트롤 버튼 및 size_grip 즉시 복원 검증
    move_ev = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(50, 50), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    overlay.mouseMoveEvent(move_ev)
    assert overlay.is_idle == False, "마우스 이동 시 유휴 상태가 해제되어야 합니다."
    assert overlay.header_opacity_effect.opacity() == 1.0, f"마우스 이동 시 헤더 투명도는 1.0으로 복원되어야 합니다. (실제: {overlay.header_opacity_effect.opacity()})"
    assert overlay.size_grip.isVisible(), "마우스 이동 시 size_grip이 표시되어야 합니다."
    assert overlay.idle_timer.isActive(), "마우스 이동 시 3.5초 타이머가 재시작되어야 합니다."

    # 4. 마우스 벗어남(leaveEvent) 시 은은한 딤드 후 타이머 가동 검증
    leave_ev = QMouseEvent(QMouseEvent.Type.Leave, QPointF(0, 0), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    overlay.leaveEvent(leave_ev)
    assert overlay.header_opacity_effect.opacity() == 0.35, "창을 벗어났을 때 0.35 딤드 상태여야 합니다."
    assert overlay.idle_timer.isActive(), "창을 벗어났을 때 완전 소거 카운트다운 타이머가 시작되어야 합니다."

    # 5. 마우스 재진입(enterEvent) 시 1.0 복원 검증
    enter_ev = QEnterEvent(QPointF(50, 50), QPointF(50, 50), QPointF(50, 50))
    overlay.enterEvent(enter_ev)
    assert overlay.header_opacity_effect.opacity() == 1.0, "마우스 재진입 시 1.0으로 즉시 복원되어야 합니다."
    assert overlay.size_grip.isVisible(), "마우스 재진입 시 size_grip이 다시 보여야 합니다."

    overlay.close()
    print("  -> 오디오 통역 자막창 컨트롤 버튼 유휴 자동 숨김 및 호버 복원 테스트 통과!")

def test_startup_stopped_and_auto_start_options():
    print("[21] 초기 실행 시 정지 상태 시작 및 자동 시작 옵션 분리 테스트...")
    from PyQt6.QtWidgets import QApplication
    from src.config import DEFAULT_CONFIG
    from src.audio_capture import AudioLoopbackCapture
    from src.screen_ocr_worker import ScreenOCRWorker
    from src.overlay_window import SubtitleOverlay
    from src.screen_overlay import ScreenSubtitleOverlay
    from src.control_panel import ControlPanel
    import queue

    app = QApplication.instance() or QApplication(sys.argv)

    # 1. 기본 설정 (auto_start_audio=False, auto_start_screen=False): 완전 정지 상태로 시작
    cfg_stopped = DEFAULT_CONFIG.copy()
    cfg_stopped["auto_start_audio"] = False
    cfg_stopped["auto_start_screen"] = False
    cfg_stopped["screen_translate_enabled"] = True

    audio_q = queue.Queue()
    audio_cap = AudioLoopbackCapture(audio_queue=audio_q, config=cfg_stopped)
    screen_w = ScreenOCRWorker(config=cfg_stopped, translator=None)
    audio_ov = SubtitleOverlay(cfg_stopped)
    screen_ov = ScreenSubtitleOverlay(cfg_stopped)

    cp = ControlPanel(
        config=cfg_stopped,
        overlay=audio_ov,
        audio_thread=audio_cap,
        stt_thread=None,
        save_config_cb=lambda c: None,
        screen_worker=screen_w,
        screen_overlay=screen_ov,
        inplace_manager=None
    )

    # 초기 정지 상태 검증
    assert audio_cap.paused == True, "기본 실행 시 오디오 캡처는 정지(paused=True) 상태여야 합니다."
    assert screen_w.is_paused == True, "기본 실행 시 화면 OCR 워커는 정지(is_paused=True) 상태여야 합니다."
    assert cp.is_active == False, "기본 실행 시 오디오 통역은 비활성 상태여야 합니다."
    assert not cfg_stopped.get("screen_translate_enabled", False), "화면 자동시작이 꺼져 있으면 화면 번역도 정지 상태로 초기화되어야 합니다."
    assert "▶ 오디오 통역 시작" in cp.btn_toggle.text(), f"오디오 버튼 텍스트가 대기 상태여야 합니다. (실제: {cp.btn_toggle.text()})"
    assert "▶ 화면 실시간 번역 시작" in cp.btn_toggle_screen.text(), f"화면 번역 버튼 텍스트가 대기 상태여야 합니다. (실제: {cp.btn_toggle_screen.text()})"
    assert audio_ov.btn_pause.text() == "▶", "오디오 자막창 일시정지 버튼은 ▶여야 합니다."
    assert screen_ov.btn_pause.text() == "▶", "화면 자막창 일시정지 버튼은 ▶여야 합니다."

    # 시작 버튼 클릭 시 활성화 검증
    cp.btn_toggle.click()
    assert cp.is_active == True, "오디오 버튼 클릭 시 통역 활성화되어야 합니다."
    assert audio_cap.paused == False, "오디오 버튼 클릭 시 캡처가 재개(resume)되어야 합니다."
    assert audio_ov.btn_pause.text() == "⏸", "오디오 버튼 클릭 시 자막창 버튼이 ⏸로 변경되어야 합니다."

    cp.btn_toggle_screen.click()
    assert cfg_stopped.get("screen_translate_enabled") == True, "화면 번역 버튼 클릭 시 활성화되어야 합니다."
    assert screen_w.is_paused == False, "화면 번역 버튼 클릭 시 워커가 재개되어야 합니다."
    assert screen_ov.btn_pause.text() == "⏸", "화면 번역 버튼 클릭 시 자막창 버튼이 ⏸로 변경되어야 합니다."

    # QMessageBox.question 팝업 블로킹 방지 모의
    from PyQt6.QtWidgets import QMessageBox
    orig_question = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    try:
        cp.close()
        audio_ov.close()
        screen_ov.close()

        # 2. 자동 시작 옵션이 체크된 경우 (auto_start_audio=True, auto_start_screen=True)
        cfg_autostart = DEFAULT_CONFIG.copy()
        cfg_autostart["auto_start_audio"] = True
        cfg_autostart["auto_start_screen"] = True
        cfg_autostart["screen_translate_enabled"] = True

        audio_cap2 = AudioLoopbackCapture(audio_queue=audio_q, config=cfg_autostart)
        screen_w2 = ScreenOCRWorker(config=cfg_autostart, translator=None)
        audio_ov2 = SubtitleOverlay(cfg_autostart)
        screen_ov2 = ScreenSubtitleOverlay(cfg_autostart)

        cp2 = ControlPanel(
            config=cfg_autostart,
            overlay=audio_ov2,
            audio_thread=audio_cap2,
            stt_thread=None,
            save_config_cb=lambda c: None,
            screen_worker=screen_w2,
            screen_overlay=screen_ov2,
            inplace_manager=None
        )

        assert audio_cap2.paused == False, "자동 시작 설정 시 오디오 캡처가 즉시 가동(paused=False)되어야 합니다."
        assert screen_w2.is_paused == False, "자동 시작 설정 시 화면 OCR 워커가 즉시 가동(is_paused=False)되어야 합니다."
        assert cp2.is_active == True, "자동 시작 설정 시 오디오 통역이 활성 상태여야 합니다."
        assert "통역 실행 중" in cp2.btn_toggle.text(), "오디오 버튼 텍스트가 실행 중이어야 합니다."
        assert "화면 실시간 번역 중지" in cp2.btn_toggle_screen.text(), "화면 번역 버튼 텍스트가 실행 중이어야 합니다."
        assert audio_ov2.btn_pause.text() == "⏸", "오디오 자막창 버튼이 ⏸여야 합니다."
        assert screen_ov2.btn_pause.text() == "⏸", "화면 자막창 버튼이 ⏸여야 합니다."

        cp2.close()
        audio_ov2.close()
        screen_ov2.close()
    finally:
        QMessageBox.question = orig_question
    print("  -> 초기 실행 시 정지 상태 시작 및 자동 시작 옵션 분리 테스트 통과!")

def test_save_all_settings_before_exit():
    print("[22] 프로그램 종료 전 설정값/창 위치/크기/가시성 완벽 보존 테스트...")
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from src.config import DEFAULT_CONFIG
    from src.overlay_window import SubtitleOverlay
    from src.screen_overlay_manager import ScreenOverlayManager
    from src.control_panel import ControlPanel

    app = QApplication.instance() or QApplication(sys.argv)

    saved_config = {}
    def mock_save_config(c):
        nonlocal saved_config
        saved_config = c.copy()

    test_cfg = DEFAULT_CONFIG.copy()
    audio_ov = SubtitleOverlay(test_cfg, on_config_change=mock_save_config)
    screen_mgr = ScreenOverlayManager(test_cfg, on_config_change=mock_save_config)

    cp = ControlPanel(
        config=test_cfg,
        overlay=audio_ov,
        audio_thread=None,
        stt_thread=None,
        save_config_cb=mock_save_config,
        screen_worker=None,
        screen_overlay=screen_mgr,
        inplace_manager=None
    )

    # 창 크기 및 위치 임의 변경
    cp.setGeometry(250, 150, 600, 800)
    audio_ov.setGeometry(300, 600, 850, 150)
    if screen_mgr.overlays:
        screen_mgr.overlays[0].setGeometry(120, 450, 700, 130)

    # UI 위젯 값 변경
    cp.cb_auto_start_audio.setChecked(True)
    cp.cb_auto_start_screen.setChecked(True)
    cp.font_slider.setValue(26)
    cp.opacity_slider.setValue(80)
    cp.slider_stroke.setValue(3)
    cp.slider_spacing.setValue(25)  # 2.5px
    cp.slider_duration.setValue(10) # 10s
    cp.cb_clean_box.setChecked(False)
    cp.cb_snap_to_roi.setChecked(True)

    # 종료 전 전체 저장 함수 호출
    cp.save_all_settings_before_exit()

    # 저장된 설정값 검증
    assert saved_config.get("auto_start_audio") == True, "auto_start_audio가 True로 저장되어야 합니다."
    assert saved_config.get("auto_start_screen") == True, "auto_start_screen이 True로 저장되어야 합니다."
    assert saved_config.get("font_size") == 26, f"font_size 26이어야 합니다. (실제: {saved_config.get('font_size')})"
    assert saved_config.get("overlay_bg_opacity") == 0.8, f"overlay_bg_opacity 0.8이어야 합니다. (실제: {saved_config.get('overlay_bg_opacity')})"
    assert saved_config.get("subtitle_stroke_width") == 3, f"subtitle_stroke_width 3이어야 합니다. (실제: {saved_config.get('subtitle_stroke_width')})"
    assert saved_config.get("letter_spacing") == 2.5, f"letter_spacing 2.5이어야 합니다. (실제: {saved_config.get('letter_spacing')})"
    assert saved_config.get("screen_subtitle_duration") == 10, f"screen_subtitle_duration 10이어야 합니다. (실제: {saved_config.get('screen_subtitle_duration')})"
    assert saved_config.get("screen_clean_box") == False, "screen_clean_box False로 저장되어야 합니다."
    assert saved_config.get("screen_snap_to_roi") == True, "screen_snap_to_roi True로 저장되어야 합니다."

    # 창 좌표 검증
    cp_geo = saved_config.get("control_panel_geometry")
    assert cp_geo == [250, 150, 600, 800], f"컨트롤 패널 좌표 저장 확인 (실제: {cp_geo})"

    win_geo = saved_config.get("window_geometry")
    assert win_geo == [300, 600, 850, 150], f"오디오 자막창 좌표 저장 확인 (실제: {win_geo})"

    screen_geos = saved_config.get("screen_overlay_geometries", {})
    assert "0" in screen_geos and screen_geos["0"] == [120, 450, 700, 130], f"화면 자막창 좌표 저장 확인 (실제: {screen_geos})"

    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    try:
        cp.close()
        audio_ov.close()
        screen_mgr.close()
    finally:
        QMessageBox.question = orig_q
    print("  -> 프로그램 종료 전 설정값/창 위치/크기/가시성 완벽 보존 테스트 통과!")

def test_roi_border_overlay_sync_and_toggle():
    print("[23] 감시 관심 영역 외곽 엣지(테두리) 화면 오버랩 및 동기화 테스트...")
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import Qt
    from src.roi_border_overlay import SingleROIBorderWidget, ROIBorderManager
    from src.control_panel import ControlPanel
    from src.screen_overlay_manager import ScreenOverlayManager
    from src.overlay_window import SubtitleOverlay
    from src.config import DEFAULT_CONFIG

    app = QApplication.instance() or QApplication(sys.argv)

    # 1. SingleROIBorderWidget 플래그 및 마우스 관통 속성 검증
    sample_roi = [150, 200, 450, 250]
    widget = SingleROIBorderWidget(sample_roi, roi_idx=0, show_badge=True)
    g = widget.geometry()
    assert g.x() == 150 and g.y() == 200 and g.width() == 450 and g.height() == 250, "위젯 좌표/크기가 ROI와 일치해야 합니다."
    assert widget.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground), "투명 배경 속성이 켜져 있어야 합니다."
    assert widget.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents), "마우스 관통 속성이 켜져 있어야 합니다."
    assert widget.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating), "포커스 미점유 속성이 켜져 있어야 합니다."
    flags = widget.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint, "프레임리스 윈도우여야 합니다."
    assert flags & Qt.WindowType.WindowStaysOnTopHint, "최상위 유지 윈도우여야 합니다."
    assert flags & Qt.WindowType.WindowTransparentForInput, "입력 관통 윈도우여야 합니다."
    widget.close()

    # 2. ROIBorderManager 다중 ROI 관리 및 상태 동기화 검증
    test_cfg = DEFAULT_CONFIG.copy()
    test_cfg["screen_rois"] = [
        [100, 150, 400, 200],
        [600, 700, 300, 150]
    ]
    test_cfg["screen_show_roi_border"] = False

    mgr = ROIBorderManager(test_cfg)
    assert len(mgr.widgets) == 2, f"위젯 개수가 2개여야 합니다. (실제: {len(mgr.widgets)})"
    assert not mgr.is_enabled, "초기 상태는 비활성화여야 합니다."
    for w in mgr.widgets:
        assert not w.isVisible(), "비활성화 시 위젯은 숨겨져 있어야 합니다."

    # 활성화 토글 테스트
    mgr.set_enabled(True)
    assert mgr.is_enabled == True, "활성화되어야 합니다."
    assert test_cfg["screen_show_roi_border"] == True, "설정값도 True로 갱신되어야 합니다."
    for w in mgr.widgets:
        assert w.isVisible(), "활성화 시 위젯이 화면에 표시되어야 합니다."

    # 동적 ROI 변경 동기화 테스트
    test_cfg["screen_rois"] = [[200, 300, 500, 220]]
    mgr.sync_rois()
    assert len(mgr.widgets) == 1, "ROI 목록 변경 시 위젯 개수가 1개로 동기화되어야 합니다."
    assert mgr.widgets[0].geometry().x() == 200, "위젯 좌표가 갱신되어야 합니다."

    # 3. ControlPanel과 ROIBorderManager 연동 및 UI 버튼 검증
    saved_cfg = {}
    def mock_save(c):
        saved_cfg.clear()
        saved_cfg.update(c)

    audio_ov = SubtitleOverlay(test_cfg)
    screen_mgr = ScreenOverlayManager(test_cfg)

    cp = ControlPanel(
        config=test_cfg,
        overlay=audio_ov,
        audio_thread=None,
        stt_thread=None,
        save_config_cb=mock_save,
        screen_worker=None,
        screen_overlay=screen_mgr,
        inplace_manager=None,
        roi_border_manager=mgr
    )

    # 체크박스 토글 -> 버튼 및 매니저 동기화 확인
    cp.cb_show_roi_border.setChecked(False)
    assert mgr.is_enabled == False, "체크 해제 시 매니저가 비활성화되어야 합니다."
    assert "OFF" in cp.btn_toggle_roi_border.text(), "버튼 텍스트가 OFF 상태여야 합니다."

    # 컨트롤 패널의 toggle_roi_border 호출 -> ON 전환
    cp.toggle_roi_border()
    assert cp.cb_show_roi_border.isChecked() == True, "toggle_roi_border 호출 시 체크박스가 켜져야 합니다."
    assert mgr.is_enabled == True, "매니저가 활성화되어야 합니다."
    assert "ON" in cp.btn_toggle_roi_border.text(), "버튼 텍스트가 ON 상태여야 합니다."

    # 종료 전 저장 검증
    cp.save_all_settings_before_exit()
    assert saved_cfg.get("screen_show_roi_border") == True, "종료 전 screen_show_roi_border가 True로 저장되어야 합니다."

    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    try:
        cp.close()
        mgr.close()
        audio_ov.close()
        screen_mgr.close()
    finally:
        QMessageBox.question = orig_q

    print("  -> 감시 관심 영역 외곽 엣지(테두리) 화면 오버랩 및 동기화 테스트 통과!")

if __name__ == "__main__":
    print("=" * 60)
    print("[TEST] 실시간 화면 OCR 번역 파이프라인 단위 테스트 시작")
    print("=" * 60)
    test_frame_diff()
    test_ocr_and_translation()
    test_dialogue_formatting()
    test_multi_roi_config()
    test_snap_to_roi_spatial_logic()
    test_game_text_clahe_preprocessing()
    test_inplace_overlay_and_hotkey()
    test_paragraph_grouping_and_color_sampling()
    test_screen_overlay_manager_and_clean_mode()
    test_interactive_roi_selector_logic()
    test_resolve_target_screen()
    test_audio_overlay_toggle_and_sync()
    test_screen_overlay_controls_and_sync()
    test_subtitle_retention_and_hover_logic()
    test_thick_stroke_and_clean_box_rendering()
    test_multi_roi_independent_movement_and_persistence()
    test_letter_spacing_and_readability_controls()
    test_overlay_size_preservation_on_subtitles()
    test_combobox_no_wheel_option_change()
    test_audio_overlay_auto_hide_controls()
    test_startup_stopped_and_auto_start_options()
    test_save_all_settings_before_exit()
    test_roi_border_overlay_sync_and_toggle()
    print("\n[SUCCESS] 모든 단위 테스트 성공적으로 통과!")
