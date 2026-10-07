import time
import re
import queue
import ctypes
from ctypes import wintypes
import threading
import numpy as np
import cv2
from PIL import Image

from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QRectF, QPointF, QObject, QTimer
from PyQt6.QtGui import (
    QPainter, QPainterPath, QColor, QFont, QPen, QBrush, QFontMetrics, QCursor, QImage
)

from src.screen_capture import preprocess_game_image
from src.screen_ocr_worker import clean_ocr_english_text, clean_ocr_text, is_valid_ocr_text
from src.hotkey_utils import parse_hotkey_string, normalize_hotkey_string, VK_MAP, QT_KEY_TO_NAME
from src.ui_theme import set_windows_dark_mode
from src.i18n import tr

VK_F4 = 0x73
HOTKEY_ID = 8848
WM_HOTKEY = 0x0312
PM_REMOVE = 1
QS_ALLINPUT = 0x04FF


def sample_text_color(img_bgr: np.ndarray, min_x: float, min_y: float, max_x: float, max_y: float) -> str:
    """
    게임 원본 화면에서 해당 텍스트 박스의 전경 폰트 색상을 자동 스펙트럼 추출합니다.
    - 골드/황금색 폰트 (제목/강조): #F6E06B
    - 실버/화이트 폰트 (본문/설명): #F4F4F4
    - 시안/하늘색 폰트: #00E5FF
    """
    if img_bgr is None:
        return "#FFFFFF"

    h, w = img_bgr.shape[:2]
    x1, y1 = max(0, int(min_x)), max(0, int(min_y))
    x2, y2 = min(w, int(max_x)), min(h, int(max_y))

    if x2 <= x1 or y2 <= y1:
        return "#FFFFFF"

    crop = img_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return "#FFFFFF"

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    bg_val = float(np.median(gray))
    max_val = float(np.max(gray))
    if max_val - bg_val < 15:
        return "#FFFFFF"

    # 배경과 글자의 중간 명도를 기준으로 텍스트 전경 픽셀만 정밀 분리
    thresh = bg_val + (max_val - bg_val) * 0.45
    mask = gray >= thresh
    if np.sum(mask) < 4:
        return "#FFFFFF"

    pts = crop[mask]
    median_bgr = np.median(pts, axis=0).astype(int)
    b, g, r = int(median_bgr[0]), int(median_bgr[1]), int(median_bgr[2])

    # 1. 골드/황금색 감지 (R, G가 높고 B가 상대적으로 낮음)
    if r > 150 and g > 125 and (r - b) > 30 and (g - b) > 15:
        r_boost = min(255, int(r * 1.15))
        g_boost = min(255, int(g * 1.12))
        b_boost = min(255, int(b * 0.85))
        return f"#{r_boost:02X}{g_boost:02X}{b_boost:02X}"

    # 2. 시안/하늘색 감지
    if b > 150 and g > 130 and (b - r) > 35:
        return f"#{r:02X}{g:02X}{b:02X}"

    # 3. 레드/주황색 감지
    if r > 160 and g < 120 and b < 120:
        return f"#{r:02X}{g:02X}{b:02X}"

    # 4. 실버 / 화이트 톤 (명도 보정)
    avg_val = int((r + g + b) / 3)
    if avg_val > 130:
        boost = min(255, int(avg_val * 1.25))
        return f"#{boost:02X}{boost:02X}{boost:02X}"

    return f"#{r:02X}{g:02X}{b:02X}"


