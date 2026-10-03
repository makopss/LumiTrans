from PyQt6.QtWidgets import QComboBox, QSlider, QListView, QApplication
from PyQt6.QtCore import QObject, QEvent, pyqtSignal, QPoint, Qt

class NoWheelComboBox(QComboBox):
    """
    마우스 휠 스크롤로 인한 의도치 않은 옵션 변경을 원천 차단하는 콤보박스 위젯.
    휠 이벤트를 무시(ignore)하여 부모 스크롤 영역(QScrollArea 등)으로 바이패스합니다.
    드롭다운 팝업 목록이 열려 있을 때는 목록 아이템 스크롤이 정상 동작합니다.
    드롭다운 열기 직전(about_to_show_popup) 시그널을 제공하여 동적 소스 새로고침을 지원합니다.
    force_down=True 시 드롭다운 팝업이 위로 튀어오르지 않고 항상 아래쪽(down)으로 펼쳐집니다.
    """
    about_to_show_popup = pyqtSignal()

    def __init__(self, parent=None, force_down: bool = True, max_visible_items: int = 8):
        super().__init__(parent)
        self.force_down = force_down
        self.setView(QListView(self))
        self.setMaxVisibleItems(max_visible_items)
        if self.view():
            self.view().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def showPopup(self):
        self.about_to_show_popup.emit()
        super().showPopup()
        if self.force_down:
            self._ensure_popup_down()

    def _ensure_popup_down(self):
        try:
            popup = self.view().window()
            if popup:
                p = self.mapToGlobal(QPoint(0, self.height()))
                screen = self.screen() or QApplication.primaryScreen()
                if screen:
                    screen_bottom = screen.availableGeometry().bottom()
                    available_h = screen_bottom - p.y() - 10
                    if available_h > 100 and popup.height() > available_h:
                        popup.resize(popup.width(), available_h)
                popup.move(p.x(), p.y())
        except Exception:
            pass

    def wheelEvent(self, event):
        event.ignore()

class NoWheelSlider(QSlider):
    """
    마우스 휠 스크롤로 인한 의도치 않은 수치 변경을 원천 차단하는 슬라이더바 위젯.
    휠 이벤트를 무시(ignore)하여 부모 창의 스크롤(QScrollArea)이 부드럽게 이어지도록 하고,
    오직 마우스로 슬라이더 바를 잡고 드래그(Drag)하거나 클릭할 때만 수치가 변경됩니다.
    """
    def wheelEvent(self, event):
        event.ignore()

class NoWheelFilter(QObject):
    """
    애플리케이션 전역 또는 특정 위젯 계층에서
    모든 QComboBox 및 QSlider의 마우스 휠 옵션/수치 변경을 일괄 차단하는 글로벌 이벤트 필터.
    """
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            if isinstance(obj, (QComboBox, QSlider)):
                event.ignore()
                return True
        return super().eventFilter(obj, event)
