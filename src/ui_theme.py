"""
루미트랜스 (LumiTrans) 프리미엄 UI 테마 시스템 및 커스텀 컴포넌트
다크 인디고 / 슬레이트 네이비 테마 팔레트 및 반응형 위젯 모음
"""

from PyQt6.QtCore import Qt, QRectF, QPropertyAnimation, pyqtProperty, QEasingCurve, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QCheckBox, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QSizePolicy, QAbstractButton
)
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont

# --- 테마 컬러 팔레트 상수 ---
COLOR_BG_DARK = "#0B0E17"         # 앱 최하단 메인 배경 (Deep Midnight Indigo)
COLOR_PANEL_BG = "#101626"        # 패널 및 섹션 배경
COLOR_CARD_BG = "#141C30"         # 개별 카드 배경
COLOR_CARD_HOVER = "#18223B"      # 카드 마우스 호버 배경
COLOR_CARD_INNER = "#0D1322"      # 내부 중첩 카드 / 텍스트 프리뷰 배경
COLOR_BORDER = "#1E2A42"          # 기본 테두리 라인
COLOR_BORDER_LIGHT = "#283858"    # 강조 테두리 라인

# 악센트 컬러
COLOR_ACCENT_PURPLE = "#6366F1"   # 메인 브랜드 인디고/퍼플 (#6366F1 ~ #7C3AED)
COLOR_ACCENT_PURPLE_HOVER = "#4F46E5"
COLOR_ACCENT_PURPLE_BG = "rgba(99, 102, 241, 0.18)"

COLOR_ACCENT_CYAN = "#00E5FF"     # 네온 시안 (음성/자막 포인트)
COLOR_ACCENT_MINT = "#10B981"     # 에메랄드/민트 (화면 번역, ON 상태)
COLOR_ACCENT_MINT_HOVER = "#059669"
COLOR_ACCENT_MINT_BG = "rgba(16, 185, 129, 0.15)"

COLOR_ACCENT_PINK = "#EC4899"     # 핫핑크/마젠타 (더빙 오디오 포인트)
COLOR_ACCENT_PINK_HOVER = "#DB2777"
COLOR_ACCENT_PINK_BG = "rgba(236, 72, 153, 0.15)"

# 텍스트 컬러
COLOR_TEXT_PRIMARY = "#F8FAFC"    # 밝은 화이트 텍스트
COLOR_TEXT_SECONDARY = "#94A3B8"  # 중간 톤 그레이-블루 텍스트
COLOR_TEXT_MUTED = "#64748B"      # 비활성 텍스트
COLOR_TEXT_CYAN = "#38BDF8"       # 시안 하이라이트 텍스트


