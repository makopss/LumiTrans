import time
import re
import ctypes
import struct
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QRect, QRectF
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QSizeGrip,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QStyle, QStyleOption
)
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QFontMetrics, QCursor, QTextDocument, QPainterPath
from src.outline_effect import ThickOutlineEffect
from src.overlay_geometry import OverlayGeometryMixin
from src.i18n import tr

# 8방향 테두리 리사이즈 플래그 및 마진 상수
EDGE_NONE = 0
EDGE_LEFT = 1
EDGE_RIGHT = 2
EDGE_TOP = 4
EDGE_BOTTOM = 8

EDGE_MARGIN = 8       # 테두리 리사이즈 감지 두께 (px)
CORNER_MARGIN = 16    # 모서리 코너 감지 크기 (px)


class ElidedBadgeLabel(QLabel):
    """너비를 초과하는 텍스트는 말줄임표(...)로 안전하게 생략하여 옆 버튼과의 겹침을 방지하는 컴팩트 뱃지"""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._raw_text = text

    def setText(self, text):
        self._raw_text = text
        self.setToolTip(text)
        super().setText(text)
        self.update()

    def text(self):
        return getattr(self, "_raw_text", super().text())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        opt = QStyleOption()
        opt.initFrom(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, painter, self)

        r = self.contentsRect().adjusted(2, 0, -2, 0)
        fm = self.fontMetrics()
        raw = getattr(self, "_raw_text", super().text()) or ""
        clean = re.sub(r'<[^>]+>', '', raw).strip()
        elided = fm.elidedText(clean, Qt.TextElideMode.ElideRight, max(10, r.width()))

        painter.setFont(self.font())
        painter.setPen(QColor(140, 220, 255, 220))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, elided)


