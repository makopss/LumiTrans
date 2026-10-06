import time
import re
import ctypes
import struct
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QRect, QByteArray, QRectF
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QSizeGrip, QComboBox,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect
)
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QFontMetrics, QCursor, QTextDocument, QPainterPath
from src.outline_effect import ThickOutlineEffect
from src.no_wheel_combobox import NoWheelComboBox
from src.overlay_geometry import OverlayGeometryMixin
from src.subtitle_manager import break_subtitle_text, smart_break_sentences
from src.i18n import tr

# 8방향 테두리 리사이즈 플래그 및 마진 상수
EDGE_NONE = 0
EDGE_LEFT = 1
EDGE_RIGHT = 2
EDGE_TOP = 4
EDGE_BOTTOM = 8

EDGE_MARGIN = 8       # 테두리 리사이즈 감지 두께 (px)
CORNER_MARGIN = 16    # 모서리 코너 감지 크기 (px)

class SubtitleOverlay(OverlayGeometryMixin, QWidget):
    update_subtitle_signal = pyqtSignal(str, str, str)
    update_preview_signal = pyqtSignal(str, str)

    def __init__(self, config, on_config_change=None):
        super().__init__()
        self.config = config
        self.on_config_change = on_config_change
        
        self.drag_position = QPoint()
        self.is_click_through = False
        self.current_original = ""
        self.current_translated = ""
        self._audio_paused = False
        self.last_translated_time = 0.0
        self.is_previewing_new_sentence = False
        self.base_geometry = list(self.config.get("window_geometry", [200, 750, 900, 140]))
        self.is_auto_resizing = False
        self.clean_text_mode = self.config.get("screen_clean_text_mode", False)
        self.show_speaker = self.config.get("show_speaker", True)
        self.speaker_diarization_enabled = self.config.get("speaker_diarization_enabled", False)
        self.is_user_sized = False
        self.is_user_positioned = False
        
        # 8방향 테두리 리사이즈 및 드래그 이동 상태 변수
        self.active_resize_edge = EDGE_NONE
        self.is_moving = False
        self.drag_start_global = QPoint()
        self.drag_start_geometry = QRect()
        self.drag_start_pos = QPoint()
        self._init_geometry_lock()
        
        self._init_ui()
        self._apply_config()
        
        # 새 자막 및 실시간 타이핑 프리뷰 시그널 연결 (스레드 안전)
        self.update_subtitle_signal.connect(self.display_subtitle)
        self.update_preview_signal.connect(self.display_preview)

        # 일정 시간 발화 없으면 자막 정리 타이머
        self.clear_timer = QTimer(self)
        self.clear_timer.setSingleShot(True)
        self.clear_timer.timeout.connect(self.fade_or_clear_subtitles)

        # 유휴 3.5초 감지 타이머 (버튼 컨트롤을 자동으로 숨기고 자막 텍스트만 표시)
        self.is_idle = False
        self.is_mouse_hovered = False
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(3500)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self._on_idle_timeout)

        self.setMouseTracking(True)

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_capture_exclusion()
        if hasattr(self, 'idle_timer'):
            self.idle_timer.start(3500)
        if hasattr(self, 'ext_visibility_change') and self.ext_visibility_change:
            self.ext_visibility_change(True)
        self._bind_screen_changed()

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, 'ext_visibility_change') and self.ext_visibility_change:
            self.ext_visibility_change(False)

    def _apply_capture_exclusion(self):
        try:
            import ctypes
            hwnd = int(self.winId())
            if hwnd:
                WDA_EXCLUDEFROMCAPTURE = 0x00000011
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        except Exception:
            pass

    def _init_ui(self):
        # 윈도우 기본 속성: 무테두리, 항상 위, 반투명 배경
        self.setWindowTitle(tr("overlay_audio_title"))
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        # 메인 레이아웃
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 8, 14, 8)
        self.main_layout.setSpacing(4)

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

        # 헤더 바 (드래그 핸들 및 빠른 컨트롤 캡슐)
        self.header_widget = QWidget()
        self.header_widget.setFixedHeight(32)
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(4, 3, 4, 3)
        self.header_layout.setSpacing(5)

        self.title_label = QLabel("🎤 " + tr("voice_translation"))
        self.title_label.setFixedHeight(26)
        self.title_label.setToolTip(tr("overlay_voice_tip"))
        self.title_label.setStyleSheet("QLabel { color: rgba(255, 255, 255, 0.55); font-size: 11px; font-weight: bold; }")
        self.header_layout.addWidget(self.title_label)

        # 1. 일시정지 / 재생 토글 버튼
        init_paused = not self.config.get("auto_start_audio", False)
        self.btn_pause = QPushButton("▶" if init_paused else "⏸")
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.setFixedHeight(26)
        self.btn_pause.setFixedWidth(34)
        if init_paused:
            self.btn_pause.setStyleSheet("QPushButton { background-color: rgba(180, 40, 40, 0.85); color: #FFF; font-weight: bold; border-radius: 4px; padding: 0px 2px; font-size: 11px; }")
            self.btn_pause.setToolTip(tr("overlay_pause_voice_on"))
        else:
            self.btn_pause.setStyleSheet("QPushButton { background-color: rgba(45, 48, 62, 0.75); color: #EEE; font-weight: bold; border-radius: 4px; padding: 0px 2px; font-size: 11px; }")
            self.btn_pause.setToolTip(tr("overlay_pause_toggle"))
        self.btn_pause.clicked.connect(self._on_pause_clicked)
        self.header_layout.addWidget(self.btn_pause)

        # 2. 번역기 선택 드롭다운 (휠 스크롤 옵션 변경 원천 방지)
        self.combo_engine = NoWheelComboBox()
        self.combo_engine.setToolTip(tr("overlay_tip_engine_combo"))
        self.combo_engine.setFixedHeight(26)
        self.combo_engine.setFixedWidth(102)
        self.combo_engine.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_engine.addItems([
            "DeepL", "Google", "Gemini", "Groq",
            "EXAONE", "Gemma", "Hy-MT2"
        ])
        cur_engine = self.config.get("translation_engine", "google").lower()
        if "hymt" in cur_engine or "hy-mt" in cur_engine:
            cur_key = "hymt"
        elif "exaone" in cur_engine:
            cur_key = "exaone"
        elif "gemma" in cur_engine:
            cur_key = "gemma"
        elif "deepl" in cur_engine:
            cur_key = "deepl"
        elif "gemini" in cur_engine:
            cur_key = "gemini"
        elif "groq" in cur_engine:
            cur_key = "groq"
        else:
            cur_key = "google"
        idx_map = {
            "deepl": 0, "google": 1, "gemini": 2, "groq": 3,
            "exaone": 4, "gemma": 5, "hymt": 6
        }
        self.combo_engine.setCurrentIndex(idx_map.get(cur_key, 1))
        self.combo_engine.currentIndexChanged.connect(self._on_combo_engine_changed)
        self.header_layout.addWidget(self.combo_engine)

        # 3. 실시간 동작 상태 뱃지 (선택 기능과 분리된 독립 인디케이터, 고정폭 Jitter 0%!)
        self.live_badge = QLabel(tr("overlay_waiting"))
        self.live_badge.setFixedHeight(26)
        self.live_badge.setFixedWidth(150)
        self.live_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.live_badge.setToolTip(tr("overlay_tip_live_badge"))
        self.live_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.live_badge.mousePressEvent = lambda e: self.toggle_live_badge_dimmed()
        self.live_badge.setStyleSheet("""
            QLabel {
                background-color: rgba(30, 32, 44, 0.85);
                color: rgba(255, 255, 255, 0.65);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 4px;
                font-size: 9.5px;
                font-weight: bold;
                padding: 0px 4px;
            }
            QLabel:hover {
                background-color: rgba(45, 50, 70, 0.95);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.3);
            }
        """)
        if not self.config.get("show_engine_badge", True):
            self.live_badge.hide()
        self.header_layout.addWidget(self.live_badge)

        # 4. 폰트 크기 미니 조절 버튼 (A- / A+)
        self.btn_font_dec = QPushButton("A-")
        self.btn_font_dec.setToolTip(tr("overlay_tip_font_dec", size=self.config.get("font_size", 22)))
        self.btn_font_dec.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_font_dec.setFixedHeight(26)
        self.btn_font_dec.setFixedWidth(36)
        self.btn_font_dec.clicked.connect(self._decrease_font)
        self.header_layout.addWidget(self.btn_font_dec)

        self.btn_font_inc = QPushButton("A+")
        self.btn_font_inc.setToolTip(tr("overlay_tip_font_inc", size=self.config.get("font_size", 22)))
        self.btn_font_inc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_font_inc.setFixedHeight(26)
        self.btn_font_inc.setFixedWidth(36)
        self.btn_font_inc.clicked.connect(self._increase_font)
        self.header_layout.addWidget(self.btn_font_inc)

        # 5. 배경 불투명도 미니 조절 버튼 (◐- / ◐+)
        cur_op_pct = int(self._normalize_bg_opacity(self.config.get("overlay_bg_opacity", 0.75)) * 100)
        self.btn_op_dec = QPushButton("◐-")
        self.btn_op_dec.setToolTip(tr("overlay_tip_op_dec", pct=cur_op_pct))
        self.btn_op_dec.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_op_dec.setFixedHeight(26)
        self.btn_op_dec.setFixedWidth(38)
        self.btn_op_dec.clicked.connect(self._decrease_opacity)
        self.header_layout.addWidget(self.btn_op_dec)

        self.btn_op_inc = QPushButton("◐+")
        self.btn_op_inc.setToolTip(tr("overlay_tip_op_inc", pct=cur_op_pct))
        self.btn_op_inc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_op_inc.setFixedHeight(26)
        self.btn_op_inc.setFixedWidth(38)
        self.btn_op_inc.clicked.connect(self._increase_opacity)
        self.header_layout.addWidget(self.btn_op_inc)

        # 5-1. 원문/번역문 표시 토글 버튼 (아이콘: 🔤 / 🌐)
        self.btn_toggle_en = QPushButton("🔤")
        self.btn_toggle_en.setToolTip(tr("overlay_tip_orig_on"))
        self.btn_toggle_en.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_en.setFixedHeight(26)
        self.btn_toggle_en.setFixedWidth(34)
        self.btn_toggle_en.clicked.connect(self._toggle_show_original)
        self.header_layout.addWidget(self.btn_toggle_en)

        self.btn_toggle_ko = QPushButton("🌐")
        self.btn_toggle_ko.setToolTip(tr("overlay_tip_trans_on"))
        self.btn_toggle_ko.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_ko.setFixedHeight(26)
        self.btn_toggle_ko.setFixedWidth(34)
        self.btn_toggle_ko.clicked.connect(self._toggle_show_translated)
        self.header_layout.addWidget(self.btn_toggle_ko)

        self._show_translated = True
        self._update_en_ko_button_styles()

        # 5-2. 클린 텍스트 모드 토글 버튼
        self.btn_clean = QPushButton("✨" if not self.clean_text_mode else "✨ON")
        self.btn_clean.setToolTip(tr("overlay_tip_clean"))
        self.btn_clean.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clean.setFixedHeight(26)
        self.btn_clean.setFixedWidth(54 if self.clean_text_mode else 34)
        self.btn_clean.clicked.connect(self.toggle_clean_mode)
        self.header_layout.addWidget(self.btn_clean)
        self._update_clean_button_style()

        # 5-3. 화자 이름 표시 토글 버튼
        self.btn_speaker = QPushButton("🗣️" if not self.show_speaker else "🗣️ON")
        self.btn_speaker.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        self.btn_speaker.setToolTip(tr("overlay_tip_speaker_on") if self.show_speaker else tr("overlay_tip_speaker_off"))
        self.btn_speaker.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_speaker.setFixedHeight(26)
        self.btn_speaker.setFixedWidth(54 if self.show_speaker else 34)
        self.btn_speaker.clicked.connect(self.toggle_show_speaker)
        self.header_layout.addWidget(self.btn_speaker)
        self._update_speaker_button_style()

        self.header_layout.addStretch()

        # 5. 설정창 열기 버튼
        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setToolTip(tr("overlay_tip_settings_detail"))
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setFixedHeight(26)
        self.btn_settings.setFixedWidth(34)
        self.btn_settings.clicked.connect(self._open_settings)
        self.header_layout.addWidget(self.btn_settings)

        # 6. 마우스 클릭 관통 버튼
        self.btn_lock = QPushButton("🔒")
        self.btn_lock.setToolTip(tr("overlay_tip_lock_voice"))
        self.btn_lock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lock.setFixedHeight(26)
        self.btn_lock.setFixedWidth(54 if self.is_click_through else 34)
        self.btn_lock.clicked.connect(self.toggle_click_through)
        self.header_layout.addWidget(self.btn_lock)

        # 7. 자막창 숨기기 (닫기) 버튼
        self.btn_hide = QPushButton("✕")
        self.btn_hide.setToolTip(tr("overlay_tip_hide_voice"))
        self.btn_hide.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_hide.setFixedHeight(26)
        self.btn_hide.setFixedWidth(32)
        self.btn_hide.clicked.connect(self.hide)
        self.header_layout.addWidget(self.btn_hide)

        # 헤더 공통 버튼 & 콤보박스 스타일시트
        btn_style = """
            QPushButton {
                background-color: rgba(45, 48, 62, 0.75);
                color: #EEE;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 4px;
                padding: 0px 2px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(75, 82, 110, 0.95);
                color: #FFF;
                border: 1px solid rgba(255, 255, 255, 0.4);
            }
            QComboBox {
                background-color: rgba(45, 48, 62, 0.75);
                color: #EEE;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 4px;
                padding: 0px 4px 0px 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QComboBox:hover {
                background-color: rgba(75, 82, 110, 0.95);
                color: #FFF;
                border: 1px solid rgba(255, 255, 255, 0.4);
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 14px;
                border-left: none;
            }
            QComboBox QAbstractItemView {
                background-color: #22242D;
                color: #FFF;
                selection-background-color: #3F51B5;
            }
        """
        for b in [self.btn_pause, self.btn_font_dec, self.btn_font_inc, self.btn_op_dec, self.btn_op_inc, self.btn_settings, self.btn_lock, self.btn_hide, self.combo_engine]:
            b.setStyleSheet(btn_style)

        # 초기 활성 상태 표시 동기화
        self.update_live_display()

        # 헤더 자동 페이드(호버 시 100%, 평소 40% 은은한 딤드)
        self.header_opacity_effect = QGraphicsOpacityEffect(self.header_widget)
        self.header_widget.setGraphicsEffect(self.header_opacity_effect)
        self._set_header_chrome_opacity(1.0)

        self.main_layout.addWidget(self.header_widget)

        # 자막 텍스트 라벨 (원문·번역 모두 가운데 정렬)
        self.label_original = QLabel("Listening for audio...")
        self.label_original.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_original.setWordWrap(True)
        self.label_original.setMinimumSize(0, 0)
        self.label_original.setTextFormat(Qt.TextFormat.RichText)
        self.label_original.setStyleSheet(self._label_sheet(14, italic=True))
        self._set_label_html(self.label_original, "Listening for audio...", "#AAAAAA")

        self.label_translated = QLabel(tr("overlay_voice_placeholder"))
        self.label_translated.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_translated.setWordWrap(True)
        self.label_translated.setMinimumSize(0, 0)
        self.label_translated.setTextFormat(Qt.TextFormat.RichText)
        self.label_translated.setStyleSheet(self._label_sheet(20, bold=True))
        self._set_label_html(self.label_translated, tr("overlay_voice_placeholder"), "#FFFFFF")

        # 텍스트 효과 (0=기본 순수 소프트 섀도우 시스템 부하 0%, 1~5=외곽선 스트로크)
        self._apply_text_effect()
        self.label_translated.setContentsMargins(8, 8, 8, 8)
        self.label_original.setContentsMargins(8, 6, 8, 6)

        self.main_layout.addWidget(self.label_original)
        self.main_layout.addWidget(self.label_translated)

        # 우측 하단 크기 조절 그립
        grip_layout = QHBoxLayout()
        grip_layout.addStretch()
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("width: 12px; height: 12px; margin: 0px;")
        grip_layout.addWidget(self.size_grip)
        self.main_layout.addLayout(grip_layout)

        # 기본 위치 및 크기 복원
        geom = self.base_geometry
        self.setGeometry(geom[0], geom[1], geom[2], geom[3])
        self.setMinimumSize(830, 120)
        if self.layout() is not None:
            from PyQt6.QtWidgets import QLayout
            self.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

    def _calc_label_text_boxes(self, label, pad_x=14, pad_y=4):
        """라벨(QLabel)에 렌더링된 텍스트의 각 시각적 라인별 정확한 밀착 사각형(QRect) 목록 계산 (수직 중앙 정렬 완벽 보정)"""
        if not label or not label.isVisible():
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
                    baseline_y = label.y() + doc_y + line.rect().y() + line.ascent()
                    text_center_y = baseline_y - (cap_h / 2.0)

                    box_w = min(self.width() - 8, text_w + pad_x * 2)
                    box_h = line.rect().height() + pad_y * 2
                    box_x = (self.width() - box_w) / 2.0
                    box_y = text_center_y - (box_h / 2.0)

                    boxes.append(QRect(int(round(box_x)), int(round(box_y)), int(round(box_w)), int(round(box_h))))
            b = b.next()
        return boxes

    def _calc_subtitle_box_rects(self):
        """자막 텍스트(영문/한글)의 실제 렌더링 라인별 밀착 반투명 라운드 박스 목록 계산"""
        show_orig = self.config.get("show_original", True)
        orig = self.label_original.text() if show_orig and hasattr(self, 'label_original') else ""
        trans = self.label_translated.text() if hasattr(self, 'label_translated') else ""
        key = (
            self.width(),
            orig,
            trans,
            int(self.config.get("font_size", 22)),
            float(self.config.get("letter_spacing", 0.0)),
            bool(show_orig),
        )
        cached = getattr(self, "_subtitle_box_cache", None)
        if cached and cached[0] == key:
            return cached[1]
        boxes = []
        if show_orig and hasattr(self, 'label_original'):
            boxes.extend(self._calc_label_text_boxes(self.label_original, pad_x=12, pad_y=3))
        if hasattr(self, 'label_translated'):
            boxes.extend(self._calc_label_text_boxes(self.label_translated, pad_x=14, pad_y=4))
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

        opacity = self._normalize_bg_opacity(self.config.get("overlay_bg_opacity", 0.75))
        clean_box_enabled = self.config.get("screen_clean_box", True)

        # 2. 클린 텍스트 모드이거나 배경 불투명도가 0%(완전 투명)인 경우
        if self.clean_text_mode or opacity <= 0.001:
            if self.underMouse() and not self.is_click_through:
                # 마우스 호버 시 조작을 돕기 위해 은은한 반투명 가이드 테두리만 점선으로 표시
                painter.setBrush(QBrush(QColor(10, 15, 24, 40)))
                painter.setPen(QPen(QColor(0, 190, 240, 100), 1.2, Qt.PenStyle.DashLine))
                rect = self.rect().adjusted(1, 1, -1, -1)
                painter.drawRoundedRect(rect, 8, 8)

            if clean_box_enabled:
                boxes = self._calc_subtitle_box_rects()
                if boxes:
                    box_alpha = 160 if opacity <= 0.001 else max(150, int(opacity * 255))
                    path = QPainterPath()
                    path.setFillRule(Qt.FillRule.WindingFill)
                    for b_rect in boxes:
                        path.addRoundedRect(QRectF(b_rect), 6, 6)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.fillPath(path, QBrush(QColor(10, 15, 24, box_alpha)))
            return

        # 3. 일반 창 모드: 배경 불투명도 > 0%
        alpha = int(opacity * 255)
        bg_color = QColor(18, 20, 26, alpha)

        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.drawRoundedRect(rect, 12, 12)

        if clean_box_enabled:
            boxes = self._calc_subtitle_box_rects()
            if boxes:
                # 창 프레임 배경 위에서도 자막 대비감을 위해 더 짙은 반투명 박스 렌더링
                box_alpha = min(220, alpha + 45)
                path = QPainterPath()
                path.setFillRule(Qt.FillRule.WindingFill)
                for b_rect in boxes:
                    path.addRoundedRect(QRectF(b_rect), 6, 6)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.fillPath(path, QBrush(QColor(10, 15, 24, box_alpha)))

    def _label_sheet(self, size, *, bold=False, italic=False):
        extra = "font-weight: bold;" if bold else ""
        extra += "font-style: italic;" if italic else ""
        return f"QLabel {{ font-size: {size}px; background: transparent; {extra} }}"

    def _html_body(self, html, color, center=False):
        if html is None or html == "":
            return html
        if center:
            return f"<div style='color:{color};text-align:center'>{html}</div>"
        return f"<span style='color:{color}'>{html}</span>"

    def _set_label_html(self, label, html, color):
        label.setText(self._html_body(html, color, center=True))

    def _original_color(self):
        return self.config.get("original_color", "#B0B0B0")

    def _translated_color(self):
        return self.config.get("text_color", "#FFFFFF")

    def _auto_fit_text(self, original_text: str, translated_text: str, adjust_window: bool = True):
        """설정한 글자 크기를 유지한다. 창 크기에 따라 축소하지 않는다."""
        font_size = int(self.config.get("font_size", 22))
        show_orig = self.config.get("show_original", True) and bool((original_text or "").strip())
        letter_spacing = float(self.config.get("letter_spacing", 2.0))
        self._apply_fixed_fonts(font_size, letter_spacing, show_orig, adjust_window=adjust_window)

    def _apply_fixed_fonts(self, font_size: int, letter_spacing: float, show_orig: bool, adjust_window: bool = True):
        en_sz = max(11, font_size - 5)
        self.label_original.setVisible(show_orig)
        orig_color = self._original_color()
        orig_key = (en_sz, orig_color, letter_spacing)
        if getattr(self, "_last_orig_style_key", None) != orig_key:
            self._last_orig_style_key = orig_key
            orig_font = QFont("Segoe UI", en_sz)
            orig_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(0.5, letter_spacing * 0.6))
            self.label_original.setFont(orig_font)
            self.label_original.setStyleSheet(self._label_sheet(en_sz))

        ko_color = self._translated_color()
        trans_key = (font_size, ko_color, letter_spacing)
        if getattr(self, "_last_trans_style_key", None) != trans_key:
            self._last_trans_style_key = trans_key
            ko_font = QFont("Malgun Gothic", font_size, QFont.Weight.Bold)
            ko_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
            self.label_translated.setFont(ko_font)
            self.label_translated.setStyleSheet(self._label_sheet(font_size, bold=True))
        if adjust_window:
            self._apply_two_line_overlay_height()

    def _apply_text_effect(self):
        """텍스트 효과 적용 (0px: 순수 네이티브 소프트 섀도우, 1px+: 고대비 외곽선)"""
        stroke_w = self.config.get("subtitle_stroke_width", 0)
        if stroke_w == 0:
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
            eff = ThickOutlineEffect(thickness=stroke_w, color=QColor(0, 0, 0, 240), parent=self.label_translated)
            self.label_translated.setGraphicsEffect(eff)
            orig_eff = ThickOutlineEffect(thickness=max(1, stroke_w - 1), color=QColor(0, 0, 0, 240), parent=self.label_original)
            self.label_original.setGraphicsEffect(orig_eff)
            self.stroke_effect = eff
            self.orig_stroke_effect = orig_eff

    def set_stroke_width(self, val: int):
        """외곽선 굵기 또는 섀도우 모드 동적 변경 (0=순수 섀도우, 1~5=외곽선)"""
        self.config["subtitle_stroke_width"] = int(val)
        self._apply_text_effect()
        self.update()
        if self.on_config_change:
            self.on_config_change(self.config)

    def set_letter_spacing(self, val: float):
        """글자 자간(간격) 동적 변경 (외곽선 뭉침 방지 및 가독성 향상)"""
        self.config["letter_spacing"] = float(val)
        self._apply_config()
        if self.on_config_change:
            self.on_config_change(self.config)

    update_stroke_width = set_stroke_width
    update_letter_spacing = set_letter_spacing

    def set_clean_box(self, enabled: bool):
        """자막 배경 박스(반투명 라운드 박스) 렌더링 온/오프"""
        self.config["screen_clean_box"] = bool(enabled)
        self.update()
        if self.on_config_change:
            self.on_config_change(self.config)

    def set_show_original(self, enabled: bool):
        """원문 함께 표시 온/오프"""
        self.config["show_original"] = bool(enabled)
        if hasattr(self, 'label_original'):
            self.label_original.setVisible(bool(enabled))
        self._apply_config()
        self.update()
        if self.on_config_change:
            self.on_config_change(self.config)
        self._update_en_ko_button_styles()

    def _toggle_show_original(self):
        """원문 버튼 클릭: 원문 표시 토글"""
        new_val = not self.config.get("show_original", True)
        if not new_val and not getattr(self, '_show_translated', True):
            return
        self.set_show_original(new_val)

    def _toggle_show_translated(self):
        """번역 버튼 클릭: 번역문 표시 토글"""
        new_val = not getattr(self, '_show_translated', True)
        if not new_val and not self.config.get("show_original", True):
            return
        self._show_translated = new_val
        self.config["show_translated"] = new_val
        if hasattr(self, 'label_translated'):
            self.label_translated.setVisible(new_val)
        self._apply_config()
        self.update()
        if self.on_config_change:
            self.on_config_change(self.config)
        self._update_en_ko_button_styles()

    def _update_en_ko_button_styles(self):
        """원문/번역 토글 버튼의 활성/비활성 스타일 및 툴팁 업데이트"""
        if not hasattr(self, 'btn_toggle_en'):
            return
        en_on = self.config.get("show_original", True)
        ko_on = getattr(self, '_show_translated', True)
        style_on = (
            "QPushButton { background-color: rgba(0, 150, 136, 0.85); "
            "color: #FFFFFF; font-weight: bold; "
            "border: 1.5px solid rgba(0, 230, 200, 0.85); "
            "border-radius: 4px; padding: 0px 2px; font-size: 13px; }"
        )
        style_off = (
            "QPushButton { background-color: rgba(40, 44, 58, 0.60); "
            "color: rgba(200, 200, 200, 0.40); font-weight: bold; "
            "border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 4px; padding: 0px 2px; font-size: 13px; }"
        )
        self.btn_toggle_en.setStyleSheet(style_on if en_on else style_off)
        self.btn_toggle_ko.setStyleSheet(style_on if ko_on else style_off)
        self.btn_toggle_en.setToolTip(tr("overlay_tip_orig_on") if en_on else tr("overlay_tip_orig_off"))
        self.btn_toggle_ko.setToolTip(tr("overlay_tip_trans_on") if ko_on else tr("overlay_tip_trans_off"))

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
            self._set_header_chrome_opacity(1.0 if self._controls_in_use() else 0.35)
            if not self.is_click_through:
                self.size_grip.show()
        if self.config.get("show_original", True):
            self.label_original.show()
        else:
            self.label_original.hide()
        self.update()
        if self.on_config_change:
            self.on_config_change(self.config)
        if hasattr(self, 'ext_sync_clean_text') and self.ext_sync_clean_text:
            self.ext_sync_clean_text(enabled)

    def _update_clean_button_style(self):
        if not hasattr(self, 'btn_clean'):
            return
        if self.clean_text_mode:
            self.btn_clean.setText("✨ON")
            self.btn_clean.setFixedWidth(54)
            self.btn_clean.setStyleSheet("QPushButton { background-color: rgba(0, 150, 136, 0.85); color: #FFF; font-weight: bold; border-radius: 4px; padding: 0px 2px; font-size: 11px; }")
        else:
            self.btn_clean.setText("✨")
            self.btn_clean.setFixedWidth(34)
            self.btn_clean.setStyleSheet("QPushButton { background-color: rgba(30, 40, 55, 0.75); color: #EEE; font-weight: bold; border-radius: 4px; padding: 0px 2px; font-size: 11px; }")

    def _cursor_over_window(self):
        return self.isVisible() and self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    def _controls_in_use(self):
        if self.is_click_through:
            return self._is_pos_in_header(self.mapFromGlobal(QCursor.pos()))
        return (
            self.is_mouse_hovered or self.is_moving or
            self.active_resize_edge != EDGE_NONE or self._cursor_over_window()
        )

    def toggle_show_speaker(self):
        if not getattr(self, 'speaker_diarization_enabled', False):
            return
        self.set_show_speaker(not self.show_speaker)

    def set_speaker_diarization_enabled(self, enabled: bool):
        self.speaker_diarization_enabled = bool(enabled)
        self._update_speaker_button_style()

    def set_show_speaker(self, enabled: bool):
        enabled = bool(enabled)
        already_same = (getattr(self, 'show_speaker', None) == enabled)
        self.show_speaker = enabled
        self.config["show_speaker"] = enabled
        self._update_speaker_button_style()
        if getattr(self, 'current_translated', None):
            self.display_subtitle(self.current_original, self.current_translated)
        if not already_same:
            if self.on_config_change:
                self.on_config_change(self.config)
            if hasattr(self, 'ext_sync_show_speaker') and self.ext_sync_show_speaker:
                self.ext_sync_show_speaker(enabled)

    def _update_speaker_button_style(self):
        if not hasattr(self, 'btn_speaker'):
            return
        diar_enabled = getattr(self, 'speaker_diarization_enabled', False)
        if not diar_enabled:
            self.btn_speaker.setEnabled(False)
            self.btn_speaker.setText("🗣️")
            self.btn_speaker.setFixedWidth(34)
            self.btn_speaker.setCursor(Qt.CursorShape.ForbiddenCursor)
            self.btn_speaker.setStyleSheet(
                "QPushButton, QPushButton:disabled { background-color: rgba(30, 40, 55, 0.35); color: #666; font-weight: normal; "
                "border-radius: 4px; padding: 0px 2px; font-size: 11px; }"
            )
            self.btn_speaker.setToolTip(tr("overlay_tip_speaker_disabled"))
        else:
            self.btn_speaker.setEnabled(True)
            self.btn_speaker.setCursor(Qt.CursorShape.PointingHandCursor)
            if self.show_speaker:
                self.btn_speaker.setText("🗣️ON")
                self.btn_speaker.setFixedWidth(54)
                self.btn_speaker.setStyleSheet(
                    "QPushButton { background-color: rgba(0, 150, 136, 0.85); color: #FFF; font-weight: bold; "
                    "border-radius: 4px; padding: 0px 2px; font-size: 11px; }"
                )
                self.btn_speaker.setToolTip(tr("overlay_tip_speaker_on"))
            else:
                self.btn_speaker.setText("🗣️")
                self.btn_speaker.setFixedWidth(34)
                self.btn_speaker.setStyleSheet(
                    "QPushButton { background-color: rgba(30, 40, 55, 0.75); color: #EEE; font-weight: bold; "
                    "border-radius: 4px; padding: 0px 2px; font-size: 11px; }"
                )
                self.btn_speaker.setToolTip(tr("overlay_tip_speaker_off"))

    def _format_speaker_text(self, text: str) -> str:
        """화자 표시 설정(show_speaker)에 따라 화자 태그 필터링"""
        if not text:
            return ""
        if not getattr(self, 'show_speaker', True):
            clean = re.sub(r'<span[^>]*>\s*\[(?:화자|Speaker|[가-힣a-zA-Z0-9_\s]+)\s*[^\]]*\]\s*</span>\s*', '', text)
            clean = re.sub(r'\[(?:화자|Speaker)\s*[^\]]*\]:?\s*', '', clean)
            return clean.strip()
        return text

    def _apply_config(self):
        font_size = int(self.config.get("font_size", 22))
        letter_spacing = float(self.config.get("letter_spacing", 2.0))
        show_orig = self.config.get("show_original", True)
        self._apply_fixed_fonts(font_size, letter_spacing, show_orig)

        if self.config.get("click_through", False):
            self.set_click_through(True)

        if hasattr(self, 'label_original'):
            self.label_original.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.label_original.setContentsMargins(8, 6, 8, 6)
        if hasattr(self, 'label_translated'):
            self.label_translated.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.label_translated.setContentsMargins(8, 8, 8, 8)
        self._apply_two_line_overlay_height()

        if hasattr(self, 'live_badge'):
            self.live_badge.setVisible(self.config.get("show_engine_badge", True))

        if hasattr(self, '_update_clean_button_style'):
            self._update_clean_button_style()

        if hasattr(self, '_update_speaker_button_style'):
            self._update_speaker_button_style()

        if hasattr(self, 'btn_font_dec'):
            font_size = self.config.get("font_size", 22)
            self.btn_font_dec.setToolTip(tr("overlay_tip_font_dec", size=font_size))
        if hasattr(self, 'btn_font_inc'):
            font_size = self.config.get("font_size", 22)
            self.btn_font_inc.setToolTip(tr("overlay_tip_font_inc", size=font_size))

        if hasattr(self, 'btn_op_dec') and hasattr(self, 'btn_op_inc'):
            pct = int(self._normalize_bg_opacity(self.config.get("overlay_bg_opacity", 0.75)) * 100)
            self.btn_op_dec.setToolTip(tr("overlay_tip_op_dec_100", pct=pct) if pct == 0 else tr("overlay_tip_op_dec", pct=pct))
            self.btn_op_inc.setToolTip(tr("overlay_tip_op_inc", pct=pct))

        stroke_w = self.config.get("subtitle_stroke_width", 0)
        if stroke_w == 0:
            if not isinstance(getattr(self, 'stroke_effect', None), QGraphicsDropShadowEffect):
                self._apply_text_effect()
        else:
            if not isinstance(getattr(self, 'stroke_effect', None), ThickOutlineEffect) or getattr(self.stroke_effect, 'thickness', 0) != stroke_w:
                self._apply_text_effect()

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

    def _apply_ui_language(self):
        self.setWindowTitle(tr("overlay_audio_title"))
        if hasattr(self, "title_label") and self.title_label:
            if not getattr(self, "is_click_through", False):
                self.title_label.setText("🎤 " + tr("voice_translation"))
            else:
                self.title_label.setText(tr("overlay_click_through_active_voice"))
            self.title_label.setToolTip(tr("overlay_voice_tip"))
        if hasattr(self, "btn_pause") and self.btn_pause:
            paused = getattr(self, "_audio_paused", False)
            self.btn_pause.setToolTip(tr("overlay_pause_voice_on") if paused else tr("overlay_pause_toggle"))
        if hasattr(self, "combo_engine") and self.combo_engine:
            self.combo_engine.setToolTip(tr("overlay_tip_engine_combo"))
        if hasattr(self, "live_badge") and self.live_badge:
            self.live_badge.setToolTip(tr("overlay_tip_live_badge"))
            if self._is_waiting_badge_text(self.live_badge.text()):
                self.live_badge.setText(tr("overlay_waiting"))
            else:
                self.update_live_display()
        if hasattr(self, "btn_font_dec") and self.btn_font_dec:
            self.btn_font_dec.setToolTip(tr("overlay_tip_font_dec", size=self.config.get("font_size", 22)))
        if hasattr(self, "btn_font_inc") and self.btn_font_inc:
            self.btn_font_inc.setToolTip(tr("overlay_tip_font_inc", size=self.config.get("font_size", 22)))
        cur_op_pct = int(self._normalize_bg_opacity(self.config.get("overlay_bg_opacity", 0.75)) * 100)
        if hasattr(self, "btn_op_dec") and self.btn_op_dec:
            self.btn_op_dec.setToolTip(tr("overlay_tip_op_dec_100", pct=cur_op_pct) if cur_op_pct == 0 else tr("overlay_tip_op_dec", pct=cur_op_pct))
        if hasattr(self, "btn_op_inc") and self.btn_op_inc:
            self.btn_op_inc.setToolTip(tr("overlay_tip_op_inc", pct=cur_op_pct))
        if hasattr(self, "_update_en_ko_button_styles"):
            self._update_en_ko_button_styles()
        if hasattr(self, "_update_clean_button_style"):
            self._update_clean_button_style()
        if hasattr(self, "_update_speaker_button_style"):
            self._update_speaker_button_style()
        if hasattr(self, "btn_settings") and self.btn_settings:
            self.btn_settings.setToolTip(tr("overlay_tip_settings_detail"))
        if hasattr(self, "btn_lock") and self.btn_lock:
            self.btn_lock.setToolTip(tr("overlay_tip_lock_voice"))
        if hasattr(self, "btn_hide") and self.btn_hide:
            self.btn_hide.setToolTip(tr("overlay_tip_hide_voice"))
        if hasattr(self, "label_translated") and self.label_translated:
            if not getattr(self, "current_translated", None):
                self._set_label_html(self.label_translated, tr("overlay_voice_placeholder"), "#FFFFFF")

        self.update()

    def toggle_live_badge_dimmed(self):
        """실시간 뱃지 클릭 시 딤드/정상 토글 (화면에서 사라지지 않고 언제든 다시 클릭 가능)"""
        self.is_badge_dimmed = not getattr(self, 'is_badge_dimmed', False)
        if self.is_badge_dimmed:
            opacity_eff = QGraphicsOpacityEffect(self.live_badge)
            opacity_eff.setOpacity(0.2)
            self.live_badge.setGraphicsEffect(opacity_eff)
            self.live_badge.setToolTip(tr("overlay_tip_live_badge_dimmed"))
        else:
            self.live_badge.setGraphicsEffect(None)
            self.live_badge.setToolTip(tr("overlay_tip_live_badge"))

    def set_badge_visible(self, visible: bool):
        """컨트롤 패널 설정창에서 뱃지 표시 여부 설정 및 저장"""
        self.config["show_engine_badge"] = visible
        self.live_badge.setVisible(visible)
        if self.on_config_change:
            self.on_config_change(self.config)

    def _on_combo_engine_changed(self, idx):
        """번역기 선택 드롭다운 변경 핸들러 (선택 기능 전용)"""
        keys = [
            "deepl", "google", "gemini", "groq",
            "exaone", "gemma", "hymt"
        ]
        if 0 <= idx < len(keys):
            selected = keys[idx]
            self.config["translation_engine"] = selected
            if self.on_config_change:
                self.on_config_change(self.config)
            if hasattr(self, 'ext_change_engine') and self.ext_change_engine:
                self.ext_change_engine(selected)
            self.update_live_display()

    def set_engine_by_key(self, engine_key: str):
        """외부(컨트롤 패널 등)에서 엔진 변경 시 콤보박스 및 실시간 뱃지 동기화"""
        if not engine_key:
            return
        ek = str(engine_key).lower()
        if "hymt" in ek or "hy-mt" in ek:
            normalized = "hymt"
        elif "exaone" in ek:
            normalized = "exaone"
        elif "gemma" in ek:
            normalized = "gemma"
        elif "deepl" in ek:
            normalized = "deepl"
        elif "gemini" in ek:
            normalized = "gemini"
        elif "groq" in ek:
            normalized = "groq"
        elif "google" in ek:
            normalized = "google"
        else:
            normalized = ek

        idx_map = {
            "deepl": 0, "google": 1, "gemini": 2, "groq": 3,
            "exaone": 4, "gemma": 5, "hymt": 6
        }
        disp_map = {
            "deepl": "DeepL", "google": "Google", "gemini": "Gemini", "groq": "Groq",
            "exaone": "EXAONE", "gemma": "Gemma", "hymt": "Hy-MT2"
        }
        if normalized in idx_map:
            self.combo_engine.blockSignals(True)
            self.combo_engine.setCurrentIndex(idx_map[normalized])
            self.combo_engine.blockSignals(False)
            disp_eng = disp_map.get(normalized, normalized.capitalize())
            self.update_live_display(engine=disp_eng)

    def update_live_display(self, hw=None, engine=None):
        """초기화 및 콤보박스 변경 시 실시간 뱃지 기본 텍스트 갱신"""
        from src.engine_badge import configured_stt_label, configured_translation_label
        hw = hw or configured_stt_label(self.config)
        engine = engine or configured_translation_label(self.config)
        self.update_badge(f"{hw} + {engine}")

    def update_badge(self, badge_text: str):
        """실시간 통역 콜백 시 전달되는 태그를 실시간 뱃지에 반영 (고정폭, Jitter 0%)"""
        if not badge_text:
            return
        from src.engine_badge import stt_badge, translation_badge, configured_translation_label

        # 분리 처리 (STT 엔진 + 번역 엔진)
        if "+" in badge_text:
            raw_hw, raw_eng = [p.strip() for p in badge_text.split("+", 1)]
        else:
            raw_hw, raw_eng = badge_text, ""
        hw, stt_fallback = stt_badge(raw_hw, self.config)
        engine, trans_fallback = translation_badge(raw_eng, self.config)
        is_fallback = stt_fallback or trans_fallback

        # 엔진별 미니 도트 색상 (폴백 시 호박색, 정상 시 고유 색상)
        # Gemma: 구글블루(#4285F4), EXAONE: 장미/로즈(#E91E63), Hy-MT2: 청록(#00E5FF), DeepL: 파랑(#64B5F6), Gemini: 보라(#BA68C8), Groq: 주황-레드(#F55036), Google: 초록(#81C784)
        if is_fallback:
            dot_color = "#FFD54F"
        elif engine == "Hy-MT2":
            dot_color = "#00E5FF"
        elif engine == "Gemma":
            dot_color = "#4285F4"
        elif engine == "EXAONE":
            dot_color = "#E91E63"
        elif engine == "DeepL":
            dot_color = "#64B5F6"
        elif engine == "Gemini":
            dot_color = "#BA68C8"
        elif engine == "Groq":
            dot_color = "#F55036"
        else:
            dot_color = "#81C784"

        tag_text = f"{hw} &middot; {engine}"
        if is_fallback:
            # 고정폭 배지를 넘치면 "(폴백)" 글자는 빼고 호박색 점과 툴팁으로만 알린다
            font = QFont(self.live_badge.font())
            font.setPixelSize(10)
            font.setBold(True)
            fallback_label = f" ({tr('badge_fallback')})"
            if QFontMetrics(font).horizontalAdvance(f"• {hw} · {engine}{fallback_label}") + 12 <= self.live_badge.width():
                tag_text += fallback_label
            reasons = []
            if stt_fallback:
                reasons.append(tr("badge_stt_fallback", hw=hw))
            if trans_fallback:
                reasons.append(tr("badge_trans_fallback", orig=configured_translation_label(self.config), engine=engine))
            self.live_badge.setToolTip(" | ".join(reasons) + tr("badge_temporary_issue"))
        else:
            self.live_badge.setToolTip(tr("badge_voice_status_tip", hw=hw, engine=engine))

        self.live_badge.setText(f"<span style='color: {dot_color}; font-size: 8px;'>&bull;</span> <span style='color: rgba(255, 255, 255, 0.85); font-size: 9.5px; font-weight: bold;'>{tag_text}</span>")

    def display_preview(self, partial_text: str, engine_badge: str = ""):
        """문장이 완성되기 전 실시간 타이핑되는 영어 프리뷰 표시 (체감 지연 0초, 타자기 커서)"""
        if getattr(self, '_audio_paused', False):
            return
        if not self.config.get("show_original", True):
            return

        now = time.time()
        self.is_previewing_new_sentence = (now - getattr(self, 'last_translated_time', 0.0) > 2.2)
        self.current_original = partial_text

        # 실시간 타이핑 중 폰트 동결 (불필요한 100ms 재계산 방지, 긴 문장일 때만 적응)
        last_len = getattr(self, '_last_preview_fit_len', 0)
        if self.is_previewing_new_sentence or last_len == 0 or abs(len(partial_text) - last_len) >= 30:
            self._auto_fit_text(partial_text, self.current_translated or "...")
            self._last_preview_fit_len = len(partial_text)

        # 영문 프리뷰 텍스트 즉시 표시 (커서 없이 깔끔한 텍스트 유지)
        format_func = getattr(self, '_format_speaker_text', lambda t: t)
        display_partial = format_func(partial_text)
        self._set_label_html(self.label_original, display_partial, self._original_color())
        self.clear_timer.start(8000)
        if hasattr(self, 'idle_timer'):
            self.idle_timer.start(3500)

    def _start_typewriter_korean(self, full_html: str):
        """한국어 번역문을 타자기처럼 빠르게 타이핑하며 출력"""
        if hasattr(self, '_typewriter_timer') and self._typewriter_timer.isActive():
            self._typewriter_timer.stop()

        # HTML 태그와 본문 분리 (화자 태그 등 보존)
        match = re.match(r'^(<span[^>]+>\[.*?\]</span>\s*)(.*)$', full_html)
        if match:
            prefix = match.group(1)
            body = match.group(2)
        else:
            prefix = ""
            body = full_html

        words = body.split()
        if len(words) <= 1:
            self._set_label_html(self.label_translated, full_html, self._translated_color())
            return

        self._tw_full_html = full_html
        self._tw_prefix = prefix
        self._tw_words = words
        self._tw_index = 1

        # 첫 단어 즉시 표시
        first_chunk = f"{prefix}{self._tw_words[0]}"
        self._set_label_html(self.label_translated, first_chunk, self._translated_color())

        if not hasattr(self, '_typewriter_timer'):
            self._typewriter_timer = QTimer(self)
            self._typewriter_timer.timeout.connect(self._advance_typewriter_korean)
        # 30ms 마다 한 단어씩 타건 (300ms 안에 한 문장 부드럽게 완성)
        self._typewriter_timer.start(30)

    def _advance_typewriter_korean(self):
        """첫 호출의 문장을 캡처하지 않고 현재 자막 상태로 진행한다."""
        if not self._typewriter_timer.isActive():
            return
        self._tw_index += 1
        if self._tw_index >= len(self._tw_words):
            self._typewriter_timer.stop()
            self._set_label_html(self.label_translated, self._tw_full_html, self._translated_color())
            return
        current_text = " ".join(self._tw_words[:self._tw_index])
        self._set_label_html(self.label_translated, f"{self._tw_prefix}{current_text}", self._translated_color())

    def display_subtitle(self, original_text: str, translated_text: str, engine_badge: str = ""):
        if getattr(self, '_audio_paused', False):
            return
        self.last_translated_time = time.time()
        self.is_previewing_new_sentence = False
        self.current_original = original_text
        self.current_translated = translated_text
        self._last_preview_fit_len = 0
        if engine_badge:
            self.update_badge(engine_badge)
        
        format_func = getattr(self, '_format_speaker_text', lambda t: t)
        display_ko = format_func(translated_text)
        display_en = format_func(original_text)
        target_lang = self.config.get("target_lang", "ko")
        formatted_ko = break_subtitle_text(display_ko, target_lang=target_lang, linebreak="<br>")
        formatted_en = smart_break_sentences(display_en, linebreak="<br>")
        self._auto_fit_text(formatted_en, formatted_ko)
        
        # 영문·한글 모두 완성된 문장을 가운데 정렬로 즉시 표시 (타자기 효과 없음)
        self._set_label_html(self.label_original, formatted_en, self._original_color())
        if hasattr(self, '_typewriter_timer') and self._typewriter_timer.isActive():
            self._typewriter_timer.stop()
        self._set_label_html(self.label_translated, formatted_ko, self._translated_color())
        
        # 8초 후 자동 지우기
        self.clear_timer.start(8000)
        if hasattr(self, 'idle_timer'):
            self.idle_timer.start(3500)

    def fade_or_clear_subtitles(self):
        if hasattr(self, '_typewriter_timer') and self._typewriter_timer.isActive():
            self._typewriter_timer.stop()
        self.current_original = ""
        self.current_translated = ""
        self.label_original.setText("")
        self._set_label_html(self.label_translated, "...", self._translated_color())

    def set_external_handlers(self, on_toggle_pause=None, on_change_engine=None, on_open_settings=None, on_sync_opacity=None, on_visibility_change=None, on_sync_font=None, on_sync_click_through=None, on_sync_clean_text=None, on_sync_show_speaker=None):
        self.ext_toggle_pause = on_toggle_pause
        self.ext_change_engine = on_change_engine
        self.ext_open_settings = on_open_settings
        self.ext_sync_opacity = on_sync_opacity
        self.ext_visibility_change = on_visibility_change
        self.ext_sync_font = on_sync_font
        self.ext_sync_click_through = on_sync_click_through
        self.ext_sync_clean_text = on_sync_clean_text
        self.ext_sync_show_speaker = on_sync_show_speaker

    def set_paused_state(self, is_paused: bool):
        """일시정지 / 재생 상태에 따른 버튼 텍스트 및 스타일 동기화"""
        self._audio_paused = bool(is_paused)
        if is_paused:
            self.btn_pause.setText("▶")
            self.btn_pause.setStyleSheet("QPushButton { background-color: rgba(180, 40, 40, 0.85); color: #FFF; font-weight: bold; border-radius: 4px; padding: 0px 2px; font-size: 11px; }")
            self.btn_pause.setToolTip(tr("overlay_pause_voice_on"))
        else:
            self.btn_pause.setText("⏸")
            self.btn_pause.setStyleSheet("QPushButton { background-color: rgba(45, 48, 62, 0.75); color: #EEE; font-weight: bold; border-radius: 4px; padding: 0px 2px; font-size: 11px; }")
            self.btn_pause.setToolTip(tr("overlay_pause_voice_off"))

    def _on_pause_clicked(self):
        if hasattr(self, 'ext_toggle_pause') and self.ext_toggle_pause:
            self.ext_toggle_pause()
        else:
            is_paused = (self.btn_pause.text() == "⏸")
            self.set_paused_state(is_paused)

    def _on_engine_selected(self, idx):
        self._on_combo_engine_changed(idx)

    def update_font_size(self, val: int):
        """글꼴 크기 외부 설정 반영"""
        self.config["font_size"] = int(val)
        self._last_orig_style_key = None
        self._last_trans_style_key = None
        self._apply_config()
        self._apply_two_line_overlay_height(follow_font=True)
        if self.on_config_change:
            self.on_config_change(self.config)

    def update_opacity(self, pct: float):
        """배경 불투명도 외부 설정 반영 (0.0~1.0 또는 0~100)"""
        val = self._normalize_bg_opacity(pct)
        self.config["overlay_bg_opacity"] = float(val)
        self.update()
        if self.on_config_change:
            self.on_config_change(self.config)

    set_font_size = update_font_size
    set_bg_opacity = update_opacity

    def _decrease_font(self):
        cur = max(14, self.config.get("font_size", 22) - 2)
        self.config["font_size"] = cur
        if self.on_config_change:
            self.on_config_change(self.config)
        self._last_orig_style_key = None
        self._last_trans_style_key = None
        self._apply_config()
        self._apply_two_line_overlay_height(follow_font=True)
        if hasattr(self, 'ext_sync_font') and self.ext_sync_font:
            self.ext_sync_font(cur)

    def _increase_font(self):
        cur = min(40, self.config.get("font_size", 22) + 2)
        self.config["font_size"] = cur
        if self.on_config_change:
            self.on_config_change(self.config)
        self._last_orig_style_key = None
        self._last_trans_style_key = None
        self._apply_config()
        self._apply_two_line_overlay_height(follow_font=True)
        if hasattr(self, 'ext_sync_font') and self.ext_sync_font:
            self.ext_sync_font(cur)

    def _decrease_opacity(self):
        cur = round(max(0.0, self._normalize_bg_opacity(self.config.get("overlay_bg_opacity", 0.75)) - 0.10), 2)
        self.config["overlay_bg_opacity"] = cur
        if self.on_config_change:
            self.on_config_change(self.config)
        self.update()
        pct = int(cur * 100)
        dec_txt = tr("overlay_tip_op_dec_100", pct=pct) if pct == 0 else tr("overlay_tip_op_dec", pct=pct)
        self.btn_op_dec.setToolTip(dec_txt)
        self.btn_op_inc.setToolTip(tr("overlay_tip_op_inc", pct=pct))
        if hasattr(self, 'ext_sync_opacity') and self.ext_sync_opacity:
            self.ext_sync_opacity(pct)

    def _increase_opacity(self):
        cur = round(min(1.0, self._normalize_bg_opacity(self.config.get("overlay_bg_opacity", 0.75)) + 0.10), 2)
        self.config["overlay_bg_opacity"] = cur
        if self.on_config_change:
            self.on_config_change(self.config)
        self.update()
        pct = int(cur * 100)
        self.btn_op_dec.setToolTip(tr("overlay_tip_op_dec_100", pct=pct) if pct == 0 else tr("overlay_tip_op_dec", pct=pct))
        self.btn_op_inc.setToolTip(tr("overlay_tip_op_inc", pct=pct))
        if hasattr(self, 'ext_sync_opacity') and self.ext_sync_opacity:
            self.ext_sync_opacity(pct)

    def _open_settings(self):
        if hasattr(self, 'ext_open_settings') and self.ext_open_settings:
            self.ext_open_settings()

    def toggle_click_through(self):
        self.set_click_through(not self.is_click_through)

    def set_click_through(self, enabled: bool):
        self.is_click_through = enabled
        self.config["click_through"] = enabled
        if self.on_config_change:
            self.on_config_change(self.config)

        # Qt 레벨 관통은 사용하지 않음 — nativeEvent(WM_NCHITTEST)로 영역별 관통 제어
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        if enabled:
            self.title_label.setText(tr("overlay_click_through_active_voice"))
            self.title_label.setStyleSheet("QLabel { color: rgba(100, 255, 100, 0.9); font-size: 11px; font-weight: bold; }")
            self.btn_lock.setText("🔓ON")
            self.btn_lock.setFixedWidth(54)
            self.btn_lock.setStyleSheet("QPushButton { background-color: rgba(30, 140, 50, 0.9); color: #FFF; border: 1px solid rgba(100, 255, 120, 0.8); border-radius: 4px; padding: 0px 2px; font-size: 11px; font-weight: bold; }")
            self.size_grip.hide()
            self._set_header_chrome_opacity(0.35)
        else:
            self.title_label.setText("🎤 " + tr("voice_translation"))
            self.title_label.setStyleSheet("QLabel { color: rgba(255, 255, 255, 0.55); font-size: 11px; font-weight: bold; }")
            self.btn_lock.setText("🔒")
            self.btn_lock.setFixedWidth(34)
            self.btn_lock.setStyleSheet("QPushButton { background-color: rgba(60, 60, 80, 0.7); color: #DDD; border-radius: 4px; padding: 0px 2px; font-size: 11px; }")
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
                # PyQt6: message는 sip.voidptr → int로 변환 후 MSG 구조체 파싱
                msg_ptr = int(message)
                # Windows x64 MSG 구조체 레이아웃:
                # HWND(8) + UINT message(4) + padding(4) + WPARAM(8) + LPARAM(8)
                msg_bytes = ctypes.string_at(msg_ptr, 36)
                msg_id = struct.unpack_from("I", msg_bytes, 8)[0]  # UINT message at offset 8

                WM_NCHITTEST = 0x0084
                HTTRANSPARENT = -1
                HTCLIENT = 1

                if msg_id == WM_NCHITTEST:
                    lparam = struct.unpack_from("q", msg_bytes, 24)[0]  # LPARAM at offset 24
                    # LPARAM → 스크린 물리 좌표 (LOWORD=x, HIWORD=y, signed)
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
                        # 자막 영역: OS에 HTTRANSPARENT 반환 → 뒤 창으로 클릭 관통
                        return True, HTTRANSPARENT
            except Exception:
                pass
        ret = super().nativeEvent(eventType, message)
        if isinstance(ret, tuple) and len(ret) == 2 and ret[1] is not None:
            return ret
        return False, 0

    def _on_idle_timeout(self):
        # 콤보박스 드롭다운이 열려있거나 마우스가 컨트롤 영역에 머물고 있으면 숨김 보류
        if hasattr(self, 'combo_engine') and self.combo_engine.view().isVisible():
            self.idle_timer.start(2000)
            return
        if self._is_pos_in_header(self.mapFromGlobal(QCursor.pos())):
            self.idle_timer.start(2000)
            return
        
        self.is_idle = True
        if self.is_click_through:
            # 관통 모드에서는 해제 버튼 위치를 인지할 수 있도록 은은하게(0.25) 유지
            self._set_header_chrome_opacity(0.25)
        else:
            self._set_header_chrome_opacity(0.0)
        self.size_grip.hide()
        if self.clean_text_mode and hasattr(self, 'label_original'):
            self.label_original.hide()
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        self.is_idle = False
        self.is_mouse_hovered = True
        # 마우스 오버 시 자막 자동 소거 타이머 일시정지 (읽는 동안 자막 소거 방지)
        if hasattr(self, 'clear_timer'):
            self.clear_timer.stop()
        if self.is_click_through:
            # 관통 모드: 헤더 영역 호버 시 컨트롤 표시 (nativeEvent가 히트테스트 관리)
            self._set_header_chrome_opacity(1.0)
        else:
            self._set_header_chrome_opacity(1.0)
            self.size_grip.show()
        self.idle_timer.start(3500)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.is_mouse_hovered = False
        if not self.active_resize_edge:
            self.unsetCursor()
        if self.is_click_through:
            self._set_header_chrome_opacity(0.25)
        elif not self.clean_text_mode:
            self._set_header_chrome_opacity(0.35)
        else:
            self._set_header_chrome_opacity(0.0)
        self.idle_timer.start(1500)
        if getattr(self, 'current_translated', None) and hasattr(self, 'clear_timer'):
            self.clear_timer.start(8000)
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
            self.update()
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

            # 커서 상태 갱신
            self._update_cursor_for_edges(self._get_resize_edges(event.position().toPoint()))

            g = self.geometry()
            if was_resizing:
                self.base_geometry = [g.x(), g.y(), g.width(), g.height()]
                self.is_user_sized = True
                self.is_user_positioned = True
                self.config["window_geometry"] = list(self.base_geometry)
                if self.on_config_change:
                    self.on_config_change(self.config)
            elif was_moving:
                # 이동만 한 경우 크기는 사용자가 조절했던 크기 보존, 위치만 안전하게 갱신
                saved_w = self.base_geometry[2] if len(self.base_geometry) == 4 else g.width()
                saved_h = self.base_geometry[3] if len(self.base_geometry) == 4 else g.height()
                self.base_geometry = [g.x(), g.y(), saved_w, saved_h]
                self.is_user_positioned = True
                self.config["window_geometry"] = list(self.base_geometry)
                if self.on_config_change:
                    self.on_config_change(self.config)

            event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._reject_unwanted_resize():
            return

        g = self.geometry()
        if not self.is_auto_resizing:
            self.base_geometry = [g.x(), g.y(), g.width(), g.height()]
            self.is_user_sized = True
            self.is_user_positioned = True
            self.config["window_geometry"] = [g.x(), g.y(), g.width(), g.height()]
            if self.on_config_change:
                self.on_config_change(self.config)

        # 창 크기 변경 시 현재 텍스트 크기 반응형 재조정 (창 높이는 사용자 조절 유지)
        if not self.is_auto_resizing and self.current_translated:
            self._auto_fit_text(self.current_original, self.current_translated, adjust_window=False)