# --- 전역 모던 QSS 스타일시트 ---
GLOBAL_QSS = f"""
QWidget {{
    background-color: transparent;
    color: {COLOR_TEXT_PRIMARY};
    font-family: 'Malgun Gothic', '맑은 고딕', 'Segoe UI', sans-serif;
    font-size: 13px;
}}

/* 레이블 기본: 불필요한 아웃라인 상자 및 테두리 완전 제거 */
QLabel {{
    background-color: transparent;
    border: none;
    outline: none;
}}

/* 통일된 툴팁 스타일: 아이콘/버튼 상태에 영향을 받지 않는 고정 다크 팔레트 */
QToolTip {{
    background-color: #141C2E;
    color: #F8FAFC;
    border: 1px solid #283858;
    border-radius: 5px;
    padding: 5px 9px;
    font-size: 12px;
    font-weight: normal;
    font-family: 'Malgun Gothic', '맑은 고딕', 'Segoe UI', sans-serif;
}}

/* 최상위 윈도우 배경 및 컨트롤 패널 */
ControlPanel, QWidget#ControlPanel, QWidget:window, QMainWindow, #central_widget, QDialog {{
    background-color: {COLOR_BG_DARK};
}}

/* 스크롤 영역 */
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    border: none;
    background-color: {COLOR_BG_DARK};
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background-color: #24324D;
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: #384C74;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    border: none;
    background-color: {COLOR_BG_DARK};
    height: 8px;
    margin: 0px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background-color: #24324D;
    min-width: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: #384C74;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* 콤보박스 */
QComboBox {{
    background-color: #101728;
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 500;
}}
QComboBox:hover {{
    border-color: {COLOR_ACCENT_PURPLE};
    background-color: #141D32;
}}
QComboBox:focus {{
    border-color: {COLOR_ACCENT_CYAN};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {COLOR_TEXT_SECONDARY};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: #101728;
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_LIGHT};
    border-radius: 6px;
    selection-background-color: #24324E;
    selection-color: {COLOR_TEXT_PRIMARY};
    padding: 4px;
    outline: none;
}}

/* 슬라이더 */
QSlider::groove:horizontal {{
    height: 6px;
    background: #1C273E;
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #818CF8);
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #FFFFFF;
    border: 2px solid #818CF8;
    width: 16px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: #E0E7FF;
    border: 2px solid #6366F1;
}}
QSlider::sub-page:horizontal:disabled {{
    background: #25334D;
}}
QSlider::handle:horizontal:disabled {{
    background: #475569;
    border: 2px solid #334155;
}}

/* 텍스트 입력창 */
QLineEdit {{
    background-color: #0E1524;
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
}}
QLineEdit:focus {{
    border-color: {COLOR_ACCENT_PURPLE};
    background-color: #121A2C;
}}

/* 일반 푸시 버튼 */
QPushButton {{
    background-color: #182238;
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: #202D4A;
    border-color: {COLOR_BORDER_LIGHT};
    color: #FFFFFF;
}}
QPushButton:pressed {{
    background-color: #141B2D;
}}
QPushButton:disabled {{
    background-color: #101625;
    color: {COLOR_TEXT_MUTED};
    border-color: #172033;
}}

/* 체크박스 기본 */
QCheckBox {{
    spacing: 8px;
    color: {COLOR_TEXT_PRIMARY};
    font-size: 12px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid {COLOR_BORDER};
    background-color: #101728;
}}
QCheckBox::indicator:hover {{
    border-color: {COLOR_ACCENT_PURPLE};
}}
QCheckBox::indicator:checked {{
    background-color: {COLOR_ACCENT_PURPLE};
    border-color: {COLOR_ACCENT_PURPLE};
    image: none;
}}

/* 그룹박스 기본 */
QGroupBox {{
    background-color: {COLOR_CARD_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding: 16px 12px 12px 12px;
    font-weight: bold;
    font-size: 13px;
    color: {COLOR_TEXT_PRIMARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: 2px;
    padding: 0 6px;
    background-color: {COLOR_CARD_BG};
    color: {COLOR_TEXT_PRIMARY};
    border-radius: 4px;
}}
"""


class ModernToggle(QAbstractButton):
    """
    모던 iOS / 슬릭 디자인 스타일의 부드러운 스위치 토글 위젯
    QCheckBox 대체 가능하며 isChecked(), setChecked(), toggled 시그널 완벽 지원
    """
    def __init__(self, parent=None, active_color=COLOR_ACCENT_MINT, inactive_color="#243048", width=40, height=20):
        super().__init__(parent)
        self.setCheckable(True)
        self._width = width
        self._height = height
        self._active_color = QColor(active_color)
        self._inactive_color = QColor(inactive_color)
        self._thumb_color = QColor("#FFFFFF")
        self._offset = 2.0 if not self.isChecked() else (self._width - self._height + 2.0)
        
        self.setFixedSize(self._width, self._height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked):
        end_val = (self._width - self._height + 2.0) if checked else 2.0
        self._anim.stop()
        self._anim.setEndValue(end_val)
        self._anim.start()

    def get_offset(self):
        return self._offset

    def set_offset(self, val):
        self._offset = val
        self.update()

    offset = pyqtProperty(float, get_offset, set_offset)

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        self._offset = (self._width - self._height + 2.0) if checked else 2.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 트랙 배경 그리기
        bg_col = self._active_color if self.isChecked() else self._inactive_color
        p.setBrush(QBrush(bg_col))
        p.setPen(Qt.PenStyle.NoPen)
        r = self._height / 2.0
        p.drawRoundedRect(0, 0, self._width, self._height, r, r)

        # 썸(원형 손잡이) 그리기
        thumb_dia = self._height - 4.0
        p.setBrush(QBrush(self._thumb_color))
        p.drawEllipse(QRectF(self._offset, 2.0, thumb_dia, thumb_dia))