def group_boxes_into_paragraphs(items: list, line_gap_ratio: float = 0.75, horiz_overlap_thresh: float = 0.20) -> list:
    """
    여러 줄 및 여러 단어로 파편화된 영문 텍스트 박스를 원본 문단(Paragraph) 형태로 지능형 병합합니다.
    - 1단계 (수평 병합): 동일한 행(Line)에 인접하여 배치된 단어/어절 단위 박스들을 하나의 행으로 완전 통합
    - 2단계 (수직 병합): 연속된 행들을 문단(Paragraph) 블록으로 병합하여 단어마다 말풍선이 난립하는 문제 원천 해결
    """
    if not items:
        return []

    parsed = []
    for box, text, score in items:
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        w = max(max_x - min_x, 1)
        h = max(max_y - min_y, 1)
        parsed.append({
            'box': box,
            'text': text,
            'score': score,
            'min_x': min_x, 'max_x': max_x,
            'min_y': min_y, 'max_y': max_y,
            'w': w, 'h': h,
            'cx': min_x + w / 2.0,
            'cy': min_y + h / 2.0
        })

    # Step 1: 같은 줄(Horizontal)에 위치한 단어/어절 단위 박스 1차 병합
    parsed.sort(key=lambda it: (it['min_y'], it['min_x']))
    lines = []
    for item in parsed:
        merged = False
        for line in lines:
            y_overlap = max(0, min(item['max_y'], line['max_y']) - max(item['min_y'], line['min_y']))
            min_h = min(item['h'], line['h'])
            # 높이의 40% 이상 Y가 겹치거나 Y 중심 거리가 50% 이내이면 같은 수평 라인으로 판정
            if y_overlap >= min_h * 0.4 or abs(item['cy'] - line['cy']) <= min_h * 0.5:
                x_gap = max(0, max(item['min_x'] - line['max_x'], line['min_x'] - item['max_x']))
                # 단어 간 수평 간격이 글자 높이의 3배 이하인 경우 같은 라인으로 통합
                if x_gap <= min_h * 3.0:
                    line['items'].append(item)
                    line['min_x'] = min(line['min_x'], item['min_x'])
                    line['max_x'] = max(line['max_x'], item['max_x'])
                    line['min_y'] = min(line['min_y'], item['min_y'])
                    line['max_y'] = max(line['max_y'], item['max_y'])
                    line['h'] = line['max_y'] - line['min_y']
                    line['cy'] = (line['min_y'] + line['max_y']) / 2.0
                    merged = True
                    break
        if not merged:
            lines.append({
                'items': [item],
                'min_x': item['min_x'], 'max_x': item['max_x'],
                'min_y': item['min_y'], 'max_y': item['max_y'],
                'h': item['h'], 'cy': item['cy']
            })

    # 수평 라인 간 추가 수렴 통합 (순서나 미세 배치 차이로 나뉜 동일 라인 완전 병합)
    changed = True
    while changed:
        changed = False
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                l1 = lines[i]
                l2 = lines[j]
                y_overlap = max(0, min(l1['max_y'], l2['max_y']) - max(l1['min_y'], l2['min_y']))
                min_h = min(l1['h'], l2['h'])
                if y_overlap >= min_h * 0.4 or abs(l1['cy'] - l2['cy']) <= min_h * 0.5:
                    x_gap = max(0, max(l1['min_x'] - l2['max_x'], l2['min_x'] - l1['max_x']))
                    if x_gap <= min_h * 3.0:
                        l1['items'].extend(l2['items'])
                        l1['min_x'] = min(l1['min_x'], l2['min_x'])
                        l1['max_x'] = max(l1['max_x'], l2['max_x'])
                        l1['min_y'] = min(l1['min_y'], l2['min_y'])
                        l1['max_y'] = max(l1['max_y'], l2['max_y'])
                        l1['h'] = l1['max_y'] - l1['min_y']
                        l1['cy'] = (l1['min_y'] + l1['max_y']) / 2.0
                        lines.pop(j)
                        changed = True
                        break
            if changed:
                break

    for line in lines:
        line['items'].sort(key=lambda it: it['min_x'])
        line['text'] = ' '.join(it['text'] for it in line['items'])
        line['scores'] = [it['score'] for it in line['items']]
        line['boxes'] = [it['box'] for it in line['items']]

    # Step 2: 연속된 행들을 문단(Paragraph) 블록으로 2차 수직 병합
    lines.sort(key=lambda l: l['min_y'])
    paragraphs = []
    for line in lines:
        merged = False
        for p in paragraphs:
            line_h = p['avg_h']
            v_gap = line['min_y'] - p['max_y']
            x_overlap = max(0, min(line['max_x'], p['max_x']) - max(line['min_x'], p['min_x']))
            min_w = min(line['max_x'] - line['min_x'], p['max_x'] - p['min_x'])
            overlap_ratio = x_overlap / max(min_w, 1)

            if -0.3 * line_h <= v_gap <= line_h * 1.3 and (overlap_ratio >= 0.2 or abs(line['min_x'] - p['min_x']) <= line_h * 2):
                p['lines'].append(line['text'])
                p['scores'].extend(line['scores'])
                p['boxes'].extend(line['boxes'])
                p['min_x'] = min(p['min_x'], line['min_x'])
                p['max_x'] = max(p['max_x'], line['max_x'])
                p['max_y'] = max(p['max_y'], line['max_y'])
                p['total_h'] += line['h']
                p['line_count'] += 1
                p['avg_h'] = p['total_h'] / p['line_count']
                merged = True
                break
        if not merged:
            paragraphs.append({
                'lines': [line['text']],
                'scores': list(line['scores']),
                'boxes': list(line['boxes']),
                'min_x': line['min_x'],
                'max_x': line['max_x'],
                'min_y': line['min_y'],
                'max_y': line['max_y'],
                'total_h': line['h'],
                'avg_h': line['h'],
                'line_count': 1
            })

    # 문단 블록 간 추가 수렴 통합 (중앙 정렬 자막 및 다중 줄 단락 완전 통합)
    changed = True
    while changed:
        changed = False
        for i in range(len(paragraphs)):
            for j in range(i + 1, len(paragraphs)):
                p1 = paragraphs[i]
                p2 = paragraphs[j]
                line_h = min(p1['avg_h'], p2['avg_h'])
                v_gap = p2['min_y'] - p1['max_y']
                x_overlap = max(0, min(p1['max_x'], p2['max_x']) - max(p1['min_x'], p2['min_x']))
                min_w = min(p1['max_x'] - p1['min_x'], p2['max_x'] - p2['min_x'])
                overlap_ratio = x_overlap / max(min_w, 1)
                cx_diff = abs((p1['min_x'] + p1['max_x'])/2.0 - (p2['min_x'] + p2['max_x'])/2.0)
                max_w = max(p1['max_x'] - p1['min_x'], p2['max_x'] - p2['min_x'])

                if -0.3 * line_h <= v_gap <= line_h * 1.5 and (overlap_ratio >= 0.15 or cx_diff <= max_w * 0.4 or abs(p1['min_x'] - p2['min_x']) <= line_h * 3.0):
                    p1['lines'].extend(p2['lines'])
                    p1['scores'].extend(p2['scores'])
                    p1['boxes'].extend(p2['boxes'])
                    p1['min_x'] = min(p1['min_x'], p2['min_x'])
                    p1['max_x'] = max(p1['max_x'], p2['max_x'])
                    p1['max_y'] = max(p1['max_y'], p2['max_y'])
                    p1['total_h'] += p2['total_h']
                    p1['line_count'] += p2['line_count']
                    p1['avg_h'] = p1['total_h'] / p1['line_count']
                    paragraphs.pop(j)
                    changed = True
                    break
            if changed:
                break

    return paragraphs


class GlobalHotkeySignals(QObject):
    hotkey_pressed = pyqtSignal()
    registration_status = pyqtSignal(bool, str)