class ScreenSubtitleOverlay(OverlayGeometryMixin, QWidget):
    update_subtitle_signal = pyqtSignal(str, str, str)  # (original, translated, engine)
    status_signal = pyqtSignal(str)

    def __init__(self, config, on_config_change=None, roi_idx: int = 0):
        super().__init__()
        self.config = config
        self.on_config_change = on_config_change
        self.assigned_roi_idx = roi_idx
        self.assigned_roi = None
        self.is_user_positioned = False

        self.drag_position = QPoint()
        self.is_click_through = False
        self.current_original = ""
        self.current_translated = ""
        self.last_translated_time = 0.0

        # 개별 영역 저장 좌표 복원
        idx_key = str(self.assigned_roi_idx)
        geo_map = self.config.get("screen_overlay_geometries", {})
        if isinstance(geo_map, dict) and idx_key in geo_map and len(geo_map[idx_key]) == 4:
            self.base_geometry = list(geo_map[idx_key])
            self.is_user_positioned = True
            self.is_user_sized = True
        else:
            self.base_geometry = list(self.config.get("screen_overlay_geometry", [200, 520, 850, 130]))
            self.is_user_sized = False
        self.is_auto_resizing = False

        # 8방향 테두리 리사이즈 및 드래그 이동 상태 변수
        self.active_resize_edge = EDGE_NONE
        self.is_moving = False
        self.drag_start_global = QPoint()
        self.drag_start_geometry = QRect()
        self.drag_start_pos = QPoint()
        self._init_geometry_lock()

        self.ext_toggle_pause = None
        self.ext_trigger_roi = None
        self.ext_trigger_instant = None
        self.ext_open_settings = None
        self.ext_toggle_dubbing = None
        self.ext_sync_show_original = None

        self.clean_text_mode = self._get_clean_text_mode()
        self.is_dubbing_enabled = bool(self.config.get("dubbing_enabled", False) and self.config.get("dubbing_source_screen", False))
        self.show_speaker = self._get_show_speaker()
        self.speaker_diarization_enabled = bool(self.config.get("speaker_diarization_enabled", False))
        self.is_click_through = self._get_click_through()
        self.is_idle = False
        self.is_mouse_hovered = False
        self.is_pinned = False

        # 자막 자동 소거 타이머 (0초=영구 유지, >0초=설정 시간 후 페이드)
        self.clear_timer = QTimer(self)
        self.clear_timer.setSingleShot(True)
        self.clear_timer.timeout.connect(self.fade_or_clear_subtitles)

        # 유휴 3.5초 감지 타이머 (버튼/배경을 숨기고 텍스트만 공중 부양)
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(3500)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self._on_idle_timeout)

        self._init_ui()
        self._apply_config()

        self.update_subtitle_signal.connect(self.display_subtitle)
        self.status_signal.connect(self.display_status)
        self.setMouseTracking(True)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'idle_timer'):
            self.idle_timer.start(3500)
        if hasattr(self, 'ext_visibility_change') and self.ext_visibility_change:
            self.ext_visibility_change(True)
        self._bind_screen_changed()

    def _get_font_size(self) -> int:
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        roi_configs = self.config.get("roi_configs", {})
        roi_specific_cfg = roi_configs.get(idx_key, {}) if isinstance(roi_configs, dict) else {}
        val = roi_specific_cfg.get("font_size")
        if val is not None:
            return int(val)
        val = self.config.get("screen_font_size")
        if val is not None:
            return int(val)
        return int(self.config.get("font_size", 22))

    def _get_bg_opacity(self) -> float:
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        roi_configs = self.config.get("roi_configs", {})
        roi_specific_cfg = roi_configs.get(idx_key, {}) if isinstance(roi_configs, dict) else {}
        if roi_specific_cfg.get("opacity") is not None:
            return roi_specific_cfg["opacity"] / 100.0
        val = self.config.get("screen_overlay_bg_opacity")
        if val is not None:
            return self._normalize_bg_opacity(val)
        return self._normalize_bg_opacity(self.config.get("overlay_bg_opacity", 0.75))

    def _get_stroke_width(self) -> int:
        val = self.config.get("screen_subtitle_stroke_width")
        if val is not None:
            return int(val)
        return int(self.config.get("subtitle_stroke_width", 0))

    def _get_letter_spacing(self) -> float:
        val = self.config.get("screen_letter_spacing")
        if val is not None:
            return float(val)
        return float(self.config.get("letter_spacing", 2.0))

    def _get_show_original(self) -> bool:
        val = self.config.get("screen_show_original")
        if val is not None:
            return bool(val)
        return bool(self.config.get("show_original", True))

    def _get_show_translated(self) -> bool:
        val = self.config.get("screen_show_translated")
        if val is not None:
            return bool(val)
        return bool(self.config.get("show_translated", True))

    def _get_show_speaker(self) -> bool:
        val = self.config.get("screen_show_speaker")
        if val is not None:
            return bool(val)
        return bool(self.config.get("show_speaker", True))

    def _get_show_badge(self) -> bool:
        val = self.config.get("screen_show_engine_badge")
        if val is not None:
            return bool(val)
        return bool(self.config.get("show_engine_badge", True))

    def _get_clean_box(self) -> bool:
        val = self.config.get("screen_clean_box")
        if val is not None:
            return bool(val)
        return bool(self.config.get("clean_box", True))

    def _get_clean_text_mode(self) -> bool:
        val = self.config.get("screen_clean_text_mode")
        if val is not None:
            return bool(val)
        return bool(self.config.get("clean_text_mode", False))

    def _get_click_through(self) -> bool:
        val = self.config.get("screen_click_through")
        if val is not None:
            return bool(val)
        return bool(self.config.get("click_through", False))

    def _init_ui(self):
        self.setWindowTitle(tr("overlay_screen_title"))
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMinimumSize(930, 120)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 8, 14, 8)
        self.main_layout.setSpacing(6)

        self.setStyleSheet("""
            QToolTip {
                background-color: #141C2E;
                color: #F8FAFC;
                border: 1px solid #283858;
                border-radius: 5px;
                padding: 5px 9px;
                font-size: 12px;
                font-weight: normal;
                font-family: 'Malgun Gothic', '맑은 고딕', 'Segoe UI', sans-serif;
            }
        """)

        # 헤더 바
        self.header_widget = QWidget()
        self.header_widget.setFixedHeight(32)
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(4, 3, 4, 3)
        self.header_layout.setSpacing(3)

        self.title_label = QLabel("👁️ " + tr("screen_translation"))
        self.title_label.setFixedHeight(26)
        self.title_label.setToolTip(tr("overlay_screen_tip"))
        self.title_label.setStyleSheet("QLabel { color: rgba(120, 220, 255, 0.9); font-size: 11px; font-weight: bold; }")
        self.header_layout.addWidget(self.title_label)

        # 1. 일시정지 토글
        init_paused = not (self.config.get("auto_start_screen", False) and self.config.get("screen_translate_enabled", False))
        self.btn_pause = QPushButton("▶" if init_paused else "⏸")
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.setFixedHeight(26)
        self.btn_pause.setFixedWidth(32)
        if init_paused:
            self.btn_pause.setStyleSheet("QPushButton { background-color: rgba(180, 40, 40, 0.85); color: #FFF; font-weight: bold; border: 1.5px solid #FF5252; border-radius: 4px; padding: 0px; margin: 0px; text-align: center; font-size: 12px; }")
            self.btn_pause.setToolTip(tr("overlay_pause_on"))
        else:
            self.btn_pause.setStyleSheet("QPushButton { background-color: rgba(30, 40, 55, 0.75); color: #EEE; font-weight: bold; border-radius: 4px; padding: 0px; margin: 0px; text-align: center; font-size: 12px; }")
            self.btn_pause.setToolTip(tr("overlay_pause_off"))
        self.btn_pause.clicked.connect(self._on_pause_clicked)
        self.header_layout.addWidget(self.btn_pause)

        # 2. ROI 영역 지정 버튼
        self.btn_roi = QPushButton("📐")
        self.btn_roi.setToolTip(tr("overlay_tip_roi"))
        self.btn_roi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_roi.setFixedHeight(26)
        self.btn_roi.setFixedWidth(32)
        self.btn_roi.clicked.connect(self._on_roi_clicked)
        self.header_layout.addWidget(self.btn_roi)

        # 3. 즉시 캡처 번역 버튼 (⚡ 번개 아이콘)
        self.btn_snap = QPushButton("⚡")
        self.btn_snap.setToolTip(tr("overlay_tip_snap"))
        self.btn_snap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_snap.setFixedHeight(26)
        self.btn_snap.setFixedWidth(32)
        self.btn_snap.clicked.connect(self._on_snap_clicked)
        self.header_layout.addWidget(self.btn_snap)

        # 3-0. 전체 화면 즉시 번역 버튼 (📷 카메라 아이콘)
        cur_hk = self.config.get("inplace_hotkey", "F4")
        self.btn_inplace = QPushButton("📷")
        self.btn_inplace.setToolTip(tr("overlay_tip_inplace", key=cur_hk))
        self.btn_inplace.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_inplace.setFixedHeight(26)
        self.btn_inplace.setFixedWidth(32)
        self.btn_inplace.setStyleSheet("""
            QPushButton {
                background-color: rgba(99, 102, 241, 0.75);
                color: #FFFFFF;
                font-weight: bold;
                border: 1px solid #818CF8;
                border-radius: 4px;
                padding: 0px;
                margin: 0px;
                text-align: center;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4F46E5;
            }
        """)
        self.btn_inplace.clicked.connect(self._on_inplace_clicked)
        self.header_layout.addWidget(self.btn_inplace)

        # 3-1. ROI 자석 밀착 토글 버튼
        self.btn_snap_roi = QPushButton("🧲")
        self.btn_snap_roi.setToolTip(tr("overlay_tip_snap_roi"))
        self.btn_snap_roi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_snap_roi.setFixedHeight(26)
        self.btn_snap_roi.setFixedWidth(32)
        self.btn_snap_roi.clicked.connect(self.toggle_snap_to_roi)
        self.header_layout.addWidget(self.btn_snap_roi)

        # 3-2. 감시 영역 외곽 엣지(테두리) 화면 오버랩 토글 버튼
        self.btn_border = QPushButton("🔲")
        self.btn_border.setToolTip(tr("overlay_tip_border"))
        self.btn_border.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_border.setFixedHeight(26)
        self.btn_border.setFixedWidth(32)
        self.btn_border.clicked.connect(self._on_border_clicked)
        self.header_layout.addWidget(self.btn_border)

        # 3-3. 클린 텍스트 모드 토글 버튼
        self.btn_clean = QPushButton("✨")
        self.btn_clean.setToolTip(tr("overlay_tip_clean"))
        self.btn_clean.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clean.setFixedHeight(26)
        self.btn_clean.setFixedWidth(32)
        self.btn_clean.clicked.connect(self.toggle_clean_mode)
        self.header_layout.addWidget(self.btn_clean)

        # 3-4. 반투명 배경 박스(자막 바) 토글 버튼 (▣)
        self.btn_box = QPushButton("▣")
        self.btn_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_box.setFixedHeight(26)
        self.btn_box.setFixedWidth(32)
        self.btn_box.clicked.connect(self.toggle_clean_box)
        self.header_layout.addWidget(self.btn_box)

        # 4. 실시간 상태 뱃지 (폭을 56px로 엄격히 제한하고 말줄임표 처리하여 겹침 방지)
        self.live_badge = ElidedBadgeLabel(tr("overlay_waiting"))
        self._is_waiting = True
        self.live_badge.setFixedHeight(26)
        self.live_badge.setFixedWidth(56)
        self.live_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.live_badge.setStyleSheet("""
            QLabel {
                background-color: rgba(20, 35, 55, 0.85);
                color: rgba(140, 220, 255, 0.85);
                border: 1px solid rgba(0, 200, 255, 0.25);
                border-radius: 4px;
                font-size: 9px;
                font-weight: bold;
                padding: 0px 2px;
            }
        """)
        if not self.config.get("show_engine_badge", True):
            self.live_badge.hide()
        self.header_layout.addWidget(self.live_badge)

        # 5. 글자 크기 조절
        self.btn_font_dec = QPushButton("A-")
        self.btn_font_dec.setFixedHeight(26)
        self.btn_font_dec.setFixedWidth(36)
        self.btn_font_dec.clicked.connect(self._decrease_font)
        self.header_layout.addWidget(self.btn_font_dec)

        self.btn_font_inc = QPushButton("A+")
        self.btn_font_inc.setFixedHeight(26)
        self.btn_font_inc.setFixedWidth(36)
        self.btn_font_inc.clicked.connect(self._increase_font)
        self.header_layout.addWidget(self.btn_font_inc)

        # 6. 투명도 조절
        self.btn_op_dec = QPushButton("◐-")
        self.btn_op_dec.setFixedHeight(26)
        self.btn_op_dec.setFixedWidth(36)
        self.btn_op_dec.clicked.connect(self._decrease_opacity)
        self.header_layout.addWidget(self.btn_op_dec)

        self.btn_op_inc = QPushButton("◐+")
        self.btn_op_inc.setFixedHeight(26)
        self.btn_op_inc.setFixedWidth(36)
        self.btn_op_inc.clicked.connect(self._increase_opacity)
        self.header_layout.addWidget(self.btn_op_inc)

        # 6-0. 원문/번역문 표시 토글 버튼 (아이콘: 🔤 / 🌐)
        self.btn_toggle_en = QPushButton("🔤")
        self.btn_toggle_en.setToolTip(tr("overlay_tip_orig_on"))
        self.btn_toggle_en.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_en.setFixedHeight(26)
        self.btn_toggle_en.setFixedWidth(32)
        self.btn_toggle_en.clicked.connect(self._toggle_show_original)
        self.header_layout.addWidget(self.btn_toggle_en)

        self.btn_toggle_ko = QPushButton("🌐")
        self.btn_toggle_ko.setToolTip(tr("overlay_tip_trans_on"))
        self.btn_toggle_ko.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_ko.setFixedHeight(26)
        self.btn_toggle_ko.setFixedWidth(32)
        self.btn_toggle_ko.clicked.connect(self._toggle_show_translated)
        self.header_layout.addWidget(self.btn_toggle_ko)

        self._show_translated = self._get_show_translated()
        self._update_en_ko_button_styles()

        # 5-2. 실시간 AI 화면 더빙 토글 버튼
        self.btn_dubbing = QPushButton("🔊")
        self.btn_dubbing.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        self.btn_dubbing.setToolTip(tr("overlay_tip_screen_dubbing_on") if self.is_dubbing_enabled else tr("overlay_tip_screen_dubbing_off"))
        self.btn_dubbing.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dubbing.setFixedHeight(26)
        self.btn_dubbing.setFixedWidth(32)
        self.btn_dubbing.clicked.connect(self._toggle_dubbing)
        self.header_layout.addWidget(self.btn_dubbing)
        self._update_dubbing_button_style()

        # 5-3. 화자 이름 표시 토글 버튼 (🗣️)
        self.btn_speaker = QPushButton("🗣️")
        self.btn_speaker.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        self.btn_speaker.setToolTip(tr("overlay_tip_speaker_on") if self.show_speaker else tr("overlay_tip_speaker_off"))
        self.btn_speaker.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_speaker.setFixedHeight(26)
        self.btn_speaker.setFixedWidth(32)
        self.btn_speaker.clicked.connect(self.toggle_show_speaker)
        self.header_layout.addWidget(self.btn_speaker)
        self._update_speaker_button_style()

        # 6-1. 자막 화면 고정 (소거 방지) 버튼
        self.btn_pin = QPushButton("📌")
        self.btn_pin.setToolTip(tr("overlay_tip_pin_unpinned"))
        self.btn_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pin.setFixedHeight(26)
        self.btn_pin.setFixedWidth(32)
        self.btn_pin.clicked.connect(self.toggle_pin)
        self.header_layout.addWidget(self.btn_pin)

        self.header_layout.addStretch()

        # 7. 마우스 관통
        self.btn_lock = QPushButton("🔒")
        self.btn_lock.setToolTip(tr("overlay_tip_lock"))
        self.btn_lock.setFixedHeight(26)
        self.btn_lock.setFixedWidth(32)
        self.btn_lock.clicked.connect(self.toggle_click_through)
        self.header_layout.addWidget(self.btn_lock)

        # 7-1. 설정 (컨트롤 패널 열기) 버튼
        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setToolTip(tr("overlay_tip_settings"))
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setFixedHeight(26)
        self.btn_settings.setFixedWidth(32)
        self.btn_settings.clicked.connect(self._open_settings)
        self.header_layout.addWidget(self.btn_settings)

        # 8. 자막창 숨기기 (닫기) 버튼
        self.btn_hide = QPushButton("✕")
        self.btn_hide.setToolTip(tr("overlay_tip_hide"))
        self.btn_hide.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_hide.setFixedHeight(26)
        self.btn_hide.setFixedWidth(30)
        self.btn_hide.clicked.connect(self.hide)
        self.header_layout.addWidget(self.btn_hide)

        # 버튼 공통 스타일 (가운데 완벽 정렬)
        btn_style = """
            QPushButton {
                background-color: rgba(30, 40, 55, 0.75);
                color: #EEE;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 4px;
                padding: 0px;
                margin: 0px;
                text-align: center;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(50, 75, 110, 0.95);
                color: #FFF;
                border: 1px solid rgba(0, 200, 255, 0.5);
            }
        """
        for b in [self.btn_pause, self.btn_roi, self.btn_snap, self.btn_font_dec, self.btn_font_inc, self.btn_op_dec, self.btn_op_inc, self.btn_pin, self.btn_lock, self.btn_settings, self.btn_hide, self.btn_border]:
            b.setStyleSheet(btn_style)
        self._update_snap_button_style()
        self._update_clean_button_style()
        self._update_box_button_style()
        self._update_pin_button_style()
        self._update_border_button_style()
        self._update_speaker_button_style()

        # 헤더 자동 페이드
        self.header_opacity_effect = QGraphicsOpacityEffect(self.header_widget)
        self.header_widget.setGraphicsEffect(self.header_opacity_effect)
        self._set_header_chrome_opacity(1.0)
        self.main_layout.addWidget(self.header_widget)

        # 자막 텍스트 라벨
        self.label_original = QLabel("Monitoring Screen Area...")
        self.label_original.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_original.setWordWrap(True)
        self.label_original.setMinimumSize(0, 0)
        self.label_original.setTextFormat(Qt.TextFormat.RichText)

        self.label_translated = QLabel(tr("overlay_screen_placeholder"))
        self.label_translated.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_translated.setWordWrap(True)
        self.label_translated.setMinimumSize(0, 0)
        self.label_translated.setTextFormat(Qt.TextFormat.RichText)

        # 텍스트 효과 (0=기본 순수 소프트 섀도우 시스템 부하 0%, 1~5=외곽선 스트로크)
        self._apply_text_effect()
        self.label_translated.setContentsMargins(8, 8, 8, 8)
        self.label_original.setContentsMargins(8, 6, 8, 6)

        self.main_layout.addWidget(self.label_original)
        self.main_layout.addWidget(self.label_translated)
        self.label_original.setVisible(self._get_show_original())
        self.label_translated.setVisible(self._show_translated)

        # 우측 하단 크기 조절 그립 (숨김 시에도 레이아웃 공간을 유지하여 자막 텍스트 점프/위치 왜곡 원천 차단)
        grip_layout = QHBoxLayout()
        grip_layout.addStretch()
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("width: 12px; height: 12px; margin: 0px;")
        sp = self.size_grip.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self.size_grip.setSizePolicy(sp)
        grip_layout.addWidget(self.size_grip)
        self.main_layout.addLayout(grip_layout)
        if self.layout() is not None:
            from PyQt6.QtWidgets import QLayout
            self.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

    def _notify_config_change(self):
        """설정 변경 사항을 상위 매니저/저장 콜백으로 안전하게 전달"""
        if self.on_config_change:
            try:
                self.on_config_change(self.config, source_overlay=self)
            except TypeError:
                self.on_config_change(self.config)

    def _apply_text_effect(self):
        """텍스트 효과 적용 (0px: 순수 네이티브 소프트 섀도우, 1px+: 고대비 외곽선)"""
        stroke_w = self.config.get("subtitle_stroke_width", 0)
        if stroke_w == 0:
            # 순수 네이티브 소프트 섀도우 (시스템 부하 0%, 폰트 외곽선 없이 깔끔하고 자연스러운 그림자만 부여)
            shadow = QGraphicsDropShadowEffect(self.label_translated)
            shadow.setBlurRadius(5)
            shadow.setOffset(1.2, 1.5)
            shadow.setColor(QColor(0, 0, 0, 220))
            self.label_translated.setGraphicsEffect(shadow)

            orig_shadow = QGraphicsDropShadowEffect(self.label_original)
            orig_shadow.setBlurRadius(3)
            orig_shadow.setOffset(1.0, 1.0)
            orig_shadow.setColor(QColor(0, 0, 0, 180))
            self.label_original.setGraphicsEffect(orig_shadow)
            self.stroke_effect = shadow
            self.orig_stroke_effect = orig_shadow
        else:
            # 외곽선 스트로크 이펙트 (1px~5px)
            eff = ThickOutlineEffect(thickness=stroke_w, color=QColor(0, 0, 0, 240), parent=self.label_translated)
            self.label_translated.setGraphicsEffect(eff)
            orig_eff = ThickOutlineEffect(thickness=max(1, stroke_w - 1), color=QColor(0, 0, 0, 240), parent=self.label_original)
            self.label_original.setGraphicsEffect(orig_eff)
            self.stroke_effect = eff
            self.orig_stroke_effect = orig_eff

    def set_stroke_width(self, val: int):
        """외곽선 굵기 또는 섀도우 모드 동적 변경 (0=순수 섀도우, 1~5=외곽선)"""
        self.config["screen_subtitle_stroke_width"] = int(val)
        self.config["subtitle_stroke_width"] = int(val)
        self._apply_text_effect()
        self._subtitle_box_cache = None
        self._refresh_current_subtitle()
        self.update()
        if hasattr(self, 'label_translated'):
            self.label_translated.update()
        if hasattr(self, 'label_original'):
            self.label_original.update()
        self._notify_config_change()

    def set_letter_spacing(self, val: float):
        """글자 자간(간격) 동적 변경 (외곽선 뭉침 방지 및 가독성 향상)"""
        self.config["screen_letter_spacing"] = float(val)
        self.config["letter_spacing"] = float(val)
        self._apply_config(apply_geometry=False)
        self._subtitle_box_cache = None
        self._refresh_current_subtitle()
        self.update()
        if hasattr(self, 'label_translated'):
            self.label_translated.update()
        if hasattr(self, 'label_original'):
            self.label_original.update()
        self._notify_config_change()

    update_stroke_width = set_stroke_width
    update_letter_spacing = set_letter_spacing

    def set_badge_visible(self, visible: bool):
        """엔진 상태 뱃지 표시/숨기기"""
        self.config["screen_show_engine_badge"] = bool(visible)
        self.config["show_engine_badge"] = bool(visible)
        if hasattr(self, 'live_badge'):
            self.live_badge.setVisible(bool(visible))

    def toggle_clean_box(self):
        """반투명 배경 박스 온/오프 토글"""
        cur = self._get_clean_box()
        self.set_clean_box(not cur)

    def _update_box_button_style(self):
        if not hasattr(self, 'btn_box'):
            return
        enabled = self._get_clean_box()
        self.btn_box.setText("▣")
        self.btn_box.setFixedWidth(32)
        if enabled:
            self.btn_box.setStyleSheet("QPushButton { background-color: rgba(0, 150, 136, 0.85); color: #FFF; font-weight: bold; border: 1.5px solid #64FFDA; border-radius: 4px; padding: 0px; margin: 0px; text-align: center; font-size: 12px; }")
            self.btn_box.setToolTip(tr("overlay_tip_clean_box_on"))
        else:
            self.btn_box.setStyleSheet("QPushButton { background-color: rgba(30, 40, 55, 0.75); color: #888; font-weight: bold; border-radius: 4px; padding: 0px; margin: 0px; text-align: center; font-size: 12px; }")
            self.btn_box.setToolTip(tr("overlay_tip_clean_box_off"))

    def set_clean_box(self, enabled: bool):
        """자막 배경 박스(반투명 라운드 박스) 렌더링 온/오프"""
        self.config["screen_clean_box"] = bool(enabled)
        self._subtitle_box_cache = None
        self._refresh_current_subtitle()
        self._update_box_button_style()
        self.update()
        self.repaint()
        self._notify_config_change()
        if hasattr(self, 'ext_sync_clean_box') and self.ext_sync_clean_box:
            self.ext_sync_clean_box(bool(enabled))

    def set_show_original(self, enabled: bool):
        """원문 함께 표시 온/오프"""
        self.config["screen_show_original"] = bool(enabled)
        self.config["show_original"] = bool(enabled)
        if hasattr(self, 'label_original'):
            self.label_original.setVisible(bool(enabled))
        self._apply_config(apply_geometry=False)
        self.update()
        self._notify_config_change()
        self._update_en_ko_button_styles()
        if hasattr(self, 'ext_sync_show_original') and self.ext_sync_show_original:
            self.ext_sync_show_original(enabled)

    def set_show_translated(self, enabled: bool):
        """번역문 함께 표시 온/오프"""
        self._show_translated = bool(enabled)
        self.config["screen_show_translated"] = bool(enabled)
        self.config["show_translated"] = bool(enabled)
        if hasattr(self, 'label_translated'):
            self.label_translated.setVisible(bool(enabled))
        self._apply_config(apply_geometry=False)
        self.update()
        self._notify_config_change()
        self._update_en_ko_button_styles()
        if hasattr(self, 'ext_sync_show_translated') and self.ext_sync_show_translated:
            self.ext_sync_show_translated(enabled)

    def _toggle_show_original(self):
        """원문 버튼 클릭: 원문 표시 토글"""
        new_val = not self._get_show_original()
        # 번역문도 숨겨진 상태면 원문을 끌 수 없음
        if not new_val and not self._get_show_translated():
            return
        self.set_show_original(new_val)

    def _toggle_show_translated(self):
        """번역 버튼 클릭: 번역문 표시 토글"""
        new_val = not self._get_show_translated()
        # 원문도 숨겨진 상태면 번역문을 끌 수 없음
        if not new_val and not self._get_show_original():
            return
        self.set_show_translated(new_val)

    def _update_en_ko_button_styles(self):
        """원문/번역 토글 버튼의 활성/비활성 스타일 및 툴팁 업데이트"""
        if not hasattr(self, 'btn_toggle_en'):
            return
        en_on = self._get_show_original()
        ko_on = self._get_show_translated()
        style_on = (
            "QPushButton { background-color: rgba(0, 150, 136, 0.85); "
            "color: #FFFFFF; font-weight: bold; "
            "border: 1.5px solid rgba(0, 230, 200, 0.85); "
            "border-radius: 4px; padding: 0px; margin: 0px; text-align: center; font-size: 13px; }"
        )
        style_off = (
            "QPushButton { background-color: rgba(40, 44, 58, 0.60); "
            "color: rgba(200, 200, 200, 0.40); font-weight: bold; "
            "border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 4px; padding: 0px; margin: 0px; text-align: center; font-size: 13px; }"
        )
        self.btn_toggle_en.setStyleSheet(style_on if en_on else style_off)
        self.btn_toggle_ko.setStyleSheet(style_on if ko_on else style_off)
        self.btn_toggle_en.setToolTip(tr("overlay_tip_orig_on") if en_on else tr("overlay_tip_orig_off"))
        self.btn_toggle_ko.setToolTip(tr("overlay_tip_trans_on") if ko_on else tr("overlay_tip_trans_off"))

    def toggle_show_speaker(self):
        self.set_show_speaker(not self.show_speaker)

    def set_speaker_diarization_enabled(self, enabled: bool):
        self.speaker_diarization_enabled = bool(enabled)

    def set_show_speaker(self, enabled: bool):
        enabled = bool(enabled)
        already_same = (getattr(self, 'show_speaker', None) == enabled)
        self.show_speaker = enabled
        self.config["screen_show_speaker"] = enabled
        self.config["show_speaker"] = enabled
        self._update_speaker_button_style()
        if getattr(self, 'current_translated', None):
            self.display_subtitle(self.current_original, self.current_translated)
        if not already_same:
            self._notify_config_change()
            if hasattr(self, 'ext_sync_show_speaker') and self.ext_sync_show_speaker:
                self.ext_sync_show_speaker(enabled)

    def _update_speaker_button_style(self):
        if not hasattr(self, 'btn_speaker'):
            return
        self.btn_speaker.setEnabled(True)
        self.btn_speaker.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_speaker.setText("🗣️")
        self.btn_speaker.setFixedWidth(32)
        if self.show_speaker:
            self.btn_speaker.setStyleSheet("QPushButton { background-color: rgba(0, 150, 136, 0.85); color: #FFF; font-weight: bold; border: 1.5px solid #64FFDA; border-radius: 4px; padding: 0px; margin: 0px; text-align: center; font-size: 12px; }")
            self.btn_speaker.setToolTip(tr("overlay_tip_speaker_on"))
        else:
            self.btn_speaker.setStyleSheet("QPushButton { background-color: rgba(30, 40, 55, 0.75); color: #EEE; font-weight: bold; border-radius: 4px; padding: 0px; margin: 0px; text-align: center; font-size: 12px; }")
            self.btn_speaker.setToolTip(tr("overlay_tip_speaker_off"))
        self.btn_speaker.show()

    def _update_dubbing_button_style(self):
        if not hasattr(self, 'btn_dubbing'):
            return
        self.btn_dubbing.setText("🔊")
        self.btn_dubbing.setFixedWidth(32)
        if self.is_dubbing_enabled:
            self.btn_dubbing.setStyleSheet("""
                QPushButton {
                    background-color: rgba(139, 92, 246, 0.85);
                    color: #FFFFFF;
                    font-weight: bold;
                    border: 1.5px solid #A78BFA;
                    border-radius: 4px;
                    padding: 0px;
                    margin: 0px;
                    text-align: center;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: rgba(167, 139, 250, 0.95);
                    border: 1.5px solid #C4B5FD;
                }
            """)
            self.btn_dubbing.setToolTip(tr("overlay_tip_screen_dubbing_on"))
        else:
            self.btn_dubbing.setStyleSheet("""
                QPushButton {
                    background-color: rgba(45, 48, 62, 0.75);
                    color: #EEE;
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 4px;
                    padding: 0px;
                    margin: 0px;
                    text-align: center;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(60, 65, 85, 0.95);
                    color: #FFF;
                    border: 1px solid rgba(139, 92, 246, 0.5);
                }
            """)
            self.btn_dubbing.setToolTip(tr("overlay_tip_screen_dubbing_off"))

    def update_dubbing_state(self, enabled: bool):
        self.is_dubbing_enabled = bool(enabled)
        self._update_dubbing_button_style()

    def _toggle_dubbing(self):
        if hasattr(self, 'ext_toggle_dubbing') and self.ext_toggle_dubbing:
            self.ext_toggle_dubbing()
        else:
            self.update_dubbing_state(not self.is_dubbing_enabled)

    def apply_config(self, apply_geometry=False):
        """설정 변경 사항 적용 (스타일 동기화 시 다른 오버레이의 위치를 덮어쓰지 않도록 기본 apply_geometry=False)"""
        self._apply_config(apply_geometry=apply_geometry)

    def _label_sheet(self, size, *, bold=False, italic=False):
        extra = "font-weight: bold;" if bold else ""
        extra += "font-style: italic;" if italic else ""
        return f"QLabel {{ font-size: {size}px; background: transparent; {extra} }}"

    def _html_body(self, html, color, center=False):
        if html is None or html == "":
            return html
        if center:
            return f"<div style='color:{color};text-align:center;line-height:135%;'>{html}</div>"
        return f"<div style='color:{color};line-height:135%;'>{html}</div>"

    def _set_label_html(self, label, html, color):
        label.setText(self._html_body(html, color, center=True))

    def _apply_config(self, apply_geometry=True):
        if apply_geometry and not self.is_auto_resizing:
            geo_map = self.config.get("screen_overlay_geometries", {})
            idx_key = str(getattr(self, 'assigned_roi_idx', 0))
            if isinstance(geo_map, dict) and idx_key in geo_map and len(geo_map[idx_key]) == 4:
                geo = geo_map[idx_key]
            else:
                geo = self.config.get("screen_overlay_geometry", self.base_geometry)
            if len(geo) == 4:
                self.setGeometry(geo[0], geo[1], geo[2], geo[3])
                self.base_geometry = list(geo)

        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        roi_configs = self.config.get("roi_configs", {})
        roi_specific_cfg = roi_configs.get(idx_key, {}) if isinstance(roi_configs, dict) else {}

        font_size = self._get_font_size()
        orig_size = max(11, font_size - 5)  # _auto_fit_text·음성 자막창과 동일해야 첫 자막 때 창 높이가 변하지 않음
        letter_spacing = self._get_letter_spacing()

        # Qt QSS에서 인라인 폰트 크기 스타일이 setFont()를 덮어쓰지 않도록 동적 QSS 적용
        ko_font = QFont("Malgun Gothic", font_size, QFont.Weight.Bold)
        ko_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
        self.label_translated.setFont(ko_font)
        self.label_translated.setStyleSheet(self._label_sheet(font_size, bold=True))

        orig_font = QFont("Segoe UI", orig_size)
        orig_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(0.5, letter_spacing * 0.6))
        self.label_original.setFont(orig_font)
        self.label_original.setStyleSheet(self._label_sheet(orig_size, italic=True))

        if hasattr(self, 'btn_font_dec'):
            self.btn_font_dec.setToolTip(tr("overlay_tip_font_dec", size=font_size))
        if hasattr(self, 'btn_font_inc'):
            self.btn_font_inc.setToolTip(tr("overlay_tip_font_inc", size=font_size))

        pct = int(self._get_bg_opacity() * 100)
        dec_txt = tr("overlay_tip_op_dec_100", pct=pct) if pct == 0 else tr("overlay_tip_op_dec", pct=pct)
        if hasattr(self, 'btn_op_dec'):
            self.btn_op_dec.setToolTip(dec_txt)
        if hasattr(self, 'btn_op_inc'):
            self.btn_op_inc.setToolTip(tr("overlay_tip_op_inc", pct=pct))

        if self._get_click_through():
            self.set_click_through(True)

        if hasattr(self, 'live_badge'):
            self.live_badge.setVisible(self._get_show_badge())

        stroke_w = self._get_stroke_width()
        if stroke_w == 0:
            if not isinstance(getattr(self, 'stroke_effect', None), QGraphicsDropShadowEffect):
                self._apply_text_effect()
        else:
            if not isinstance(getattr(self, 'stroke_effect', None), ThickOutlineEffect) or getattr(self.stroke_effect, 'thickness', 0) != stroke_w:
                self._apply_text_effect()

        # 현재 표시 중인 자막이 있다면 폰트 크기 변경에 맞추어 텍스트 반응형 재계산
        if getattr(self, 'current_translated', None):
            formatted_ko = self.format_korean_dialogue(self.current_translated)
            if self.config.get("screen_snap_to_roi", False) and not getattr(self, 'is_user_positioned', False):
                target_roi = getattr(self, 'assigned_roi', None) or self._get_target_roi_from_text(self.current_translated)
                if target_roi:
                    self.snap_to_roi(target_roi)
            self._auto_fit_text(self.format_original_text(getattr(self, 'current_original', '')), formatted_ko)

        # 자막 유지 시간 설정 변경 반영
        badge_txt = self.live_badge.text() if hasattr(self, 'live_badge') else ""
        is_instant = "즉시" in badge_txt.lower() or "instant" in badge_txt.lower()
        if "duration" in roi_specific_cfg:
            duration_sec = int(roi_specific_cfg["duration"])
        else:
            duration_sec = self.config.get("screen_subtitle_duration", 5)
        if hasattr(self, 'clear_timer'):
            if duration_sec == 0 or getattr(self, 'is_pinned', False) or is_instant:
                self.clear_timer.stop()
            elif duration_sec > 0 and getattr(self, 'current_translated', None) and not getattr(self, 'is_mouse_hovered', False):
                self.clear_timer.start(duration_sec * 1000)

        if hasattr(self, '_update_box_button_style'):
            self._update_box_button_style()
        if hasattr(self, '_update_pin_button_style'):
            self._update_pin_button_style()
        if hasattr(self, '_update_border_button_style'):
            self._update_border_button_style()
        if hasattr(self, '_update_snap_button_style'):
            self._update_snap_button_style()
        if hasattr(self, '_update_clean_button_style'):
            self._update_clean_button_style()
        if hasattr(self, '_update_speaker_button_style'):
            self._update_speaker_button_style()

        self._apply_two_line_overlay_height()
        self.update()

    @staticmethod
    def _is_waiting_badge_text(txt: str) -> bool:
        if not txt:
            return True
        clean = txt.strip()
        waiting_variants = {
            "대기 중", "Waiting", "Waiting...", "準備中", "待機中", "等待中",
            "En espera", "En attente", "Warten", "Aguardando", "Ожидание",
            "In attesa", "Đang chờ", "กำลังรอ", "Menunggu", "قيد الانتظار", "प्रतीक्षारत"
        }
        return clean in waiting_variants or "대기" in clean or "wait" in clean.lower()

    @staticmethod
    def _is_paused_badge_text(txt: str) -> bool:
        if not txt:
            return False
        clean = txt.strip()
        paused_variants = {
            "일시정지됨", "일시정지", "Paused", "一時停止中", "一時停止", "已暂停",
            "En pausa", "En pause", "Pausiert", "Em pausa", "На паузе", "Пауза",
            "In pausa", "Đang tạm dừng", "หยุดชั่วคราว", "Dijeda", "متوقف مؤقتًا", "متوقف", "रुका हुआ"
        }
        return clean in paused_variants or "일시정지" in clean or "pause" in clean.lower()

    def _apply_ui_language(self):
        self.setWindowTitle(tr("overlay_screen_title"))
        cur_hk = self.config.get("inplace_hotkey", "F4")
        if hasattr(self, "title_label") and self.title_label:
            if not getattr(self, "is_click_through", False):
                idx = getattr(self, "assigned_roi_idx", 0)
                is_multi = getattr(self, "is_multi", False)
                title = f"👁️ {tr('screen_translation')} #{idx + 1}" if is_multi else f"👁️ {tr('screen_translation')}"
                self.title_label.setText(title)
            else:
                self.title_label.setText(tr("overlay_click_through_active"))
        if hasattr(self, "btn_pause") and self.btn_pause:
            paused = getattr(self, "is_paused", False)
            self.btn_pause.setToolTip(tr("overlay_pause_on") if paused else tr("overlay_pause_off"))
        if hasattr(self, "btn_roi") and self.btn_roi:
            self.btn_roi.setToolTip(tr("overlay_tip_roi"))
        if hasattr(self, "btn_snap") and self.btn_snap:
            self.btn_snap.setToolTip(tr("overlay_tip_snap"))
        if hasattr(self, "btn_inplace") and self.btn_inplace:
            self.btn_inplace.setToolTip(tr("overlay_tip_inplace", key=cur_hk))
        if hasattr(self, "btn_snap_roi") and self.btn_snap_roi:
            self.btn_snap_roi.setToolTip(tr("overlay_tip_snap_roi"))
        if hasattr(self, "btn_border") and self.btn_border:
            self.btn_border.setToolTip(tr("overlay_tip_border"))
        if hasattr(self, "btn_clean") and self.btn_clean:
            self.btn_clean.setToolTip(tr("overlay_tip_clean"))
        if hasattr(self, "live_badge") and self.live_badge:
            if getattr(self, "is_paused", False) or self._is_paused_badge_text(self.live_badge.text()):
                self.is_paused = True
                self._is_waiting = False
                self.live_badge.setText(tr("ocr_status_paused"))
            elif getattr(self, "_is_waiting", True) or self._is_waiting_badge_text(self.live_badge.text()):
                self._is_waiting = True
                self.live_badge.setText(tr("overlay_waiting"))
        if hasattr(self, "btn_font_dec") and self.btn_font_dec:
            font_size = self.config.get("screen_font_size", 22)
            self.btn_font_dec.setToolTip(tr("overlay_tip_font_dec", size=font_size))
        if hasattr(self, "btn_font_inc") and self.btn_font_inc:
            font_size = self.config.get("screen_font_size", 22)
            self.btn_font_inc.setToolTip(tr("overlay_tip_font_inc", size=font_size))
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        roi_configs = self.config.get("roi_configs", {})
        roi_specific_cfg = roi_configs.get(idx_key, {}) if isinstance(roi_configs, dict) else {}
        if "opacity" in roi_specific_cfg:
            cur_op_pct = int(roi_specific_cfg["opacity"])
        else:
            cur_op_pct = int(self._normalize_bg_opacity(self.config.get("overlay_bg_opacity", 0.75)) * 100)
        if hasattr(self, "btn_op_dec") and self.btn_op_dec:
            self.btn_op_dec.setToolTip(tr("overlay_tip_op_dec_100", pct=cur_op_pct) if cur_op_pct == 0 else tr("overlay_tip_op_dec", pct=cur_op_pct))
        if hasattr(self, "btn_op_inc") and self.btn_op_inc:
            self.btn_op_inc.setToolTip(tr("overlay_tip_op_inc", pct=cur_op_pct))
        if hasattr(self, "_update_en_ko_button_styles"):
            self._update_en_ko_button_styles()
        if hasattr(self, "_update_dubbing_button_style"):
            self._update_dubbing_button_style()
        if hasattr(self, "_update_speaker_button_style"):
            self._update_speaker_button_style()
        if hasattr(self, "_update_clean_button_style"):
            self._update_clean_button_style()
        if hasattr(self, "_update_box_button_style"):
            self._update_box_button_style()
        if hasattr(self, "btn_pin") and self.btn_pin:
            is_pinned = getattr(self, "is_pinned", False)
            self.btn_pin.setToolTip(tr("overlay_tip_pin_pinned") if is_pinned else tr("overlay_tip_pin_unpinned"))
        if hasattr(self, "btn_lock") and self.btn_lock:
            self.btn_lock.setToolTip(tr("overlay_tip_lock"))
        if hasattr(self, "btn_settings") and self.btn_settings:
            self.btn_settings.setToolTip(tr("overlay_tip_settings"))
        if hasattr(self, "btn_hide") and self.btn_hide:
            self.btn_hide.setToolTip(tr("overlay_tip_hide"))
        if hasattr(self, "label_translated") and self.label_translated:
            if not getattr(self, "current_translated", None):
                self._set_label_html(self.label_translated, tr("overlay_screen_placeholder"), "#FFFFFF")
        self.update()

    def _refresh_current_subtitle(self):
        """현재 화면에 렌더링 중인 자막을 새 폰트 크기/자간/외곽선 스타일로 즉시 재포맷 및 리페인트"""
        if not getattr(self, "current_translated", None):
            return
        if getattr(self, "_is_waiting", False):
            return
        orig = getattr(self, "current_original", "") or ""
        trans = getattr(self, "current_translated", "") or ""
        formatted_ko = self.format_korean_dialogue(trans)
        formatted_en = self.format_original_text(orig)
        self._auto_fit_text(formatted_en, formatted_ko)
        self._set_label_html(self.label_original, formatted_en, self.config.get("original_color", "#AAAAAA"))
        self._set_label_html(self.label_translated, formatted_ko, self.config.get("text_color", "#FFFFFF"))
        self._subtitle_box_cache = None
        self.update()

    def update_duration(self, val: int):
        self.subtitle_duration = int(val)
        self.config["screen_subtitle_duration"] = int(val)
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        roi_configs = self.config.get("roi_configs", {})
        if isinstance(roi_configs, dict) and idx_key in roi_configs:
            roi_configs[idx_key]["duration"] = int(val)
        self._apply_config(apply_geometry=False)
        self._notify_config_change()

    set_subtitle_duration = update_duration

    def set_external_handlers(self, on_toggle_pause=None, on_trigger_roi=None,
                              on_trigger_instant=None, on_trigger_inplace=None, on_open_settings=None,
                              on_sync_snap=None, on_visibility_change=None,
                              on_sync_font=None, on_sync_opacity=None,
                              on_toggle_border=None, on_sync_click_through=None,
                              on_sync_clean_text=None, on_sync_clean_box=None, on_sync_show_speaker=None,
                              on_toggle_dubbing=None, on_sync_show_original=None, on_sync_show_translated=None):
        self.ext_toggle_pause = on_toggle_pause
        self.ext_trigger_roi = on_trigger_roi
        self.ext_trigger_instant = on_trigger_instant
        self.ext_trigger_inplace = on_trigger_inplace
        self.ext_open_settings = on_open_settings
        self.ext_sync_snap = on_sync_snap
        self.ext_visibility_change = on_visibility_change
        self.ext_sync_font = on_sync_font
        self.ext_sync_opacity = on_sync_opacity
        self.ext_toggle_border = on_toggle_border
        self.ext_sync_click_through = on_sync_click_through
        self.ext_sync_clean_text = on_sync_clean_text
        self.ext_sync_clean_box = on_sync_clean_box
        self.ext_sync_show_speaker = on_sync_show_speaker
        self.ext_toggle_dubbing = on_toggle_dubbing
        self.ext_sync_show_original = on_sync_show_original
        self.ext_sync_show_translated = on_sync_show_translated

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_capture_exclusion()
        if hasattr(self, 'idle_timer'):
            self.idle_timer.start(3500)
        if hasattr(self, 'ext_visibility_change') and self.ext_visibility_change:
            self.ext_visibility_change(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, 'ext_visibility_change') and self.ext_visibility_change:
            self.ext_visibility_change(False)

    def _apply_capture_exclusion(self):
        """윈도우 화면 캡처 시 자막창 자체를 100% 투명하게 제외 (OCR 자기 복제 및 CPU 90% 무한 루프 완벽 차단)"""
        try:
            import ctypes
            hwnd = int(self.winId())
            if hwnd:
                WDA_EXCLUDEFROMCAPTURE = 0x00000011
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        except Exception:
            pass

    def format_korean_dialogue(self, text: str) -> str:
        """대화형 자막 줄바꿈 및 가독성 최적화 (화자별 줄바꿈, 영역 구분 줄바꿈, 화자 강조, 자연스러운 단락 유지)"""
        if not text:
            return ""
        import re
        text = re.sub(r'\s+', ' ', text).strip()

        # 1. 화자 변경 감지 줄바꿈 (예: "...입니다. 진행자: ..." -> "\n진행자: ...")
        text = re.sub(r'([.!?~])\s*([가-힣a-zA-Z0-9\'.\-\s]{2,30}:)', r'\1\n\2', text)

        # 2. 다중 영역 태그([영역 N]) 감지 줄바꿈
        text = re.sub(r'([.!?~]|\b)\s*(\[영역\s*\d+\])', r'\1\n\2', text).strip()

        # 3. 문장 마침 부호 뒤에서 줄바꿈. 한국어 도착 자막만 한국어 줄바꿈을 쓴다.
        from src.subtitle_manager import break_subtitle_text
        target_lang = self.config.get("target_lang", "ko") if hasattr(self, "config") else "ko"
        text = break_subtitle_text(text, target_lang=target_lang, linebreak='\n')

        # 4. 화자 이름 및 [영역 N] 태그 시각화 강조
        lines = text.split('\n')
        res_lines = []
        for ln in lines:
            # 1) 화자 이름 먼저 감지 (예: "[영역 1] 진행자: 다음 순서는...")
            m = re.match(r'^(.*?)(([가-힣a-zA-Z0-9\'.\-\s]{2,30}:)\s*)(.*)', ln)
            if m:
                prefix = m.group(1)
                speaker = m.group(3)
                dialogue = m.group(4)
                if getattr(self, 'show_speaker', True):
                    line_html = f"{prefix}<b style='color: #64B5F6;'>{speaker}</b> {dialogue}"
                else:
                    line_html = f"{prefix}{dialogue}"
            else:
                line_html = ln

            # 2) 그 후 [영역 N] 태그 하이라이트 치환 (HTML 속성 내 color: 와의 충돌 방지)
            line_html = re.sub(
                r'(\[영역\s*\d+\])',
                r"<span style='color: #00E5FF; font-weight: bold;'>\1</span>",
                line_html
            )
            res_lines.append(line_html)

        return "<br>".join(res_lines)

    def format_original_text(self, text: str) -> str:
        """대화형 원문(영문) 자막 줄바꿈 및 가독성 최적화 (화자별 줄바꿈, 영역 구분 줄바꿈, 화자 강조, 스마트 줄바꿈)"""
        if not text:
            return ""
        import re
        from src.subtitle_manager import smart_break_sentences
        text = re.sub(r'\s+', ' ', text).strip()

        # 1. 화자 변경 감지 줄바꿈 (예: "...hello. Alex Chen: ..." -> "\nAlex Chen: ...")
        text = re.sub(r'([.!?~])\s*([a-zA-Z0-9\'.\-\s]{2,30}:)', r'\1\n\2', text)

        # 2. 다중 영역 태그 감지 줄바꿈 ([Area N], [ROI N], [영역 N])
        text = re.sub(r'([.!?~]|\b)\s*(\[(?:Area|ROI|영역)\s*\d+\])', r'\1\n\2', text, flags=re.IGNORECASE).strip()

        # 3. 문장 마침 부호 뒤 스마트 줄바꿈 (약어 보호, 1줄 또는 최대 2줄 제한, 감탄사/단문 보호)
        text = smart_break_sentences(text, linebreak='\n')

        # 4. 화자 이름 및 영역 태그 시각화 강조
        lines = text.split('\n')
        res_lines = []
        for ln in lines:
            m = re.match(r'^(.*?)(([a-zA-Z0-9\'.\-\s]{2,30}:)\s*)(.*)', ln)
            if m:
                prefix = m.group(1)
                speaker = m.group(3)
                dialogue = m.group(4)
                if getattr(self, 'show_speaker', True):
                    line_html = f"{prefix}<b style='color: #64B5F6;'>{speaker}</b> {dialogue}"
                else:
                    line_html = f"{prefix}{dialogue}"
            else:
                line_html = ln

            line_html = re.sub(
                r'(\[(?:Area|ROI|영역)\s*\d+\])',
                r"<span style='color: #00E5FF; font-weight: bold;'>\1</span>",
                line_html,
                flags=re.IGNORECASE
            )
            res_lines.append(line_html)

        return "<br>".join(res_lines)

    def set_snap_to_roi(self, enabled: bool):
        self.config["screen_snap_to_roi"] = bool(enabled)
        self.is_user_positioned = False
        self._update_snap_button_style()
        if hasattr(self, 'ext_sync_snap') and self.ext_sync_snap:
            self.ext_sync_snap(bool(enabled))
        self._notify_config_change()
        if enabled:
            effective_roi = getattr(self, 'assigned_roi', None) or self._get_target_roi_from_text(self.current_translated)
            if effective_roi:
                self.snap_to_roi(effective_roi)

    def toggle_snap_to_roi(self):
        new_val = not self.config.get("screen_snap_to_roi", False)
        self.set_snap_to_roi(new_val)

    def _update_snap_button_style(self):
        enabled = self.config.get("screen_snap_to_roi", False)
        self.btn_snap_roi.setText("🧲")
        self.btn_snap_roi.setFixedWidth(32)
        if enabled:
            self.btn_snap_roi.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 150, 100, 0.85);
                    color: #00E676;
                    border: 1.5px solid #00E676;
                    border-radius: 4px;
                    padding: 0px;
                    margin: 0px;
                    text-align: center;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)
        else:
            self.btn_snap_roi.setStyleSheet("""
                QPushButton {
                    background-color: rgba(30, 40, 55, 0.75);
                    color: #BBB;
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 4px;
                    padding: 0px;
                    margin: 0px;
                    text-align: center;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)

    def _update_border_button_style(self):
        if not hasattr(self, 'btn_border'):
            return
        enabled = self.config.get("screen_show_roi_border", False)
        self.btn_border.setText("🔲")
        self.btn_border.setFixedWidth(32)
        if enabled:
            self.btn_border.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 137, 123, 0.85);
                    color: #A7FFEB;
                    border: 1.5px solid #64FFDA;
                    border-radius: 4px;
                    padding: 0px;
                    margin: 0px;
                    text-align: center;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)
        else:
            self.btn_border.setStyleSheet("""
                QPushButton {
                    background-color: rgba(30, 40, 55, 0.75);
                    color: #BBB;
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 4px;
                    padding: 0px;
                    margin: 0px;
                    text-align: center;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)

    def _on_border_clicked(self):
        if hasattr(self, 'ext_toggle_border') and self.ext_toggle_border:
            self.ext_toggle_border()
            self._update_border_button_style()
        else:
            cur = not self.config.get("screen_show_roi_border", False)
            self.config["screen_show_roi_border"] = cur
            self._notify_config_change()
            self._update_border_button_style()

    def _calc_needed_height(self, formatted_ko: str) -> int:
        if not formatted_ko:
            return self.height()
        import re
        plain = re.sub(r'<br\s*/?>', '\n', formatted_ko)
        plain = re.sub(r'<[^>]+>', '', plain)
        avail_w = max(120, self.width() - 40)
        font = self.label_translated.font()
        fm = QFontMetrics(font)
        bounding = fm.boundingRect(0, 0, avail_w, 10000, int(Qt.TextFlag.TextWordWrap), plain)
        text_h = bounding.height()
        overhead = 56 if not self.clean_text_mode else 16
        needed = overhead + text_h + 10
        if self.config.get("show_original", True) and self.label_original.text():
            needed += 22
        return needed

    def _get_target_roi_from_text(self, text: str):
        import re
        rois = self.config.get("screen_rois", [])
        m = re.search(r'\[영역\s*(\d+)\]', text or "")
        if m and rois:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(rois):
                return rois[idx]
        assigned_idx = getattr(self, 'assigned_roi_idx', None)
        if assigned_idx is not None and 0 <= assigned_idx < len(rois):
            return rois[assigned_idx]
        if getattr(self, 'assigned_roi', None):
            return self.assigned_roi
        if rois:
            return rois[0]
        return self.config.get("screen_roi")

    def snap_to_roi(self, roi, needed_height=None):
        """
        지정된 ROI의 위치 및 주변 가용 공간을 계산하여 자막창을 위/아래로 지능형 밀착 배치
        """
        if not roi or len(roi) < 4:
            return

        rx, ry, rw, rh = int(roi[0]), int(roi[1]), int(roi[2]), int(roi[3])
        if rw <= 10 or rh <= 10:
            return

        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QPoint

        app = QApplication.instance()
        if not app:
            return

        center = QPoint(rx + rw // 2, ry + rh // 2)
        screen = app.screenAt(center) or app.primaryScreen()
        if not screen:
            return

        s_geo = screen.geometry()

        # 자막창 높이 결정: 외부 지정(단위 테스트 등)이 없으면 현재 사용자가 설정한 높이 엄격 유지
        if needed_height is not None:
            oh = needed_height
        else:
            oh = self.base_geometry[3]
        oh = min(max(self.minimumHeight(), int(oh)), max(self.minimumHeight(), s_geo.height() - 30))

        # 가로 너비 결정: 사용자가 수동 조절한 경우 그 너비 유지, 아니면 ROI 너비에 맞춤
        if getattr(self, 'is_user_sized', False):
            ow = self.base_geometry[2]
        else:
            ow = max(self.base_geometry[2], min(rw + 40, s_geo.width() - 40))
        ow = min(max(self.minimumWidth(), int(ow)), max(self.minimumWidth(), s_geo.width() - 30))

        # 가로 중심축 정렬
        target_x = rx + (rw - ow) // 2
        target_x = max(s_geo.x() + 15, min(target_x, s_geo.x() + s_geo.width() - ow - 15))

        # 세로 가용 공간 계산
        margin = 12
        space_above = ry - s_geo.y()
        space_below = (s_geo.y() + s_geo.height()) - (ry + rh)

        # 1. 하단 자막창인 경우 (위쪽 공간이 충분하면 무조건 위쪽에 배치)
        if space_above >= oh + margin:
            target_y = ry - oh - margin
        # 2. 상단 알림/메뉴인 경우 (아래쪽 공간이 충분하면 아래쪽에 배치)
        elif space_below >= oh + margin:
            target_y = ry + rh + margin
        # 3. 화면을 가득 채운 초대형 영역인 경우 (영역 내부 하단에 정렬)
        else:
            target_y = max(s_geo.y() + 15, ry + rh - oh - 10)
        target_y = max(s_geo.y() + 15, min(target_y, s_geo.y() + s_geo.height() - oh - 15))

        # 부드럽게 지오메트리 적용
        self.is_auto_resizing = True
        self.setGeometry(target_x, target_y, ow, oh)
        self.is_auto_resizing = False

    def _auto_fit_text(self, original_text: str, formatted_ko: str, adjust_window: bool = True):
        """설정한 글자 크기를 유지한다. 창 크기에 따라 축소하지 않는다."""
        idx_key = str(getattr(self, "assigned_roi_idx", 0))
        roi_configs = self.config.get("roi_configs", {})
        roi_specific_cfg = roi_configs.get(idx_key, {}) if isinstance(roi_configs, dict) else {}
        font_size = int(roi_specific_cfg.get("font_size", self.config.get("font_size", 22)))
        letter_spacing = float(self.config.get("letter_spacing", 2.0))
        show_orig = self.config.get("show_original", True) and bool(original_text and original_text.strip())

        ko_font = QFont("Malgun Gothic", font_size, QFont.Weight.Bold)
        ko_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
        self.label_translated.setFont(ko_font)
        self.label_translated.setStyleSheet(self._label_sheet(font_size, bold=True))

        if show_orig:
            en_sz = max(11, font_size - 5)
            orig_font = QFont("Segoe UI", en_sz)
            orig_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(0.5, letter_spacing * 0.6))
            self.label_original.setFont(orig_font)
            self.label_original.setStyleSheet(self._label_sheet(en_sz, italic=True))
        if adjust_window:
            self._apply_two_line_overlay_height()

    def display_status(self, status: str):
        self._is_waiting = self._is_waiting_badge_text(status)
        is_paused = self._is_paused_badge_text(status)
        self.is_paused = is_paused
        if hasattr(self, 'btn_pause') and self.btn_pause:
            if is_paused:
                self.btn_pause.setText("▶")
                self.btn_pause.setStyleSheet("QPushButton { background-color: rgba(180, 40, 40, 0.85); color: #FFF; font-weight: bold; border: 1.5px solid #FF5252; border-radius: 4px; padding: 0px; margin: 0px; text-align: center; font-size: 12px; }")
                self.btn_pause.setToolTip(tr("overlay_pause_on"))
            elif self._is_waiting:
                self.btn_pause.setText("⏸")
                self.btn_pause.setStyleSheet("QPushButton { background-color: rgba(30, 40, 55, 0.75); color: #EEE; font-weight: bold; border-radius: 4px; padding: 0px; margin: 0px; text-align: center; font-size: 12px; }")
                self.btn_pause.setToolTip(tr("overlay_pause_off"))
        self.live_badge.setText(status)

    def display_subtitle(self, original_text: str, translated_text: str, engine_badge: str = "", target_roi: list = None):
        self._is_waiting = False
        self._subtitle_box_cache = None
        self.last_translated_time = time.time()
        self.current_original = original_text
        self.current_translated = translated_text
        if engine_badge:
            is_instant = "즉시" in engine_badge or "instant" in engine_badge.lower()
            from src.engine_badge import translation_badge, configured_translation_label
            engine, fallback = translation_badge(engine_badge, self.config)
            fallback_suffix = f" ({tr('badge_fallback')})" if fallback else ""
            if is_instant:
                self.live_badge.setText(f"⚡ {tr('badge_instant')} · {engine}{fallback_suffix}")
            else:
                self.live_badge.setText(f"OCR + {engine}{fallback_suffix}")
            self.live_badge.setToolTip(
                tr("screen_engine_fallback_tip", orig=configured_translation_label(self.config), engine=engine, badge=engine_badge)
                if fallback else tr("screen_engine_tip", engine=engine, badge=engine_badge))

        # 가독성 높은 대화형 줄바꿈 및 화자 하이라이트 적용
        formatted_ko = self.format_korean_dialogue(translated_text)
        formatted_en = self.format_original_text(original_text)

        # 🧲 영역 자동 밀착 모드가 켜져 있는 경우, 해당 영역 주변으로 자동 배치
        if self.config.get("screen_snap_to_roi", False) and not getattr(self, 'is_user_positioned', False):
            roi_to_snap = target_roi or getattr(self, 'assigned_roi', None) or self._get_target_roi_from_text(translated_text)
            if roi_to_snap:
                self.snap_to_roi(roi_to_snap)

        # 사용자가 설정/조절한 창 크기를 100% 엄격히 유지하며 텍스트 반응형 맞춤 (창 크기 절대 불변)
        self._auto_fit_text(formatted_en, formatted_ko)

        self._set_label_html(self.label_original, formatted_en, self.config.get("original_color", "#AAAAAA"))
        if self.config.get("show_original", True):
            self.label_original.show()
        else:
            self.label_original.hide()
        self.label_translated.setTextFormat(Qt.TextFormat.RichText)
        self._set_label_html(self.label_translated, formatted_ko, self.config.get("text_color", "#FFFFFF"))

        # ⏳ 자막 유지 시간 (초): 0이면 새 자막이 올 때까지 영구 유지 (무제한)
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        roi_configs = self.config.get("roi_configs", {})
        roi_specific_cfg = roi_configs.get(idx_key, {}) if isinstance(roi_configs, dict) else {}
        if "duration" in roi_specific_cfg:
            duration_sec = int(roi_specific_cfg["duration"])
        else:
            duration_sec = self.config.get("screen_subtitle_duration", 5)
        is_instant = "즉시" in (engine_badge or "") or "instant" in (engine_badge or "").lower()

        if self.is_pinned or is_instant or duration_sec == 0:
            # 1회 즉시 캡처 번역, 영구 유지(0초), 또는 📌 고정 모드: 소거 타이머 작동 중지 (무제한 영구 유지)
            self.clear_timer.stop()
        elif duration_sec > 0:
            if not getattr(self, 'is_mouse_hovered', False):
                self.clear_timer.start(duration_sec * 1000)
            else:
                self.clear_timer.stop()

        if self._controls_in_use():
            self.idle_timer.stop()
        else:
            self.idle_timer.start(3500)
        self.update()

    def fade_or_clear_subtitles(self):
        self._is_waiting = True
        self._subtitle_box_cache = None
        self.current_original = ""
        self.current_translated = ""
        self.label_original.setText("")
        self._set_label_html(self.label_translated, "...", self.config.get("text_color", "#FFFFFF"))
        self.update()

    def _on_pause_clicked(self):
        if self.ext_toggle_pause:
            is_paused = self.ext_toggle_pause()
            self.set_paused_state(is_paused)

    def set_paused_state(self, is_paused: bool):
        self.is_paused = bool(is_paused)
        if is_paused:
            self.btn_pause.setText("▶")
            self.btn_pause.setStyleSheet("QPushButton { background-color: rgba(180, 40, 40, 0.85); color: #FFF; font-weight: bold; border: 1.5px solid #FF5252; border-radius: 4px; padding: 0px 2px; font-size: 11px; }")
            self.btn_pause.setToolTip(tr("overlay_pause_on"))
            self.display_status(tr("ocr_status_paused"))
        else:
            self.btn_pause.setText("⏸")
            self.btn_pause.setStyleSheet("QPushButton { background-color: rgba(30, 40, 55, 0.75); color: #EEE; font-weight: bold; border-radius: 4px; padding: 0px 2px; font-size: 11px; }")
            self.btn_pause.setToolTip(tr("overlay_pause_off"))
            self.display_status(tr("overlay_waiting"))

    def _open_settings(self):
        if hasattr(self, 'ext_open_settings') and self.ext_open_settings:
            self.ext_open_settings()

    def _on_roi_clicked(self):
        if self.ext_trigger_roi:
            self.ext_trigger_roi()

    def _on_snap_clicked(self):
        if self.ext_trigger_instant:
            self.ext_trigger_instant()

    def _on_inplace_clicked(self):
        if hasattr(self, 'ext_trigger_inplace') and self.ext_trigger_inplace:
            self.ext_trigger_inplace()

    def update_inplace_hotkey_tooltip(self, hotkey_str: str):
        if hasattr(self, 'btn_inplace'):
            self.btn_inplace.setToolTip(tr("overlay_tip_inplace", key=hotkey_str))

    def _decrease_font(self):
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        roi_configs = self.config.get("roi_configs", {})
        cur = max(14, self._get_font_size() - 2)
        self.config["screen_font_size"] = cur
        self.config["font_size"] = cur
        if isinstance(roi_configs, dict):
            roi_configs.setdefault(idx_key, {})["font_size"] = cur
        self._notify_config_change()
        self._apply_config(apply_geometry=False)
        self._apply_two_line_overlay_height(follow_font=True)
        self._subtitle_box_cache = None
        self._refresh_current_subtitle()
        self.update()
        if hasattr(self, 'label_translated'):
            self.label_translated.update()
        if hasattr(self, 'label_original'):
            self.label_original.update()
        if hasattr(self, 'ext_sync_font') and self.ext_sync_font:
            self.ext_sync_font(cur)

    def _increase_font(self):
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        roi_configs = self.config.get("roi_configs", {})
        cur = min(40, self._get_font_size() + 2)
        self.config["screen_font_size"] = cur
        self.config["font_size"] = cur
        if isinstance(roi_configs, dict):
            roi_configs.setdefault(idx_key, {})["font_size"] = cur
        self._notify_config_change()
        self._apply_config(apply_geometry=False)
        self._apply_two_line_overlay_height(follow_font=True)
        self._subtitle_box_cache = None
        self._refresh_current_subtitle()
        self.update()
        if hasattr(self, 'label_translated'):
            self.label_translated.update()
        if hasattr(self, 'label_original'):
            self.label_original.update()
        if hasattr(self, 'ext_sync_font') and self.ext_sync_font:
            self.ext_sync_font(cur)

    def update_font_size(self, val: int):
        self.config["screen_font_size"] = int(val)
        self.config["font_size"] = int(val)
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        roi_configs = self.config.get("roi_configs", {})
        if isinstance(roi_configs, dict):
            roi_configs.setdefault(idx_key, {})["font_size"] = int(val)
        self._apply_config(apply_geometry=False)
        self._apply_two_line_overlay_height(follow_font=True)
        self._subtitle_box_cache = None
        self._refresh_current_subtitle()
        self.update()
        if hasattr(self, 'label_translated'):
            self.label_translated.update()
        if hasattr(self, 'label_original'):
            self.label_original.update()

    set_font_size = update_font_size

    def update_opacity(self, pct: float):
        norm = self._normalize_bg_opacity(pct)
        self.config["screen_overlay_bg_opacity"] = norm
        self.config["overlay_bg_opacity"] = norm
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        roi_configs = self.config.get("roi_configs", {})
        if isinstance(roi_configs, dict):
            roi_configs.setdefault(idx_key, {})["opacity"] = int(norm * 100)
        self._notify_config_change()
        self._apply_config(apply_geometry=False)
        self.update()

    set_bg_opacity = update_opacity

    def _decrease_opacity(self):
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        roi_configs = self.config.get("roi_configs", {})
        cur = round(max(0.0, self._get_bg_opacity() - 0.10), 2)
        self.config["screen_overlay_bg_opacity"] = cur
        self.config["overlay_bg_opacity"] = cur
        if isinstance(roi_configs, dict):
            roi_configs.setdefault(idx_key, {})["opacity"] = int(cur * 100)
        self._notify_config_change()
        self._apply_config(apply_geometry=False)
        self.update()
        pct = int(cur * 100)
        if hasattr(self, 'ext_sync_opacity') and self.ext_sync_opacity:
            self.ext_sync_opacity(pct)

    def _increase_opacity(self):
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        roi_configs = self.config.get("roi_configs", {})
        cur = round(min(1.0, self._get_bg_opacity() + 0.10), 2)
        self.config["screen_overlay_bg_opacity"] = cur
        self.config["overlay_bg_opacity"] = cur
        if isinstance(roi_configs, dict):
            roi_configs.setdefault(idx_key, {})["opacity"] = int(cur * 100)
        self._notify_config_change()
        self._apply_config(apply_geometry=False)
        self.update()
        pct = int(cur * 100)
        if hasattr(self, 'ext_sync_opacity') and self.ext_sync_opacity:
            self.ext_sync_opacity(pct)

    def toggle_click_through(self):
        self.set_click_through(not self.is_click_through)

    def set_click_through(self, enabled: bool):
        self.is_click_through = enabled
        self.config["screen_click_through"] = enabled
        self.config["click_through"] = enabled
        self._notify_config_change()

        # Qt 레벨 관통은 사용하지 않음 — nativeEvent(WM_NCHITTEST)로 영역별 관통 제어
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        if enabled:
            self.is_mouse_hovered = False
            self.idle_timer.start(3500)
            self.title_label.setText(tr("overlay_click_through_active"))
            self.title_label.setStyleSheet("QLabel { color: rgba(100, 255, 100, 0.9); font-size: 11px; font-weight: bold; }")
            self.btn_lock.setText("🔓")
            self.btn_lock.setFixedWidth(32)
            self.btn_lock.setStyleSheet("QPushButton { background-color: rgba(30, 140, 50, 0.9); color: #FFF; border: 1.5px solid #69F0AE; border-radius: 4px; padding: 0px 2px; font-size: 11px; font-weight: bold; }")
            self.size_grip.hide()
            self._set_header_chrome_opacity(0.35)
        else:
            idx = getattr(self, "assigned_roi_idx", 0)
            is_multi = getattr(self, "is_multi", False)
            title = f"👁️ {tr('screen_translation')} #{idx + 1}" if is_multi else f"👁️ {tr('screen_translation')}"
            self.title_label.setText(title)
            self.title_label.setStyleSheet("QLabel { color: rgba(255, 255, 255, 0.5); font-size: 11px; font-weight: bold; }")
            self.btn_lock.setText("🔒")
            self.btn_lock.setFixedWidth(32)
            self.btn_lock.setStyleSheet("QPushButton { background-color: rgba(30, 40, 55, 0.75); color: #EEE; border-radius: 4px; padding: 0px 2px; font-size: 11px; font-weight: bold; }")
            self.size_grip.show()
            self._set_header_chrome_opacity(0.4)

        # 컨트롤 패널 토글 UI 동기화 콜백
        if hasattr(self, 'ext_sync_click_through') and self.ext_sync_click_through:
            self.ext_sync_click_through(enabled)

    def _is_pos_in_header(self, local_pos: QPoint) -> bool:
        """로컬 좌표가 헤더(컨트롤) 영역 안에 있는지 판별"""
        if not hasattr(self, 'header_widget') or self.header_widget is None:
            return False
        hg = self.header_widget.geometry()
        # 헤더 영역에 상하 여유 8px 추가 (호버 감도 향상)
        expanded = QRect(hg.x(), max(0, hg.y() - 8), hg.width(), hg.height() + 16)
        if expanded.contains(local_pos):
            return True
        if hasattr(self, 'btn_lock') and self.btn_lock is not None and self.btn_lock.isVisible():
            btn_geo = self.btn_lock.geometry()
            btn_parent = self.btn_lock.parentWidget()
            if btn_parent and btn_parent is not self:
                top_left = btn_parent.mapTo(self, btn_geo.topLeft())
                btn_overlay_rect = QRect(top_left, btn_geo.size())
            else:
                btn_overlay_rect = btn_geo
            if btn_overlay_rect.adjusted(-6, -6, 6, 6).contains(local_pos):
                return True
        return False

    def nativeEvent(self, eventType, message):
        """Windows WM_NCHITTEST: 마우스 관통 모드일 때 헤더 영역 외부는 HTTRANSPARENT(관통), 헤더는 HTCLIENT(클릭 수신)"""
        if self.is_click_through and eventType == b"windows_generic_MSG":
            try:
                msg_ptr = int(message)
                # Windows x64 MSG: HWND(8) + UINT(4) + padding(4) + WPARAM(8) + LPARAM(8)
                msg_bytes = ctypes.string_at(msg_ptr, 36)
                msg_id = struct.unpack_from("I", msg_bytes, 8)[0]

                WM_NCHITTEST = 0x0084
                HTTRANSPARENT = -1
                HTCLIENT = 1

                if msg_id == WM_NCHITTEST:
                    lparam = struct.unpack_from("q", msg_bytes, 24)[0]  # LPARAM at offset 24
                    screen_x = ctypes.c_short(lparam & 0xFFFF).value
                    screen_y = ctypes.c_short((lparam >> 16) & 0xFFFF).value

                    # 1. QCursor.pos()는 Qt가 시스템 DPI를 감안하여 이미 논리 좌표로 변환해 둔 전역 좌표
                    local_pos = self.mapFromGlobal(QCursor.pos())

                    # 2. lparam 물리 좌표의 DPI 역스케일링 검사 (테스트 환경 또는 가상 이벤트 호환성 확보)
                    if not self._is_pos_in_header(local_pos):
                        dpr = self.devicePixelRatio()
                        if dpr and dpr > 0:
                            alt_pos = self.mapFromGlobal(QPoint(int(round(screen_x / dpr)), int(round(screen_y / dpr))))
                            if self._is_pos_in_header(alt_pos):
                                local_pos = alt_pos
                        raw_pos = self.mapFromGlobal(QPoint(screen_x, screen_y))
                        if self._is_pos_in_header(raw_pos):
                            local_pos = raw_pos

                    if self._is_pos_in_header(local_pos):
                        # 헤더 영역: 버튼 호버 및 클릭을 위해 즉시 헤더 불투명도 100% 복원 및 HTCLIENT 반환
                        if self.is_idle or (hasattr(self, 'header_opacity_effect') and self.header_opacity_effect.opacity() < 0.95):
                            self.is_idle = False
                            self._set_header_chrome_opacity(1.0)
                            self.idle_timer.start(3500)
                            self.update()
                        return True, HTCLIENT
                    else:
                        return True, HTTRANSPARENT
            except Exception:
                pass
        ret = super().nativeEvent(eventType, message)
        if isinstance(ret, tuple) and len(ret) == 2 and ret[1] is not None:
            return ret
        return False, 0

    def toggle_clean_mode(self):
        self.set_clean_mode(not self.clean_text_mode)

    def set_clean_mode(self, enabled: bool):
        self.clean_text_mode = enabled
        self.config["screen_clean_text_mode"] = enabled
        self._update_clean_button_style()
        if self.clean_text_mode:
            self._set_header_chrome_opacity(1.0 if self._controls_in_use() else 0.0)
            self.size_grip.hide()
        else:
            self._set_header_chrome_opacity(1.0 if self._controls_in_use() else 0.4)
            if not self.is_click_through:
                self.size_grip.show()
        if self.config.get("show_original", True):
            self.label_original.show()
        else:
            self.label_original.hide()
        self._notify_config_change()
        self.update()
        # 컨트롤 패널 토글 UI 동기화
        if hasattr(self, 'ext_sync_clean_text') and self.ext_sync_clean_text:
            self.ext_sync_clean_text(enabled)

    def _update_clean_button_style(self):
        self.btn_clean.setText("✨")
        self.btn_clean.setFixedWidth(32)
        if self.clean_text_mode:
            self.btn_clean.setStyleSheet("QPushButton { background-color: rgba(0, 150, 136, 0.85); color: #FFF; font-weight: bold; border: 1.5px solid #64FFDA; border-radius: 4px; padding: 0px; margin: 0px; text-align: center; font-size: 12px; }")
        else:
            self.btn_clean.setStyleSheet("QPushButton { background-color: rgba(30, 40, 55, 0.75); color: #EEE; font-weight: bold; border-radius: 4px; padding: 0px; margin: 0px; text-align: center; font-size: 12px; }")

    def toggle_pin(self):
        self.is_pinned = not getattr(self, 'is_pinned', False)
        self._update_pin_button_style()
        if self.is_pinned:
            self.clear_timer.stop()
        else:
            duration_sec = self.config.get("screen_subtitle_duration", 5)
            is_instant = "즉시" in (self.live_badge.text() or "").lower() or "instant" in (self.live_badge.text() or "").lower()
            if duration_sec > 0 and not is_instant and self.current_translated and not self.is_mouse_hovered:
                self.clear_timer.start(duration_sec * 1000)

    def _update_pin_button_style(self):
        self.btn_pin.setText("📌")
        self.btn_pin.setFixedWidth(32)
        if getattr(self, 'is_pinned', False):
            self.btn_pin.setStyleSheet("""
                QPushButton {
                    background-color: rgba(230, 140, 20, 0.90);
                    color: #FFF;
                    border: 1.5px solid #FFA726;
                    border-radius: 4px;
                    padding: 0px;
                    margin: 0px;
                    text-align: center;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)
            self.btn_pin.setToolTip(tr("overlay_tip_pin_pinned"))
        else:
            self.btn_pin.setStyleSheet("""
                QPushButton {
                    background-color: rgba(30, 40, 55, 0.75);
                    color: #EEE;
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 4px;
                    padding: 0px;
                    margin: 0px;
                    text-align: center;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(50, 75, 110, 0.95);
                    color: #FFF;
                    border: 1px solid rgba(0, 200, 255, 0.5);
                }
            """)
            self.btn_pin.setToolTip(tr("overlay_tip_pin_unpinned"))

    def _on_idle_timeout(self):
        if self._controls_in_use():
            self.is_idle = False
            self.idle_timer.stop()
            self._set_header_chrome_opacity(1.0)
            if not self.is_click_through:
                self.size_grip.show()
            return
        self.is_idle = True
        if self.is_click_through:
            # 관통 모드에서는 해제 버튼 위치를 인지할 수 있도록 은은하게(0.25) 유지
            self._set_header_chrome_opacity(0.25)
        else:
            self._set_header_chrome_opacity(0.0)
        self.size_grip.hide()
        # 주의: 자막 원문(label_original)을 idle 상태라고 해서 임의로 숨기면(hide)
        # 자막 텍스트와 배경 박스의 수직 위치가 불일치해지고 상하 박스가 비어 보이는 심각한 디싱크가 발생하므로 절대 hide하지 않는다.
        self._subtitle_box_cache = None
        self.update()

    def _cursor_over_window(self):
        return self.isVisible() and self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    def _controls_in_use(self):
        if self.is_click_through:
            return self._is_pos_in_header(self.mapFromGlobal(QCursor.pos()))
        return (
            self.is_mouse_hovered or self.is_moving or
            self.active_resize_edge != EDGE_NONE or self._cursor_over_window()
        )

    def enterEvent(self, event):
        super().enterEvent(event)
        self.is_idle = False
        self.is_mouse_hovered = True
        # 마우스 오버 시 자막 소거 타이머 일시정지 (읽는 동안 자막 소거 원천 방지)
        if hasattr(self, 'clear_timer'):
            self.clear_timer.stop()
        if self.is_click_through:
            # 관통 모드: 헤더 영역 호버 시 컨트롤 표시 (nativeEvent가 히트테스트 관리)
            self._set_header_chrome_opacity(1.0)
        else:
            self._set_header_chrome_opacity(1.0)
            self.size_grip.show()
            if self.config.get("show_original", True):
                self.label_original.show()
        if self.is_click_through:
            self.idle_timer.start(3500)
        else:
            self.idle_timer.stop()
        self._subtitle_box_cache = None
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if not self.is_click_through and (self._cursor_over_window() or self.is_moving or self.active_resize_edge != EDGE_NONE):
            # 자식 버튼으로 커서가 이동한 경우에도 상위 창의 leave 이벤트가 올 수 있다.
            self.is_mouse_hovered = True
            self.idle_timer.stop()
            return
        self.is_mouse_hovered = False
        if not self.active_resize_edge:
            self.unsetCursor()
        if self.is_click_through:
            self._set_header_chrome_opacity(0.25)
        elif not self.clean_text_mode:
            self._set_header_chrome_opacity(0.4)
        else:
            self._set_header_chrome_opacity(0.0)
        if self._controls_in_use():
            self.idle_timer.stop()
        else:
            self.idle_timer.start(3500)
        # 마우스가 나갔을 때 고정/영구유지/즉시번역이 아니면 설정된 유지 시간 카운트다운 재개
        if not getattr(self, 'is_pinned', False):
            duration_sec = self.config.get("screen_subtitle_duration", 5)
            is_instant = "즉시" in (self.live_badge.text() or "").lower() or "instant" in (self.live_badge.text() or "").lower()
            if duration_sec > 0 and not is_instant and self.current_translated:
                self.clear_timer.start(duration_sec * 1000)
        self._subtitle_box_cache = None
        self.update()

    def _get_resize_edges(self, pos: QPoint) -> int:
        """마우스 좌표가 창의 어느 테두리/모서리에 위치하는지 판별"""
        if self._interactive_chrome_at(pos):
            return EDGE_NONE
        edges = EDGE_NONE
        w = self.width()
        h = self.height()
        x = pos.x()
        y = pos.y()

        # 4개 코너(모서리) 우선 판별 (더 넓은 히트박스 제공)
        if x < CORNER_MARGIN and y < CORNER_MARGIN:
            return EDGE_LEFT | EDGE_TOP
        if x > w - CORNER_MARGIN and y < CORNER_MARGIN:
            return EDGE_RIGHT | EDGE_TOP
        if x < CORNER_MARGIN and y > h - CORNER_MARGIN:
            return EDGE_LEFT | EDGE_BOTTOM
        if x > w - CORNER_MARGIN and y > h - CORNER_MARGIN:
            return EDGE_RIGHT | EDGE_BOTTOM

        # 4개 테두리 판별
        if x < EDGE_MARGIN:
            edges |= EDGE_LEFT
        elif x > w - EDGE_MARGIN:
            edges |= EDGE_RIGHT

        if y < EDGE_MARGIN:
            edges |= EDGE_TOP
        elif y > h - EDGE_MARGIN:
            edges |= EDGE_BOTTOM

        return edges

    def _update_cursor_for_edges(self, edges: int):
        """판별된 가장자리에 맞추어 마우스 커서 모양 설정"""
        if edges in (EDGE_LEFT | EDGE_TOP, EDGE_RIGHT | EDGE_BOTTOM):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges in (EDGE_RIGHT | EDGE_TOP, EDGE_LEFT | EDGE_BOTTOM):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edges & (EDGE_LEFT | EDGE_RIGHT):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edges & (EDGE_TOP | EDGE_BOTTOM):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()

    # 8방향 리사이즈 및 안전한 창 드래그 이동 처리
    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        if self.is_click_through:
            if self._is_pos_in_header(pos) or self._interactive_chrome_at(pos):
                super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self._interactive_chrome_at(pos):
                super().mousePressEvent(event)
                return
            edges = self._get_resize_edges(pos)
            if edges != EDGE_NONE:
                # 8방향 리사이즈 시작
                self.active_resize_edge = edges
                self.is_moving = False
                self._begin_user_resize()
                self.drag_start_global = event.globalPosition().toPoint()
                self.drag_start_geometry = self.geometry()
                event.accept()
                return

            # 가장자리가 아닌 경우 창 이동 드래그 시작 (커서 핫스팟 기준)
            self.active_resize_edge = EDGE_NONE
            self.is_moving = True
            self._begin_user_move()
            event.accept()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self.is_idle:
            self.is_idle = False
            self._set_header_chrome_opacity(1.0)
            if not self.is_click_through:
                self.size_grip.show()
            self._subtitle_box_cache = None
            self.update()
        if self._cursor_over_window():
            self.is_mouse_hovered = True
        if self._controls_in_use():
            self.idle_timer.stop()
        else:
            self.idle_timer.start(3500)

        if self.is_click_through:
            if self._is_pos_in_header(pos) or self._interactive_chrome_at(pos):
                self._set_header_chrome_opacity(1.0)
            return

        # 1. 마우스가 눌려있지 않은 상태: 호버 위치에 따른 리사이즈 커서 실시간 반영
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            edges = self._get_resize_edges(pos)
            self._update_cursor_for_edges(edges)
            return

        # 2. 리사이즈 진행 중
        if self.active_resize_edge != EDGE_NONE:
            diff = event.globalPosition().toPoint() - self.drag_start_global
            geo = QRect(self.drag_start_geometry)
            min_w = max(250, self.minimumWidth())
            min_h = max(45, self.minimumHeight())

            new_left = geo.left()
            new_right = geo.right()
            new_top = geo.top()
            new_bottom = geo.bottom()

            if self.active_resize_edge & EDGE_LEFT:
                new_left = min(geo.left() + diff.x(), geo.right() - min_w + 1)
            if self.active_resize_edge & EDGE_RIGHT:
                new_right = max(geo.right() + diff.x(), geo.left() + min_w - 1)
            if self.active_resize_edge & EDGE_TOP:
                new_top = min(geo.top() + diff.y(), geo.bottom() - min_h + 1)
            if self.active_resize_edge & EDGE_BOTTOM:
                new_bottom = max(geo.bottom() + diff.y(), geo.top() + min_h - 1)

            new_geo = QRect(QPoint(new_left, new_top), QPoint(new_right, new_bottom))
            self.setGeometry(new_geo)
            event.accept()
            return

        # 3. 창 이동 진행 중 (다중 모니터에서도 커서를 따라감)
        if self.is_moving:
            self._move_following_cursor()
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.is_click_through:
            pos = event.position().toPoint()
            if self._is_pos_in_header(pos) or self._interactive_chrome_at(pos):
                super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            was_resizing = (self.active_resize_edge != EDGE_NONE)
            was_moving = self.is_moving

            self.active_resize_edge = EDGE_NONE
            self.is_moving = False
            self._end_user_interaction()
            if not self._cursor_over_window():
                self.is_mouse_hovered = False
                self.idle_timer.start(3500)

            # 커서 상태 갱신
            self._update_cursor_for_edges(self._get_resize_edges(event.position().toPoint()))

            g = self.geometry()
            idx_key = str(getattr(self, 'assigned_roi_idx', 0))
            if "screen_overlay_geometries" not in self.config or not isinstance(self.config["screen_overlay_geometries"], dict):
                self.config["screen_overlay_geometries"] = {}

            if was_resizing:
                self.config["screen_overlay_geometries"][idx_key] = [g.x(), g.y(), g.width(), g.height()]
                if getattr(self, 'assigned_roi_idx', 0) == 0:
                    self.config["screen_overlay_geometry"] = [g.x(), g.y(), g.width(), g.height()]
                self.base_geometry = [g.x(), g.y(), g.width(), g.height()]
                self.is_user_positioned = True
                self.is_user_sized = True
                self._notify_config_change()
            elif was_moving:
                # 이동만 한 경우 크기는 사용자가 조절했던 크기 보존, 위치만 안전하게 갱신
                saved_w = self.base_geometry[2] if len(self.base_geometry) == 4 else g.width()
                saved_h = self.base_geometry[3] if len(self.base_geometry) == 4 else g.height()
                self.base_geometry = [g.x(), g.y(), saved_w, saved_h]
                self.config["screen_overlay_geometries"][idx_key] = list(self.base_geometry)
                if getattr(self, 'assigned_roi_idx', 0) == 0:
                    self.config["screen_overlay_geometry"] = list(self.base_geometry)
                self.is_user_positioned = True
                # 사용자가 마우스로 직접 드래그 이동한 경우 자동 밀착 모드 해제
                if self.config.get("screen_snap_to_roi", False):
                    self.config["screen_snap_to_roi"] = False
                    self._update_snap_button_style()
                    if hasattr(self, 'ext_sync_snap') and self.ext_sync_snap:
                        self.ext_sync_snap(False)
                self._notify_config_change()

            event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._subtitle_box_cache = None
        if self._reject_unwanted_resize():
            return

        g = self.geometry()
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        if "screen_overlay_geometries" not in self.config or not isinstance(self.config["screen_overlay_geometries"], dict):
            self.config["screen_overlay_geometries"] = {}
        self.config["screen_overlay_geometries"][idx_key] = [g.x(), g.y(), g.width(), g.height()]
        if getattr(self, 'assigned_roi_idx', 0) == 0:
            self.config["screen_overlay_geometry"] = [g.x(), g.y(), g.width(), g.height()]
        if not self.is_auto_resizing:
            self.base_geometry = [g.x(), g.y(), g.width(), g.height()]
            self.is_user_positioned = True
            self.is_user_sized = True
            self._notify_config_change()
            # 사용자가 창 크기를 수동 조절했을 때 현재 자막 텍스트 폰트 반응형 최적화
            if getattr(self, 'current_translated', None) and not self.is_auto_resizing:
                self._auto_fit_text(
                    self.format_original_text(getattr(self, 'current_original', '')),
                    self.format_korean_dialogue(self.current_translated),
                    adjust_window=False,
                )

    def reset_geometry(self):
        """기본 자막 위치 및 크기로 초기화"""
        default_geo = [200, 520, 850, 130]
        self.setGeometry(default_geo[0], default_geo[1], default_geo[2], default_geo[3])
        self.base_geometry = list(default_geo)
        self.is_user_positioned = False
        self.is_user_sized = False
        idx_key = str(getattr(self, 'assigned_roi_idx', 0))
        if "screen_overlay_geometries" in self.config and isinstance(self.config["screen_overlay_geometries"], dict):
            self.config["screen_overlay_geometries"].pop(idx_key, None)
        if getattr(self, 'assigned_roi_idx', 0) == 0:
            self.config["screen_overlay_geometry"] = list(default_geo)
        self._apply_two_line_overlay_height()
        self._notify_config_change()

    def _calc_label_text_boxes(self, label, pad_x=14, pad_y=4):
        """라벨(QLabel)에 렌더링된 텍스트의 각 시각적 라인별 정확한 밀착 사각형(QRect) 목록 계산 (수직 중앙 정렬 완벽 보정)"""
        if not label or label.isHidden():
            return []
        text = label.text().strip()
        if not text or text == "...":
            return []

        # 순수 텍스트 유무 검증
        plain = re.sub(r'<[^>]+>', '', text).strip()
        if not plain or plain == "...":
            return []

        crect = label.contentsRect()
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(label.font())
        avail_w = max(100, crect.width())
        doc.setTextWidth(avail_w)
        doc.setHtml(text)

        doc_h = doc.size().height()
        # QLabel은 contentsRect 내부의 수직 중앙에 텍스트 문서를 렌더링함
        doc_y = crect.y() + max(0.0, (crect.height() - doc_h) / 2.0)

        fm = QFontMetrics(label.font())
        cap_h = fm.capHeight()

        boxes = []
        b = doc.begin()
        while b.isValid():
            layout = b.layout()
            if layout:
                for i in range(layout.lineCount()):
                    line = layout.lineAt(i)
                    text_w = line.naturalTextWidth()
                    if text_w <= 0:
                        continue
                    # 실제 베이스라인(baseline) 및 글자들의 시각적 수직 중심(visual center) 계산
                    label_pos = label.mapTo(self, QPoint(0, 0))
                    baseline_y = label_pos.y() + doc_y + line.rect().y() + line.ascent()
                    text_center_y = baseline_y - (cap_h / 2.0)

                    box_w = min(self.width() - 8, text_w + pad_x * 2)
                    box_h = line.rect().height() + pad_y * 2
                    box_x = (self.width() - box_w) / 2.0
                    box_y = text_center_y - (box_h / 2.0)

                    boxes.append(QRect(int(round(box_x)), int(round(box_y)), int(round(box_w)), int(round(box_h))))
            b = b.next()
        return boxes

    def _calc_subtitle_box_rects(self):
        """자막 텍스트(영문/한글)의 실제 렌더링 라인별 밀착 반투명 라운드 박스 목록 계산 (완벽한 라인 분리 및 위치 동기화)"""
        show_orig = self._get_show_original()
        show_trans = self._get_show_translated()
        orig_visible = bool(show_orig and hasattr(self, 'label_original') and not self.label_original.isHidden())
        trans_visible = bool(show_trans and hasattr(self, 'label_translated') and not self.label_translated.isHidden())
        orig = self.label_original.text() if orig_visible else ""
        trans = self.label_translated.text() if trans_visible else ""

        plain_orig = re.sub(r'<[^>]+>', '', orig).strip()
        plain_trans = re.sub(r'<[^>]+>', '', trans).strip()
        if not plain_orig and not plain_trans:
            self._subtitle_box_cache = None
            return []
        if (not plain_orig or plain_orig == "...") and (not plain_trans or plain_trans == "..."):
            self._subtitle_box_cache = None
            return []

        orig_geo = self.label_original.geometry().getRect() if orig_visible else None
        trans_geo = self.label_translated.geometry().getRect() if trans_visible else None

        key = (
            self.width(),
            self.height(),
            orig,
            trans,
            orig_visible,
            trans_visible,
            orig_geo,
            trans_geo,
            self._get_font_size(),
            self._get_letter_spacing(),
        )
        cached = getattr(self, "_subtitle_box_cache", None)
        if cached and cached[0] == key:
            return cached[1]
        boxes = []
        if orig_visible and plain_orig and plain_orig != "...":
            boxes.extend(self._calc_label_text_boxes(self.label_original, pad_x=12, pad_y=3))
        if trans_visible and plain_trans and plain_trans != "...":
            boxes.extend(self._calc_label_text_boxes(self.label_translated, pad_x=14, pad_y=4))

        # 각 라인 박스 간 최소 간격(min_gap) 보장 및 겹침 방지 처리 (2줄 이상 시 테두리/박스 중첩 원천 차단)
        min_gap = 5
        for i in range(1, len(boxes)):
            prev = boxes[i - 1]
            curr = boxes[i]
            if curr.top() < prev.bottom() + min_gap:
                diff = (prev.bottom() + min_gap) - curr.top()
                shift_up = diff // 2
                shift_down = diff - shift_up
                boxes[i - 1] = QRect(prev.x(), prev.y() - shift_up, prev.width(), prev.height())
                boxes[i] = QRect(curr.x(), curr.y() + shift_down, curr.width(), curr.height())

        self._subtitle_box_cache = (key, boxes)
        return boxes

    def _calc_subtitle_box_rect(self):
        """하위 호환용 단일 박스 영역 반환"""
        rects = self._calc_subtitle_box_rects()
        return rects[-1] if rects else None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. 반투명 버퍼 완전 소거 (이전 자막 잔상 및 텍스트 찌꺼기 완벽 제거)
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.restore()

        opacity = self._get_bg_opacity()
        clean_box_enabled = self._get_clean_box()

        # 2. 클린 텍스트 모드이거나 배경 불투명도가 0%(완전 투명)인 경우
        if self.clean_text_mode or opacity <= 0.001:
            if self.underMouse() and not self.is_click_through:
                # 마우스 호버 시 조작을 돕기 위해 은은한 반투명 가이드 테두리만 점선으로 표시
                painter.setBrush(QBrush(QColor(10, 15, 24, 40)))
                painter.setPen(QPen(QColor(0, 190, 240, 100), 1.2, Qt.PenStyle.DashLine))
                rect = self.rect().adjusted(1, 1, -1, -1)
                painter.drawRoundedRect(rect, 8, 8)

            # 자막 뒤 은은한 반투명 박스 (자막 텍스트 영역에 꼭 맞춘 넷플릭스 스타일 다크 라운드 박스)
            if clean_box_enabled:
                boxes = self._calc_subtitle_box_rects()
                if boxes:
                    box_alpha = 185 if opacity <= 0.001 else max(150, int(opacity * 255))
                    path = QPainterPath()
                    path.setFillRule(Qt.FillRule.WindingFill)
                    for b_rect in boxes:
                        path.addRoundedRect(QRectF(b_rect), 6, 6)
                    painter.fillPath(path, QBrush(QColor(8, 12, 20, box_alpha)))
                    painter.setPen(Qt.PenStyle.NoPen)
            return

        # 3. 일반 창 모드: 배경 불투명도 > 0% (설정된 opacity에 따른 둥근 창 배경)
        alpha = int(opacity * 255)
        bg_color = QColor(10, 15, 24, alpha)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.drawRoundedRect(rect, 10, 10)

        # 일반 창 모드에서도 자막 뒤 반투명 박스가 켜져 있을 때 자막 대비감 강화 (아웃라인 테두리 없이 깔끔한 다크 바)
        if clean_box_enabled:
            boxes = self._calc_subtitle_box_rects()
            if boxes:
                box_alpha = min(245, alpha + 60)
                path = QPainterPath()
                path.setFillRule(Qt.FillRule.WindingFill)
                for b_rect in boxes:
                    path.addRoundedRect(QRectF(b_rect), 6, 6)
                painter.fillPath(path, QBrush(QColor(6, 8, 14, box_alpha)))
                painter.setPen(Qt.PenStyle.NoPen)
