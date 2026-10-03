from PyQt6.QtCore import Qt, QRect, QObject
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush

class SingleROIBorderWidget(QWidget):
    """
    개별 감시 관심 영역(ROI)의 외곽 테두리(엣지)만을 화면에 실시간 오버랩 표시하는 전용 창.
    - 완벽한 마우스 클릭 관통 (WA_TransparentForMouseEvents, WS_EX_TRANSPARENT)
    - 화면 캡처 제외 (WDA_EXCLUDEFROMCAPTURE)로 OCR 간섭 0%
    - 4개 모서리 L-브래킷 + 고대비 네온 사이언 엣지 라인으로 시인성 극대화
    """
    def __init__(self, roi, roi_idx=0, show_badge=True, parent=None):
        super().__init__(parent)
        self.roi = roi
        self.roi_idx = roi_idx
        self.show_badge = show_badge

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.update_geometry_from_roi(roi)

    def update_geometry_from_roi(self, roi, roi_idx=None, show_badge=None):
        if roi and len(roi) == 4:
            self.roi = list(roi)
            self.setGeometry(roi[0], roi[1], roi[2], roi[3])
        if roi_idx is not None:
            self.roi_idx = roi_idx
        if show_badge is not None:
            self.show_badge = show_badge
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        try:
            import ctypes
            hwnd = int(self.winId())
            if hwnd:
                # 1. 캡처 제외 (RapidOCR / 스크린 캡처에 테두리가 찍히지 않도록 차단)
                WDA_EXCLUDEFROMCAPTURE = 0x00000011
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)

                # 2. 윈도우 OS 레벨 마우스 클릭 관통(WS_EX_TRANSPARENT | WS_EX_LAYERED) 강제 보장
                GWL_EXSTYLE = -20
                WS_EX_TRANSPARENT = 0x00000020
                WS_EX_LAYERED = 0x00080000
                WS_EX_NOACTIVATE = 0x08000000
                cur_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(
                    hwnd, GWL_EXSTYLE,
                    cur_style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE
                )
        except Exception:
            pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        if w <= 10 or h <= 10:
            return

        # 1. 엣지 테두리 (1.5px 점선 네온 사이언)
        border_color = QColor(0, 229, 255, 180)  # #00E5FF 70%
        pen_border = QPen(border_color, 1.5, Qt.PenStyle.DashLine)
        painter.setPen(pen_border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(1, 1, w - 2, h - 2)

        # 2. 4개 모서리 강조 엣지 브래킷 (L-Bracket, 3.0px 고대비 솔리드 라인)
        corner_len = min(28, max(12, min(w, h) // 4))
        corner_color = QColor(0, 229, 255, 255) # #00E5FF 100%
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

        # 3. 다중 영역 식별 뱃지 (다중 영역일 때 또는 show_badge=True 시 표시)
        if self.show_badge:
            badge_text = f" #{self.roi_idx + 1} "
            font = QFont("Malgun Gothic", 8, QFont.Weight.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            bw = fm.horizontalAdvance(badge_text) + 6
            bh = 16
            badge_rect = QRect(4, 4, bw, bh)
            painter.setPen(QPen(QColor(0, 229, 255, 200), 1))
            painter.setBrush(QBrush(QColor(15, 23, 42, 220)))
            painter.drawRoundedRect(badge_rect, 3, 3)
            painter.setPen(QColor(0, 229, 255, 255))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

class ROIBorderManager(QObject):
    """
    모든 감시 관심 영역(ROI) 테두리 오버레이 위젯들의 생명주기와 동기화를 총괄하는 관리자 클래스.
    """
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.widgets = []
        self.is_enabled = self.config.get("screen_show_roi_border", False)
        self.sync_rois()

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
            w = SingleROIBorderWidget(rois[idx], roi_idx=idx, show_badge=(len(rois) > 1))
            self.widgets.append(w)

        # 기존 위젯 좌표 및 뱃지 표시 여부 업데이트
        show_badge = len(rois) > 1
        for idx, (w, r) in enumerate(zip(self.widgets, rois)):
            w.update_geometry_from_roi(r, roi_idx=idx, show_badge=show_badge)

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