class GlobalHotkeyWorker(threading.Thread):
    """
    Win32 RegisterHotKey 기반 전역 단축키 수신기 (순수 Python 데몬 스레드).
    QThread가 아니므로 Qt 종료 시 C++ 소멸자(QThread::~QThread) 크래시가 원천 차단됩니다.
    """
    def __init__(self, hotkey_str="F4", vk_code=None, modifiers=None, parent=None):
        super().__init__(daemon=True, name="GlobalHotkeyWorker")
        self.signals = GlobalHotkeySignals()
        self.hotkey_pressed = self.signals.hotkey_pressed
        self.registration_status = self.signals.registration_status

        if vk_code is not None:
            self.vk_code = vk_code
            self.modifiers = modifiers or 0
            self.hotkey_str = hotkey_str or "Custom"
        else:
            self.hotkey_str = normalize_hotkey_string(hotkey_str or "F4")
            self.vk_code, self.modifiers = parse_hotkey_string(self.hotkey_str)

        self.is_running = True
        self.registered = False
        self.is_enabled = True

    def isRunning(self):
        return self.is_alive()

    def run(self):
        user32 = ctypes.windll.user32
        ret = user32.RegisterHotKey(None, HOTKEY_ID, self.modifiers | 0x4000, self.vk_code)
        if not ret:
            ret = user32.RegisterHotKey(None, HOTKEY_ID, self.modifiers, self.vk_code)

        if ret:
            self.registered = True
            msg = tr("inplace_hotkey_registered", key=self.hotkey_str)
            print(f"[InPlaceHotkey] {msg} (VK: 0x{self.vk_code:X}, Mod: 0x{self.modifiers:X})")
            self.registration_status.emit(True, msg)
        else:
            msg = tr("inplace_hotkey_failed", key=self.hotkey_str)
            print(f"[InPlaceHotkey] {msg}")
            self.registration_status.emit(False, msg)

        msg_obj = wintypes.MSG()
        user32.MsgWaitForMultipleObjects.argtypes = (
            wintypes.DWORD, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, wintypes.DWORD
        )
        user32.MsgWaitForMultipleObjects.restype = wintypes.DWORD
        while self.is_running:
            # PeekMessage를 20ms마다 돌리면 스레드가 계속 깨어 있다.
            # 메시지가 올 때까지 최대 250ms 대기하고, 단축키는 도착 즉시 처리한다.
            waited = user32.MsgWaitForMultipleObjects(0, None, False, 250, QS_ALLINPUT)
            if waited == 0xFFFFFFFF:
                time.sleep(0.25)
                continue
            while self.is_running and user32.PeekMessageW(ctypes.byref(msg_obj), None, 0, 0, PM_REMOVE):
                if msg_obj.message == WM_HOTKEY and msg_obj.wParam == HOTKEY_ID:
                    if getattr(self, 'is_enabled', True):
                        self.hotkey_pressed.emit()

        if self.registered:
            try:
                user32.UnregisterHotKey(None, HOTKEY_ID)
            except Exception:
                pass
            self.registered = False
            print(f"[InPlaceHotkey] 단축키 '{self.hotkey_str}' 등록 해제됨.")

    def set_enabled(self, enabled: bool):
        self.is_enabled = bool(enabled)

    def stop(self):
        self.is_running = False
        if self.is_alive() and self is not threading.current_thread():
            self.join(timeout=0.5)

    def wait(self, timeout_ms=None):
        if self.is_alive() and self is not threading.current_thread():
            self.join(timeout=timeout_ms / 1000.0 if timeout_ms else None)

    def terminate(self):
        self.is_running = False

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass



class GameTextBadge(QWidget):
    """
    게임 자막/UI 스타일에 최적화된 한국어 텍스트 패치 위젯:
    - 원본 영어 텍스트 완벽 마스킹 (반투명 다크 백드롭)
    - 폰트 전경색 (골드/실버/화이트 추출 색상 매칭)
    - 글자 크기에 최적화된 2.0~2.8px 검은색 스트로크(외곽선 라인)로 번짐 없는 또렷한 가독성 확보
    - 중앙 정렬 및 원본 문단 너비 자동 줄바꿈
    """
    def __init__(self, korean_text: str, english_text: str, score: float,
                 font_color: str = "#FFFFFF", font_size: int = 12,
                 is_bold: bool = True, align=Qt.AlignmentFlag.AlignCenter,
                 clean_text_mode: bool = False, parent=None):
        super().__init__(parent)
        self.korean_text = korean_text
        self.english_text = english_text
        self.score = score
        self.font_color = QColor(font_color)
        self.stroke_color = QColor(0, 0, 0, 255)
        self.font_size = font_size
        self.stroke_width = max(1.8, min(self.font_size * 0.18, 2.8))
        self.is_bold = is_bold
        self.align = align
        self.clean_text_mode = clean_text_mode

        self.font = QFont("Malgun Gothic", self.font_size)
        self.font.setBold(self.is_bold)
        self.font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.4)

        self.setToolTip(f"{tr('inplace_original')}:\n{self.english_text}\n\n({tr('inplace_ocr_confidence')}: {int(self.score * 100)}%)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_clean_mode(self, enabled: bool):
        self.clean_text_mode = enabled
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect_f = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        # 1. 배경 마스킹 (클린 텍스트 모드가 아닐 때 원문 영문 글씨 차단)
        if not self.clean_text_mode:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(12, 16, 24, 235))
            painter.drawRoundedRect(rect_f, 4, 4)

            # 2. 은은한 테두리 (폰트 색상과 톤 매칭)
            border_col = QColor(self.font_color)
            border_col.setAlpha(70)
            painter.setPen(QPen(border_col, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect_f, 4, 4)

        # 3. 문단 너비에 맞춘 지능형 줄바꿈 계산
        fm = QFontMetrics(self.font)
        max_w = max(self.width() - 12, 40)
        words = self.korean_text.split()
        lines = []
        curr = []

        for w in words:
            cand = " ".join(curr + [w])
            if fm.horizontalAdvance(cand) > max_w and curr:
                lines.append(" ".join(curr))
                curr = [w]
            else:
                curr.append(w)
        if curr:
            lines.append(" ".join(curr))

        line_h = fm.height()
        total_text_h = len(lines) * line_h
        start_y = max((self.height() - total_text_h) / 2 + fm.ascent(), float(fm.ascent()))

        # 4. 검은색 스트로크(외곽선) + 전경 폰트 채우기 렌더링
        stroke_pen = QPen(self.stroke_color, self.stroke_width)
        stroke_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        stroke_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        fill_brush = QBrush(self.font_color)

        for i, line in enumerate(lines):
            line_w = fm.horizontalAdvance(line)
            if self.align == Qt.AlignmentFlag.AlignCenter:
                x = (self.width() - line_w) / 2
            else:
                x = 6.0
            y = start_y + i * line_h

            path = QPainterPath()
            path.addText(QPointF(x, y), self.font, line)

            painter.strokePath(path, stroke_pen)
            painter.fillPath(path, fill_brush)

class InPlaceOverlayWindow(QWidget):
    """
    F4 입력 시 순간 화면을 정지한 듯 번역 결과를 제자리에 띄우는 전체화면 투명 오버레이.
    - WDA_EXCLUDEFROMCAPTURE 적용으로 화면 캡처 시 오버레이 자기 복제 원천 차단
    - 유휴 3.5초 후 상단 바 자동 페이드아웃 및 마우스 움직임 시 즉시 복구
    - 클린 텍스트 모드(배경 박스 없이 외곽선 스트로크 텍스트만 출력) 지원
    """
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.font_offset = self.config.get("inplace_font_offset", 0)
        self.clean_text_mode = self.config.get("inplace_clean_text_mode", False)

        self.current_items = []
        self.current_screen_geo = None
        self.current_engine_name = "Google"

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setMouseTracking(True)

        self.badges = []
        self._init_ui()

        # 유휴 시간 감지 타이머 (3.5초 후 헤더 바 자동 숨김)
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(3500)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self._on_idle_timeout)

    def _clean_mode_btn_text(self) -> str:
        return ("✨ " + tr("inplace_text_only")) if not self.clean_text_mode else ("🔲 " + tr("inplace_with_bg"))

    def _init_ui(self):
        self.banner_widget = QWidget(self)
        self.banner_widget.setObjectName("inplace_banner")
        banner_layout = QHBoxLayout(self.banner_widget)
        banner_layout.setContentsMargins(12, 4, 12, 4)
        banner_layout.setSpacing(6)

        # 1. 아이콘
        self.lbl_icon = QLabel("📸", self.banner_widget)
        self.lbl_icon.setStyleSheet("font-size: 14px; background: transparent; border: none; padding: 0 2px;")
        self.lbl_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        banner_layout.addWidget(self.lbl_icon)

        # 2. 텍스트만 토글 버튼
        self.btn_clean_mode = QPushButton(self._clean_mode_btn_text(), self.banner_widget)
        self.btn_clean_mode.setToolTip(tr("inplace_clean_mode_tooltip"))
        self.btn_clean_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clean_mode.setFixedHeight(24)
        self.btn_clean_mode.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 150, 136, 0.85);
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 11.5px;
                font-weight: bold;
                padding: 0 8px;
            }
            QPushButton:hover {
                background-color: #26A69A;
            }
        """)
        self.btn_clean_mode.clicked.connect(self.toggle_clean_mode)
        banner_layout.addWidget(self.btn_clean_mode)

        # 3. 글자크기 표시 라벨
        self.lbl_font_size = QLabel(self.banner_widget)
        self.lbl_font_size.setStyleSheet("color: #ECEFF1; font-size: 11.5px; font-weight: 600; background: transparent; border: none; padding-left: 4px;")
        banner_layout.addWidget(self.lbl_font_size)
        self.banner_label = self.lbl_font_size

        # 4. 글자크기 조절 아이콘들 (A-, A+): 34x24px 충분한 크기로 깨짐 방지 및 border 제거
        btn_font_style = """
            QPushButton {
                background-color: rgba(45, 55, 72, 0.90);
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 0px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #4A5568;
                color: #64FFDA;
            }
        """
        self.btn_font_dec = QPushButton("A-", self.banner_widget)
        self.btn_font_dec.setToolTip(tr("inplace_font_dec_tooltip"))
        self.btn_font_dec.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_font_dec.setFixedSize(34, 24)
        self.btn_font_dec.setStyleSheet(btn_font_style)
        self.btn_font_dec.clicked.connect(lambda: self.change_font_size(-1))
        banner_layout.addWidget(self.btn_font_dec)

        self.btn_font_inc = QPushButton("A+", self.banner_widget)
        self.btn_font_inc.setToolTip(tr("inplace_font_inc_tooltip"))
        self.btn_font_inc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_font_inc.setFixedSize(34, 24)
        self.btn_font_inc.setStyleSheet(btn_font_style)
        self.btn_font_inc.clicked.connect(lambda: self.change_font_size(+1))
        banner_layout.addWidget(self.btn_font_inc)

        # 5. 닫기 아이콘 버튼: x아이콘 버튼으로 클릭 시 즉시 닫기
        self.btn_close = QPushButton("✕", self.banner_widget)
        self.btn_close.setToolTip(tr("inplace_close_hint"))
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setFixedSize(26, 24)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #94A3B8;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                padding: 0px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.85);
                color: #FFFFFF;
            }
        """)
        self.btn_close.clicked.connect(self.hide)
        banner_layout.addWidget(self.btn_close)
        self.lbl_close_hint = self.btn_close  # 하위 호환성 유지

        # 컨트롤 패널 박스 아웃라인 제거: 깔끔한 라운드 플로팅 바
        self.banner_widget.setStyleSheet("""
            QWidget#inplace_banner {
                background-color: rgba(15, 20, 28, 0.92);
                border: none;
                border-radius: 17px;
            }
        """)

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_capture_exclusion()
        self._apply_ui_language()
        self._restart_idle_timer()

    def _apply_capture_exclusion(self):
        """인플레이스 오버레이 창이 화면 캡처에 찍히지 않도록 윈도우 캡처 배제 속성 적용"""
        try:
            hwnd = int(self.winId())
            if hwnd:
                WDA_EXCLUDEFROMCAPTURE = 0x00000011
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        except Exception:
            pass

    def _restart_idle_timer(self):
        self.banner_widget.show()
        self.idle_timer.start(3500)

    def _on_idle_timeout(self):
        self.banner_widget.hide()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._restart_idle_timer()

    def mouseMoveEvent(self, event):
        self._restart_idle_timer()
        super().mouseMoveEvent(event)

    def toggle_clean_mode(self):
        self.clean_text_mode = not self.clean_text_mode
        self.config["inplace_clean_text_mode"] = self.clean_text_mode
        self.btn_clean_mode.setText(self._clean_mode_btn_text())
        for b in self.badges:
            b.set_clean_mode(self.clean_text_mode)
        self.update()
        self._restart_idle_timer()

    def change_font_size(self, delta: int):
        self.font_offset = max(-4, min(self.font_offset + delta, 8))
        self.config["inplace_font_offset"] = self.font_offset
        self._update_banner_text()
        self._render_badges()
        self._restart_idle_timer()

    def _update_banner_text(self):
        font_px = max(8, min(12 + self.font_offset, 24))
        self.lbl_font_size.setText(f"{tr('inplace_font_size')}: {font_px}px")
        self.btn_close.setToolTip(tr("inplace_close_hint"))
        if hasattr(self, 'lbl_close_hint') and self.lbl_close_hint is not self.btn_close:
            self.lbl_close_hint.setText(tr("inplace_close_hint"))
        self.btn_clean_mode.setText(self._clean_mode_btn_text())
        self.btn_clean_mode.setToolTip(tr("inplace_clean_mode_tooltip"))
        self.btn_font_dec.setToolTip(tr("inplace_font_dec_tooltip"))
        self.btn_font_inc.setToolTip(tr("inplace_font_inc_tooltip"))
        cur_hk = self.config.get("inplace_hotkey", "F4")
        self.lbl_icon.setToolTip(tr("inplace_icon_tooltip", key=cur_hk))

        self.banner_widget.adjustSize()
        if self.current_screen_geo:
            bw = self.banner_widget.width() + 10
            self.banner_widget.setGeometry(
                (self.current_screen_geo.width() - bw) // 2, 20, bw, 36
            )

    def _apply_ui_language(self):
        self._update_banner_text()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.restore()
        if not self.clean_text_mode:
            painter.fillRect(self.rect(), QColor(10, 14, 20, 80))

    def keyPressEvent(self, event):
        self._restart_idle_timer()
        key = event.key()
        # Esc 또는 등록된 핫키(F4, F9 등)를 누르면 오버레이 닫기
        is_close_key = (key == Qt.Key.Key_Escape)
        if not is_close_key:
            hotkey_str = self.config.get("inplace_hotkey", "F4")
            target_vk, _ = parse_hotkey_string(hotkey_str)
            key_name = QT_KEY_TO_NAME.get(key)
            if key_name and VK_MAP.get(key_name.upper()) == target_vk:
                is_close_key = True
            elif key == Qt.Key.Key_F4:
                is_close_key = True

        if is_close_key:
            self.hide()
        elif key == Qt.Key.Key_T:
            self.toggle_clean_mode()
        elif key in (Qt.Key.Key_Minus, Qt.Key.Key_BracketLeft):
            self.change_font_size(-1)
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_BracketRight):
            self.change_font_size(+1)
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        self._restart_idle_timer()
        delta = event.angleDelta().y()
        if delta > 0:
            self.change_font_size(+1)
        elif delta < 0:
            self.change_font_size(-1)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 배너 위가 아니라면 화면 아무 곳이나 클릭 시 닫기
            if not self.banner_widget.geometry().contains(event.position().toPoint()):
                self.hide()
                event.accept()
                return
        super().mousePressEvent(event)

    def set_results(self, items: list, screen_geo: QRect, engine_name: str = "Google"):
        self.current_items = items
        self.current_screen_geo = screen_geo
        self.current_engine_name = engine_name
        self.setGeometry(screen_geo)
        self._update_banner_text()
        self._render_badges()

    def _render_badges(self):
        for b in self.badges:
            b.setParent(None)
            b.deleteLater()
        self.badges.clear()

        if not self.current_screen_geo:
            return

        screen_geo = self.current_screen_geo

        for p_info, en_text, ko_text, color in self.current_items:
            min_x = p_info["min_x"]
            max_x = p_info["max_x"]
            min_y = p_info["min_y"]
            max_y = p_info["max_y"]
            orig_w = max_x - min_x
            orig_h = max_y - min_y
            avg_h = p_info["total_h"] / max(p_info["line_count"], 1)
            score = sum(p_info["scores"]) / max(len(p_info["scores"]), 1)

            center_x = min_x + orig_w / 2.0
            center_y = min_y + orig_h / 2.0

            is_title = (p_info["line_count"] == 1 and (avg_h >= 16 or color.upper() in ("#F6E06B", "#EFD360", "#FFEB55")))
            if is_title:
                base_size = max(13, min(int(avg_h * 0.85), 18))
            else:
                base_size = max(10, min(int(avg_h * 0.75), 14))

            font_size = max(8, min(base_size + self.font_offset, 24))

            temp_font = QFont("Malgun Gothic", font_size)
            temp_font.setBold(True)
            fm = QFontMetrics(temp_font)

            target_w = max(orig_w + 10, 50.0)
            words = ko_text.split()
            lines = []
            curr = []
            for w in words:
                cand = " ".join(curr + [w])
                if fm.horizontalAdvance(cand) > (target_w - 12) and curr:
                    lines.append(" ".join(curr))
                    curr = [w]
                else:
                    curr.append(w)
            if curr:
                lines.append(" ".join(curr))

            max_line_w = max((fm.horizontalAdvance(l) for l in lines), default=target_w)
            badge_w = max(max_line_w + 16, target_w)
            badge_h = max(len(lines) * fm.height() + 8, orig_h + 4)

            pos_x = int(center_x - badge_w / 2.0)
            pos_y = int(center_y - badge_h / 2.0)

            pos_x = max(6, min(pos_x, screen_geo.width() - int(badge_w) - 6))
            pos_y = max(6, min(pos_y, screen_geo.height() - int(badge_h) - 6))

            badge = GameTextBadge(
                korean_text=ko_text,
                english_text=en_text,
                score=score,
                font_color=color,
                font_size=font_size,
                is_bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
                clean_text_mode=self.clean_text_mode,
                parent=self
            )

            badge.setGeometry(pos_x, pos_y, int(badge_w), int(badge_h))
            badge.show()
            self.badges.append(badge)


