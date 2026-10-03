import os
import sys
from PyQt6.QtWidgets import (
    QWidget, QLabel, QProgressBar, QVBoxLayout, QHBoxLayout, QApplication
)
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import (
    QPixmap, QColor, QPainter, QPainterPath, QLinearGradient, QPen
)


class LumiSplashScreen(QWidget):
    """
    루미트랜스 (LumiTrans) 전용 프리미엄 스플래시 스크린
    - 라운드 코너 (14px) 및 미세 발광 테두리
    - 풀블리드 고해상도 AI 스튜디오 아트워크 렌더링
    - 하단 상태 메시지 및 네온 그라디언트 프로그레스 바
    - 로딩이 끝나면 즉시 닫힘
    """
    def __init__(self, splash_image_path: str = None, width: int = 680, height: int = 380):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(width, height)

        if splash_image_path is None:
            if getattr(sys, "frozen", False):
                base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
                splash_image_path = os.path.join(base, "assets", "splash.png")
                if not os.path.exists(splash_image_path):
                    splash_image_path = os.path.join(os.path.dirname(sys.executable), "assets", "splash.png")
            else:
                base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                splash_image_path = os.path.join(base, "assets", "splash.png")

        self.image_path = splash_image_path
        self.pixmap = None
        if os.path.exists(self.image_path):
            self.pixmap = QPixmap(self.image_path).scaled(
                width, height,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )

        # UI 위젯 레이아웃 (하단 진행 상태 및 버전 표시)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)

        # 상단 우측: 버전 배지
        top_row = QHBoxLayout()
        top_row.addStretch(1)
        lbl_ver = QLabel("v2.5 Pro")
        lbl_ver.setStyleSheet("""
            color: rgba(255, 255, 255, 0.90);
            font-size: 11px;
            font-weight: bold;
            background-color: rgba(15, 23, 42, 0.70);
            border: 1px solid rgba(255, 255, 255, 0.20);
            border-radius: 6px;
            padding: 3px 9px;
        """)
        top_row.addWidget(lbl_ver)
        layout.addLayout(top_row)

        layout.addStretch(1)

        # 하단: 상태 메시지 & 슬림 네온 프로그레스 바
        self.lbl_status = QLabel("스튜디오 초기화 중...")
        self.lbl_status.setStyleSheet("""
            color: #F1F5F9;
            font-size: 12px;
            font-weight: 600;
            background: transparent;
        """)
        layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.15);
                border: none;
                border-radius: 1px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38BDF8, stop:0.5 #818CF8, stop:1 #34D399);
                border-radius: 1px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # 화면 중앙 배치
        self._center_on_screen()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2 + geo.left()
            y = (geo.height() - self.height()) // 2 + geo.top()
            self.move(x, y)

    def set_message(self, text: str, progress: int = None):
        """실시간 로딩 단계 안내 및 진행률 갱신"""
        self.lbl_status.setText(text)
        if progress is not None:
            self.progress_bar.setValue(min(100, max(0, progress)))
        QApplication.processEvents()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(self.width()), float(self.height()), 14.0, 14.0)
        painter.setClipPath(path)

        if self.pixmap and not self.pixmap.isNull():
            painter.drawPixmap(0, 0, self.pixmap)
        else:
            # 이미지 로드 실패 시 세련된 다크 테마 폴백
            grad = QLinearGradient(0, 0, float(self.width()), float(self.height()))
            grad.setColorAt(0.0, QColor("#0B0F19"))
            grad.setColorAt(1.0, QColor("#1E1B4B"))
            painter.fillPath(path, grad)

        # 하단 텍스트 가독성을 위한 은은한 다크 비네팅
        bottom_grad = QLinearGradient(0, float(self.height() - 90), 0, float(self.height()))
        bottom_grad.setColorAt(0.0, QColor(11, 15, 25, 0))
        bottom_grad.setColorAt(1.0, QColor(11, 15, 25, 220))
        painter.fillPath(path, bottom_grad)

        # 외곽 프리미엄 테두리 라인
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1.2))
        painter.drawRoundedRect(QRectF(1.0, 1.0, float(self.width() - 2), float(self.height() - 2)), 14.0, 14.0)

    def finish(self, target_window=None, delay_ms: int = 0):
        """로딩 완료 후 메인 창이 완벽히 렌더링된 상태에서 스플래시를 닫는다 (흰색 번쩍임 원천 차단)."""
        if target_window:
            target_window.setWindowOpacity(0.0)
            target_window.show()
            QApplication.processEvents()
            target_window.setWindowOpacity(1.0)
            target_window.raise_()
            target_window.activateWindow()
        if delay_ms > 0:
            QTimer.singleShot(delay_ms, self.close)
            return
        self.close()
