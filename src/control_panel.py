import os
import sys
import html
import threading
import datetime
from typing import Optional, Dict, Any, Tuple, List

def _get_asset_path(filename):
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        p = os.path.join(base, "assets", filename)
        if os.path.exists(p):
            return p
        return os.path.join(os.path.dirname(sys.executable), "assets", filename)
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", filename)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF, QByteArray, QSize, QRect, QPoint, QPointF, QEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QSlider, QComboBox, QGroupBox, QProgressBar,
    QMessageBox, QDialog, QProgressDialog, QLineEdit, QFormLayout, QDialogButtonBox,
    QScrollArea, QFrame, QGridLayout, QApplication, QTabWidget, QStackedWidget,
    QStyle, QTextBrowser, QFileDialog, QSizePolicy, QButtonGroup, QRadioButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QStyleOption, QMenu,
    QLayout
)
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QPixmap, QIcon, QPainterPath, QPalette, QFontMetrics

from src.no_wheel_combobox import NoWheelComboBox, NoWheelSlider, NoWheelFilter
from src.subtitle_manager import (
    SubtitleHistoryManager, SubtitleEntry, format_display_time,
    recent_screen_dialogues, clean_html_tags,
)
from src.config import active_builtin_presets, CONTENT_TEMPO_PRESETS, tempo_preset_desc, tempo_scope_caption, tempo_deepgram_notice, uses_local_tempo_vad
from src.i18n import ask, bind, is_cancel_message, refresh_texts, set_ui_language, tell, tr, ui_language, UI_LANGUAGE_NAMES, get_model_desc
from src.product import is_global
from src.ui_theme import (
    GLOBAL_QSS, ModernToggle, SegmentLevelMeter, CardWidget,
    COLOR_BG_DARK, COLOR_PANEL_BG, COLOR_CARD_BG, COLOR_CARD_HOVER, COLOR_CARD_INNER,
    COLOR_BORDER, COLOR_BORDER_LIGHT, COLOR_ACCENT_PURPLE, COLOR_ACCENT_PURPLE_HOVER,
    COLOR_ACCENT_CYAN, COLOR_ACCENT_MINT, COLOR_ACCENT_MINT_HOVER,
    COLOR_ACCENT_PINK, COLOR_ACCENT_PINK_HOVER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    set_windows_dark_mode
)
from src.hotkey_utils import HotkeyCaptureButton, normalize_hotkey_string

SVG_GEAR_ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"/>
  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
</svg>"""

SVG_TRASH_ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="3 6 5 6 21 6"/>
  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
  <line x1="10" y1="11" x2="10" y2="17"/>
  <line x1="14" y1="11" x2="14" y2="17"/>
</svg>"""

SVG_EYE_OPEN = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
  <circle cx="12" cy="12" r="3.2"/>
</svg>"""

SVG_EYE_CLOSED = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/>
  <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/>
  <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/>
  <line x1="2" y1="2" x2="22" y2="22"/>
</svg>"""

def get_eye_icon(visible: bool = False, color: str = None) -> QIcon:
    if color is None:
        color = "#38BDF8" if visible else "#94A3B8"
    svg_str = (SVG_EYE_OPEN if visible else SVG_EYE_CLOSED).format(color=color)
    try:
        from PyQt6.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(svg_str.encode("utf-8"))
        pix = QPixmap(24, 24)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()
        return QIcon(pix)
    except Exception:
        pix = QPixmap(24, 24)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 2)
        p.setPen(pen)
        p.drawEllipse(4, 7, 16, 10)
        p.drawEllipse(9, 9, 6, 6)
        if not visible:
            p.drawLine(3, 3, 21, 21)
        p.end()
        return QIcon(pix)

def _make_status_circle_icon(color_hex: str, size: int = 10) -> QIcon:
    """간결하고 선명한 상태 표시 원형 QIcon 생성 (녹색=사용가능, 빨간색=사용불가)"""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pix)

def _make_status_circle_pixmap(color_hex: str, size: int = 10) -> QPixmap:
    """간결하고 선명한 상태 표시 원형 QPixmap 생성 (녹색=사용가능, 빨간색=사용불가)"""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return pix

def create_status_badge(text: str, badge_type: str = "ready") -> QLabel:
    """원형 상태 도트 아이콘 라벨 생성 (녹색=사용가능, 빨간색=사용불가)"""
    is_usable = badge_type in ("ready", "key_ok")
    color = "#10B981" if is_usable else "#EF4444"
    b = QLabel()
    b.setPixmap(_make_status_circle_pixmap(color, 10))
    b.setFixedSize(16, 16)
    b.setAlignment(Qt.AlignmentFlag.AlignCenter)
    b.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    b.setStyleSheet("background: transparent; border: none; padding: 0px;")
    b.setToolTip(text)
    return b

NAV_TAB_SPECS = [
    ("🎮 음성 번역", 0),
    ("🖥️ 화면 번역", 1),
    ("📊 자막 탐색기", 2),
    ("🪄 자막 설정", 3),
    ("⚙️ 설정", 4),
]
NAV_TAB_PALETTE = [
    {  # 음성 번역
        "idle_bg": "rgba(56, 189, 248, 0.14)",
        "idle_border": "rgba(56, 189, 248, 0.45)",
        "idle_text": "#7DD3FC",
        "hover_bg": "rgba(56, 189, 248, 0.28)",
        "hover_border": "#38BDF8",
        "checked_bg": "#0284C7",
        "checked_border": "#38BDF8",
    },
    {  # 화면 번역
        "idle_bg": "rgba(52, 211, 153, 0.14)",
        "idle_border": "rgba(52, 211, 153, 0.45)",
        "idle_text": "#6EE7B7",
        "hover_bg": "rgba(52, 211, 153, 0.28)",
        "hover_border": "#34D399",
        "checked_bg": "#059669",
        "checked_border": "#34D399",
    },
    {  # 자막 탐색기
        "idle_bg": "rgba(96, 165, 250, 0.14)",
        "idle_border": "rgba(96, 165, 250, 0.45)",
        "idle_text": "#93C5FD",
        "hover_bg": "rgba(96, 165, 250, 0.28)",
        "hover_border": "#60A5FA",
        "checked_bg": "#2563EB",
        "checked_border": "#60A5FA",
    },
    {  # 자막 설정
        "idle_bg": "rgba(167, 139, 250, 0.16)",
        "idle_border": "rgba(167, 139, 250, 0.48)",
        "idle_text": "#C4B5FD",
        "hover_bg": "rgba(167, 139, 250, 0.30)",
        "hover_border": "#A78BFA",
        "checked_bg": "#7C3AED",
        "checked_border": "#A78BFA",
    },
    {  # 설정
        "idle_bg": "rgba(251, 191, 36, 0.14)",
        "idle_border": "rgba(251, 191, 36, 0.48)",
        "idle_text": "#FCD34D",
        "hover_bg": "rgba(251, 191, 36, 0.28)",
        "hover_border": "#FBBF24",
        "checked_bg": "#D97706",
        "checked_border": "#FBBF24",
    },
]
NAV_TAB_HEIGHT = 32
NAV_TAB_SPACING = 4
NAV_TAB_PAD_X = 8
BRAND_TITLE = "루미트랜스"
BRAND_SLOGAN = "세상의 이야기를, 바로 여기서"
CONTROL_PANEL_MIN_HEIGHT = 800


def _header_metric_font(base_font: QFont | None, point_size: float, weight: QFont.Weight) -> QFont:
    font = QFont(base_font) if base_font is not None else QFont()
    if is_global() and ui_language() != "ko":
        font.setFamilies([
            "Segoe UI", "Malgun Gothic", "Yu Gothic UI", "Microsoft YaHei UI",
            "Leelawadee UI", "Nirmala UI", "Segoe UI Historic",
        ])
    else:
        font.setFamily("Malgun Gothic")
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font


def nav_tab_width(text: str, base_font: QFont | None = None) -> int:
    font = _header_metric_font(base_font, 12.5, QFont.Weight.Bold)
    return QFontMetrics(font).horizontalAdvance(text) + NAV_TAB_PAD_X * 2 + 10


def control_panel_min_width(base_font: QFont | None = None) -> int:
    """Brand + tab buttons + header/root margins, with no horizontal scroll."""
    tab_total = 0
    for i, (text, _) in enumerate(NAV_TAB_SPECS):
        if i:
            tab_total += NAV_TAB_SPACING
        tab_total += nav_tab_width(text, base_font)

    title_font = _header_metric_font(base_font, 16, QFont.Weight.ExtraBold)
    slogan_font = _header_metric_font(base_font, 11, QFont.Weight.Normal)
    brand_text = max(
        QFontMetrics(title_font).horizontalAdvance(BRAND_TITLE),
        QFontMetrics(slogan_font).horizontalAdvance(BRAND_SLOGAN),
    )
    brand = 22 + 8 + brand_text
    root_margins = 20
    header_margins = 28
    header_gap = 12
    ui_lang_combo = 120
    return root_margins + header_margins + brand + header_gap + ui_lang_combo + tab_total + 16


def nav_tab_stylesheet(palette: dict) -> str:
    return f"""
        QPushButton {{
            background-color: {palette["idle_bg"]};
            color: {palette["idle_text"]};
            border: 1px solid {palette["idle_border"]};
            border-radius: 6px;
            padding: 0 {NAV_TAB_PAD_X}px;
            font-size: 12.5px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {palette["hover_bg"]};
            color: {COLOR_TEXT_PRIMARY};
            border: 1px solid {palette["hover_border"]};
        }}
        QPushButton:checked {{
            background-color: {palette["checked_bg"]};
            color: #FFFFFF;
            font-weight: bold;
            border: 1px solid {palette["checked_border"]};
        }}
    """


def create_svg_icon(svg_str: str, size: int = 18, color: str = "#94A3B8") -> QIcon:
    try:
        from PyQt6.QtSvg import QSvgRenderer
        svg_colored = svg_str.replace("currentColor", color)
        renderer = QSvgRenderer(QByteArray(svg_colored.strip().encode("utf-8")))
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        renderer.render(p)
        p.end()
        return QIcon(pix)
    except Exception:
        return QIcon()


class ShrinkableScrollArea(QScrollArea):
    """Window can shrink below page content; extra content scrolls instead of squashing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def minimumSizeHint(self):
        return QSize(0, 0)

    def sizeHint(self):
        return QSize(800, 480)


class StableStackedWidget(QStackedWidget):
    """Keep resize constraints stable so switching tabs does not change the window min size."""

    def minimumSizeHint(self):
        return QSize(0, 0)

    def sizeHint(self):
        return QSize(800, 480)


class PresetScrollArea(QScrollArea):
    """프리셋 목록이 늘어나도 전체 창 높이를 밀어 올리지 않고 스크롤되도록 고정 sizeHint 제공"""

    def sizeHint(self):
        return QSize(250, 240)

    def minimumSizeHint(self):
        return QSize(100, 150)




class ApiKeyDialog(QDialog):
    """DeepL, Gemini, Groq 무료 API 키 관리 다이얼로그 (팝업 전용)"""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(tr("api_title"))
        self.setFixedSize(480, 360)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLOR_PANEL_BG};
                color: {COLOR_TEXT_PRIMARY};
            }}
            QLabel {{
                color: {COLOR_TEXT_PRIMARY};
                font-size: 11px;
            }}
            QLineEdit {{
                background-color: {COLOR_CARD_INNER};
                color: #FFFFFF;
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border-color: {COLOR_ACCENT_PURPLE};
            }}
            QPushButton {{
                background-color: #1E293B;
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 7px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #334155;
                color: #FFFFFF;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        info = QLabel(tr("dlg_api_info"))
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {COLOR_ACCENT_MINT}; font-size: 11px;")
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(10)

        def _make_form_label(title: str) -> QLabel:
            lbl = QLabel(f"{title}:")
            lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 11px;")
            return lbl

        self.input_deepl = QLineEdit()
        self.input_deepl.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_deepl.setPlaceholderText("DeepL API Key (Developer / Growth / Pro)")
        self.input_deepl.setText(self.config.get("deepl_api_key", ""))
        form.addRow(_make_form_label("DeepL API Key"), self.input_deepl)

        self.input_gemini = QLineEdit()
        self.input_gemini.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_gemini.setPlaceholderText("Google AI Studio Gemini Key (AIza...)")
        self.input_gemini.setText(self.config.get("gemini_api_key", ""))
        form.addRow(_make_form_label("Gemini Flash Key"), self.input_gemini)

        self.input_groq = QLineEdit()
        self.input_groq.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_groq.setPlaceholderText("Groq Cloud LPU Key (gsk_...)")
        self.input_groq.setText(self.config.get("groq_api_key", ""))
        form.addRow(_make_form_label("Groq LPU Key"), self.input_groq)

        self.input_deepgram = QLineEdit()
        self.input_deepgram.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_deepgram.setPlaceholderText("Deepgram Cloud API Key")
        self.input_deepgram.setText(self.config.get("deepgram_api_key", ""))
        form.addRow(_make_form_label("Deepgram Key"), self.input_deepgram)

        layout.addLayout(form)

        tips = QLabel(
            "• DeepL: <a href='https://www.deepl.com/pro-api' style='color:#38BDF8; text-decoration:none;'>deepl.com/pro-api</a><br>"
            "• Gemini: <a href='https://aistudio.google.com/app/apikey' style='color:#38BDF8; text-decoration:none;'>aistudio.google.com</a><br>"
            "• Groq: <a href='https://console.groq.com/keys' style='color:#38BDF8; text-decoration:none;'>console.groq.com</a><br>"
            "• Deepgram: <a href='https://console.deepgram.com/' style='color:#38BDF8; text-decoration:none;'>console.deepgram.com</a>"
        )
        tips.setTextFormat(Qt.TextFormat.RichText)
        tips.setOpenExternalLinks(True)
        tips.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(tips)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.save_keys)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def save_keys(self):
        self.config["deepl_api_key"] = self.input_deepl.text().strip()
        self.config["gemini_api_key"] = self.input_gemini.text().strip()
        self.config["groq_api_key"] = self.input_groq.text().strip()
        self.config["deepgram_api_key"] = self.input_deepgram.text().strip()
        self.accept()


class SubtitlePreviewWidget(QWidget):
    """
    자막 디자인 및 화면 번역 프리뷰를 렌더링하는 고해상도 캔버스 위젯
    """
    def __init__(self, bg_image_path=None, parent=None):
        super().__init__(parent)
        self.bg_image = None
        if bg_image_path and os.path.exists(bg_image_path):
            self.bg_image = QPixmap(bg_image_path)
        self.font_size = 22
        self.opacity = 0.70
        self.stroke_width = 0
        self.letter_spacing = 0.0
        self.show_original = True
        self.show_translated = True
        self.show_badge = True
        self.clean_box = True
        self.clean_text_mode = False
        self.show_speaker = True
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def update_params(self, font_size, opacity, stroke_width, letter_spacing, show_original, show_badge, clean_box, clean_text_mode=False, show_speaker=True, show_translated=True,
                      screen_font_size=None, screen_opacity=None, screen_stroke_width=None, screen_letter_spacing=None,
                      screen_show_original=None, screen_show_badge=None, screen_clean_box=None, screen_clean_text_mode=None, screen_show_speaker=None, screen_show_translated=None):
        self.font_size = font_size
        self.opacity = opacity
        self.stroke_width = stroke_width
        self.letter_spacing = letter_spacing
        self.show_original = show_original
        self.show_translated = show_translated
        self.show_badge = show_badge
        self.clean_box = clean_box
        self.clean_text_mode = clean_text_mode
        self.show_speaker = show_speaker

        self.screen_font_size = screen_font_size if screen_font_size is not None else font_size
        self.screen_opacity = screen_opacity if screen_opacity is not None else opacity
        self.screen_stroke_width = screen_stroke_width if screen_stroke_width is not None else stroke_width
        self.screen_letter_spacing = screen_letter_spacing if screen_letter_spacing is not None else letter_spacing
        self.screen_show_original = screen_show_original if screen_show_original is not None else show_original
        self.screen_show_translated = screen_show_translated if screen_show_translated is not None else show_translated
        self.screen_show_badge = screen_show_badge if screen_show_badge is not None else show_badge
        self.screen_clean_box = screen_clean_box if screen_clean_box is not None else clean_box
        self.screen_clean_text_mode = screen_clean_text_mode if screen_clean_text_mode is not None else clean_text_mode
        self.screen_show_speaker = screen_show_speaker if screen_show_speaker is not None else show_speaker
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()

        # 1. 배경 이미지 또는 그라디언트 렌더링
        if self.bg_image and not self.bg_image.isNull():
            p.drawPixmap(0, 0, w, h, self.bg_image.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            p.fillRect(0, 0, w, h, QColor(8, 12, 22, 110))
        else:
            p.fillRect(0, 0, w, h, QColor("#0E1626"))

        # 텍스트 전용 모드 상단 상태 안내 배지
        if self.clean_text_mode or getattr(self, "screen_clean_text_mode", False):
            info_font = QFont("Malgun Gothic", 8, QFont.Weight.Bold)
            p.setFont(info_font)
            fm_info = QFontMetrics(info_font)
            info_text = tr("clean_text_preview_badge")
            info_w = fm_info.horizontalAdvance(info_text) + 24
            info_rect = QRectF((w - info_w) / 2, 7, info_w, 19)
            p.setBrush(QBrush(QColor(14, 24, 38, 220)))
            p.setPen(QPen(QColor("#00E5FF"), 0.9))
            p.drawRoundedRect(info_rect, 9, 9)
            p.setPen(QColor("#00E5FF"))
            p.drawText(info_rect, Qt.AlignmentFlag.AlignCenter, info_text)

        audio_orig = "[Speaker 1] We should leave before sunset." if self.show_speaker else "We should leave before sunset."
        audio_trans = tr("sample_line")
        screen_speaker_on = getattr(self, "screen_show_speaker", self.show_speaker)
        screen_orig = "Carter: We should leave before sunset." if screen_speaker_on else "We should leave before sunset."
        screen_trans = tr("sample_line")

        # 2. 음성 자막 박스 렌더링 (상단부)
        self._draw_sample_box(p, cx=w // 2, cy=int(h * 0.32),
                              tag=tr("section_audio"), tag_color="#00E5FF",
                              badge_text=tr("badge_ready"), badge_dot_color="#00E5FF",
                              orig=audio_orig,
                              trans=audio_trans,
                              is_clean_text=self.clean_text_mode,
                              font_size=self.font_size,
                              opacity=self.opacity,
                              stroke_width=self.stroke_width,
                              letter_spacing=self.letter_spacing,
                              show_original=self.show_original,
                              show_badge=self.show_badge,
                              clean_box=self.clean_box,
                              show_translated=getattr(self, 'show_translated', True))

        # 3. 화면 자막 박스 렌더링 (하단부)
        screen_clean_text = getattr(self, "screen_clean_text_mode", self.clean_text_mode)
        self._draw_sample_box(p, cx=w // 2, cy=int(h * 0.74),
                              tag=tr("section_screen"), tag_color="#A78BFA",
                              badge_text=tr("status_watching"), badge_dot_color="#69F0AE",
                              orig=screen_orig,
                              trans=screen_trans,
                              is_clean_text=screen_clean_text,
                              font_size=getattr(self, "screen_font_size", self.font_size),
                              opacity=getattr(self, "screen_opacity", self.opacity),
                              stroke_width=getattr(self, "screen_stroke_width", self.stroke_width),
                              letter_spacing=getattr(self, "screen_letter_spacing", self.letter_spacing),
                              show_original=getattr(self, "screen_show_original", self.show_original),
                              show_badge=getattr(self, "screen_show_badge", self.show_badge),
                              clean_box=getattr(self, "screen_clean_box", self.clean_box),
                              show_translated=getattr(self, "screen_show_translated", getattr(self, 'show_translated', True)))

    def _draw_sample_box(self, p: QPainter, cx: int, cy: int, tag: str, tag_color: str,
                          badge_text: str, badge_dot_color: str,
                          orig: str, trans: str, is_clean_text: bool = False,
                          font_size=None, opacity=None, stroke_width=None, letter_spacing=None,
                          show_original=None, show_badge=None, clean_box=None, show_translated=None):
        f_size = font_size if font_size is not None else self.font_size
        op = opacity if opacity is not None else self.opacity
        st_w = stroke_width if stroke_width is not None else self.stroke_width
        spc = letter_spacing if letter_spacing is not None else self.letter_spacing
        s_orig = show_original if show_original is not None else self.show_original
        s_badge = show_badge if show_badge is not None else self.show_badge
        c_box = clean_box if clean_box is not None else self.clean_box
        s_trans = show_translated if show_translated is not None else getattr(self, 'show_translated', True)

        if not s_orig and not s_trans:
            s_trans = True

        # 1. 폰트 및 텍스트 치수 정밀 측정
        orig_font = QFont("Malgun Gothic", max(10, f_size - 6))
        if spc > 0:
            orig_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spc * 0.5)
        fm_orig = QFontMetrics(orig_font)
        orig_w = fm_orig.horizontalAdvance(orig)
        orig_h = fm_orig.height()

        trans_font = QFont("Malgun Gothic", max(12, f_size - 2), QFont.Weight.Bold)
        if spc > 0:
            trans_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spc)
        fm_trans = QFontMetrics(trans_font)
        trans_w = fm_trans.horizontalAdvance(trans)
        trans_h = fm_trans.height()

        # 자막 텍스트 밀착 박스 치수 (반투명 배경 박스용)
        pad_x_orig = 14
        pad_y_orig = 4
        orig_box_w = min(self.width() - 50, orig_w + pad_x_orig * 2)
        orig_box_h = orig_h + pad_y_orig * 2

        pad_x_trans = 18
        pad_y_trans = 6
        trans_box_w = min(self.width() - 50, trans_w + pad_x_trans * 2)
        trans_box_h = trans_h + pad_y_trans * 2

        content_w = max(orig_box_w if s_orig else 0, trans_box_w if s_trans else 0)
        if content_w == 0:
            content_w = 200

        if not is_clean_text:
            # [일반 모드]: 헤더 바(타이틀+배지) + 창 프레임 배경
            header_h = 24
            content_h = 0
            if s_trans:
                content_h += trans_box_h
            if s_orig:
                content_h += orig_box_h + (6 if s_trans else 0)
            if content_h == 0:
                content_h = trans_box_h
            win_h = header_h + content_h + 14
            win_w = min(self.width() - 30, max(content_w + 32, 300))
            win_rect = QRectF(cx - win_w / 2, cy - win_h / 2, win_w, win_h)

            # 창 프레임 배경 (op > 0.001일 때 채움, c_box와 무관)
            if op > 0.001:
                alpha = int(op * 255)
                p.setBrush(QBrush(QColor(14, 20, 32, alpha)))
                p.setPen(QPen(QColor(255, 255, 255, 20), 1.0))
                p.drawRoundedRect(win_rect, 8, 8)
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(255, 255, 255, 15), 1.0, Qt.PenStyle.DashLine))
                p.drawRoundedRect(win_rect, 8, 8)

            # 헤더 바 (타이틀)
            header_y = win_rect.y() + 4
            title_font = QFont("Malgun Gothic", 8, QFont.Weight.Bold)
            p.setFont(title_font)
            fm_title = QFontMetrics(title_font)
            title_w = fm_title.horizontalAdvance(tag)
            p.setPen(QColor(tag_color))
            p.drawText(QRectF(win_rect.x() + 10, header_y, title_w + 6, 18), Qt.AlignmentFlag.AlignVCenter, tag)

            # 엔진 상태 배지 그리기 (s_badge가 켜져 있을 때만!)
            if s_badge and badge_text:
                badge_x = win_rect.x() + 10 + title_w + 10
                badge_font = QFont("Malgun Gothic", 7, QFont.Weight.Bold)
                p.setFont(badge_font)
                fm_badge = QFontMetrics(badge_font)
                text_w = fm_badge.horizontalAdvance(badge_text)
                badge_w = text_w + 18
                badge_h = 16
                badge_rect = QRectF(badge_x, header_y + 1, badge_w, badge_h)

                # 배지 배경 및 테두리
                p.setBrush(QBrush(QColor(22, 34, 52, 220)))
                p.setPen(QPen(QColor(badge_dot_color), 0.8))
                p.drawRoundedRect(badge_rect, 4, 4)

                # 상태 표시 인디케이터 도트
                dot_r = 2.5
                p.setBrush(QBrush(QColor(badge_dot_color)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(badge_rect.x() + 6, badge_rect.center().y()), dot_r, dot_r)

                # 배지 텍스트
                p.setFont(badge_font)
                p.setPen(QColor("#E2E8F0"))
                p.drawText(QRectF(badge_rect.x() + 12, badge_rect.y(), text_w + 4, badge_h),
                           Qt.AlignmentFlag.AlignVCenter, badge_text)

            body_top = win_rect.y() + header_h + 2
        else:
            # [텍스트 전용 모드]: 창 프레임 및 헤더 바 완전히 숨김!
            total_text_h = 0
            if s_trans:
                total_text_h += trans_box_h
            if s_orig:
                total_text_h += orig_box_h + (4 if s_trans else 0)
            if total_text_h == 0:
                total_text_h = trans_box_h

            tag_font = QFont("Malgun Gothic", 7, QFont.Weight.Bold)
            p.setFont(tag_font)
            fm_tag = QFontMetrics(tag_font)
            tw = fm_tag.horizontalAdvance(tag) + 14
            tag_rect = QRectF(cx - tw / 2, cy - total_text_h / 2 - 16, tw, 14)
            p.setBrush(QBrush(QColor(14, 20, 32, 150)))
            p.setPen(QPen(QColor(tag_color), 0.6))
            p.drawRoundedRect(tag_rect, 7, 7)
            p.setPen(QColor(tag_color))
            p.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, tag)

            body_top = cy - total_text_h / 2 + 2

        # 4. 자막 텍스트 및 반투명 배경 박스(clean_box) 렌더링
        if s_orig and s_trans:
            rect_orig = QRectF(cx - orig_box_w / 2, body_top, orig_box_w, orig_box_h)
            rect_trans = QRectF(cx - trans_box_w / 2, body_top + orig_box_h + 4, trans_box_w, trans_box_h)

            # 반투명 배경 박스 (c_box가 켜져 있을 때만 자막 뒤 밀착 박스 렌더링)
            if c_box:
                box_alpha = 185 if is_clean_text else max(120, int(op * 255) + 35)
                box_brush = QBrush(QColor(8, 12, 20, min(240, box_alpha)))
                p.setBrush(box_brush)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(rect_orig, 5, 5)
                p.drawRoundedRect(rect_trans, 5, 5)

            # 원문 텍스트
            p.setFont(orig_font)
            p.setPen(QColor("#94A3B8"))
            p.drawText(rect_orig, Qt.AlignmentFlag.AlignCenter, orig)

            # 번역문 텍스트
            p.setFont(trans_font)
            if st_w > 0:
                path = QPainterPath()
                tx = rect_trans.x() + (trans_box_w - trans_w) / 2
                ty = rect_trans.y() + (trans_box_h - trans_h) / 2 + fm_trans.ascent()
                path.addText(tx, ty, trans_font, trans)
                p.strokePath(path, QPen(QColor(0, 0, 0, 230), st_w * 1.5))
                p.fillPath(path, QBrush(QColor("#FFFFFF")))
            else:
                p.setPen(QColor("#FFFFFF"))
                p.drawText(rect_trans, Qt.AlignmentFlag.AlignCenter, trans)
        elif s_orig and not s_trans:
            rect_orig = QRectF(cx - orig_box_w / 2, body_top, orig_box_w, orig_box_h)

            if c_box:
                box_alpha = 185 if is_clean_text else max(120, int(op * 255) + 35)
                box_brush = QBrush(QColor(8, 12, 20, min(240, box_alpha)))
                p.setBrush(box_brush)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(rect_orig, 5, 5)

            p.setFont(orig_font)
            p.setPen(QColor("#94A3B8"))
            p.drawText(rect_orig, Qt.AlignmentFlag.AlignCenter, orig)
        else:
            rect_trans = QRectF(cx - trans_box_w / 2, body_top, trans_box_w, trans_box_h)

            # 반투명 배경 박스
            if c_box:
                box_alpha = 185 if is_clean_text else max(120, int(op * 255) + 35)
                box_brush = QBrush(QColor(8, 12, 20, min(240, box_alpha)))
                p.setBrush(box_brush)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(rect_trans, 5, 5)

            # 번역문 텍스트
            p.setFont(trans_font)
            if st_w > 0:
                path = QPainterPath()
                tx = rect_trans.x() + (trans_box_w - trans_w) / 2
                ty = rect_trans.y() + (trans_box_h - trans_h) / 2 + fm_trans.ascent()
                path.addText(tx, ty, trans_font, trans)
                p.strokePath(path, QPen(QColor(0, 0, 0, 230), st_w * 1.5))
                p.fillPath(path, QBrush(QColor("#FFFFFF")))
            else:
                p.setPen(QColor("#FFFFFF"))
                p.drawText(rect_trans, Qt.AlignmentFlag.AlignCenter, trans)


class ReadabilityPreviewWidget(QWidget):
    """
    배경별 가독성(검은색 배경 vs 흰색 배경)을
    실시간 자막 스타일 파라미터와 연동하여 비교 렌더링하는 위젯
    """
    def __init__(self, bg_image_path=None, parent=None):
        super().__init__(parent)
        self.bg_image = None
        if bg_image_path and os.path.exists(bg_image_path):
            self.bg_image = QPixmap(bg_image_path)
        self.font_size = 24
        self.opacity = 0.66
        self.stroke_width = 0
        self.letter_spacing = 0.0
        self.show_original = True
        self.clean_box = True
        self.setFixedHeight(114)

    def update_params(self, font_size, opacity, stroke_width, letter_spacing, show_original, clean_box):
        self.font_size = font_size
        self.opacity = opacity
        self.stroke_width = stroke_width
        self.letter_spacing = letter_spacing
        self.show_original = show_original
        self.clean_box = clean_box
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()
        gap = 12
        box_w = (w - gap) // 2

        # 1. 좌측: 검은색 배경
        rect_dark = QRectF(0, 0, box_w, h)
        p.setPen(QPen(QColor(COLOR_BORDER), 1))
        p.setBrush(QBrush(QColor("#000000")))
        p.drawRoundedRect(rect_dark, 6, 6)

        # 2. 우측: 흰색 배경
        rect_comp = QRectF(box_w + gap, 0, box_w, h)
        p.setPen(QPen(QColor(COLOR_BORDER), 1))
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawRoundedRect(rect_comp, 6, 6)

        # 자막 샘플 렌더링
        self._draw_sub_sample(p, rect_dark)
        self._draw_sub_sample(p, rect_comp)

    def _draw_sub_sample(self, p: QPainter, container: QRectF):
        scale = 0.60
        fsize = max(11, int(self.font_size * scale))
        orig_txt = "We should leave before sunset."
        trans_txt = tr("sample_line")

        orig_font = QFont("Malgun Gothic", max(9, fsize - 4))
        if self.letter_spacing > 0:
            orig_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.letter_spacing * 0.5)
        fm_orig = QFontMetrics(orig_font)
        orig_w = fm_orig.horizontalAdvance(orig_txt)
        orig_h = fm_orig.height()

        trans_font = QFont("Malgun Gothic", fsize, QFont.Weight.Bold)
        if self.letter_spacing > 0:
            trans_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.letter_spacing)
        fm_trans = QFontMetrics(trans_font)
        trans_w = fm_trans.horizontalAdvance(trans_txt)
        trans_h = fm_trans.height()

        alpha = max(130, int(self.opacity * 255))
        bg_brush = QBrush(QColor(12, 17, 28, alpha))
        box_pen = Qt.PenStyle.NoPen

        cx = container.center().x()
        cy = container.center().y()

        if self.show_original:
            pad_x_orig = 12
            pad_y_orig = 3
            orig_box_w = min(container.width() - 20, orig_w + pad_x_orig * 2)
            orig_box_h = orig_h + pad_y_orig * 2

            pad_x_trans = 16
            pad_y_trans = 4
            trans_box_w = min(container.width() - 20, trans_w + pad_x_trans * 2)
            trans_box_h = trans_h + pad_y_trans * 2

            gap = 5
            total_h = orig_box_h + gap + trans_box_h
            start_y = cy - total_h // 2

            rect_orig = QRectF(cx - orig_box_w / 2, start_y, orig_box_w, orig_box_h)
            rect_trans = QRectF(cx - trans_box_w / 2, start_y + orig_box_h + gap, trans_box_w, trans_box_h)

            if self.clean_box:
                p.setBrush(bg_brush)
                p.setPen(box_pen)
                p.drawRoundedRect(rect_orig, 5, 5)
                p.drawRoundedRect(rect_trans, 5, 5)

            p.setFont(orig_font)
            p.setPen(QColor("#94A3B8"))
            p.drawText(rect_orig, Qt.AlignmentFlag.AlignCenter, orig_txt)

            p.setFont(trans_font)
            if self.stroke_width > 0:
                path = QPainterPath()
                tx = rect_trans.x() + (trans_box_w - trans_w) / 2
                ty = rect_trans.y() + (trans_box_h - trans_h) / 2 + fm_trans.ascent()
                path.addText(tx, ty, trans_font, trans_txt)
                p.strokePath(path, QPen(QColor(0, 0, 0, 230), self.stroke_width * 1.2))
                p.fillPath(path, QBrush(QColor("#FFFFFF")))
            else:
                p.setPen(QColor("#FFFFFF"))
                p.drawText(rect_trans, Qt.AlignmentFlag.AlignCenter, trans_txt)
        else:
            pad_x_trans = 16
            pad_y_trans = 5
            trans_box_w = min(container.width() - 20, trans_w + pad_x_trans * 2)
            trans_box_h = trans_h + pad_y_trans * 2

            rect_trans = QRectF(cx - trans_box_w / 2, cy - trans_box_h / 2, trans_box_w, trans_box_h)

            if self.clean_box:
                p.setBrush(bg_brush)
                p.setPen(box_pen)
                p.drawRoundedRect(rect_trans, 5, 5)

            p.setFont(trans_font)
            if self.stroke_width > 0:
                path = QPainterPath()
                tx = rect_trans.x() + (trans_box_w - trans_w) / 2
                ty = rect_trans.y() + (trans_box_h - trans_h) / 2 + fm_trans.ascent()
                path.addText(tx, ty, trans_font, trans_txt)
                p.strokePath(path, QPen(QColor(0, 0, 0, 230), self.stroke_width * 1.2))
                p.fillPath(path, QBrush(QColor("#FFFFFF")))
            else:
                p.setPen(QColor("#FFFFFF"))
                p.drawText(rect_trans, Qt.AlignmentFlag.AlignCenter, trans_txt)



class MonitorIdentificationOverlay(QWidget):
    """각 모니터에 잠시 표시되는 식별 번호."""

    def __init__(self, screen, number, parent=None):
        super().__init__(parent)
        self.number = number
        self.screen_name = screen.name()
        self.resolution = screen.geometry().size()
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(screen.geometry())
        self.create()
        self.windowHandle().setScreen(screen)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        panel = QRectF((self.width() - 340) / 2, (self.height() - 190) / 2, 340, 190)
        painter.setBrush(QColor(9, 14, 27, 225))
        painter.setPen(QPen(QColor('#38BDF8'), 3))
        painter.drawRoundedRect(panel, 20, 20)
        painter.setPen(QColor('#FFFFFF'))
        painter.setFont(QFont('Malgun Gothic', 62, QFont.Weight.Bold))
        painter.drawText(QRectF(panel.x(), panel.y() + 10, panel.width(), 105),
                         Qt.AlignmentFlag.AlignCenter, str(self.number))
        painter.setFont(QFont('Malgun Gothic', 13, QFont.Weight.Bold))
        painter.drawText(QRectF(panel.x(), panel.y() + 110, panel.width(), 32),
                         Qt.AlignmentFlag.AlignCenter, tr('monitor_num', n=self.number))
        painter.setFont(QFont('Malgun Gothic', 10))
        painter.drawText(QRectF(panel.x(), panel.y() + 145, panel.width(), 24),
                         Qt.AlignmentFlag.AlignCenter,
                         f'{self.screen_name}  {self.resolution.width()} × {self.resolution.height()}')


class ScreenCanvasPreviewWidget(QWidget):
    """
    화면 번역 전용 게임 화면 & 실제 ROI 다중 영역 동적 시각화 프리뷰 캔버스
    """
    def __init__(self, bg_image_path=None, parent=None):
        super().__init__(parent)
        self.bg_image = None
        self.monitor_image = None
        self.monitor_geometry = None
        self.rois = []
        if bg_image_path and os.path.exists(bg_image_path):
            self.bg_image = QPixmap(bg_image_path)
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_rois(self, rois: list):
        self.rois = list(rois) if rois else []
        self.update()

    def set_monitor(self, geometry, image=None):
        self.monitor_geometry = QRect(geometry) if geometry is not None else None
        self.monitor_image = image
        self.update()

    def _monitor_rect(self):
        geometry = self.monitor_geometry
        if geometry is None or geometry.width() <= 0 or geometry.height() <= 0:
            return QRectF(0, 0, self.width(), self.height())
        scale = min(self.width() / geometry.width(), self.height() / geometry.height())
        width = geometry.width() * scale
        height = geometry.height() * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def _roi_preview_rect(self, roi):
        if len(roi) < 4:
            return None
        geometry = self.monitor_geometry or QRect(0, 0, 1920, 1080)
        if geometry.width() <= 0 or geometry.height() <= 0:
            return None
        clipped = QRect(*map(int, roi[:4])).intersected(geometry)
        if clipped.isEmpty():
            return None
        view = self._monitor_rect()
        return QRectF(view.x() + (clipped.x() - geometry.x()) / geometry.width() * view.width(),
                      view.y() + (clipped.y() - geometry.y()) / geometry.height() * view.height(),
                      clipped.width() / geometry.width() * view.width(),
                      clipped.height() / geometry.height() * view.height())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        view = self._monitor_rect()
        w = view.width()
        h = view.height()

        # 선택 모니터 화면을 비율대로 표시한다. 화면을 얻지 못하면 예시 배경을 사용한다.
        p.fillRect(self.rect(), QColor('#090E17'))
        if self.monitor_image and not self.monitor_image.isNull():
            p.drawPixmap(view.toRect(), self.monitor_image, self.monitor_image.rect())
            p.fillRect(view, QColor(8, 12, 22, 35))
        elif self.bg_image and not self.bg_image.isNull():
            p.drawPixmap(view.toRect(), self.bg_image, self.bg_image.rect())
            p.fillRect(view, QColor(8, 12, 22, 60))
        else:
            p.fillRect(view, QColor("#0E1626"))
        p.setPen(QPen(QColor('#38BDF8'), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(view)

        # 2. 선택 모니터와 교차하는 ROI만 실제 좌표에 맞춰 표시한다.
        visible_rois = [(idx, roi, self._roi_preview_rect(roi))
                        for idx, roi in enumerate(self.rois)]
        visible_rois = [(idx, roi, box) for idx, roi, box in visible_rois if box is not None]
        if not visible_rois:
            # 영역 미설정 시 프리뷰 중앙 안내 배너
            guide_box = QRectF(view.x() + w * 0.15, view.y() + h * 0.42, w * 0.7, 44)
            p.setBrush(QBrush(QColor(10, 16, 28, 200)))
            p.setPen(QPen(QColor("#38BDF8"), 1.2, Qt.PenStyle.DashLine))
            p.drawRoundedRect(guide_box, 8, 8)
            p.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
            p.setPen(QColor("#ECEFF1"))
            p.drawText(guide_box, Qt.AlignmentFlag.AlignCenter, tr("no_region_preview"))
            return

        colors = ["#8B5CF6", "#10B981", "#38BDF8", "#F59E0B", "#EC4899"]

        for idx, roi, box_rect in visible_rois:
            rx, ry, rw, rh = roi
            cx, cy = box_rect.x(), box_rect.y()
            hex_col = colors[idx % len(colors)]
            q_col = QColor(hex_col)

            # 반투명 배경 영역
            p.setBrush(QBrush(QColor(q_col.red(), q_col.green(), q_col.blue(), 35)))
            pen = QPen(q_col, 2, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRoundedRect(box_rect, 6, 6)

            # 좌측 상단 ROI 번호 뱃지
            badge_w, badge_h = 24, 20
            bx = cx
            by = max(view.y() + 4, cy - badge_h) if cy >= view.y() + badge_h else cy
            badge_rect = QRectF(bx, by, badge_w, badge_h)
            p.setBrush(QBrush(q_col))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(badge_rect, 4, 4)
            p.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))
            p.setPen(QColor("#FFFFFF"))
            p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, str(idx + 1))

            # ROI 크기 정보 표시 라벨
            p.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
            p.setPen(QColor("#FFFFFF"))
            info_text = f"ROI #{idx + 1} [{rw}×{rh}]"
            p.drawText(QRectF(bx + badge_w + 6, by, 160, badge_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, info_text)


class STTQuickMenu(QMenu):
    """STT 모델/언어 퀵 메뉴: 다국어 모델 클릭 시 창을 닫지 않고 인플레이스 상태 갱신하여 깜빡임 원천 차단"""
    def mouseReleaseEvent(self, event):
        act = self.actionAt(event.pos())
        if act and getattr(act, "_keep_open", False):
            act.trigger()
            return
        super().mouseReleaseEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            act = self.activeAction()
            if act and getattr(act, "_keep_open", False):
                act.trigger()
                return
        super().keyReleaseEvent(event)


class ControlPanel(QWidget):
    audio_level_signal = pyqtSignal(float)
    speaker_updated_signal = pyqtSignal()
    subtitle_entry_signal = pyqtSignal(object)
    tempo_updated_signal = pyqtSignal(str)
    engine_status_signal = pyqtSignal(str, str)
    youtube_status_signal = pyqtSignal(bool, str)
    audio_sources_updated_signal = pyqtSignal(list)

    def __init__(self, config, overlay, audio_thread, stt_thread, save_config_cb, screen_worker=None, screen_overlay=None, inplace_manager=None, roi_border_manager=None, dubbing_engine=None):
        super().__init__()
        self.config = config
        current_ui = self.config.get("ui_lang")
        if not current_ui:
            from src.i18n import detect_system_ui_language
            current_ui = detect_system_ui_language()
            self.config["ui_lang"] = current_ui
        set_ui_language(current_ui)
        self.overlay = overlay
        self.audio_thread = audio_thread
        self.stt_thread = stt_thread
        self.save_config_cb = save_config_cb
        self.screen_worker = screen_worker
        self.screen_overlay = screen_overlay
        self.inplace_manager = inplace_manager
        self.roi_border_manager = roi_border_manager
        if self.roi_border_manager:
            self.roi_border_manager.set_on_rois_changed(self._on_rois_border_adjusted)
        self.dubbing_engine = dubbing_engine

        # 올라마 미설치 환경에서는 무조건 내장(embedded) 백엔드로 정규화
        from src.llm_model_manager import LLMModelManager
        if not LLMModelManager.is_ollama_installed():
            if self.config.get("llm_backend") == "ollama":
                self.config["llm_backend"] = "embedded"
                if self.save_config_cb:
                    self.save_config_cb(self.config)

        # STT 로컬 모델 유효성 검사: 미설치된 모델이 설정되어 있다면 기본 번들로 안전하게 자동 복구
        from src.stt_model_manager import STTModelManager
        cur_stt_provider = self.config.get("stt_provider", "local")
        if cur_stt_provider == "local":
            default_stt = "small" if is_global() else "distil-small.en"
            cur_model = self.config.get("model_size", default_stt)
            if not (STTModelManager.is_model_installed(cur_model) or STTModelManager.is_bundled_model(cur_model)) and cur_model not in ("sensevoice-small", "moonshine-tiny", "parakeet-tdt-0.6b"):
                print(f"[ControlPanel] 미설치 STT 모델('{cur_model}') 감지 -> 기본 번들 모델('{default_stt}')로 자동 복구")
                self.config["model_size"] = default_stt
                if self.save_config_cb:
                    self.save_config_cb(self.config)

        if self.roi_border_manager is None:
            try:
                from src.roi_border_overlay import ROIBorderManager
                self.roi_border_manager = ROIBorderManager(self.config)
                self.roi_border_manager.set_on_rois_changed(self._on_rois_border_adjusted)
            except Exception:
                self.roi_border_manager = None

        # 실시간 자막 기록 & 모니터링 매니저 초기화
        self.subtitle_history = SubtitleHistoryManager()
        self._sub_refresh_timer = QTimer(self)
        self._sub_refresh_timer.setSingleShot(True)
        self._sub_refresh_timer.setInterval(250)
        self._sub_refresh_timer.timeout.connect(self._do_debounced_subtitle_refresh)
        self.subtitle_entry_signal.connect(self._on_new_subtitle_received_gui)
        self.youtube_status_signal.connect(self._on_youtube_manual_status_updated)


        # 실시간 자막/더빙/상태 이벤트 수신 연결
        if self.overlay and hasattr(self.overlay, 'update_subtitle_signal'):
            self.overlay.update_subtitle_signal.connect(self._on_audio_subtitle_received)

        if self.overlay and hasattr(self.overlay, 'update_preview_signal'):
            self.overlay.update_preview_signal.connect(self._on_audio_preview_received)

        if self.overlay and hasattr(self.overlay, 'set_speaker_diarization_enabled'):
            self.overlay.set_speaker_diarization_enabled(self.config.get("speaker_diarization_enabled", False))

        if self.screen_overlay and hasattr(self.screen_overlay, 'set_speaker_diarization_enabled'):
            self.screen_overlay.set_speaker_diarization_enabled(self.config.get("speaker_diarization_enabled", False))

        if self.screen_worker and hasattr(self.screen_worker, 'subtitle_signal'):
            self.screen_worker.subtitle_signal.connect(self._on_screen_subtitle_received)

        if self.dubbing_engine:
            if hasattr(self.dubbing_engine, 'register_playback_callback'):
                self.dubbing_engine.register_playback_callback(self._on_dubbing_playback_received)
            self.dubbing_engine.on_playback_status = self._on_dubbing_playback_received

        self.engine_status_signal.connect(self._do_update_engine_status)
        if self.inplace_manager and hasattr(self.inplace_manager, 'registration_status'):
            self.inplace_manager.registration_status.connect(self._on_hotkey_registration_status)

        # 퀵 프리셋 상태 및 커스텀 프리셋 페이징 변수
        self._active_preset_id = None
        self._custom_preset_page = 0

        # 기본 윈도우 설정 및 다크 테마 속성 강제 (Windows 기본 흰색 번쩍임 방지)
        self.setWindowTitle(tr("window_title"))
        self.setObjectName("ControlPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(COLOR_BG_DARK))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(COLOR_TEXT_PRIMARY))
        self.setPalette(pal)

        # 화면 밖 엉뚱한 위치 방지 및 노트북 최적화 컴팩트 안전 좌표 보정
        geom = self.config.get("control_panel_geometry", [80, 40, 1080, 680])
        if len(geom) == 4:
            screen = QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                # 노트북/작은 화면에서도 상하좌우가 넘치지 않도록 최대 가용 크기 내로 자동 맞춤
                max_w = min(geom[2], max(control_panel_min_width(self.font()), avail.width() - 30))
                # 프리셋 리스트 확장으로 인해 창 높이가 800을 초과하여 비정상 저장된 경우 기본 높이(800)로 자동 복원
                saved_h = geom[3]
                if saved_h > CONTROL_PANEL_MIN_HEIGHT + 20 and not self.config.get("user_custom_window_height", False):
                    saved_h = CONTROL_PANEL_MIN_HEIGHT
                max_h = max(CONTROL_PANEL_MIN_HEIGHT, min(saved_h, max(400, avail.height() - 50)))
                # 저장된 좌표가 화면 밖이거나 하단 작업표시줄을 침범하는 경우 화면 중앙으로 안전 복원
                if (geom[0] < avail.left() - 40 or geom[0] + max_w > avail.right() + 40 or
                    geom[1] < avail.top() - 20 or geom[1] + max_h > avail.bottom()):
                    x = avail.left() + max(0, (avail.width() - max_w) // 2)
                    y = avail.top() + max(0, (avail.height() - max_h) // 2)
                    geom = [x, y, max_w, max_h]
                else:
                    geom = [geom[0], geom[1], max_w, max_h]
            self.setGeometry(geom[0], geom[1], geom[2], geom[3])
        self.setMinimumSize(control_panel_min_width(self.font()), CONTROL_PANEL_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        # 하위 호환성 (테스트 및 레거시 버튼 연동)
        self._is_audio_active = False
        self.btn_toggle = QPushButton()
        self._i18n(self.btn_toggle, "audio_start")
        self.btn_toggle.clicked.connect(self.toggle_translation)
        self.btn_toggle_screen = QPushButton()
        self._i18n(self.btn_toggle_screen, "screen_start")
        self.btn_toggle_screen.clicked.connect(self.toggle_screen_translation)

        # UI 초기화 및 빌드
        self.device_keys = ["cuda", "cpu", "groq"]
        self.tempo_buttons_tab4 = []
        self._init_ui()
        required_width = max(control_panel_min_width(self.font()),
                             getattr(self, '_required_content_width', 0))
        self.setMinimumSize(required_width, CONTROL_PANEL_MIN_HEIGHT)
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            self.move(min(max(self.x(), avail.left()), max(avail.left(), avail.right() - self.width() + 1)),
                      min(max(self.y(), avail.top()), max(avail.top(), avail.bottom() - self.height() + 1)))

        # 시그널 연결
        self.audio_level_signal.connect(self._update_level_meter)
        self.speaker_updated_signal.connect(lambda: self.refresh_speaker_mgmt_ui(force=True))
        identifier = getattr(self.stt_thread, 'speaker_identifier', None)
        if identifier:
            identifier.speaker_updated_callback = self.speaker_updated_signal.emit
        self.tempo_updated_signal.connect(self._on_tempo_status_updated)
        if self.stt_thread is not None:
            self.stt_thread.tempo_callback = self.tempo_updated_signal.emit

        # 화자 목록 폴링 타이머
        self.speaker_poll_timer = QTimer(self)
        self.speaker_poll_timer.setInterval(1000)
        self.speaker_poll_timer.timeout.connect(self._poll_speakers)
        self.speaker_poll_timer.start()
        self._last_rendered_speakers = set()

        # 오디오 입력 소스 실시간 자동 감지 타이머 (15초 주기 비동기 백그라운드 쿼리)
        self.audio_sources_updated_signal.connect(self._on_audio_sources_ready)
        self.audio_source_poll_timer = QTimer(self)
        self.audio_source_poll_timer.setInterval(15000)
        self.audio_source_poll_timer.timeout.connect(self._poll_audio_sources)
        self.audio_source_poll_timer.start()
        self._audio_query_in_progress = False

        # 오디오 덕킹 매니저
        try:
            from src.process_volume import AudioDuckingManager
            cur_cap = self.config.get("audio_capture_device", "default")
            self.ducking_manager = AudioDuckingManager(
                dubbing_engine=self.dubbing_engine,
                config=self.config,
                target_name_or_pid=cur_cap
            )
            self.ducking_manager.start()
        except Exception as e:
            print(f"[ControlPanel] AudioDuckingManager 초기화 실패: {e}")

        # 초기 활성 상태 설정
        init_audio = self.config.get("auto_start_audio", False)
        self.set_audio_active_state(init_audio)

        init_screen = self.config.get("auto_start_screen", False) and self.config.get("screen_translate_enabled", False)
        self.set_screen_active_state(init_screen)
        self._apply_ui_language()
        self._sync_all_pipeline_status()
        self.refresh_speaker_mgmt_ui(force=True)
        self._init_default_demo_data()

    def _init_default_demo_data(self):
        """초기 가이드 자막 및 화자 데모 세팅 (LUMITRANS_DEMO 환경 변수 또는 demo_mode 설정 시)"""
        if os.environ.get("LUMITRANS_DEMO") != "1" and not self.config.get("demo_mode", False):
            return
        if not self.subtitle_history.entries:
            demo_items = [
                ("audio", "회의를 시작하겠습니다.", "Let's get started.", "진행자", "Whisper"),
                ("screen", "다음 안건은 일정 조율입니다.", "The next item is scheduling.", "게스트", "DeepL"),
                ("audio", "자료는 공유 폴더에 올려 두었습니다.", "I've uploaded the files to the shared folder.", "진행자", "Whisper"),
                ("dubbing", "10분 뒤에 다시 모이겠습니다.", "We'll reconvene in ten minutes.", "내레이션", "Edge-TTS"),
                ("screen", "질문 있으시면 채팅으로 남겨 주세요.", "Please leave questions in the chat.", "게스트", "DeepL"),
                ("audio", "감사합니다. 이어서 진행하겠습니다.", "Thank you. Let's continue.", "진행자", "Whisper")
            ]
            import time
            base_t = time.time() - 25
            for idx, (src, tr, orig, spk, eng) in enumerate(demo_items):
                entry = SubtitleEntry(
                    id=idx + 1,
                    timestamp=base_t + idx * 3,
                    start_sec=float(idx * 3),
                    end_sec=float(idx * 3 + 2.5),
                    source=src,
                    trans_text=tr,
                    orig_text=orig,
                    dub_text=tr,
                    speaker=spk,
                    engine=eng,
                    voice="ko-KR-SunHiNeural"
                )
                self.subtitle_history.entries.append(entry)
            self.refresh_subtitle_view()
            self.refresh_speaker_mgmt_ui(force=True)
            self._sync_dubbing_overlay_buttons()
            self._populate_dubbing_voice_combos()

    def _init_ui(self):
        # 전역 스타일시트 적용
        self.setStyleSheet(GLOBAL_QSS)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 6, 10, 6)
        root_layout.setSpacing(6)

        # 1. 상단 글로벌 헤더 (앱 타이틀, 5대 탭 네비게이션 버튼, 윈도우 조작/설정)
        self.header_widget = self._build_header()
        root_layout.addWidget(self.header_widget)

        # 2. 중앙 컨텐츠 영역: QStackedWidget (5대 탭)
        self.tab_stack = StableStackedWidget(self)
        self.tab_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tab_audio = self._build_tab_audio()
        self.tab_screen = self._build_tab_screen()
        self.tab_history = self._build_tab_history()
        self.tab_subtitles = self._build_tab_subtitles()
        self.tab_settings = self._build_tab_settings()

        self.tab_stack.addWidget(self.tab_audio)      # 0: 음성 번역
        self.tab_stack.addWidget(self.tab_screen)     # 1: 화면 번역
        self.tab_stack.addWidget(self.tab_history)    # 2: 자막 탐색기
        self.tab_stack.addWidget(self.tab_subtitles)  # 3: 자막 설정
        self.tab_stack.addWidget(self.tab_settings)   # 4: 설정
        for page in (self.tab_audio, self.tab_screen, self.tab_history, self.tab_subtitles, self.tab_settings):
            page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 하위 호환성 (테스트 및 기존 인터페이스 연동용)
        self.tab_widget = self.tab_stack
        tab_names = ["음성 번역", "화면 번역", "자막 탐색기", "자막 설정", "설정"]
        self.tab_stack.tabText = lambda idx: tab_names[idx] if 0 <= idx < len(tab_names) else ""

        root_layout.addWidget(self.tab_stack, stretch=1)

        # 3. 하단 고정 제어 바 (어느 탭에서나 항상 접근 가능한 3대 엔진 컨트롤 & 상태)
        self.bottom_bar = self._build_bottom_persistent_bar()
        root_layout.addWidget(self.bottom_bar)

        # 마지막으로 활성화되었던 탭(기본 0: 음성 번역) 복원
        last_tab = self.config.get("last_active_tab", 0)
        if not (0 <= last_tab < self.tab_stack.count()):
            last_tab = 0
        self._switch_tab(last_tab)

    def minimumSizeHint(self):
        return QSize(max(control_panel_min_width(self.font()),
                         getattr(self, '_required_content_width', 0)), CONTROL_PANEL_MIN_HEIGHT)

    # ----------------------------------------------------------------------
    # 1. 상단 헤더 빌더
    # ----------------------------------------------------------------------
    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("HeaderFrame")
        header.setFixedHeight(48)
        header.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        header.setStyleSheet(f"""
            QFrame#HeaderFrame {{
                background-color: {COLOR_PANEL_BG};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
            }}
            QLabel {{
                border: none;
                background-color: transparent;
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(14, 4, 14, 4)
        h_layout.setSpacing(12)

        # 좌측: 브랜드 로고 + 이름 + 슬로건
        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(8)

        logo_lbl = QLabel("💎")
        logo_lbl.setStyleSheet(f"font-size: 18px; color: {COLOR_ACCENT_PURPLE};")
        logo_lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(1)
        title_lbl = QLabel()
        self._brand_title = self._i18n(title_lbl, "brand_title")
        title_lbl.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {COLOR_TEXT_PRIMARY}; letter-spacing: 0.5px;")
        title_lbl.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        slogan_lbl = QLabel()
        self._i18n(slogan_lbl, "brand_slogan")
        slogan_lbl.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SECONDARY};")
        slogan_lbl.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        slogan_lbl.setWordWrap(False)
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(slogan_lbl)

        brand_layout.addWidget(logo_lbl)
        brand_layout.addLayout(title_vbox)
        h_layout.addLayout(brand_layout)

        h_layout.addStretch(1)
        # UI 언어 선택 드롭다운 (상단 헤더 바 기존 위치에 상시 노출, 한국어/English 지원)
        self.combo_ui_lang = NoWheelComboBox()
        self.combo_ui_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_ui_lang.setFixedHeight(30)
        self.combo_ui_lang.setMinimumWidth(110)
        self.combo_ui_lang.setToolTip(tr("ui_lang_label"))
        current_ui = str(self.config.get("ui_lang") or ui_language()).strip().lower().split("-")[0]
        from src.i18n import SUPPORTED_UI_LANGUAGES
        for code, label in SUPPORTED_UI_LANGUAGES.items():
            self.combo_ui_lang.addItem(f"🌐 {label}", code)
        ui_index = self.combo_ui_lang.findData(current_ui)
        if ui_index < 0:
            ui_index = self.combo_ui_lang.findData("ko" if current_ui == "ko" else "en")
        self.combo_ui_lang.blockSignals(True)
        self.combo_ui_lang.setCurrentIndex(max(0, ui_index))
        self.combo_ui_lang.blockSignals(False)
        self.combo_ui_lang.currentIndexChanged.connect(self._on_ui_lang_changed)
        h_layout.addWidget(self.combo_ui_lang)

        # 탭 버튼은 아이콘+글자가 잘리지 않는 고정 폭. 창 최소폭이 헤더를 보호한다.
        nav_host = QWidget()
        nav_host.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        nav_layout = QHBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(NAV_TAB_SPACING)

        self.nav_buttons = []
        nav_keys = ("nav_audio", "nav_screen", "nav_history", "nav_subtitles", "nav_settings")
        for (text, idx), key in zip(NAV_TAB_SPECS, nav_keys):
            btn = QPushButton()
            self._i18n(btn, key)
            text = btn.text()
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(nav_tab_width(text, self.font()), NAV_TAB_HEIGHT)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setStyleSheet(nav_tab_stylesheet(NAV_TAB_PALETTE[idx]))
            btn.clicked.connect(lambda _, i=idx: self._switch_tab(i))
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        nav_width = sum(btn.width() for btn in self.nav_buttons) + NAV_TAB_SPACING * (len(self.nav_buttons) - 1)
        nav_host.setFixedSize(nav_width, NAV_TAB_HEIGHT)
        self.nav_host = nav_host
        h_layout.addWidget(nav_host)
        return header

    def _switch_tab(self, index: int):
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.tab_stack.setCurrentIndex(index)
        self.config["last_active_tab"] = index
        if index == 1 and hasattr(self, 'screen_canvas'):
            QTimer.singleShot(0, self._refresh_screen_preview)
        if index == 3 and hasattr(self, 'preview_canvas'):
            self._update_subtitle_preview()

    # ----------------------------------------------------------------------
    # 2. 하단 고정 제어 바 빌더 (모든 탭 공통)
    # ----------------------------------------------------------------------
    def _build_bottom_persistent_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("BottomBarFrame")
        bar.setFixedHeight(84)
        bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bar.setStyleSheet("""
            QFrame#BottomBarFrame {
                background-color: transparent;
                border: none;
            }
            QLabel {
                border: none;
                background-color: transparent;
            }
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 좌측 섹션: [오디오 및 번역 제어] 3대 코어 버튼 유닛 (독립 카드 섹션)
        ctrl_card = CardWidget(bg_color=COLOR_CARD_INNER, border_radius=8)
        ctrl_layout = QHBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(12, 6, 12, 6)
        ctrl_layout.setSpacing(8)

        # 1) 음성 번역 유닛
        u1_layout = QVBoxLayout()
        u1_layout.setSpacing(3)
        lbl_u1 = QLabel()
        self._i18n(lbl_u1, "section_audio")
        lbl_u1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_u1.setStyleSheet("font-weight: bold; font-size: 11.5px; color: #ECEFF1;")
        self.btn_bottom_audio = QPushButton()
        self._i18n(self.btn_bottom_audio, "start_translation")
        self.btn_bottom_audio.setCheckable(True)
        self.btn_bottom_audio.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bottom_audio.setFixedHeight(36)
        self.btn_bottom_audio.setMinimumWidth(82)
        self.btn_bottom_audio.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #4338CA);
                color: #FFFFFF;
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #6366F1;
                border-radius: 6px;
                padding: 4px 10px;
                text-align: center;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #4F46E5);
                border-color: #818CF8;
            }}
        """)
        self.btn_bottom_audio.clicked.connect(self.toggle_translation)
        u1_layout.addWidget(lbl_u1)
        u1_layout.addWidget(self.btn_bottom_audio)
        ctrl_layout.addLayout(u1_layout)

        # 2) 화면 번역 유닛
        u2_layout = QVBoxLayout()
        u2_layout.setSpacing(3)
        lbl_u2 = QLabel()
        self._i18n(lbl_u2, "section_screen")
        lbl_u2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_u2.setStyleSheet("font-weight: bold; font-size: 11.5px; color: #ECEFF1;")
        self.btn_bottom_screen = QPushButton()
        self._i18n(self.btn_bottom_screen, "start_translation")
        self.btn_bottom_screen.setCheckable(True)
        self.btn_bottom_screen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bottom_screen.setFixedHeight(36)
        self.btn_bottom_screen.setMinimumWidth(82)
        self.btn_bottom_screen.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #0369A1);
                color: #FFFFFF;
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #38BDF8;
                border-radius: 6px;
                padding: 4px 10px;
                text-align: center;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0EA5E9, stop:1 #0284C7);
                border-color: #7DD3FC;
            }}
        """)
        self.btn_bottom_screen.clicked.connect(self.toggle_screen_translation)
        u2_layout.addWidget(lbl_u2)
        u2_layout.addWidget(self.btn_bottom_screen)
        ctrl_layout.addLayout(u2_layout)

        # 3) AI 음성 더빙 유닛
        u3_layout = QVBoxLayout()
        u3_layout.setSpacing(3)
        lbl_u3 = QLabel()
        self._i18n(lbl_u3, "section_dub")
        lbl_u3.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_u3.setStyleSheet("font-weight: bold; font-size: 11.5px; color: #ECEFF1;")
        self.btn_bottom_dubbing = QPushButton()
        self._i18n(self.btn_bottom_dubbing, "start_dubbing")
        self.btn_bottom_dubbing.setCheckable(True)
        self.btn_bottom_dubbing.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bottom_dubbing.setFixedHeight(36)
        self.btn_bottom_dubbing.setMinimumWidth(82)
        self.btn_bottom_dubbing.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #DB2777, stop:1 #BE185D);
                color: #FFFFFF;
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #F472B6;
                border-radius: 6px;
                padding: 4px 10px;
                text-align: center;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #EC4899, stop:1 #DB2777);
                border-color: #FB7185;
            }}
        """)
        self.btn_bottom_dubbing.clicked.connect(self.toggle_dubbing)
        u3_layout.addWidget(lbl_u3)
        u3_layout.addWidget(self.btn_bottom_dubbing)
        ctrl_layout.addLayout(u3_layout)

        layout.addWidget(ctrl_card)

        # 우측: 실시간 대화형 퀵 파이프라인 스위처
        status_card = CardWidget(bg_color=COLOR_CARD_INNER, border_radius=8)
        st_layout = QHBoxLayout(status_card)
        st_layout.setContentsMargins(14, 6, 14, 6)
        st_layout.setSpacing(10)

        self.pipe_container = QWidget()
        self.pipe_container.setFixedWidth(633)
        pipe_vbox = QVBoxLayout(self.pipe_container)
        pipe_vbox.setContentsMargins(0, 0, 0, 0)
        pipe_vbox.setSpacing(5)

        # 상단 헤더 행: 타이틀(좌) + [언어 선택 칩 (글로벌)] + 퀵 프리셋 아이콘 스위처(우)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        lbl_pipe_title = QLabel()
        self._i18n(lbl_pipe_title, "pipeline_title")
        lbl_pipe_title.setStyleSheet("color: #ECEFF1; font-size: 12px; font-weight: bold;")
        title_row.addWidget(lbl_pipe_title)

        if is_global():
            # 0-1) 출발 언어 (원문) 칩 - 윗쪽 빈 공간에 컴팩트 분리 배치
            self.chip_src_lang = QPushButton(f"🌐 {tr('source_lang_auto')} ▾")
            self.chip_src_lang.setCursor(Qt.CursorShape.PointingHandCursor)
            self.chip_src_lang.setFixedHeight(24)
            self.chip_src_lang.setFixedWidth(102)
            self.chip_src_lang.setStyleSheet(self._get_compact_chip_style("#38BDF8"))
            self.chip_src_lang.clicked.connect(self._show_pipe_src_lang_menu)

            arr_src_tgt = QLabel("➔")
            arr_src_tgt.setFixedWidth(10)
            arr_src_tgt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            arr_src_tgt.setStyleSheet(f"color: {COLOR_ACCENT_PURPLE}; font-size: 11px; font-weight: bold;")

            # 0-2) 도착 언어 (번역) 칩 - 윗쪽 빈 공간에 컴팩트 분리 배치
            self.chip_tgt_lang = QPushButton("🎯 한국어 ▾")
            self.chip_tgt_lang.setCursor(Qt.CursorShape.PointingHandCursor)
            self.chip_tgt_lang.setFixedHeight(24)
            self.chip_tgt_lang.setFixedWidth(98)
            self.chip_tgt_lang.setStyleSheet(self._get_compact_chip_style("#A78BFA"))
            self.chip_tgt_lang.clicked.connect(self._show_pipe_tgt_lang_menu)

            title_row.addWidget(self.chip_src_lang)
            title_row.addWidget(arr_src_tgt)
            title_row.addWidget(self.chip_tgt_lang)
        else:
            self.chip_src_lang = None
            self.chip_tgt_lang = None

        title_row.addStretch(1)

        self.quick_presets_widget = QWidget()
        self.quick_presets_layout = QHBoxLayout(self.quick_presets_widget)
        self.quick_presets_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_presets_layout.setSpacing(4)
        title_row.addWidget(self.quick_presets_widget)

        pipe_vbox.addLayout(title_row)

        chips_row = QHBoxLayout()
        chips_row.setContentsMargins(0, 0, 0, 0)
        chips_row.setSpacing(5)

        # 1) STT 디바이스 칩 (프리셋 변경 시 폭 흔들림 방지를 위해 고정폭 설정)
        self.chip_stt_dev = QPushButton("🎙 CUDA ▾")
        self.chip_stt_dev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chip_stt_dev.setFixedHeight(36)
        self.chip_stt_dev.setFixedWidth(108)
        self.chip_stt_dev.setStyleSheet(self._get_chip_style("#818CF8"))
        self.chip_stt_dev.clicked.connect(self._show_pipe_stt_dev_menu)
        self.chip_stt = self.chip_stt_dev  # 하위 호환성 별칭

        arr1 = QLabel("➔")
        arr1.setFixedWidth(12)
        arr1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arr1.setStyleSheet(f"color: {COLOR_ACCENT_PURPLE}; font-size: 12px; font-weight: bold;")

        # 2) STT 모델 칩 (프리셋 변경 시 폭 흔들림 방지를 위해 고정폭 설정)
        self.chip_stt_model = QPushButton("🤖 large-v3-turbo ▾")
        self.chip_stt_model.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chip_stt_model.setFixedHeight(36)
        self.chip_stt_model.setFixedWidth(190)
        self.chip_stt_model.setStyleSheet(self._get_chip_style("#A5B4FC"))
        self.chip_stt_model.clicked.connect(self._show_pipe_stt_model_menu)

        arr2 = QLabel("➔")
        arr2.setFixedWidth(12)
        arr2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arr2.setStyleSheet(f"color: {COLOR_ACCENT_PURPLE}; font-size: 12px; font-weight: bold;")

        # 3) 번역 엔진 칩 (프리셋 변경 시 폭 흔들림 방지를 위해 고정폭 설정)
        self.chip_trans = QPushButton("🌐 Google ▾")
        self.chip_trans.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chip_trans.setFixedHeight(36)
        self.chip_trans.setFixedWidth(130)
        self.chip_trans.setStyleSheet(self._get_chip_style(COLOR_ACCENT_CYAN))
        self.chip_trans.clicked.connect(self._show_pipe_trans_menu)

        arr3 = QLabel("➔")
        arr3.setFixedWidth(12)
        arr3.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arr3.setStyleSheet(f"color: {COLOR_ACCENT_PURPLE}; font-size: 12px; font-weight: bold;")

        # 4) 콘텐츠 템포 칩 (프리셋 변경 시 폭 흔들림 방지를 위해 고정폭 설정)
        self.chip_tempo = QPushButton(f"⏱️ {tr('tempo_smart')} ▾")
        self.chip_tempo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chip_tempo.setFixedHeight(36)
        self.chip_tempo.setFixedWidth(127)
        self.chip_tempo.setStyleSheet(self._get_chip_style(COLOR_ACCENT_PINK))
        self.chip_tempo.clicked.connect(self._show_pipe_tempo_menu)

        chips_row.addWidget(self.chip_stt_dev)
        chips_row.addWidget(arr1)
        chips_row.addWidget(self.chip_stt_model)
        chips_row.addWidget(arr2)
        chips_row.addWidget(self.chip_trans)
        chips_row.addWidget(arr3)
        chips_row.addWidget(self.chip_tempo)
        pipe_vbox.addLayout(chips_row)

        st_layout.addWidget(self.pipe_container)
        st_layout.addStretch(1)

        # 우측: 실시간 상태 & 프로그램 로그 (상단: 텍스트 로그, 하단: 상태 배지 바닥 밀착 정렬)
        status_box = QVBoxLayout()
        status_box.setContentsMargins(0, 0, 0, 0)
        status_box.setSpacing(0)

        # 1행 (상단): 실시간 상태 상세 텍스트 로그 (상단 수평 정렬)
        self.lbl_status_detail = QLabel()
        self._i18n(self.lbl_status_detail, "status_idle")
        self.lbl_status_detail.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        self.lbl_status_detail.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_status_detail.setMinimumWidth(220)
        self.lbl_status_detail.setMaximumWidth(270)
        self.lbl_status_detail.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        status_box.addWidget(self.lbl_status_detail)

        status_box.addStretch(1)

        # 2행 (하단): 실시간 상태 배지 (바닥에 완벽 밀착 정렬)
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(0)
        badge_row.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        self.lbl_ready_badge = QLabel()
        self._i18n(self.lbl_ready_badge, "engine_ready")
        self.lbl_ready_badge.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_ACCENT_MINT};
                font-size: 11.5px;
                font-weight: bold;
                background-color: rgba(16, 185, 129, 0.14);
                border: 1px solid rgba(16, 185, 129, 0.35);
                padding: 4px 10px;
                border-radius: 11px;
                margin: 0px;
            }}
        """)
        badge_row.addWidget(self.lbl_ready_badge)
        status_box.addLayout(badge_row)

        st_layout.addLayout(status_box)
        layout.addWidget(status_card, stretch=1)

        self._refresh_quick_presets_ui()

        return bar

    def _get_chip_style(self, color_hex: str, disabled: bool = False) -> str:
        if disabled:
            return f"""
                QPushButton {{
                    background-color: #101625;
                    color: {COLOR_TEXT_MUTED};
                    border: 1px solid {COLOR_BORDER};
                    border-radius: 6px;
                    padding: 4px 4px;
                    font-size: 12px;
                    font-weight: 600;
                    text-align: center;
                }}
            """
        return f"""
            QPushButton {{
                background-color: #141C30;
                color: {color_hex};
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 6px;
                padding: 4px 4px;
                font-size: 12px;
                font-weight: 600;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: #1E294A;
                border-color: {color_hex};
                color: #FFFFFF;
            }}
        """

    def _get_compact_chip_style(self, color_hex: str) -> str:
        return f"""
            QPushButton {{
                background-color: #141C30;
                color: {color_hex};
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 5px;
                padding: 1px 4px;
                font-size: 11px;
                font-weight: 600;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: #1E294A;
                border-color: {color_hex};
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: #0E1524;
            }}
        """

    def _create_styled_menu(self, menu_cls=QMenu) -> QMenu:
        menu = menu_cls(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: #111827;
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
                padding: 6px;
                color: #ECEFF1;
                font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
                font-size: 11px;
            }}
            QMenu::item {{
                padding: 6px 18px 6px 14px;
                border-radius: 4px;
            }}
            QMenu::item:disabled {{
                color: #9CA3AF;
                font-weight: bold;
                background-color: transparent;
            }}
            QMenu::item:selected {{
                background-color: #4F46E5;
                color: #FFFFFF;
                font-weight: bold;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {COLOR_BORDER};
                margin: 4px 6px;
            }}
        """)
        return menu


    def _popup_menu_above(self, menu: QMenu, widget: QWidget):
        menu.adjustSize()
        pos = widget.mapToGlobal(QPoint(0, -menu.sizeHint().height() - 4))
        try:
            menu.exec(pos)
        finally:
            import time
            self._last_menu_closed_widget = widget
            self._last_pipe_menu_closed_time = time.time()

    def _show_pipe_src_lang_menu(self):
        if not getattr(self, "chip_src_lang", None):
            return
        menu = self._create_styled_menu()
        cur_src = self.config.get("source_lang", "auto")

        act_h = menu.addAction(f"🌐 {tr('source_lang_label')}")
        act_h.setEnabled(False)

        # 1. 자동 감지
        auto_label = tr("source_lang_auto")
        prefix = "✓ " if cur_src == "auto" else "   "
        act_auto = menu.addAction(f"{prefix}{auto_label}")
        act_auto.triggered.connect(lambda: self._select_source_lang_from_pipe("auto"))

        menu.addSeparator()

        from src.translator import LANGUAGE_NAMES
        for code in LANGUAGE_NAMES:
            name = UI_LANGUAGE_NAMES.get(code, code)
            prefix = "✓ " if cur_src == code else "   "
            act = menu.addAction(f"{prefix}{name}")
            act.triggered.connect(lambda _, c=code: self._select_source_lang_from_pipe(c))

        self._popup_menu_above(menu, self.chip_src_lang)

    def _show_pipe_tgt_lang_menu(self):
        if not getattr(self, "chip_tgt_lang", None):
            return
        menu = self._create_styled_menu()
        cur_tgt = self.config.get("target_lang", "ko")

        act_h = menu.addAction(f"🎯 {tr('target_lang_label')}")
        act_h.setEnabled(False)

        from src.translator import LANGUAGE_NAMES
        for code in LANGUAGE_NAMES:
            name = UI_LANGUAGE_NAMES.get(code, code)
            prefix = "✓ " if cur_tgt == code else "   "
            act = menu.addAction(f"{prefix}{name}")
            act.triggered.connect(lambda _, c=code: self._select_target_lang_from_pipe(c))

        self._popup_menu_above(menu, self.chip_tgt_lang)

    def _select_source_lang_from_pipe(self, code: str):
        self._apply_source_lang(code)

    def _select_target_lang_from_pipe(self, code: str):
        self._apply_target_lang(code)

    def _show_pipe_stt_dev_menu(self):
        menu = self._create_styled_menu()
        cur_p = self.config.get("stt_provider", "local")
        cur_dev = self.config.get("device", "cuda")
        active_k = cur_p if cur_p in ("groq", "deepgram") else cur_dev

        stt_opts = [
            ("cuda", "NVIDIA CUDA"),
            ("cpu", "CPU"),
            ("groq", "Groq"),
            ("deepgram", "Deepgram"),
        ]
        for k, label in stt_opts:
            prefix = "✓ " if k == active_k else "   "
            txt, btype = self._get_stt_badge_info(k)
            dot = "🟢" if btype in ("ready", "key_ok") else "🔴"
            act = menu.addAction(f"{prefix}{label}\t{dot}")
            act.setToolTip(txt)
            act.triggered.connect(lambda _, key=k: self._on_stt_dev_selected(key))
        self._popup_menu_above(menu, self.chip_stt_dev)

    def _show_pipe_stt_model_menu(self, force: bool = False):
        if not force:
            import time
            if getattr(self, "_last_menu_closed_widget", None) == getattr(self, "chip_stt_model", None):
                if time.time() - getattr(self, "_last_pipe_menu_closed_time", 0) < 0.25:
                    return

        menu = self._create_styled_menu(STTQuickMenu)
        cur_p = self.config.get("stt_provider", "local")

        from src.stt_model_manager import STTModelManager
        model_action_items = []
        lang_action_items = []

        def refresh_menu_state(selected_mid):
            cur_prov = self.config.get("stt_provider", "local")
            is_multi_now = STTModelManager.is_multilingual_model(selected_mid, cur_prov)
            cur_l = self.config.get("stt_language", "en") if is_multi_now else "en"

            for mid, act, usable in model_action_items:
                pref = "✓ " if mid == selected_mid else "   "
                dot = "🟢" if usable else "🔴"
                act.setText(f"{pref}{mid}\t{dot}")

            for lc, l_lbl, act_l in lang_action_items:
                pref = "✓ " if cur_l == lc else "   "
                can = is_multi_now or (lc == "en")
                dot = "🟢" if can else "🔴"
                act_l.setText(f"{pref}{l_lbl}\t{dot}")
                act_l.setEnabled(can)
                if can:
                    act_l.setToolTip(tr("status_active_now") if cur_l == lc else tr("ready_now"))
                else:
                    act_l.setToolTip(tr("status_english_only_warn", mid=selected_mid))

        if cur_p == "deepgram":
            cur_model = self.config.get("deepgram_model", "nova-3")
            from src.stt_model_manager import AVAILABLE_DEEPGRAM_STT_MODELS
            has_key = bool(self.config.get("deepgram_api_key", "").strip())
            dot = "🟢" if has_key else "🔴"
            for m in AVAILABLE_DEEPGRAM_STT_MODELS:
                m_id = m["id"]
                prefix = "✓ " if cur_model == m_id else "   "
                act = menu.addAction(f"{prefix}{m_id}\t{dot}")
                act.setToolTip(tr("status_key_registered") if has_key else tr("need_key"))
                is_multi_m = STTModelManager.is_multilingual_model(m_id, cur_p)
                if has_key and is_multi_m:
                    act._keep_open = True
                act.triggered.connect(lambda _, mid=m_id: self._on_stt_model_quick_selected(mid, refresh_menu_cb=refresh_menu_state))
                model_action_items.append((m_id, act, has_key))
        elif cur_p == "groq":
            cur_model = self.config.get("groq_model", "whisper-large-v3-turbo")
            from src.stt_model_manager import AVAILABLE_GROQ_STT_MODELS
            has_key = bool(self.config.get("groq_api_key", "").strip())
            dot = "🟢" if has_key else "🔴"
            for m in AVAILABLE_GROQ_STT_MODELS:
                m_id = m["id"]
                prefix = "✓ " if cur_model == m_id else "   "
                act = menu.addAction(f"{prefix}{m_id}\t{dot}")
                act.setToolTip(tr("status_key_registered") if has_key else tr("need_key"))
                is_multi_m = STTModelManager.is_multilingual_model(m_id, cur_p)
                if has_key and is_multi_m:
                    act._keep_open = True
                act.triggered.connect(lambda _, mid=m_id: self._on_stt_model_quick_selected(mid, refresh_menu_cb=refresh_menu_state))
                model_action_items.append((m_id, act, has_key))
        else:
            default_stt = "small" if is_global() else "distil-small.en"
            cur_model = self.config.get("model_size", default_stt)
            dev = str(self.config.get("device", "cpu")).lower()
            is_cpu = (dev == "cpu")
            from src.stt_model_manager import AVAILABLE_STT_MODELS

            whisper_models = [m for m in AVAILABLE_STT_MODELS if m.get("category") == "whisper"]
            distil_models = [m for m in AVAILABLE_STT_MODELS if m.get("category") == "distil"]

            act_h1 = menu.addAction(tr("stt_section_official"))
            act_h1.setEnabled(False)
            for m in whisper_models:
                m_id = m["id"]
                prefix = "✓ " if cur_model == m_id else "   "
                installed = STTModelManager.is_model_installed(m_id)
                bundled = STTModelManager.is_bundled_model(m_id)
                is_installed = installed or bundled
                can_select = (not is_cpu) or m.get("cpu_usable", False)
                dot = "🟢" if is_installed else "🔴"
                is_multi_m = STTModelManager.is_multilingual_model(m_id, cur_p)
                act = menu.addAction(f"{prefix}{m_id}\t{dot}")
                if can_select:
                    act.setToolTip(tr("status_ready_immediate") if is_installed else tr("status_uninstalled_dl"))
                    if is_installed and is_multi_m:
                        act._keep_open = True
                    act.triggered.connect(lambda _, mid=m_id: self._on_stt_model_quick_selected(mid, refresh_menu_cb=refresh_menu_state))
                else:
                    act.setToolTip(tr("status_cpu_no_stream"))
                    act.setEnabled(False)
                model_action_items.append((m_id, act, is_installed))

            menu.addSeparator()
            act_h2 = menu.addAction(tr("stt_section_distil"))
            act_h2.setEnabled(False)
            for m in distil_models:
                m_id = m["id"]
                prefix = "✓ " if cur_model == m_id else "   "
                installed = STTModelManager.is_model_installed(m_id)
                bundled = STTModelManager.is_bundled_model(m_id)
                is_installed = installed or bundled
                can_select = (not is_cpu) or m.get("cpu_usable", False)
                dot = "🟢" if is_installed else "🔴"
                is_multi_m = STTModelManager.is_multilingual_model(m_id, cur_p)
                act = menu.addAction(f"{prefix}{m_id}\t{dot}")
                if can_select:
                    act.setToolTip(tr("status_ready_immediate") if is_installed else tr("status_uninstalled_dl"))
                    if is_installed and is_multi_m:
                        act._keep_open = True
                    act.triggered.connect(lambda _, mid=m_id: self._on_stt_model_quick_selected(mid, refresh_menu_cb=refresh_menu_state))
                else:
                    act.setToolTip(tr("status_cpu_no_stream"))
                    act.setEnabled(False)
                model_action_items.append((m_id, act, is_installed))

        # STT 인식 언어 선택 메뉴 (자동 감지 vs 특정 언어 고정)
        menu.addSeparator()
        act_lang_h = menu.addAction(tr("menu_stt_lang"))
        act_lang_h.setEnabled(False)

        is_multi = STTModelManager.is_multilingual_model(cur_model, cur_p)
        cur_lang = self.config.get("stt_language", "en") if is_multi else "en"

        lang_choices = [
            ("auto", tr("lang_auto")),
            ("ja", tr("lang_ja")),
            ("en", tr("lang_en")),
            ("zh", tr("lang_zh")),
            ("ko", tr("lang_ko")),
        ]
        for l_code, l_label in lang_choices:
            prefix = "✓ " if cur_lang == l_code else "   "
            can_select = is_multi or (l_code == "en")
            dot = "🟢" if can_select else "🔴"
            act_l = menu.addAction(f"{prefix}{l_label}\t{dot}")
            if can_select:
                act_l.setToolTip(tr("status_active_now") if cur_lang == l_code else tr("ready_now"))
                act_l.triggered.connect(lambda _, lc=l_code: self._on_stt_language_quick_selected(lc))
            else:
                act_l.setEnabled(False)
                act_l.setToolTip(tr("status_english_only_warn", mid=cur_model))
            lang_action_items.append((l_code, l_label, act_l))

        self._popup_menu_above(menu, self.chip_stt_model)

    def _on_stt_language_quick_selected(self, lang_code: str):
        self._apply_source_lang(lang_code)

    def _on_stt_model_quick_selected(self, model_id: str, prompt_missing: bool = True, refresh_menu_cb=None):
        from src.stt_model_manager import STTModelManager, AVAILABLE_STT_MODELS
        cur_p = self.config.get("stt_provider", "local")

        if cur_p == "deepgram":
            if not bool(self.config.get("deepgram_api_key", "").strip()):
                if prompt_missing:
                    tell(self, "msg_need_key_title", "msg_need_deepgram")
                    self.open_api_key_dialog()
                return
            self.config["deepgram_model"] = model_id
        elif cur_p == "groq":
            if not bool(self.config.get("groq_api_key", "").strip()):
                if prompt_missing:
                    tell(self, "msg_need_key_title", "msg_need_groq")
                    self.open_api_key_dialog()
                return
            self.config["groq_model"] = model_id
        else:
            # 로컬 Whisper 모델: 설치 여부 우선 검사
            is_installed = STTModelManager.is_model_installed(model_id) or STTModelManager.is_bundled_model(model_id)
            if not is_installed:
                if prompt_missing:
                    # 미설치 모델 선택 시: 백그라운드 다운로드가 아닌 모델 관리창으로 유도
                    ret = ask(
                        self,
                        "msg_model_missing_title",
                        "msg_model_missing",
                        name=model_id,
                    )
                    if ret == QMessageBox.StandardButton.Yes:
                        self.open_stt_model_manager(target_model_id=model_id)
                return

            dev = str(self.config.get("device", "cpu")).lower()
            if dev == "cpu" and not STTModelManager.is_cpu_usable(model_id):
                from src.stt_engine import is_cuda_installed
                if is_cuda_installed():
                    self.config["device"] = "cuda"
                    self.config["compute_type"] = "float16"
                    if hasattr(self, 'stt_thread') and self.stt_thread:
                        self.stt_thread.device = "cuda"
                        self.stt_thread.compute_type = "float16"
                else:
                    if not prompt_missing:
                        return
                    ret = ask(self, "msg_cpu_slow_title", "msg_cpu_slow", name=model_id)
                    if ret != QMessageBox.StandardButton.Yes:
                        return
            self.config["model_size"] = model_id

        is_multi = STTModelManager.is_multilingual_model(model_id, cur_p)
        src_lang = self.config.get("source_lang", "auto")
        if is_multi:
            if src_lang and src_lang != "auto":
                self.config["stt_language"] = src_lang
            else:
                self.config["stt_language"] = self.config.get("stt_language", "auto")
        else:
            self.config["stt_language"] = "en"

        if self.stt_thread:
            self.stt_thread.update_config(self.config)
            if hasattr(self.stt_thread, 'change_model'):
                self.stt_thread.change_model(model_id)
        self._populate_models()
        self.save_config_cb(self.config)
        self._sync_all_pipeline_status()

        if refresh_menu_cb:
            refresh_menu_cb(model_id)

    def _show_pipe_trans_menu(self):
        menu = self._create_styled_menu()
        cur_eng = self.config.get("translation_engine", "google")

        cloud_engines = [
            ("deepl", "DeepL"),
            ("google", "Google"),
            ("gemini", "Gemini Flash"),
            ("groq", "Groq Qwen 27B"),
        ]
        local_engines = [
            ("gemma", f"TranslateGemma 4B {tr('engine_multilingual_tag')}"),
            ("exaone", f"EXAONE 3.5 2.4B {tr('engine_bilingual_tag')}"),
            ("exaone7b", f"EXAONE 3.5 7.8B {tr('engine_bilingual_tag')}"),
            ("hymt", f"Hy-MT2 1.8B {tr('engine_multilingual_tag')}"),
        ]

        act_h1 = menu.addAction(tr("online_cloud"))
        act_h1.setEnabled(False)
        for k, label in cloud_engines:
            prefix = "✓ " if cur_eng == k else "   "
            txt, btype = self._get_online_trans_badge_info(k)
            dot = "🟢" if btype in ("ready", "key_ok") else "🔴"
            act = menu.addAction(f"{prefix}{label}\t{dot}")
            act.setToolTip(txt)
            act.triggered.connect(lambda _, key=k: self.set_engine_by_key(key))

        menu.addSeparator()
        act_h2 = menu.addAction(tr("dlg_local_models"))
        act_h2.setEnabled(False)
        for k, label in local_engines:
            matched = (cur_eng == k) or (k == "exaone" and cur_eng in ["exaone", "exaone-3.5-2.4b"]) or (k == "exaone7b" and cur_eng in ["exaone7b", "exaone-3.5-7.8b"]) or (k == "gemma" and "gemma" in str(cur_eng).lower()) or (k == "hymt" and "hymt" in str(cur_eng).lower())
            prefix = "✓ " if matched else "   "
            txt, btype = self._get_local_trans_badge_info(k)
            dot = "🟢" if btype in ("ready", "key_ok") else "🔴"
            act = menu.addAction(f"{prefix}{label}\t{dot}")
            act.setToolTip(txt)
            act.triggered.connect(lambda _, key=k: self.set_engine_by_key(key))

        self._popup_menu_above(menu, self.chip_trans)

    def _show_pipe_tempo_menu(self):
        if not uses_local_tempo_vad(self.config):
            return
        menu = self._create_styled_menu()
        cur_tempo = self.config.get("content_tempo_preset", "smart")

        for k, p in CONTENT_TEMPO_PRESETS.items():
            prefix = "✓ " if cur_tempo == k else "   "
            act = menu.addAction(f"{prefix}{tr(f'tempo_{k}')}")
            act.setToolTip(tr(f"tempo_{k}_desc"))
            act.triggered.connect(lambda _, key=k: self._apply_tempo_preset_key(key, source="pipe"))

        self._popup_menu_above(menu, self.chip_tempo)

    # ----------------------------------------------------------------------
    # 2-1. 실시간 엔진 상태 배지 & 간략 프로그램 로그 업데이트
    # ----------------------------------------------------------------------
    def update_engine_status(self, state: str, detail: str = ""):
        """스레드 안전한 실시간 엔진 상태 및 프로그램 간략 로그 발행"""
        if hasattr(self, 'engine_status_signal'):
            self.engine_status_signal.emit(state, detail)
        else:
            self._do_update_engine_status(state, detail)

    def _do_update_engine_status(self, state: str, detail: str = ""):
        if not hasattr(self, 'lbl_ready_badge') or not hasattr(self, 'lbl_status_detail'):
            return

        styles = {
            "ready": {
                "badge": tr("badge_ready"),
                "color": COLOR_ACCENT_MINT,
                "bg": "rgba(16, 185, 129, 0.14)",
                "border": "rgba(16, 185, 129, 0.35)",
                "default_detail": tr("status_idle"),
            },
            "loading": {
                "badge": tr("badge_loading"),
                "color": "#F59E0B",
                "bg": "rgba(245, 158, 11, 0.16)",
                "border": "rgba(245, 158, 11, 0.4)",
                "default_detail": tr("detail_loading"),
            },
            "translating": {
                "badge": tr("badge_translating"),
                "color": COLOR_ACCENT_CYAN,
                "bg": "rgba(6, 182, 212, 0.16)",
                "border": "rgba(6, 182, 212, 0.4)",
                "default_detail": tr("detail_translating"),
            },
            "recognizing": {
                "badge": tr("badge_recognizing"),
                "color": COLOR_ACCENT_PURPLE,
                "bg": "rgba(129, 140, 248, 0.16)",
                "border": "rgba(129, 140, 248, 0.4)",
                "default_detail": tr("detail_recognizing"),
            },
            "paused": {
                "badge": tr("badge_paused"),
                "color": "#94A3B8",
                "bg": "rgba(148, 163, 184, 0.12)",
                "border": "rgba(148, 163, 184, 0.25)",
                "default_detail": tr("detail_paused"),
            },
            "error": {
                "badge": tr("badge_error"),
                "color": "#EF4444",
                "bg": "rgba(239, 68, 68, 0.16)",
                "border": "rgba(239, 68, 68, 0.4)",
                "default_detail": tr("detail_error"),
            },
        }

        cfg = styles.get(state, styles["ready"])
        self.lbl_ready_badge.setText(cfg["badge"])
        self.lbl_ready_badge.setStyleSheet(f"""
            QLabel {{
                color: {cfg['color']};
                font-size: 11px;
                font-weight: bold;
                background-color: {cfg['bg']};
                border: 1px solid {cfg['border']};
                padding: 3px 9px;
                border-radius: 10px;
                margin: 0px;
            }}
        """)

        full_detail = " ".join(clean_html_tags(html.unescape(str(detail or cfg["default_detail"]))).split())
        available_width = max(180, min(260, self.lbl_status_detail.width() - 8))
        visible_detail = self.lbl_status_detail.fontMetrics().elidedText(
            full_detail, Qt.TextElideMode.ElideRight, available_width)
        self.lbl_status_detail.setText(visible_detail)
        self.lbl_status_detail.setToolTip(full_detail if visible_detail != full_detail else "")
        self._last_engine_state = state
        self._last_engine_detail = detail

        # 3.5초 뒤 기본 ready 상태로 자동 복귀 (단, 일시정지나 오류 상태는 영구 유지)
        if state not in ("paused", "error"):
            if not hasattr(self, '_status_reset_timer') or self._status_reset_timer is None:
                self._status_reset_timer = QTimer(self)
                self._status_reset_timer.setSingleShot(True)
                self._status_reset_timer.timeout.connect(self._revert_engine_status)
            self._status_reset_timer.start(3500)

    def _revert_engine_status(self):
        is_screen_paused = (getattr(self, 'screen_worker', None) and getattr(self.screen_worker, 'paused', False)) or (getattr(self, 'screen_overlay', None) and getattr(self.screen_overlay, '_paused', False))
        is_audio_paused = (getattr(self, 'overlay', None) and getattr(self.overlay, '_audio_paused', False)) or (getattr(self, 'stt_thread', None) and getattr(self.stt_thread, 'is_paused', False))
        if is_screen_paused or is_audio_paused or getattr(self, '_last_engine_state', '') == 'paused':
            self.update_engine_status("paused", tr("detail_paused"))
            return
        if getattr(self, '_is_audio_active', False):
            self.update_engine_status("ready", tr("status_listening"))
        elif getattr(self, '_is_screen_active', False):
            self.update_engine_status("ready", tr("status_watching"))
        else:
            self.update_engine_status("ready", tr("status_idle"))

    def _on_audio_preview_received(self, text: str, ptype: str = ""):
        if not self.is_active:
            return
        if text:
            clean = text.strip()
            if clean:
                self.update_engine_status("recognizing", tr("status_heard", text=clean))

    # ----------------------------------------------------------------------
    # 3. 탭 1: 음성 번역 빌더 (컨셉 01-audio.png 완벽 일치)
    # ----------------------------------------------------------------------
    def _build_tab_audio(self) -> QWidget:
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 4, 0, 4)
        main_layout.setSpacing(10)

        # 상단 행: 오디오 소스 / 레벨 미터 / 통역 템포
        top_card = CardWidget()
        top_layout = QHBoxLayout(top_card)
        top_layout.setContentsMargins(12, 6, 12, 6)
        top_layout.setSpacing(14)

        # 1) 오디오 입력 소스
        src_vbox = QVBoxLayout()
        src_vbox.setSpacing(3)
        src_title = QLabel()
        self._i18n(src_title, "audio_source")
        src_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #ECEFF1;")
        src_row = QHBoxLayout()
        self.combo_audio_cap_dev = NoWheelComboBox()
        self.combo_audio_cap_dev.addItem(f"🔊 {tr('audio_default')}", "default")
        self.combo_audio_cap_dev.about_to_show_popup.connect(lambda: self._populate_audio_devices(silent=False))
        self.btn_refresh_sources = QPushButton()
        self._i18n(self.btn_refresh_sources, "refresh_sources")
        self.btn_refresh_sources.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.btn_refresh_sources.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_sources.clicked.connect(lambda: self._populate_audio_devices(silent=False))
        src_row.addWidget(self.combo_audio_cap_dev, stretch=1)
        src_row.addWidget(self.btn_refresh_sources)
        src_vbox.addWidget(src_title)
        src_vbox.addLayout(src_row)
        top_layout.addLayout(src_vbox, stretch=4)

        # 2) 입력 음량
        vol_vbox = QVBoxLayout()
        vol_vbox.setSpacing(4)
        vol_title = QLabel()
        self._i18n(vol_title, "input_volume")
        vol_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #ECEFF1;")
        vol_row = QHBoxLayout()
        mic_icon = QLabel("🎙️")
        mic_icon.setStyleSheet("font-size: 14px;")
        self.segment_level_meter = SegmentLevelMeter(segments=20)
        vol_row.addWidget(mic_icon)
        vol_row.addWidget(self.segment_level_meter, stretch=1)
        vol_vbox.addWidget(vol_title)
        vol_vbox.addLayout(vol_row)
        top_layout.addLayout(vol_vbox, stretch=3)

        # 3) 콘텐츠 템포
        tempo_vbox = QVBoxLayout()
        tempo_vbox.setSpacing(3)
        tempo_title = QLabel()
        self._i18n(tempo_title, "content_tempo")
        tempo_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #ECEFF1;")
        self.lbl_tempo_title_audio = tempo_title
        self.combo_tempo_preset = NoWheelComboBox()
        cur_preset = self.config.get("content_tempo_preset", "smart")
        cur_idx = 0
        for i, (k, p) in enumerate(CONTENT_TEMPO_PRESETS.items()):
            self.combo_tempo_preset.addItem(p["short_name"], k)
            if k == cur_preset:
                cur_idx = i
        self.combo_tempo_preset.setCurrentIndex(cur_idx)
        self.combo_tempo_preset.currentIndexChanged.connect(self.on_tempo_preset_changed)
        self.lbl_tempo_desc = QLabel(tempo_preset_desc(cur_preset, self.config))
        self.lbl_tempo_desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        tempo_vbox.addWidget(tempo_title)
        tempo_vbox.addWidget(self.combo_tempo_preset)
        tempo_vbox.addWidget(self.lbl_tempo_desc)
        top_layout.addLayout(tempo_vbox, stretch=3)

        main_layout.addWidget(top_card)

        # 중앙 행: 실시간 원본/번역문 텍스트 프리뷰 2열 카드
        preview_row = QHBoxLayout()
        preview_row.setSpacing(10)

        # 좌: 원문
        self.card_orig_preview = CardWidget(bg_color=COLOR_CARD_INNER)
        orig_layout = QVBoxLayout(self.card_orig_preview)
        orig_layout.setContentsMargins(14, 8, 14, 8)
        orig_layout.setSpacing(6)

        orig_head = QHBoxLayout()
        lbl_orig_title = QLabel()
        self._i18n(lbl_orig_title, "original")
        lbl_orig_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #ECEFF1;")
        badge_en = QLabel()
        self._i18n(badge_en, "original")
        badge_en.setStyleSheet(f"background-color: #1E293B; color: {COLOR_ACCENT_CYAN}; font-size: 11px; font-weight: bold; padding: 2px 8px; border-radius: 4px;")
        orig_head.addWidget(lbl_orig_title)
        orig_head.addStretch(1)
        if is_global():
            from src.translator import LANGUAGE_NAMES
            self.combo_source_lang = NoWheelComboBox()
            self.combo_source_lang.setCursor(Qt.CursorShape.PointingHandCursor)
            self.combo_source_lang.setFixedHeight(28)
            self.combo_source_lang.setMinimumWidth(120)
            self.combo_source_lang.setToolTip(tr("source_lang_label"))
            current_source = str(self.config.get("source_lang") or self.config.get("stt_language") or "auto").strip().lower().split("-")[0]
            self.combo_source_lang.addItem(tr("source_lang_auto"), "auto")
            for code in LANGUAGE_NAMES:
                self.combo_source_lang.addItem(UI_LANGUAGE_NAMES.get(code, code), code)
            source_index = self.combo_source_lang.findData(current_source)
            if source_index < 0:
                self.combo_source_lang.addItem(current_source.upper(), current_source)
                source_index = self.combo_source_lang.findData(current_source)
            self.combo_source_lang.blockSignals(True)
            self.combo_source_lang.setCurrentIndex(max(0, source_index))
            self.combo_source_lang.blockSignals(False)
            self.combo_source_lang.currentIndexChanged.connect(self._on_source_lang_changed)
            orig_head.addWidget(self.combo_source_lang)
        orig_head.addWidget(badge_en)
        orig_layout.addLayout(orig_head)

        orig_body = QHBoxLayout()
        orig_wave = QLabel("📶")
        orig_wave.setStyleSheet(f"font-size: 18px; color: {COLOR_ACCENT_CYAN};")
        self.lbl_live_orig = QLabel("We should leave before sunset.")
        self.lbl_live_orig.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF;")
        self.lbl_live_orig.setWordWrap(True)
        orig_body.addWidget(orig_wave)
        orig_body.addWidget(self.lbl_live_orig, stretch=1)
        orig_layout.addLayout(orig_body)
        preview_row.addWidget(self.card_orig_preview, stretch=1)

        # 우: 번역
        self.card_trans_preview = CardWidget(bg_color=COLOR_CARD_INNER)
        trans_layout = QVBoxLayout(self.card_trans_preview)
        trans_layout.setContentsMargins(14, 8, 14, 8)
        trans_layout.setSpacing(6)

        trans_head = QHBoxLayout()
        lbl_trans_title = QLabel()
        self._i18n(lbl_trans_title, "translation")
        lbl_trans_title.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {COLOR_ACCENT_PINK};")
        badge_ko = QLabel()
        self._i18n(badge_ko, "translation")
        badge_ko.setStyleSheet(f"background-color: rgba(236,72,153,0.18); color: {COLOR_ACCENT_PINK}; font-size: 11px; font-weight: bold; padding: 2px 8px; border-radius: 4px;")
        trans_head.addWidget(lbl_trans_title)
        trans_head.addStretch(1)
        if is_global():
            from src.translator import LANGUAGE_NAMES
            self.combo_target_lang = NoWheelComboBox()
            self.combo_target_lang.setCursor(Qt.CursorShape.PointingHandCursor)
            self.combo_target_lang.setFixedHeight(28)
            self.combo_target_lang.setMinimumWidth(120)
            self.combo_target_lang.setToolTip(tr("target_lang_label"))
            current_target = str(self.config.get("target_lang") or "en").strip().lower().split("-")[0]
            for code in LANGUAGE_NAMES:
                self.combo_target_lang.addItem(UI_LANGUAGE_NAMES.get(code, code), code)
            target_index = self.combo_target_lang.findData(current_target)
            if target_index < 0:
                self.combo_target_lang.addItem(current_target.upper(), current_target)
                target_index = self.combo_target_lang.findData(current_target)
            self.combo_target_lang.blockSignals(True)
            self.combo_target_lang.setCurrentIndex(max(0, target_index))
            self.combo_target_lang.blockSignals(False)
            self.combo_target_lang.currentIndexChanged.connect(self._on_target_lang_changed)
            trans_head.addWidget(self.combo_target_lang)
        trans_head.addWidget(badge_ko)
        trans_layout.addLayout(trans_head)

        trans_body = QHBoxLayout()
        trans_spk = QLabel("🔊")
        trans_spk.setStyleSheet(f"font-size: 18px; color: {COLOR_ACCENT_PINK};")
        self.lbl_live_trans = QLabel()
        self._i18n(self.lbl_live_trans, "sample_line")
        self.lbl_live_trans.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF;")
        self.lbl_live_trans.setWordWrap(True)
        trans_body.addWidget(trans_spk)
        trans_body.addWidget(self.lbl_live_trans, stretch=1)
        trans_layout.addLayout(trans_body)
        preview_row.addWidget(self.card_trans_preview, stretch=1)

        main_layout.addLayout(preview_row)

        # 하단 2열 분할: 좌측 [화자 관리 테이블] (65%) + 우측 [음성 더빙 출력 설정] (35%)
        lower_row = QHBoxLayout()
        lower_row.setSpacing(10)

        # --- 좌측: 화자 관리 카드 ---
        spk_card = CardWidget()
        self.speaker_management_card = spk_card
        spk_layout = QVBoxLayout(spk_card)
        spk_layout.setContentsMargins(12, 8, 12, 8)
        spk_layout.setSpacing(6)

        spk_header = QHBoxLayout()
        spk_header.setSpacing(10)
        spk_title = QLabel()
        self._i18n(spk_title, "speaker_mgmt")
        spk_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ECEFF1;")
        spk_header.addWidget(spk_title)
        spk_header.addStretch(1)

        self.lbl_speaker_status = QLabel()
        self._i18n(self.lbl_speaker_status, "speaker_checking")
        self.lbl_speaker_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_speaker_status.setToolTip(tr("tip_speaker_status"))
        self.lbl_speaker_status.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        spk_header.addWidget(self.lbl_speaker_status)
        spk_layout.addLayout(spk_header)

        # 화자 관리 옵션은 제목과 상태 메시지의 다음 줄에 배치한다.
        spk_controls = QHBoxLayout()
        self.speaker_controls_layout = spk_controls
        spk_controls.setSpacing(10)
        lbl_diar = QLabel()
        self._i18n(lbl_diar, "diarization")
        lbl_diar.setStyleSheet("font-size: 12px; font-weight: 600;")
        diar_tip = tr("tip_speaker_diarization")
        lbl_diar.setToolTip(diar_tip)
        self.toggle_speaker_diarization = ModernToggle(active_color=COLOR_ACCENT_PURPLE)
        self.toggle_speaker_diarization.setChecked(self.config.get("speaker_diarization_enabled", False))
        self.toggle_speaker_diarization.setToolTip(diar_tip)
        self.toggle_speaker_diarization.toggled.connect(self.on_speaker_diarization_toggled)
        self.cb_speaker_diarization = self.toggle_speaker_diarization  # 하위 호환 별칭

        lbl_max_spk = QLabel()
        self._i18n(lbl_max_spk, "max_speakers")
        lbl_max_spk.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.combo_speaker_max_count = NoWheelComboBox()
        self.combo_speaker_max_count.addItem(tr("spk_count_2"), 2)
        self.combo_speaker_max_count.addItem(tr("spk_count_3"), 3)
        self.combo_speaker_max_count.addItem(tr("spk_count_4"), 4)
        self.combo_speaker_max_count.addItem(tr("spk_count_8"), 8)
        cur_max = int(self.config.get("speaker_max_count", 2))
        found_max_idx = self.combo_speaker_max_count.findData(cur_max)
        if found_max_idx >= 0:
            self.combo_speaker_max_count.setCurrentIndex(found_max_idx)
        self.combo_speaker_max_count.setFixedWidth(130)
        self.combo_speaker_max_count.currentIndexChanged.connect(self.on_speaker_max_count_changed)

        lbl_thresh = QLabel()
        self._i18n(lbl_thresh, "sensitivity")
        lbl_thresh.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.lbl_speaker_threshold = lbl_thresh
        self.slider_speaker_threshold = NoWheelSlider(Qt.Orientation.Horizontal)
        self.slider_speaker_threshold.setRange(25, 65)
        cur_th = float(self.config.get("speaker_similarity_threshold", 0.42))
        self.slider_speaker_threshold.setValue(int(cur_th * 100))
        self.slider_speaker_threshold.setFixedWidth(80)
        self.slider_speaker_threshold.setToolTip(tr("tip_speaker_threshold"))
        self.slider_speaker_threshold.valueChanged.connect(self.on_speaker_threshold_changed)
        self.lbl_speaker_threshold_num = QLabel(str(int(cur_th * 100)))
        self.lbl_speaker_threshold_num.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 12px;")

        lbl_ocr_link = QLabel()
        self._i18n(lbl_ocr_link, "name_link")
        lbl_ocr_link.setStyleSheet("font-size: 12px; font-weight: 600;")
        lbl_ocr_link.setToolTip(tr("tip_ocr_speaker_link"))
        self.toggle_ocr_auto_mapping = ModernToggle(active_color=COLOR_ACCENT_MINT)
        self.toggle_ocr_auto_mapping.setChecked(self.config.get("speaker_ocr_auto_mapping", True))
        self.toggle_ocr_auto_mapping.setToolTip(tr("tip_ocr_speaker_link"))
        self.toggle_ocr_auto_mapping.toggled.connect(self.on_ocr_auto_mapping_toggled)

        spk_controls.addWidget(lbl_diar)
        spk_controls.addWidget(self.toggle_speaker_diarization)
        spk_controls.addSpacing(8)
        spk_controls.addWidget(lbl_max_spk)
        spk_controls.addWidget(self.combo_speaker_max_count)
        spk_controls.addSpacing(8)
        spk_controls.addWidget(lbl_thresh)
        spk_controls.addWidget(self.slider_speaker_threshold)
        spk_controls.addWidget(self.lbl_speaker_threshold_num)
        spk_controls.addSpacing(8)
        spk_controls.addWidget(lbl_ocr_link)
        spk_controls.addWidget(self.toggle_ocr_auto_mapping)
        spk_controls.addStretch(1)
        spk_layout.addLayout(spk_controls)

        # 화자 목록 테이블 / 컨테이너
        self.speaker_scroll = QScrollArea()
        self.speaker_scroll.setWidgetResizable(True)
        self.speaker_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.speaker_scroll.setStyleSheet("background: transparent;")
        self.speaker_list_container = QWidget()
        self.speaker_list_layout = QVBoxLayout(self.speaker_list_container)
        self.speaker_list_layout.setSpacing(4)
        self.speaker_list_layout.setContentsMargins(0, 0, 0, 0)
        self.speaker_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.speaker_scroll.setWidget(self.speaker_list_container)
        spk_layout.addWidget(self.speaker_scroll, stretch=1)

        # 화자 관리 하단 액션 버튼들
        spk_actions = QHBoxLayout()
        self.speaker_actions_layout = spk_actions
        spk_actions.setSpacing(6)
        self.btn_reset_speakers = QPushButton()
        self._i18n(self.btn_reset_speakers, "reset_speakers")
        self.btn_reset_speakers.clicked.connect(self.on_reset_speakers_clicked)
        spk_actions.addWidget(self.btn_reset_speakers)

        spk_actions.addStretch(1)

        btn_sel_trans = QPushButton()
        self._i18n(btn_sel_trans, "apply_selected_trans")
        btn_sel_trans.setStyleSheet(f"border-color: {COLOR_ACCENT_MINT}; color: {COLOR_ACCENT_MINT};")
        btn_sel_trans.clicked.connect(self.on_translate_selected_speakers)
        btn_sel_dub = QPushButton()
        self._i18n(btn_sel_dub, "apply_selected_dub")
        btn_sel_dub.setStyleSheet(f"border-color: {COLOR_ACCENT_PINK}; color: {COLOR_ACCENT_PINK};")
        btn_sel_dub.clicked.connect(self.on_dub_selected_speakers)
        btn_all_trans = QPushButton()
        self._i18n(btn_all_trans, "all_speakers_trans")
        btn_all_trans.clicked.connect(self.on_unmute_all_speakers)
        btn_all_dub = QPushButton()
        self._i18n(btn_all_dub, "all_speakers_dub")
        btn_all_dub.clicked.connect(self.on_dub_all_speakers)

        spk_actions.addWidget(btn_sel_trans)
        spk_actions.addWidget(btn_sel_dub)
        spk_actions.addWidget(btn_all_trans)
        spk_actions.addWidget(btn_all_dub)
        spk_layout.addLayout(spk_actions)

        lower_row.addWidget(spk_card, stretch=6)

        # --- 우측: 음성 더빙 (출력 설정) 사이드바 패널 ---
        dub_card = CardWidget()
        self.dubbing_settings_card = dub_card
        dub_layout = QVBoxLayout(dub_card)
        dub_layout.setContentsMargins(14, 12, 14, 12)
        dub_layout.setSpacing(8)

        dub_head = QHBoxLayout()
        lbl_dub_title = QLabel()
        self._i18n(lbl_dub_title, "dub_output")
        lbl_dub_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        self.btn_toggle_audio_overlay = QPushButton()
        self._i18n(self.btn_toggle_audio_overlay, "show_overlay")
        self.btn_toggle_audio_overlay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_audio_overlay.setStyleSheet("font-size: 11px; padding: 3px 8px;")
        self.btn_toggle_audio_overlay.clicked.connect(self.toggle_audio_overlay_window)
        self._update_audio_overlay_btn_ui()
        dub_head.addWidget(lbl_dub_title)
        dub_head.addStretch(1)
        dub_head.addWidget(self.btn_toggle_audio_overlay)
        dub_layout.addLayout(dub_head)

        # 1. 오디오 출력 장치 (가장 상단 배치)
        out_dev_row = QHBoxLayout()
        out_dev_row.setContentsMargins(0, 0, 0, 0)
        lbl_out_dev = QLabel()
        self._i18n(lbl_out_dev, "output_device")
        lbl_out_dev.setStyleSheet("font-size: 11.5px; font-weight: 600; color: #ECEFF1;")
        self.combo_dub_out_dev = NoWheelComboBox()
        self.combo_dub_out_dev.setFixedHeight(28)
        self.combo_dub_out_dev.addItem(f"🔊 {tr('audio_default')}", "default")
        self.combo_dub_out_dev.currentIndexChanged.connect(self.on_dubbing_output_device_changed)
        out_dev_row.addWidget(lbl_out_dev, stretch=3)
        out_dev_row.addWidget(self.combo_dub_out_dev, stretch=6)
        dub_layout.addLayout(out_dev_row)

        # 2. 핵심 더빙 소스 선택 (음성 / 화면) 및 개별 목소리 설정
        # 2-1. 음성 번역 더빙 토글
        row_voice = QHBoxLayout()
        row_voice.setContentsMargins(0, 0, 0, 0)
        lbl_v = QLabel()
        self._i18n(lbl_v, "dub_voice")
        lbl_v.setStyleSheet("font-size: 11.5px; font-weight: 600; color: #ECEFF1;")
        self.toggle_dub_voice = ModernToggle(active_color=COLOR_ACCENT_MINT)
        self.toggle_dub_voice.setFixedHeight(24)
        is_audio_dub = bool(self.config.get("dubbing_enabled", False) and self.config.get("dubbing_source_audio", True))
        self.toggle_dub_voice.setChecked(is_audio_dub)
        self.toggle_dub_voice.toggled.connect(self.on_dubbing_source_audio_toggled)
        row_voice.addWidget(lbl_v)
        row_voice.addStretch(1)
        row_voice.addWidget(self.toggle_dub_voice)
        dub_layout.addLayout(row_voice)

        # 음성 번역 더빙 목소리 선택 드롭다운
        row_v_voice = QHBoxLayout()
        row_v_voice.setContentsMargins(12, 0, 0, 2)
        lbl_v_voice = QLabel()
        self._i18n(lbl_v_voice, "dub_voice_select_audio")
        lbl_v_voice.setStyleSheet("font-size: 11px; color: #94A3B8;")
        self.combo_dub_voice_audio = NoWheelComboBox()
        self.combo_dub_voice_audio.setFixedHeight(26)
        self.combo_dub_voice_audio.currentIndexChanged.connect(self.on_dubbing_voice_audio_changed)
        row_v_voice.addWidget(lbl_v_voice, stretch=3)
        row_v_voice.addWidget(self.combo_dub_voice_audio, stretch=6)
        dub_layout.addLayout(row_v_voice)

        # 2-2. 화면 번역 더빙 토글
        row_screen = QHBoxLayout()
        row_screen.setContentsMargins(0, 4, 0, 0)
        lbl_s = QLabel()
        self._i18n(lbl_s, "dub_screen")
        lbl_s.setStyleSheet("font-size: 11.5px; font-weight: 600; color: #ECEFF1;")
        self.toggle_dub_screen = ModernToggle(active_color=COLOR_ACCENT_MINT)
        self.toggle_dub_screen.setFixedHeight(24)
        is_screen_dub = bool(self.config.get("dubbing_enabled", False) and self.config.get("dubbing_source_screen", False))
        self.toggle_dub_screen.setChecked(is_screen_dub)
        self.toggle_dub_screen.toggled.connect(self.on_dubbing_source_screen_toggled)
        row_screen.addWidget(lbl_s)
        row_screen.addStretch(1)
        row_screen.addWidget(self.toggle_dub_screen)
        dub_layout.addLayout(row_screen)

        # 화면 번역 더빙 목소리 선택 드롭다운
        row_s_voice = QHBoxLayout()
        row_s_voice.setContentsMargins(12, 0, 0, 4)
        lbl_s_voice = QLabel()
        self._i18n(lbl_s_voice, "dub_voice_select_screen")
        lbl_s_voice.setStyleSheet("font-size: 11px; color: #94A3B8;")
        self.combo_dub_voice_screen = NoWheelComboBox()
        self.combo_dub_voice_screen.setFixedHeight(26)
        self.combo_dub_voice_screen.currentIndexChanged.connect(self.on_dubbing_voice_screen_changed)
        row_s_voice.addWidget(lbl_s_voice, stretch=3)
        row_s_voice.addWidget(self.combo_dub_voice_screen, stretch=6)
        dub_layout.addLayout(row_s_voice)

        self._populate_dubbing_voice_combos()

        # 3. 슬라이더: 더빙 음량
        dub_vol_row = QHBoxLayout()
        dub_vol_row.setContentsMargins(0, 0, 0, 0)
        cur_d_vol = int(self.config.get("dubbing_volume", 80))
        self.lbl_dubbing_vol = QLabel()
        self._i18n(self.lbl_dubbing_vol, "dub_volume")
        self.lbl_dubbing_vol.setStyleSheet("font-size: 11.5px; font-weight: 600; color: #ECEFF1;")
        self.lbl_dubbing_vol.setFixedHeight(24)
        self.lbl_dubbing_vol_val = QLabel(f"{cur_d_vol}%")
        self.lbl_dubbing_vol_val.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.lbl_dubbing_vol_val.setFixedWidth(38)
        self.lbl_dubbing_vol_val.setFixedHeight(24)
        self.lbl_dubbing_vol_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.slider_dubbing_vol = NoWheelSlider(Qt.Orientation.Horizontal)
        self.slider_dubbing_vol.setRange(0, 100)
        self.slider_dubbing_vol.setFixedHeight(24)
        self.slider_dubbing_vol.setValue(cur_d_vol)
        self.slider_dubbing_vol.valueChanged.connect(self.on_dubbing_volume_changed)
        dub_vol_row.addWidget(self.lbl_dubbing_vol, stretch=3)
        dub_vol_row.addWidget(self.slider_dubbing_vol, stretch=6)
        dub_vol_row.addWidget(self.lbl_dubbing_vol_val)
        dub_layout.addLayout(dub_vol_row)

        # 4. 슬라이더: 원본 음량
        orig_vol_row = QHBoxLayout()
        orig_vol_row.setContentsMargins(0, 0, 0, 0)
        cur_o_vol = int(self.config.get("original_volume", 100))
        self.lbl_original_vol = QLabel()
        self._i18n(self.lbl_original_vol, "original_volume")
        self.lbl_original_vol.setStyleSheet("font-size: 11.5px; font-weight: 600; color: #ECEFF1;")
        self.lbl_original_vol.setFixedHeight(24)
        self.lbl_original_vol_val = QLabel(f"{cur_o_vol}%")
        self.lbl_original_vol_val.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.lbl_original_vol_val.setFixedWidth(38)
        self.lbl_original_vol_val.setFixedHeight(24)
        self.lbl_original_vol_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.slider_original_vol = NoWheelSlider(Qt.Orientation.Horizontal)
        self.slider_original_vol.setRange(0, 100)
        self.slider_original_vol.setFixedHeight(24)
        self.slider_original_vol.setValue(cur_o_vol)
        self.slider_original_vol.valueChanged.connect(self.on_original_volume_changed)
        orig_vol_row.addWidget(self.lbl_original_vol, stretch=3)
        orig_vol_row.addWidget(self.slider_original_vol, stretch=6)
        orig_vol_row.addWidget(self.lbl_original_vol_val)
        dub_layout.addLayout(orig_vol_row)

        # 5. 콤보: 더빙 속도
        spd_row = QHBoxLayout()
        spd_row.setContentsMargins(0, 0, 0, 0)
        lbl_spd = QLabel()
        self._i18n(lbl_spd, "dub_speed")
        lbl_spd.setStyleSheet("font-size: 11.5px; font-weight: 600; color: #ECEFF1;")
        self.lbl_spd_val = QLabel(self.config.get("dubbing_speed", "+10%"))
        self.combo_dubbing_speed = NoWheelComboBox()
        self.combo_dubbing_speed.setFixedHeight(28)
        speeds = [
            ("+0%", tr("speed_normal")), ("+10%", tr("speed_brisk")), ("+15%", "1.15x"),
            ("+20%", "1.2x"), ("+25%", "1.25x"), ("+30%", "1.3x"), ("+40%", "1.4x"),
            ("+50%", "1.5x"), ("+80%", "1.8x"), ("+100%", "2.0x")
        ]
        for s_code, s_name in speeds:
            self.combo_dubbing_speed.addItem(s_name, s_code)
        idx_s = self.combo_dubbing_speed.findData(self.config.get("dubbing_speed", "+10%"))
        if idx_s >= 0:
            self.combo_dubbing_speed.setCurrentIndex(idx_s)
        self.combo_dubbing_speed.currentIndexChanged.connect(self.on_dubbing_speed_changed)
        spd_row.addWidget(lbl_spd, stretch=3)
        spd_row.addWidget(self.combo_dubbing_speed, stretch=6)
        dub_layout.addLayout(spd_row)

        # 6. 토글: 오디오 덕킹 ON/OFF
        duck_toggle_row = QHBoxLayout()
        duck_toggle_row.setContentsMargins(0, 0, 0, 0)
        self.lbl_duck_toggle = QLabel()
        self._i18n(self.lbl_duck_toggle, "ducking")
        self.lbl_duck_toggle.setStyleSheet("font-size: 11.5px; font-weight: 600; color: #ECEFF1;")
        self.toggle_audio_ducking = ModernToggle(active_color=COLOR_ACCENT_MINT)
        self.toggle_audio_ducking.setFixedHeight(24)
        is_ducking_enabled = self.config.get("audio_ducking_enabled", True)
        self.toggle_audio_ducking.setChecked(is_ducking_enabled)
        self.toggle_audio_ducking.toggled.connect(self.on_audio_ducking_toggled)
        duck_toggle_row.addWidget(self.lbl_duck_toggle)
        duck_toggle_row.addStretch(1)
        duck_toggle_row.addWidget(self.toggle_audio_ducking)
        dub_layout.addLayout(duck_toggle_row)

        # 7. 슬라이더: 감쇄 목표 (%)
        att_row = QHBoxLayout()
        att_row.setContentsMargins(0, 0, 0, 0)
        self.lbl_att_title = QLabel()
        self._i18n(self.lbl_att_title, "duck_target")
        self.lbl_att_title.setStyleSheet("font-size: 11.5px; font-weight: 600; color: #ECEFF1;")
        self.lbl_att_title.setFixedHeight(24)
        cur_duck = int(self.config.get("audio_ducking_volume", 25))
        self.lbl_att_val = QLabel(f"{cur_duck}%")
        self.lbl_att_val.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.lbl_att_val.setFixedWidth(38)
        self.lbl_att_val.setFixedHeight(24)
        self.lbl_att_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_duck_val = self.lbl_att_val  # 하위 호환성 유지
        self.slider_ducking_vol = NoWheelSlider(Qt.Orientation.Horizontal)
        self.slider_ducking_vol.setRange(0, 100)
        self.slider_ducking_vol.setFixedHeight(24)
        self.slider_ducking_vol.setValue(cur_duck)
        self.slider_ducking_vol.valueChanged.connect(self.on_ducking_volume_changed)
        att_row.addWidget(self.lbl_att_title, stretch=3)
        att_row.addWidget(self.slider_ducking_vol, stretch=6)
        att_row.addWidget(self.lbl_att_val)
        dub_layout.addLayout(att_row)

        # 덕킹 토글 상태에 따른 슬라이더 활성화/비활성화
        self.slider_ducking_vol.setEnabled(is_ducking_enabled)
        self.lbl_att_title.setEnabled(is_ducking_enabled)
        self.lbl_att_val.setEnabled(is_ducking_enabled)

        # 8. 하단 부가 토글 옵션 2종
        sub_opts = [
            ("dub_cut", "dubbing_interrupt", self.on_dubbing_interrupt_toggled, False),
            ("dub_echo", "dubbing_echo_cancellation", self.on_dubbing_echo_cancel_toggled, True),
        ]
        for name, key, cb, default_val in sub_opts:
            t_row = QHBoxLayout()
            t_row.setContentsMargins(0, 0, 0, 0)
            lbl_t = QLabel()
            self._i18n(lbl_t, name)
            lbl_t.setStyleSheet("font-size: 11.5px; font-weight: 600; color: #ECEFF1;")
            tgl = ModernToggle(active_color=COLOR_ACCENT_MINT)
            tgl.setFixedHeight(24)
            tgl.setChecked(self.config.get(key, default_val))
            tgl.toggled.connect(cb)
            t_row.addWidget(lbl_t)
            t_row.addStretch(1)
            t_row.addWidget(tgl)
            dub_layout.addLayout(t_row)

        # 9. 하단 싱크 초기화
        self.btn_reset_sync = QPushButton()
        self._i18n(self.btn_reset_sync, "reset_sync")
        self.btn_reset_sync.setStyleSheet("font-size: 11.5px; font-weight: 600; padding: 6px;")
        self.btn_reset_sync.setFixedHeight(30)
        self.btn_reset_sync.clicked.connect(self.on_reset_sync_clicked)
        dub_layout.addWidget(self.btn_reset_sync)
        dub_layout.addStretch(1)

        # 좌우 카드의 실제 컨트롤 폭을 창 최소 너비에 반영한다. 탭 스택은
        # minimumSizeHint를 0으로 보고하므로 카드만으로는 창 축소를 막지 못한다.
        speaker_inner_width = max(spk_header.sizeHint().width(),
                                  spk_controls.sizeHint().width(),
                                  spk_actions.sizeHint().width())
        self._audio_speaker_min_width = max(800, speaker_inner_width + 44)
        self._audio_dubbing_min_width = max(370, dub_card.sizeHint().width())
        spk_card.setMinimumWidth(self._audio_speaker_min_width)
        dub_card.setMinimumWidth(self._audio_dubbing_min_width)
        self._required_content_width = (self._audio_speaker_min_width +
                                        self._audio_dubbing_min_width + lower_row.spacing() + 20)

        lower_row.addWidget(dub_card, stretch=4)
        main_layout.addLayout(lower_row, stretch=1)

        # 초기 장치 로드
        self._populate_audio_devices()
        self.combo_audio_cap_dev.currentIndexChanged.connect(self.on_audio_capture_device_changed)

        return container

    # ----------------------------------------------------------------------
    # 4. 탭 2: 화면 번역 빌더 (컨셉 06-screen-capture-workflow.png 일치)
    # ----------------------------------------------------------------------
    def _build_tab_screen(self) -> QWidget:
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 4, 0, 4)
        main_layout.setSpacing(10)

        # 상단 툴바: 모니터 선택 / F4 전체 번역 / 1회 번역 / 영역 추가
        toolbar_card = CardWidget()
        tb_layout = QHBoxLayout(toolbar_card)
        tb_layout.setContentsMargins(14, 8, 14, 8)
        tb_layout.setSpacing(12)

        lbl_mon = QLabel()
        self._i18n(lbl_mon, "monitor")
        lbl_mon.setStyleSheet("font-weight: bold; font-size: 11px; color: #ECEFF1;")
        self.combo_display = NoWheelComboBox()
        self._populate_display_combo()
        self.combo_display.currentIndexChanged.connect(self.on_display_changed)
        tb_layout.addWidget(lbl_mon)
        tb_layout.addWidget(self.combo_display)

        self.btn_identify_monitors = QPushButton()
        self._i18n(self.btn_identify_monitors, "show_numbers")
        self.btn_identify_monitors.setToolTip(tr("tip_identify_monitors"))
        self.btn_identify_monitors.clicked.connect(self.show_monitor_identifiers)
        tb_layout.addWidget(self.btn_identify_monitors)

        cur_hk = self.config.get("inplace_hotkey", "F4")
        self.btn_inplace_translate = QPushButton()
        self._i18n(self.btn_inplace_translate, "fullscreen_translate")
        self.btn_inplace_translate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_inplace_translate.setToolTip(tr("tip_fullscreen_translate", key=cur_hk))
        self.btn_inplace_translate.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ACCENT_PURPLE};
                color: #FFFFFF;
                font-weight: bold;
                border: 1px solid #818CF8;
                border-radius: 6px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_ACCENT_PURPLE_HOVER};
            }}
        """)
        self.btn_inplace_translate.clicked.connect(lambda: self.trigger_inplace_translate(from_button=True))
        tb_layout.addWidget(self.btn_inplace_translate)

        tb_layout.addSpacing(6)

        self.btn_select_roi = QPushButton()
        self._i18n(self.btn_select_roi, "edit_regions")
        self.btn_select_roi.clicked.connect(self.open_roi_selector)
        tb_layout.addWidget(self.btn_select_roi)

        self.btn_instant_ocr = QPushButton()
        self._i18n(self.btn_instant_ocr, "instant_region")
        self.btn_instant_ocr.clicked.connect(self.trigger_instant_screen_ocr)
        tb_layout.addWidget(self.btn_instant_ocr)

        is_border = self.config.get("screen_show_roi_border", False)
        self.cb_show_roi_border = ModernToggle(active_color=COLOR_ACCENT_PURPLE)
        self.cb_show_roi_border.setChecked(is_border)
        self.cb_show_roi_border.toggled.connect(self.on_show_roi_border_toggled)

        self.btn_toggle_roi_border = QPushButton(f"🔲 {tr('region_border')} {'ON' if is_border else 'OFF'}")
        self.btn_toggle_roi_border.clicked.connect(self.toggle_roi_border)
        tb_layout.addWidget(self.btn_toggle_roi_border)

        tb_layout.addStretch(1)

        main_layout.addWidget(toolbar_card)

        # 중앙: 대형 화면 프리뷰 캔버스 (65%) + 우측 영역 설정 (35%)
        mid_layout = QHBoxLayout()
        mid_layout.setSpacing(10)

        # 좌측 프리뷰 카드
        screen_preview_card = CardWidget(bg_color=COLOR_CARD_INNER)
        sp_layout = QVBoxLayout(screen_preview_card)
        sp_layout.setContentsMargins(8, 8, 8, 8)
        sp_layout.setSpacing(6)

        preview_head = QHBoxLayout()
        self.lbl_screen_preview = QLabel()
        self._i18n(self.lbl_screen_preview, "preview")
        self.lbl_screen_preview.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        preview_head.addWidget(self.lbl_screen_preview)
        preview_head.addStretch(1)
        self.btn_refresh_screen_preview = QPushButton()
        self._i18n(self.btn_refresh_screen_preview, "refresh_screen")
        self.btn_refresh_screen_preview.clicked.connect(self._refresh_screen_preview)
        preview_head.addWidget(self.btn_refresh_screen_preview)
        sp_layout.addLayout(preview_head)

        # 프리뷰 캔버스 (선택 모니터 화면과 동적 ROI 박스 오버레이)
        bg_asset = _get_asset_path("preview_bg.png")
        self.screen_canvas = ScreenCanvasPreviewWidget(bg_image_path=bg_asset)
        self.screen_canvas.set_rois(self.config.get("screen_rois", []))
        current_index = self.combo_display.currentIndex()
        screens = QApplication.screens()
        if 0 <= current_index < len(screens):
            self.screen_canvas.set_monitor(screens[current_index].geometry())
        sp_layout.addWidget(self.screen_canvas, stretch=1)

        guide_lbl = QLabel()
        self._i18n(guide_lbl, "roi_guide")
        guide_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        sp_layout.addWidget(guide_lbl)

        mid_layout.addWidget(screen_preview_card, stretch=6)

        # 우측: 영역별 자막 설정 패널 (Multi-ROI 묶음 카드 목록)
        roi_card_container = CardWidget()
        roi_main_layout = QVBoxLayout(roi_card_container)
        roi_main_layout.setContentsMargins(12, 8, 12, 8)
        roi_main_layout.setSpacing(6)

        # 상단 헤더: 타이틀 + 뱃지 + 추가/전체삭제 버튼
        roi_top_bar = QHBoxLayout()
        lbl_card_title = QLabel()
        self._i18n(lbl_card_title, "roi_manage")
        lbl_card_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ECEFF1;")
        roi_top_bar.addWidget(lbl_card_title)

        self.lbl_roi_count_badge = QLabel()
        self._i18n(self.lbl_roi_count_badge, "roi_count", count=0)
        self.lbl_roi_count_badge.setStyleSheet(f"background-color: #1E293B; color: {COLOR_ACCENT_CYAN}; font-size: 11px; font-weight: bold; padding: 2px 6px; border-radius: 10px;")
        roi_top_bar.addWidget(self.lbl_roi_count_badge)

        roi_top_bar.addStretch(1)

        btn_top_add = QPushButton()
        self._i18n(btn_top_add, "add")
        btn_top_add.setStyleSheet(f"background-color: {COLOR_ACCENT_PURPLE}; color: #FFF; font-weight: bold; padding: 3px 8px; font-size: 11px; border-radius: 4px;")
        btn_top_add.clicked.connect(self.open_roi_selector)
        roi_top_bar.addWidget(btn_top_add)

        btn_top_clear = QPushButton()
        self._i18n(btn_top_clear, "clear_all")
        btn_top_clear.setStyleSheet("background-color: rgba(239,68,68,0.15); color: #EF4444; border: 1px solid #EF4444; padding: 3px 8px; font-size: 11px; border-radius: 4px;")
        btn_top_clear.clicked.connect(self.clear_rois)
        roi_top_bar.addWidget(btn_top_clear)

        roi_main_layout.addLayout(roi_top_bar)

        lbl_card_sub = QLabel()
        self._i18n(lbl_card_sub, "roi_hint")
        lbl_card_sub.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        roi_main_layout.addWidget(lbl_card_sub)

        # ROI 묶음 카드 스크롤 영역
        self.roi_scroll = QScrollArea()
        self.roi_scroll.setWidgetResizable(True)
        self.roi_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.roi_container_widget = QWidget()
        self.roi_container_widget.setStyleSheet("background: transparent;")
        self.roi_cards_layout = QVBoxLayout(self.roi_container_widget)
        self.roi_cards_layout.setContentsMargins(0, 4, 0, 4)
        self.roi_cards_layout.setSpacing(10)
        self.roi_scroll.setWidget(self.roi_container_widget)
        roi_main_layout.addWidget(self.roi_scroll, stretch=1)

        # 공통 전처리 & 자막 스냅 설정 바
        pre_card = QFrame()
        pre_card.setObjectName("PreCard")
        pre_card.setStyleSheet(f"#PreCard {{ background-color: {COLOR_CARD_INNER}; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }} QLabel {{ border: none; background: transparent; }}")
        pre_layout = QHBoxLayout(pre_card)
        pre_layout.setContentsMargins(8, 4, 8, 4)
        pre_layout.setSpacing(10)

        lbl_pre = QLabel()
        self._i18n(lbl_pre, "sharpen")
        lbl_pre.setStyleSheet("font-size: 11px; color: #94A3B8;")
        pre_layout.addWidget(lbl_pre)
        self.slider_ocr_clahe = NoWheelSlider(Qt.Orientation.Horizontal)
        self.slider_ocr_clahe.setRange(0, 100)
        self.slider_ocr_clahe.setValue(70)
        self.slider_ocr_clahe.valueChanged.connect(lambda v: self.config.update({"screen_ocr_preprocess": v > 30}))
        pre_layout.addWidget(self.slider_ocr_clahe, stretch=1)

        lbl_snap = QLabel()
        self._i18n(lbl_snap, "snap")
        lbl_snap.setStyleSheet("font-size: 11px; color: #94A3B8;")
        pre_layout.addWidget(lbl_snap)
        self.toggle_snap_to_roi = ModernToggle(active_color=COLOR_ACCENT_PURPLE)
        self.toggle_snap_to_roi.setChecked(self.config.get("screen_snap_to_roi", False))
        self.toggle_snap_to_roi.toggled.connect(self.on_snap_to_roi_toggled)
        self.cb_snap_to_roi = self.toggle_snap_to_roi
        pre_layout.addWidget(self.toggle_snap_to_roi)

        roi_main_layout.addWidget(pre_card)

        # 카드 갱신
        self.refresh_roi_settings_cards()

        mid_layout.addWidget(roi_card_container, stretch=4)
        main_layout.addLayout(mid_layout, stretch=1)

        # 하단: 최근 화면 OCR 대화 두 건
        bottom_chat_card = CardWidget()
        bc_layout = QVBoxLayout(bottom_chat_card)
        bc_layout.setContentsMargins(12, 8, 12, 8)
        bc_layout.setSpacing(6)

        bc_head = QHBoxLayout()
        lbl_bc_title = QLabel()
        self._i18n(lbl_bc_title, "recent_screen")
        lbl_bc_title.setStyleSheet("font-weight: bold; font-size: 11px; color: #ECEFF1;")
        bc_head.addWidget(lbl_bc_title)
        bc_head.addStretch(1)

        btn_copy = QPushButton()
        self._i18n(btn_copy, "copy")
        btn_copy.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        btn_copy.clicked.connect(lambda: self.on_copy_subtitles_clicked(source_filter="screen"))
        btn_srt = QPushButton()
        self._i18n(btn_srt, "export_srt")
        btn_srt.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        btn_srt.clicked.connect(lambda: self.on_export_srt_clicked(source_filter="screen"))
        btn_txt = QPushButton()
        self._i18n(btn_txt, "export_txt")
        btn_txt.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        btn_txt.clicked.connect(lambda: self.on_export_txt_clicked(source_filter="screen"))

        bc_head.addWidget(btn_copy)
        bc_head.addWidget(btn_srt)
        bc_head.addWidget(btn_txt)
        bc_layout.addLayout(bc_head)

        self.screen_dialogue_table = QTableWidget(0, 2)
        self.screen_dialogue_table.setHorizontalHeaderLabels([tr("original"), tr("translation")])
        self.screen_dialogue_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.screen_dialogue_table.horizontalHeader().setFixedHeight(24)
        self.screen_dialogue_table.verticalHeader().hide()
        self.screen_dialogue_table.setShowGrid(False)
        self.screen_dialogue_table.setWordWrap(True)
        self.screen_dialogue_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.screen_dialogue_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.screen_dialogue_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.screen_dialogue_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.screen_dialogue_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.screen_dialogue_table.setFixedHeight(116)
        self.screen_dialogue_table.setStyleSheet("QTableWidget { background-color: #0E1524; border: 1px solid #1E2A42; border-radius: 6px; font-size: 11px; } QHeaderView::section { background-color: #172238; color: #94A3B8; border: none; padding: 3px 8px; font-weight: bold; }")
        bc_layout.addWidget(self.screen_dialogue_table)
        self._update_mini_chat()

        main_layout.addWidget(bottom_chat_card)

        return container

    # ----------------------------------------------------------------------
    # 5. 탭 3: 실시간 자막 빌더 (컨셉 02-transcripts.png 일치)
    # ----------------------------------------------------------------------
    def _build_tab_history(self) -> QWidget:
        container = QWidget()
        main_layout = QHBoxLayout(container)
        main_layout.setContentsMargins(0, 4, 0, 4)
        main_layout.setSpacing(10)

        # 좌측 메인: [자막 기록] 카드 (75%)
        log_card = CardWidget()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(16, 12, 16, 12)
        log_layout.setSpacing(10)

        head_vbox = QVBoxLayout()
        head_vbox.setSpacing(2)
        log_title = QLabel()
        self._i18n(log_title, "history_title")
        log_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ECEFF1;")
        log_sub = QLabel()
        self._i18n(log_sub, "history_sub")
        log_sub.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SECONDARY};")
        head_vbox.addWidget(log_title)
        head_vbox.addWidget(log_sub)
        log_layout.addLayout(head_vbox)

        # 툴바: 뷰 모드 콤보, 검색창, 자동 스크롤, 건수 카운트, 액션 버튼
        tb_row = QHBoxLayout()
        tb_row.setSpacing(8)

        self.combo_sub_filter = NoWheelComboBox()
        self.combo_sub_filter.addItem(tr("filter_all_compare"), "all")
        self.combo_sub_filter.addItem(tr("filter_voice_trans"), "audio")
        self.combo_sub_filter.addItem(tr("filter_screen_trans"), "screen")
        self.combo_sub_filter.addItem(tr("filter_dub_voice"), "dubbing")
        self.combo_sub_filter.addItem(tr("filter_orig_only"), "orig_only")
        self.combo_sub_filter.addItem(tr("filter_trans_only"), "trans_only")
        self.combo_sub_filter.addItem(tr("filter_dub_speech_only"), "dub_only")
        self.combo_sub_filter.currentIndexChanged.connect(self.on_subtitle_filter_changed)
        self.combo_sub_filter.setFixedWidth(160)
        tb_row.addWidget(self.combo_sub_filter)

        self.input_sub_search = QLineEdit()
        self.input_sub_search.setPlaceholderText(f"🔍 {tr('search_placeholder')}...")
        self.input_sub_search.textChanged.connect(self.on_subtitle_filter_changed)
        tb_row.addWidget(self.input_sub_search, stretch=1)

        lbl_autoscroll = QLabel()
        self._i18n(lbl_autoscroll, "autoscroll")
        lbl_autoscroll.setStyleSheet("font-size: 11px;")
        self.toggle_sub_autoscroll = ModernToggle(active_color=COLOR_ACCENT_PURPLE)
        self.toggle_sub_autoscroll.setChecked(True)
        tb_row.addWidget(lbl_autoscroll)
        tb_row.addWidget(self.toggle_sub_autoscroll)

        self.lbl_sub_count = QLabel()
        self._i18n(self.lbl_sub_count, "count_total", total=0)
        self.lbl_sub_count.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-size: 11px; font-weight: bold; background: #0E1524; padding: 4px 8px; border-radius: 4px;")
        tb_row.addWidget(self.lbl_sub_count)

        self.btn_export_srt = QPushButton()
        self._i18n(self.btn_export_srt, "save_srt")
        self.btn_export_srt.clicked.connect(self.on_export_srt_clicked)
        self.btn_export_txt = QPushButton()
        self._i18n(self.btn_export_txt, "save_txt")
        self.btn_export_txt.clicked.connect(self.on_export_txt_clicked)
        self.btn_copy_sub = QPushButton()
        self._i18n(self.btn_copy_sub, "copy_all")
        self.btn_copy_sub.clicked.connect(self.on_copy_subtitles_clicked)
        self.btn_clear_sub = QPushButton()
        self._i18n(self.btn_clear_sub, "clear_history")
        self.btn_clear_sub.setStyleSheet("color: #EF4444; border-color: rgba(239,68,68,0.4);")
        self.btn_clear_sub.clicked.connect(self.on_clear_subtitles_clicked)

        tb_row.addWidget(self.btn_export_srt)
        tb_row.addWidget(self.btn_export_txt)
        tb_row.addWidget(self.btn_copy_sub)
        tb_row.addWidget(self.btn_clear_sub)
        log_layout.addLayout(tb_row)

        # 고정 헤더 바 (스크롤되지 않고 상단에 항상 고정)
        self.header_sub_history = QFrame()
        self.header_sub_history.setObjectName("SubHistoryHeader")
        self.header_sub_history.setFixedHeight(34)
        self.header_sub_history.setStyleSheet("""
            QFrame#SubHistoryHeader {
                background-color: #101726;
                border: 1px solid #1C273E;
                border-bottom: 2px solid #1E2A42;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }
            QLabel {
                color: #94A3B8;
                font-size: 11px;
                font-weight: bold;
                font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
            }
        """)
        self.header_sub_layout = QHBoxLayout(self.header_sub_history)
        self.header_sub_layout.setContentsMargins(12, 0, 24, 0)
        self.header_sub_layout.setSpacing(0)

        self.lbl_th_time = QLabel()
        self._i18n(self.lbl_th_time, "history_th_time")
        self.lbl_th_source = QLabel()
        self._i18n(self.lbl_th_source, "history_th_source")
        self.lbl_th_orig = QLabel()
        self._i18n(self.lbl_th_orig, "original")
        self.lbl_th_trans = QLabel()
        self._i18n(self.lbl_th_trans, "translation")
        self.lbl_th_dub = QLabel()
        self._i18n(self.lbl_th_dub, "history_th_dub")

        self.header_sub_layout.addWidget(self.lbl_th_time, stretch=12)
        self.header_sub_layout.addWidget(self.lbl_th_source, stretch=15)
        self.header_sub_layout.addWidget(self.lbl_th_orig, stretch=28)
        self.header_sub_layout.addWidget(self.lbl_th_trans, stretch=25)
        self.header_sub_layout.addWidget(self.lbl_th_dub, stretch=20)

        # 5열 자막 뷰어 테이블 (본문만 스크롤됨)
        self.text_sub_history = QTextBrowser()
        self.text_sub_history.setOpenExternalLinks(False)
        self.text_sub_history.setReadOnly(True)
        self.text_sub_history.setStyleSheet("""
            QTextBrowser {
                background-color: #0E1422;
                color: #ECEFF1;
                border: 1px solid #1C273E;
                border-top: none;
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                padding: 2px 4px 6px 4px;
                font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
            }
        """)
        self.text_sub_history.setHtml(SubtitleHistoryManager.format_html_table([]))

        table_container = QVBoxLayout()
        table_container.setContentsMargins(0, 0, 0, 0)
        table_container.setSpacing(0)
        table_container.addWidget(self.header_sub_history)
        table_container.addWidget(self.text_sub_history, stretch=1)
        log_layout.addLayout(table_container, stretch=1)

        main_layout.addWidget(log_card, stretch=7)

        # 우측 패널: [표시 필터] 사이드바 (25%)
        filter_card = CardWidget()
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setContentsMargins(14, 14, 14, 14)
        filter_layout.setSpacing(10)

        f_title = QLabel()
        self._i18n(f_title, "filter_title")
        f_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        filter_layout.addWidget(f_title)

        filter_options = [
            ("filter_all_compare", "all"),
            ("filter_voice_trans", "audio"),
            ("filter_screen_trans", "screen"),
            ("filter_dub_voice", "dubbing"),
            ("---", ""),
            ("filter_orig_only", "orig_only"),
            ("filter_trans_only", "trans_only"),
            ("filter_dub_speech_only", "dub_only"),
        ]
        self.filter_buttons = []
        for key, val in filter_options:
            if key == "---":
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setStyleSheet(f"background-color: {COLOR_BORDER};")
                filter_layout.addWidget(line)
                continue

            btn = QPushButton()
            self._i18n(btn, key)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(34)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #101728;
                    color: {COLOR_TEXT_PRIMARY};
                    border: 1px solid {COLOR_BORDER};
                    border-radius: 6px;
                    text-align: left;
                    padding-left: 12px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: #182238;
                }}
                QPushButton:checked {{
                    background-color: {COLOR_ACCENT_PURPLE};
                    color: #FFFFFF;
                    font-weight: bold;
                    border: 1px solid #818CF8;
                }}
            """)
            btn.clicked.connect(lambda _, v=val: self._on_sidebar_filter_selected(v))
            filter_layout.addWidget(btn)
            self.filter_buttons.append((btn, val))

        if self.filter_buttons:
            self.filter_buttons[0][0].setChecked(True)

        filter_layout.addStretch(1)

        info_box = CardWidget(bg_color=COLOR_CARD_INNER, border_radius=6)
        ib_layout = QVBoxLayout(info_box)
        ib_layout.setContentsMargins(10, 10, 10, 10)
        ib_txt = QLabel()
        self._i18n(ib_txt, "history_hint")
        ib_txt.setWordWrap(True)
        ib_txt.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 10px; line-height: 1.4;")
        ib_layout.addWidget(ib_txt)
        filter_layout.addWidget(info_box)

        main_layout.addWidget(filter_card, stretch=3)
        return container

    def _on_sidebar_filter_selected(self, filter_key: str):
        for btn, key in self.filter_buttons:
            btn.setChecked(key == filter_key)
        idx = self.combo_sub_filter.findData(filter_key)
        if idx >= 0:
            self.combo_sub_filter.setCurrentIndex(idx)
        else:
            self.on_subtitle_filter_changed()

    # ----------------------------------------------------------------------
    # 6. 탭 4: 자막 디자인 빌더 (컨셉 03-subtitle-design.png 일치)
    # ----------------------------------------------------------------------
    def _build_tab_subtitles(self) -> QWidget:
        container = QWidget()
        main_layout = QHBoxLayout(container)
        main_layout.setContentsMargins(0, 4, 0, 4)
        main_layout.setSpacing(10)

        # 좌측: [자막 디자인 미리보기] 대형 캔버스 & 가독성 예시 (65%)
        canvas_card = CardWidget()
        c_layout = QVBoxLayout(canvas_card)
        c_layout.setContentsMargins(16, 12, 16, 12)
        c_layout.setSpacing(10)

        c_head = QHBoxLayout()
        c_vbox = QVBoxLayout()
        c_vbox.setSpacing(2)
        c_title = QLabel()
        self._i18n(c_title, "design_preview")
        c_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ECEFF1;")
        c_sub = QLabel()
        self._i18n(c_sub, "design_sub")
        c_sub.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SECONDARY};")
        c_vbox.addWidget(c_title)
        c_vbox.addWidget(c_sub)
        c_head.addLayout(c_vbox)
        c_head.addStretch(1)

        c_layout.addLayout(c_head)

        # 대형 렌더링 캔버스
        bg_asset = _get_asset_path("preview_bg.png")
        self.preview_canvas = SubtitlePreviewWidget(bg_image_path=bg_asset)
        c_layout.addWidget(self.preview_canvas, stretch=1)

        # 하단: 검은색 vs 흰색 (100% 전폭 카드 및 스타일 실시간 연동)
        ex_card = CardWidget(bg_color=COLOR_CARD_INNER)
        ex_layout = QVBoxLayout(ex_card)
        ex_layout.setContentsMargins(14, 10, 14, 10)
        ex_layout.setSpacing(8)
        ex_title = QLabel()
        self._i18n(ex_title, "contrast_sample")
        ex_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #ECEFF1;")
        ex_layout.addWidget(ex_title)

        self.readability_widget = ReadabilityPreviewWidget(bg_image_path=bg_asset)
        ex_layout.addWidget(self.readability_widget)
        c_layout.addWidget(ex_card)

        main_layout.addWidget(canvas_card, stretch=6)

        # 우측: [자막 표시 제어] & [자막 스타일] & [표시 설정] 카드 (35%)
        side_card = CardWidget()
        s_layout = QVBoxLayout(side_card)
        s_layout.setContentsMargins(16, 14, 16, 14)
        s_layout.setSpacing(10)

        # 섹션 1: 자막 표시 제어
        sec0_title = QLabel()
        self._i18n(sec0_title, "display_control")
        sec0_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        s_layout.addWidget(sec0_title)

        ctrl_box = QVBoxLayout()
        ctrl_box.setSpacing(6)

        r1 = QHBoxLayout()
        r1.setContentsMargins(0, 1, 0, 1)
        lbl_r1 = QLabel()
        self._i18n(lbl_r1, "show_audio_sub")
        lbl_r1.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        self.toggle_audio_overlay_vis = ModernToggle(active_color=COLOR_ACCENT_MINT)
        self.toggle_audio_overlay_vis.setChecked(self.config.get("audio_overlay_visible", True))
        self.toggle_audio_overlay_vis.toggled.connect(self.toggle_audio_overlay_window)
        r1.addWidget(lbl_r1)
        r1.addStretch(1)
        r1.addWidget(self.toggle_audio_overlay_vis)
        ctrl_box.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setContentsMargins(0, 1, 0, 1)
        lbl_r2 = QLabel()
        self._i18n(lbl_r2, "show_screen_sub")
        lbl_r2.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        self.toggle_screen_overlay_vis = ModernToggle(active_color=COLOR_ACCENT_PURPLE)
        self.toggle_screen_overlay_vis.setChecked(self.config.get("screen_overlay_visible", True))
        self.toggle_screen_overlay_vis.toggled.connect(self.toggle_screen_overlay_window)
        r2.addWidget(lbl_r2)
        r2.addStretch(1)
        r2.addWidget(self.toggle_screen_overlay_vis)
        ctrl_box.addLayout(r2)
        s_layout.addLayout(ctrl_box)

        line0 = QFrame()
        line0.setFrameShape(QFrame.Shape.HLine)
        line0.setStyleSheet(f"background-color: {COLOR_BORDER}; max-height: 1px;")
        s_layout.addWidget(line0)

        # ==============================================================
        # 서브탭 전환 버튼: [ 🎙️ 음성 번역 자막 ]  |  [ 👁️ 화면 번역 자막 ]
        # ==============================================================
        self._current_subtab = "audio"

        subtab_layout = QHBoxLayout()
        subtab_layout.setContentsMargins(0, 2, 0, 4)
        subtab_layout.setSpacing(6)

        self.btn_subtab_audio = QPushButton()
        self._i18n(self.btn_subtab_audio, "subtab_audio_subtitles")
        self.btn_subtab_audio.setCheckable(True)
        self.btn_subtab_audio.setChecked(True)
        self.btn_subtab_audio.setFixedHeight(34)
        self.btn_subtab_audio.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_subtab_screen = QPushButton()
        self._i18n(self.btn_subtab_screen, "subtab_screen_subtitles")
        self.btn_subtab_screen.setCheckable(True)
        self.btn_subtab_screen.setChecked(False)
        self.btn_subtab_screen.setFixedHeight(34)
        self.btn_subtab_screen.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_subtab_audio.clicked.connect(lambda: self._on_subtab_switched("audio"))
        self.btn_subtab_screen.clicked.connect(lambda: self._on_subtab_switched("screen"))

        subtab_layout.addWidget(self.btn_subtab_audio, 1)
        subtab_layout.addWidget(self.btn_subtab_screen, 1)
        s_layout.addLayout(subtab_layout)

        # 독립 스택 위젯 (0: 음성 자막 패널, 1: 화면 자막 패널)
        self.sub_stack = QStackedWidget()

        # --------------------------------------------------------------
        # 서브패널 1: 음성 번역 자막 설정
        # --------------------------------------------------------------
        self.panel_sub_audio = QWidget()
        audio_layout = QVBoxLayout(self.panel_sub_audio)
        audio_layout.setContentsMargins(0, 0, 0, 0)
        audio_layout.setSpacing(8)

        # 음성 - 섹션 1: 자막 스타일
        sec1_audio_title = QLabel()
        self._i18n(sec1_audio_title, "subtitle_style")
        sec1_audio_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        audio_layout.addWidget(sec1_audio_title)

        audio_style_box = QVBoxLayout()
        audio_style_box.setSpacing(6)

        # 글꼴 크기
        r_a_font = QHBoxLayout()
        r_a_font.setContentsMargins(0, 1, 0, 1)
        lbl_a_font = QLabel()
        self._i18n(lbl_a_font, "font_size")
        lbl_a_font.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        lbl_a_font.setFixedWidth(84)
        _v = self.config.get("audio_font_size")
        cur_a_font = int(_v) if _v is not None else int(self.config.get("font_size", 24))
        self.audio_font_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.audio_font_slider.setRange(14, 40)
        self.audio_font_slider.setValue(cur_a_font)
        self.audio_font_label = QLabel(f"{cur_a_font}px")
        self.audio_font_label.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.audio_font_label.setFixedWidth(52)
        self.audio_font_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.audio_font_slider.valueChanged.connect(lambda v: (self.on_audio_font_slider_changed(v, None), self.audio_font_label.setText(f"{v}px"), self._update_subtitle_preview()))
        r_a_font.addWidget(lbl_a_font)
        r_a_font.addWidget(self.audio_font_slider, stretch=1)
        r_a_font.addWidget(self.audio_font_label)
        audio_style_box.addLayout(r_a_font)

        # 배경 불투명도
        r_a_op = QHBoxLayout()
        r_a_op.setContentsMargins(0, 1, 0, 1)
        lbl_a_op = QLabel()
        self._i18n(lbl_a_op, "opacity")
        lbl_a_op.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        lbl_a_op.setFixedWidth(84)
        _v = self.config.get("audio_overlay_bg_opacity")
        cur_a_op = int(float(_v) * 100) if _v is not None else int(float(self.config.get("overlay_bg_opacity", 0.66)) * 100)
        self.audio_opacity_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.audio_opacity_slider.setRange(0, 100)
        self.audio_opacity_slider.setValue(cur_a_op)
        self.audio_opacity_label = QLabel(f"{cur_a_op}%")
        self.audio_opacity_label.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.audio_opacity_label.setFixedWidth(52)
        self.audio_opacity_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.audio_opacity_slider.valueChanged.connect(lambda v: (self.on_audio_opacity_slider_changed(v, None), self.audio_opacity_label.setText(f"{v}%"), self._update_subtitle_preview()))
        r_a_op.addWidget(lbl_a_op)
        r_a_op.addWidget(self.audio_opacity_slider, stretch=1)
        r_a_op.addWidget(self.audio_opacity_label)
        audio_style_box.addLayout(r_a_op)

        # 외곽선 두께
        r_a_str = QHBoxLayout()
        r_a_str.setContentsMargins(0, 1, 0, 1)
        lbl_a_str = QLabel()
        self._i18n(lbl_a_str, "stroke")
        lbl_a_str.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        lbl_a_str.setFixedWidth(84)
        _v = self.config.get("audio_subtitle_stroke_width")
        cur_a_str = int(_v) if _v is not None else int(self.config.get("subtitle_stroke_width", 0))
        self.audio_slider_stroke = NoWheelSlider(Qt.Orientation.Horizontal)
        self.audio_slider_stroke.setRange(0, 5)
        self.audio_slider_stroke.setValue(cur_a_str)
        self.audio_lbl_stroke = QLabel(f"{cur_a_str}px")
        self.audio_lbl_stroke.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.audio_lbl_stroke.setFixedWidth(52)
        self.audio_lbl_stroke.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.audio_slider_stroke.valueChanged.connect(lambda v: (self.on_audio_stroke_slider_changed(v), self.audio_lbl_stroke.setText(f"{v}px"), self._update_subtitle_preview()))
        r_a_str.addWidget(lbl_a_str)
        r_a_str.addWidget(self.audio_slider_stroke, stretch=1)
        r_a_str.addWidget(self.audio_lbl_stroke)
        audio_style_box.addLayout(r_a_str)

        # 글자 자간
        r_a_spc = QHBoxLayout()
        r_a_spc.setContentsMargins(0, 1, 0, 1)
        lbl_a_spc = QLabel()
        self._i18n(lbl_a_spc, "letter_spacing")
        lbl_a_spc.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        lbl_a_spc.setFixedWidth(84)
        _v = self.config.get("audio_letter_spacing")
        cur_a_spc = float(_v) if _v is not None else float(self.config.get("letter_spacing", 0.0))
        self.audio_slider_spacing = NoWheelSlider(Qt.Orientation.Horizontal)
        self.audio_slider_spacing.setRange(0, 40)
        self.audio_slider_spacing.setValue(int(cur_a_spc * 10))
        self.audio_lbl_spacing = QLabel(f"{cur_a_spc:.1f}px")
        self.audio_lbl_spacing.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.audio_lbl_spacing.setFixedWidth(52)
        self.audio_lbl_spacing.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.audio_slider_spacing.valueChanged.connect(lambda v: (self.on_audio_spacing_slider_changed(v), self.audio_lbl_spacing.setText(f"{v/10.0:.1f}px"), self._update_subtitle_preview()))
        r_a_spc.addWidget(lbl_a_spc)
        r_a_spc.addWidget(self.audio_slider_spacing, stretch=1)
        r_a_spc.addWidget(self.audio_lbl_spacing)
        audio_style_box.addLayout(r_a_spc)

        # 유지 시간 (음성 번역 전용)
        r_a_dur = QHBoxLayout()
        r_a_dur.setContentsMargins(0, 1, 0, 1)
        lbl_a_dur = QLabel()
        self._i18n(lbl_a_dur, "duration")
        lbl_a_dur.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        lbl_a_dur.setFixedWidth(84)
        _v_a = self.config.get("audio_subtitle_duration")
        if _v_a is None:
            _v_a = self.config.get("subtitle_duration")
        cur_a_dur = int(_v_a) if _v_a is not None else 5
        self.audio_slider_duration = NoWheelSlider(Qt.Orientation.Horizontal)
        self.audio_slider_duration.setRange(0, 90)
        self.audio_slider_duration.setValue(cur_a_dur)
        self.audio_lbl_duration = QLabel(self._duration_text(cur_a_dur))
        self.audio_lbl_duration.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.audio_lbl_duration.setFixedWidth(52)
        self.audio_lbl_duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.audio_slider_duration.valueChanged.connect(lambda v: (self.on_audio_duration_slider_changed(v), self.audio_lbl_duration.setText(self._duration_text(v))))
        r_a_dur.addWidget(lbl_a_dur)
        r_a_dur.addWidget(self.audio_slider_duration, stretch=1)
        r_a_dur.addWidget(self.audio_lbl_duration)
        audio_style_box.addLayout(r_a_dur)

        audio_layout.addLayout(audio_style_box)

        line_a = QFrame()
        line_a.setFrameShape(QFrame.Shape.HLine)
        line_a.setStyleSheet(f"background-color: {COLOR_BORDER}; max-height: 1px;")
        audio_layout.addWidget(line_a)

        # 음성 - 섹션 2: 표시 설정
        sec2_audio_title = QLabel()
        self._i18n(sec2_audio_title, "display_settings")
        sec2_audio_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        audio_layout.addWidget(sec2_audio_title)

        audio_disp_box = QVBoxLayout()
        audio_disp_box.setSpacing(6)

        audio_disp_opts = [
            ("opt_show_speaker", "audio_show_speaker", "show_speaker", self.on_audio_show_speaker_toggled, True),
            ("opt_show_original", "audio_show_original", "show_original", self.on_audio_show_original_toggled, True),
            ("opt_show_translated", "audio_show_translated", "show_translated", self.on_audio_show_translated_toggled, True),
            ("opt_show_badge", "audio_show_engine_badge", "show_engine_badge", self.on_audio_show_badge_toggled, True),
            ("opt_click_through", "audio_click_through", "click_through", self.on_audio_click_through_toggled, False),
            ("opt_clean_text", "audio_clean_text_mode", "clean_text_mode", self.on_audio_clean_text_toggled, False),
            ("opt_clean_box", "audio_clean_box", "clean_box", self.on_audio_clean_box_toggled, True),
        ]
        for opt_key, primary_key, fallback_key, cb, default_val in audio_disp_opts:
            row = QHBoxLayout()
            row.setContentsMargins(0, 1, 0, 1)
            lbl = QLabel()
            self._i18n(lbl, opt_key)
            lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
            tgl = ModernToggle(active_color=COLOR_ACCENT_MINT)
            _val = self.config.get(primary_key)
            if _val is None:
                _val = self.config.get(fallback_key)
            if _val is None:
                _val = default_val
            tgl.setChecked(bool(_val))
            tgl.toggled.connect(lambda checked, fn=cb: (fn(checked), self._update_subtitle_preview()))
            if opt_key == "opt_clean_box":
                self.audio_cb_clean_box = tgl
            elif opt_key == "opt_clean_text":
                self.audio_cb_clean_text = tgl
            elif opt_key == "opt_show_original":
                self.audio_cb_show_original = tgl
            elif opt_key == "opt_show_translated":
                self.audio_cb_show_translated = tgl
            elif opt_key == "opt_show_badge":
                self.audio_cb_show_badge = tgl
            elif opt_key == "opt_click_through":
                self.audio_cb_click_through = tgl
            elif opt_key == "opt_show_speaker":
                self.audio_cb_show_speaker = tgl
            row.addWidget(lbl)
            row.addStretch(1)
            row.addWidget(tgl)
            audio_disp_box.addLayout(row)

        audio_layout.addLayout(audio_disp_box)
        audio_layout.addStretch(1)
        self.sub_stack.addWidget(self.panel_sub_audio)

        # --------------------------------------------------------------
        # 서브패널 2: 화면 번역 자막 설정
        # --------------------------------------------------------------
        self.panel_sub_screen = QWidget()
        screen_layout = QVBoxLayout(self.panel_sub_screen)
        screen_layout.setContentsMargins(0, 0, 0, 0)
        screen_layout.setSpacing(8)

        # 화면 - 섹션 1: 자막 스타일
        sec1_screen_title = QLabel()
        self._i18n(sec1_screen_title, "subtitle_style")
        sec1_screen_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        screen_layout.addWidget(sec1_screen_title)

        screen_style_box = QVBoxLayout()
        screen_style_box.setSpacing(6)

        # 글꼴 크기
        r_s_font = QHBoxLayout()
        r_s_font.setContentsMargins(0, 1, 0, 1)
        lbl_s_font = QLabel()
        self._i18n(lbl_s_font, "font_size")
        lbl_s_font.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        lbl_s_font.setFixedWidth(84)
        _v = self.config.get("screen_font_size")
        cur_s_font = int(_v) if _v is not None else int(self.config.get("font_size", 24))
        self.screen_font_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.screen_font_slider.setRange(14, 40)
        self.screen_font_slider.setValue(cur_s_font)
        self.screen_font_label = QLabel(f"{cur_s_font}px")
        self.screen_font_label.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.screen_font_label.setFixedWidth(52)
        self.screen_font_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.screen_font_slider.valueChanged.connect(lambda v: (self.on_screen_font_slider_changed(v, None), self.screen_font_label.setText(f"{v}px"), self._update_subtitle_preview()))
        r_s_font.addWidget(lbl_s_font)
        r_s_font.addWidget(self.screen_font_slider, stretch=1)
        r_s_font.addWidget(self.screen_font_label)
        screen_style_box.addLayout(r_s_font)

        # 배경 불투명도
        r_s_op = QHBoxLayout()
        r_s_op.setContentsMargins(0, 1, 0, 1)
        lbl_s_op = QLabel()
        self._i18n(lbl_s_op, "opacity")
        lbl_s_op.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        lbl_s_op.setFixedWidth(84)
        _v = self.config.get("screen_overlay_bg_opacity")
        cur_s_op = int(float(_v) * 100) if _v is not None else int(float(self.config.get("overlay_bg_opacity", 0.66)) * 100)
        self.screen_opacity_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.screen_opacity_slider.setRange(0, 100)
        self.screen_opacity_slider.setValue(cur_s_op)
        self.screen_opacity_label = QLabel(f"{cur_s_op}%")
        self.screen_opacity_label.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.screen_opacity_label.setFixedWidth(52)
        self.screen_opacity_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.screen_opacity_slider.valueChanged.connect(lambda v: (self.on_screen_opacity_slider_changed(v, None), self.screen_opacity_label.setText(f"{v}%"), self._update_subtitle_preview()))
        r_s_op.addWidget(lbl_s_op)
        r_s_op.addWidget(self.screen_opacity_slider, stretch=1)
        r_s_op.addWidget(self.screen_opacity_label)
        screen_style_box.addLayout(r_s_op)

        # 외곽선 두께
        r_s_str = QHBoxLayout()
        r_s_str.setContentsMargins(0, 1, 0, 1)
        lbl_s_str = QLabel()
        self._i18n(lbl_s_str, "stroke")
        lbl_s_str.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        lbl_s_str.setFixedWidth(84)
        _v = self.config.get("screen_subtitle_stroke_width")
        cur_s_str = int(_v) if _v is not None else int(self.config.get("subtitle_stroke_width", 0))
        self.screen_slider_stroke = NoWheelSlider(Qt.Orientation.Horizontal)
        self.screen_slider_stroke.setRange(0, 5)
        self.screen_slider_stroke.setValue(cur_s_str)
        self.screen_lbl_stroke = QLabel(f"{cur_s_str}px")
        self.screen_lbl_stroke.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.screen_lbl_stroke.setFixedWidth(52)
        self.screen_lbl_stroke.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.screen_slider_stroke.valueChanged.connect(lambda v: (self.on_screen_stroke_slider_changed(v), self.screen_lbl_stroke.setText(f"{v}px"), self._update_subtitle_preview()))
        r_s_str.addWidget(lbl_s_str)
        r_s_str.addWidget(self.screen_slider_stroke, stretch=1)
        r_s_str.addWidget(self.screen_lbl_stroke)
        screen_style_box.addLayout(r_s_str)

        # 글자 자간
        r_s_spc = QHBoxLayout()
        r_s_spc.setContentsMargins(0, 1, 0, 1)
        lbl_s_spc = QLabel()
        self._i18n(lbl_s_spc, "letter_spacing")
        lbl_s_spc.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        lbl_s_spc.setFixedWidth(84)
        _v = self.config.get("screen_letter_spacing")
        cur_s_spc = float(_v) if _v is not None else float(self.config.get("letter_spacing", 0.0))
        self.screen_slider_spacing = NoWheelSlider(Qt.Orientation.Horizontal)
        self.screen_slider_spacing.setRange(0, 40)
        self.screen_slider_spacing.setValue(int(cur_s_spc * 10))
        self.screen_lbl_spacing = QLabel(f"{cur_s_spc:.1f}px")
        self.screen_lbl_spacing.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.screen_lbl_spacing.setFixedWidth(52)
        self.screen_lbl_spacing.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.screen_slider_spacing.valueChanged.connect(lambda v: (self.on_screen_spacing_slider_changed(v), self.screen_lbl_spacing.setText(f"{v/10.0:.1f}px"), self._update_subtitle_preview()))
        r_s_spc.addWidget(lbl_s_spc)
        r_s_spc.addWidget(self.screen_slider_spacing, stretch=1)
        r_s_spc.addWidget(self.screen_lbl_spacing)
        screen_style_box.addLayout(r_s_spc)

        # 유지 시간 (화면 번역 전용)
        r_s_dur = QHBoxLayout()
        r_s_dur.setContentsMargins(0, 1, 0, 1)
        lbl_s_dur = QLabel()
        self._i18n(lbl_s_dur, "duration")
        lbl_s_dur.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
        lbl_s_dur.setFixedWidth(84)
        _v = self.config.get("screen_subtitle_duration")
        cur_s_dur = int(_v) if _v is not None else 5
        self.screen_slider_duration = NoWheelSlider(Qt.Orientation.Horizontal)
        self.screen_slider_duration.setRange(0, 90)
        self.screen_slider_duration.setValue(cur_s_dur)
        self.screen_lbl_duration = QLabel(self._duration_text(cur_s_dur))
        self.screen_lbl_duration.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-weight: bold; font-size: 11.5px;")
        self.screen_lbl_duration.setFixedWidth(52)
        self.screen_lbl_duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.screen_slider_duration.valueChanged.connect(lambda v: (self.on_screen_duration_slider_changed(v), self.screen_lbl_duration.setText(self._duration_text(v))))
        r_s_dur.addWidget(lbl_s_dur)
        r_s_dur.addWidget(self.screen_slider_duration, stretch=1)
        r_s_dur.addWidget(self.screen_lbl_duration)
        screen_style_box.addLayout(r_s_dur)

        screen_layout.addLayout(screen_style_box)

        line_s = QFrame()
        line_s.setFrameShape(QFrame.Shape.HLine)
        line_s.setStyleSheet(f"background-color: {COLOR_BORDER}; max-height: 1px;")
        screen_layout.addWidget(line_s)

        # 화면 - 섹션 2: 표시 설정
        sec2_screen_title = QLabel()
        self._i18n(sec2_screen_title, "display_settings")
        sec2_screen_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        screen_layout.addWidget(sec2_screen_title)

        screen_disp_box = QVBoxLayout()
        screen_disp_box.setSpacing(6)

        screen_disp_opts = [
            ("opt_show_speaker", "screen_show_speaker", "show_speaker", self.on_screen_show_speaker_toggled, True),
            ("opt_show_original", "screen_show_original", "show_original", self.on_screen_show_original_toggled, True),
            ("opt_show_translated", "screen_show_translated", "show_translated", self.on_screen_show_translated_toggled, True),
            ("opt_show_badge", "screen_show_engine_badge", "show_engine_badge", self.on_screen_show_badge_toggled, True),
            ("opt_click_through", "screen_click_through", "click_through", self.on_screen_click_through_toggled, False),
            ("opt_clean_text", "screen_clean_text_mode", "screen_clean_text_mode", self.on_screen_clean_text_toggled, False),
            ("opt_clean_box", "screen_clean_box", "screen_clean_box", self.on_screen_clean_box_toggled, True),
        ]
        for opt_key, primary_key, fallback_key, cb, default_val in screen_disp_opts:
            row = QHBoxLayout()
            row.setContentsMargins(0, 1, 0, 1)
            lbl = QLabel()
            self._i18n(lbl, opt_key)
            lbl.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px;")
            tgl = ModernToggle(active_color=COLOR_ACCENT_PURPLE)
            _val = self.config.get(primary_key)
            if _val is None:
                _val = self.config.get(fallback_key)
            if _val is None:
                _val = default_val
            tgl.setChecked(bool(_val))
            tgl.toggled.connect(lambda checked, fn=cb: (fn(checked), self._update_subtitle_preview()))
            if opt_key == "opt_clean_box":
                self.screen_cb_clean_box = tgl
            elif opt_key == "opt_clean_text":
                self.screen_cb_clean_text = tgl
            elif opt_key == "opt_show_original":
                self.screen_cb_show_original = tgl
            elif opt_key == "opt_show_translated":
                self.screen_cb_show_translated = tgl
            elif opt_key == "opt_show_badge":
                self.screen_cb_show_badge = tgl
            elif opt_key == "opt_click_through":
                self.screen_cb_click_through = tgl
            elif opt_key == "opt_show_speaker":
                self.screen_cb_show_speaker = tgl
            row.addWidget(lbl)
            row.addStretch(1)
            row.addWidget(tgl)
            screen_disp_box.addLayout(row)

        screen_layout.addLayout(screen_disp_box)
        screen_layout.addStretch(1)
        self.sub_stack.addWidget(self.panel_sub_screen)

        s_layout.addWidget(self.sub_stack)

        # 하위 호환성 (테스트 및 레거시 모듈 연동용 슬라이더 및 체크박스 별칭)
        cur_f = int(self.config.get("font_size", 24))
        self.font_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(14, 40)
        self.font_slider.setValue(cur_f)
        self.font_label = QLabel(f"{cur_f}px")
        self.font_slider.valueChanged.connect(lambda v: (self.on_font_slider_changed(v, None), self.font_label.setText(f"{v}px"), self._update_subtitle_preview()))

        cur_op = int(float(self.config.get("overlay_bg_opacity", 0.66)) * 100)
        self.opacity_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(cur_op)
        self.opacity_label = QLabel(f"{cur_op}%")
        self.opacity_slider.valueChanged.connect(lambda v: (self.on_opacity_slider_changed(v, None), self.opacity_label.setText(f"{v}%"), self._update_subtitle_preview()))

        cur_str = int(self.config.get("subtitle_stroke_width", 0))
        self.slider_stroke = NoWheelSlider(Qt.Orientation.Horizontal)
        self.slider_stroke.setRange(0, 5)
        self.slider_stroke.setValue(cur_str)
        self.lbl_stroke = QLabel(f"{cur_str}px")
        self.slider_stroke.valueChanged.connect(lambda v: (self.on_stroke_slider_changed(v), self.lbl_stroke.setText(f"{v}px"), self._update_subtitle_preview()))

        cur_spc = float(self.config.get("letter_spacing", 0.0))
        self.slider_spacing = NoWheelSlider(Qt.Orientation.Horizontal)
        self.slider_spacing.setRange(0, 40)
        self.slider_spacing.setValue(int(cur_spc * 10))
        self.lbl_spacing = QLabel(f"{cur_spc:.1f}px")
        self.slider_spacing.valueChanged.connect(lambda v: (self.on_spacing_slider_changed(v), self.lbl_spacing.setText(f"{v/10.0:.1f}px"), self._update_subtitle_preview()))

        self.slider_duration = self.screen_slider_duration
        self.lbl_duration = self.screen_lbl_duration

        self.cb_show_speaker = self.audio_cb_show_speaker
        self.cb_show_original = self.audio_cb_show_original
        self.cb_show_badge = self.audio_cb_show_badge
        self.cb_click_through = self.audio_cb_click_through
        self.cb_clean_text = self.screen_cb_clean_text
        self.cb_clean_box = self.screen_cb_clean_box

        self.slider_spacing_sec4 = self.slider_spacing
        self.lbl_spacing_sec4 = self.lbl_spacing

        self._update_subtab_button_styles()

        s_layout.addStretch(1)

        btn_reset_pos = QPushButton()
        self._i18n(btn_reset_pos, "reset_geometry")
        btn_reset_pos.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset_pos.setFixedHeight(34)
        btn_reset_pos.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                font-weight: 600;
                padding: 6px 12px;
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                color: #ECEFF1;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                border-color: rgba(255, 255, 255, 0.24);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.04);
            }
        """)
        btn_reset_pos.clicked.connect(self.reset_overlay_position)
        s_layout.addWidget(btn_reset_pos)

        main_layout.addWidget(side_card, stretch=4)
        self._update_subtitle_preview()
        return container

    def _update_subtab_button_styles(self):
        is_audio = getattr(self, "_current_subtab", "audio") == "audio"
        if is_audio:
            self.btn_subtab_audio.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(0, 242, 254, 0.16);
                    color: {COLOR_ACCENT_CYAN};
                    border: 1.5px solid {COLOR_ACCENT_CYAN};
                    border-radius: 6px;
                    font-size: 11.5px;
                    font-weight: bold;
                    padding: 4px 8px;
                }}
            """)
            self.btn_subtab_screen.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_CARD_INNER};
                    color: {COLOR_TEXT_SECONDARY};
                    border: 1px solid {COLOR_BORDER};
                    border-radius: 6px;
                    font-size: 11.5px;
                    font-weight: normal;
                    padding: 4px 8px;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.08);
                    color: {COLOR_TEXT_PRIMARY};
                }}
            """)
        else:
            self.btn_subtab_audio.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_CARD_INNER};
                    color: {COLOR_TEXT_SECONDARY};
                    border: 1px solid {COLOR_BORDER};
                    border-radius: 6px;
                    font-size: 11.5px;
                    font-weight: normal;
                    padding: 4px 8px;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.08);
                    color: {COLOR_TEXT_PRIMARY};
                }}
            """)
            self.btn_subtab_screen.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(168, 85, 247, 0.16);
                    color: {COLOR_ACCENT_PURPLE};
                    border: 1.5px solid {COLOR_ACCENT_PURPLE};
                    border-radius: 6px;
                    font-size: 11.5px;
                    font-weight: bold;
                    padding: 4px 8px;
                }}
            """)

    def _on_subtab_switched(self, tab_type: str):
        self._current_subtab = tab_type
        if tab_type == "audio":
            self.btn_subtab_audio.setChecked(True)
            self.btn_subtab_screen.setChecked(False)
            self.sub_stack.setCurrentIndex(0)
        else:
            self.btn_subtab_audio.setChecked(False)
            self.btn_subtab_screen.setChecked(True)
            self.sub_stack.setCurrentIndex(1)
        self._update_subtab_button_styles()
        self._update_subtitle_preview()

    def _update_subtitle_preview(self):
        # Audio params
        _v = self.audio_font_slider.value() if hasattr(self, 'audio_font_slider') else self.config.get("audio_font_size")
        a_font = _v if _v is not None else self.config.get("font_size", 24)

        _v = (self.audio_opacity_slider.value() / 100.0) if hasattr(self, 'audio_opacity_slider') else self.config.get("audio_overlay_bg_opacity")
        a_op = _v if _v is not None else self.config.get("overlay_bg_opacity", 0.66)

        _v = self.audio_slider_stroke.value() if hasattr(self, 'audio_slider_stroke') else self.config.get("audio_subtitle_stroke_width")
        a_stroke = _v if _v is not None else self.config.get("subtitle_stroke_width", 0)

        _v = (self.audio_slider_spacing.value() / 10.0) if hasattr(self, 'audio_slider_spacing') else self.config.get("audio_letter_spacing")
        a_spacing = _v if _v is not None else float(self.config.get("letter_spacing", 0.0))

        if hasattr(self, 'audio_cb_show_original'):
            a_orig = self.audio_cb_show_original.isChecked()
        else:
            _v = self.config.get("audio_show_original")
            a_orig = _v if _v is not None else self.config.get("show_original", True)

        if hasattr(self, 'audio_cb_show_translated'):
            a_trans = self.audio_cb_show_translated.isChecked()
        else:
            _v = self.config.get("audio_show_translated")
            a_trans = _v if _v is not None else self.config.get("show_translated", True)

        if hasattr(self, 'audio_cb_show_badge'):
            a_badge = self.audio_cb_show_badge.isChecked()
        else:
            _v = self.config.get("audio_show_engine_badge")
            a_badge = _v if _v is not None else self.config.get("show_engine_badge", True)

        if hasattr(self, 'audio_cb_clean_box'):
            a_clean_box = self.audio_cb_clean_box.isChecked()
        else:
            _v = self.config.get("audio_clean_box")
            a_clean_box = _v if _v is not None else self.config.get("clean_box", True)

        if hasattr(self, 'audio_cb_clean_text'):
            a_clean_text = self.audio_cb_clean_text.isChecked()
        else:
            _v = self.config.get("audio_clean_text_mode")
            a_clean_text = _v if _v is not None else self.config.get("clean_text_mode", False)

        if hasattr(self, 'audio_cb_show_speaker'):
            a_speaker = self.audio_cb_show_speaker.isChecked()
        else:
            _v = self.config.get("audio_show_speaker")
            a_speaker = _v if _v is not None else self.config.get("show_speaker", True)

        # Screen params
        _v = self.screen_font_slider.value() if hasattr(self, 'screen_font_slider') else self.config.get("screen_font_size")
        s_font = _v if _v is not None else self.config.get("font_size", 24)

        _v = (self.screen_opacity_slider.value() / 100.0) if hasattr(self, 'screen_opacity_slider') else self.config.get("screen_overlay_bg_opacity")
        s_op = _v if _v is not None else self.config.get("overlay_bg_opacity", 0.66)

        _v = self.screen_slider_stroke.value() if hasattr(self, 'screen_slider_stroke') else self.config.get("screen_subtitle_stroke_width")
        s_stroke = _v if _v is not None else self.config.get("subtitle_stroke_width", 0)

        _v = (self.screen_slider_spacing.value() / 10.0) if hasattr(self, 'screen_slider_spacing') else self.config.get("screen_letter_spacing")
        s_spacing = _v if _v is not None else float(self.config.get("letter_spacing", 0.0))

        if hasattr(self, 'screen_cb_show_original'):
            s_orig = self.screen_cb_show_original.isChecked()
        else:
            _v = self.config.get("screen_show_original")
            s_orig = _v if _v is not None else self.config.get("show_original", True)

        if hasattr(self, 'screen_cb_show_translated'):
            s_trans = self.screen_cb_show_translated.isChecked()
        else:
            _v = self.config.get("screen_show_translated")
            s_trans = _v if _v is not None else self.config.get("show_translated", True)

        if hasattr(self, 'screen_cb_show_badge'):
            s_badge = self.screen_cb_show_badge.isChecked()
        else:
            _v = self.config.get("screen_show_engine_badge")
            s_badge = _v if _v is not None else self.config.get("show_engine_badge", True)

        if hasattr(self, 'screen_cb_clean_box'):
            s_clean_box = self.screen_cb_clean_box.isChecked()
        else:
            _v = self.config.get("screen_clean_box")
            s_clean_box = _v if _v is not None else True

        if hasattr(self, 'screen_cb_clean_text'):
            s_clean_text = self.screen_cb_clean_text.isChecked()
        else:
            _v = self.config.get("screen_clean_text_mode")
            s_clean_text = _v if _v is not None else False

        if hasattr(self, 'screen_cb_show_speaker'):
            s_speaker = self.screen_cb_show_speaker.isChecked()
        else:
            _v = self.config.get("screen_show_speaker")
            s_speaker = _v if _v is not None else self.config.get("show_speaker", True)

        # Readability preview shows the currently selected subtab's style
        is_audio = getattr(self, "_current_subtab", "audio") == "audio"
        cur_font = a_font if is_audio else s_font
        cur_op = a_op if is_audio else s_op
        cur_stroke = a_stroke if is_audio else s_stroke
        cur_spacing = a_spacing if is_audio else s_spacing
        cur_orig = a_orig if is_audio else s_orig
        cur_clean_box = a_clean_box if is_audio else s_clean_box

        if hasattr(self, 'preview_canvas'):
            self.preview_canvas.update_params(
                font_size=a_font,
                opacity=a_op,
                stroke_width=a_stroke,
                letter_spacing=a_spacing,
                show_original=a_orig,
                show_badge=a_badge,
                clean_box=a_clean_box,
                clean_text_mode=a_clean_text,
                show_speaker=a_speaker,
                show_translated=a_trans,
                screen_font_size=s_font,
                screen_opacity=s_op,
                screen_stroke_width=s_stroke,
                screen_letter_spacing=s_spacing,
                screen_show_original=s_orig,
                screen_show_badge=s_badge,
                screen_clean_box=s_clean_box,
                screen_clean_text_mode=s_clean_text,
                screen_show_speaker=s_speaker,
                screen_show_translated=s_trans
            )
        if hasattr(self, 'readability_widget'):
            self.readability_widget.update_params(
                font_size=cur_font,
                opacity=cur_op,
                stroke_width=cur_stroke,
                letter_spacing=cur_spacing,
                show_original=cur_orig,
                clean_box=cur_clean_box
            )

    # ----------------------------------------------------------------------
    # 7. 탭 5: 설정 빌더
    # ----------------------------------------------------------------------
    def _build_tab_settings(self) -> QWidget:
        container = QWidget()
        main_layout = QHBoxLayout(container)
        main_layout.setContentsMargins(0, 4, 0, 4)
        main_layout.setSpacing(10)

        # ======================================================================
        # 1열: [시작 옵션] (높이 컴팩트) & [설정 프리셋] (하단 확장)
        # ======================================================================
        col1_layout = QVBoxLayout()
        col1_layout.setSpacing(10)

        # 1) 시작 옵션 카드 (높이 컴팩트 조정)
        start_card = CardWidget()
        start_layout = QVBoxLayout(start_card)
        start_layout.setContentsMargins(14, 12, 14, 12)
        start_layout.setSpacing(8)

        st_title = QLabel()
        self._i18n(st_title, "startup")
        st_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        st_sub = QLabel()
        self._i18n(st_sub, "startup_sub")
        st_sub.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_SECONDARY};")
        start_layout.addWidget(st_title)
        start_layout.addWidget(st_sub)

        # 음성 번역 자동 시작
        a_row = QHBoxLayout()
        lbl_a = QLabel()
        self._i18n(lbl_a, "auto_audio")
        lbl_a.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_PRIMARY};")
        self.toggle_auto_audio = ModernToggle(active_color=COLOR_ACCENT_MINT)
        self.toggle_auto_audio.setChecked(self.config.get("auto_start_audio", False))
        self.toggle_auto_audio.toggled.connect(self.on_auto_start_audio_toggled)
        self.cb_auto_start_audio = self.toggle_auto_audio
        a_row.addWidget(lbl_a)
        a_row.addStretch(1)
        a_row.addWidget(self.toggle_auto_audio)
        start_layout.addLayout(a_row)

        # 화면 번역 자동 시작
        s_row = QHBoxLayout()
        lbl_s = QLabel()
        self._i18n(lbl_s, "auto_screen")
        lbl_s.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_PRIMARY};")
        self.toggle_auto_screen = ModernToggle(active_color=COLOR_ACCENT_PURPLE)
        self.toggle_auto_screen.setChecked(self.config.get("auto_start_screen", False))
        self.toggle_auto_screen.toggled.connect(self.on_auto_start_screen_toggled)
        self.cb_auto_start_screen = self.toggle_auto_screen
        s_row.addWidget(lbl_s)
        s_row.addStretch(1)
        s_row.addWidget(self.toggle_auto_screen)
        start_layout.addLayout(s_row)

        # GPU 모델 즉시 예열
        w_row = QHBoxLayout()
        lbl_w = QLabel()
        self._i18n(lbl_w, "gpu_warmup")
        lbl_w.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_PRIMARY};")
        self.toggle_gpu_warmup = ModernToggle(active_color=COLOR_ACCENT_CYAN)
        self.toggle_gpu_warmup.setChecked(self.config.get("gpu_warmup_on_startup", False))
        self.toggle_gpu_warmup.toggled.connect(self.on_gpu_warmup_toggled)
        self.cb_gpu_warmup = self.toggle_gpu_warmup
        w_row.addWidget(lbl_w)
        w_row.addStretch(1)
        w_row.addWidget(self.toggle_gpu_warmup)
        start_layout.addLayout(w_row)

        # 유튜브 자동 감지 및 도메인 사전 적용
        y_row = QHBoxLayout()
        lbl_y = QLabel()
        self._i18n(lbl_y, "youtube_detect")
        lbl_y.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_PRIMARY};")
        self.toggle_auto_youtube = ModernToggle(active_color=COLOR_ACCENT_PINK)
        has_gemini_init = bool(self.config.get("gemini_api_key", "").strip())
        init_yt_detect = self.config.get("auto_youtube_detect", False) and has_gemini_init
        if not has_gemini_init and self.config.get("auto_youtube_detect", False):
            self.config["auto_youtube_detect"] = False
        self.toggle_auto_youtube.setChecked(init_yt_detect)
        self.toggle_auto_youtube.toggled.connect(self.on_auto_youtube_detect_toggled)
        self.cb_auto_youtube_detect = self.toggle_auto_youtube
        y_row.addWidget(lbl_y)
        y_row.addStretch(1)
        y_row.addWidget(self.toggle_auto_youtube)
        start_layout.addLayout(y_row)

        # 유튜브 URL 직접 입력 및 사전 즉시 적용 컨테이너 (토글이 ON일 때만 가시화)
        self.yt_input_container = QWidget()
        yt_container_layout = QVBoxLayout(self.yt_input_container)
        yt_container_layout.setContentsMargins(0, 2, 0, 2)
        yt_container_layout.setSpacing(4)

        yt_input_row = QHBoxLayout()
        yt_input_row.setSpacing(6)
        self.edit_youtube_url = QLineEdit()
        self.edit_youtube_url.setPlaceholderText(tr("youtube_url_placeholder"))
        self.edit_youtube_url.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLOR_CARD_INNER};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border: 1px solid {COLOR_ACCENT_PINK};
            }}
        """)
        self.btn_apply_youtube_url = QPushButton()
        self._i18n(self.btn_apply_youtube_url, "apply_glossary")
        self.btn_apply_youtube_url.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_youtube_url.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(236, 72, 153, 0.15);
                color: {COLOR_ACCENT_PINK};
                border: 1px solid {COLOR_ACCENT_PINK};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(236, 72, 153, 0.3);
            }}
            QPushButton:disabled {{
                background-color: transparent;
                color: {COLOR_TEXT_MUTED};
                border-color: {COLOR_BORDER};
            }}
        """)
        self.btn_apply_youtube_url.clicked.connect(self.on_apply_youtube_url_clicked)
        self.edit_youtube_url.returnPressed.connect(self.on_apply_youtube_url_clicked)
        yt_input_row.addWidget(self.edit_youtube_url, 1)
        yt_input_row.addWidget(self.btn_apply_youtube_url)
        yt_container_layout.addLayout(yt_input_row)

        self.lbl_youtube_status = QLabel("")
        self.lbl_youtube_status.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_SECONDARY};")
        self.lbl_youtube_status.setVisible(False)
        self.lbl_youtube_status.setWordWrap(True)
        yt_container_layout.addWidget(self.lbl_youtube_status)

        start_layout.addWidget(self.yt_input_container)
        self.yt_input_container.setVisible(self.toggle_auto_youtube.isChecked())

        # 전체 화면 번역 전역 단축키 설정
        lbl_hk = QLabel()
        self._i18n(lbl_hk, "hotkey")
        lbl_hk.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_PRIMARY};")
        start_layout.addWidget(lbl_hk)

        hk_btn_row = QHBoxLayout()
        hk_btn_row.setSpacing(6)

        cur_hk = self.config.get("inplace_hotkey", "F4")
        self.btn_settings_hotkey = HotkeyCaptureButton(current_hotkey=cur_hk)
        self.btn_settings_hotkey.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_settings_hotkey.setToolTip(tr("hotkey_tooltip", key=cur_hk))
        self.btn_settings_hotkey.hotkey_changed.connect(self._on_inplace_hotkey_changed)
        self.btn_settings_hotkey.recording_state_changed.connect(self._on_hotkey_recording_state_changed)
        hk_btn_row.addWidget(self.btn_settings_hotkey, 1)

        self.btn_reset_hotkey = QPushButton()
        self._i18n(self.btn_reset_hotkey, "reset_default")
        self.btn_reset_hotkey.setToolTip(tr("tip_reset_hotkey"))
        self.btn_reset_hotkey.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_hotkey.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_CARD_INNER};
                color: {COLOR_TEXT_SECONDARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: #FFFFFF;
                border-color: #94A3B8;
            }}
        """)
        self.btn_reset_hotkey.clicked.connect(self._on_reset_hotkey_clicked)
        hk_btn_row.addWidget(self.btn_reset_hotkey)
        start_layout.addLayout(hk_btn_row)

        self.lbl_hotkey_status = QLabel(tr("hotkey_status", key=cur_hk))
        self.lbl_hotkey_status.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SECONDARY}; padding-left: 2px;")
        start_layout.addWidget(self.lbl_hotkey_status)

        # 문제 진단: 배포판은 콘솔 창이 없으므로 로그 파일 위치를 바로 열 수 있게 한다.
        log_row = QHBoxLayout()
        lbl_log = QLabel()
        self._i18n(lbl_log, "diagnostics")
        lbl_log.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_PRIMARY};")
        self.btn_open_logs = QPushButton()
        self._i18n(self.btn_open_logs, "open_logs")
        self.btn_open_logs.setToolTip(tr("tip_open_logs"))
        self.btn_open_logs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_logs.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_CARD_INNER};
                color: {COLOR_TEXT_SECONDARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: #FFFFFF;
                border-color: #94A3B8;
            }}
        """)
        self.btn_open_logs.clicked.connect(self.open_log_folder)
        log_row.addWidget(lbl_log)
        log_row.addStretch(1)
        log_row.addWidget(self.btn_open_logs)
        start_layout.addLayout(log_row)

        col1_layout.addWidget(start_card)

        # 2) 설정 프리셋 카드 (시작 옵션 하단 배치, 남은 공간 채움)
        preset_card = CardWidget()
        preset_layout = QVBoxLayout(preset_card)
        preset_layout.setContentsMargins(14, 12, 14, 12)
        preset_layout.setSpacing(8)

        pr_head = QHBoxLayout()
        pr_vbox = QVBoxLayout()
        pr_vbox.setSpacing(2)
        pr_title = QLabel()
        self._i18n(pr_title, "preset_section")
        pr_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        pr_sub = QLabel()
        self._i18n(pr_sub, "preset_section_sub")
        pr_sub.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_SECONDARY};")
        pr_vbox.addWidget(pr_title)
        pr_vbox.addWidget(pr_sub)
        pr_head.addLayout(pr_vbox)
        pr_head.addStretch(1)

        self.btn_save_preset = QPushButton()
        self._i18n(self.btn_save_preset, "save_current")
        self.btn_save_preset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_preset.setStyleSheet(f"""
            QPushButton {{
                background-color: #101728;
                color: {COLOR_ACCENT_CYAN};
                border: 1px solid {COLOR_ACCENT_CYAN};
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(56,189,248,0.2);
            }}
        """)
        self.btn_save_preset.clicked.connect(self.save_current_as_custom_preset)
        pr_head.addWidget(self.btn_save_preset)
        preset_layout.addLayout(pr_head)

        self.preset_scroll = PresetScrollArea()
        self.preset_scroll.setWidgetResizable(True)
        self.preset_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preset_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.preset_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                border: none;
                background-color: rgba(14, 21, 36, 0.5);
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background-color: #24324D;
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #38BDF8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        self.preset_container_widget = QWidget()
        self.preset_list_layout = QVBoxLayout(self.preset_container_widget)
        self.preset_list_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.preset_list_layout.setContentsMargins(0, 2, 8, 2)
        self.preset_list_layout.setSpacing(6)
        self.preset_scroll.setWidget(self.preset_container_widget)
        preset_layout.addWidget(self.preset_scroll, stretch=1)

        self._refresh_presets_ui()

        col1_layout.addWidget(preset_card, stretch=1)
        main_layout.addLayout(col1_layout, stretch=3)

        # ======================================================================
        # 2열: [음성인식] & [STT 모델] & [콘텐츠 템포] (세로 배치)
        # ======================================================================
        col2_layout = QVBoxLayout()
        col2_layout.setSpacing(10)

        # 1) 음성인식 카드 (STT 가속 디바이스)
        stt_dev_card = CardWidget()
        stt_dev_layout = QVBoxLayout(stt_dev_card)
        stt_dev_layout.setContentsMargins(14, 12, 14, 12)
        stt_dev_layout.setSpacing(8)

        stt_dev_title = QLabel()
        self._i18n(stt_dev_title, "stt_title")
        stt_dev_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        stt_dev_sub = QLabel()
        self._i18n(stt_dev_sub, "stt_sub")
        stt_dev_sub.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_SECONDARY};")
        stt_dev_layout.addWidget(stt_dev_title)
        stt_dev_layout.addWidget(stt_dev_sub)

        self.device_keys = ["cuda", "cpu", "groq", "deepgram"]
        self.stt_buttons = []
        stt_devs = [
            ("NVIDIA CUDA", "stt_desc_cuda", "cuda"),
            ("CPU", "stt_desc_cpu", "cpu"),
            ("Groq", "stt_desc_groq", "groq"),
            ("Deepgram", "stt_desc_deepgram", "deepgram"),
        ]
        cur_dev = self.config.get("device", "cpu")
        if self.config.get("stt_provider") in ("groq", "deepgram"):
            cur_dev = self.config.get("stt_provider")

        from src.cuda_utils import is_nvidia_gpu_present
        has_nvidia = is_nvidia_gpu_present()
        for title, desc_key, key in stt_devs:
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setChecked(key == cur_dev)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if key == "cuda" and not has_nvidia:
                desc = tr("stt_no_nvidia_desc")
                btn.setEnabled(False)
            else:
                desc = tr(desc_key)
            btn.setToolTip(desc)
            btn.setFixedHeight(32)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #101728;
                    border: 1px solid {COLOR_BORDER};
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: #1A243D;
                    border-color: #4A5568;
                }}
                QPushButton:checked {{
                    background-color: rgba(99,102,241,0.18);
                    border: 1px solid {COLOR_ACCENT_PURPLE};
                }}
            """)
            h = QHBoxLayout(btn)
            h.setContentsMargins(10, 0, 10, 0)
            lbl = QLabel(title)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lbl.setStyleSheet("color: #ECEFF1; font-size: 11px; font-weight: 500;")
            h.addWidget(lbl)
            h.addStretch(1)

            st_text, st_type = self._get_stt_badge_info(key)
            badge = create_status_badge(st_text, st_type)
            h.addWidget(badge)
            btn.badge_label = badge
            btn.title_label = lbl

            btn.clicked.connect(lambda _, k=key: self._on_stt_dev_selected(k))
            stt_dev_layout.addWidget(btn)
            self.stt_buttons.append((btn, key))

        col2_layout.addWidget(stt_dev_card)

        # 2) STT 모델 카드 (음성인식과 콘텐츠 템포 사이로 재배치)
        stt_model_card = CardWidget()
        stt_model_layout = QVBoxLayout(stt_model_card)
        stt_model_layout.setContentsMargins(14, 12, 14, 12)
        stt_model_layout.setSpacing(8)

        m_head = QHBoxLayout()
        m_vbox = QVBoxLayout()
        m_vbox.setSpacing(2)
        lbl_model_title = QLabel()
        self._i18n(lbl_model_title, "stt_model")
        lbl_model_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        self.lbl_model_sub = QLabel()
        self._i18n(self.lbl_model_sub, "stt_model_sub")
        self.lbl_model_sub.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_SECONDARY};")
        m_vbox.addWidget(lbl_model_title)
        m_vbox.addWidget(self.lbl_model_sub)
        m_head.addLayout(m_vbox)
        m_head.addStretch(1)

        self.btn_manage_stt = QPushButton()
        self._i18n(self.btn_manage_stt, "manage_stt")
        self.btn_manage_stt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_manage_stt.setStyleSheet(f"""
            QPushButton {{
                background-color: #101728;
                color: {COLOR_ACCENT_PURPLE};
                border: 1px solid {COLOR_ACCENT_PURPLE};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(99,102,241,0.2);
            }}
        """)
        self.btn_manage_stt.clicked.connect(self.open_stt_model_manager)
        m_head.addWidget(self.btn_manage_stt)
        stt_model_layout.addLayout(m_head)

        self.combo_model = NoWheelComboBox()
        self.combo_model.setIconSize(QSize(10, 10))
        self.combo_model.currentIndexChanged.connect(self.on_model_changed)
        stt_model_layout.addWidget(self.combo_model)

        self.lbl_stt_model_note = QLabel(self._get_stt_model_note_text())
        self.lbl_stt_model_note.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 10px;")
        self.lbl_stt_model_note.setWordWrap(True)
        stt_model_layout.addWidget(self.lbl_stt_model_note)

        self._populate_models()

        # 하위 호환성 (테스트 및 NoWheelComboBox 검증용 콤보박스)
        self.combo_device = NoWheelComboBox()
        self.combo_device.addItem("CUDA (NVIDIA GPU)", "cuda")
        self.combo_device.addItem("CPU", "cpu")
        self.combo_device.addItem("Groq Cloud", "groq")

        self.combo_trans_engine = NoWheelComboBox()
        self.combo_trans_engine.addItem("DeepL", "deepl")
        self.combo_trans_engine.addItem(tr("engine_google"), "google")
        self.combo_trans_engine.addItem("Gemini Flash", "gemini")
        self.combo_trans_engine.addItem("Groq Qwen 27B", "groq")
        self.combo_trans_engine.addItem(tr("engine_gemma"), "gemma")
        self.combo_trans_engine.addItem(tr("engine_exaone"), "exaone")
        self.combo_trans_engine.addItem(tr("engine_hymt"), "hymt")

        col2_layout.addWidget(stt_model_card)

        # 2) 콘텐츠 템포 카드 (2열 그리드 배열로 높이 최적화)
        tempo_card = CardWidget()
        tempo_layout = QVBoxLayout(tempo_card)
        tempo_layout.setContentsMargins(14, 12, 14, 12)
        tempo_layout.setSpacing(8)

        t_head_vbox = QVBoxLayout()
        t_head_vbox.setSpacing(2)
        lbl_tempo_title = QLabel()
        self._i18n(lbl_tempo_title, "content_tempo")
        lbl_tempo_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        self.lbl_tempo_title_tab4 = lbl_tempo_title
        self.tempo_card_tab4 = tempo_card
        self.lbl_tempo_sub = QLabel(tempo_scope_caption(self.config))
        self.lbl_tempo_sub.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_SECONDARY};")
        self.lbl_tempo_sub.setWordWrap(True)
        t_head_vbox.addWidget(lbl_tempo_title)
        t_head_vbox.addWidget(self.lbl_tempo_sub)
        tempo_layout.addLayout(t_head_vbox)

        # 2열 그리드 배치 (3행 x 2열)
        tempo_grid = QGridLayout()
        tempo_grid.setSpacing(8)

        self.tempo_buttons_tab4 = []
        cur_tempo_preset = self.config.get("content_tempo_preset", "smart")

        tempo_items = [
            ("smart", "🧠 스마트 자동", "로컬 STT 호흡·더빙 속도", 0, 0),
            ("youtube", "⚡ 유튜브 / 방송", "짧은 호흡, 빠른 더빙", 0, 1),
            ("interview", "🎙️ 인터뷰 / 대담", "대화 호흡 보존", 1, 0),
            ("movie", "🎬 영화 / 드라마", "BGM 둔감, 여운 보존", 1, 1),
            ("news", "📰 뉴스 / 발표", "또박또박한 전달", 2, 0),
            ("documentary", "🌿 다큐 / 강의", "긴 문장 완결", 2, 1),
        ]

        for key, title, desc, r, c in tempo_items:
            btn = QPushButton()
            self._i18n(btn, f"tempo_{key}")
            btn.setCheckable(True)
            btn.setChecked(key == cur_tempo_preset)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tr(f"tempo_{key}") if is_global() else desc)
            btn.setFixedHeight(32)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #101728;
                    color: {COLOR_TEXT_PRIMARY};
                    border: 1px solid {COLOR_BORDER};
                    border-radius: 6px;
                    text-align: left;
                    padding-left: 10px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: #1A243D;
                    border-color: #4A5568;
                }}
                QPushButton:checked {{
                    background-color: rgba(99,102,241,0.18);
                    border: 1px solid {COLOR_ACCENT_PURPLE};
                    color: #FFFFFF;
                    font-weight: bold;
                }}
            """)
            btn.clicked.connect(lambda _, k=key: self._on_tempo_btn_clicked_tab4(k))
            tempo_grid.addWidget(btn, r, c)
            self.tempo_buttons_tab4.append((btn, key))

        tempo_layout.addLayout(tempo_grid)
        tempo_layout.addStretch(1)

        # 하위 호환성용 NoWheelComboBox (비가시화 유지)
        self.combo_tempo_preset_tab4 = NoWheelComboBox()
        cur_t_idx = 0
        for i, (k, p) in enumerate(CONTENT_TEMPO_PRESETS.items()):
            self.combo_tempo_preset_tab4.addItem(p["short_name"], k)
            if k == cur_tempo_preset:
                cur_t_idx = i
        self.combo_tempo_preset_tab4.setCurrentIndex(cur_t_idx)
        self.combo_tempo_preset_tab4.currentIndexChanged.connect(self.on_tempo_preset_changed_tab4)
        self.combo_tempo_preset_tab4.hide()
        tempo_layout.addWidget(self.combo_tempo_preset_tab4)

        desc_text = tempo_preset_desc(cur_tempo_preset, self.config)
        self.lbl_tempo_desc_tab4 = QLabel(desc_text)
        self.lbl_tempo_desc_tab4.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 10px;")
        self.lbl_tempo_desc_tab4.setWordWrap(True)
        self.lbl_tempo_desc_tab4.hide()
        tempo_layout.addWidget(self.lbl_tempo_desc_tab4)

        self.lbl_tempo_note = QLabel(tempo_deepgram_notice(self.config))
        self.lbl_tempo_note.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 10px;")
        self.lbl_tempo_note.setWordWrap(True)
        tempo_layout.addWidget(self.lbl_tempo_note)

        col2_layout.addWidget(tempo_card, stretch=1)
        main_layout.addLayout(col2_layout, stretch=3)

        # ======================================================================
        # 3열: [번역 엔진] & [API 키 관리] (세로 배치)
        # ======================================================================
        col3_layout = QVBoxLayout()
        col3_layout.setSpacing(10)

        # 1) 번역 엔진 카드
        eng_card = CardWidget()
        eng_layout = QVBoxLayout(eng_card)
        eng_layout.setContentsMargins(14, 12, 14, 12)
        eng_layout.setSpacing(8)

        eng_title = QLabel()
        self._i18n(eng_title, "engine_title")
        eng_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        eng_sub = QLabel()
        self._i18n(eng_sub, "engine_sub")
        eng_sub.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_SECONDARY};")
        eng_layout.addWidget(eng_title)
        eng_layout.addWidget(eng_sub)

        # 온라인 (클라우드)
        lbl_online = QLabel()
        self._i18n(lbl_online, "online_cloud")
        lbl_online.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-size: 11px; font-weight: bold;")
        eng_layout.addWidget(lbl_online)

        online_grid = QGridLayout()
        online_grid.setSpacing(6)
        self.trans_engine_buttons = []
        cur_eng = self.config.get("translation_engine", "google")

        onlines = [
            ("DeepL", "deepl"),
            ("Google", "google"),
            ("Gemini Flash", "gemini"),
            ("Groq Qwen 27B", "groq"),
        ]
        for i, (name, k) in enumerate(onlines):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setChecked(k == cur_eng)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(32)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #101728;
                    border: 1px solid {COLOR_BORDER};
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: #1A243D;
                    border-color: #4A5568;
                }}
                QPushButton:checked {{
                    background-color: rgba(99,102,241,0.18);
                    border: 1px solid {COLOR_ACCENT_PURPLE};
                }}
            """)
            h = QHBoxLayout(btn)
            h.setContentsMargins(8, 0, 8, 0)
            lbl = QLabel(name)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lbl.setStyleSheet("color: #ECEFF1; font-size: 10.5px; font-weight: 500;")
            h.addWidget(lbl)
            h.addStretch(1)

            st_text, st_type = self._get_online_trans_badge_info(k)
            badge = create_status_badge(st_text, st_type)
            h.addWidget(badge)
            btn.badge_label = badge
            btn.title_label = lbl

            btn.clicked.connect(lambda _, ek=k: self._on_trans_engine_selected(ek))
            online_grid.addWidget(btn, i // 2, i % 2)
            self.trans_engine_buttons.append((btn, k))
        eng_layout.addLayout(online_grid)

        # 로컬 (내 PC / Ollama 실행)
        loc_head = QHBoxLayout()
        lbl_local = QLabel()
        self._i18n(lbl_local, "local_ai")
        lbl_local.setStyleSheet(f"color: {COLOR_ACCENT_MINT}; font-size: 11px; font-weight: bold;")
        self.btn_manage_llm = QPushButton()
        self._i18n(self.btn_manage_llm, "manage_llm")
        self.btn_manage_llm.setToolTip(tr("tip_manage_llm"))
        self.btn_manage_llm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_manage_llm.setStyleSheet(f"""
            QPushButton {{
                background-color: #101728;
                color: {COLOR_ACCENT_MINT};
                border: 1px solid {COLOR_ACCENT_MINT};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(16,185,129,0.2);
            }}
        """)
        self.btn_manage_llm.clicked.connect(self.open_llm_model_manager)
        loc_head.addWidget(lbl_local)
        loc_head.addStretch(1)
        loc_head.addWidget(self.btn_manage_llm)
        eng_layout.addLayout(loc_head)

        local_grid = QGridLayout()
        local_grid.setSpacing(6)
        locals_list = [
            ("TranslateGemma 4B", "gemma"),
            ("EXAONE 3.5 2.4B", "exaone"),
            ("EXAONE 3.5 7.8B", "exaone7b"),
            ("Tencent Hy-MT2 1.8B", "hymt"),
        ]
        for i, (name, k) in enumerate(locals_list):
            btn = QPushButton()
            btn.setCheckable(True)
            matched = (k == cur_eng) or (k == "exaone" and cur_eng in ["exaone", "exaone-3.5-2.4b"]) or (k == "exaone7b" and cur_eng in ["exaone7b", "exaone-3.5-7.8b"]) or (k == "gemma" and "gemma" in str(cur_eng).lower()) or (k == "hymt" and "hymt" in str(cur_eng).lower())
            btn.setChecked(matched)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(32)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #101728;
                    border: 1px solid {COLOR_BORDER};
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: #1A243D;
                    border-color: #4A5568;
                }}
                QPushButton:checked {{
                    background-color: rgba(16,185,129,0.18);
                    border: 1px solid {COLOR_ACCENT_MINT};
                }}
            """)
            h = QHBoxLayout(btn)
            h.setContentsMargins(8, 0, 8, 0)
            lbl = QLabel(name)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lbl.setStyleSheet("color: #ECEFF1; font-size: 10.5px; font-weight: 500;")
            h.addWidget(lbl)
            h.addStretch(1)

            st_text, st_type = self._get_local_trans_badge_info(k)
            badge = create_status_badge(st_text, st_type)
            h.addWidget(badge)
            btn.badge_label = badge
            btn.title_label = lbl

            btn.clicked.connect(lambda _, ek=k: self._on_trans_engine_selected(ek))
            local_grid.addWidget(btn, i // 2, i % 2)
            self.trans_engine_buttons.append((btn, k))
        eng_layout.addLayout(local_grid)
        eng_layout.addStretch(1)

        # 번역 엔진 카드 추가 (고정 높이 제약을 해제하여 하단 API 카드와의 겹침 원천 차단)
        col3_layout.addWidget(eng_card)

        # 2) API 키 관리 카드
        api_card = CardWidget()
        api_layout = QVBoxLayout(api_card)
        api_layout.setContentsMargins(14, 12, 14, 12)
        api_layout.setSpacing(8)

        api_title = QLabel()
        self._i18n(api_title, "api_title")
        api_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ECEFF1;")
        api_sub = QLabel()
        self._i18n(api_sub, "api_sub")
        api_sub.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_SECONDARY};")
        api_layout.addWidget(api_title)
        api_layout.addWidget(api_sub)

        def _make_api_header(title: str, display_addr: str, url: str) -> QHBoxLayout:
            h = QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            h.setAlignment(Qt.AlignmentFlag.AlignVCenter)

            lbl = QLabel(title)
            lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #ECEFF1; padding: 0px; margin: 0px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            h.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

            h.addStretch(1)

            link = QLabel(f'<a href="{url}" style="color: #38BDF8; text-decoration: none; font-size: 11px; font-weight: 500;">{display_addr} ↗</a>')
            link.setOpenExternalLinks(True)
            link.setTextFormat(Qt.TextFormat.RichText)
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.setStyleSheet("QLabel { color: #38BDF8; font-size: 11px; padding: 0px; margin: 0px; } QLabel:hover { color: #7DD3FC; text-decoration: underline; }")
            link.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            h.addWidget(link, alignment=Qt.AlignmentFlag.AlignVCenter)
            return h

        btn_eye_style = """
            QPushButton {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
            }
        """

        # DeepL
        api_layout.addLayout(_make_api_header("DeepL API Key", "deepl.com/pro-api", "https://www.deepl.com/pro-api"))
        d_row = QHBoxLayout()
        self.input_card_deepl = QLineEdit(self.config.get("deepl_api_key", ""))
        self.input_card_deepl.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_card_deepl.setPlaceholderText("DeepL API Key")
        self.input_card_deepl.textChanged.connect(lambda t: (self.config.update({"deepl_api_key": t.strip()}), self._refresh_all_status_badges()))
        self.input_card_deepl.editingFinished.connect(lambda: self.save_config_cb(self.config))
        btn_eye_d = QPushButton()
        btn_eye_d.setIcon(get_eye_icon(False))
        btn_eye_d.setIconSize(QSize(18, 18))
        btn_eye_d.setFixedSize(32, 28)
        btn_eye_d.setStyleSheet(btn_eye_style)
        btn_eye_d.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_eye_d.setToolTip(tr("show_password"))
        btn_eye_d.clicked.connect(lambda: self._toggle_echo_mode(self.input_card_deepl, btn_eye_d))
        d_row.addWidget(self.input_card_deepl, stretch=1)
        d_row.addWidget(btn_eye_d)
        api_layout.addLayout(d_row)

        # Gemini
        api_layout.addLayout(_make_api_header("Gemini Flash Key", "aistudio.google.com", "https://aistudio.google.com/app/apikey"))
        g_row = QHBoxLayout()
        self.input_card_gemini = QLineEdit(self.config.get("gemini_api_key", ""))
        self.input_card_gemini.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_card_gemini.setPlaceholderText("Google AI Studio Key")
        self.input_card_gemini.textChanged.connect(lambda t: (self.config.update({"gemini_api_key": t.strip()}), self._refresh_all_status_badges()))
        self.input_card_gemini.editingFinished.connect(lambda: self.save_config_cb(self.config))
        btn_eye_g = QPushButton()
        btn_eye_g.setIcon(get_eye_icon(False))
        btn_eye_g.setIconSize(QSize(18, 18))
        btn_eye_g.setFixedSize(32, 28)
        btn_eye_g.setStyleSheet(btn_eye_style)
        btn_eye_g.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_eye_g.setToolTip(tr("show_password"))
        btn_eye_g.clicked.connect(lambda: self._toggle_echo_mode(self.input_card_gemini, btn_eye_g))
        g_row.addWidget(self.input_card_gemini, stretch=1)
        g_row.addWidget(btn_eye_g)
        api_layout.addLayout(g_row)

        # Groq
        api_layout.addLayout(_make_api_header("Groq LPU Key", "console.groq.com", "https://console.groq.com/keys"))
        gr_row = QHBoxLayout()
        self.input_card_groq = QLineEdit(self.config.get("groq_api_key", ""))
        self.input_card_groq.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_card_groq.setPlaceholderText("Groq Cloud Key")
        self.input_card_groq.textChanged.connect(lambda t: (self.config.update({"groq_api_key": t.strip()}), self._refresh_all_status_badges()))
        self.input_card_groq.editingFinished.connect(lambda: self.save_config_cb(self.config))
        btn_eye_gr = QPushButton()
        btn_eye_gr.setIcon(get_eye_icon(False))
        btn_eye_gr.setIconSize(QSize(18, 18))
        btn_eye_gr.setFixedSize(32, 28)
        btn_eye_gr.setStyleSheet(btn_eye_style)
        btn_eye_gr.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_eye_gr.setToolTip(tr("show_password"))
        btn_eye_gr.clicked.connect(lambda: self._toggle_echo_mode(self.input_card_groq, btn_eye_gr))
        gr_row.addWidget(self.input_card_groq, stretch=1)
        gr_row.addWidget(btn_eye_gr)
        api_layout.addLayout(gr_row)

        # Deepgram
        api_layout.addLayout(_make_api_header("Deepgram Key", "console.deepgram.com", "https://console.deepgram.com/"))
        dg_row = QHBoxLayout()
        self.input_card_deepgram = QLineEdit(self.config.get("deepgram_api_key", ""))
        self.input_card_deepgram.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_card_deepgram.setPlaceholderText("Deepgram Cloud API Key")
        self.input_card_deepgram.textChanged.connect(lambda t: (self.config.update({"deepgram_api_key": t.strip()}), self._refresh_all_status_badges()))
        self.input_card_deepgram.editingFinished.connect(lambda: self.save_config_cb(self.config))
        btn_eye_dg = QPushButton()
        btn_eye_dg.setIcon(get_eye_icon(False))
        btn_eye_dg.setIconSize(QSize(18, 18))
        btn_eye_dg.setFixedSize(32, 28)
        btn_eye_dg.setStyleSheet(btn_eye_style)
        btn_eye_dg.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_eye_dg.setToolTip(tr("show_password"))
        btn_eye_dg.clicked.connect(lambda: self._toggle_echo_mode(self.input_card_deepgram, btn_eye_dg))
        dg_row.addWidget(self.input_card_deepgram, stretch=1)
        dg_row.addWidget(btn_eye_dg)
        api_layout.addLayout(dg_row)

        api_layout.addStretch(1)

        api_info = QLabel()
        self._i18n(api_info, "api_info")
        api_info.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 10px;")
        api_info.setWordWrap(True)
        api_layout.addWidget(api_info)

        # 2열 콘텐츠 템포 섹션 하단과 높이를 정확히 맞추기 위해 stretch=1 할당 (하단 빈 공간 완전 제거)
        col3_layout.addWidget(api_card, stretch=1)
        main_layout.addLayout(col3_layout, stretch=4)

        return container

    def open_log_folder(self):
        """로그(crash.log·stderr.log·stdout.log)가 저장되는 사용자 데이터 폴더를 탐색기로 연다."""
        try:
            from src.app_paths import roaming_data_dir
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            folder = roaming_data_dir()
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            return folder
        except Exception as error:
            print(f"[로그] 로그 폴더를 열 수 없습니다: {error}")
            return None

    def _toggle_echo_mode(self, line_edit: QLineEdit, btn: QPushButton = None):
        if line_edit.echoMode() == QLineEdit.EchoMode.Password:
            line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            if btn:
                btn.setIcon(get_eye_icon(True))
                btn.setToolTip(tr("hide_password"))
        else:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            if btn:
                btn.setIcon(get_eye_icon(False))
                btn.setToolTip(tr("show_password"))

    def _get_stt_badge_info(self, key: str) -> tuple:
        from src.llm_model_manager import LLMModelManager
        from src.stt_engine import is_cuda_installed
        if key == "cuda":
            if is_cuda_installed():
                return (tr("status_usable"), "ready")
            elif LLMModelManager.is_nvidia_gpu_present():
                return (tr("status_need_pack"), "need_key")
            return (tr("status_no_gpu"), "muted")
        elif key == "cpu":
            return (tr("status_immediate"), "ready")
        elif key == "groq":
            has_key = bool(self.config.get("groq_api_key", "").strip())
            return (tr("status_key_registered") if has_key else tr("need_key"), "ready" if has_key else "need_key")
        elif key == "deepgram":
            has_key = bool(self.config.get("deepgram_api_key", "").strip())
            return (tr("status_key_registered") if has_key else tr("need_key"), "ready" if has_key else "need_key")
        return (tr("ready_now"), "ready")

    def _get_online_trans_badge_info(self, key: str) -> tuple:
        if key == "google":
            return (tr("status_free_ready"), "ready")
        elif key == "deepl":
            has_key = bool(self.config.get("deepl_api_key", "").strip())
            return (tr("status_key_registered") if has_key else tr("need_key"), "ready" if has_key else "need_key")
        elif key == "gemini":
            has_key = bool(self.config.get("gemini_api_key", "").strip())
            return (tr("status_key_registered") if has_key else tr("need_key"), "ready" if has_key else "need_key")
        elif key == "groq":
            has_key = bool(self.config.get("groq_api_key", "").strip())
            return (tr("status_key_registered") if has_key else tr("need_key"), "ready" if has_key else "need_key")
        return (tr("ready_now"), "ready")

    def _get_local_trans_badge_info(self, key: str) -> tuple:
        is_ready = self._check_model_ready(key)
        if is_ready:
            return (tr("ready_now"), "ready")
        return (tr("need_download"), "need_dl")

    def _update_status_badge(self, b: QLabel, text: str, badge_type: str):
        if not b:
            return
        is_usable = badge_type in ("ready", "key_ok")
        color = "#10B981" if is_usable else "#EF4444"
        b.setPixmap(_make_status_circle_pixmap(color, 10))
        b.setToolTip(text)

    def _refresh_all_status_badges(self):
        if hasattr(self, 'stt_buttons'):
            for btn, key in self.stt_buttons:
                if hasattr(btn, 'badge_label'):
                    txt, btype = self._get_stt_badge_info(key)
                    self._update_status_badge(btn.badge_label, txt, btype)
        if hasattr(self, 'trans_engine_buttons'):
            for btn, key in self.trans_engine_buttons:
                if hasattr(btn, 'badge_label'):
                    if key in ("deepl", "google", "gemini", "groq"):
                        txt, btype = self._get_online_trans_badge_info(key)
                    else:
                        txt, btype = self._get_local_trans_badge_info(key)
                    self._update_status_badge(btn.badge_label, txt, btype)
        if hasattr(self, '_refresh_presets_ui'):
            self._refresh_presets_ui()

    def _sync_stt_buttons_ui(self):
        """현재 config의 실제 활성 STT 디바이스에 맞춰 버튼 체크 상태 원복"""
        stt_p = self.config.get("stt_provider", "local")
        cur_dev = stt_p if stt_p in ("groq", "deepgram") else self.config.get("device", "cuda")
        if hasattr(self, 'stt_buttons'):
            for btn, k in self.stt_buttons:
                btn.blockSignals(True)
                btn.setChecked(k == cur_dev)
                btn.blockSignals(False)

    def _show_no_nvidia_notice(self):
        tell(self, "msg_no_nvidia_title", "msg_no_nvidia")
        self._sync_stt_buttons_ui()

    def _on_stt_dev_selected(self, selected_key: str):
        if selected_key == "groq":
            has_key = bool(self.config.get("groq_api_key", "").strip())
            if not has_key:
                ret = ask(self, "msg_need_key_title", "msg_open_key_settings", name="Groq")
                self._sync_stt_buttons_ui()
                if ret == QMessageBox.StandardButton.Yes:
                    self.open_api_key_dialog()
                return
        elif selected_key == "deepgram":
            has_key = bool(self.config.get("deepgram_api_key", "").strip())
            if not has_key:
                ret = ask(self, "msg_need_key_title", "msg_open_key_settings", name="Deepgram")
                self._sync_stt_buttons_ui()
                if ret == QMessageBox.StandardButton.Yes:
                    self.open_api_key_dialog()
                return
        elif selected_key == "cuda":
            from src.llm_model_manager import LLMModelManager
            from src.stt_engine import is_cuda_installed

            # CUDA GPU 가속(cuBLAS 및 ctranslate2) 사용 가능 여부 확인
            if not is_cuda_installed():
                if not LLMModelManager.is_nvidia_gpu_present():
                    self._show_no_nvidia_notice()
                    return
                ret = ask(self, "msg_cuda_pack_title", "msg_cuda_pack")
                self._sync_stt_buttons_ui()
                if ret == QMessageBox.StandardButton.Yes:
                    self.open_llm_model_manager()
                return

        for btn, k in self.stt_buttons:
            btn.setChecked(k == selected_key)
        idx = self.device_keys.index(selected_key) if selected_key in self.device_keys else 0
        self.on_device_changed(idx)
        self._sync_all_pipeline_status()
        self.update_engine_status("ready", tr("status_device", name=selected_key.upper()))

    def _on_trans_engine_selected(self, selected_key: str):
        self.set_engine_by_key(selected_key)

    def _sync_all_pipeline_status(self):
        # 0. 출발어 / 도착어 칩 동기화
        src_code = self.config.get("source_lang", "auto")
        tgt_code = self.config.get("target_lang", "ko")

        src_raw = tr("source_lang_auto") if src_code == "auto" else UI_LANGUAGE_NAMES.get(src_code, src_code.upper())
        src_clean = src_raw.replace("🌐 ", "").strip()
        tgt_raw = UI_LANGUAGE_NAMES.get(tgt_code, tgt_code.upper())
        tgt_clean = tgt_raw.replace("🎯 ", "").strip()

        if getattr(self, 'chip_src_lang', None) is not None:
            self.chip_src_lang.setText(f"🌐 {src_clean} ▾")
            self.chip_src_lang.setToolTip(f"{tr('source_lang_label')}: {src_clean}")

        if getattr(self, 'chip_tgt_lang', None) is not None:
            self.chip_tgt_lang.setText(f"🎯 {tgt_clean} ▾")
            self.chip_tgt_lang.setToolTip(f"{tr('target_lang_label')}: {tgt_clean}")

        stt_p = self.config.get("stt_provider", "local")
        dev = self.config.get("device", "cuda")
        if stt_p == "deepgram":
            stt_txt = "Deepgram"
            cur_model = self.config.get("deepgram_model", "nova-3")
        elif stt_p == "groq":
            stt_txt = "Groq"
            cur_model = self.config.get("groq_model", "whisper-large-v3-turbo")
        else:
            stt_txt = dev.upper()
            default_stt = "small" if is_global() else "distil-small.en"
            cur_model = self.config.get("model_size", default_stt)
        short_model = cur_model.replace("whisper-", "")

        eng_key = self.config.get("translation_engine", "google")
        eng_names = {
            "deepl": "DeepL", "google": "Google", "gemini": "Gemini", "groq": "Groq Qwen",
            "gemma": "Gemma 4B", "exaone": "EXAONE 2.4B", "exaone7b": "EXAONE 7.8B",
            "hymt": "HY-MT 1.8B",
        }
        if eng_key.startswith("ollama:"):
            raw_tag = eng_key.split(":", 1)[1]
            tag_name = raw_tag.split(":")[0]
            if "7.8b" in tag_name.lower() or "7b" in tag_name.lower():
                eng_display = "EXAONE 7.8B"
            elif "exaone" in tag_name.lower():
                eng_display = "EXAONE 2.4B"
            elif "gemma" in tag_name.lower():
                eng_display = "Gemma 4B"
            elif "hy-mt" in tag_name.lower() or "hymt" in tag_name.lower():
                eng_display = "HY-MT 1.8B"
            else:
                eng_display = f"Ollama ({tag_name})"
        else:
            eng_display = eng_names.get(eng_key.lower(), eng_key.upper())

        cur_tempo = self.config.get("content_tempo_preset", "smart")
        tempo_info = CONTENT_TEMPO_PRESETS.get(cur_tempo, {})
        tempo_short = tempo_info.get("short_name", cur_tempo)

        if hasattr(self, 'chip_stt_dev'):
            self.chip_stt_dev.setText(f"🎙 {stt_txt} ▾")
            self.chip_stt_dev.setToolTip(tr("tip_stt_chip", stt=stt_txt))
        elif hasattr(self, 'chip_stt'):
            self.chip_stt.setText(f"🎙 {stt_txt}")

        from src.stt_model_manager import STTModelManager
        is_multi = STTModelManager.is_multilingual_model(cur_model, stt_p)
        cur_stt_lang = self.config.get("stt_language", "en") if is_multi else "en"
        stt_lang_map = {
            "auto": tr("lang_auto"),
            "ja": tr("lang_ja"),
            "en": tr("lang_en"),
            "zh": tr("lang_zh"),
            "ko": tr("lang_ko"),
        }
        lang_label = stt_lang_map.get(cur_stt_lang, UI_LANGUAGE_NAMES.get(cur_stt_lang, cur_stt_lang))
        lang_tag = f" ({lang_label})" if is_multi else ""

        if hasattr(self, 'chip_stt_model'):
            self.chip_stt_model.setText(f"🤖 {short_model}{lang_tag} ▾")
            self.chip_stt_model.setToolTip(
                tr("tip_stt_model_lang", model=cur_model, lang=lang_label)
                if is_multi else
                tr("tip_stt_model_nolang", model=cur_model)
            )

        if hasattr(self, 'chip_trans'):
            self.chip_trans.setText(f"🌐 {eng_display} ▾")
            self.chip_trans.setToolTip(tr("tip_engine_chip", engine=eng_display))

        if hasattr(self, 'lbl_tempo_sub'):
            self.lbl_tempo_sub.setText(tempo_scope_caption(self.config))
        if hasattr(self, 'lbl_tempo_note'):
            self.lbl_tempo_note.setText(tempo_deepgram_notice(self.config))
        if hasattr(self, 'chip_tempo'):
            clean_tempo = tempo_short
            for icon in ["🧠", "⚡", "📰", "🎙️", "🎙", "🎬", "🌿"]:
                clean_tempo = clean_tempo.replace(icon, "").strip()
            tempo_key = self.config.get("content_tempo_preset", "smart")
            tempo_label = tr(f"tempo_{tempo_key}")
            if tempo_label.startswith("tempo_"):
                tempo_label = clean_tempo
            self.chip_tempo.setText(f"⏱️ {tempo_label} ▾")
            if uses_local_tempo_vad(self.config):
                tempo_tip = tr("tip_tempo_local", tempo=tempo_label)
            else:
                tempo_tip = tr("tip_tempo_deepgram", tempo=tempo_label)
            self.chip_tempo.setToolTip(tempo_tip)

        if hasattr(self, 'chip_dub'):
            out_txt = self.config.get("dubbing_output_device", "default")
            out_name = tr("default_device") if out_txt == "default" else out_txt[:16]
            self.chip_dub.setText(tr("tip_dubbing_chip", name=out_name))
        self._refresh_tempo_controls_enabled()
        self._refresh_speaker_controls_enabled()
        self._refresh_quick_presets_ui()

    def _refresh_tempo_controls_enabled(self):
        """Deepgram은 서버 분절을 쓰므로 통역 템포 UI를 비활성처럼 표시한다."""
        enabled = uses_local_tempo_vad(self.config)
        muted = COLOR_TEXT_MUTED if not enabled else COLOR_TEXT_SECONDARY
        title_color = COLOR_TEXT_MUTED if not enabled else "#ECEFF1"

        if hasattr(self, "combo_tempo_preset"):
            self.combo_tempo_preset.setEnabled(enabled)
        if hasattr(self, "lbl_tempo_title_audio"):
            self.lbl_tempo_title_audio.setEnabled(enabled)
            self.lbl_tempo_title_audio.setStyleSheet(
                f"font-weight: bold; font-size: 12px; color: {title_color};"
            )
        if hasattr(self, "lbl_tempo_desc"):
            self.lbl_tempo_desc.setEnabled(enabled)
            if enabled:
                self.lbl_tempo_desc.setText(tempo_preset_desc(self.config.get("content_tempo_preset", "smart"), self.config))
            else:
                self.lbl_tempo_desc.setText(self._tempo_caption())
            self.lbl_tempo_desc.setStyleSheet(f"color: {muted}; font-size: 11px;")

        if hasattr(self, "tempo_card_tab4"):
            self.tempo_card_tab4.setEnabled(enabled)
        if hasattr(self, "lbl_tempo_title_tab4"):
            self.lbl_tempo_title_tab4.setStyleSheet(
                f"font-size: 13px; font-weight: bold; color: {title_color};"
            )
        if hasattr(self, "lbl_tempo_sub"):
            self.lbl_tempo_sub.setText(tempo_scope_caption(self.config))
            self.lbl_tempo_sub.setStyleSheet(f"font-size: 10px; color: {muted};")
        if hasattr(self, "lbl_tempo_note"):
            self.lbl_tempo_note.setText(tempo_deepgram_notice(self.config))
            self.lbl_tempo_note.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 10px;")

        if hasattr(self, "chip_tempo"):
            self.chip_tempo.setEnabled(enabled)
            self.chip_tempo.setCursor(
                Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor
            )
            self.chip_tempo.setStyleSheet(self._get_chip_style(COLOR_ACCENT_PINK, disabled=not enabled))
            if enabled:
                tempo_key = self.config.get("content_tempo_preset", "smart")
                tempo_label = tr(f"tempo_{tempo_key}")
                self.chip_tempo.setToolTip(tr("tip_tempo_local", tempo=tempo_label))
            else:
                self.chip_tempo.setToolTip(tr("tempo_ignored"))

    def _refresh_speaker_controls_enabled(self):
        """Deepgram 화자 분리는 서버가 담당하므로 로컬 분리 감도만 비활성으로 표시한다."""
        local_threshold = not (
            self.config.get("stt_provider") == "deepgram"
            and self.config.get("speaker_diarization_enabled", False)
        )
        if hasattr(self, "slider_speaker_threshold"):
            self.slider_speaker_threshold.setEnabled(local_threshold)
            if local_threshold:
                self.slider_speaker_threshold.setToolTip(tr("spk_similarity_guide"))
            else:
                self.slider_speaker_threshold.setToolTip(tr("tempo_ignored"))
        if hasattr(self, "lbl_speaker_threshold"):
            self.lbl_speaker_threshold.setEnabled(local_threshold)
        if hasattr(self, "lbl_speaker_threshold_num"):
            self.lbl_speaker_threshold_num.setEnabled(local_threshold)

    # ----------------------------------------------------------------------
    # 8. 핵심 비즈니스 로직 및 이벤트 핸들러
    # ----------------------------------------------------------------------
    def _update_level_meter(self, rms: float):
        level = min(1.0, rms * 15.0)
        if hasattr(self, 'segment_level_meter'):
            self.segment_level_meter.setLevel(level)

    @property
    def is_active(self):
        return getattr(self, '_is_audio_active', False)

    @is_active.setter
    def is_active(self, val):
        self._is_audio_active = bool(val)

    def _trigger_deferred_gpu_warmup(self):
        """시작 옵션에서 GPU 예열이 꺼져있을 경우, 번역 활성화 시점에 백그라운드 웜업 선제 구동"""
        cur_eng = self.config.get("translation_engine", "")
        if cur_eng in ("gemma", "exaone", "exaone7b", "hymt"):
            translator = None
            if self.stt_thread and hasattr(self.stt_thread, "translator"):
                translator = self.stt_thread.translator
            elif hasattr(self, "screen_worker") and self.screen_worker and hasattr(self.screen_worker, "translator"):
                translator = self.screen_worker.translator
            if translator and hasattr(translator, "preload_engine"):
                threading.Thread(target=translator.preload_engine, args=(cur_eng,), daemon=True).start()

    def _trigger_youtube_detection_on_start(self):
        """번역 시작 순간: 열려 있는 유튜브 영상을 비동기로 즉시 감지하고 사전을 백그라운드 생성 (자막은 지연 없이 즉시 개시)"""
        monitor = getattr(self, "youtube_monitor", None)
        if monitor and hasattr(monitor, "on_translation_started"):
            monitor.on_translation_started()

    def _sync_youtube_monitor_active_state(self):
        """오디오와 화면 번역이 둘 다 꺼지면 유튜브 감시 워커도 비활성화"""
        if not getattr(self, "_is_audio_active", False) and not getattr(self, "_is_screen_active", False):
            monitor = getattr(self, "youtube_monitor", None)
            if monitor and hasattr(monitor, "set_active"):
                monitor.set_active(False)

    def set_audio_active_state(self, is_active: bool):
        self._is_audio_active = is_active
        if is_active:
            if not self.config.get("gpu_warmup_on_startup", False):
                self._trigger_deferred_gpu_warmup()
            self._trigger_youtube_detection_on_start()
        else:
            self._sync_youtube_monitor_active_state()
        if self.dubbing_engine and hasattr(self.dubbing_engine, "set_source_active"):
            self.dubbing_engine.set_source_active("audio", is_active)
        if self.stt_thread and hasattr(self.stt_thread, 'set_paused_state'):
            self.stt_thread.set_paused_state(not is_active)
        if self.audio_thread:
            if hasattr(self.audio_thread, "set_paused_state"):
                self.audio_thread.set_paused_state(not is_active)
            elif hasattr(self.audio_thread, "paused"):
                self.audio_thread.paused = not is_active
            elif hasattr(self.audio_thread, "pause") and hasattr(self.audio_thread, "resume"):
                if is_active:
                    self.audio_thread.resume()
                else:
                    self.audio_thread.pause()
        if self.overlay and hasattr(self.overlay, "set_paused_state"):
            self.overlay.set_paused_state(not is_active)
        if hasattr(self, 'btn_toggle'):
            if is_active:
                self._i18n(self.btn_toggle, "audio_running")
            else:
                self._i18n(self.btn_toggle, "audio_start")
        if hasattr(self, 'btn_bottom_audio'):
            self.btn_bottom_audio.setChecked(is_active)
            if is_active:
                self._i18n(self.btn_bottom_audio, "pause")
                self.btn_bottom_audio.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                        color: #000000;
                        font-weight: bold;
                        font-size: 12px;
                        border: 1px solid #34D399;
                        border-radius: 6px;
                        padding: 4px 10px;
                        text-align: center;
                    }}
                    QPushButton:hover {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #34D399, stop:1 #10B981);
                    }}
                """)
                self.update_engine_status("ready", tr("status_audio_started"))
            else:
                self._i18n(self.btn_bottom_audio, "start_translation")
                self.btn_bottom_audio.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #4338CA);
                        color: #FFFFFF;
                        font-weight: bold;
                        font-size: 12px;
                        border: 1px solid #6366F1;
                        border-radius: 6px;
                        padding: 4px 10px;
                        text-align: center;
                    }}
                    QPushButton:hover {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #4F46E5);
                        border-color: #818CF8;
                    }}
                """)
                self.update_engine_status("paused", tr("status_audio_paused"))

    def set_screen_active_state(self, is_active: bool):
        self._is_screen_active = is_active
        self.config["screen_translate_enabled"] = is_active
        if is_active:
            if not self.config.get("gpu_warmup_on_startup", False):
                self._trigger_deferred_gpu_warmup()
            self._trigger_youtube_detection_on_start()
        else:
            self._sync_youtube_monitor_active_state()
        if self.dubbing_engine and hasattr(self.dubbing_engine, "set_source_active"):
            self.dubbing_engine.set_source_active("screen", is_active)
        if self.screen_overlay:
            if hasattr(self.screen_overlay, "set_paused_state"):
                self.screen_overlay.set_paused_state(not is_active)
            overlay_visible = (self.screen_overlay.is_visible()
                               if hasattr(self.screen_overlay, "is_visible")
                               else self.screen_overlay.isVisible())
            if is_active and self.config.get("screen_overlay_visible", True) and not overlay_visible:
                self.screen_overlay.show()
        if self.screen_worker:
            if hasattr(self.screen_worker, "update_config"):
                self.screen_worker.update_config(self.config)
            if hasattr(self.screen_worker, "set_paused_state"):
                self.screen_worker.set_paused_state(not is_active)
            elif hasattr(self.screen_worker, "is_paused"):
                self.screen_worker.is_paused = not is_active
            elif hasattr(self.screen_worker, "set_enabled"):
                self.screen_worker.set_enabled(is_active)
        if hasattr(self, 'btn_toggle_screen'):
            if is_active:
                self._i18n(self.btn_toggle_screen, "screen_stop")
            else:
                self._i18n(self.btn_toggle_screen, "screen_start")
        if hasattr(self, 'btn_bottom_screen'):
            self.btn_bottom_screen.setChecked(is_active)
            if is_active:
                self._i18n(self.btn_bottom_screen, "pause")
                self.btn_bottom_screen.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                        color: #000000;
                        font-weight: bold;
                        font-size: 12px;
                        border: 1px solid #34D399;
                        border-radius: 6px;
                        padding: 4px 10px;
                        text-align: center;
                    }}
                    QPushButton:hover {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #34D399, stop:1 #10B981);
                    }}
                """)
                self.update_engine_status("ready", tr("status_screen_started"))
            else:
                self._i18n(self.btn_bottom_screen, "start_translation")
                self.btn_bottom_screen.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #0369A1);
                        color: #FFFFFF;
                        font-weight: bold;
                        font-size: 12px;
                        border: 1px solid #38BDF8;
                        border-radius: 6px;
                        padding: 4px 10px;
                        text-align: center;
                    }}
                    QPushButton:hover {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0EA5E9, stop:1 #0284C7);
                        border-color: #7DD3FC;
                    }}
                """)
                self.update_engine_status("paused", tr("status_screen_paused"))

    def _update_dubbing_toggle_btn_ui(self):
        is_on = self.config.get("dubbing_enabled", False)
        if hasattr(self, 'btn_bottom_dubbing'):
            self.btn_bottom_dubbing.setChecked(is_on)
            if is_on:
                self._i18n(self.btn_bottom_dubbing, "pause")
                self.btn_bottom_dubbing.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                        color: #000000;
                        font-weight: bold;
                        font-size: 12px;
                        border: 1px solid #34D399;
                        border-radius: 6px;
                        padding: 4px 10px;
                        text-align: center;
                    }}
                    QPushButton:hover {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #34D399, stop:1 #10B981);
                    }}
                """)
            else:
                self._i18n(self.btn_bottom_dubbing, "start_dubbing")
                self.btn_bottom_dubbing.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #DB2777, stop:1 #BE185D);
                        color: #FFFFFF;
                        font-weight: bold;
                        font-size: 12px;
                        border: 1px solid #F472B6;
                        border-radius: 6px;
                        padding: 4px 10px;
                        text-align: center;
                    }}
                    QPushButton:hover {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #EC4899, stop:1 #DB2777);
                        border-color: #FB7185;
                    }}
                """)

    def toggle_translation(self):
        self.set_audio_active_state(not self.is_active)

    def toggle_screen_translation(self):
        cur = self.config.get("screen_translate_enabled", False)
        new_state = not cur
        self.set_screen_active_state(new_state)

    def toggle_dubbing(self):
        cur = self.config.get("dubbing_enabled", False)
        new_val = not cur
        self.config["dubbing_enabled"] = new_val
        if self.dubbing_engine:
            self.dubbing_engine.set_enabled(new_val)
        if hasattr(self, 'screen_worker') and self.screen_worker and hasattr(self.screen_worker, 'update_config'):
            self.screen_worker.update_config(self.config)
        if hasattr(self, 'stt_thread') and self.stt_thread and hasattr(self.stt_thread, 'update_config'):
            self.stt_thread.update_config(self.config)
        self._update_dubbing_toggle_btn_ui()
        self._sync_dubbing_overlay_buttons()
        self.save_config_cb(self.config)

    def _sync_dubbing_overlay_buttons(self):
        """오디오 및 화면 오버레이 창과 컨트롤 패널 토글 스위치 간의 양방향 실시간 동기화"""
        is_audio_dub = bool(self.config.get("dubbing_enabled", False) and self.config.get("dubbing_source_audio", True))
        is_screen_dub = bool(self.config.get("dubbing_enabled", False) and self.config.get("dubbing_source_screen", False))

        # 1. 컨트롤 패널 토글 스위치 UI 동기화
        if hasattr(self, 'toggle_dub_voice') and self.toggle_dub_voice:
            self.toggle_dub_voice.blockSignals(True)
            self.toggle_dub_voice.setChecked(is_audio_dub)
            self.toggle_dub_voice.blockSignals(False)

        if hasattr(self, 'toggle_dub_screen') and self.toggle_dub_screen:
            self.toggle_dub_screen.blockSignals(True)
            self.toggle_dub_screen.setChecked(is_screen_dub)
            self.toggle_dub_screen.blockSignals(False)

        # 2. 오버레이 창 더빙 아이콘 버튼 동기화
        if hasattr(self, 'overlay') and self.overlay and hasattr(self.overlay, 'update_dubbing_state'):
            self.overlay.update_dubbing_state(is_audio_dub)
        if hasattr(self, 'screen_overlay') and self.screen_overlay and hasattr(self.screen_overlay, 'update_dubbing_state'):
            self.screen_overlay.update_dubbing_state(is_screen_dub)

        self._update_dubbing_toggle_btn_ui()

    def toggle_audio_dubbing_from_overlay(self):
        """음성 번역 오버레이 헤더의 더빙 버튼 클릭 핸들러"""
        cur_active = bool(self.config.get("dubbing_enabled", False) and self.config.get("dubbing_source_audio", True))
        new_active = not cur_active
        if new_active:
            self.config["dubbing_enabled"] = True
            self.config["dubbing_source_audio"] = True
        else:
            self.config["dubbing_source_audio"] = False
            if not self.config.get("dubbing_source_screen", False):
                self.config["dubbing_enabled"] = False
        if self.dubbing_engine:
            self.dubbing_engine.set_enabled(self.config.get("dubbing_enabled", False))
            self.dubbing_engine.set_source_enabled("audio", self.config["dubbing_source_audio"])
        if hasattr(self, 'stt_thread') and self.stt_thread and hasattr(self.stt_thread, 'update_config'):
            self.stt_thread.update_config(self.config)
        self._update_dubbing_toggle_btn_ui()
        self._sync_dubbing_overlay_buttons()
        self.save_config_cb(self.config)

    def toggle_screen_dubbing_from_overlay(self):
        """화면 번역 오버레이 헤더의 더빙 버튼 클릭 핸들러"""
        cur_active = bool(self.config.get("dubbing_enabled", False) and self.config.get("dubbing_source_screen", False))
        new_active = not cur_active
        if new_active:
            self.config["dubbing_enabled"] = True
            self.config["dubbing_source_screen"] = True
        else:
            self.config["dubbing_source_screen"] = False
            if not self.config.get("dubbing_source_audio", True):
                self.config["dubbing_enabled"] = False
        if self.dubbing_engine:
            self.dubbing_engine.set_enabled(self.config.get("dubbing_enabled", False))
            self.dubbing_engine.set_source_enabled("screen", self.config["dubbing_source_screen"])
        if hasattr(self, 'screen_worker') and self.screen_worker and hasattr(self.screen_worker, 'update_config'):
            self.screen_worker.update_config(self.config)
        self._update_dubbing_toggle_btn_ui()
        self._sync_dubbing_overlay_buttons()
        self.save_config_cb(self.config)

    def on_auto_start_audio_toggled(self, checked: bool):
        self.config["auto_start_audio"] = checked
        self.save_config_cb(self.config)

    def on_auto_start_screen_toggled(self, checked: bool):
        self.config["auto_start_screen"] = checked
        self.save_config_cb(self.config)

    def on_auto_youtube_detect_toggled(self, checked: bool):
        if checked:
            has_gemini = bool(self.config.get("gemini_api_key", "").strip())
            if not has_gemini:
                ret = ask(self, "msg_need_key_title", "msg_open_key_settings", name="Gemini")
                if ret == QMessageBox.StandardButton.Yes:
                    self.open_api_key_dialog()

                has_gemini = bool(self.config.get("gemini_api_key", "").strip())
                if not has_gemini:
                    if hasattr(self, 'toggle_auto_youtube'):
                        self.toggle_auto_youtube.blockSignals(True)
                        self.toggle_auto_youtube.setChecked(False)
                        self.toggle_auto_youtube.blockSignals(False)
                    self.config["auto_youtube_detect"] = False
                    self.save_config_cb(self.config)
                    if hasattr(self, 'yt_input_container'):
                        self.yt_input_container.setVisible(False)
                    return

        self.config["auto_youtube_detect"] = checked
        self.save_config_cb(self.config)
        if hasattr(self, 'yt_input_container'):
            self.yt_input_container.setVisible(checked)

    def on_gpu_warmup_toggled(self, checked: bool):
        self.config["gpu_warmup_on_startup"] = checked
        self.save_config_cb(self.config)
        if checked and (getattr(self, "_is_audio_active", False) or getattr(self, "_is_screen_active", False)):
            self._trigger_deferred_gpu_warmup()

    def on_apply_youtube_url_clicked(self):
        if not hasattr(self, "edit_youtube_url"):
            return
        url = self.edit_youtube_url.text().strip()
        if not url:
            self._set_youtube_status_ui(False, tr("msg_youtube_url"))
            return

        from src.youtube_helper import extract_youtube_id
        vid = extract_youtube_id(url)
        if not vid:
            self._set_youtube_status_ui(False, tr("msg_youtube_bad"))
            return

        api_key = self.config.get("gemini_api_key", "").strip()
        if not api_key:
            ret = ask(self, "msg_need_key_title", "msg_open_key_settings", name="Gemini")
            if ret == QMessageBox.StandardButton.Yes:
                self.open_api_key_dialog()
            api_key = self.config.get("gemini_api_key", "").strip()
            if not api_key:
                self._set_youtube_status_ui(False, tr("msg_youtube_no_key"))
                return

        self.btn_apply_youtube_url.setEnabled(False)
        self.edit_youtube_url.setEnabled(False)
        self._set_youtube_status_ui(True, tr("msg_youtube_building"), is_loading=True)

        def _worker():
            try:
                # youtube_monitor 가 존재하면 중복 처리 방지
                monitor = getattr(self, "youtube_monitor", None)
                if monitor and hasattr(monitor, "last_video_id"):
                    monitor.last_video_id = vid

                from src.youtube_helper import fetch_youtube_full_data
                from src.pre_processor import GeminiPreProcessor

                yt_data = fetch_youtube_full_data(vid, source_lang=self.config.get("stt_language", "en"))
                title = yt_data.get("title", "") or f"YouTube Video ({vid})"
                has_transcript = yt_data.get("has_transcript", False)
                transcript = yt_data.get("transcript", "")

                api_key = self.config.get("gemini_api_key", "").strip()
                preprocessor = GeminiPreProcessor(api_key=api_key)

                src_lang = self.config.get("stt_language", "en")
                tgt_lang = str(self.config.get("target_lang") or self.config.get("target") or "ko").strip().lower().split("-")[0]
                if has_transcript and len(transcript) > 100:
                    ctx = preprocessor.analyze_full_script(transcript, title=title, source_lang=src_lang, target_lang=tgt_lang)
                else:
                    ctx = preprocessor.analyze_metadata(title, additional_topic=f"채널: {yt_data.get('author', '')}", source_lang=src_lang, target_lang=tgt_lang)

                if ctx and not ctx.is_empty():
                    # STT 워커 및 번역기에 즉시 사전 주입
                    if self.stt_thread and hasattr(self.stt_thread, "set_pre_context"):
                        self.stt_thread.set_pre_context(ctx)

                    # 오버레이 알림 시그널
                    if self.overlay and hasattr(self.overlay, "update_preview_signal"):
                        try:
                            self.overlay.update_preview_signal.emit(f"[{tr('yt_glossary_active')}] {title[:20]}...", "YouTube")
                        except Exception:
                            pass

                    msg = tr("yt_glossary_active_detail", title=title[:22], terms=len(ctx.glossary), fixes=len(ctx.phonetic_fix_map))
                    self.youtube_status_signal.emit(True, msg)
                else:
                    self.youtube_status_signal.emit(False, tr("yt_glossary_failed_key"))
            except Exception as e:
                self.youtube_status_signal.emit(False, tr("yt_glossary_failed_error", error=str(e)))

        threading.Thread(target=_worker, daemon=True, name="ManualYTPreprocessThread").start()

    def _on_youtube_manual_status_updated(self, success: bool, message: str):
        if hasattr(self, "btn_apply_youtube_url"):
            self.btn_apply_youtube_url.setEnabled(True)
        if hasattr(self, "edit_youtube_url"):
            self.edit_youtube_url.setEnabled(True)
        self._set_youtube_status_ui(success, message, is_loading=False)

    def _set_youtube_status_ui(self, success: bool, message: str, is_loading: bool = False):
        if not hasattr(self, "lbl_youtube_status"):
            return
        self.lbl_youtube_status.setVisible(True)
        self.lbl_youtube_status.setText(message)
        if is_loading:
            self.lbl_youtube_status.setStyleSheet(f"font-size: 10px; color: {COLOR_ACCENT_CYAN};")
        elif success:
            self.lbl_youtube_status.setStyleSheet(f"font-size: 10px; color: {COLOR_ACCENT_MINT};")
        else:
            self.lbl_youtube_status.setStyleSheet(f"font-size: 10px; color: {COLOR_ACCENT_PINK};")

    def on_speaker_diarization_toggled(self, checked: bool):
        self.config["speaker_diarization_enabled"] = checked
        if self.stt_thread:
            if hasattr(self.stt_thread, "update_config"):
                self.stt_thread.update_config(self.config)
            elif hasattr(self.stt_thread, "speaker_identifier") and self.stt_thread.speaker_identifier:
                self.stt_thread.speaker_identifier.is_enabled = checked
            identifier = getattr(self.stt_thread, 'speaker_identifier', None)
            if identifier:
                identifier.speaker_updated_callback = self.speaker_updated_signal.emit
        self._poll_speakers()
        self._refresh_speaker_controls_enabled()
        if self.overlay and hasattr(self.overlay, "set_speaker_diarization_enabled"):
            self.overlay.set_speaker_diarization_enabled(checked)
        if self.screen_overlay and hasattr(self.screen_overlay, "set_speaker_diarization_enabled"):
            self.screen_overlay.set_speaker_diarization_enabled(checked)
        self.save_config_cb(self.config)

    def on_reset_speakers_clicked(self):
        if self.stt_thread and hasattr(self.stt_thread, "speaker_identifier") and self.stt_thread.speaker_identifier:
            self.stt_thread.speaker_identifier.reset_speakers()
        self.config["speaker_aliases"] = {}
        self.config["speaker_mutes"] = {}
        self.config["speaker_dubbing_mutes"] = {}
        self.config["speaker_voices"] = {}
        self.config["speaker_alias_sources"] = {}
        self.save_config_cb(self.config)
        self.refresh_speaker_mgmt_ui(force=True)

    def on_tempo_preset_changed(self, idx: int):
        cur_data = self.combo_tempo_preset.itemData(idx)
        if cur_data and cur_data in CONTENT_TEMPO_PRESETS:
            self._apply_tempo_preset_key(cur_data, source="tab0")

    def on_tempo_preset_changed_tab4(self, idx: int):
        if hasattr(self, 'combo_tempo_preset_tab4'):
            cur_data = self.combo_tempo_preset_tab4.itemData(idx)
            if cur_data and cur_data in CONTENT_TEMPO_PRESETS:
                self._apply_tempo_preset_key(cur_data, source="tab4")

    def _on_tempo_btn_clicked_tab4(self, key: str):
        self._apply_tempo_preset_key(key, source="tab4_btn")

    def _apply_tempo_preset_key(self, cur_data: str, source: str = "programmatic"):
        if cur_data not in CONTENT_TEMPO_PRESETS:
            return
        self.config["content_tempo_preset"] = cur_data
        p = CONTENT_TEMPO_PRESETS[cur_data]
        desc = tempo_preset_desc(cur_data, self.config)

        # 1. Tab 0 동기화
        if hasattr(self, 'combo_tempo_preset') and source != "tab0":
            for i in range(self.combo_tempo_preset.count()):
                if self.combo_tempo_preset.itemData(i) == cur_data:
                    self.combo_tempo_preset.blockSignals(True)
                    self.combo_tempo_preset.setCurrentIndex(i)
                    self.combo_tempo_preset.blockSignals(False)
                    break
        if hasattr(self, 'lbl_tempo_desc'):
            self.lbl_tempo_desc.setText(desc)

        # 2. Tab 4 동기화 (버튼 그룹 & 콤보)
        if hasattr(self, 'tempo_buttons_tab4'):
            for btn, k in self.tempo_buttons_tab4:
                btn.setChecked(k == cur_data)
        if hasattr(self, 'combo_tempo_preset_tab4') and source != "tab4":
            for i in range(self.combo_tempo_preset_tab4.count()):
                if self.combo_tempo_preset_tab4.itemData(i) == cur_data:
                    self.combo_tempo_preset_tab4.blockSignals(True)
                    self.combo_tempo_preset_tab4.setCurrentIndex(i)
                    self.combo_tempo_preset_tab4.blockSignals(False)
                    break
        if hasattr(self, 'lbl_tempo_desc_tab4'):
            self.lbl_tempo_desc_tab4.setText(desc)

        # 3. 파이프라인 칩 동기화
        if hasattr(self, 'chip_tempo'):
            t_short = p.get("short_name", cur_data)
            clean_t = t_short
            for icon in ["🧠", "⚡", "📰", "🎙️", "🎙", "🎬", "🌿"]:
                clean_t = clean_t.replace(icon, "").strip()
            tempo_label = tr(f"tempo_{cur_data}")
            if tempo_label.startswith("tempo_"):
                tempo_label = clean_t
            self.chip_tempo.setText(f"⏱️ {tempo_label} ▾")

        if self.stt_thread:
            try:
                if hasattr(self.stt_thread, "apply_tempo_preset"):
                    self.stt_thread.apply_tempo_preset(cur_data)
                elif hasattr(self.stt_thread, "_apply_fixed_preset"):
                    self.stt_thread._apply_fixed_preset(cur_data)
            except Exception as e:
                print(f"[ControlPanel] 템포 프리셋 적용 주의: {e}")
        self.save_config_cb(self.config)
        self.update_engine_status("ready", tr("status_tempo_applied", name=p.get("name", cur_data)))

    def _on_tempo_status_updated(self, text: str):
        if hasattr(self, 'lbl_tempo_desc'):
            self.lbl_tempo_desc.setText(text)
        if hasattr(self, 'lbl_tempo_desc_tab4'):
            self.lbl_tempo_desc_tab4.setText(text)

    def on_speaker_threshold_changed(self, int_val: int):
        val = int_val / 100.0
        self.config["speaker_similarity_threshold"] = val
        if hasattr(self, 'lbl_speaker_threshold_num'):
            self.lbl_speaker_threshold_num.setText(str(int_val))
        if self.stt_thread and hasattr(self.stt_thread, "speaker_identifier") and self.stt_thread.speaker_identifier:
            self.stt_thread.speaker_identifier.threshold = val
            self.stt_thread.speaker_identifier.similarity_threshold = val
        self.save_config_cb(self.config)

    def on_speaker_max_count_changed(self, index: int):
        if not hasattr(self, 'combo_speaker_max_count'):
            return
        val = self.combo_speaker_max_count.currentData()
        if val is None:
            val = [2, 3, 4, 8][min(max(0, index), 3)]
        self.config["speaker_max_count"] = int(val)
        if self.stt_thread and hasattr(self.stt_thread, "speaker_identifier") and self.stt_thread.speaker_identifier:
            self.stt_thread.speaker_identifier.apply_max_speakers(int(val))
        self.refresh_speaker_mgmt_ui(force=True)
        self.save_config_cb(self.config)

    def on_ocr_auto_mapping_toggled(self, checked: bool):
        self.config["speaker_ocr_auto_mapping"] = checked
        identifier = getattr(self.stt_thread, 'speaker_identifier', None)
        if identifier:
            identifier.ocr_auto_mapping = checked
        self.save_config_cb(self.config)

    def _selected_speakers(self):
        return [name for name, checkbox in getattr(self, 'speaker_selection_checkboxes', {}).items()
                if checkbox.isChecked()]

    def on_translate_selected_speakers(self):
        identifier = getattr(self.stt_thread, 'speaker_identifier', None)
        for name in self._selected_speakers():
            self.config.setdefault("speaker_mutes", {})[name] = False
            if identifier:
                identifier.set_speaker_muted(name, False)
        self.refresh_speaker_mgmt_ui(force=True)
        self.save_config_cb(self.config)

    def on_dub_selected_speakers(self):
        for name in self._selected_speakers():
            self.config.setdefault("speaker_dubbing_mutes", {})[name] = False
        self.refresh_speaker_mgmt_ui(force=True)
        self.save_config_cb(self.config)

    def on_unmute_all_speakers(self):
        self.config["speaker_mutes"] = {}
        if self.stt_thread and hasattr(self.stt_thread, "speaker_identifier") and self.stt_thread.speaker_identifier:
            self.stt_thread.speaker_identifier.speaker_mutes = {}
        self.refresh_speaker_mgmt_ui(force=True)
        self.save_config_cb(self.config)

    def on_mute_all_speakers(self):
        if self.stt_thread and hasattr(self.stt_thread, "speaker_identifier") and self.stt_thread.speaker_identifier:
            speakers = self.stt_thread.speaker_identifier.get_all_known_speakers()
            for s in speakers:
                raw = s.get("raw_name")
                if raw:
                    self.config.setdefault("speaker_mutes", {})[raw] = True
            self.stt_thread.speaker_identifier.speaker_mutes = dict(self.config["speaker_mutes"])
        self.refresh_speaker_mgmt_ui(force=True)
        self.save_config_cb(self.config)

    def on_dub_all_speakers(self):
        self.config["speaker_dubbing_mutes"] = {}
        self.refresh_speaker_mgmt_ui(force=True)
        self.save_config_cb(self.config)

    def on_dubbing_volume_changed(self, val):
        self.config["dubbing_volume"] = val
        if hasattr(self, 'lbl_dubbing_vol_val'):
            self.lbl_dubbing_vol_val.setText(f"{val}%")
        if self.dubbing_engine:
            self.dubbing_engine.volume = val
        self.save_config_cb(self.config)

    def on_original_volume_changed(self, val):
        self.config["original_volume"] = val
        if hasattr(self, 'lbl_original_vol_val'):
            self.lbl_original_vol_val.setText(f"{val}%")
        if hasattr(self, 'ducking_manager') and self.ducking_manager:
            if hasattr(self.ducking_manager, 'set_original_volume'):
                self.ducking_manager.set_original_volume(val)
            elif hasattr(self.ducking_manager, 'set_normal_volume'):
                self.ducking_manager.set_normal_volume(val)
        self.save_config_cb(self.config)

    def on_audio_ducking_toggled(self, checked):
        self.config["audio_ducking_enabled"] = checked
        if hasattr(self, 'slider_ducking_vol'):
            self.slider_ducking_vol.setEnabled(checked)
        if hasattr(self, 'lbl_att_title'):
            self.lbl_att_title.setEnabled(checked)
        if hasattr(self, 'lbl_att_val'):
            self.lbl_att_val.setEnabled(checked)
        if hasattr(self, 'ducking_manager') and self.ducking_manager:
            self.ducking_manager.set_ducking_enabled(checked)
        self.save_config_cb(self.config)

    def on_ducking_volume_changed(self, val):
        self.config["audio_ducking_volume"] = val
        if hasattr(self, 'lbl_att_val'):
            self.lbl_att_val.setText(f"{val}%")
        elif hasattr(self, 'lbl_duck_val'):
            self.lbl_duck_val.setText(f"{val}%")
        if hasattr(self, 'ducking_manager') and self.ducking_manager:
            self.ducking_manager.set_ducking_volume(val)
        self.save_config_cb(self.config)

    def on_dubbing_speed_changed(self, idx):
        spd = self.combo_dubbing_speed.itemData(idx)
        if spd:
            self.config["dubbing_speed"] = spd
            if hasattr(self, 'lbl_spd_val'):
                self.lbl_spd_val.setText(spd)
            if self.dubbing_engine:
                self.dubbing_engine.speed = spd
            self.save_config_cb(self.config)

    def on_dubbing_source_audio_toggled(self, checked):
        self.config["dubbing_source_audio"] = checked
        if checked:
            self.config["dubbing_enabled"] = True
        else:
            if not self.config.get("dubbing_source_screen", False):
                self.config["dubbing_enabled"] = False
        if self.dubbing_engine:
            self.dubbing_engine.set_enabled(self.config.get("dubbing_enabled", False))
            self.dubbing_engine.set_source_enabled("audio", checked)
        if hasattr(self, 'stt_thread') and self.stt_thread and hasattr(self.stt_thread, 'update_config'):
            self.stt_thread.update_config(self.config)
        self._sync_dubbing_overlay_buttons()
        self.save_config_cb(self.config)

    def on_dubbing_source_screen_toggled(self, checked):
        self.config["dubbing_source_screen"] = checked
        if checked:
            self.config["dubbing_enabled"] = True
        else:
            if not self.config.get("dubbing_source_audio", True):
                self.config["dubbing_enabled"] = False
        if self.dubbing_engine:
            self.dubbing_engine.set_enabled(self.config.get("dubbing_enabled", False))
            self.dubbing_engine.set_source_enabled("screen", checked)
        if hasattr(self, 'screen_worker') and self.screen_worker and hasattr(self.screen_worker, 'update_config'):
            self.screen_worker.update_config(self.config)
        self._sync_dubbing_overlay_buttons()
        self.save_config_cb(self.config)

    def _populate_dubbing_voice_combos(self):
        if not hasattr(self, 'combo_dub_voice_audio') or not hasattr(self, 'combo_dub_voice_screen'):
            return
        tgt_code = str(self.config.get("target_lang", "ko")).strip().lower().split("-")[0]
        from src.dubbing_engine import get_available_voices
        voices = get_available_voices(tgt_code)

        cur_audio_v = self.config.get("dubbing_voice_audio", "auto")
        cur_screen_v = self.config.get("dubbing_voice_screen", "auto")

        self.combo_dub_voice_audio.blockSignals(True)
        self.combo_dub_voice_audio.clear()
        for v_id, v_label in voices:
            self.combo_dub_voice_audio.addItem(v_label, v_id)
        idx_a = self.combo_dub_voice_audio.findData(cur_audio_v)
        self.combo_dub_voice_audio.setCurrentIndex(max(0, idx_a))
        self.combo_dub_voice_audio.blockSignals(False)

        self.combo_dub_voice_screen.blockSignals(True)
        self.combo_dub_voice_screen.clear()
        for v_id, v_label in voices:
            self.combo_dub_voice_screen.addItem(v_label, v_id)
        idx_s = self.combo_dub_voice_screen.findData(cur_screen_v)
        self.combo_dub_voice_screen.setCurrentIndex(max(0, idx_s))
        self.combo_dub_voice_screen.blockSignals(False)

    def on_dubbing_voice_audio_changed(self, idx: int):
        if idx < 0 or not hasattr(self, 'combo_dub_voice_audio'):
            return
        v_id = self.combo_dub_voice_audio.itemData(idx)
        self.config["dubbing_voice_audio"] = v_id
        if self.dubbing_engine and hasattr(self.dubbing_engine, 'config'):
            self.dubbing_engine.config["dubbing_voice_audio"] = v_id
        self.save_config_cb(self.config)

    def on_dubbing_voice_screen_changed(self, idx: int):
        if idx < 0 or not hasattr(self, 'combo_dub_voice_screen'):
            return
        v_id = self.combo_dub_voice_screen.itemData(idx)
        self.config["dubbing_voice_screen"] = v_id
        if self.dubbing_engine and hasattr(self.dubbing_engine, 'config'):
            self.dubbing_engine.config["dubbing_voice_screen"] = v_id
        self.save_config_cb(self.config)

    def on_dubbing_interrupt_toggled(self, checked):
        self.config["dubbing_interrupt"] = checked
        if self.dubbing_engine:
            self.dubbing_engine.interrupt = checked
        self.save_config_cb(self.config)

    def on_dubbing_echo_cancel_toggled(self, checked):
        self.config["dubbing_echo_cancellation"] = checked
        if self.dubbing_engine:
            self.dubbing_engine.echo_cancellation = checked
        self.save_config_cb(self.config)

    def on_reset_sync_clicked(self):
        if self.dubbing_engine:
            self.dubbing_engine.clear_queue()
        if hasattr(self, 'ducking_manager') and self.ducking_manager:
            self.ducking_manager.restore_immediately()

    def _poll_audio_sources(self):
        """백그라운드 비동기 워커를 통해 주기적으로 오디오 프로세스 변화를 감지하여 콤보박스를 갱신 (팝업이 열려있지 않을 때만)"""
        if not hasattr(self, 'combo_audio_cap_dev'):
            return
        # 팝업이 펼쳐져 있으면 사용자의 마우스 선택을 방해하지 않음
        view = self.combo_audio_cap_dev.view()
        if view and view.isVisible():
            return
        self._async_populate_audio_devices()

    def _async_populate_audio_devices(self):
        """GUI 메인 스레드 멈칫(Micro-stutter)을 원천 차단하기 위해 백그라운드 스레드에서 psutil/COM 세션 쿼리 수행"""
        if getattr(self, '_audio_query_in_progress', False):
            return
        self._audio_query_in_progress = True
        cur_cap = self.config.get("audio_capture_device", "default")

        def _worker():
            try:
                from src.audio_capture import AudioLoopbackCapture
                sources = AudioLoopbackCapture.get_available_capture_sources(current_selected=cur_cap)
            except Exception:
                sources = [{"id": "default", "type": "device", "name": tr("audio_default_system")}]
            finally:
                self._audio_query_in_progress = False
            self.audio_sources_updated_signal.emit(sources)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_audio_sources_ready(self, sources):
        """비동기 백그라운드 쿼리 완료 시 메인 스레드에서 안전하게 UI 콤보박스 갱신"""
        if not hasattr(self, 'combo_audio_cap_dev'):
            return
        view = self.combo_audio_cap_dev.view()
        if view and view.isVisible():
            return

        existing_ids = [self.combo_audio_cap_dev.itemData(i) for i in range(self.combo_audio_cap_dev.count())]
        new_ids = [s["id"] for s in sources]
        if existing_ids == new_ids:
            return

        cur_cap = self.config.get("audio_capture_device", "default")
        self.combo_audio_cap_dev.blockSignals(True)
        self.combo_audio_cap_dev.clear()
        for src in sources:
            self.combo_audio_cap_dev.addItem(src["name"], src["id"])

        idx_cap = self.combo_audio_cap_dev.findData(cur_cap)
        if idx_cap >= 0:
            self.combo_audio_cap_dev.setCurrentIndex(idx_cap)
        else:
            self.combo_audio_cap_dev.setCurrentIndex(0)
        self.combo_audio_cap_dev.blockSignals(False)

    def _populate_audio_devices(self, silent=False):
        if not hasattr(self, 'combo_audio_cap_dev') or not hasattr(self, 'combo_dub_out_dev'):
            return

        cur_cap = self.config.get("audio_capture_device", "default")
        cur_dub = self.config.get("dubbing_output_device", "default")

        # 1. 캡처 소스 목록 조회 (무설치 앱 + 활성 오디오 세션 프로세스 + 물리 장치)
        try:
            from src.audio_capture import AudioLoopbackCapture
            sources = AudioLoopbackCapture.get_available_capture_sources(current_selected=cur_cap)
        except Exception:
            sources = [{"id": "default", "type": "device", "name": f"🔊 {tr('audio_default')}"}]

        # 변경 사항이 없으면 UI 재구성을 건너뛰어 깜빡임 방지 (silent=True일 때)
        if silent:
            existing_ids = [self.combo_audio_cap_dev.itemData(i) for i in range(self.combo_audio_cap_dev.count())]
            new_ids = [s["id"] for s in sources]
            if existing_ids == new_ids:
                return

        self.combo_audio_cap_dev.blockSignals(True)
        self.combo_audio_cap_dev.clear()
        for src in sources:
            self.combo_audio_cap_dev.addItem(src["name"], src["id"])

        idx_cap = self.combo_audio_cap_dev.findData(cur_cap)
        if idx_cap >= 0:
            self.combo_audio_cap_dev.setCurrentIndex(idx_cap)
        else:
            self.combo_audio_cap_dev.setCurrentIndex(0)
        self.combo_audio_cap_dev.blockSignals(False)

        # 2. 더빙 출력 장치 (물리 스피커) - silent가 아닐 때만 갱신
        if not silent:
            self.combo_dub_out_dev.blockSignals(True)
            self.combo_dub_out_dev.clear()
            self.combo_dub_out_dev.addItem(f"🔊 {tr('audio_default')}", "default")
            try:
                import soundcard as sc
                for spk in sc.all_speakers():
                    self.combo_dub_out_dev.addItem(f"🔊 {spk.name}", spk.name)
            except Exception:
                pass

            idx_dub = self.combo_dub_out_dev.findData(cur_dub)
            if idx_dub >= 0:
                self.combo_dub_out_dev.setCurrentIndex(idx_dub)
            else:
                self.combo_dub_out_dev.setCurrentIndex(0)
            self.combo_dub_out_dev.blockSignals(False)

    def on_audio_capture_device_changed(self, index):
        dev = self.combo_audio_cap_dev.itemData(index)
        if dev:
            self.config["audio_capture_device"] = dev
            if self.audio_thread:
                try:
                    if hasattr(self.audio_thread, "set_capture_device"):
                        self.audio_thread.set_capture_device(dev)
                    elif hasattr(self.audio_thread, "switch_device"):
                        self.audio_thread.switch_device(dev)
                except Exception as e:
                    print(f"[Audio] 캡처 장치 변경 예외: {e}")
            self.save_config_cb(self.config)


    def on_dubbing_output_device_changed(self, index):
        dev = self.combo_dub_out_dev.itemData(index)
        if dev:
            self.config["dubbing_output_device"] = dev
            if self.dubbing_engine:
                self.dubbing_engine.output_device = dev
            self.save_config_cb(self.config)
            self._sync_all_pipeline_status()

    # --- 자막 및 화자 이벤트 수신 ---
    def _on_audio_subtitle_received(self, orig, trans, engine):
        if not self.is_active:
            return
        if hasattr(self, 'lbl_live_orig'):
            self.lbl_live_orig.setText(orig)
        if hasattr(self, 'lbl_live_trans'):
            self.lbl_live_trans.setText(trans)
        speaker = ""
        if self.stt_thread and hasattr(self.stt_thread, 'last_detected_speaker'):
            speaker = getattr(self.stt_thread, 'last_detected_speaker', '') or ""
        is_audio_dub = bool(self.config.get("dubbing_enabled", False) and self.config.get("dubbing_source_audio", True))
        self.subtitle_history.add_entry(
            source="audio",
            trans_text=trans,
            orig_text=orig,
            speaker=speaker,
            engine=engine,
            dub_status="waiting" if is_audio_dub else "none"
        )
        self.subtitle_entry_signal.emit(None)
        clean_trans = trans.strip() if trans else ""
        self.update_engine_status("translating", tr("status_voice_line", engine=engine, text=clean_trans))

    def _on_screen_subtitle_received(self, orig, trans, engine, roi_idx=0):
        if not self._is_screen_active and not str(engine).startswith("즉시·"):
            return
        is_screen_dub = bool(self.config.get("dubbing_enabled", False) and self.config.get("dubbing_source_screen", True))
        self.subtitle_history.add_entry(
            source="screen",
            trans_text=trans,
            orig_text=orig,
            speaker=f"ROI {roi_idx + 1}" if roi_idx is not None else "",
            engine=engine,
            region_idx=roi_idx if roi_idx is not None else 0,
            dub_status="waiting" if is_screen_dub else "none"
        )
        self.subtitle_entry_signal.emit(None)
        clean_trans = trans.strip() if trans else ""
        self.update_engine_status("translating", tr("status_screen_line", engine=engine, text=clean_trans))

    def _on_dubbing_playback_received(self, text, speaker=None, orig_text=None, source="audio", voice=None, speed=None, region_idx=0):
        self.subtitle_history.update_or_add_dubbing(
            dub_text=text,
            speaker=speaker or "",
            orig_text=orig_text or "",
            source=source or "dubbing",
            voice=voice or "",
            speed=speed or "+0%",
            region_idx=region_idx or 0
        )
        self.subtitle_entry_signal.emit(None)

    def _on_new_subtitle_received_gui(self, entry=None):
        if not self.isVisible() or getattr(self, '_skip_sub_debounce', False) or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self._do_debounced_subtitle_refresh()
            return

        # 라이브 GUI: 카운트 배지 및 미니 프리뷰는 즉시 갱신 (0.01ms), 무거운 Full HTML 리치 텍스트만 디바운스
        if hasattr(self, 'lbl_sub_count'):
            try:
                total_cnt = self.subtitle_history.count()
                filter_mode = self.combo_sub_filter.currentData() if hasattr(self, 'combo_sub_filter') else "all"
                search_kw = self.input_sub_search.text().strip() if hasattr(self, 'input_sub_search') else ""
                if (filter_mode and filter_mode != "all") or search_kw:
                    filtered_len = len(self.subtitle_history.get_entries(source_filter=filter_mode, keyword=search_kw))
                    self._i18n(self.lbl_sub_count, "count_filtered", shown=filtered_len, total=total_cnt)
                else:
                    self._i18n(self.lbl_sub_count, "count_total", total=total_cnt)
            except Exception:
                pass
        self._update_mini_chat()

        if hasattr(self, '_sub_refresh_timer') and self._sub_refresh_timer:
            self._sub_refresh_timer.start(200)
        else:
            self.refresh_subtitle_view()

    def _do_debounced_subtitle_refresh(self):
        try:
            self.refresh_subtitle_view()
            self._update_mini_chat()
        except Exception:
            pass



    def _update_mini_chat(self):
        if not hasattr(self, 'screen_dialogue_table'):
            return
        try:
            rows = recent_screen_dialogues(self.subtitle_history.get_entries(source_filter="screen"))
            table = self.screen_dialogue_table
            table.setUpdatesEnabled(False)
            table.setRowCount(2)
            for row_index in range(2):
                table.setRowHeight(row_index, 42)
                if row_index < len(rows):
                    speaker, original, translated = rows[row_index]
                    prefix = f"[{speaker}] " if speaker else ""
                    values = (prefix + (original or "—"), prefix + (translated or "—"))
                elif not rows and row_index == 0:
                    values = (tr("screen_dialogue_placeholder"), "")
                else:
                    values = ("", "")
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    item.setForeground(QColor("#94A3B8" if column == 0 else "#FFFFFF"))
                    table.setItem(row_index, column, item)
            table.setUpdatesEnabled(True)
        except Exception:
            pass

    def on_subtitle_filter_changed(self):
        if hasattr(self, 'combo_sub_filter') and hasattr(self, 'filter_buttons'):
            cur_key = self.combo_sub_filter.currentData()
            for btn, key in self.filter_buttons:
                btn.setChecked(key == cur_key)
        self.refresh_subtitle_view()

    def _update_sub_history_header(self, filter_mode: str = "all"):
        if not hasattr(self, 'header_sub_history'):
            return
        is_grid_mode = filter_mode not in ("orig_only", "trans_only", "dub_only")
        self.header_sub_history.setVisible(is_grid_mode)
        if is_grid_mode:
            self.text_sub_history.setStyleSheet("""
                QTextBrowser {
                    background-color: #0E1422;
                    color: #ECEFF1;
                    border: 1px solid #1C273E;
                    border-top: none;
                    border-top-left-radius: 0px;
                    border-top-right-radius: 0px;
                    border-bottom-left-radius: 8px;
                    border-bottom-right-radius: 8px;
                    padding: 2px 4px 6px 4px;
                    font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
                }
            """)
        else:
            self.text_sub_history.setStyleSheet("""
                QTextBrowser {
                    background-color: #0E1422;
                    color: #ECEFF1;
                    border: 1px solid #1C273E;
                    border-radius: 8px;
                    padding: 8px;
                    font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
                }
            """)

    def refresh_subtitle_view(self):
        if not hasattr(self, 'text_sub_history'):
            return
        try:
            filter_mode = self.combo_sub_filter.currentData() or "all"
            search_kw = self.input_sub_search.text().strip() if hasattr(self, 'input_sub_search') else ""
            filtered = self.subtitle_history.get_entries(source_filter=filter_mode, keyword=search_kw)
            is_single_view = filter_mode in ("orig_only", "trans_only", "dub_only")
            html = SubtitleHistoryManager.format_html_table(filtered, filter_mode=filter_mode, include_header=is_single_view)
            self.text_sub_history.setHtml(html)
            self._update_sub_history_header(filter_mode)
            if hasattr(self, 'lbl_sub_count'):
                total_cnt = self.subtitle_history.count()
                if (filter_mode and filter_mode != "all") or search_kw:
                    self._i18n(self.lbl_sub_count, "count_filtered", shown=len(filtered), total=total_cnt)
                else:
                    self._i18n(self.lbl_sub_count, "count_total", total=total_cnt)
            if hasattr(self, 'toggle_sub_autoscroll') and self.toggle_sub_autoscroll.isChecked():
                sb = self.text_sub_history.verticalScrollBar()
                sb.setValue(sb.maximum())
        except Exception:
            pass


    def on_export_srt_clicked(self, checked=False, source_filter=None):
        filter_mode = source_filter or (self.combo_sub_filter.currentData() if hasattr(self, 'combo_sub_filter') else "all") or "all"
        search_kw = self.input_sub_search.text().strip() if hasattr(self, 'input_sub_search') else ""
        name_map = {
            "all": "subtitles_all.srt",
            "audio": "audio_subtitles.srt",
            "screen": "screen_subtitles.srt",
            "dubbing": "dubbing_subtitles.srt",
            "orig_only": "english_subtitles.srt",
            "trans_only": "korean_subtitles.srt",
            "dub_only": "dubbing_speech_only.srt",
        }
        default_name = self._subtitle_export_filename(filter_mode, "srt", name_map)
        fn, _ = QFileDialog.getSaveFileName(self, tr("msg_save_dialog_srt"), default_name, "SubRip (*.srt)")
        if fn:
            ok = self.subtitle_history.export_to_srt(filepath=fn, source_filter=filter_mode, keyword=search_kw)
            if ok:
                tell(self, "msg_saved_title", "msg_saved_file", path=fn)
            else:
                tell(self, "msg_save_failed_title", "msg_save_failed_sub", kind="warn")

    def on_export_txt_clicked(self, checked=False, source_filter=None):
        filter_mode = source_filter or (self.combo_sub_filter.currentData() if hasattr(self, 'combo_sub_filter') else "all") or "all"
        search_kw = self.input_sub_search.text().strip() if hasattr(self, 'input_sub_search') else ""
        name_map = {
            "all": "subtitles_all.txt",
            "audio": "audio_subtitles.txt",
            "screen": "screen_subtitles.txt",
            "dubbing": "dubbing_subtitles.txt",
            "orig_only": "english_transcript.txt",
            "trans_only": "korean_transcript.txt",
            "dub_only": "dubbing_transcript.txt",
        }
        default_name = self._subtitle_export_filename(filter_mode, "txt", name_map)
        fn, _ = QFileDialog.getSaveFileName(self, tr("msg_save_dialog_txt"), default_name, "Text (*.txt)")
        if fn:
            ok = self.subtitle_history.export_to_txt(filepath=fn, source_filter=filter_mode, keyword=search_kw)
            if ok:
                tell(self, "msg_saved_title", "msg_saved_file", path=fn)
            else:
                tell(self, "msg_save_failed_title", "msg_save_failed_text", kind="warn")

    def on_copy_subtitles_clicked(self, checked=False, source_filter=None):
        filter_mode = source_filter or (self.combo_sub_filter.currentData() if hasattr(self, 'combo_sub_filter') else "all") or "all"
        search_kw = self.input_sub_search.text().strip() if hasattr(self, 'input_sub_search') else ""
        content = self.subtitle_history.export_to_txt(source_filter=filter_mode, keyword=search_kw)
        if isinstance(content, str):
            QApplication.clipboard().setText(content)
            tell(self, "msg_copied_title", "msg_copied")

    def on_clear_subtitles_clicked(self):
        self.subtitle_history.clear()
        self.refresh_subtitle_view()
        self._update_mini_chat()

    def _poll_speakers(self):
        try:
            if hasattr(self, 'lbl_speaker_status'):
                status = self._speaker_status_text()
                if self.lbl_speaker_status.text() != status:
                    self.lbl_speaker_status.setText(status)
            if self.stt_thread and hasattr(self.stt_thread, "speaker_identifier") and self.stt_thread.speaker_identifier:
                spk_id = self.stt_thread.speaker_identifier
                if hasattr(spk_id, "get_all_known_speakers"):
                    speakers = spk_id.get_all_known_speakers()
                    cur_set = {s["raw_name"] for s in speakers}
                elif hasattr(spk_id, "speaker_profiles"):
                    cur_set = set(spk_id.speaker_profiles.keys())
                else:
                    cur_set = set()
                if cur_set != self._last_rendered_speakers:
                    self.refresh_speaker_mgmt_ui()
        except Exception:
            pass

    def _speaker_status_text(self):
        if not self.config.get('speaker_diarization_enabled', False):
            return tr("speaker_off")
        deepgram = getattr(self.stt_thread, 'deepgram_streamer', None)
        if (self.config.get('stt_provider') == 'deepgram' and deepgram and
                deepgram.is_connected()):
            return tr("speaker_live", count=int(self.config.get('speaker_max_count', 2)))
        identifier = getattr(self.stt_thread, 'speaker_identifier', None)
        if identifier and identifier.is_enabled:
            from src.speaker_identifier import localize_speaker_status
            return f'{tr("engine_local")} · {localize_speaker_status(identifier.get_status())}'
        return tr("speaker_wait")

    def refresh_speaker_mgmt_ui(self, force: bool = False):
        if not hasattr(self, 'speaker_list_layout'):
            return
        speakers = []
        if self.stt_thread and hasattr(self.stt_thread, "speaker_identifier") and self.stt_thread.speaker_identifier:
            speakers = self.stt_thread.speaker_identifier.get_all_known_speakers()
        elif self.config.get("speaker_aliases"):
            for raw, alias in self.config.get("speaker_aliases", {}).items():
                speakers.append({
                    "num": 1,
                    "raw_name": raw,
                    "alias": alias,
                    "display_name": alias or raw,
                    "color": COLOR_ACCENT_CYAN,
                    "muted": self.config.get("speaker_mutes", {}).get(raw, False)
                })

        cur_set = {s["raw_name"] for s in speakers}
        if not force and cur_set == self._last_rendered_speakers:
            return
        self._last_rendered_speakers = cur_set

        selected = set(self._selected_speakers())
        self.speaker_selection_checkboxes = {}

        while self.speaker_list_layout.count() > 0:
            item = self.speaker_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not speakers:
            empty_lbl = QLabel()
            self._i18n(empty_lbl, "no_speakers")
            empty_lbl.setStyleSheet("color: #64748B; font-size: 11px; padding: 12px;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.speaker_list_layout.addWidget(empty_lbl)
            return

        for idx, spk in enumerate(speakers):
            spk_name = spk["raw_name"]
            row_card = CardWidget(bg_color=COLOR_CARD_INNER, border_radius=6)
            r_layout = QHBoxLayout(row_card)
            r_layout.setContentsMargins(8, 4, 8, 4)
            r_layout.setSpacing(8)

            num_lbl = QLabel(str(spk.get("num", idx + 1)))
            num_lbl.setFixedWidth(16)
            name_lbl = QLabel(spk.get("display_name") or spk_name)
            name_lbl.setStyleSheet(f"font-weight: bold; color: {spk.get('color', COLOR_ACCENT_CYAN)};")

            select_cb = QPushButton(tr("select_speaker"))
            select_cb.setCheckable(True)
            select_cb.setChecked(spk_name in selected)
            self.speaker_selection_checkboxes[spk_name] = select_cb

            alias_edit = QLineEdit()
            alias_edit.setPlaceholderText(tr("alias_placeholder"))
            alias_edit.setText(spk.get("alias", self.config.get("speaker_aliases", {}).get(spk_name, "")))
            def _on_alias(s=spk_name, field=alias_edit):
                txt = field.text()
                self.config.setdefault("speaker_aliases", {})[s] = txt
                if self.stt_thread and hasattr(self.stt_thread, "speaker_identifier") and self.stt_thread.speaker_identifier:
                    self.stt_thread.speaker_identifier.set_speaker_alias(s, txt)
                self.save_config_cb(self.config)
            alias_edit.editingFinished.connect(_on_alias)

            cb_trans = QCheckBox(tr("translation"))
            is_muted = spk.get("muted", self.config.get("speaker_mutes", {}).get(spk_name, False))
            cb_trans.setChecked(not is_muted)
            def _on_trans(checked, s=spk_name):
                self.config.setdefault("speaker_mutes", {})[s] = not checked
                if self.stt_thread and hasattr(self.stt_thread, "speaker_identifier") and self.stt_thread.speaker_identifier:
                    self.stt_thread.speaker_identifier.set_speaker_muted(s, not checked)
                self.save_config_cb(self.config)
            cb_trans.toggled.connect(_on_trans)

            cb_dub = QCheckBox(tr("dubbing"))
            is_dub_muted = self.config.get("speaker_dubbing_mutes", {}).get(spk_name, False)
            cb_dub.setChecked(not is_dub_muted)
            def _on_dub(checked, s=spk_name):
                self.config.setdefault("speaker_dubbing_mutes", {})[s] = not checked
                self.save_config_cb(self.config)
            cb_dub.toggled.connect(_on_dub)

            btn_del = QPushButton("🗑")
            btn_del.setFixedSize(24, 24)
            btn_del.setStyleSheet("color: #EF4444; padding:0;")
            btn_del.clicked.connect(lambda _, s=spk_name: self._delete_speaker(s))

            r_layout.addWidget(select_cb)
            r_layout.addWidget(num_lbl)
            r_layout.addWidget(name_lbl)
            r_layout.addWidget(alias_edit, stretch=2)
            r_layout.addWidget(cb_trans)
            r_layout.addWidget(cb_dub)
            r_layout.addWidget(btn_del)

            self.speaker_list_layout.addWidget(row_card)

    def _delete_speaker(self, spk_name: str):
        if self.stt_thread and hasattr(self.stt_thread, "speaker_identifier") and self.stt_thread.speaker_identifier:
            self.stt_thread.speaker_identifier.remove_speaker(spk_name)
        self.config.get("speaker_aliases", {}).pop(spk_name, None)
        self.config.get("speaker_mutes", {}).pop(spk_name, None)
        self.config.get("speaker_dubbing_mutes", {}).pop(spk_name, None)
        self.config.get("speaker_voices", {}).pop(spk_name, None)
        self.refresh_speaker_mgmt_ui(force=True)
        self.save_config_cb(self.config)

    def _check_model_ready(self, model_type: str) -> bool:
        """LLM 모델이 Ollama 또는 내장 GGUF에 준비되어 있는지 확인"""
        from src.llm_model_manager import LLMModelManager, RECOMMENDED_GGUF_MODELS
        is_alive, _ = LLMModelManager.check_ollama_alive()
        if model_type in ("hymt", "hy-mt"):
            target_tag = "tencent/hy-mt2:1.8b"
        elif model_type in ("translategemma", "gemma"):
            target_tag = "translategemma:4b"
        elif model_type in ("exaone7b", "exaone-7b", "exaone-3.5-7.8b"):
            target_tag = "exaone3.5:7.8b"
        else:
            target_tag = "exaone3.5:2.4b"
        if is_alive and LLMModelManager.is_ollama_model_installed(target_tag):
            return True
        for m in RECOMMENDED_GGUF_MODELS:
            m_id = m.get("id", "")
            matched = False
            if model_type in ("hymt", "hy-mt") and "hymt" in m_id:
                matched = True
            elif model_type in ("translategemma", "gemma") and "translategemma" in m_id:
                matched = True
            elif model_type in ("exaone7b", "exaone-7b", "exaone-3.5-7.8b") and "7.8b" in m_id:
                matched = True
            elif model_type in ("exaone", "exaone-2.4b", "exaone-3.5-2.4b") and "2.4b" in m_id:
                matched = True
            if matched and LLMModelManager.is_gguf_model_installed(m):
                return True
        return False

    def _handle_preset_model_preflight(self, model_name: str, model_type: str, preset_key: str, notify: bool, is_stt: bool = False) -> bool:
        """프리셋 클릭 시 모델 미설치 모델 관리창 유도 다이얼로그 (LLM 팝업과 동일한 표준 QMessageBox.question 형태)"""
        from PyQt6.QtWidgets import QMessageBox
        role_label = "STT" if is_stt else tr("dlg_local_models")
        ret = ask(self, "msg_model_missing_title", "msg_model_missing", name=model_name or role_label)
        if ret == QMessageBox.StandardButton.Yes:
            if is_stt:
                self.open_stt_model_manager(target_model_id=model_type)
            else:
                self.open_llm_model_manager(target_model_id=model_type)
        return False

    def _handle_preset_dual_model_preflight(self, preset_name: str, llm_name: str, llm_type: str, stt_name: str, stt_type: str, notify: bool) -> bool:
        """번역 및 STT 모델이 둘 다 미설치된 경우 번역 모델부터 순차 유도"""
        return self._handle_preset_model_preflight(llm_name, llm_type, "", notify, is_stt=False)

    def _start_model_download_and_hotswap(self, model_type: str, target_preset: str):
        """백그라운드 모델 다운로드 후 무중단 핫스왑"""
        from src.llm_model_manager import LLMModelManager, OllamaPullWorker, GGUFDownloadWorker, RECOMMENDED_GGUF_MODELS
        is_alive, _ = LLMModelManager.check_ollama_alive()
        if model_type in ("hymt", "hy-mt"):
            target_tag = "tencent/hy-mt2:1.8b"
        elif model_type in ("translategemma", "gemma"):
            target_tag = "translategemma:4b"
        elif model_type in ("exaone7b", "exaone-7b", "exaone-3.5-7.8b"):
            target_tag = "exaone3.5:7.8b"
        else:
            target_tag = "exaone3.5:2.4b"

        if is_alive:
            self._active_worker = OllamaPullWorker(target_tag, parent=None)
            def _on_done(tag, success, msg):
                if success:
                    self.config["translation_engine"] = f"ollama:{tag}"
                    self.save_config_cb(self.config)
                    self.set_engine_by_key(self.config["translation_engine"])
                    self._refresh_presets_ui()
                    tell(self, "msg_download_switched_title", "msg_download_switched", name=tag)
            self._active_worker.finished_signal.connect(_on_done)
            self._active_worker.start()
        else:
            if model_type in ("exaone7b", "exaone-7b", "exaone-3.5-7.8b") or "7.8b" in model_type:
                gguf_info = next((m for m in RECOMMENDED_GGUF_MODELS if "7.8b" in m.get("id", "").lower()), None)
            else:
                gguf_info = next((m for m in RECOMMENDED_GGUF_MODELS if model_type in m.get("id", "") or m.get("id") == model_type), None)
            if gguf_info:
                self._active_worker = GGUFDownloadWorker(gguf_info, parent=None)
                def _on_done_gguf(m_id, success, msg):
                    if success:
                        if "hymt" in m_id or "hy-mt" in m_id:
                            self.config["translation_engine"] = "hymt"
                        elif "translategemma" in m_id:
                            self.config["translation_engine"] = "gemma"
                        elif "7.8b" in m_id:
                            self.config["translation_engine"] = "exaone7b"
                        else:
                            self.config["translation_engine"] = "exaone"
                        self.save_config_cb(self.config)
                        self.set_engine_by_key(self.config["translation_engine"])
                        self._refresh_presets_ui()
                        tell(self, "msg_download_switched_title", "msg_download_switched", name=gguf_info["name"])
                self._active_worker.finished_signal.connect(_on_done_gguf)
                self._active_worker.start()

    def _builtin_presets(self):
        return active_builtin_presets()

    def _i18n(self, widget, key, **fmt):
        return bind(widget, key, **fmt)

    def _preset_display_name(self, key, preset):
        label = tr(f"preset_{key}_name")
        if label != f"preset_{key}_name":
            return label
        return preset.get("name", key)

    def _refill_combo(self, combo, items):
        if combo is None:
            return
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for label, data in items:
            combo.addItem(label, data)
        index = combo.findData(current)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _tempo_caption(self, key=None):
        if not uses_local_tempo_vad(self.config):
            return tr("tempo_ignored")
        key = key or self.config.get("content_tempo_preset", "smart")
        return tr(f"tempo_{key}_desc")

    def _duration_text(self, seconds, short=False):
        seconds = int(seconds or 0)
        if seconds <= 0:
            return tr("duration_forever")
        return tr("duration_sec", n=seconds)

    def _refill_localized_lists(self):
        if hasattr(self, "combo_tempo_preset"):
            self._refill_combo(self.combo_tempo_preset, [(tr(f"tempo_{key}"), key) for key in CONTENT_TEMPO_PRESETS])
        if hasattr(self, "combo_tempo_preset_tab4"):
            self._refill_combo(self.combo_tempo_preset_tab4, [(tr(f"tempo_{key}"), key) for key in CONTENT_TEMPO_PRESETS])
        if hasattr(self, "combo_speaker_max_count"):
            self._refill_combo(self.combo_speaker_max_count, [
                (tr("spk_2"), 2), (tr("spk_3"), 3), (tr("spk_4"), 4), (tr("spk_8"), 8),
            ])
        if hasattr(self, "combo_dubbing_speed"):
            speeds = [
                ("+0%", tr("speed_normal")), ("+10%", tr("speed_brisk")),
                ("+15%", "1.15x"), ("+20%", "1.2x"), ("+25%", "1.25x"),
                ("+30%", "1.3x"), ("+40%", "1.4x"), ("+50%", "1.5x"),
                ("+80%", "1.8x"), ("+100%", "2.0x"),
            ]
            self._refill_combo(self.combo_dubbing_speed, [(label, code) for code, label in speeds])
        if hasattr(self, "combo_sub_filter"):
            self._refill_combo(self.combo_sub_filter, [
                (tr("filter_all_compare"), "all"), (tr("filter_voice_trans"), "audio"),
                (tr("filter_screen_trans"), "screen"), (tr("filter_dub_voice"), "dubbing"),
                (tr("filter_orig_only"), "orig_only"), (tr("filter_trans_only"), "trans_only"),
                (tr("filter_dub_speech_only"), "dub_only"),
            ])
        if hasattr(self, "combo_speaker_max_count"):
            self._refill_combo(self.combo_speaker_max_count, [
                (tr("spk_count_2"), 2),
                (tr("spk_count_3"), 3),
                (tr("spk_count_4"), 4),
                (tr("spk_count_8"), 8),
            ])
        if hasattr(self, "combo_trans_engine"):
            local = tr("engine_local")
            self._refill_combo(self.combo_trans_engine, [
                ("DeepL", "deepl"), (tr("engine_google"), "google"),
                ("Gemini Flash", "gemini"), ("Groq Qwen 27B", "groq"),
                (f"TranslateGemma ({local})", "gemma"),
                (f"EXAONE ({local})", "exaone"),
                (f"Hy-MT2 ({local})", "hymt"),
            ])
        for combo in (getattr(self, "combo_audio_cap_dev", None), getattr(self, "combo_dub_out_dev", None)):
            if combo is None:
                continue
            index = combo.findData("default")
            if index >= 0:
                combo.setItemText(index, "🔊 " + tr("audio_default"))
        if hasattr(self, "lbl_tempo_desc"):
            self.lbl_tempo_desc.setText(self._tempo_caption())
        if hasattr(self, "lbl_tempo_desc_tab4"):
            self.lbl_tempo_desc_tab4.setText(self._tempo_caption())
        if hasattr(self, "input_sub_search"):
            self.input_sub_search.setPlaceholderText(f"🔍 {tr('search_placeholder')}...")
        if hasattr(self, "edit_youtube_url"):
            self.edit_youtube_url.setPlaceholderText(tr("msg_youtube_url"))
        if hasattr(self, "lbl_duration"):
            value = self.slider_duration.value() if hasattr(self, "slider_duration") else 0
            self.lbl_duration.setText(self._duration_text(value))
        if hasattr(self, "audio_lbl_duration"):
            value = self.audio_slider_duration.value() if hasattr(self, "audio_slider_duration") else 0
            self.audio_lbl_duration.setText(self._duration_text(value))
        if hasattr(self, "screen_lbl_duration"):
            value = self.screen_slider_duration.value() if hasattr(self, "screen_slider_duration") else 0
            self.screen_lbl_duration.setText(self._duration_text(value))
        if hasattr(self, "lbl_speaker_status"):
            self.lbl_speaker_status.setText(self._speaker_status_text())

    def _apply_ui_language(self):
        set_ui_language(self.config.get("ui_lang") or "ko")
        self.setWindowTitle(tr("window_title"))
        refresh_texts(self)
        if getattr(self, "nav_buttons", None):
            tab_total = 0
            for index, btn in enumerate(self.nav_buttons):
                w = nav_tab_width(btn.text(), self.font())
                btn.setFixedSize(w, NAV_TAB_HEIGHT)
                if index:
                    tab_total += NAV_TAB_SPACING
                tab_total += w
            if hasattr(self, "nav_host") and self.nav_host is not None:
                self.nav_host.setFixedSize(tab_total, NAV_TAB_HEIGHT)
                self.nav_host.updateGeometry()
            self.setMinimumWidth(max(self.minimumWidth(), control_panel_min_width(self.font()), tab_total + 380))
        if hasattr(self, "_refresh_audio_devices"):
            self._refresh_audio_devices()
        if hasattr(self, "_populate_models"):
            self._populate_models()
        if hasattr(self, "combo_source_lang"):
            self.combo_source_lang.setToolTip(tr("source_lang_label"))
            current_src = self.combo_source_lang.currentData()
            self.combo_source_lang.blockSignals(True)
            self.combo_source_lang.clear()
            self.combo_source_lang.addItem(tr("source_lang_auto"), "auto")
            from src.translator import LANGUAGE_NAMES
            for code in LANGUAGE_NAMES:
                self.combo_source_lang.addItem(UI_LANGUAGE_NAMES.get(code, code), code)
            src_index = self.combo_source_lang.findData(current_src)
            if src_index < 0 and current_src:
                self.combo_source_lang.addItem(str(current_src).upper(), current_src)
                src_index = self.combo_source_lang.findData(current_src)
            self.combo_source_lang.setCurrentIndex(max(0, src_index))
            self.combo_source_lang.blockSignals(False)
        if hasattr(self, "combo_target_lang"):
            self.combo_target_lang.setToolTip(tr("target_lang_label"))
            current_tgt = self.combo_target_lang.currentData()
            self.combo_target_lang.blockSignals(True)
            self.combo_target_lang.clear()
            from src.translator import LANGUAGE_NAMES
            for code in LANGUAGE_NAMES:
                self.combo_target_lang.addItem(UI_LANGUAGE_NAMES.get(code, code), code)
            tgt_index = self.combo_target_lang.findData(current_tgt)
            if tgt_index < 0 and current_tgt:
                self.combo_target_lang.addItem(str(current_tgt).upper(), current_tgt)
                tgt_index = self.combo_target_lang.findData(current_tgt)
            self.combo_target_lang.setCurrentIndex(max(0, tgt_index))
            self.combo_target_lang.blockSignals(False)
        if hasattr(self, "combo_ui_lang"):
            self.combo_ui_lang.setToolTip(tr("ui_lang_label"))
        if hasattr(self, "quick_presets_layout"):
            self._refresh_presets_ui()
        if hasattr(self, "chip_tempo"):
            self._sync_all_pipeline_status()
        if hasattr(self, "_revert_engine_status"):
            self._revert_engine_status()
        if getattr(self, "overlay", None) is not None:
            if hasattr(self.overlay, "_apply_ui_language"):
                self.overlay._apply_ui_language()
            elif hasattr(self.overlay, "setWindowTitle"):
                self.overlay.setWindowTitle(tr("overlay_audio_title"))
        screen_overlay = getattr(self, "screen_overlay", None)
        if getattr(self, "screen_overlay", None) is not None:
            if hasattr(screen_overlay, "_apply_ui_language"):
                screen_overlay._apply_ui_language()
            overlays = screen_overlay.get_overlays() if hasattr(screen_overlay, "get_overlays") else [screen_overlay]
            for window in overlays:
                if hasattr(window, "_apply_ui_language"):
                    window._apply_ui_language()
                elif hasattr(window, "setWindowTitle"):
                    window.setWindowTitle(tr("overlay_screen_title"))
        if hasattr(self, "refresh_speaker_mgmt_ui"):
            self.refresh_speaker_mgmt_ui(force=True)
        if hasattr(self, "screen_dialogue_table"):
            self.screen_dialogue_table.setHorizontalHeaderLabels([tr("original"), tr("translation")])
            self._update_mini_chat()
        if hasattr(self, "btn_toggle_roi_border"):
            is_border = self.config.get("screen_show_roi_border", False)
            self.btn_toggle_roi_border.setText(f"🔲 {tr('region_border')} {'ON' if is_border else 'OFF'}")
        if hasattr(self, "lbl_hotkey_status"):
            cur_hk = self.config.get("inplace_hotkey", "F4")
            self.lbl_hotkey_status.setText(tr("hotkey_status", key=cur_hk))
        if hasattr(self, "btn_settings_hotkey") and hasattr(self.btn_settings_hotkey, "_update_text"):
            self.btn_settings_hotkey._update_text()
        if hasattr(self, "_populate_display_combo"):
            self._populate_display_combo()
        if hasattr(self, "refresh_roi_settings_cards"):
            self.refresh_roi_settings_cards()
        if hasattr(self, "refresh_subtitle_view"):
            self.refresh_subtitle_view()
        if hasattr(self, "_refresh_screen_preview"):
            self._refresh_screen_preview()
        if hasattr(self, "_refresh_all_status_badges"):
            self._refresh_all_status_badges()
        if hasattr(self, "lbl_screen_status"):
            is_worker_paused = getattr(self, 'screen_worker', None) and getattr(self.screen_worker, 'paused', False)
            is_overlay_paused = getattr(self, 'screen_overlay', None) and getattr(self.screen_overlay, '_paused', False)
            from src.screen_overlay_manager import ScreenOverlayManager
            if is_worker_paused or is_overlay_paused or (self.lbl_screen_status.text() and ScreenOverlayManager._is_paused_status_text(self.lbl_screen_status.text())):
                self.lbl_screen_status.setText(tr("ocr_status_paused"))
        self._refill_localized_lists()

    def _on_ui_lang_changed(self, index):
        if index < 0 or not hasattr(self, "combo_ui_lang"):
            return
        code = self.combo_ui_lang.itemData(index)
        if not code or code == self.config.get("ui_lang"):
            return
        self.config["ui_lang"] = code
        self.save_config_cb(self.config)
        self._apply_ui_language()

    def _on_source_lang_changed(self, index):
        if index < 0 or not hasattr(self, "combo_source_lang"):
            return
        code = self.combo_source_lang.itemData(index)
        if not code:
            return
        self._apply_source_lang(code)

    def _on_target_lang_changed(self, index):
        if index < 0 or not hasattr(self, "combo_target_lang"):
            return
        code = self.combo_target_lang.itemData(index)
        if not code:
            return
        self._apply_target_lang(code)

    def _apply_source_lang(self, code: str):
        if not code:
            return
        code = str(code).strip().lower()
        self.config["source_lang"] = code
        self.config["stt_language"] = code
        self.save_config_cb(self.config)

        if hasattr(self, "combo_source_lang"):
            idx = self.combo_source_lang.findData(code)
            if idx >= 0 and self.combo_source_lang.currentIndex() != idx:
                self.combo_source_lang.blockSignals(True)
                self.combo_source_lang.setCurrentIndex(idx)
                self.combo_source_lang.blockSignals(False)

        # 1. STT Worker 실시간 반영
        if getattr(self, "stt_thread", None) is not None:
            if hasattr(self.stt_thread, "update_config"):
                self.stt_thread.update_config(self.config)
            elif hasattr(self.stt_thread, "translator") and hasattr(self.stt_thread.translator, "update_config"):
                self.stt_thread.translator.update_config(self.config)

        # 2. Screen Worker 실시간 반영 (기존 화면 텍스트 즉시 새 출발어로 재번역 유도)
        if getattr(self, "screen_worker", None) is not None:
            if hasattr(self.screen_worker, "update_config"):
                self.screen_worker.update_config(self.config)
            elif hasattr(self.screen_worker, "translator") and hasattr(self.screen_worker.translator, "update_config"):
                self.screen_worker.translator.update_config(self.config)

        # 3. 오버레이 창 설정 동기화
        if getattr(self, "overlay", None) is not None and hasattr(self.overlay, "config"):
            self.overlay.config["source_lang"] = code
        if getattr(self, "screen_overlay", None) is not None and hasattr(self.screen_overlay, "config"):
            self.screen_overlay.config["source_lang"] = code

        # 4. 더빙 엔진 동기화
        d_engine = getattr(self, "dubbing_engine", None)
        if d_engine is not None and hasattr(d_engine, "update_config"):
            d_engine.update_config(self.config)

        # 5. 파이프라인 칩 및 상태 UI 갱신
        if hasattr(self, "_sync_all_pipeline_status"):
            self._sync_all_pipeline_status()

        # 6. 모델 호환성 점검 (영어 전용 STT 모델 자동 전환 등)
        self._check_multilingual_model_compatibility()

    def _apply_target_lang(self, code: str):
        if not code:
            return
        code = str(code).strip().lower()
        self.config["target_lang"] = code
        self.save_config_cb(self.config)

        if hasattr(self, "combo_target_lang"):
            idx = self.combo_target_lang.findData(code)
            if idx >= 0 and self.combo_target_lang.currentIndex() != idx:
                self.combo_target_lang.blockSignals(True)
                self.combo_target_lang.setCurrentIndex(idx)
                self.combo_target_lang.blockSignals(False)

        # 1. STT Worker 및 오디오 번역기 실시간 반영
        if getattr(self, "stt_thread", None) is not None:
            if hasattr(self.stt_thread, "update_config"):
                self.stt_thread.update_config(self.config)
            elif hasattr(self.stt_thread, "translator") and hasattr(self.stt_thread.translator, "update_config"):
                self.stt_thread.translator.update_config(self.config)

        # 2. Screen Worker 실시간 반영 (기존 화면 텍스트 즉시 새 도착어로 재번역 유도)
        if getattr(self, "screen_worker", None) is not None:
            if hasattr(self.screen_worker, "update_config"):
                self.screen_worker.update_config(self.config)
            elif hasattr(self.screen_worker, "translator") and hasattr(self.screen_worker.translator, "update_config"):
                self.screen_worker.translator.update_config(self.config)

        # 3. 오버레이 창 설정 동기화
        if getattr(self, "overlay", None) is not None and hasattr(self.overlay, "config"):
            self.overlay.config["target_lang"] = code
        if getattr(self, "screen_overlay", None) is not None and hasattr(self.screen_overlay, "config"):
            self.screen_overlay.config["target_lang"] = code

        # 4. 더빙 엔진 동기화 (도착 언어 변경 시 대기 큐 비우고 새 언어 음성 로드)
        d_engine = getattr(self, "dubbing_engine", None)
        if d_engine is not None and hasattr(d_engine, "update_config"):
            d_engine.update_config(self.config)
            if hasattr(d_engine, "clear_queue"):
                d_engine.clear_queue()
        self._populate_dubbing_voice_combos()

        # 5. 파이프라인 칩 및 상태 UI 갱신
        if hasattr(self, "_sync_all_pipeline_status"):
            self._sync_all_pipeline_status()

        # 6. 모델 호환성 점검 (EXAONE 한·영 전용 모델 자동 전환 등)
        self._check_multilingual_model_compatibility()

    def _check_multilingual_model_compatibility(self):
        """출발어/도착어 변경 시 로컬 LLM 및 STT 모델 호환성 점검 및 지능형 자동 전환"""
        if getattr(self, "_in_model_compatibility_check", False):
            return
        self._in_model_compatibility_check = True
        try:
            src = str(self.config.get("source_lang", "auto")).strip().lower()
            tgt = str(self.config.get("target_lang", "ko")).strip().lower()
            eng = str(self.config.get("translation_engine", "google")).strip().lower()

            from src.llm_model_manager import LLMModelManager
            from src.stt_model_manager import STTModelManager

            # 1. 로컬 LLM 호환성 점검 및 지능형 전환 (EXAONE 한·영 전용 제약 대응)
            if LLMModelManager.is_bilingual_only(eng) and not LLMModelManager.is_language_pair_supported(eng, src, tgt):
                custom_dir = self.config.get("custom_model_dir")
                multi_eng = LLMModelManager.is_multilingual_model_installed(custom_dir=custom_dir)
                if multi_eng:
                    disp_name = "Hy-MT2 1.8B" if multi_eng == "hymt" else "TranslateGemma 4B"
                    self.set_engine_by_key(multi_eng, prompt_missing=False)
                    msg = tr("warn_exaone_switched_to_multi", name=disp_name)
                else:
                    self.set_engine_by_key("google", prompt_missing=False)
                    msg = tr("warn_exaone_bilingual_only")
                if hasattr(self, "update_engine_status"):
                    self.update_engine_status("ready", msg)

            # 2. 로컬 STT 영어 전용 모델 점검 및 지능형 전환 (비영어/자동감지 출발어 시)
            if src != "en" and self.config.get("stt_provider", "local") == "local":
                default_stt = "small" if is_global() else "distil-small.en"
                model_sz = self.config.get("model_size", default_stt)
                if not STTModelManager.is_multilingual_model(model_sz, "local"):
                    dev = str(self.config.get("device", "cpu")).lower()
                    candidates = ["small", "base", "tiny"] if (dev == "cpu" or is_global()) else ["large-v3-turbo", "small", "base", "tiny", "medium", "large-v3"]
                    installed_multi = None
                    for cand in candidates:
                        if STTModelManager.is_model_installed(cand) or STTModelManager.is_bundled_model(cand):
                            installed_multi = cand
                            break

                    if installed_multi:
                        self._on_stt_model_quick_selected(installed_multi, prompt_missing=False)
                        src_label = tr("source_lang_auto") if src == "auto" else UI_LANGUAGE_NAMES.get(src, src.upper())
                        src_clean = src_label.replace("🌐 ", "").strip()
                        msg = tr("msg_stt_switched_to_multi", src=src_clean, name=installed_multi)
                    else:
                        msg = tr("warn_stt_english_only")
                    if hasattr(self, "update_engine_status"):
                        self.update_engine_status("ready", msg)
        finally:
            self._in_model_compatibility_check = False

    def _subtitle_export_filename(self, filter_mode, extension, fallback_map):
        from src.product import get_product
        from src.subtitle_manager import subtitle_export_filename
        name = subtitle_export_filename(
            filter_mode,
            extension,
            source_lang=self.config.get("source_lang", "en"),
            target_lang=self.config.get("target_lang", "ko"),
            product=get_product(),
        )
        if name:
            return name
        return fallback_map.get(filter_mode, f"subtitles.{extension}")

    def _coerce_device_without_nvidia(self):
        """GPU 프리셋이라도 NVIDIA 가 없는 PC 에서는 CPU 로 실행한다."""
        from src.cuda_utils import is_nvidia_gpu_present
        if self.config.get("device") != "cuda" or is_nvidia_gpu_present():
            return
        from src.stt_model_manager import STTModelManager
        self.config["device"] = "cpu"
        self.config["compute_type"] = "int8"
        fallback_model = "small" if is_global() else "distil-small.en"
        if not STTModelManager.is_cpu_usable(self.config.get("model_size", fallback_model)):
            self.config["model_size"] = fallback_model
            if is_global():
                self.config["stt_language"] = "auto"

    def _apply_preset_with_temp_engine(self, preset_key: str, temp_engine: str = "google", notify: bool = True):
        """프리셋의 템포 및 기타 설정을 적용하되 번역 엔진만 임시 엔진으로 연결"""
        if preset_key == "cloud":
            preset_key = "low_spec"
        item = self._builtin_presets().get(preset_key)
        if item:
            self._active_preset_id = preset_key
            self.config["translation_engine"] = temp_engine
            self.config["content_tempo_preset"] = item["content_tempo_preset"]
            for k in ("device", "compute_type", "stt_provider", "model_size"):
                if k in item:
                    self.config[k] = item[k]
            self._coerce_device_without_nvidia()
            self.save_config_cb(self.config)

            if hasattr(self, 'trans_engine_buttons'):
                for btn, k in self.trans_engine_buttons:
                    btn.setChecked(k == temp_engine)

            if hasattr(self, 'combo_tempo_preset'):
                t_key = item["content_tempo_preset"]
                for idx in range(self.combo_tempo_preset.count()):
                    if self.combo_tempo_preset.itemData(idx) == t_key:
                        self.combo_tempo_preset.blockSignals(True)
                        self.combo_tempo_preset.setCurrentIndex(idx)
                        self.combo_tempo_preset.blockSignals(False)
                        break

            self._sync_all_pipeline_status()
            self.update_engine_status("ready", tr("status_preset_applied", name=self._preset_display_name(preset_key, item)))
            if notify:
                tell(self, "msg_preset_temp_title", "msg_preset_temp", name=self._preset_display_name(preset_key, item), desc=item.get("desc", ""), engine=temp_engine)

    def apply_preset(self, preset_key: str, notify: bool = True):
        if preset_key == "cloud":
            preset_key = "low_spec"

        if preset_key not in self._builtin_presets():
            return

        item = self._builtin_presets()[preset_key]
        req_model = item.get("requires_model")
        req_api_key = item.get("requires_api_key")

        # 1. Groq API 키 점검
        if req_api_key == "groq":
            if not self.config.get("groq_api_key", "").strip():
                ret = ask(self, "msg_need_key_title", "msg_open_key_settings", name=item.get("name", "Groq"))
                if ret == QMessageBox.StandardButton.Yes:
                    self.open_api_key_dialog()
                return

        # 2. 로컬 번역(LLM) 모델 점검
        llm_ready = True
        llm_title = ""
        if req_model:
            model_titles = {
                "hymt": "Tencent Hy-MT2 1.8B",
                "translategemma": "Google TranslateGemma 4B",
                "exaone": "LG EXAONE 3.5 2.4B",
                "exaone7b": "LG EXAONE 3.5 7.8B",
            }
            llm_title = model_titles.get(req_model, req_model)
            llm_ready = self._check_model_ready(req_model)

        # 3. 로컬 STT 모델 점검
        stt_ready = True
        stt_title = ""
        req_stt_model = item.get("model_size")
        req_stt_provider = item.get("stt_provider", "local")
        if req_stt_provider == "local" and req_stt_model:
            from src.stt_model_manager import STTModelManager
            stt_ready = STTModelManager.is_model_installed(req_stt_model) or STTModelManager.is_bundled_model(req_stt_model)
            stt_title = req_stt_model

        if not llm_ready and not stt_ready:
            self._handle_preset_dual_model_preflight(item["name"], llm_title, req_model, stt_title, req_stt_model, notify)
            return
        elif not llm_ready:
            self._handle_preset_model_preflight(llm_title, req_model, preset_key, notify, is_stt=False)
            return
        elif not stt_ready:
            self._handle_preset_model_preflight(stt_title, req_stt_model, preset_key, notify, is_stt=True)
            return

        self._active_preset_id = preset_key
        for k in ("device", "compute_type", "stt_provider", "translation_engine", "model_size", "groq_model", "content_tempo_preset", "stt_language"):
            if k in item:
                self.config[k] = item[k]
        if is_global() and self.config.get("source_lang") and self.config.get("source_lang") != "auto":
            self.config["stt_language"] = self.config["source_lang"]
        self._coerce_device_without_nvidia()
        self.save_config_cb(self.config)

        # 1. 번역 엔진 버튼 상태 동기화
        if hasattr(self, 'trans_engine_buttons'):
            for btn, k in self.trans_engine_buttons:
                btn.setChecked(k == self.config.get("translation_engine"))

        # STT 디바이스 버튼 동기화
        if hasattr(self, 'stt_buttons'):
            cur_dev = self.config.get("device", "cuda")
            if self.config.get("stt_provider") in ("groq", "deepgram"):
                cur_dev = self.config.get("stt_provider")
            for btn, k in self.stt_buttons:
                btn.setChecked(k == cur_dev)

        # 2. 템포 드롭다운 동기화 (Tab 0 & Tab 4)
        t_key = self.config.get("content_tempo_preset", "smart")
        if hasattr(self, 'combo_tempo_preset'):
            for idx in range(self.combo_tempo_preset.count()):
                if self.combo_tempo_preset.itemData(idx) == t_key:
                    self.combo_tempo_preset.blockSignals(True)
                    self.combo_tempo_preset.setCurrentIndex(idx)
                    self.combo_tempo_preset.blockSignals(False)
                    break
        if hasattr(self, 'tempo_buttons_tab4'):
            for btn, k in self.tempo_buttons_tab4:
                btn.setChecked(k == t_key)
        if hasattr(self, 'combo_tempo_preset_tab4'):
            for idx in range(self.combo_tempo_preset_tab4.count()):
                if self.combo_tempo_preset_tab4.itemData(idx) == t_key:
                    self.combo_tempo_preset_tab4.blockSignals(True)
                    self.combo_tempo_preset_tab4.setCurrentIndex(idx)
                    self.combo_tempo_preset_tab4.blockSignals(False)
                    break
        t_desc = tempo_preset_desc(t_key, self.config)
        if hasattr(self, 'lbl_tempo_desc'):
            self.lbl_tempo_desc.setText(t_desc)
        if hasattr(self, 'lbl_tempo_desc_tab4'):
            self.lbl_tempo_desc_tab4.setText(t_desc)

        # 3. STT 및 오디오 스레드 갱신
        if hasattr(self, 'stt_thread') and self.stt_thread:
            self.stt_thread.update_config(self.config)
        if hasattr(self, 'audio_thread') and self.audio_thread:
            self.audio_thread.update_config(self.config)
        if hasattr(self, 'screen_worker') and self.screen_worker:
            if hasattr(self.screen_worker, 'update_config'):
                self.screen_worker.update_config(self.config)

        # 4. 오버레이 창 동기화
        if hasattr(self, 'overlay') and self.overlay:
            if hasattr(self.overlay, 'set_engine_by_key'):
                self.overlay.set_engine_by_key(self.config.get("translation_engine"))
            if hasattr(self.overlay, 'update_live_display'):
                self.overlay.update_live_display()

        self._sync_all_pipeline_status()
        self._check_multilingual_model_compatibility()
        self.update_engine_status("ready", tr("status_preset_applied", name=self._preset_display_name(preset_key, item)))
        self._refresh_presets_ui()
        if notify:
            tell(self, "msg_preset_applied_title", "msg_preset_applied", name=self._preset_display_name(preset_key, item), desc=item.get("desc", ""))

    def _check_custom_preset_status(self, p_cfg: dict) -> tuple[str, str]:
        """커스텀 프리셋의 엔진 및 모델 사용 가능 상태(텍스트, 타입) 점검"""
        engine = p_cfg.get("translation_engine", "google")
        stt = p_cfg.get("stt_provider", "local")

        # 1. API 키 점검
        if engine == "groq" or stt == "groq":
            if not self.config.get("groq_api_key", "").strip():
                return tr("need_key"), "need_key"
        if engine == "deepgram" or stt == "deepgram":
            if not self.config.get("deepgram_api_key", "").strip():
                return tr("need_key"), "need_key"
        if engine == "deepl":
            if not self.config.get("deepl_api_key", "").strip():
                return tr("need_key"), "need_key"
        if engine == "gemini":
            if not self.config.get("gemini_api_key", "").strip():
                return tr("need_key"), "need_key"

        # 2. 로컬 LLM 준비 여부 점검
        if "translategemma" in engine or engine == "gemma":
            if not self._check_model_ready("translategemma"):
                return tr("need_download"), "need_dl"
        elif "exaone" in engine:
            if not self._check_model_ready("exaone"):
                return tr("need_download"), "need_dl"
        elif "hymt" in engine or "hy-mt" in engine:
            if not self._check_model_ready("hymt"):
                return tr("need_download"), "need_dl"

        # 3. 로컬 STT 준비 여부 점검
        if stt == "local" and p_cfg.get("model_size"):
            from src.stt_model_manager import STTModelManager
            if not (STTModelManager.is_model_installed(p_cfg["model_size"]) or STTModelManager.is_bundled_model(p_cfg["model_size"])):
                return tr("need_stt"), "need_dl"

        return tr("ready_now"), "ready"

    def _format_preset_tooltip(self, name: str, cfg: dict, status_text: str = "") -> str:
        """프리셋의 세부 구성(번역 엔진, STT, 콘텐츠 템포, 상태)을 툴팁 텍스트로 생성"""
        eng_key = cfg.get("translation_engine", "google")
        local_tag = f"({tr('engine_local')})"
        eng_names = {
            "google": "Google",
            "deepl": "DeepL",
            "gemini": "Gemini Flash",
            "groq": "Groq Qwen 27B",
            "gemma": f"TranslateGemma 4B {local_tag}",
            "translategemma": f"TranslateGemma 4B {local_tag}",
            "exaone": f"LG EXAONE 3.5 2.4B {local_tag}",
            "exaone7b": f"LG EXAONE 3.5 7.8B {local_tag}",
            "hymt": f"Tencent Hy-MT2 1.8B {local_tag}",
        }
        eng_display = eng_names.get(eng_key, eng_key)
        if "(로컬)" in eng_display:
            eng_display = eng_display.replace("(로컬)", local_tag)
        if "(Local)" in eng_display and local_tag != "(Local)":
            eng_display = eng_display.replace("(Local)", local_tag)
        if "(로컬)" in name:
            name = name.replace("(로컬)", local_tag)
        if "(Local)" in name and local_tag != "(Local)":
            name = name.replace("(Local)", local_tag)

        stt_p = cfg.get("stt_provider", "local")
        dev = cfg.get("device", "cuda")
        if stt_p == "groq":
            groq_m = cfg.get("groq_model", "whisper-large-v3-turbo")
            stt_display = f"Groq ({groq_m})"
        elif stt_p == "deepgram":
            stt_display = "Deepgram Nova-3"
        else:
            dev_name = "NVIDIA CUDA" if dev == "cuda" else "CPU"
            model_name = cfg.get("model_size", "distil-large-v3.5")
            stt_display = f"{dev_name} ({model_name})"
        if cfg.get("stt_language") == "auto":
            stt_display += f" [{tr('preset_auto_detect_langs')}]"

        tempo_key = cfg.get("content_tempo_preset", "smart")
        tempo_label = tr(f"tempo_{tempo_key}")
        if not tempo_label.startswith("tempo_"):
            tempo_display = tempo_label
        else:
            tempo_info = CONTENT_TEMPO_PRESETS.get(tempo_key)
            tempo_display = tempo_info.get("name", tempo_key) if tempo_info else tempo_key

        lines = [
            f"[{name}] {tr('preset_info_header')}",
            f"• {tr('translation_engine')}: {eng_display}",
            f"• {tr('th_stt')}: {stt_display}",
            f"• {tr('content_tempo')}: {tempo_display}",
        ]
        if status_text:
            lines.append(f"• {tr('status')}: {status_text}")

        return "\n".join(lines)

    def _refresh_presets_ui(self):
        """추천 프리셋 및 사용자가 생성한 커스텀 프리셋 목록 동적 렌더링"""
        if not hasattr(self, 'preset_list_layout'):
            return

        while self.preset_list_layout.count():
            item = self.preset_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        active_id = self._detect_active_preset_id()

        for p_key, p_def in self._builtin_presets().items():
            req_m = p_def.get("requires_model")
            req_k = p_def.get("requires_api_key")
            if req_k == "groq":
                groq_ready = bool(self.config.get("groq_api_key", "").strip())
                st_text = tr("ready_now") if groq_ready else tr("need_key")
                st_type = "ready" if groq_ready else "need_key"
            elif req_m:
                ready = self._check_model_ready(req_m)
                st_text = tr("ready_now") if ready else tr("need_download")
                st_type = "ready" if ready else "need_dl"
            else:
                st_text = tr("ready_now")
                st_type = "ready"

            btn = QPushButton()
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.setToolTip(self._format_preset_tooltip(self._preset_display_name(p_key, p_def), p_def, st_text))
            if p_key == active_id:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: #1A243D;
                        border: 1.5px solid {COLOR_ACCENT_PURPLE};
                        border-radius: 6px;
                    }}
                    QPushButton:hover {{
                        background-color: #223052;
                        border-color: #A5B4FC;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: #101728;
                        border: 1px solid {COLOR_BORDER};
                        border-radius: 6px;
                    }}
                    QPushButton:hover {{
                        background-color: #1A243D;
                        border-color: {COLOR_ACCENT_PURPLE};
                    }}
                """)
            h = QHBoxLayout(btn)
            h.setContentsMargins(8, 0, 8, 0)
            lbl = QLabel(self._preset_display_name(p_key, p_def))
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lbl.setStyleSheet("color: #ECEFF1; font-size: 10.5px; font-weight: 500;")
            h.addWidget(lbl)
            h.addStretch(1)

            badge = create_status_badge(st_text, st_type)
            h.addWidget(badge)

            btn.clicked.connect(lambda _, pk=p_key: self.apply_preset(pk))
            self.preset_list_layout.addWidget(btn)

        # 2. 사용자 정의 커스텀 프리셋 (기본 프리셋과 동일한 버튼 방식 & 사용 가능 상태 표시, 옆에 삭제 버튼 배치)
        custom_presets = self.config.get("custom_presets", {})
        if custom_presets:
            cust_title = QLabel()
            self._i18n(cust_title, "custom_presets")
            cust_title.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {COLOR_ACCENT_CYAN}; margin-top: 10px; margin-bottom: 2px;")
            self.preset_list_layout.addWidget(cust_title)

            for idx, (p_id, p_info) in enumerate(custom_presets.items()):
                p_name = p_info.get("name", tr("custom_preset"))
                p_cfg = p_info.get("config", {})

                st_text, st_type = self._check_custom_preset_status(p_cfg)

                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(6)

                # 커스텀 프리셋 버튼 (기본 프리셋과 동일한 버튼 방식 및 상태 도트 뱃지)
                btn_preset = QPushButton()
                btn_preset.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_preset.setFixedHeight(30)

                if p_id == active_id:
                    btn_preset.setStyleSheet(f"""
                        QPushButton {{
                            background-color: #1A243D;
                            border: 1.5px solid {COLOR_ACCENT_PURPLE};
                            border-radius: 6px;
                        }}
                        QPushButton:hover {{
                            background-color: #223052;
                            border-color: #A5B4FC;
                        }}
                    """)
                else:
                    btn_preset.setStyleSheet(f"""
                        QPushButton {{
                            background-color: #101728;
                            border: 1px solid {COLOR_BORDER};
                            border-radius: 6px;
                        }}
                        QPushButton:hover {{
                            background-color: #1A243D;
                            border-color: {COLOR_ACCENT_PURPLE};
                        }}
                    """)

                h = QHBoxLayout(btn_preset)
                h.setContentsMargins(8, 0, 8, 0)

                # 아이콘 및 이름 (하단 퀵 프리셋 바와 100% 동일한 아이콘 동기화)
                icon, clean_name = self._get_custom_preset_icon_and_name(p_name, idx, p_info)
                display_name = p_name if p_name.startswith(icon) else f"{icon} {clean_name}"
                lbl = QLabel(display_name)
                lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                lbl.setStyleSheet("color: #ECEFF1; font-size: 10.5px; font-weight: 500;")
                h.addWidget(lbl)
                h.addStretch(1)

                badge = create_status_badge(st_text, st_type)
                h.addWidget(badge)

                btn_preset.setToolTip(self._format_preset_tooltip(display_name, p_cfg, st_text))
                btn_preset.clicked.connect(lambda _, pid=p_id: self.apply_custom_preset(pid))

                # 삭제 버튼 (섹션 분리: 프리셋 버튼 옆에 버튼으로 배치, SVG 아이콘으로 잘림 방지)
                btn_del = QPushButton()
                btn_del.setIcon(create_svg_icon(SVG_TRASH_ICON, 14, "#EF4444"))
                btn_del.setIconSize(QSize(14, 14))
                btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_del.setFixedSize(30, 30)
                btn_del.setToolTip(tr("tip_delete_preset"))
                btn_del.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(239, 68, 68, 0.12);
                        border-radius: 6px;
                        border: 1px solid rgba(239, 68, 68, 0.28);
                        padding: 0px;
                        margin: 0px;
                    }
                    QPushButton:hover {
                        background-color: rgba(239, 68, 68, 0.28);
                        border-color: #EF4444;
                    }
                """)
                btn_del.clicked.connect(lambda _, pid=p_id: self.delete_custom_preset(pid))

                row_layout.addWidget(btn_preset, stretch=1)
                row_layout.addWidget(btn_del)
                self.preset_list_layout.addWidget(row_widget)

        self.preset_list_layout.addStretch(1)
        if hasattr(self, 'btn_save_preset'):
            c_count = len(custom_presets)
            if c_count >= 6:
                self.btn_save_preset.setToolTip(tr("tip_preset_full"))
            else:
                self.btn_save_preset.setToolTip(tr("tip_save_preset", count=c_count))
        self._refresh_quick_presets_ui()

    def save_current_as_custom_preset(self):
        """현재 설정 상태를 새 커스텀 프리셋으로 저장 (이름만 입력, 최대 6개 제한)"""
        custom_presets = self.config.setdefault("custom_presets", {})
        if len(custom_presets) >= 6:
            tell(self, "msg_preset_limit_title", "msg_preset_limit", kind="warn")
            return

        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, tr("msg_preset_name_title"), tr("msg_preset_name_prompt"))
        if not ok or not name.strip():
            return

        import time
        preset_id = f"custom_{int(time.time() * 1000)}"
        custom_presets = self.config.setdefault("custom_presets", {})
        idx = len(custom_presets)
        icon, _ = self._get_custom_preset_icon_and_name(name.strip(), idx)
        snapshot = {
            "name": name.strip(),
            "icon": icon,
            "desc": "",
            "config": {
                "device": self.config.get("device", "cuda"),
                "stt_provider": self.config.get("stt_provider", "local"),
                "model_size": self.config.get("model_size", "distil-large-v3.5"),
                "content_tempo_preset": self.config.get("content_tempo_preset", "smart"),
                "translation_engine": self.config.get("translation_engine", "google"),
                "llm_backend": self.config.get("llm_backend", "embedded"),
                "selected_llm_model": self.config.get("selected_llm_model", "exaone-3.5-2.4b"),
                "font_size": self.config.get("font_size", 24),
                "overlay_bg_opacity": self.config.get("overlay_bg_opacity", 0.66),
                "subtitle_stroke_width": self.config.get("subtitle_stroke_width", 0),
                "letter_spacing": float(self.config.get("letter_spacing", 0.0)),
                "screen_clean_box": self.config.get("screen_clean_box", True),
                "screen_snap_to_roi": self.config.get("screen_snap_to_roi", False),
            }
        }
        custom_presets[preset_id] = snapshot
        self.save_config_cb(self.config)
        self._active_preset_id = preset_id
        self._refresh_presets_ui()
        tell(self, "msg_preset_saved_title", "msg_preset_saved", name=name.strip())

    def apply_custom_preset(self, preset_id: str, notify: bool = True):
        """커스텀 프리셋 적용"""
        custom_presets = self.config.get("custom_presets", {})
        if preset_id not in custom_presets:
            return
        p_info = custom_presets[preset_id]
        p_cfg = p_info.get("config", {})

        # 1. API 키 점검
        eng = p_cfg.get("translation_engine", "google")
        stt_p = p_cfg.get("stt_provider", "local")
        stt_m = p_cfg.get("model_size")

        if eng == "groq" or stt_p == "groq":
            if not self.config.get("groq_api_key", "").strip():
                ret = ask(self, "msg_need_key_title", "msg_open_key_settings", name=p_info.get("name", "Groq"))
                if ret == QMessageBox.StandardButton.Yes:
                    self.open_api_key_dialog()
                return

        # 2. 로컬 LLM 점검
        req_llm = None
        if "translategemma" in eng or eng == "gemma":
            req_llm = "translategemma"
        elif "exaone7b" in eng or "7.8b" in eng:
            req_llm = "exaone7b"
        elif "exaone" in eng:
            req_llm = "exaone"
        elif "hymt" in eng or "hy-mt" in eng:
            req_llm = "hymt"

        llm_ready = True
        llm_title = ""
        if req_llm:
            model_titles = {
                "hymt": "Tencent Hy-MT2 1.8B",
                "translategemma": "Google TranslateGemma 4B",
                "exaone": "LG EXAONE 3.5 2.4B",
                "exaone7b": "LG EXAONE 3.5 7.8B",
            }
            llm_title = model_titles.get(req_llm, req_llm)
            llm_ready = self._check_model_ready(req_llm)

        # 3. 로컬 STT 점검
        stt_ready = True
        stt_title = ""
        if stt_p == "local" and stt_m:
            from src.stt_model_manager import STTModelManager
            stt_ready = STTModelManager.is_model_installed(stt_m) or STTModelManager.is_bundled_model(stt_m)
            stt_title = stt_m

        if not llm_ready and not stt_ready:
            self._handle_preset_dual_model_preflight(p_info.get("name", tr("custom_preset")), llm_title, req_llm, stt_title, stt_m, notify)
            return
        elif not llm_ready:
            self._handle_preset_model_preflight(llm_title, req_llm, preset_id, notify, is_stt=False)
            return
        elif not stt_ready:
            self._handle_preset_model_preflight(stt_title, stt_m, preset_id, notify, is_stt=True)
            return

        self._active_preset_id = preset_id
        for k, v in p_cfg.items():
            self.config[k] = v
        self.save_config_cb(self.config)

        # UI 동기화
        if hasattr(self, 'trans_engine_buttons'):
            for btn, k in self.trans_engine_buttons:
                btn.setChecked(k == self.config.get("translation_engine"))

        t_key = self.config.get("content_tempo_preset", "smart")
        if hasattr(self, 'combo_tempo_preset'):
            for idx in range(self.combo_tempo_preset.count()):
                if self.combo_tempo_preset.itemData(idx) == t_key:
                    self.combo_tempo_preset.blockSignals(True)
                    self.combo_tempo_preset.setCurrentIndex(idx)
                    self.combo_tempo_preset.blockSignals(False)
                    break
        if hasattr(self, 'tempo_buttons_tab4'):
            for btn, k in self.tempo_buttons_tab4:
                btn.setChecked(k == t_key)
        if hasattr(self, 'combo_tempo_preset_tab4'):
            for idx in range(self.combo_tempo_preset_tab4.count()):
                if self.combo_tempo_preset_tab4.itemData(idx) == t_key:
                    self.combo_tempo_preset_tab4.blockSignals(True)
                    self.combo_tempo_preset_tab4.setCurrentIndex(idx)
                    self.combo_tempo_preset_tab4.blockSignals(False)
                    break
        t_desc = tempo_preset_desc(t_key, self.config)
        if hasattr(self, 'lbl_tempo_desc'):
            self.lbl_tempo_desc.setText(t_desc)
        if hasattr(self, 'lbl_tempo_desc_tab4'):
            self.lbl_tempo_desc_tab4.setText(t_desc)

        if hasattr(self, 'combo_model'):
            self._populate_models()

        if hasattr(self, 'font_slider'):
            self.font_slider.setValue(self.config.get("font_size", 24))
        if hasattr(self, 'opacity_slider'):
            self.opacity_slider.setValue(int(self.config.get("overlay_bg_opacity", 0.66) * 100))
        if hasattr(self, 'slider_stroke'):
            self.slider_stroke.setValue(self.config.get("subtitle_stroke_width", 0))
        if hasattr(self, 'slider_spacing'):
            self.slider_spacing.setValue(int(float(self.config.get("letter_spacing", 0.0)) * 10))

        if hasattr(self, 'stt_thread') and self.stt_thread:
            self.stt_thread.update_config(self.config)
        if hasattr(self, 'audio_thread') and self.audio_thread:
            self.audio_thread.update_config(self.config)
        if hasattr(self, 'screen_worker') and self.screen_worker:
            if hasattr(self.screen_worker, 'update_config'):
                self.screen_worker.update_config(self.config)

        self._sync_all_pipeline_status()
        self._check_multilingual_model_compatibility()
        self._update_subtitle_preview()

        if notify:
            tell(self, "msg_preset_applied_title", "msg_preset_applied", name=p_info.get("name", ""), desc=p_info.get("desc", ""))

    def delete_custom_preset(self, preset_id: str):
        """커스텀 프리셋 삭제"""
        custom_presets = self.config.get("custom_presets", {})
        if preset_id not in custom_presets:
            return
        p_name = custom_presets[preset_id].get("name", tr("custom_preset"))
        ret = ask(self, "msg_delete_preset_title", "msg_delete_preset", name=p_name)
        if ret == QMessageBox.StandardButton.Yes:
            del custom_presets[preset_id]
            self.config["custom_presets"] = custom_presets
            self.save_config_cb(self.config)
            if self._active_preset_id == preset_id:
                self._active_preset_id = None
            self._refresh_presets_ui()

    def _get_custom_preset_icon_and_name(self, name: str, index: int, p_info: Optional[dict] = None) -> tuple[str, str]:
        """커스텀 프리셋 이름에서 이모지 아이콘 추출 또는 기본 아이콘 팔레트 부여"""
        import re
        name_str = name.strip()
        if p_info and p_info.get("icon"):
            icon = p_info["icon"]
            if name_str.startswith(icon):
                clean = name_str[len(icon):].strip()
                return icon, clean or name_str
            return icon, name_str

        if name_str:
            match = re.match(r"^([\U00010000-\U0010ffff]|[\u2600-\u27ff]|[\u2300-\u23ff]|[\u2b50-\u2b55])\s*", name_str)
            if match:
                icon = match.group(1)
                clean = name_str[match.end():].strip()
                return icon, clean or name_str
        palette = ["⭐", "✨", "💎", "🎯", "🚀", "🔥", "🔖", "🌟", "💡", "⚡"]
        return palette[index % len(palette)], name_str

    def _is_builtin_preset_matching(self, p_key: str, p_def: dict) -> bool:
        """현재 설정이 특정 빌트인 프리셋과 일치하는지 판별"""
        cur_eng = str(self.config.get("translation_engine", ""))
        cur_tempo = self.config.get("content_tempo_preset", "smart")
        cur_dev = self.config.get("device", "cpu")
        cur_model = self.config.get("model_size", "")

        target_eng = p_def.get("translation_engine", "")
        target_tempo = p_def.get("content_tempo_preset", "")
        target_dev = p_def.get("device", "")
        target_model = p_def.get("model_size", "")

        # 템포 일치 필수
        if cur_tempo != target_tempo:
            return False

        # 엔진 일치 검사
        if target_eng == "hymt":
            if not ("hymt" in cur_eng or "hy-mt" in cur_eng):
                return False
        elif target_eng == "gemma":
            if "gemma" not in cur_eng:
                return False
        elif target_eng == "exaone7b":
            if not ("7b" in cur_eng or "7.8b" in cur_eng):
                return False
        elif target_eng == "exaone":
            if ("exaone" not in cur_eng) or ("7b" in cur_eng or "7.8b" in cur_eng):
                return False
        else:
            if cur_eng != target_eng:
                return False

        # 디바이스 일치 검사 (low_spec은 CPU 전용, 나머지는 CUDA 중심)
        if target_dev and cur_dev != target_dev:
            return False

        # 모델 크기 검사 (distil-small.en vs distil-large-v3.5)
        if target_model and cur_model != target_model:
            return False

        return True

    def _detect_active_preset_id(self) -> Optional[str]:
        """현재 활성화된 프리셋 ID 감지 (빌트인 또는 커스텀)"""
        custom_presets = self.config.get("custom_presets", {})

        # 1. 기존 활성 ID가 여전히 유효한지 우선 점검
        if self._active_preset_id:
            chk_id = "low_spec" if self._active_preset_id == "cloud" else self._active_preset_id
            if chk_id in self._builtin_presets():
                if self._is_builtin_preset_matching(chk_id, self._builtin_presets()[chk_id]):
                    self._active_preset_id = chk_id
                    return chk_id
            elif self._active_preset_id in custom_presets:
                c_cfg = custom_presets[self._active_preset_id].get("config", {})
                match = True
                for k in ("translation_engine", "content_tempo_preset", "model_size", "stt_provider"):
                    if k in c_cfg and self.config.get(k) != c_cfg[k]:
                        match = False
                        break
                if match:
                    return self._active_preset_id

        # 2. 일치하는 빌트인 프리셋 자동 감지
        for p_key, p_def in self._builtin_presets().items():
            if self._is_builtin_preset_matching(p_key, p_def):
                self._active_preset_id = p_key
                return p_key

        # 3. 일치하는 커스텀 프리셋 자동 감지
        for c_key, c_info in custom_presets.items():
            c_cfg = c_info.get("config", {})
            match = True
            for k in ("translation_engine", "content_tempo_preset", "model_size", "stt_provider"):
                if k in c_cfg and self.config.get(k) != c_cfg[k]:
                    match = False
                    break
            if match:
                self._active_preset_id = c_key
                return c_key

        self._active_preset_id = None
        return None

    def _refresh_quick_presets_ui(self):
        """하단 영구 표시 바의 퀵 프리셋 아이콘 스위처 UI 새로고침"""
        if not hasattr(self, 'quick_presets_layout'):
            return

        while self.quick_presets_layout.count():
            item = self.quick_presets_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        active_id = self._detect_active_preset_id()

        style_normal = """
            QPushButton {
                background-color: #101625;
                border: 1px solid #1F293D;
                border-radius: 6px;
                font-size: 13px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #1E293B;
                border-color: #818CF8;
            }
        """
        style_active = """
            QPushButton {
                background-color: rgba(99, 102, 241, 0.28);
                border: 1.5px solid #818CF8;
                border-radius: 6px;
                font-size: 13px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(99, 102, 241, 0.40);
                border-color: #A5B4FC;
            }
        """
        style_arrow_enabled = """
            QPushButton {
                background-color: #101625;
                border: 1px solid #1F293D;
                border-radius: 4px;
                color: #94A3B8;
                font-size: 10px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #1E293B;
                border-color: #818CF8;
                color: #FFFFFF;
            }
        """
        style_arrow_disabled = """
            QPushButton {
                background-color: transparent;
                border: 1px solid transparent;
                color: #334155;
                font-size: 10px;
                padding: 0px;
            }
        """

        # 1. 추천 빌트인 프리셋 아이콘 버튼 (BUILTIN_PRESETS SSOT)
        for p_key, p_def in self._builtin_presets().items():
            btn = QPushButton(p_def["icon"])
            btn.setFixedSize(26, 26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            st_text, _ = self._check_custom_preset_status(p_def)
            btn.setToolTip(self._format_preset_tooltip(self._preset_display_name(p_key, p_def), p_def, st_text))
            if p_key == active_id:
                btn.setStyleSheet(style_active)
            else:
                btn.setStyleSheet(style_normal)
            btn.clicked.connect(lambda _, pk=p_key: self._on_quick_preset_clicked(pk))
            self.quick_presets_layout.addWidget(btn)

        # 2. 사용자 커스텀 프리셋 (3개 초과 시 ◀ ▶ 화살표 페이징)
        custom_presets = self.config.get("custom_presets", {})
        if custom_presets:
            div = QFrame()
            div.setFrameShape(QFrame.Shape.VLine)
            div.setFrameShadow(QFrame.Shadow.Plain)
            div.setStyleSheet("color: #243048; background-color: #243048; width: 1px; margin: 3px 2px;")
            div.setFixedWidth(1)
            div.setFixedHeight(18)
            self.quick_presets_layout.addWidget(div)

            custom_items = list(custom_presets.items())
            total_custom = len(custom_items)
            page_size = 3
            total_pages = max(1, (total_custom + page_size - 1) // page_size)

            if self._custom_preset_page >= total_pages:
                self._custom_preset_page = max(0, total_pages - 1)

            if total_custom > page_size:
                btn_prev = QPushButton("◀")
                btn_prev.setFixedSize(18, 26)
                if self._custom_preset_page > 0:
                    btn_prev.setStyleSheet(style_arrow_enabled)
                    btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn_prev.clicked.connect(self._on_prev_custom_preset_page)
                else:
                    btn_prev.setStyleSheet(style_arrow_disabled)
                    btn_prev.setEnabled(False)
                self.quick_presets_layout.addWidget(btn_prev)

            start_idx = self._custom_preset_page * page_size
            page_items = custom_items[start_idx : start_idx + page_size]

            for idx, (p_id, p_info) in enumerate(page_items):
                p_name = p_info.get("name", tr("custom_preset"))
                icon, clean_name = self._get_custom_preset_icon_and_name(p_name, start_idx + idx, p_info)
                display_name = p_name if p_name.startswith(icon) else f"{icon} {clean_name}"
                btn_c = QPushButton(icon)
                btn_c.setFixedSize(26, 26)
                btn_c.setCursor(Qt.CursorShape.PointingHandCursor)

                p_cfg = p_info.get("config", {})
                st_text, _ = self._check_custom_preset_status(p_cfg)
                btn_c.setToolTip(self._format_preset_tooltip(display_name, p_cfg, st_text))
                if p_id == active_id:
                    btn_c.setStyleSheet(style_active)
                else:
                    btn_c.setStyleSheet(style_normal)
                btn_c.clicked.connect(lambda _, pid=p_id: self._on_quick_custom_preset_clicked(pid))
                self.quick_presets_layout.addWidget(btn_c)

            # 다음 페이지 등에서 아이콘 개수가 3개 미만이어도 3개 표시 영역만큼 폭을 일정하게 유지
            if total_custom > page_size:
                for _ in range(page_size - len(page_items)):
                    ph = QWidget()
                    ph.setFixedSize(26, 26)
                    ph.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    ph.setStyleSheet("background: transparent; border: none;")
                    self.quick_presets_layout.addWidget(ph)

            if total_custom > page_size:
                btn_next = QPushButton("▶")
                btn_next.setFixedSize(18, 26)
                if self._custom_preset_page < total_pages - 1:
                    btn_next.setStyleSheet(style_arrow_enabled)
                    btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn_next.clicked.connect(self._on_next_custom_preset_page)
                else:
                    btn_next.setStyleSheet(style_arrow_disabled)
                    btn_next.setEnabled(False)
                self.quick_presets_layout.addWidget(btn_next)

    def _on_quick_preset_clicked(self, preset_key: str):
        """하단 영구 바 추천 프리셋 클릭 핸들러 (모달 안내 없이 즉시 적용)"""
        p_key = "low_spec" if preset_key == "cloud" else preset_key
        self._active_preset_id = p_key
        self.apply_preset(p_key, notify=False)
        self._refresh_quick_presets_ui()

    def _on_quick_custom_preset_clicked(self, preset_id: str):
        """하단 영구 바 커스텀 프리셋 클릭 핸들러 (모달 안내 없이 즉시 적용)"""
        self._active_preset_id = preset_id
        self.apply_custom_preset(preset_id, notify=False)
        self._refresh_quick_presets_ui()

    def _on_prev_custom_preset_page(self):
        """커스텀 프리셋 이전 페이지"""
        if self._custom_preset_page > 0:
            self._custom_preset_page -= 1
            self._refresh_quick_presets_ui()

    def _on_next_custom_preset_page(self):
        """커스텀 프리셋 다음 페이지"""
        self._custom_preset_page += 1
        self._refresh_quick_presets_ui()

    def open_stt_model_manager(self, target_model_id: str = None):
        """STT 모델 관리 다이얼로그 열기"""
        if not isinstance(target_model_id, str):
            target_model_id = None
        default_stt = "small" if is_global() else "distil-small.en"
        from src.stt_model_dialog import STTModelDialog
        dlg = STTModelDialog(
            current_model_id=self.config.get("model_size", default_stt),
            device=self.config.get("device", "cpu"),
            target_model_id=target_model_id,
            parent=self
        )
        dlg.model_chosen.connect(self._on_stt_model_chosen_from_dialog)
        dlg.exec()
        self._populate_models()
        self._sync_all_pipeline_status()

    def _on_stt_model_chosen_from_dialog(self, model_id: str):
        """다이얼로그에서 STT 모델 선택 시 반영"""
        self.config["model_size"] = model_id
        from src.stt_model_manager import STTModelManager
        dev = str(self.config.get("device", "cpu")).lower()
        if dev == "cpu" and not STTModelManager.is_cpu_usable(model_id):
            from src.stt_engine import is_cuda_installed
            if is_cuda_installed():
                self.config["device"] = "cuda"
                self.config["compute_type"] = "float16"
                if hasattr(self, 'stt_thread') and self.stt_thread:
                    self.stt_thread.device = "cuda"
                    self.stt_thread.compute_type = "float16"

        cur_p = self.config.get("stt_provider", "local")
        src_lang = self.config.get("source_lang", "auto")
        if STTModelManager.is_multilingual_model(model_id, cur_p):
            if src_lang and src_lang != "auto":
                self.config["stt_language"] = src_lang
            else:
                self.config["stt_language"] = self.config.get("stt_language", "auto")
        else:
            self.config["stt_language"] = "en"

        self.save_config_cb(self.config)
        self._populate_models()
        if self.stt_thread:
            self.stt_thread.update_config(self.config)
            if hasattr(self.stt_thread, 'change_model'):
                self.stt_thread.change_model(model_id)
        self._sync_all_pipeline_status()

    def open_llm_model_manager(self, target_model_id: str = None):
        """로컬 번역 모델(LLM / NMT) 관리 다이얼로그 열기"""
        if not isinstance(target_model_id, str):
            target_model_id = None
        from src.llm_model_dialog import LLMModelDialog
        dlg = LLMModelDialog(
            current_backend=self.config.get("llm_backend", "embedded"),
            current_model=self.config.get("selected_llm_model", "exaone-3.5-2.4b"),
            current_engine=self.config.get("translation_engine", "hymt"),
            target_model_id=target_model_id,
            parent=self
        )
        dlg.llm_selected_signal.connect(self._on_llm_model_chosen_from_dialog)
        dlg.exec()
        self._refresh_all_status_badges()
        self._sync_all_pipeline_status()

    def _on_llm_model_chosen_from_dialog(self, backend: str, model_tag_or_id: str):
        """다이얼로그에서 LLM 또는 NMT 모델 선택 시 반영"""
        if backend == "ollama":
            self.config["llm_backend"] = "ollama"
            self.config["selected_llm_model"] = model_tag_or_id
            self.config["translation_engine"] = f"ollama:{model_tag_or_id}"
        else:
            self.config["llm_backend"] = "embedded"
            self.config["selected_llm_model"] = model_tag_or_id
            if "7.8b" in model_tag_or_id.lower() or "7b" in model_tag_or_id.lower():
                self.config["translation_engine"] = "exaone7b"
            elif "exaone" in model_tag_or_id:
                self.config["translation_engine"] = "exaone"
            elif "gemma" in model_tag_or_id:
                self.config["translation_engine"] = "gemma"
            elif "hymt" in model_tag_or_id or "hy-mt" in model_tag_or_id:
                self.config["translation_engine"] = "hymt"
            else:
                self.config["translation_engine"] = model_tag_or_id
        self.save_config_cb(self.config)
        self.set_engine_by_key(self.config["translation_engine"])
        if hasattr(self, 'trans_engine_buttons'):
            cur_eng = self.config.get("translation_engine", "")
            for btn, k in self.trans_engine_buttons:
                matched = (k == cur_eng) or (k == "exaone" and cur_eng in ["exaone", "exaone-3.5-2.4b"]) or (k == "exaone7b" and cur_eng in ["exaone7b", "exaone-3.5-7.8b"]) or (k == "gemma" and "gemma" in cur_eng)
                btn.setChecked(matched)

    def open_api_key_dialog(self):
        dlg = ApiKeyDialog(self.config, self)
        if dlg.exec():
            self.save_config_cb(self.config)
            if hasattr(self, 'input_card_deepl'):
                self.input_card_deepl.setText(self.config.get("deepl_api_key", ""))
            if hasattr(self, 'input_card_gemini'):
                self.input_card_gemini.setText(self.config.get("gemini_api_key", ""))
            if hasattr(self, 'input_card_groq'):
                self.input_card_groq.setText(self.config.get("groq_api_key", ""))
            if hasattr(self, 'input_card_deepgram'):
                self.input_card_deepgram.setText(self.config.get("deepgram_api_key", ""))
            self._populate_models()
            self._refresh_all_status_badges()
            self._sync_all_pipeline_status()

    def _revert_engine_ui(self):
        """이전 정상 번역 엔진으로 UI 버튼 및 오버레이 드롭다운 복귀"""
        cur_eng = self.config.get("translation_engine", "google")
        if hasattr(self, 'trans_engine_buttons'):
            for btn, k in self.trans_engine_buttons:
                matched = (k == cur_eng) or (k == "exaone" and cur_eng in ["exaone", "exaone-3.5-2.4b"]) or (k == "exaone7b" and cur_eng in ["exaone7b", "exaone-3.5-7.8b"]) or (k == "gemma" and "gemma" in str(cur_eng).lower()) or (k == "hymt" and "hymt" in str(cur_eng).lower())
                btn.blockSignals(True)
                btn.setChecked(matched)
                btn.blockSignals(False)
        if hasattr(self, 'overlay') and self.overlay:
            if hasattr(self.overlay, 'set_engine_by_key'):
                self.overlay.set_engine_by_key(cur_eng)
        self._sync_all_pipeline_status()

    def set_engine_by_key(self, engine_key: str, prompt_missing: bool = True):
        if not engine_key:
            return

        if engine_key in ("deepl", "gemini", "groq"):
            has_key = bool(self.config.get(f"{engine_key}_api_key", "").strip())
            if not has_key:
                if prompt_missing:
                    eng_names = {"deepl": "DeepL", "gemini": "Gemini Flash", "groq": "Groq Qwen 27B"}
                    disp_name = eng_names.get(engine_key, engine_key.upper())
                    ret = ask(self, "msg_need_key_title", "msg_open_key_settings", name=disp_name)
                    self._revert_engine_ui()
                    if ret == QMessageBox.StandardButton.Yes:
                        self.open_api_key_dialog()
                return

        model_tags = {
            "exaone": ("exaone3.5:2.4b", "exaone-3.5-2.4b"),
            "exaone-2.4b": ("exaone3.5:2.4b", "exaone-3.5-2.4b"),
            "exaone-3.5-2.4b": ("exaone3.5:2.4b", "exaone-3.5-2.4b"),
            "exaone7b": ("exaone3.5:7.8b", "exaone-3.5-7.8b"),
            "exaone-7b": ("exaone3.5:7.8b", "exaone-3.5-7.8b"),
            "exaone-3.5-7.8b": ("exaone3.5:7.8b", "exaone-3.5-7.8b"),
            "gemma": ("translategemma:4b", "translategemma-4b"),
            "translategemma": ("translategemma:4b", "translategemma-4b"),
            "translategemma-4b": ("translategemma:4b", "translategemma-4b"),
            "hymt": ("tencent/hy-mt2:1.8b", "hymt-2-1.8b"),
            "hy-mt": ("tencent/hy-mt2:1.8b", "hymt-2-1.8b"),
            "hymt-2-1.8b": ("tencent/hy-mt2:1.8b", "hymt-2-1.8b"),
        }
        if engine_key in model_tags:
            from src.llm_model_manager import LLMModelManager, RECOMMENDED_GGUF_MODELS
            eng_names = {
                "exaone": "EXAONE 2.4B",
                "exaone-2.4b": "EXAONE 2.4B",
                "exaone-3.5-2.4b": "EXAONE 2.4B",
                "exaone7b": "EXAONE 7.8B",
                "exaone-7b": "EXAONE 7.8B",
                "exaone-3.5-7.8b": "EXAONE 7.8B",
                "gemma": "TranslateGemma 4B",
                "translategemma": "TranslateGemma 4B",
                "translategemma-4b": "TranslateGemma 4B",
                "hymt": "Tencent Hy-MT2 1.8B",
                "hy-mt": "Tencent Hy-MT2 1.8B",
                "hymt-2-1.8b": "Tencent Hy-MT2 1.8B",
            }
            disp_name = eng_names.get(engine_key, engine_key)
            ollama_tag, embedded_id = model_tags[engine_key]

            # 1. 로컬 LLM의 GPU 가속 팩 설치 여부 검사 (CPU 모드 저속 실행 사전 차단 및 안내)
            has_cuda = LLMModelManager.is_cuda_binary_available()
            if not has_cuda:
                if not prompt_missing:
                    return
                if LLMModelManager.can_install_llm_cuda():
                    ret = ask(self, "msg_gpu_pack_needed_title", "msg_gpu_pack_needed", name=disp_name)
                    if ret == QMessageBox.StandardButton.Yes:
                        self.open_llm_model_manager(target_model_id=engine_key)
                    self._revert_engine_ui()
                    return
                else:
                    ret = ask(self, "msg_gpu_slow_title", "msg_gpu_slow", reason=LLMModelManager.llm_gpu_unavailable_reason(), name=disp_name)
                    if ret != QMessageBox.StandardButton.Yes:
                        self._revert_engine_ui()
                        return

            # 2. 모델 파일(.gguf) 설치 여부 검사
            model_info = next((m for m in RECOMMENDED_GGUF_MODELS if m.get("id") == embedded_id or engine_key in m.get("id", "").lower() or ("7.8b" in m.get("id", "").lower() and ("7b" in engine_key or "7.8b" in engine_key))), None)
            is_embedded_installed = model_info and LLMModelManager.is_gguf_model_installed(model_info, self.config.get("custom_model_dir"))
            if not is_embedded_installed:
                ollama_alive, _ = LLMModelManager.check_ollama_alive()
                ollama_installed = False
                if ollama_alive:
                    ollama_tag, _ = model_tags[engine_key]
                    ollama_installed = LLMModelManager.is_ollama_model_installed(ollama_tag)

                if not ollama_installed:
                    if prompt_missing:
                        ret = ask(self, "msg_model_missing_title", "msg_model_missing", name=disp_name)
                        if ret == QMessageBox.StandardButton.Yes:
                            self.open_llm_model_manager(target_model_id=engine_key)
                        self._revert_engine_ui()
                    return

            ollama_tag, embedded_id = model_tags[engine_key]
            if is_embedded_installed or not LLMModelManager.is_ollama_installed():
                self.config["llm_backend"] = "embedded"
                self.config["selected_llm_model"] = embedded_id
            else:
                self.config["selected_llm_model"] = (
                    ollama_tag if self.config.get("llm_backend") == "ollama" else embedded_id)

        self.config["translation_engine"] = engine_key
        if self.stt_thread and hasattr(self.stt_thread, 'translator') and self.stt_thread.translator:
            self.stt_thread.translator.update_config(self.config)
        if hasattr(self, 'screen_worker') and self.screen_worker:
            if hasattr(self.screen_worker, 'update_config'):
                self.screen_worker.update_config(self.config)
        self.save_config_cb(self.config)

        # 1. 설정 탭의 번역 엔진 라디오/토글 버튼 동기화
        if hasattr(self, 'trans_engine_buttons'):
            for btn, k in self.trans_engine_buttons:
                matched = (k == engine_key) or (k == "exaone" and engine_key in ["exaone", "exaone-3.5-2.4b"]) or (k == "exaone7b" and engine_key in ["exaone7b", "exaone-3.5-7.8b"]) or (k == "gemma" and "gemma" in str(engine_key).lower()) or (k == "hymt" and "hymt" in str(engine_key).lower())
                btn.blockSignals(True)
                btn.setChecked(matched)
                btn.blockSignals(False)

        # 2. 오디오 자막 오버레이 창 드롭다운/뱃지 동기화
        if hasattr(self, 'overlay') and self.overlay:
            if hasattr(self.overlay, 'set_engine_by_key'):
                self.overlay.set_engine_by_key(engine_key)
            elif hasattr(self.overlay, 'update_live_display'):
                self.overlay.update_live_display()

        # 3. 메인 상단 엔진 파이프라인 칩 바 동기화
        self._sync_all_pipeline_status()

        # 4. 실시간 상태 라벨 업데이트
        eng_names = {
            "deepl": "DeepL", "google": "Google", "gemini": "Gemini", "groq": "Groq Qwen",
            "gemma": "Gemma 4B", "exaone": "EXAONE 2.4B", "exaone7b": "EXAONE 7.8B",
            "hymt": "Hy-MT2 1.8B",
        }
        if engine_key.startswith("ollama:"):
            raw_tag = engine_key.split(":", 1)[1]
            tag_name = raw_tag.split(":")[0]
            if "7.8b" in tag_name.lower() or "7b" in tag_name.lower():
                disp = "EXAONE 7.8B (Ollama)"
            elif "exaone" in tag_name.lower():
                disp = "EXAONE 2.4B (Ollama)"
            elif "gemma" in tag_name.lower():
                disp = "Gemma 4B (Ollama)"
            elif "hy-mt" in tag_name.lower() or "hymt" in tag_name.lower():
                disp = "Hy-MT2 1.8B (Ollama)"
            else:
                disp = f"Ollama ({tag_name})"
        else:
            disp = eng_names.get(engine_key.lower(), engine_key.upper())
        self.update_engine_status("ready", tr("status_engine_changed", name=disp))

    def open_from_overlay(self):
        """오버레이창에서 ⚙️ 설정 버튼 클릭 시 전체화면(유튜브, 동영상 등) 위로 컨트롤 패널을 최상위로 띄움"""
        # 1. 최소화 상태 복원 및 가시화
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

        # 전체화면 앱(유튜브 등) 위로 확실히 올라오도록 Windows API 처리
        try:
            import ctypes
            hwnd = int(self.winId())

            # Windows 포그라운드 잠금 우회 (Alt 키 시뮬레이션)
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            ctypes.windll.user32.keybd_event(VK_MENU, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            # SW_RESTORE (9) 로 최소화 상태라도 확실하게 윈도우 복원
            SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)

            # TOPMOST 설정으로 전체화면(유튜브 등) 위로 강제 노출
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040
            HWND_TOPMOST = -1
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
            )
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.BringWindowToTop(hwnd)

            self._opened_from_overlay_topmost = True
        except Exception:
            pass

    def _release_topmost_flag(self, hwnd=None):
        """일시적 TOPMOST 플래그 해제 (항상-위 고정 방지)"""
        try:
            import ctypes
            if hwnd is None:
                hwnd = int(self.winId())
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            HWND_NOTOPMOST = -2
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            )
        except Exception:
            pass

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow() and getattr(self, '_opened_from_overlay_topmost', False):
                # 다른 외부 앱(유튜브 전체화면, 브라우저 등)으로 포커스가 넘어갔을 때만 TOPMOST 해제하여 창 순서 정상화
                active_w = QApplication.activeWindow()
                if active_w is None or (active_w is not self and active_w.parent() != self):
                    self._release_topmost_flag()
                    self._opened_from_overlay_topmost = False

    def _get_stt_model_note_text(self) -> str:
        default_model = "small" if is_global() else "distil-small.en"
        try:
            from src.stt_model_manager import STTModelManager
            if STTModelManager.is_bundled_model(default_model):
                return f"ⓘ {default_model} {tr('model_bundled')}"
            elif STTModelManager.is_model_installed(default_model):
                return f"ⓘ {default_model} {tr('model_installed')}"
            else:
                return f"ⓘ {default_model} ({tr('stt_auto_download_first')})"
        except Exception:
            return f"ⓘ {default_model} {tr('model_bundled')}"

    def _populate_models(self):
        if hasattr(self, 'combo_model'):
            self.combo_model.blockSignals(True)
            self.combo_model.clear()
            cur_p = self.config.get("stt_provider", "local")
            icon_green = _make_status_circle_icon("#10B981", 10)
            icon_red = _make_status_circle_icon("#EF4444", 10)

            if cur_p == "deepgram":
                if hasattr(self, 'lbl_model_sub'):
                    self.lbl_model_sub.setText(tr("stt_sub_deepgram"))
                if hasattr(self, 'lbl_stt_model_note'):
                    self.lbl_stt_model_note.setText(tr("stt_note_deepgram"))
                    self.lbl_stt_model_note.setVisible(True)
                from src.stt_model_manager import AVAILABLE_DEEPGRAM_STT_MODELS
                cur = self.config.get("deepgram_model", "nova-3")
                has_key = bool(self.config.get("deepgram_api_key", "").strip())
                icon = icon_green if has_key else icon_red
                cur_idx = 0
                for i, m in enumerate(AVAILABLE_DEEPGRAM_STT_MODELS):
                    m_id = m["id"]
                    self.combo_model.addItem(icon, m_id, m_id)
                    self.combo_model.setItemData(i, f"{m['name']} · {get_model_desc(m)}", Qt.ItemDataRole.ToolTipRole)
                    if m_id == cur:
                        cur_idx = i
                self.combo_model.setCurrentIndex(cur_idx)
            elif cur_p == "groq":
                if hasattr(self, 'lbl_model_sub'):
                    self.lbl_model_sub.setText(tr("stt_sub_groq"))
                if hasattr(self, 'lbl_stt_model_note'):
                    self.lbl_stt_model_note.setText(tr("stt_note_groq"))
                    self.lbl_stt_model_note.setVisible(True)
                from src.stt_model_manager import AVAILABLE_GROQ_STT_MODELS
                cur = self.config.get("groq_model", "whisper-large-v3-turbo")
                has_key = bool(self.config.get("groq_api_key", "").strip())
                icon = icon_green if has_key else icon_red
                cur_idx = 0
                for i, m in enumerate(AVAILABLE_GROQ_STT_MODELS):
                    m_id = m["id"]
                    self.combo_model.addItem(icon, m_id, m_id)
                    self.combo_model.setItemData(i, f"{m['name']} · {get_model_desc(m)}", Qt.ItemDataRole.ToolTipRole)
                    if m_id == cur:
                        cur_idx = i
                self.combo_model.setCurrentIndex(cur_idx)
            else:
                dev = str(self.config.get("device", "cpu")).lower()
                is_cpu = (dev == "cpu")
                if hasattr(self, 'lbl_model_sub'):
                    if is_cpu:
                        self.lbl_model_sub.setText(tr("stt_sub_cpu"))
                    else:
                        self.lbl_model_sub.setText(tr("stt_sub_cuda"))
                if hasattr(self, 'lbl_stt_model_note'):
                    self.lbl_stt_model_note.setText(self._get_stt_model_note_text())
                    self.lbl_stt_model_note.setVisible(True)
                from src.stt_model_manager import AVAILABLE_STT_MODELS, STTModelManager
                default_stt = "small" if is_global() else "distil-small.en"
                cur = self.config.get("model_size", default_stt)

                models_to_show = AVAILABLE_STT_MODELS
                cur_idx = 0
                for i, m in enumerate(models_to_show):
                    m_id = m["id"]
                    installed = STTModelManager.is_model_installed(m_id)
                    bundled = STTModelManager.is_bundled_model(m_id)
                    is_usable = installed or bundled
                    icon = icon_green if is_usable else icon_red
                    self.combo_model.addItem(icon, m_id, m_id)
                    self.combo_model.setItemData(i, f"{m['name']} · {get_model_desc(m)}", Qt.ItemDataRole.ToolTipRole)
                    if m_id == cur:
                        cur_idx = i
                self.combo_model.setCurrentIndex(cur_idx)
            self.combo_model.blockSignals(False)

    def _revert_model_selection(self):
        """이전에 선택되어 있던 활성 모델로 콤보박스 인덱스 되돌리기"""
        if not hasattr(self, 'combo_model'):
            return
        self.combo_model.blockSignals(True)
        cur_p = self.config.get("stt_provider", "local")
        if cur_p == "deepgram":
            cur_model = self.config.get("deepgram_model", "nova-3")
        elif cur_p == "groq":
            cur_model = self.config.get("groq_model", "whisper-large-v3-turbo")
        else:
            default_stt = "small" if is_global() else "distil-small.en"
            cur_model = self.config.get("model_size", default_stt)

        for i in range(self.combo_model.count()):
            if self.combo_model.itemData(i) == cur_model:
                self.combo_model.setCurrentIndex(i)
                break
        self.combo_model.blockSignals(False)

    def _download_stt_model_direct(self, model_info: dict):
        """콤보박스에서 사용불가 모델 선택 시 바로 다운로드 수행"""
        from src.stt_model_manager import STTDownloadWorker

        m_id = model_info["id"]
        m_name = model_info.get("name", m_id)

        progress_dlg = QProgressDialog(tr("dlg_downloading_model", name=m_name), tr("btn_cancel"), 0, 100, self)
        progress_dlg.setWindowTitle(tr("progress_stt_title"))
        progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.setValue(10)
        progress_dlg.setStyleSheet(f"""
            QProgressDialog {{
                background-color: {COLOR_BG_DARK};
                color: {COLOR_TEXT_PRIMARY};
            }}
            QLabel {{
                color: {COLOR_TEXT_PRIMARY};
                font-size: 12px;
            }}
            QPushButton {{
                background-color: #1E293B;
                color: #EF4444;
                border: 1px solid #334155;
                border-radius: 5px;
                padding: 6px 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(239, 68, 68, 0.2);
            }}
        """)

        worker = STTDownloadWorker(model_info, parent=None)
        self._active_stt_worker = worker

        def _on_progress(model_id, percent, msg):
            if model_id == m_id and not progress_dlg.wasCanceled():
                progress_dlg.setValue(percent)
                progress_dlg.setLabelText(f"[{model_id}] {msg} ({percent}%)")

        def _on_finished(model_id, success, msg):
            progress_dlg.close()
            self._active_progress_dlg = None
            self._active_stt_worker = None

            if success:
                self.config["model_size"] = model_id
                self.save_config_cb(self.config)
                self._populate_models()
                if self.stt_thread:
                    self.stt_thread.update_config(self.config)
                    if hasattr(self.stt_thread, 'change_model'):
                        self.stt_thread.change_model(model_id)
                self._sync_all_pipeline_status()
                tell(self, "msg_download_switched_title", "msg_stt_download_done", name=m_name)
            else:
                self._revert_model_selection()
                if not is_cancel_message(msg):
                    tell(self, "msg_download_switched_title", "msg_download_fail", kind="warn", error=msg)

        progress_dlg.canceled.connect(worker.cancel)
        worker.progress_signal.connect(_on_progress)
        worker.finished_signal.connect(_on_finished)
        self._active_progress_dlg = progress_dlg
        self._active_stt_worker = worker
        worker.start()
        progress_dlg.show()

    def on_device_changed(self, idx):
        key = self.device_keys[idx]
        if key == "deepgram":
            self.config["stt_provider"] = "deepgram"
            if self.config.get("device") in ("groq", "deepgram"):
                self.config["device"] = "cuda"
        elif key == "groq":
            self.config["stt_provider"] = "groq"
            if self.config.get("device") in ("groq", "deepgram"):
                self.config["device"] = "cuda"
        else:
            if key == "cuda":
                from src.stt_engine import is_cuda_installed
                from src.llm_model_manager import LLMModelManager
                if not is_cuda_installed():
                    if not LLMModelManager.is_nvidia_gpu_present():
                        self._show_no_nvidia_notice()
                        return
                    ret = ask(self, "msg_cuda_pack_title", "msg_cuda_pack")
                    self._sync_stt_buttons_ui()
                    if ret == QMessageBox.StandardButton.Yes:
                        self.open_llm_model_manager()
                    return

            self.config["stt_provider"] = "local"
            self.config["device"] = key
            if key == "cpu":
                from src.stt_model_manager import STTModelManager
                fallback_stt = "small" if is_global() else "distil-small.en"
                cur_model = self.config.get("model_size", fallback_stt)
                if not STTModelManager.is_cpu_usable(cur_model):
                    self.config["model_size"] = fallback_stt

        from src.stt_model_manager import STTModelManager
        cur_p = self.config.get("stt_provider", "local")
        fallback_stt = "small" if is_global() else "distil-small.en"
        cur_m = self.config.get("deepgram_model", "nova-3") if cur_p == "deepgram" else (
            self.config.get("groq_model", "whisper-large-v3-turbo") if cur_p == "groq" else self.config.get("model_size", fallback_stt)
        )
        if not STTModelManager.is_multilingual_model(cur_m, cur_p):
            if self.config.get("stt_language", "en") != "en":
                self.config["stt_language"] = "en"

        self.save_config_cb(self.config)
        self._populate_models()
        if hasattr(self, 'stt_thread') and self.stt_thread:
            # 장치가 바뀌면 update_config 가 리로드를 예약하고 STT 스레드가 다시 로드한다.
            self.stt_thread.update_config(self.config)
            # 로컬 LLM 의 GPU 오프로드 여부도 device 설정을 따르므로 다음 번역 때 새로 로드하게 한다.
            translator = getattr(self.stt_thread, 'translator', None)
            if key in ("cuda", "cpu") and translator is not None and hasattr(translator, 'unload_local_models'):
                translator.unload_local_models()
        if hasattr(self, 'audio_thread') and self.audio_thread:
            self.audio_thread.update_config(self.config)
        if getattr(self, 'overlay', None) is not None and hasattr(self.overlay, 'update_live_display'):
            self.overlay.update_live_display()
        if hasattr(self, 'stt_buttons'):
            for btn, k in self.stt_buttons:
                btn.blockSignals(True)
                btn.setChecked(k == key)
                btn.blockSignals(False)
        self._sync_all_pipeline_status()

    def on_model_changed(self, idx):
        if idx < 0:
            return
        m = self.combo_model.itemData(idx) or self.combo_model.currentText()
        if not m:
            return

        cur_provider = self.config.get("stt_provider", "local")
        if cur_provider == "deepgram":
            has_key = bool(self.config.get("deepgram_api_key", "").strip())
            if not has_key:
                ret = ask(self, "msg_need_key_title", "msg_open_key_settings", name=f"Deepgram {m}")
                self._revert_model_selection()
                if ret == QMessageBox.StandardButton.Yes:
                    self.open_api_key_dialog()
                return
            self.config["deepgram_model"] = m
            if self.stt_thread:
                self.stt_thread.update_config(self.config)
            self.save_config_cb(self.config)
            self._sync_all_pipeline_status()
            return
        elif cur_provider == "groq":
            has_key = bool(self.config.get("groq_api_key", "").strip())
            if not has_key:
                ret = ask(self, "msg_need_key_title", "msg_open_key_settings", name=f"Groq {m}")
                self._revert_model_selection()
                if ret == QMessageBox.StandardButton.Yes:
                    self.open_api_key_dialog()
                return
            self.config["groq_model"] = m
            if self.stt_thread:
                self.stt_thread.update_config(self.config)
            self.save_config_cb(self.config)
            self._sync_all_pipeline_status()
            return

        # 로컬 Whisper 모델
        from src.stt_model_manager import STTModelManager, AVAILABLE_STT_MODELS
        is_usable = STTModelManager.is_model_installed(m) or STTModelManager.is_bundled_model(m)

        if not is_usable:
            self._revert_model_selection()
            ret = ask(self, "msg_model_missing_title", "msg_model_missing", name=m)
            if ret == QMessageBox.StandardButton.Yes:
                self.open_stt_model_manager(target_model_id=m)
            return

        # 사용 가능한 모델 적용
        self.config["model_size"] = m
        dev = str(self.config.get("device", "cpu")).lower()
        if dev == "cpu" and not STTModelManager.is_cpu_usable(m):
            from src.stt_engine import is_cuda_installed
            if is_cuda_installed():
                self.config["device"] = "cuda"
                self.config["compute_type"] = "float16"
                if hasattr(self, 'stt_thread') and self.stt_thread:
                    self.stt_thread.device = "cuda"
                    self.stt_thread.compute_type = "float16"

        cur_p = self.config.get("stt_provider", "local")
        src_lang = self.config.get("source_lang", "auto")
        if STTModelManager.is_multilingual_model(m, cur_p):
            if src_lang and src_lang != "auto":
                self.config["stt_language"] = src_lang
            else:
                self.config["stt_language"] = self.config.get("stt_language", "auto")
        else:
            self.config["stt_language"] = "en"

        if self.stt_thread:
            self.stt_thread.update_config(self.config)
            if hasattr(self.stt_thread, 'change_model'):
                self.stt_thread.change_model(m)
        self.save_config_cb(self.config)
        self._sync_all_pipeline_status()

    # ------------------------------------------------------------------
    # 음성 번역 자막 전용 컨트롤 핸들러
    # ------------------------------------------------------------------
    def on_audio_font_slider_changed(self, val, label=None):
        self.config["audio_font_size"] = val
        self.config["font_size"] = val
        if hasattr(self, 'audio_font_slider') and self.audio_font_slider.value() != val:
            self.audio_font_slider.blockSignals(True)
            self.audio_font_slider.setValue(val)
            self.audio_font_slider.blockSignals(False)
        if hasattr(self, 'audio_font_label'):
            self.audio_font_label.setText(f"{val}px")
        if self.overlay:
            if hasattr(self.overlay, "update_font_size"):
                self.overlay.update_font_size(val)
            elif hasattr(self.overlay, "set_font_size"):
                self.overlay.set_font_size(val)
        elif self.screen_overlay:
            if hasattr(self.screen_overlay, "update_font_size"):
                self.screen_overlay.update_font_size(val)
            elif hasattr(self.screen_overlay, "set_font_size"):
                self.screen_overlay.set_font_size(val)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_audio_opacity_slider_changed(self, val, label=None):
        pct = val / 100.0
        self.config["audio_overlay_bg_opacity"] = pct
        self.config["overlay_bg_opacity"] = pct
        if hasattr(self, 'audio_opacity_slider') and self.audio_opacity_slider.value() != val:
            self.audio_opacity_slider.blockSignals(True)
            self.audio_opacity_slider.setValue(val)
            self.audio_opacity_slider.blockSignals(False)
        if hasattr(self, 'audio_opacity_label'):
            self.audio_opacity_label.setText(f"{val}%")
        if self.overlay:
            if hasattr(self.overlay, "update_opacity"):
                self.overlay.update_opacity(pct)
            elif hasattr(self.overlay, "set_bg_opacity"):
                self.overlay.set_bg_opacity(pct)
        elif self.screen_overlay:
            if hasattr(self.screen_overlay, "update_opacity"):
                self.screen_overlay.update_opacity(pct)
            elif hasattr(self.screen_overlay, "set_bg_opacity"):
                self.screen_overlay.set_bg_opacity(pct)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_audio_stroke_slider_changed(self, val: int):
        self.config["audio_subtitle_stroke_width"] = val
        self.config["subtitle_stroke_width"] = val
        if hasattr(self, 'audio_lbl_stroke'):
            self.audio_lbl_stroke.setText(f"{val}px")
        if self.overlay:
            self.overlay.set_stroke_width(val)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_audio_spacing_slider_changed(self, int_val: int):
        val = int_val / 10.0
        self.config["audio_letter_spacing"] = val
        self.config["letter_spacing"] = val
        if hasattr(self, 'audio_lbl_spacing'):
            self.audio_lbl_spacing.setText(f"{val:.1f}px")
        if self.overlay:
            self.overlay.set_letter_spacing(val)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_audio_duration_slider_changed(self, val: int):
        self.config["audio_subtitle_duration"] = val
        self.config["subtitle_duration"] = val
        if hasattr(self, 'audio_slider_duration') and self.audio_slider_duration.value() != val:
            self.audio_slider_duration.blockSignals(True)
            self.audio_slider_duration.setValue(val)
            self.audio_slider_duration.blockSignals(False)
        if hasattr(self, 'audio_lbl_duration'):
            self.audio_lbl_duration.setText(self._duration_text(val))
        if self.overlay:
            if hasattr(self.overlay, "set_subtitle_duration"):
                self.overlay.set_subtitle_duration(val)
            elif hasattr(self.overlay, "update_duration"):
                self.overlay.update_duration(val)
            elif hasattr(self.overlay, "apply_config"):
                self.overlay.apply_config(apply_geometry=False)
            elif hasattr(self.overlay, "_apply_config"):
                self.overlay._apply_config(apply_geometry=False)
        self.save_config_cb(self.config)

    def on_audio_show_speaker_toggled(self, checked: bool):
        self.config["audio_show_speaker"] = checked
        self.config["show_speaker"] = checked
        if hasattr(self, 'audio_cb_show_speaker') and self.audio_cb_show_speaker.isChecked() != checked:
            self.audio_cb_show_speaker.blockSignals(True)
            self.audio_cb_show_speaker.setChecked(checked)
            self.audio_cb_show_speaker.blockSignals(False)
        if self.overlay and hasattr(self.overlay, "set_show_speaker"):
            self.overlay.set_show_speaker(checked)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_audio_show_original_toggled(self, checked: bool):
        self.config["audio_show_original"] = checked
        self.config["show_original"] = checked
        if hasattr(self, 'audio_cb_show_original') and self.audio_cb_show_original.isChecked() != checked:
            self.audio_cb_show_original.blockSignals(True)
            self.audio_cb_show_original.setChecked(checked)
            self.audio_cb_show_original.blockSignals(False)
        if self.overlay:
            if hasattr(self.overlay, "set_show_original"):
                self.overlay.set_show_original(checked)
            else:
                self.overlay.show_original = checked
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_audio_show_translated_toggled(self, checked: bool):
        self.config["audio_show_translated"] = checked
        self.config["show_translated"] = checked
        if hasattr(self, 'audio_cb_show_translated') and self.audio_cb_show_translated.isChecked() != checked:
            self.audio_cb_show_translated.blockSignals(True)
            self.audio_cb_show_translated.setChecked(checked)
            self.audio_cb_show_translated.blockSignals(False)
        if self.overlay:
            if hasattr(self.overlay, "set_show_translated"):
                self.overlay.set_show_translated(checked)
            else:
                self.overlay.show_translated = checked
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_audio_show_badge_toggled(self, checked: bool):
        self.config["audio_show_engine_badge"] = checked
        self.config["show_engine_badge"] = checked
        if hasattr(self, 'audio_cb_show_badge') and self.audio_cb_show_badge.isChecked() != checked:
            self.audio_cb_show_badge.blockSignals(True)
            self.audio_cb_show_badge.setChecked(checked)
            self.audio_cb_show_badge.blockSignals(False)
        if self.overlay:
            if hasattr(self.overlay, "set_badge_visible"):
                self.overlay.set_badge_visible(checked)
            else:
                self.overlay.show_engine_badge = checked
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_audio_click_through_toggled(self, checked: bool):
        self.config["audio_click_through"] = checked
        self.config["click_through"] = checked
        if hasattr(self, 'audio_cb_click_through') and self.audio_cb_click_through.isChecked() != checked:
            self.audio_cb_click_through.blockSignals(True)
            self.audio_cb_click_through.setChecked(checked)
            self.audio_cb_click_through.blockSignals(False)
        if self.overlay:
            self.overlay.set_click_through(checked)
        self.save_config_cb(self.config)

    def on_audio_clean_text_toggled(self, checked: bool):
        self.config["audio_clean_text_mode"] = checked
        self.config["clean_text_mode"] = checked
        if hasattr(self, 'audio_cb_clean_text') and self.audio_cb_clean_text.isChecked() != checked:
            self.audio_cb_clean_text.blockSignals(True)
            self.audio_cb_clean_text.setChecked(checked)
            self.audio_cb_clean_text.blockSignals(False)
        if self.overlay and hasattr(self.overlay, "set_clean_mode"):
            self.overlay.set_clean_mode(checked)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_audio_clean_box_toggled(self, checked: bool):
        self.config["audio_clean_box"] = checked
        self.config["clean_box"] = checked
        if hasattr(self, 'audio_cb_clean_box') and self.audio_cb_clean_box.isChecked() != checked:
            self.audio_cb_clean_box.blockSignals(True)
            self.audio_cb_clean_box.setChecked(checked)
            self.audio_cb_clean_box.blockSignals(False)
        if self.overlay and hasattr(self.overlay, "set_clean_box"):
            self.overlay.set_clean_box(checked)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_audio_font_from_overlay(self, val):
        self.config["audio_font_size"] = val
        self.config["font_size"] = val
        if hasattr(self, 'audio_font_slider'):
            self.audio_font_slider.blockSignals(True)
            self.audio_font_slider.setValue(val)
            self.audio_font_slider.blockSignals(False)
        if hasattr(self, 'audio_font_label'):
            self.audio_font_label.setText(f"{val}px")
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_audio_opacity_from_overlay(self, pct):
        val = float(pct)
        if val <= 1.0:
            val = val * 100.0
        val_int = int(round(val))
        pct_float = val_int / 100.0
        self.config["audio_overlay_bg_opacity"] = pct_float
        self.config["overlay_bg_opacity"] = pct_float
        if hasattr(self, 'audio_opacity_slider'):
            self.audio_opacity_slider.blockSignals(True)
            self.audio_opacity_slider.setValue(val_int)
            self.audio_opacity_slider.blockSignals(False)
        if hasattr(self, 'audio_opacity_label'):
            self.audio_opacity_label.setText(f"{val_int}%")
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_audio_click_through_from_overlay(self, checked):
        self.config["audio_click_through"] = checked
        self.config["click_through"] = checked
        if hasattr(self, 'audio_cb_click_through'):
            self.audio_cb_click_through.blockSignals(True)
            self.audio_cb_click_through.setChecked(checked)
            self.audio_cb_click_through.blockSignals(False)
        self.save_config_cb(self.config)

    def sync_audio_clean_text_from_overlay(self, checked):
        self.config["audio_clean_text_mode"] = checked
        self.config["clean_text_mode"] = checked
        if hasattr(self, 'audio_cb_clean_text'):
            self.audio_cb_clean_text.blockSignals(True)
            self.audio_cb_clean_text.setChecked(checked)
            self.audio_cb_clean_text.blockSignals(False)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_audio_show_speaker_from_overlay(self, checked):
        self.config["audio_show_speaker"] = checked
        self.config["show_speaker"] = checked
        if hasattr(self, 'audio_cb_show_speaker'):
            self.audio_cb_show_speaker.blockSignals(True)
            self.audio_cb_show_speaker.setChecked(checked)
            self.audio_cb_show_speaker.blockSignals(False)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_audio_show_original_from_overlay(self, checked):
        self.config["audio_show_original"] = checked
        self.config["show_original"] = checked
        if hasattr(self, 'audio_cb_show_original'):
            self.audio_cb_show_original.blockSignals(True)
            self.audio_cb_show_original.setChecked(checked)
            self.audio_cb_show_original.blockSignals(False)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_audio_show_translated_from_overlay(self, checked):
        self.config["audio_show_translated"] = checked
        self.config["show_translated"] = checked
        if hasattr(self, 'audio_cb_show_translated'):
            self.audio_cb_show_translated.blockSignals(True)
            self.audio_cb_show_translated.setChecked(checked)
            self.audio_cb_show_translated.blockSignals(False)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    # ------------------------------------------------------------------
    # 화면 번역 자막 전용 컨트롤 핸들러
    # ------------------------------------------------------------------
    def on_screen_font_slider_changed(self, val, label=None):
        self.config["screen_font_size"] = val
        roi_configs = self.config.get("roi_configs", {})
        if isinstance(roi_configs, dict):
            for r_cfg in roi_configs.values():
                if isinstance(r_cfg, dict):
                    r_cfg["font_size"] = val
        if hasattr(self, 'screen_font_slider') and self.screen_font_slider.value() != val:
            self.screen_font_slider.blockSignals(True)
            self.screen_font_slider.setValue(val)
            self.screen_font_slider.blockSignals(False)
        if hasattr(self, 'screen_font_label'):
            self.screen_font_label.setText(f"{val}px")
        if self.screen_overlay:
            if hasattr(self.screen_overlay, "update_font_size"):
                self.screen_overlay.update_font_size(val)
            elif hasattr(self.screen_overlay, "set_font_size"):
                self.screen_overlay.set_font_size(val)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_screen_opacity_slider_changed(self, val, label=None):
        pct = val / 100.0
        self.config["screen_overlay_bg_opacity"] = pct
        roi_configs = self.config.get("roi_configs", {})
        if isinstance(roi_configs, dict):
            for r_cfg in roi_configs.values():
                if isinstance(r_cfg, dict):
                    r_cfg["opacity"] = val
        if hasattr(self, 'screen_opacity_slider') and self.screen_opacity_slider.value() != val:
            self.screen_opacity_slider.blockSignals(True)
            self.screen_opacity_slider.setValue(val)
            self.screen_opacity_slider.blockSignals(False)
        if hasattr(self, 'screen_opacity_label'):
            self.screen_opacity_label.setText(f"{val}%")
        if self.screen_overlay:
            if hasattr(self.screen_overlay, "update_opacity"):
                self.screen_overlay.update_opacity(pct)
            elif hasattr(self.screen_overlay, "set_bg_opacity"):
                self.screen_overlay.set_bg_opacity(pct)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_screen_stroke_slider_changed(self, val: int):
        self.config["screen_subtitle_stroke_width"] = val
        if hasattr(self, 'screen_lbl_stroke'):
            self.screen_lbl_stroke.setText(f"{val}px")
        if self.screen_overlay:
            self.screen_overlay.set_stroke_width(val)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_screen_spacing_slider_changed(self, int_val: int):
        val = int_val / 10.0
        self.config["screen_letter_spacing"] = val
        if hasattr(self, 'screen_lbl_spacing'):
            self.screen_lbl_spacing.setText(f"{val:.1f}px")
        if self.screen_overlay:
            self.screen_overlay.set_letter_spacing(val)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_screen_duration_slider_changed(self, val: int):
        self.config["screen_subtitle_duration"] = val
        roi_configs = self.config.get("roi_configs", {})
        if isinstance(roi_configs, dict):
            for r_cfg in roi_configs.values():
                if isinstance(r_cfg, dict):
                    r_cfg["duration"] = val
        if hasattr(self, 'screen_slider_duration') and self.screen_slider_duration.value() != val:
            self.screen_slider_duration.blockSignals(True)
            self.screen_slider_duration.setValue(val)
            self.screen_slider_duration.blockSignals(False)
        if hasattr(self, 'screen_lbl_duration'):
            self.screen_lbl_duration.setText(self._duration_text(val))
        if self.screen_overlay:
            if hasattr(self.screen_overlay, "set_subtitle_duration"):
                self.screen_overlay.set_subtitle_duration(val)
            elif hasattr(self.screen_overlay, "update_duration"):
                self.screen_overlay.update_duration(val)
            elif hasattr(self.screen_overlay, "apply_config"):
                self.screen_overlay.apply_config(apply_geometry=False)
            elif hasattr(self.screen_overlay, "_apply_config"):
                self.screen_overlay._apply_config(apply_geometry=False)
        self.save_config_cb(self.config)

    def on_screen_show_speaker_toggled(self, checked: bool):
        self.config["screen_show_speaker"] = checked
        if hasattr(self, 'screen_cb_show_speaker') and self.screen_cb_show_speaker.isChecked() != checked:
            self.screen_cb_show_speaker.blockSignals(True)
            self.screen_cb_show_speaker.setChecked(checked)
            self.screen_cb_show_speaker.blockSignals(False)
        if self.screen_overlay and hasattr(self.screen_overlay, "set_show_speaker"):
            self.screen_overlay.set_show_speaker(checked)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_screen_show_original_toggled(self, checked: bool):
        self.config["screen_show_original"] = checked
        if hasattr(self, 'screen_cb_show_original') and self.screen_cb_show_original.isChecked() != checked:
            self.screen_cb_show_original.blockSignals(True)
            self.screen_cb_show_original.setChecked(checked)
            self.screen_cb_show_original.blockSignals(False)
        if self.screen_overlay:
            if hasattr(self.screen_overlay, "set_show_original"):
                self.screen_overlay.set_show_original(checked)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_screen_show_translated_toggled(self, checked: bool):
        self.config["screen_show_translated"] = checked
        if hasattr(self, 'screen_cb_show_translated') and self.screen_cb_show_translated.isChecked() != checked:
            self.screen_cb_show_translated.blockSignals(True)
            self.screen_cb_show_translated.setChecked(checked)
            self.screen_cb_show_translated.blockSignals(False)
        if self.screen_overlay:
            if hasattr(self.screen_overlay, "set_show_translated"):
                self.screen_overlay.set_show_translated(checked)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_screen_show_badge_toggled(self, checked: bool):
        self.config["screen_show_engine_badge"] = checked
        if hasattr(self, 'screen_cb_show_badge') and self.screen_cb_show_badge.isChecked() != checked:
            self.screen_cb_show_badge.blockSignals(True)
            self.screen_cb_show_badge.setChecked(checked)
            self.screen_cb_show_badge.blockSignals(False)
        if self.screen_overlay:
            if hasattr(self.screen_overlay, "set_badge_visible"):
                self.screen_overlay.set_badge_visible(checked)
            else:
                for o in getattr(self.screen_overlay, 'overlays', []):
                    if hasattr(o, 'live_badge'):
                        o.live_badge.setVisible(checked)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_screen_click_through_toggled(self, checked: bool):
        self.config["screen_click_through"] = checked
        if hasattr(self, 'screen_cb_click_through') and self.screen_cb_click_through.isChecked() != checked:
            self.screen_cb_click_through.blockSignals(True)
            self.screen_cb_click_through.setChecked(checked)
            self.screen_cb_click_through.blockSignals(False)
        if self.screen_overlay:
            self.screen_overlay.set_click_through(checked)
        self.save_config_cb(self.config)

    def on_screen_clean_text_toggled(self, checked: bool):
        self.config["screen_clean_text_mode"] = checked
        if hasattr(self, 'screen_cb_clean_text') and self.screen_cb_clean_text.isChecked() != checked:
            self.screen_cb_clean_text.blockSignals(True)
            self.screen_cb_clean_text.setChecked(checked)
            self.screen_cb_clean_text.blockSignals(False)
        if self.screen_overlay and hasattr(self.screen_overlay, "set_clean_mode"):
            self.screen_overlay.set_clean_mode(checked)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_screen_clean_box_toggled(self, checked: bool):
        self.config["screen_clean_box"] = checked
        if hasattr(self, 'screen_cb_clean_box') and self.screen_cb_clean_box.isChecked() != checked:
            self.screen_cb_clean_box.blockSignals(True)
            self.screen_cb_clean_box.setChecked(checked)
            self.screen_cb_clean_box.blockSignals(False)
        if self.screen_overlay and hasattr(self.screen_overlay, "set_clean_box"):
            self.screen_overlay.set_clean_box(checked)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_screen_font_from_overlay(self, val):
        self.config["screen_font_size"] = val
        roi_configs = self.config.get("roi_configs", {})
        if isinstance(roi_configs, dict):
            for r_cfg in roi_configs.values():
                if isinstance(r_cfg, dict):
                    r_cfg["font_size"] = val
        if hasattr(self, 'screen_font_slider'):
            self.screen_font_slider.blockSignals(True)
            self.screen_font_slider.setValue(val)
            self.screen_font_slider.blockSignals(False)
        if hasattr(self, 'screen_font_label'):
            self.screen_font_label.setText(f"{val}px")
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_screen_opacity_from_overlay(self, pct):
        val = float(pct)
        if val <= 1.0:
            val = val * 100.0
        val_int = int(round(val))
        pct_float = val_int / 100.0
        self.config["screen_overlay_bg_opacity"] = pct_float
        roi_configs = self.config.get("roi_configs", {})
        if isinstance(roi_configs, dict):
            for r_cfg in roi_configs.values():
                if isinstance(r_cfg, dict):
                    r_cfg["opacity"] = val_int
        if hasattr(self, 'screen_opacity_slider'):
            self.screen_opacity_slider.blockSignals(True)
            self.screen_opacity_slider.setValue(val_int)
            self.screen_opacity_slider.blockSignals(False)
        if hasattr(self, 'screen_opacity_label'):
            self.screen_opacity_label.setText(f"{val_int}%")
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_screen_click_through_from_overlay(self, checked):
        self.config["screen_click_through"] = checked
        if hasattr(self, 'screen_cb_click_through'):
            self.screen_cb_click_through.blockSignals(True)
            self.screen_cb_click_through.setChecked(checked)
            self.screen_cb_click_through.blockSignals(False)
        self.save_config_cb(self.config)

    def sync_screen_clean_text_from_overlay(self, checked):
        self.config["screen_clean_text_mode"] = checked
        if hasattr(self, 'screen_cb_clean_text'):
            self.screen_cb_clean_text.blockSignals(True)
            self.screen_cb_clean_text.setChecked(checked)
            self.screen_cb_clean_text.blockSignals(False)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_screen_show_speaker_from_overlay(self, checked):
        self.config["screen_show_speaker"] = checked
        if hasattr(self, 'screen_cb_show_speaker'):
            self.screen_cb_show_speaker.blockSignals(True)
            self.screen_cb_show_speaker.setChecked(checked)
            self.screen_cb_show_speaker.blockSignals(False)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_screen_show_original_from_overlay(self, checked):
        self.config["screen_show_original"] = checked
        if hasattr(self, 'screen_cb_show_original'):
            self.screen_cb_show_original.blockSignals(True)
            self.screen_cb_show_original.setChecked(checked)
            self.screen_cb_show_original.blockSignals(False)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_screen_show_translated_from_overlay(self, checked):
        self.config["screen_show_translated"] = checked
        if hasattr(self, 'screen_cb_show_translated'):
            self.screen_cb_show_translated.blockSignals(True)
            self.screen_cb_show_translated.setChecked(checked)
            self.screen_cb_show_translated.blockSignals(False)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    # ------------------------------------------------------------------
    # 하위 호환성 (레거시 모듈 및 기존 테스트 연동용 범용 핸들러)
    # ------------------------------------------------------------------
    def on_click_through_toggled(self, checked):
        self.on_audio_click_through_toggled(checked)
        self.on_screen_click_through_toggled(checked)

    def sync_click_through_from_overlay(self, checked):
        self.sync_audio_click_through_from_overlay(checked)
        self.sync_screen_click_through_from_overlay(checked)

    def sync_clean_text_from_overlay(self, checked):
        self.sync_audio_clean_text_from_overlay(checked)
        self.sync_screen_clean_text_from_overlay(checked)

    def on_show_speaker_toggled(self, checked):
        self.on_audio_show_speaker_toggled(checked)
        self.on_screen_show_speaker_toggled(checked)

    def sync_show_speaker_from_overlay(self, checked):
        self.sync_audio_show_speaker_from_overlay(checked)
        self.sync_screen_show_speaker_from_overlay(checked)

    def on_show_original_toggled(self, checked):
        self.on_audio_show_original_toggled(checked)
        self.on_screen_show_original_toggled(checked)

    def sync_show_original_from_overlay(self, checked):
        self.sync_audio_show_original_from_overlay(checked)
        self.sync_screen_show_original_from_overlay(checked)

    def on_show_translated_toggled(self, checked):
        self.on_audio_show_translated_toggled(checked)
        self.on_screen_show_translated_toggled(checked)

    def sync_show_translated_from_overlay(self, checked):
        self.sync_audio_show_translated_from_overlay(checked)
        self.sync_screen_show_translated_from_overlay(checked)

    def on_show_badge_toggled(self, checked):
        self.on_audio_show_badge_toggled(checked)
        self.on_screen_show_badge_toggled(checked)

    def on_font_slider_changed(self, val, label=None):
        self.config["font_size"] = val
        self.config["audio_font_size"] = val
        self.config["screen_font_size"] = val
        roi_configs = self.config.get("roi_configs", {})
        if isinstance(roi_configs, dict):
            for r_cfg in roi_configs.values():
                if isinstance(r_cfg, dict):
                    r_cfg["font_size"] = val
        if hasattr(self, 'audio_font_slider'):
            self.audio_font_slider.blockSignals(True)
            self.audio_font_slider.setValue(val)
            self.audio_font_slider.blockSignals(False)
        if hasattr(self, 'screen_font_slider'):
            self.screen_font_slider.blockSignals(True)
            self.screen_font_slider.setValue(val)
            self.screen_font_slider.blockSignals(False)
        if hasattr(self, 'audio_font_label'):
            self.audio_font_label.setText(f"{val}px")
        if hasattr(self, 'screen_font_label'):
            self.screen_font_label.setText(f"{val}px")
        if self.overlay:
            if hasattr(self.overlay, "update_font_size"):
                self.overlay.update_font_size(val)
            elif hasattr(self.overlay, "set_font_size"):
                self.overlay.set_font_size(val)
        if self.screen_overlay:
            if hasattr(self.screen_overlay, "update_font_size"):
                self.screen_overlay.update_font_size(val)
            elif hasattr(self.screen_overlay, "set_font_size"):
                self.screen_overlay.set_font_size(val)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_opacity_slider_changed(self, val, label=None):
        pct = val / 100.0
        self.config["overlay_bg_opacity"] = pct
        self.config["audio_overlay_bg_opacity"] = pct
        self.config["screen_overlay_bg_opacity"] = pct
        roi_configs = self.config.get("roi_configs", {})
        if isinstance(roi_configs, dict):
            for r_cfg in roi_configs.values():
                if isinstance(r_cfg, dict):
                    r_cfg["opacity"] = val
        if hasattr(self, 'audio_opacity_slider'):
            self.audio_opacity_slider.blockSignals(True)
            self.audio_opacity_slider.setValue(val)
            self.audio_opacity_slider.blockSignals(False)
        if hasattr(self, 'screen_opacity_slider'):
            self.screen_opacity_slider.blockSignals(True)
            self.screen_opacity_slider.setValue(val)
            self.screen_opacity_slider.blockSignals(False)
        if hasattr(self, 'audio_opacity_label'):
            self.audio_opacity_label.setText(f"{val}%")
        if hasattr(self, 'screen_opacity_label'):
            self.screen_opacity_label.setText(f"{val}%")
        if self.overlay:
            if hasattr(self.overlay, "update_opacity"):
                self.overlay.update_opacity(pct)
            elif hasattr(self.overlay, "set_bg_opacity"):
                self.overlay.set_bg_opacity(pct)
        if self.screen_overlay:
            if hasattr(self.screen_overlay, "update_opacity"):
                self.screen_overlay.update_opacity(pct)
            elif hasattr(self.screen_overlay, "set_bg_opacity"):
                self.screen_overlay.set_bg_opacity(pct)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def sync_font_from_overlay(self, val):
        if hasattr(self, 'font_slider') and self.font_slider.value() != val:
            self.font_slider.blockSignals(True)
            self.font_slider.setValue(val)
            self.font_slider.blockSignals(False)
        if hasattr(self, 'font_label'):
            self.font_label.setText(f"{val}px")
        self.sync_audio_font_from_overlay(val)
        self.sync_screen_font_from_overlay(val)

    def sync_opacity_from_overlay(self, pct):
        val = float(pct)
        if val <= 1.0:
            val = val * 100.0
        val_int = int(round(val))
        if hasattr(self, 'opacity_slider') and self.opacity_slider.value() != val_int:
            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(val_int)
            self.opacity_slider.blockSignals(False)
        if hasattr(self, 'opacity_label'):
            self.opacity_label.setText(f"{val_int}%")
        self.sync_audio_opacity_from_overlay(pct)
        self.sync_screen_opacity_from_overlay(pct)

    def reset_overlay_position(self):
        try:
            if self.overlay:
                self.overlay.setGeometry(200, 750, 900, 140)
            if self.screen_overlay:
                if hasattr(self.screen_overlay, 'reset_geometry'):
                    self.screen_overlay.reset_geometry()
                elif hasattr(self.screen_overlay, 'setGeometry'):
                    self.screen_overlay.setGeometry(200, 520, 850, 130)
        except Exception as e:
            print(f"[Overlay] 위치 초기화 오류: {e}")

    def update_screen_worker_status(self, status_text: str):
        from src.screen_overlay_manager import ScreenOverlayManager
        is_paused = ScreenOverlayManager._is_paused_status_text(status_text)
        if not getattr(self, '_is_screen_active', False) and not is_paused:
            return
        if hasattr(self, 'lbl_screen_status'):
            self.lbl_screen_status.setText(status_text)
        if is_paused:
            self.update_engine_status("ready", tr("ocr_status_paused"))
        elif "번역 중" in status_text or "Translating" in status_text or "翻訳中" in status_text:
            self.update_engine_status("translating", tr("status_screen_prefix", text=status_text))
        elif "완료" in status_text or "complete" in status_text.lower() or "完了" in status_text:
            self.update_engine_status("ready", tr("status_screen_prefix", text=status_text))
        elif "감시 중" in status_text or "Monitoring" in status_text or "監視中" in status_text:
            if getattr(self, '_is_screen_active', False):
                self.update_engine_status("ready", tr("status_watching"))

    def trigger_inplace_translate(self, from_button: bool = False):
        if self.inplace_manager:
            self.inplace_manager.trigger_snapshot(from_button=from_button)

    def _on_inplace_hotkey_changed(self, new_hotkey: str):
        """사용자가 화면 제자리 번역 단축키를 변경했을 때 실시간 반영 및 설정 저장"""
        if not new_hotkey:
            return
        self.config["inplace_hotkey"] = new_hotkey
        self.save_config_cb(self.config)
        if hasattr(self, 'inplace_manager') and self.inplace_manager:
            self.inplace_manager.set_hotkey(new_hotkey)
        if hasattr(self, 'btn_inplace_translate'):
            self.btn_inplace_translate.setText(tr("fullscreen_translate"))
            self.btn_inplace_translate.setToolTip(tr("tip_fullscreen_translate", key=new_hotkey))
        if hasattr(self, 'btn_screen_hotkey'):
            self.btn_screen_hotkey.set_hotkey(new_hotkey)
        if hasattr(self, 'btn_settings_hotkey'):
            self.btn_settings_hotkey.set_hotkey(new_hotkey)
        if hasattr(self, 'lbl_hotkey_status'):
            self.lbl_hotkey_status.setText(tr("hotkey_status", key=new_hotkey))
            self.lbl_hotkey_status.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SECONDARY}; padding-left: 2px;")
        if hasattr(self, 'screen_overlay') and self.screen_overlay:
            if hasattr(self.screen_overlay, 'update_inplace_hotkey_tooltip'):
                self.screen_overlay.update_inplace_hotkey_tooltip(new_hotkey)

    def _on_hotkey_recording_state_changed(self, is_recording: bool):
        """단축키 키 캡처 녹음 중에는 백그라운드 핫키 가로채기를 일시 비활성화하여 오작동/깜빡임 차단"""
        if hasattr(self, 'inplace_manager') and self.inplace_manager:
            self.inplace_manager.set_hotkey_enabled(not is_recording)

    def _on_reset_hotkey_clicked(self):
        """단축키를 F4 기본값으로 재설정"""
        self._on_inplace_hotkey_changed("F4")

    def _on_hotkey_registration_status(self, success: bool, message: str):
        """Win32 전역 단축키 등록 결과 실시간 수신 및 UI 상태 알림"""
        if not hasattr(self, 'lbl_hotkey_status'):
            return
        cur_hk = self.config.get("inplace_hotkey", "F4")
        if success:
            self.lbl_hotkey_status.setText(tr("hotkey_status", key=cur_hk))
            self.lbl_hotkey_status.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SECONDARY}; padding-left: 2px;")
        else:
            self.lbl_hotkey_status.setText(f"⚠️ {message}")
            self.lbl_hotkey_status.setStyleSheet("font-size: 10px; color: #F59E0B; padding-left: 2px; font-weight: bold;")

    def _populate_display_combo(self):
        if not hasattr(self, 'combo_display'):
            return
        selected = int(self.config.get("screen_display_index", 0))
        self.combo_display.blockSignals(True)
        self.combo_display.clear()
        screens = QApplication.screens()
        for i, s in enumerate(screens):
            geo = s.geometry()
            self.combo_display.addItem(tr("monitor_name", n=i + 1) + f" ({geo.width()} × {geo.height()})", i)
        if screens:
            selected = min(max(0, selected), len(screens) - 1)
            self.combo_display.setCurrentIndex(selected)
            self.config["screen_display_index"] = selected
        self.combo_display.blockSignals(False)

    def on_display_changed(self, idx: int):
        if not 0 <= idx < len(QApplication.screens()):
            return
        self.config["screen_display_index"] = idx
        self._refresh_screen_preview()
        if self.screen_overlay and hasattr(self.screen_overlay, "sync_rois"):
            self.screen_overlay.sync_rois()
        self.save_config_cb(self.config)

    def show_monitor_identifiers(self):
        self._populate_display_combo()
        for overlay in getattr(self, '_monitor_identifier_windows', []):
            overlay.close()
        self._monitor_identifier_windows = []
        for number, screen in enumerate(QApplication.screens(), start=1):
            overlay = MonitorIdentificationOverlay(screen, number)
            overlay.show()
            overlay.setGeometry(screen.geometry())
            overlay.raise_()
            self._monitor_identifier_windows.append(overlay)
        if not hasattr(self, '_monitor_identifier_timer'):
            self._monitor_identifier_timer = QTimer(self)
            self._monitor_identifier_timer.setSingleShot(True)
            self._monitor_identifier_timer.timeout.connect(self._clear_monitor_identifiers)
        self._monitor_identifier_timer.start(2200)

    def _clear_monitor_identifiers(self):
        if hasattr(self, '_monitor_identifier_timer'):
            self._monitor_identifier_timer.stop()
        for overlay in getattr(self, '_monitor_identifier_windows', []):
            overlay.close()
        self._monitor_identifier_windows = []

    def _refresh_screen_preview(self):
        if not hasattr(self, 'screen_canvas'):
            return
        screens = QApplication.screens()
        index = self.combo_display.currentIndex() if hasattr(self, 'combo_display') else -1
        if not 0 <= index < len(screens):
            self.screen_canvas.set_monitor(None)
            self.lbl_screen_preview.setText(tr("no_monitor"))
            return
        screen = screens[index]
        image = screen.grabWindow(0)
        if not image.isNull():
            image = image.scaled(1280, 720, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            caption = tr("screen_preview_caption", index=index + 1)
        else:
            image = None
            caption = tr("screen_preview_nocap", index=index + 1)
        self.screen_canvas.set_monitor(screen.geometry(), image)
        self.lbl_screen_preview.setText(caption)

    def on_preprocess_toggled(self, checked: bool):
        self.config["screen_ocr_preprocess"] = checked
        self.save_config_cb(self.config)

    def on_clean_text_toggled(self, checked: bool):
        self.config["screen_clean_text_mode"] = checked
        if self.overlay and hasattr(self.overlay, "set_clean_mode"):
            self.overlay.set_clean_mode(checked)
        if self.screen_overlay:
            if hasattr(self.screen_overlay, "set_clean_mode"):
                self.screen_overlay.set_clean_mode(checked)
            elif hasattr(self.screen_overlay, "set_clean_text_mode"):
                self.screen_overlay.set_clean_text_mode(checked)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_clean_box_toggled(self, checked: bool):
        self.config["screen_clean_box"] = checked
        if self.overlay and hasattr(self.overlay, "set_clean_box"):
            self.overlay.set_clean_box(checked)
        if self.screen_overlay and hasattr(self.screen_overlay, "set_clean_box"):
            self.screen_overlay.set_clean_box(checked)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_show_roi_border_toggled(self, checked: bool):
        self.config["screen_show_roi_border"] = checked
        if hasattr(self, 'cb_show_roi_border') and self.cb_show_roi_border.isChecked() != checked:
            self.cb_show_roi_border.blockSignals(True)
            self.cb_show_roi_border.setChecked(checked)
            self.cb_show_roi_border.blockSignals(False)
        if hasattr(self, 'btn_toggle_roi_border'):
            self.btn_toggle_roi_border.setText(f"🔲 {tr('region_border')} {'ON' if checked else 'OFF'}")
        if self.roi_border_manager:
            self.roi_border_manager.set_enabled(checked)
        if self.screen_overlay and hasattr(self.screen_overlay, 'update_border_button_style'):
            self.screen_overlay.update_border_button_style()
        self.save_config_cb(self.config)

    def toggle_roi_border(self):
        cur = self.config.get("screen_show_roi_border", False)
        new_val = not cur
        if hasattr(self, 'cb_show_roi_border'):
            self.cb_show_roi_border.setChecked(new_val)
        else:
            self.on_show_roi_border_toggled(new_val)

    def on_stroke_slider_changed(self, val: int):
        self.config["subtitle_stroke_width"] = val
        self.config["audio_subtitle_stroke_width"] = val
        self.config["screen_subtitle_stroke_width"] = val
        if hasattr(self, 'lbl_stroke'):
            self.lbl_stroke.setText(f"{val}px")
        if hasattr(self, 'audio_slider_stroke') and self.audio_slider_stroke.value() != val:
            self.audio_slider_stroke.blockSignals(True)
            self.audio_slider_stroke.setValue(val)
            self.audio_slider_stroke.blockSignals(False)
        if hasattr(self, 'audio_lbl_stroke'):
            self.audio_lbl_stroke.setText(f"{val}px")
        if hasattr(self, 'screen_slider_stroke') and self.screen_slider_stroke.value() != val:
            self.screen_slider_stroke.blockSignals(True)
            self.screen_slider_stroke.setValue(val)
            self.screen_slider_stroke.blockSignals(False)
        if hasattr(self, 'screen_lbl_stroke'):
            self.screen_lbl_stroke.setText(f"{val}px")
        if self.overlay:
            self.overlay.set_stroke_width(val)
        if self.screen_overlay:
            self.screen_overlay.set_stroke_width(val)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_spacing_slider_changed(self, int_val: int):
        val = int_val / 10.0
        self.config["letter_spacing"] = val
        self.config["audio_letter_spacing"] = val
        self.config["screen_letter_spacing"] = val
        if hasattr(self, 'lbl_spacing'):
            self.lbl_spacing.setText(f"{val:.1f}px")
        if hasattr(self, 'audio_slider_spacing') and self.audio_slider_spacing.value() != int_val:
            self.audio_slider_spacing.blockSignals(True)
            self.audio_slider_spacing.setValue(int_val)
            self.audio_slider_spacing.blockSignals(False)
        if hasattr(self, 'audio_lbl_spacing'):
            self.audio_lbl_spacing.setText(f"{val:.1f}px")
        if hasattr(self, 'screen_slider_spacing') and self.screen_slider_spacing.value() != int_val:
            self.screen_slider_spacing.blockSignals(True)
            self.screen_slider_spacing.setValue(int_val)
            self.screen_slider_spacing.blockSignals(False)
        if hasattr(self, 'screen_lbl_spacing'):
            self.screen_lbl_spacing.setText(f"{val:.1f}px")
        if self.overlay:
            self.overlay.set_letter_spacing(val)
        if self.screen_overlay:
            self.screen_overlay.set_letter_spacing(val)
        self.save_config_cb(self.config)
        self._update_subtitle_preview()

    def on_duration_slider_changed(self, val: int):
        self.config["screen_subtitle_duration"] = val
        self.config["audio_subtitle_duration"] = val
        self.config["subtitle_duration"] = val
        roi_configs = self.config.get("roi_configs", {})
        if isinstance(roi_configs, dict):
            for r_cfg in roi_configs.values():
                if isinstance(r_cfg, dict):
                    r_cfg["duration"] = val
        if hasattr(self, 'lbl_duration'):
            self.lbl_duration.setText(self._duration_text(val))
        if hasattr(self, 'audio_slider_duration') and self.audio_slider_duration.value() != val:
            self.audio_slider_duration.blockSignals(True)
            self.audio_slider_duration.setValue(val)
            self.audio_slider_duration.blockSignals(False)
        if hasattr(self, 'audio_lbl_duration'):
            self.audio_lbl_duration.setText(self._duration_text(val))
        if hasattr(self, 'screen_slider_duration') and self.screen_slider_duration.value() != val:
            self.screen_slider_duration.blockSignals(True)
            self.screen_slider_duration.setValue(val)
            self.screen_slider_duration.blockSignals(False)
        if hasattr(self, 'screen_lbl_duration'):
            self.screen_lbl_duration.setText(self._duration_text(val))
        if self.overlay and hasattr(self.overlay, "set_subtitle_duration"):
            self.overlay.set_subtitle_duration(val)
        if self.screen_overlay:
            if hasattr(self.screen_overlay, "set_subtitle_duration"):
                self.screen_overlay.set_subtitle_duration(val)
            elif hasattr(self.screen_overlay, "update_duration"):
                self.screen_overlay.update_duration(val)
            elif hasattr(self.screen_overlay, "apply_config"):
                self.screen_overlay.apply_config(apply_geometry=False)
            elif hasattr(self.screen_overlay, "_apply_config"):
                self.screen_overlay._apply_config(apply_geometry=False)
        self.save_config_cb(self.config)

    def open_roi_selector(self):
        try:
            from src.roi_selector import ROISelector
            self.selector = ROISelector(
                self.config.get("screen_rois", []),
                callback=self._on_rois_selected,
                selected_display_index=self.combo_display.currentIndex() if hasattr(self, 'combo_display') else 0
            )
            self.selector.show()
        except Exception as e:
            tell(self, "msg_roi_error_title", "msg_roi_error", kind="warn", error=e)

    def refresh_roi_settings_cards(self):
        if not hasattr(self, 'roi_cards_layout'):
            return

        # 기존 카드 위젯 제거
        while self.roi_cards_layout.count() > 0:
            item = self.roi_cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        rois = self.config.get("screen_rois", [])
        if hasattr(self, 'lbl_roi_count_badge'):
            self._i18n(self.lbl_roi_count_badge, "roi_count", count=len(rois))

        roi_configs = self.config.setdefault("roi_configs", {})

        if not rois:
            empty_card = QFrame()
            empty_card.setObjectName("EmptyRoiCard")
            empty_card.setStyleSheet(f"""
                #EmptyRoiCard {{
                    background-color: {COLOR_CARD_INNER};
                    border: 1px dashed {COLOR_BORDER};
                    border-radius: 8px;
                    padding: 24px 16px;
                }}
                QLabel {{
                    border: none;
                    background: transparent;
                }}
            """)
            evbox = QVBoxLayout(empty_card)
            evbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
            evbox.setSpacing(10)

            lbl_icon = QLabel("📐")
            lbl_icon.setStyleSheet("font-size: 28px;")
            lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            evbox.addWidget(lbl_icon)

            lbl_txt = QLabel()
            self._i18n(lbl_txt, "no_regions")
            lbl_txt.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11.5px; line-height: 1.4;")
            lbl_txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            evbox.addWidget(lbl_txt)

            btn_add = QPushButton("➕ " + tr("new_region"))
            btn_add.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_ACCENT_PURPLE};
                    color: #FFFFFF;
                    font-weight: bold;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {COLOR_ACCENT_PURPLE_HOVER};
                }}
            """)
            btn_add.clicked.connect(self.open_roi_selector)
            evbox.addWidget(btn_add, alignment=Qt.AlignmentFlag.AlignCenter)

            self.roi_cards_layout.addWidget(empty_card)
            self.roi_cards_layout.addStretch(1)
            return

        colors = ["#8B5CF6", "#10B981", "#38BDF8", "#F59E0B", "#EC4899"]

        for idx, roi in enumerate(rois):
            card = QFrame()
            card.setObjectName("RoiCard")
            card.setStyleSheet(f"""
                #RoiCard {{
                    background-color: {COLOR_CARD_INNER};
                    border: 1px solid {COLOR_BORDER};
                    border-radius: 8px;
                    padding: 8px;
                }}
                QLabel {{
                    border: none;
                    background: transparent;
                }}
            """)
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(10, 8, 10, 8)
            c_layout.setSpacing(6)

            col = colors[idx % len(colors)]
            idx_str = str(idx)
            cfg = roi_configs.setdefault(idx_str, {})
            if "name" not in cfg:
                cfg["name"] = tr("region_num", n=idx + 1)
            if "font_size" not in cfg:
                cfg["font_size"] = self.config.get("font_size", 24)
            if "opacity" not in cfg:
                cfg["opacity"] = int(self.config.get("overlay_bg_opacity", 0.70) * 100)
            if "duration" not in cfg:
                cfg["duration"] = self.config.get("screen_subtitle_duration", 5)
            if "snap" not in cfg:
                cfg["snap"] = self.config.get("screen_snap_to_roi", False)

            # 헤더
            head = QHBoxLayout()
            head.setSpacing(6)

            badge = QLabel(f"#{idx + 1}")
            badge.setStyleSheet(f"background-color: {col}; color: #FFFFFF; font-weight: bold; font-size: 10px; border-radius: 4px; padding: 2px 6px;")
            head.addWidget(badge)

            name_edit = QLineEdit(cfg["name"])
            name_edit.setStyleSheet(f"background-color: #0A0F1D; color: #FFFFFF; border: 1px solid {COLOR_BORDER}; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: bold;")
            name_edit.textChanged.connect(lambda txt, i=idx_str: self._on_roi_name_changed(i, txt))
            head.addWidget(name_edit, stretch=1)

            btn_del = QPushButton()
            btn_del.setIcon(create_svg_icon(SVG_TRASH_ICON, 14, "#EF4444"))
            btn_del.setIconSize(QSize(14, 14))
            btn_del.setToolTip(tr("tip_delete_roi"))
            btn_del.setFixedSize(28, 24)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet("""
                QPushButton {
                    background-color: rgba(239, 68, 68, 0.12);
                    border: 1px solid rgba(239, 68, 68, 0.4);
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: rgba(239, 68, 68, 0.28);
                    border-color: #EF4444;
                }
            """)
            btn_del.clicked.connect(lambda _, i=idx: self.delete_single_roi(i))
            head.addWidget(btn_del)
            c_layout.addLayout(head)

            # 좌표 정보
            rx, ry, rw, rh = roi if len(roi) >= 4 else (0, 0, 0, 0)
            lbl_coords = QLabel(f"X: {rx}  Y: {ry}  |  {rw} × {rh} px")
            lbl_coords.setStyleSheet(f"color: {COLOR_ACCENT_CYAN}; font-size: 10px; font-weight: bold;")
            c_layout.addWidget(lbl_coords)

            # 폼
            form = QFormLayout()
            form.setSpacing(5)

            # 1. 글자 크기
            font_slider = NoWheelSlider(Qt.Orientation.Horizontal)
            font_slider.setRange(14, 40)
            font_slider.setValue(cfg.get("font_size", 24))
            lbl_fval = QLabel(f"{cfg.get('font_size', 24)}px")
            lbl_fval.setStyleSheet("color: #94A3B8; font-size: 10px; min-width: 32px;")
            font_row = QHBoxLayout()
            font_row.addWidget(font_slider, stretch=1)
            font_row.addWidget(lbl_fval)
            font_slider.valueChanged.connect(lambda v, lbl=lbl_fval, i=idx: self._on_roi_font_changed(i, v, lbl))
            form.addRow(f"{tr('font_size')}:", font_row)

            # 2. 배경 불투명도
            op_slider = NoWheelSlider(Qt.Orientation.Horizontal)
            op_slider.setRange(0, 100)
            op_slider.setValue(cfg.get("opacity", 70))
            lbl_opval = QLabel(f"{cfg.get('opacity', 70)}%")
            lbl_opval.setStyleSheet("color: #94A3B8; font-size: 10px; min-width: 32px;")
            op_row = QHBoxLayout()
            op_row.addWidget(op_slider, stretch=1)
            op_row.addWidget(lbl_opval)
            op_slider.valueChanged.connect(lambda v, lbl=lbl_opval, i=idx: self._on_roi_opacity_changed(i, v, lbl))
            form.addRow(f"{tr('opacity')}:", op_row)

            # 3. 표시 지속 시간
            dur_slider = NoWheelSlider(Qt.Orientation.Horizontal)
            dur_slider.setRange(0, 90)
            dur_val = cfg.get("duration", 5)
            dur_slider.setValue(dur_val)
            lbl_durval = QLabel(self._duration_text(dur_val))
            lbl_durval.setStyleSheet("color: #94A3B8; font-size: 10px; min-width: 32px;")
            dur_row = QHBoxLayout()
            dur_row.addWidget(dur_slider, stretch=1)
            dur_row.addWidget(lbl_durval)
            dur_slider.valueChanged.connect(lambda v, lbl=lbl_durval, i=idx: self._on_roi_duration_changed(i, v, lbl))
            form.addRow(f"{tr('duration')}:", dur_row)

            # 4. 밀착 스냅
            snap_toggle = ModernToggle(active_color=col)
            snap_toggle.setChecked(cfg.get("snap", False))
            snap_toggle.toggled.connect(lambda c, i=idx: self._on_roi_snap_toggled(i, c))
            snap_lbl = tr('snap') if tr('snap').endswith(':') else f"{tr('snap')}:"
            form.addRow(snap_lbl, snap_toggle)

            c_layout.addLayout(form)
            self.roi_cards_layout.addWidget(card)

        self.roi_cards_layout.addStretch(1)

    def _on_roi_name_changed(self, idx_str: str, name: str):
        self.config.setdefault("roi_configs", {}).setdefault(idx_str, {})["name"] = name
        self.save_config_cb(self.config)

    def _on_roi_font_changed(self, idx: int, val: int, lbl_widget: QLabel):
        lbl_widget.setText(f"{val}px")
        idx_str = str(idx)
        self.config.setdefault("roi_configs", {}).setdefault(idx_str, {})["font_size"] = val
        if idx == 0:
            self.config["font_size"] = val
        if self.screen_overlay and hasattr(self.screen_overlay, "overlays") and idx < len(self.screen_overlay.overlays):
            o = self.screen_overlay.overlays[idx]
            o._apply_config(apply_geometry=False)
        self.save_config_cb(self.config)

    def _on_roi_opacity_changed(self, idx: int, val: int, lbl_widget: QLabel):
        lbl_widget.setText(f"{val}%")
        idx_str = str(idx)
        self.config.setdefault("roi_configs", {}).setdefault(idx_str, {})["opacity"] = val
        pct = val / 100.0
        if idx == 0:
            self.config["overlay_bg_opacity"] = pct
        if self.screen_overlay and hasattr(self.screen_overlay, "overlays") and idx < len(self.screen_overlay.overlays):
            o = self.screen_overlay.overlays[idx]
            o._apply_config(apply_geometry=False)
            o.update()
        self.save_config_cb(self.config)

    def _on_roi_duration_changed(self, idx: int, val: int, lbl_widget: QLabel):
        lbl_widget.setText(self._duration_text(val))
        idx_str = str(idx)
        self.config.setdefault("roi_configs", {}).setdefault(idx_str, {})["duration"] = val
        if idx == 0:
            self.config["screen_subtitle_duration"] = val
        if self.screen_overlay and hasattr(self.screen_overlay, "overlays") and idx < len(self.screen_overlay.overlays):
            o = self.screen_overlay.overlays[idx]
            o._apply_config(apply_geometry=False)
        self.save_config_cb(self.config)

    def _on_roi_snap_toggled(self, idx: int, checked: bool):
        idx_str = str(idx)
        self.config.setdefault("roi_configs", {}).setdefault(idx_str, {})["snap"] = checked
        rois = self.config.get("screen_rois", [])
        if idx == 0:
            self.config["screen_snap_to_roi"] = checked
        if self.screen_overlay and hasattr(self.screen_overlay, "overlays") and idx < len(self.screen_overlay.overlays):
            o = self.screen_overlay.overlays[idx]
            if checked and idx < len(rois):
                o.snap_to_roi(rois[idx])
        self.save_config_cb(self.config)

    def delete_single_roi(self, idx: int):
        rois = self.config.get("screen_rois", [])
        if 0 <= idx < len(rois):
            rois.pop(idx)
            self.config["screen_rois"] = rois
            self.config["screen_roi"] = rois[0] if rois else None
            if self.screen_worker and hasattr(self.screen_worker, "invalidate_regions"):
                self.screen_worker.invalidate_regions()
            old_cfgs = self.config.get("roi_configs", {})
            new_cfgs = {}
            target_i = 0
            for i in range(len(rois) + 1):
                if i == idx:
                    continue
                if str(i) in old_cfgs:
                    new_cfgs[str(target_i)] = old_cfgs[str(i)]
                target_i += 1
            self.config["roi_configs"] = new_cfgs

            if self.roi_border_manager:
                self.roi_border_manager.update_rois()
            if self.screen_overlay and hasattr(self.screen_overlay, "sync_rois"):
                self.screen_overlay.sync_rois()
            if hasattr(self, 'screen_canvas'):
                self.screen_canvas.set_rois(rois)
            self.refresh_roi_settings_cards()
            self.save_config_cb(self.config)

    def _on_rois_border_adjusted(self, rois: list, is_final: bool = True):
        self.config["screen_rois"] = rois
        self.config["screen_roi"] = rois[0] if rois else None

        if hasattr(self, 'lbl_roi_coords') and rois:
            r = rois[0]
            self.lbl_roi_coords.setText(f"X: {r[0]}  Y: {r[1]}  W: {r[2]}  H: {r[3]}")

        # 밀착 스냅 모드일 경우 실시간으로 자막 위치도 추종
        if self.config.get("screen_snap_to_roi", False) and self.screen_overlay:
            if hasattr(self.screen_overlay, "snap_all_to_rois"):
                self.screen_overlay.snap_all_to_rois()
            elif hasattr(self.screen_overlay, "snap_to_roi") and rois:
                self.screen_overlay.snap_to_roi(rois[0])

        if is_final:
            if self.screen_worker and hasattr(self.screen_worker, "update_config"):
                self.screen_worker.update_config(self.config)
            elif self.screen_worker and hasattr(self.screen_worker, "invalidate_regions"):
                self.screen_worker.invalidate_regions()
            if self.screen_overlay and hasattr(self.screen_overlay, "sync_rois"):
                self.screen_overlay.sync_rois()
            if hasattr(self, 'screen_canvas'):
                self.screen_canvas.set_rois(rois)
            self.refresh_roi_settings_cards()
            self.save_config_cb(self.config)

    def _on_rois_selected(self, rois: list):
        self.config["screen_rois"] = rois
        self.config["screen_roi"] = rois[0] if rois else None
        if self.screen_worker and hasattr(self.screen_worker, "update_config"):
            self.screen_worker.update_config(self.config)
        elif self.screen_worker and hasattr(self.screen_worker, "invalidate_regions"):
            self.screen_worker.invalidate_regions()
        if hasattr(self, 'lbl_roi_coords') and rois:
            r = rois[0]
            self.lbl_roi_coords.setText(f"X: {r[0]}  Y: {r[1]}  W: {r[2]}  H: {r[3]}")
        if self.roi_border_manager:
            self.roi_border_manager.update_rois()
        if self.screen_overlay and hasattr(self.screen_overlay, "sync_rois"):
            self.screen_overlay.sync_rois()
        if hasattr(self, 'screen_canvas'):
            self.screen_canvas.set_rois(rois)
        self.refresh_roi_settings_cards()
        self.save_config_cb(self.config)

    def clear_rois(self):
        self.config["screen_rois"] = []
        self.config["screen_roi"] = None
        if self.screen_worker and hasattr(self.screen_worker, "update_config"):
            self.screen_worker.update_config(self.config)
        elif self.screen_worker and hasattr(self.screen_worker, "invalidate_regions"):
            self.screen_worker.invalidate_regions()
        self.config["roi_configs"] = {}
        if hasattr(self, 'lbl_roi_coords'):
            self.lbl_roi_coords.setText(tr("no_regions_set"))
        if self.roi_border_manager:
            self.roi_border_manager.update_rois()
        if self.screen_overlay and hasattr(self.screen_overlay, "sync_rois"):
            self.screen_overlay.sync_rois()
        if hasattr(self, 'screen_canvas'):
            self.screen_canvas.set_rois([])
        self.refresh_roi_settings_cards()
        self.save_config_cb(self.config)

    def on_snap_to_roi_toggled(self, checked: bool):
        self.config["screen_snap_to_roi"] = checked
        if self.screen_overlay:
            self.screen_overlay.set_snap_to_roi(checked)
        self.save_config_cb(self.config)

    def sync_snap_from_overlay(self, enabled: bool):
        if hasattr(self, 'toggle_snap_to_roi'):
            self.toggle_snap_to_roi.blockSignals(True)
            self.toggle_snap_to_roi.setChecked(enabled)
            self.toggle_snap_to_roi.blockSignals(False)

    def trigger_instant_screen_ocr(self):
        if self.screen_worker:
            self.screen_worker.trigger_instant_capture()

    def _update_audio_overlay_btn_ui(self):
        if not hasattr(self, 'btn_toggle_audio_overlay'):
            return
        vis = self.overlay.isVisible() if self.overlay else False
        if vis:
            self._i18n(self.btn_toggle_audio_overlay, "hide_overlay")
        else:
            self._i18n(self.btn_toggle_audio_overlay, "show_overlay")
        if hasattr(self, 'toggle_audio_overlay_vis'):
            self.toggle_audio_overlay_vis.blockSignals(True)
            self.toggle_audio_overlay_vis.setChecked(vis)
            self.toggle_audio_overlay_vis.blockSignals(False)

    def toggle_audio_overlay_window(self):
        if self.overlay:
            vis = not self.overlay.isVisible()
            self.overlay.setVisible(vis)
            self.config["audio_overlay_visible"] = vis
            self.save_config_cb(self.config)
            self._update_audio_overlay_btn_ui()

    def sync_audio_overlay_visibility(self, visible: bool):
        if getattr(self, '_is_closing', False):
            return
        self.config["audio_overlay_visible"] = bool(visible)
        self.save_config_cb(self.config)
        self._update_audio_overlay_btn_ui()

    def toggle_screen_overlay_window(self, visible: bool):
        if self.screen_overlay:
            self.config["screen_overlay_visible"] = bool(visible)
            if hasattr(self.screen_overlay, "set_visible"):
                self.screen_overlay.set_visible(bool(visible))
            else:
                self.screen_overlay.setVisible(bool(visible))
            self.save_config_cb(self.config)
            self.sync_screen_overlay_visibility(bool(visible))

    def sync_screen_overlay_visibility(self, visible: bool):
        if getattr(self, '_is_closing', False):
            return
        self.config["screen_overlay_visible"] = bool(visible)
        self.save_config_cb(self.config)
        if hasattr(self, 'toggle_screen_overlay_vis'):
            self.toggle_screen_overlay_vis.blockSignals(True)
            self.toggle_screen_overlay_vis.setChecked(visible)
            self.toggle_screen_overlay_vis.blockSignals(False)

    def save_all_settings_before_exit(self):
        if getattr(self, '_already_saved_settings', False):
            return
        self._already_saved_settings = True

        # 1. 창 위치 및 크기 저장
        try:
            geo = self.geometry()
            if geo.isValid() and geo.width() >= 400 and geo.height() >= 300:
                screen = QApplication.primaryScreen()
                if screen:
                    avail = screen.availableGeometry()
                    if (avail.left() - 100 <= geo.x() <= avail.right() and
                        avail.top() - 50 <= geo.y() <= avail.bottom()):
                        self.config["control_panel_geometry"] = [geo.x(), geo.y(), geo.width(), geo.height()]
                else:
                    self.config["control_panel_geometry"] = [geo.x(), geo.y(), geo.width(), geo.height()]
        except Exception:
            pass


        if self.overlay and hasattr(self.overlay, "geometry"):
            try:
                og = self.overlay.geometry()
                if hasattr(og, 'x') and callable(og.x):
                    self.config["window_geometry"] = [og.x(), og.y(), og.width(), og.height()]
            except Exception:
                pass

        if self.screen_overlay:
            try:
                overlays_list = getattr(self.screen_overlay, "overlays", None)
                if isinstance(overlays_list, (list, tuple)) and overlays_list:
                    self.config["screen_overlay_geometries"] = {
                        str(i): [ov.geometry().x(), ov.geometry().y(), ov.geometry().width(), ov.geometry().height()]
                        for i, ov in enumerate(overlays_list)
                        if hasattr(ov, 'geometry') and hasattr(ov.geometry(), 'x')
                    }
                elif hasattr(self.screen_overlay, "geometry"):
                    og = self.screen_overlay.geometry()
                    if hasattr(og, 'x') and callable(og.x):
                        self.config["screen_overlay_geometries"] = {"0": [og.x(), og.y(), og.width(), og.height()]}
            except Exception:
                pass

        # 2. 마지막 활성 탭 인덱스
        if hasattr(self, 'tab_stack'):
            self.config["last_active_tab"] = self.tab_stack.currentIndex()

        # 3. 오버레이 가시성
        if self.overlay and hasattr(self.overlay, "isVisible"):
            self.config["audio_overlay_visible"] = self.overlay.isVisible()
        elif hasattr(self, 'toggle_audio_overlay_vis'):
            self.config["audio_overlay_visible"] = self.toggle_audio_overlay_vis.isChecked()

        if self.screen_overlay:
            if hasattr(self.screen_overlay, "is_visible"):
                self.config["screen_overlay_visible"] = self.screen_overlay.is_visible()
            elif hasattr(self.screen_overlay, "isVisible"):
                self.config["screen_overlay_visible"] = self.screen_overlay.isVisible()
        elif hasattr(self, 'toggle_screen_overlay_vis'):
            self.config["screen_overlay_visible"] = self.toggle_screen_overlay_vis.isChecked()

        # 4. 자동 시작 및 기본 옵션
        if hasattr(self, 'cb_auto_start_audio'):
            self.config["auto_start_audio"] = self.cb_auto_start_audio.isChecked()
        if hasattr(self, 'cb_auto_start_screen'):
            self.config["auto_start_screen"] = self.cb_auto_start_screen.isChecked()
        if hasattr(self, 'cb_gpu_warmup'):
            self.config["gpu_warmup_on_startup"] = self.cb_gpu_warmup.isChecked()
        if hasattr(self, 'cb_auto_youtube_detect'):
            self.config["auto_youtube_detect"] = self.cb_auto_youtube_detect.isChecked()

        # 5. 자막 외관 및 동작 옵션
        if hasattr(self, 'font_slider'):
            self.config["font_size"] = self.font_slider.value()
        if hasattr(self, 'opacity_slider'):
            self.config["overlay_bg_opacity"] = round(self.opacity_slider.value() / 100.0, 2)
        if hasattr(self, 'slider_stroke'):
            self.config["subtitle_stroke_width"] = self.slider_stroke.value()
        if hasattr(self, 'slider_spacing'):
            self.config["letter_spacing"] = round(self.slider_spacing.value() / 10.0, 1)
        if hasattr(self, 'audio_slider_duration'):
            self.config["audio_subtitle_duration"] = self.audio_slider_duration.value()
            self.config["subtitle_duration"] = self.audio_slider_duration.value()
        if hasattr(self, 'screen_slider_duration'):
            self.config["screen_subtitle_duration"] = self.screen_slider_duration.value()
        elif hasattr(self, 'slider_duration'):
            self.config["screen_subtitle_duration"] = self.slider_duration.value()
        if hasattr(self, 'audio_cb_clean_box'):
            self.config["audio_clean_box"] = self.audio_cb_clean_box.isChecked()
            self.config["clean_box"] = self.audio_cb_clean_box.isChecked()
        if hasattr(self, 'screen_cb_clean_box'):
            self.config["screen_clean_box"] = self.screen_cb_clean_box.isChecked()
        elif hasattr(self, 'cb_clean_box'):
            self.config["screen_clean_box"] = self.cb_clean_box.isChecked()

        if hasattr(self, 'audio_cb_clean_text'):
            self.config["audio_clean_text_mode"] = self.audio_cb_clean_text.isChecked()
        if hasattr(self, 'screen_cb_clean_text'):
            self.config["screen_clean_text_mode"] = self.screen_cb_clean_text.isChecked()
        elif hasattr(self, 'cb_clean_text'):
            self.config["screen_clean_text_mode"] = self.cb_clean_text.isChecked()

        if hasattr(self, 'audio_cb_show_original'):
            self.config["audio_show_original"] = self.audio_cb_show_original.isChecked()
            self.config["show_original"] = self.audio_cb_show_original.isChecked()
        elif hasattr(self, 'cb_show_original'):
            self.config["show_original"] = self.cb_show_original.isChecked()
        if hasattr(self, 'screen_cb_show_original'):
            self.config["screen_show_original"] = self.screen_cb_show_original.isChecked()

        if hasattr(self, 'audio_cb_show_translated'):
            self.config["audio_show_translated"] = self.audio_cb_show_translated.isChecked()
            self.config["show_translated"] = self.audio_cb_show_translated.isChecked()
        if hasattr(self, 'screen_cb_show_translated'):
            self.config["screen_show_translated"] = self.screen_cb_show_translated.isChecked()

        if hasattr(self, 'audio_cb_show_badge'):
            self.config["audio_show_engine_badge"] = self.audio_cb_show_badge.isChecked()
            self.config["show_engine_badge"] = self.audio_cb_show_badge.isChecked()
        elif hasattr(self, 'cb_show_badge'):
            self.config["show_engine_badge"] = self.cb_show_badge.isChecked()
        if hasattr(self, 'screen_cb_show_badge'):
            self.config["screen_show_engine_badge"] = self.screen_cb_show_badge.isChecked()

        if hasattr(self, 'audio_cb_click_through'):
            self.config["audio_click_through"] = self.audio_cb_click_through.isChecked()
            self.config["click_through"] = self.audio_cb_click_through.isChecked()
        elif hasattr(self, 'cb_click_through'):
            self.config["click_through"] = self.cb_click_through.isChecked()
        if hasattr(self, 'screen_cb_click_through'):
            self.config["screen_click_through"] = self.screen_cb_click_through.isChecked()

        if hasattr(self, 'audio_cb_show_speaker'):
            self.config["audio_show_speaker"] = self.audio_cb_show_speaker.isChecked()
            self.config["show_speaker"] = self.audio_cb_show_speaker.isChecked()
        elif hasattr(self, 'cb_show_speaker'):
            self.config["show_speaker"] = self.cb_show_speaker.isChecked()
        if hasattr(self, 'screen_cb_show_speaker'):
            self.config["screen_show_speaker"] = self.screen_cb_show_speaker.isChecked()

        if hasattr(self, 'cb_snap_to_roi'):
            self.config["screen_snap_to_roi"] = self.cb_snap_to_roi.isChecked()
        if hasattr(self, 'cb_show_roi_border'):
            self.config["screen_show_roi_border"] = self.cb_show_roi_border.isChecked()
        if hasattr(self, 'slider_ocr_clahe'):
            self.config["screen_ocr_preprocess"] = self.slider_ocr_clahe.value() > 30

        # 6. STT 디바이스/엔진 및 모델
        if hasattr(self, 'stt_buttons'):
            for btn, k in self.stt_buttons:
                if btn.isChecked():
                    if k in ("groq", "deepgram"):
                        self.config["stt_provider"] = k
                    else:
                        self.config["stt_provider"] = "local"
                        self.config["device"] = k
                    break
        if hasattr(self, 'combo_model'):
            cur_m = self.combo_model.itemData(self.combo_model.currentIndex()) or self.combo_model.currentText()
            if cur_m:
                stt_p = self.config.get("stt_provider", "local")
                if stt_p == "deepgram":
                    self.config["deepgram_model"] = cur_m
                elif stt_p == "groq":
                    self.config["groq_model"] = cur_m
                else:
                    self.config["model_size"] = cur_m

        # 7. 번역 엔진
        if hasattr(self, 'trans_engine_buttons'):
            for btn, k in self.trans_engine_buttons:
                if btn.isChecked():
                    self.config["translation_engine"] = k
                    break

        # 8. 템포 프리셋
        if hasattr(self, 'combo_tempo_preset'):
            k = self.combo_tempo_preset.itemData(self.combo_tempo_preset.currentIndex())
            if k:
                self.config["content_tempo_preset"] = k

        # 9. 오디오 캡처 & 더빙 디바이스
        if hasattr(self, 'combo_audio_cap_dev') and self.combo_audio_cap_dev.currentIndex() >= 0:
            dev_data = self.combo_audio_cap_dev.itemData(self.combo_audio_cap_dev.currentIndex())
            dev_text = self.combo_audio_cap_dev.currentText()
            self.config["audio_capture_device"] = dev_data if dev_data is not None else dev_text
        if hasattr(self, 'combo_dub_out_dev') and self.combo_dub_out_dev.currentIndex() >= 0:
            dev_data = self.combo_dub_out_dev.itemData(self.combo_dub_out_dev.currentIndex())
            dev_text = self.combo_dub_out_dev.currentText()
            self.config["dubbing_output_device"] = dev_data if dev_data is not None else dev_text

        # 10. 더빙 볼륨 및 속도
        if hasattr(self, 'slider_dubbing_vol'):
            self.config["dubbing_volume"] = self.slider_dubbing_vol.value()
        if hasattr(self, 'slider_original_vol'):
            self.config["original_volume"] = self.slider_original_vol.value()
        if hasattr(self, 'combo_dubbing_speed'):
            s_val = self.combo_dubbing_speed.itemData(self.combo_dubbing_speed.currentIndex())
            if s_val:
                self.config["dubbing_speed"] = s_val
        if hasattr(self, 'slider_ducking_vol'):
            self.config["audio_ducking_volume"] = self.slider_ducking_vol.value()
        if hasattr(self, 'toggle_audio_ducking'):
            self.config["audio_ducking_enabled"] = self.toggle_audio_ducking.isChecked()
        if hasattr(self, 'toggle_dub_voice'):
            self.config["dubbing_source_audio"] = self.toggle_dub_voice.isChecked()
        if hasattr(self, 'toggle_dub_screen'):
            self.config["dubbing_source_screen"] = self.toggle_dub_screen.isChecked()
        if hasattr(self, 'combo_dub_voice_audio') and self.combo_dub_voice_audio.currentIndex() >= 0:
            v_a = self.combo_dub_voice_audio.itemData(self.combo_dub_voice_audio.currentIndex())
            if v_a:
                self.config["dubbing_voice_audio"] = v_a
        if hasattr(self, 'combo_dub_voice_screen') and self.combo_dub_voice_screen.currentIndex() >= 0:
            v_s = self.combo_dub_voice_screen.itemData(self.combo_dub_voice_screen.currentIndex())
            if v_s:
                self.config["dubbing_voice_screen"] = v_s

        # 11. 화자 분리(Diarization) 설정
        if hasattr(self, 'toggle_speaker_diarization'):
            self.config["speaker_diarization_enabled"] = self.toggle_speaker_diarization.isChecked()
        if hasattr(self, 'combo_speaker_max_count'):
            s_max = self.combo_speaker_max_count.itemData(self.combo_speaker_max_count.currentIndex())
            if s_max is not None:
                self.config["speaker_max_count"] = s_max
        if hasattr(self, 'slider_speaker_threshold'):
            self.config["speaker_similarity_threshold"] = round(self.slider_speaker_threshold.value() / 100.0, 2)
        if hasattr(self, 'toggle_ocr_auto_mapping'):
            self.config["speaker_ocr_auto_mapping"] = self.toggle_ocr_auto_mapping.isChecked()
        if hasattr(self, 'combo_display') and self.combo_display.currentIndex() >= 0:
            self.config["screen_display_index"] = self.combo_display.currentIndex()

        # 12. API 키 동기화
        if hasattr(self, 'input_card_deepl') and self.input_card_deepl.text():
            self.config["deepl_api_key"] = self.input_card_deepl.text().strip()
        if hasattr(self, 'input_card_gemini') and self.input_card_gemini.text():
            self.config["gemini_api_key"] = self.input_card_gemini.text().strip()
        if hasattr(self, 'input_card_groq') and self.input_card_groq.text():
            self.config["groq_api_key"] = self.input_card_groq.text().strip()
        if hasattr(self, 'input_card_deepgram') and self.input_card_deepgram.text():
            self.config["deepgram_api_key"] = self.input_card_deepgram.text().strip()

        # 13. 화자 별칭 및 음소거
        if self.stt_thread and hasattr(self.stt_thread, "speaker_identifier") and self.stt_thread.speaker_identifier:
            self.config["speaker_aliases"] = dict(self.stt_thread.speaker_identifier.speaker_aliases)
            self.config["speaker_mutes"] = dict(self.stt_thread.speaker_identifier.speaker_mutes)
            self.config["speaker_ocr_auto_mapping"] = getattr(self.stt_thread.speaker_identifier, 'ocr_auto_mapping', self.config.get("speaker_ocr_auto_mapping", True))

        self.save_config_cb(self.config)

    def closeEvent(self, event):
        self._cleanup_on_close()
        event.accept()
        app = QApplication.instance()
        if app:
            app.quit()

    def _cleanup_on_close(self):
        self._is_closing = True
        if hasattr(self, 'speaker_poll_timer') and self.speaker_poll_timer:
            try:
                self.speaker_poll_timer.stop()
            except Exception:
                pass
        if hasattr(self, 'audio_source_poll_timer') and self.audio_source_poll_timer:
            try:
                self.audio_source_poll_timer.stop()
            except Exception:
                pass
        if hasattr(self, '_sub_refresh_timer') and self._sub_refresh_timer:
            try:
                self._sub_refresh_timer.stop()
            except Exception:
                pass
        if hasattr(self, 'ducking_manager') and self.ducking_manager:
            try:
                self.ducking_manager.stop()
            except Exception:
                pass
        self._clear_monitor_identifiers()
        self.save_all_settings_before_exit()

        # 백그라운드 QThread 및 매니저를 명시적으로 정지하여 QThread::~QThread 크래시 방지
        if hasattr(self, 'screen_worker') and self.screen_worker:
            try:
                self.screen_worker.stop()
            except Exception:
                pass
        if hasattr(self, 'inplace_manager') and self.inplace_manager:
            try:
                self.inplace_manager.stop()
            except Exception:
                pass

        # 열려 있는 독립 오버레이 창들을 명시적으로 닫아 Qt 이벤트 루프 종료 보장
        if hasattr(self, 'overlay') and self.overlay:
            try:
                self.overlay.close()
            except Exception:
                pass
        if hasattr(self, 'screen_overlay') and self.screen_overlay:
            try:
                self.screen_overlay.close()
            except Exception:
                pass
        if hasattr(self, 'roi_border_manager') and self.roi_border_manager:
            try:
                self.roi_border_manager.close()
            except Exception:
                pass


    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, p, self)
        p.end()