class SnapshotWorkerSignals(QObject):
    finished_signal = pyqtSignal(list, QRect, str)
    error_signal = pyqtSignal(str)


class SnapshotWorkerThread(threading.Thread):
    """
    DirectML OCR 연산 충돌(Race condition)을 완벽 차단하고,
    백그라운드에서 OCR, 문단 병합, 색상 추출, High-DPI 정규화, 배치 번역을 안전하게 수행하는 순수 Python 데몬 스레드.
    QThread가 아니므로 QThread::~QThread 크래시가 발생하지 않습니다.
    """
    def __init__(self, config, translator, get_ocr_cb, ocr_lock=None, parent=None):
        super().__init__(daemon=True, name="SnapshotWorkerThread")
        self.signals = SnapshotWorkerSignals()
        self.finished_signal = self.signals.finished_signal
        self.error_signal = self.signals.error_signal

        self.config = config
        self.translator = translator
        self.get_ocr_cb = get_ocr_cb
        self.ocr_lock = ocr_lock or threading.Lock()
        self._is_busy = False
        self._is_interrupted = False
        self._queue = queue.Queue()
        self.is_running = True

    def isRunning(self):
        return self._is_busy

    def isInterruptionRequested(self):
        return self._is_interrupted or not self.is_running

    def requestInterruption(self):
        self._is_interrupted = True

    def set_snapshot_data(self, pil_img, np_bgr, screen_geo, scale_x, scale_y):
        self._is_interrupted = False
        self._queue.put((pil_img, np_bgr, screen_geo, scale_x, scale_y))

    def stop(self):
        self.is_running = False
        self.requestInterruption()
        self._queue.put(None)
        if self.is_alive() and self is not threading.current_thread():
            self.join(timeout=0.5)

    def wait(self, timeout_ms=None):
        if self.is_alive() and self is not threading.current_thread():
            self.join(timeout=timeout_ms / 1000.0 if timeout_ms else None)

    def terminate(self):
        self.is_running = False
        self.requestInterruption()

    def run(self):
        while self.is_running:
            try:
                task = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if not self.is_running or task is None:
                break

            self._is_busy = True
            try:
                pil_img, np_bgr, screen_geo, scale_x, scale_y = task
                self._execute_snapshot(pil_img, np_bgr, screen_geo, scale_x, scale_y)
            except Exception as e:
                print(f"[InPlace Worker 오류] {e}")
                self.error_signal.emit(str(e))
            finally:
                self._is_busy = False

    def _execute_snapshot(self, pil_img, np_bgr, screen_geo, scale_x, scale_y):
        try:
            # 1. DirectML OCR 인스턴스 획득
            ocr = self.get_ocr_cb()
            if ocr is None:
                self.error_signal.emit(tr("inplace_err_ocr_engine"))
                return

            if self.config.get("screen_ocr_preprocess", True):
                ocr_input = preprocess_game_image(pil_img)
            else:
                ocr_input = pil_img

            # 2. DirectML 스레드 동시 호출 충돌 방지 락 (Crash 원천 차단)
            t0 = time.time()
            with self.ocr_lock:
                ocr_result, _ = ocr(ocr_input)
            ocr_time = (time.time() - t0) * 1000
            del pil_img, ocr_input

            if not ocr_result:
                print("[InPlace] 감지된 텍스트가 없습니다.")
                self.error_signal.emit(tr("inplace_err_no_text"))
                return

            # 3. 유효 라인 필터링
            src_lang = str(self.config.get("source_lang", "auto")).strip().lower().split("-")[0]
            min_conf = float(self.config.get("screen_ocr_min_confidence", 0.45))
            valid_items = []
            for item in ocr_result:
                box, raw_text, score = item[0], item[1], float(item[2])
                if score < min_conf or not raw_text:
                    continue
                raw_stripped = raw_text.strip()
                if len(raw_stripped) <= 2 and score < 0.60:
                    continue
                cleaned = clean_ocr_text(raw_stripped, source_lang=src_lang)
                if cleaned and is_valid_ocr_text(cleaned, source_lang=src_lang):
                    valid_items.append((box, cleaned, score))

            if not valid_items:
                self.error_signal.emit(tr("inplace_err_no_paragraphs"))
                return

            # 4. 문단(Paragraph) 구조 지능형 병합 (물리 좌표계 기준)
            paragraphs = group_boxes_into_paragraphs(valid_items)
            print(f"[InPlace] DirectML OCR 안전 완료 ({len(valid_items)}개 라인 -> {len(paragraphs)}개 문단, {ocr_time:.1f}ms)")

            # 5. 각 문단별 폰트 색상 추출 후 High-DPI 정규화 변환
            for p in paragraphs:
                p["color"] = sample_text_color(np_bgr, p["min_x"], p["min_y"], p["max_x"], p["max_y"])
                p["min_x"] = p["min_x"] / scale_x
                p["max_x"] = p["max_x"] / scale_x
                p["min_y"] = p["min_y"] / scale_y
                p["max_y"] = p["max_y"] / scale_y
                p["total_h"] = p["total_h"] / scale_y

            del np_bgr

            # 6. 문단별 독립 정밀 번역 (로컬 LLM 환각 및 구분자 유실 원천 방지)
            final_results = []
            used_engine = "번역기"
            for p in paragraphs:
                en_text = " ".join(p["lines"])
                if self.isInterruptionRequested():
                    return
                ko_text, engine = self.translator.translate(en_text)
                if engine:
                    used_engine = engine
                final_results.append((p, en_text, ko_text, p["color"]))

            print(f"[InPlace] 문단별 번역 완료 ({len(paragraphs)}개 문단)! 오버레이 렌더링 준비 ({used_engine})")
            if not self.isInterruptionRequested():
                self.finished_signal.emit(final_results, screen_geo, used_engine)

        except Exception as e:
            print(f"[InPlace Snapshot 실행 오류] {e}")
            self.error_signal.emit(str(e))


