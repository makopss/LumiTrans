from PyQt6.QtCore import Qt, QRect, QPoint, QObject
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QRegion, QFontMetrics
from src.i18n import tr

EDGE_NONE = 0
EDGE_LEFT = 1
EDGE_RIGHT = 2
EDGE_TOP = 4
EDGE_BOTTOM = 8
EDGE_MARGIN = 10       # 테두리 감지 두께 (px)
CORNER_MARGIN = 20     # 모서리 리사이즈 감지 길이 (px)


class SingleROIBorderWidget(QWidget):
    """
    개별 감시 관심 영역(ROI)의 외곽 테두리(엣지)를 화면에 실시간 오버랩 표시하고
    마우스 드래그를 통해 실시간으로 크기 조절 및 위치 이동이 가능한 인터랙티브 오버레이 창.
    - 영역 내부는 완벽한 마우스 클릭 관통(setMask)으로 게임/작업 방해 0%
    - 테두리(8방향) 및 배지(✥) 드래그로 실시간 직관적 조절 가능
    - 화면 캡처 제외(WDA_EXCLUDEFROMCAPTURE)로 OCR 간섭 0%
    - 4개 모서리 L-브래킷 + 고대비 네온 사이언 엣지 라인으로 시인성 극대화
    """
    def __init__(self, roi, roi_idx=0, show_badge=True, on_adjusted=None, parent=None):
        super().__init__(parent)
        self.roi = list(roi) if roi else [100, 100, 400, 200]
        self.roi_idx = roi_idx
        self.show_badge = show_badge
        self.on_adjusted = on_adjusted  # cb(roi_idx, roi, is_final)

        self.is_moving = False
        self.is_resizing = False
        self.active_resize_edge = EDGE_NONE
        self.drag_start_pos = None
        self.drag_start_geo = None
        self.is_badge_hovered = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)

        self.update_geometry_from_roi(self.roi)

    def _get_badge_rect(self) -> QRect:
        w = self.width()
        h = self.height()
        badge_text = f" ✥ #{self.roi_idx + 1}  {w}×{h} "
        font = QFont("Malgun Gothic", 8, QFont.Weight.Bold)
        fm = QFontMetrics(font)
        bw = fm.horizontalAdvance(badge_text) + 10
        bh = 18
        start_x = 24 if w > 120 else 4
        return QRect(start_x, 2, min(bw, max(40, w - start_x - 4)), min(bh, max(14, h - 4)))

    def _update_mask(self):
        w = self.width()
        h = self.height()
        margin = EDGE_MARGIN
        if w <= 2 * margin or h <= 2 * margin:
            self.clearMask()
            return

        outer_rect = QRect(0, 0, w, h)
        inner_rect = QRect(margin, margin, w - 2 * margin, h - 2 * margin)
        border_region = QRegion(outer_rect).subtracted(QRegion(inner_rect))

        c_size = min(CORNER_MARGIN + 4, max(12, min(w, h) // 4))
        c_tl = QRegion(QRect(0, 0, c_size, c_size))
        c_tr = QRegion(QRect(w - c_size, 0, c_size, c_size))
        c_bl = QRegion(QRect(0, h - c_size, c_size, c_size))
        c_br = QRegion(QRect(w - c_size, h - c_size, c_size, c_size))

        badge_region = QRegion(self._get_badge_rect())
        total_region = border_region.united(c_tl).united(c_tr).united(c_bl).united(c_br).united(badge_region)
        self.setMask(total_region)

    def update_geometry_from_roi(self, roi, roi_idx=None, show_badge=None):
        if getattr(self, 'is_moving', False) or getattr(self, 'is_resizing', False):
            return
        if roi and len(roi) == 4:
            self.roi = list(roi)
            self.setGeometry(roi[0], roi[1], roi[2], roi[3])
            self._update_mask()
        if roi_idx is not None:
            self.roi_idx = roi_idx
        if show_badge is not None:
            self.show_badge = show_badge
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_mask()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_mask()
        try:
            import ctypes
            hwnd = int(self.winId())
            if hwnd:
                # 1. 캡처 제외 (RapidOCR / 스크린 캡처에 테두리가 찍히지 않도록 차단)
                WDA_EXCLUDEFROMCAPTURE = 0x00000011
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)

                # 2. 윈도우 스타일 (클릭 시 포커스 뺏기지 않도록 WS_EX_NOACTIVATE 유지, 
                #    WS_EX_TRANSPARENT는 적용하지 않아 마스크된 테두리/배지 영역에서 마우스 조작 보장)
                GWL_EXSTYLE = -20
                WS_EX_LAYERED = 0x00080000
                WS_EX_NOACTIVATE = 0x08000000
                cur_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(
                    hwnd, GWL_EXSTYLE,
                    cur_style | WS_EX_LAYERED | WS_EX_NOACTIVATE
                )
        except Exception:
            pass

    def _get_resize_edge(self, pos: QPoint) -> int:
        badge_rect = self._get_badge_rect()
        if badge_rect.contains(pos):
            return EDGE_NONE

        edges = EDGE_NONE
        w = self.width()
        h = self.height()
        x = pos.x()
        y = pos.y()

        is_left = (x < CORNER_MARGIN)
        is_right = (x > w - CORNER_MARGIN)
        is_top = (y < CORNER_MARGIN)
        is_bottom = (y > h - CORNER_MARGIN)

        if is_left and is_top:
            return EDGE_LEFT | EDGE_TOP
        if is_right and is_top:
            return EDGE_RIGHT | EDGE_TOP
        if is_left and is_bottom:
            return EDGE_LEFT | EDGE_BOTTOM
        if is_right and is_bottom:
            return EDGE_RIGHT | EDGE_BOTTOM

        if x < EDGE_MARGIN:
            edges |= EDGE_LEFT
        elif x > w - EDGE_MARGIN:
            edges |= EDGE_RIGHT

        if y < EDGE_MARGIN:
            edges |= EDGE_TOP
        elif y > h - EDGE_MARGIN:
            edges |= EDGE_BOTTOM

        return edges

    def _update_cursor_for_edge(self, edge: int, pos: QPoint):
        badge_rect = self._get_badge_rect()
        if badge_rect.contains(pos):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.setToolTip(f"#{self.roi_idx + 1} {tr('roi_drag_to_move')}")
            return

        self.setToolTip(tr("roi_border_resize"))
        if edge in (EDGE_LEFT | EDGE_TOP, EDGE_RIGHT | EDGE_BOTTOM):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge in (EDGE_RIGHT | EDGE_TOP, EDGE_LEFT | EDGE_BOTTOM):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edge & (EDGE_LEFT | EDGE_RIGHT):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edge & (EDGE_TOP | EDGE_BOTTOM):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setToolTip("")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            badge_rect = self._get_badge_rect()
            if badge_rect.contains(pos):
                self.is_moving = True
                self.drag_start_pos = event.globalPosition().toPoint()
                self.drag_start_geo = self.geometry()
                self.update()
                event.accept()
                return

            edge = self._get_resize_edge(pos)
            if edge != EDGE_NONE:
                self.is_resizing = True
                self.active_resize_edge = edge
                self.drag_start_pos = event.globalPosition().toPoint()
                self.drag_start_geo = self.geometry()
                self.update()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        cur_global = event.globalPosition().toPoint()
        if self.is_moving and self.drag_start_pos and self.drag_start_geo:
            delta = cur_global - self.drag_start_pos
            new_x = self.drag_start_geo.x() + delta.x()
            new_y = self.drag_start_geo.y() + delta.y()
            self.move(new_x, new_y)
            self.roi = [new_x, new_y, self.width(), self.height()]
            if self.on_adjusted:
                self.on_adjusted(self.roi_idx, self.roi, False)
            event.accept()
            return

        if self.is_resizing and self.drag_start_pos and self.drag_start_geo:
            delta = cur_global - self.drag_start_pos
            orig_x = self.drag_start_geo.x()
            orig_y = self.drag_start_geo.y()
            orig_w = self.drag_start_geo.width()
            orig_h = self.drag_start_geo.height()
            dx = delta.x()
            dy = delta.y()
            min_w, min_h = 60, 40

            new_x, new_y, new_w, new_h = orig_x, orig_y, orig_w, orig_h

            if self.active_resize_edge & EDGE_LEFT:
                if orig_w - dx < min_w:
                    new_w = min_w
                    new_x = orig_x + (orig_w - min_w)
                else:
                    new_w = orig_w - dx
                    new_x = orig_x + dx
            elif self.active_resize_edge & EDGE_RIGHT:
                new_w = max(min_w, orig_w + dx)

            if self.active_resize_edge & EDGE_TOP:
                if orig_h - dy < min_h:
                    new_h = min_h
                    new_y = orig_y + (orig_h - min_h)
                else:
                    new_h = orig_h - dy
                    new_y = orig_y + dy
            elif self.active_resize_edge & EDGE_BOTTOM:
                new_h = max(min_h, orig_h + dy)

            self.setGeometry(new_x, new_y, new_w, new_h)
            self.roi = [new_x, new_y, new_w, new_h]
            self._update_mask()
            if self.on_adjusted:
                self.on_adjusted(self.roi_idx, self.roi, False)
            event.accept()
            return

        badge_rect = self._get_badge_rect()
        was_badge_hovered = getattr(self, 'is_badge_hovered', False)
        self.is_badge_hovered = badge_rect.contains(event.pos())
        if was_badge_hovered != self.is_badge_hovered:
            self.update()

        edge = self._get_resize_edge(event.pos())
        self._update_cursor_for_edge(edge, event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            was_active = self.is_moving or self.is_resizing
            self.is_moving = False
            self.is_resizing = False
            self.active_resize_edge = EDGE_NONE
            self.drag_start_pos = None
            self.drag_start_geo = None
            self.update()
            if was_active:
                self.roi = [self.x(), self.y(), self.width(), self.height()]
                self._update_mask()
                if self.on_adjusted:
                    self.on_adjusted(self.roi_idx, self.roi, True)
                event.accept()
                return

        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self.is_badge_hovered = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setToolTip("")
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        if w <= 10 or h <= 10:
            return

        is_active = self.is_moving or self.is_resizing

        # 1. 엣지 테두리 (1.5px 점선 네온 사이언)
        border_color = QColor(0, 245, 255, 240) if is_active else QColor(0, 229, 255, 180)
        pen_border = QPen(border_color, 1.5, Qt.PenStyle.DashLine)
        painter.setPen(pen_border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(1, 1, w - 2, h - 2)

        # 2. 4개 모서리 강조 엣지 브래킷 (L-Bracket, 3.0px 고대비 솔리드 라인)
        corner_len = min(28, max(12, min(w, h) // 4))
        corner_color = QColor(0, 245, 255, 255)
        pen_corner = QPen(corner_color, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap)
        painter.setPen(pen_corner)

        # Top-Left
        painter.drawLine(1, 1, 1 + corner_len, 1)
        painter.drawLine(1, 1, 1, 1 + corner_len)
        # Top-Right
        painter.drawLine(w - 2, 1, w - 2 - corner_len, 1)
        painter.drawLine(w - 2, 1, w - 2, 1 + corner_len)
        # Bottom-Left
        painter.drawLine(1, h - 2, 1 + corner_len, h - 2)
        painter.drawLine(1, h - 2, 1, h - 2 - corner_len)
        # Bottom-Right
        painter.drawLine(w - 2, h - 2, w - 2 - corner_len, h - 2)
        painter.drawLine(w - 2, h - 2, w - 2, h - 2 - corner_len)

        # 2-1. 4개 변 중앙 리사이즈 핸들 점
        s = 6
        s2 = s // 2
        painter.setPen(QPen(QColor(15, 23, 42, 220), 1))
        painter.setBrush(QBrush(QColor(0, 245, 255, 230)))
        painter.drawRect(w // 2 - s2, 1 - s2, s, s)
        painter.drawRect(w // 2 - s2, h - 2 - s2, s, s)
        painter.drawRect(1 - s2, h // 2 - s2, s, s)
        painter.drawRect(w - 2 - s2, h // 2 - s2, s, s)

        # 3. 감시 영역 식별 및 이동 핸들 배지
        badge_rect = self._get_badge_rect()
        badge_text = f" ✥ #{self.roi_idx + 1}  {w}×{h} "
        font = QFont("Malgun Gothic", 8, QFont.Weight.Bold)
        painter.setFont(font)

        is_bh = getattr(self, 'is_badge_hovered', False) or is_active
        bg_color = QColor(18, 32, 60, 245) if is_bh else QColor(10, 18, 36, 220)
        border_c = QColor(0, 255, 255, 255) if is_bh else QColor(0, 229, 255, 200)
        text_c = QColor(255, 255, 255) if is_bh else QColor(0, 229, 255, 255)

        painter.setPen(QPen(border_c, 1.5 if is_bh else 1.0))
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(badge_rect, 4, 4)
        painter.setPen(text_c)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)


class ROIBorderManager(QObject):
    """
    모든 감시 관심 영역(ROI) 테두리 오버레이 위젯들의 생명주기, 실시간 조절 및 동기화를 총괄하는 관리자 클래스.
    """
    def __init__(self, config, on_rois_changed=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.on_rois_changed = on_rois_changed
        self.widgets = []
        self.is_enabled = self.config.get("screen_show_roi_border", False)
        self.sync_rois()

    def set_on_rois_changed(self, cb):
        self.on_rois_changed = cb

    def _on_widget_roi_adjusted(self, roi_idx: int, new_roi: list, is_final: bool):
        rois = self.config.get("screen_rois", [])
        if 0 <= roi_idx < len(rois):
            rois[roi_idx] = list(new_roi)
        elif roi_idx == 0:
            rois = [list(new_roi)]
            self.config["screen_rois"] = rois

        if roi_idx == 0:
            self.config["screen_roi"] = list(new_roi)

        if self.on_rois_changed:
            self.on_rois_changed(rois, is_final=is_final)

    def sync_rois(self):
        """현재 config의 screen_rois 목록에 맞추어 테두리 위젯 인스턴스 동기화"""
        rois = [r for r in self.config.get("screen_rois", []) if len(r) == 4 and r[2] > 20 and r[3] > 20]
        if not rois:
            single = self.config.get("screen_roi")
            if single and len(single) == 4 and single[2] > 20 and single[3] > 20:
                rois = [single]

        # 잉여 위젯 제거
        while len(self.widgets) > len(rois):
            extra = self.widgets.pop()
            extra.hide()
            extra.deleteLater()

        # 부족한 위젯 추가
        while len(self.widgets) < len(rois):
            idx = len(self.widgets)
            w = SingleROIBorderWidget(
                rois[idx],
                roi_idx=idx,
                show_badge=True,
                on_adjusted=self._on_widget_roi_adjusted
            )
            self.widgets.append(w)

        # 기존 위젯 좌표 및 콜백/뱃지 업데이트
        for idx, (w, r) in enumerate(zip(self.widgets, rois)):
            w.on_adjusted = self._on_widget_roi_adjusted
            w.update_geometry_from_roi(r, roi_idx=idx, show_badge=True)

        # 활성화 상태에 따른 가시성 동기화
        if self.is_enabled and rois:
            for w in self.widgets:
                w.show()
                w.raise_()
        else:
            for w in self.widgets:
                w.hide()

    def set_enabled(self, enabled: bool):
        """테두리 오버레이 표시 켜기/끄기"""
        self.is_enabled = enabled
        self.config["screen_show_roi_border"] = enabled
        self.sync_rois()

    update_rois = sync_rois

    def toggle(self):
        """테두리 오버레이 토글"""
        self.set_enabled(not self.is_enabled)
        return self.is_enabled

    def show(self):
        self.set_enabled(True)

    def hide(self):
        for w in self.widgets:
            w.hide()

    def isVisible(self):
        return any(w.isVisible() for w in self.widgets)

    def close(self):
        for w in self.widgets:
            w.close()

    def get_overlays(self):
        """스냅샷 캡처 시 일시 숨김용 위젯 리스트 반환"""
        return list(self.widgets)