class SegmentLevelMeter(QWidget):
    """
    오디오 입력 레벨을 표시하는 세그먼트 LED 스타일의 미려한 레벨 미터
    """
    def __init__(self, segments=18, parent=None):
        super().__init__(parent)
        self.segments = segments
        self._level = 0.0  # 0.0 ~ 1.0
        self.setFixedHeight(14)
        self.setMinimumWidth(120)

    def setLevel(self, level: float):
        level = max(0.0, min(1.0, level))
        previous = int(self._level * self.segments)
        self._level = level
        # 같은 LED 칸이면 다시 그리지 않는다. 오디오 콜백은 초당 10회 들어온다.
        if int(level * self.segments) != previous:
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        gap = 3
        seg_w = (w - (self.segments - 1) * gap) / self.segments
        active_count = int(self._level * self.segments)

        for i in range(self.segments):
            x = i * (seg_w + gap)
            is_active = i < active_count

            if is_active:
                ratio = i / float(self.segments)
                if ratio < 0.7:
                    col = QColor(COLOR_ACCENT_CYAN)
                elif ratio < 0.85:
                    col = QColor("#FBBF24")
                else:
                    col = QColor("#EF4444")
            else:
                col = QColor("#192439")

            p.setBrush(QBrush(col))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(x, 1, seg_w, h - 2), 2, 2)


class CardWidget(QFrame):
    """
    컨셉 이미지와 완벽하게 일치하는 라운드 코너(10px),
    은은한 테두리와 깊이감 있는 배경을 가진 카드 컴포넌트
    """
    def __init__(self, parent=None, bg_color=COLOR_CARD_BG, border_color=COLOR_BORDER, border_radius=10):
        super().__init__(parent)
        self.setObjectName("CardWidget")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setStyleSheet(f"""
            QFrame#CardWidget, CardWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: {border_radius}px;
            }}
            QLabel {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
        """)


def apply_dark_theme(app):
    """
    애플리케이션 전역에 퓨전 다크 팔레트 및 프리미엄 다크 스타일시트를 강제 적용
    (Windows 라이트 테마 환경에서도 100% 미려한 다크 테마 보장)
    """
    from PyQt6.QtGui import QPalette
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLOR_BG_DARK))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLOR_PANEL_BG))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLOR_CARD_BG))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(COLOR_CARD_INNER))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLOR_PANEL_BG))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(COLOR_ACCENT_CYAN))
    palette.setColor(QPalette.ColorRole.Link, QColor(COLOR_ACCENT_PURPLE))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLOR_ACCENT_PURPLE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)
    app.setStyleSheet(GLOBAL_QSS)


def set_windows_dark_mode(hwnd):
    """
    Windows 10/11 DWM 창 타이틀바, 테두리 및 기본 창 배경을 네이티브 다크 모드로 강제 설정
    (창 기동 시 Windows 기본 흰색 프레임/배경 번쩍임 원천 차단)
    """
    import sys
    if sys.platform != "win32" or not hwnd:
        return
    try:
        import ctypes
        from ctypes import wintypes
        dwm = ctypes.windll.dwmapi
        # 1. DWM Immersive Dark Mode 적용 (Win11 / Win10 20H1+ = 20, Win10 1809~1909 = 19)
        val = wintypes.BOOL(True)
        if dwm.DwmSetWindowAttribute(int(hwnd), 20, ctypes.byref(val), ctypes.sizeof(val)) != 0:
            dwm.DwmSetWindowAttribute(int(hwnd), 19, ctypes.byref(val), ctypes.sizeof(val))

        # 2. Windows 11 전용 타이틀바 및 테두리 다크 색상 강제 매핑 (COLORREF: 0x00BBGGRR)
        # COLOR_BG_DARK = "#0B0E17" -> R=0x0B, G=0x0E, B=0x17 -> COLORREF = 0x00170E0B
        caption_color = wintypes.DWORD(0x00170E0B)
        dwm.DwmSetWindowAttribute(int(hwnd), 35, ctypes.byref(caption_color), ctypes.sizeof(caption_color))
        # COLOR_TEXT_PRIMARY = "#F8FAFC" -> COLORREF = 0x00FCFAF8
        text_color = wintypes.DWORD(0x00FCFAF8)
        dwm.DwmSetWindowAttribute(int(hwnd), 36, ctypes.byref(text_color), ctypes.sizeof(text_color))
        # COLOR_BORDER = "#1E2A42" -> COLORREF = 0x00422A1E
        border_color = wintypes.DWORD(0x00422A1E)
        dwm.DwmSetWindowAttribute(int(hwnd), 34, ctypes.byref(border_color), ctypes.sizeof(border_color))
    except Exception:
        pass