def resolve_target_screen(config: dict, app: QApplication, cursor_pos: QPoint, from_button: bool = False):
    """
    화면 번역 탭에서 선택한 모니터를 버튼과 F4의 공통 대상으로 사용한다.
    이전 버전의 고정 모니터 및 ROI 좌표는 선택 정보가 없을 때만 사용한다.
    """
    screens = app.screens()
    if not screens:
        return app.primaryScreen()

    selected_idx = config.get("screen_display_index", -1)
    if isinstance(selected_idx, int) and 0 <= selected_idx < len(screens):
        return screens[selected_idx]

    target_idx = config.get("target_display_index", -1)
    if isinstance(target_idx, int) and 0 <= target_idx < len(screens):
        return screens[target_idx]

    # 스마트 자동: 관심 영역(ROI)이 위치한 모니터 우선
    rois = config.get("screen_rois", [])
    if not rois:
        single = config.get("screen_roi")
        if single:
            rois = [single]

    if rois and len(rois[0]) >= 4:
        rx, ry, rw, rh = rois[0]
        roi_center = QPoint(rx + rw // 2, ry + rh // 2)
        for s in screens:
            if s.geometry().contains(roi_center) or s.geometry().intersects(QRect(rx, ry, rw, rh)):
                return s

    # 3. 버튼 클릭 시: 마우스가 컨트롤 패널(보조 모니터)에 있을 가능성이 높으므로 주 모니터 우선
    if from_button:
        return app.primaryScreen() or screens[0]

    # 4. 단축키(F4) 시: 커서 위치 모니터
    return app.screenAt(cursor_pos) or app.primaryScreen() or screens[0]


class InPlaceTranslatorManager(QObject):
    """
    단축키 수신, GUI 스레드 안전 캡처, 스냅샷 작업 스레드, 오버레이 창을 통합 관리하는 매니저.
    """
    registration_status = pyqtSignal(bool, str)

    def __init__(self, config, translator, get_ocr_cb, ocr_lock=None, get_overlays_to_hide=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.translator = translator
        self.get_ocr_cb = get_ocr_cb
        self.ocr_lock = ocr_lock or threading.Lock()
        self.get_overlays_to_hide = get_overlays_to_hide

        self.overlay_window = InPlaceOverlayWindow(config=self.config)

        self.worker_thread = SnapshotWorkerThread(
            config=self.config,
            translator=self.translator,
            get_ocr_cb=self.get_ocr_cb,
            ocr_lock=self.ocr_lock,
            parent=None
        )
        self.worker_thread.finished_signal.connect(self._on_snapshot_finished)
        self.worker_thread.error_signal.connect(self._on_snapshot_error)
        self.worker_thread.start()

        self.current_hotkey = self.config.get("inplace_hotkey", "F4")
        self.hotkey_worker = None
        self._start_hotkey_worker(self.current_hotkey)

    def _start_hotkey_worker(self, hotkey_str: str):
        """기존 핫키 리스너를 안전하게 해제하고 새 핫키로 백그라운드 스레드 가동"""
        if self.hotkey_worker and self.hotkey_worker.is_alive():
            self.hotkey_worker.stop()
        self.current_hotkey = normalize_hotkey_string(hotkey_str)
        self.hotkey_worker = GlobalHotkeyWorker(hotkey_str=self.current_hotkey, parent=None)
        self.hotkey_worker.hotkey_pressed.connect(self.trigger_snapshot, Qt.ConnectionType.QueuedConnection)
        self.hotkey_worker.registration_status.connect(self.registration_status.emit)
        self.hotkey_worker.start()

    def set_hotkey(self, hotkey_str: str) -> bool:
        """단축키를 실시간으로 변경하고 백그라운드 리스너를 재시작"""
        norm_key = normalize_hotkey_string(hotkey_str)
        self.config["inplace_hotkey"] = norm_key
        self._start_hotkey_worker(norm_key)
        return True

    def get_hotkey(self) -> str:
        return getattr(self, 'current_hotkey', "F4")

    def set_hotkey_enabled(self, enabled: bool):
        """단축키 입력 중 또는 일시 정지 시 전역 핫키 가로채기 방지"""
        if hasattr(self, 'hotkey_worker') and self.hotkey_worker:
            self.hotkey_worker.set_enabled(enabled)

    def _apply_ui_language(self):
        """다국어 언어 변경 시 인플레이스 오버레이 창 UI 갱신"""
        if hasattr(self, 'overlay_window') and self.overlay_window:
            if hasattr(self.overlay_window, '_apply_ui_language'):
                self.overlay_window._apply_ui_language()

    def trigger_snapshot(self, from_button: bool = False):
        """GUI 메인 스레드에서 안전하게 화면을 1회 캡처한 뒤 백그라운드 스레드로 전달"""
        if getattr(self, '_stopping', False):
            return
        try:
            if self.worker_thread.isRunning():
                return

            app = QApplication.instance()
            if app is None:
                return

            cursor_pos = QCursor.pos()
            screen = resolve_target_screen(self.config, app, cursor_pos, from_button=from_button)
            if screen is None:
                return

            screen_geo = screen.geometry()

            # 1. 캡처 직전 대상 화면과 겹치는 오버레이/창들을 투명화하여 깜빡임/흰색 번쩍임 원천 차단
            windows_to_restore_opacity = []
            if self.overlay_window.isVisible():
                self.overlay_window.hide()

            if self.get_overlays_to_hide:
                try:
                    for o in self.get_overlays_to_hide():
                        if o and hasattr(o, 'isVisible') and o.isVisible():
                            # 대상 화면(screen_geo)과 전혀 겹치지 않는 창은 건드리지 않음
                            if hasattr(o, 'geometry') and not o.geometry().intersects(screen_geo):
                                continue
                            if hasattr(o, 'windowOpacity') and hasattr(o, 'setWindowOpacity'):
                                old_op = o.windowOpacity()
                                o.setWindowOpacity(0.0)
                                windows_to_restore_opacity.append((o, old_op))
                            else:
                                o.hide()
                                windows_to_restore_opacity.append((o, None))
                except Exception:
                    pass

            # GUI 스레드에서 깨끗한 순수 게임 화면 캡처
            pm = screen.grabWindow(0)

            # 2. 캡처 직후 원래 투명도 즉각 복원 (창 hide/show 리맵이 없으므로 흰색 번쩍임 0%)
            for o, old_op in windows_to_restore_opacity:
                try:
                    if old_op is not None:
                        o.setWindowOpacity(old_op)
                    else:
                        o.show()
                except Exception:
                    pass

            if pm.isNull():
                print("[InPlace] 화면 캡처 실패!")
                return

            scale_x = pm.width() / max(screen_geo.width(), 1)
            scale_y = pm.height() / max(screen_geo.height(), 1)

            # 4바이트 정렬이 보장되는 Format_RGBA8888 사용으로 High-DPI/해상도별 패딩 불일치 크래시 원천 차단
            qimg = pm.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
            w_img, h_img = qimg.width(), qimg.height()
            ptr = qimg.bits()
            ptr.setsize(qimg.sizeInBytes())
            raw_bytes = bytes(ptr)
            pil_img = Image.frombuffer("RGBA", (w_img, h_img), raw_bytes, "raw", "RGBA", 0, 1).convert("RGB")
            np_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            del pm, qimg

            print(f"\n[InPlace] 전체화면 스냅샷 번역 트리거됨! 캡처 해상도: {pil_img.width}x{pil_img.height}")
            self.worker_thread.set_snapshot_data(pil_img, np_bgr, screen_geo, scale_x, scale_y)
            if not self.worker_thread.is_alive():
                self.worker_thread.start()
        except Exception as e:
            print(f"[InPlace] 캡처 트리거 예외 발생: {e}")
            import traceback
            traceback.print_exc()

    def _on_snapshot_finished(self, results: list, screen_geo: QRect, engine_name: str):
        if getattr(self, '_stopping', False):
            return
        try:
            target_screen = next(
                (screen for screen in QApplication.screens() if screen.geometry() == screen_geo),
                None,
            )
            if target_screen:
                handle = self.overlay_window.windowHandle()
                if handle:
                    handle.setScreen(target_screen)
            self.overlay_window.set_results(results, screen_geo, engine_name)
            self.overlay_window.show()
            # Windows가 처음 표시할 때 창을 주 모니터로 옮기는 경우가 있어 표시 후 다시 맞춘다.
            self.overlay_window.setGeometry(screen_geo)
            self.overlay_window.raise_()
            self.overlay_window.activateWindow()
        except Exception as e:
            print(f"[InPlace] 오버레이 렌더링 예외 발생: {e}")
            import traceback
            traceback.print_exc()

    def _on_snapshot_error(self, err: str):
        print(f"[InPlace] 스냅샷 처리 알림: {err}")

    def stop(self):
        self._stopping = True
        if self.hotkey_worker and self.hotkey_worker.is_alive():
            try:
                self.hotkey_worker.stop()
            except Exception:
                pass
        if self.worker_thread and self.worker_thread.is_alive():
            try:
                self.worker_thread.stop()
            except Exception:
                pass
        try:
            self.overlay_window.close()
        except Exception:
            pass

