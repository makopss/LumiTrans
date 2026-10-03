from PyQt6.QtCore import Qt, QRect, QPoint, QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QCursor

class SingleScreenOverlay(QWidget):
    """
    개별 모니터마다 1:1로 띄워지는 풀스크린 인터랙티브 다중 ROI 편집기.
    - 기존 영역 시각화 및 박스 내부 드래그로 위치 이동
    - 8방향 리사이즈 핸들(모서리 및 상하좌우)을 통한 실시간 바운더리 크기 조절
    - 개별 [✕] 버튼 및 Del 키를 통한 특정 ROI 삭제
    - 빈 공간 마우스 드래그로 새 ROI 추가
    """
    HANDLE_SIZE = 10

    def __init__(self, screen, screen_idx, coordinator, current_rois=None):
        super().__init__(None)
        self.target_screen = screen
        self.screen_idx = screen_idx
        self.coordinator = coordinator
        self.current_rois = current_rois or []

        self.is_selecting = False
        self.local_start = None
        self.local_current = None

        self.is_moving = False
        self.is_resizing = False
        self.active_roi_idx = -1
        self.resize_handle = None
        self.press_pos = None
        self.orig_roi = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self.setScreen(screen)
        geo = screen.geometry()
        self.setGeometry(geo)

    def _get_top_buttons_rects(self):
        w = self.width()
        btn_finish = QRect(w // 2 - 200, 14, 180, 36)
        btn_clear = QRect(w // 2 - 10, 14, 110, 36)
        btn_cancel = QRect(w // 2 + 110, 14, 90, 36)
        return btn_finish, btn_clear, btn_cancel

    def _get_roi_local_rect(self, gx, gy, gw, gh):
        s_geo = self.target_screen.geometry()
        lx = gx - s_geo.x()
        ly = gy - s_geo.y()
        return QRect(lx, ly, gw, gh)

    def _get_roi_badge_and_del_rects(self, local_rect):
        lx = local_rect.x()
        ly = local_rect.y()
        lw = local_rect.width()
        lh = local_rect.height()
        badge_w = 160
        badge_h = 24
        badge_y = ly - badge_h - 2 if ly >= (badge_h + 4) else ly + lh + 2
        badge_rect = QRect(lx, badge_y, badge_w, badge_h)
        del_btn_rect = QRect(lx + badge_w - 22, badge_y + 2, 20, 20)
        return badge_rect, del_btn_rect

    def _get_roi_visual_handles(self, r):
        """외곽선 위에 정확히 위치하는 그리기 전용 8개 리사이즈 핸들 포인트 (작고 깔끔한 8x8 사각형)"""
        s = 8
        s2 = s // 2
        lx, ly, lw, lh = r.x(), r.y(), r.width(), r.height()
        return [
            QRect(lx - s2, ly - s2, s, s),                 # top-left
            QRect(lx + lw - s2, ly - s2, s, s),            # top-right
            QRect(lx - s2, ly + lh - s2, s, s),            # bottom-left
            QRect(lx + lw - s2, ly + lh - s2, s, s),       # bottom-right
            QRect(lx + lw // 2 - s2, ly - s2, s, s),       # top-center
            QRect(lx + lw // 2 - s2, ly + lh - s2, s, s),  # bottom-center
            QRect(lx - s2, ly + lh // 2 - s2, s, s),       # left-center
            QRect(lx + lw - s2, ly + lh // 2 - s2, s, s),  # right-center
        ]

    def _get_roi_handles(self, r):
        hs = self.HANDLE_SIZE
        h2 = hs // 2
        lx, ly, lw, lh = r.x(), r.y(), r.width(), r.height()
        return {
            "top-left": QRect(lx - h2, ly - h2, hs, hs),
            "top-right": QRect(lx + lw - h2, ly - h2, hs, hs),
            "bottom-left": QRect(lx - h2, ly + lh - h2, hs, hs),
            "bottom-right": QRect(lx + lw - h2, ly + lh - h2, hs, hs),
            "top": QRect(lx + hs, ly - h2, max(1, lw - 2 * hs), hs),
            "bottom": QRect(lx + hs, ly + lh - h2, max(1, lw - 2 * hs), hs),
            "left": QRect(lx - h2, ly + hs, hs, max(1, lh - 2 * hs)),
            "right": QRect(lx + lw - h2, ly + hs, hs, max(1, lh - 2 * hs)),
        }

    def hit_test(self, pos: QPoint):
        s_geo = self.target_screen.geometry()

        # 1. 상단 버튼 체크
        btn_finish, btn_clear, btn_cancel = self._get_top_buttons_rects()
        if btn_finish.contains(pos):
            return "btn_finish", None, None
        if btn_clear.contains(pos):
            return "btn_clear", None, None
        if btn_cancel.contains(pos):
            return "btn_cancel", None, None

        # 2. ROI 박스 체크 (역순: 가장 최근에 등록된 것이 상위)
        for idx in range(len(self.coordinator.selected_rois) - 1, -1, -1):
            gx, gy, gw, gh = self.coordinator.selected_rois[idx]
            global_rect = QRect(gx, gy, gw, gh)
            if not s_geo.intersects(global_rect):
                continue

            local_r = self._get_roi_local_rect(gx, gy, gw, gh)
            badge_r, del_r = self._get_roi_badge_and_del_rects(local_r)

            # (1) 개별 삭제 버튼
            if del_r.contains(pos):
                return "roi_delete", idx, None

            # (2) 8방향 리사이즈 핸들
            handles = self._get_roi_handles(local_r)
            for h_name, h_rect in handles.items():
                if h_rect.contains(pos):
                    return "roi_resize", idx, h_name

            # (3) 박스 내부 또는 배지 바 (이동 영역)
            if local_r.contains(pos) or badge_r.contains(pos):
                return "roi_move", idx, None

        # 3. 아무것도 아니면 빈 공간
        return "empty", None, None

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        btn = event.button()

        hit_type, idx, handle_name = self.hit_test(pos)

        if btn == Qt.MouseButton.LeftButton:
            if hit_type == "btn_finish":
                self.coordinator.finish()
                return
            elif hit_type == "btn_clear":
                self.coordinator.clear_all()
                return
            elif hit_type == "btn_cancel":
                self.coordinator.cancel()
                return
            elif hit_type == "roi_delete":
                self.coordinator.delete_roi(idx)
                return
            elif hit_type == "roi_resize":
                self.is_resizing = True
                self.active_roi_idx = idx
                self.resize_handle = handle_name
                self.press_pos = pos
                self.orig_roi = list(self.coordinator.selected_rois[idx])
                self.coordinator.active_roi_idx = idx
                self.grabMouse()
                self.coordinator.update_all_overlays()
                return
            elif hit_type == "roi_move":
                self.is_moving = True
                self.active_roi_idx = idx
                self.press_pos = pos
                self.orig_roi = list(self.coordinator.selected_rois[idx])
                self.coordinator.active_roi_idx = idx
                self.grabMouse()
                self.coordinator.update_all_overlays()
                return
            elif hit_type == "empty":
                # 빈 공간 드래그 -> 새 ROI 생성
                self.is_selecting = True
                self.local_start = pos
                self.local_current = self.local_start
                self.grabMouse()
                self.update()
                return

        elif btn == Qt.MouseButton.RightButton:
            # 우클릭 시: 박스 위라면 해당 박스 삭제, 빈 공간이라면 최근 영역 취소
            if hit_type in ("roi_move", "roi_resize", "roi_delete"):
                self.coordinator.delete_roi(idx)
            else:
                if not self.coordinator.pop_roi():
                    self.coordinator.cancel()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()

        if self.is_resizing and self.active_roi_idx >= 0:
            dx = pos.x() - self.press_pos.x()
            dy = pos.y() - self.press_pos.y()
            ogx, ogy, ogw, ogh = self.orig_roi
            ngx, ngy, ngw, ngh = ogx, ogy, ogw, ogh

            h = self.resize_handle
            if "left" in h:
                ngx = ogx + dx
                ngw = ogw - dx
            if "right" in h:
                ngw = ogw + dx
            if "top" in h:
                ngy = ogy + dy
                ngh = ogh - dy
            if "bottom" in h:
                ngh = ogh + dy

            # 최소 크기 방어 (40×30)
            if ngw < 40:
                if "left" in h:
                    ngx = ogx + (ogw - 40)
                ngw = 40
            if ngh < 30:
                if "top" in h:
                    ngy = ogy + (ogh - 30)
                ngh = 30

            self.coordinator.selected_rois[self.active_roi_idx] = [ngx, ngy, ngw, ngh]
            self.coordinator.update_all_overlays()
            return

        elif self.is_moving and self.active_roi_idx >= 0:
            dx = pos.x() - self.press_pos.x()
            dy = pos.y() - self.press_pos.y()
            ogx, ogy, ogw, ogh = self.orig_roi
            self.coordinator.selected_rois[self.active_roi_idx][0] = ogx + dx
            self.coordinator.selected_rois[self.active_roi_idx][1] = ogy + dy
            self.coordinator.update_all_overlays()
            return

        elif self.is_selecting:
            self.local_current = pos
            self.update()
            return

        # 드래그 중이 아닐 때 커서 형태 지능형 전환
        hit_type, idx, handle_name = self.hit_test(pos)
        if hit_type in ("btn_finish", "btn_clear", "btn_cancel", "roi_delete"):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif hit_type == "roi_resize":
            if handle_name in ("top-left", "bottom-right"):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif handle_name in ("top-right", "bottom-left"):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif handle_name in ("top", "bottom"):
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif handle_name in ("left", "right"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif hit_type == "roi_move":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_resizing:
                self.is_resizing = False
                self.releaseMouse()
                self.coordinator.update_all_overlays()
                return

            if self.is_moving:
                self.is_moving = False
                self.releaseMouse()
                self.coordinator.update_all_overlays()
                return

            if self.is_selecting:
                self.is_selecting = False
                self.releaseMouse()
                self.local_current = event.position().toPoint()

                if self.local_start and self.local_current:
                    lx = min(self.local_start.x(), self.local_current.x())
                    ly = min(self.local_start.y(), self.local_current.y())
                    lw = abs(self.local_start.x() - self.local_current.x())
                    lh = abs(self.local_start.y() - self.local_current.y())

                    if lw > 25 and lh > 20:
                        s_geo = self.target_screen.geometry()
                        gx = s_geo.x() + lx
                        gy = s_geo.y() + ly
                        self.coordinator.add_roi(gx, gy, lw, lh)

                self.local_start = None
                self.local_current = None
                self.update()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.coordinator.finish()
        elif key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            if self.coordinator.active_roi_idx >= 0:
                self.coordinator.delete_roi(self.coordinator.active_roi_idx)
            else:
                self.coordinator.pop_roi()
        elif key == Qt.Key.Key_Escape:
            self.coordinator.cancel()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. 화면 전체 어두운 반투명 딤드 처리
        painter.fillRect(self.rect(), QColor(0, 0, 0, 125))

        s_geo = self.target_screen.geometry()
        sel_count = len(self.coordinator.selected_rois)

        # 2. 등록된 다중 영역(Multi-ROI) 렌더링
        for idx, (gx, gy, gw, gh) in enumerate(self.coordinator.selected_rois):
            global_rect = QRect(gx, gy, gw, gh)
            if not s_geo.intersects(global_rect):
                continue

            local_r = self._get_roi_local_rect(gx, gy, gw, gh)
            is_active = (idx == self.coordinator.active_roi_idx)

            # (1) 드래그 영역 내부 투명화 (게임 원본 화면 100% 투과)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(local_r, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # (2) 박스 테두리 (활성 ROI: 선명한 네온 그린, 비활성: 시안 블루)
            border_color = QColor(0, 230, 118) if is_active else QColor(0, 210, 255)
            pen = QPen(border_color, 2.5 if is_active else 2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(local_r)

            # (3) 8개 리사이즈 핸들 포인트 그리기 (경계선 위의 작고 깔끔한 8x8 사각형)
            v_handles = self._get_roi_visual_handles(local_r)
            painter.setPen(QPen(border_color, 1.5))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            for vh in v_handles:
                painter.drawRect(vh)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            # (4) 상단 배지 바: [영역 1] 800×200  [✕]
            badge_r, del_r = self._get_roi_badge_and_del_rects(local_r)
            badge_bg = QColor(10, 30, 50, 235) if not is_active else QColor(0, 60, 45, 240)
            badge_border = QColor(0, 210, 255) if not is_active else QColor(0, 230, 118)
            painter.setPen(QPen(badge_border, 1.2))
            painter.setBrush(QBrush(badge_bg))
            painter.drawRoundedRect(badge_r, 4, 4)

            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(badge_r.adjusted(8, 0, -28, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"영역 {idx + 1} ({gw}×{gh})")

            # [✕] 삭제 버튼 배지 (선명한 레드)
            painter.setPen(QPen(QColor(255, 120, 120), 1.0))
            painter.setBrush(QBrush(QColor(220, 50, 50, 240)))
            painter.drawRoundedRect(del_r, 3, 3)
            painter.setPen(Qt.GlobalColor.white)
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(del_r, Qt.AlignmentFlag.AlignCenter, "✕")
            painter.setBrush(Qt.BrushStyle.NoBrush)

        # 3. 신규 드래그 중인 영역 표시 (노란빛 테두리)
        if self.is_selecting and self.local_start and self.local_current:
            lx = min(self.local_start.x(), self.local_current.x())
            ly = min(self.local_start.y(), self.local_current.y())
            lw = abs(self.local_start.x() - self.local_current.x())
            lh = abs(self.local_start.y() - self.local_current.y())
            sel_rect = QRect(lx, ly, lw, lh)

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(sel_rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            pen = QPen(QColor(255, 220, 0), 2.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sel_rect)

            badge_text = f" 영역 {sel_count + 1} 생성 중: {lw}×{lh} "
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            badge_y = max(0, ly - 26) if ly >= 26 else ly + lh + 4
            drag_badge_r = QRect(lx, badge_y, 190, 24)
            painter.setPen(QPen(QColor(255, 215, 0), 1.2))
            painter.setBrush(QBrush(QColor(230, 130, 0, 240)))
            painter.drawRoundedRect(drag_badge_r, 4, 4)
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(drag_badge_r, Qt.AlignmentFlag.AlignCenter, badge_text)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        # 4. 상단 버튼 툴바
        btn_finish, btn_clear, btn_cancel = self._get_top_buttons_rects()

        # (1) [선택 완료] 버튼 (고급스러운 딥 에메랄드)
        finish_bg = QColor(27, 94, 32, 240)
        finish_border = QColor(102, 187, 106)
        painter.setPen(QPen(finish_border, 1.8))
        painter.setBrush(QBrush(finish_bg))
        painter.drawRoundedRect(btn_finish, 6, 6)
        painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(btn_finish, Qt.AlignmentFlag.AlignCenter, f"✔ 설정 완료 ({sel_count}개 / Enter)")

        # (2) [전체 초기화] 버튼 (고급스러운 딥 크림슨)
        clear_bg = QColor(136, 14, 79, 240)
        clear_border = QColor(239, 83, 80)
        painter.setPen(QPen(clear_border, 1.5))
        painter.setBrush(QBrush(clear_bg))
        painter.drawRoundedRect(btn_clear, 6, 6)
        painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(btn_clear, Qt.AlignmentFlag.AlignCenter, "⟲ 전체 초기화")

        # (3) [닫기] 버튼 (고급스러운 딥 슬레이트 그레이)
        cancel_bg = QColor(38, 50, 56, 240)
        cancel_border = QColor(144, 164, 174)
        painter.setPen(QPen(cancel_border, 1.5))
        painter.setBrush(QBrush(cancel_bg))
        painter.drawRoundedRect(btn_cancel, 6, 6)
        painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(btn_cancel, Qt.AlignmentFlag.AlignCenter, "✕ 닫기 (ESC)")
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # (4) 하단 도움말 안내문 (선택된 모니터 번호 및 실제 해상도 명시)
        dpr = self.target_screen.devicePixelRatio()
        phys_w = int(round(self.target_screen.geometry().width() * dpr))
        phys_h = int(round(self.target_screen.geometry().height() * dpr))
        guide_text = (
            f"🖥️ 모니터 {self.screen_idx + 1} ({phys_w}×{phys_h})  |  "
            "이동: 박스 드래그  |  크기 조절: 테두리·모서리 핸들 드래그  |  "
            "추가: 빈 공간 드래그  |  삭제: [✕] 클릭 또는 Del 키"
        )
        painter.setFont(QFont("Malgun Gothic", 10))
        painter.setPen(QColor(225, 225, 225, 230))
        painter.drawText(
            self.rect().adjusted(0, 56, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            guide_text
        )


class ROISelectorWidget(QObject):
    """
    멀티 모니터 & 다중 영역 인터랙티브 코디네이터.
    - 대상 모니터(target_display_index)가 지정된 경우 다른 모니터를 가리지 않고 해당 모니터에만 선택창 표시
    """
    roi_selected_signal = pyqtSignal(int, int, int, int)  # 단일 영역 하위 호환: global x, y, w, h
    roi_list_selected_signal = pyqtSignal(list)            # 다중 영역: [[x, y, w, h], ...]

    def __init__(self, config=None, current_rois=None, parent=None, callback=None, selected_display_index=None):
        super().__init__(parent)
        if isinstance(config, list):
            # Positional usage: ROISelector(current_rois, callback=..., selected_display_index=...)
            current_rois = config
            config = {}
        self.config = config or {}
        if selected_display_index is not None and selected_display_index >= 0:
            self.config["target_display_index"] = selected_display_index

        if current_rois and isinstance(current_rois[0], int):
            self.current_rois = [current_rois]
        else:
            self.current_rois = current_rois or []

        self.callback = callback
        if self.callback:
            self.roi_list_selected_signal.connect(self.callback)

        self.selected_rois = []
        self.active_roi_idx = -1
        self.overlays = []

    def show(self):
        self.show_fullscreen_selection()

    def show_fullscreen_selection(self):
        screens = QApplication.screens()
        if not screens:
            return
        self.overlays.clear()

        # 1. 활성화할 대상 모니터 지능형 결정 (다른 모니터 침범 원천 차단!)
        target_idx = self.config.get("target_display_index", -1)
        target_screens = []

        if 0 <= target_idx < len(screens):
            # 사용자가 특정 모니터를 명시적으로 고정한 경우: 오직 그 모니터에만 활성화!
            target_screens = [(target_idx, screens[target_idx])]
        else:
            # 스마트 자동:
            # 기존 등록된 ROI가 있다면 해당 ROI가 위치한 모니터 우선
            found_screen = None
            if self.current_rois:
                first = self.current_rois[0]
                if len(first) == 4:
                    rx, ry, rw, rh = first
                    center = QPoint(rx + rw // 2, ry + rh // 2)
                    for idx, s in enumerate(screens):
                        if s.geometry().contains(center) or s.geometry().intersects(QRect(rx, ry, rw, rh)):
                            found_screen = (idx, s)
                            break

            if not found_screen:
                # 커서 위치 모니터
                cursor_pos = QCursor.pos()
                app = QApplication.instance()
                s = app.screenAt(cursor_pos) or app.primaryScreen() or screens[0]
                idx = screens.index(s) if s in screens else 0
                found_screen = (idx, s)

            target_screens = [found_screen]

        # 2. 현재 활성화된 모니터에 속한 유효 ROI만 로드 (다른 모니터의 유령 영역 유입 원천 차단!)
        active_screen = target_screens[0][1]
        s_geo = active_screen.geometry()
        self.selected_rois = [
            list(r) for r in self.current_rois
            if len(r) == 4 and r[2] > 20 and r[3] > 20 and s_geo.intersects(QRect(r[0], r[1], r[2], r[3]))
        ]
        self.active_roi_idx = len(self.selected_rois) - 1 if self.selected_rois else -1

        for idx, screen in target_screens:
            overlay = SingleScreenOverlay(
                screen=screen,
                screen_idx=idx,
                coordinator=self,
                current_rois=self.current_rois
            )
            self.overlays.append(overlay)
            overlay.show()
            overlay.raise_()
            overlay.activateWindow()

    def add_roi(self, gx: int, gy: int, gw: int, gh: int):
        self.selected_rois.append([gx, gy, gw, gh])
        self.active_roi_idx = len(self.selected_rois) - 1
        print(f"[ROISelector] 영역 {len(self.selected_rois)} 추가됨: X={gx}, Y={gy}, {gw}x{gh}px")
        self.update_all_overlays()

    def delete_roi(self, idx: int) -> bool:
        if 0 <= idx < len(self.selected_rois):
            removed = self.selected_rois.pop(idx)
            self.active_roi_idx = max(-1, len(self.selected_rois) - 1)
            print(f"[ROISelector] 영역 {idx + 1} 삭제됨: {removed}")
            self.update_all_overlays()
            return True
        return False

    def pop_roi(self) -> bool:
        if self.selected_rois:
            removed = self.selected_rois.pop()
            self.active_roi_idx = max(-1, len(self.selected_rois) - 1)
            print(f"[ROISelector] 최근 영역 취소됨: {removed}")
            self.update_all_overlays()
            return True
        return False

    def clear_all(self):
        self.selected_rois.clear()
        self.active_roi_idx = -1
        print("[ROISelector] 모든 영역 초기화됨.")
        self.update_all_overlays()

    def update_all_overlays(self):
        for o in self.overlays:
            try:
                o.update()
            except Exception:
                pass

    def finish(self):
        print(f"[ROISelector] 총 {len(self.selected_rois)}개 영역 설정 완료: {self.selected_rois}")
        self.roi_list_selected_signal.emit(self.selected_rois)
        if self.selected_rois:
            first = self.selected_rois[0]
            self.roi_selected_signal.emit(first[0], first[1], first[2], first[3])
        self.close_all()

    def cancel(self):
        self.close_all()

    def close_all(self):
        for o in self.overlays:
            try:
                o.close()
                o.deleteLater()
            except Exception:
                pass
        self.overlays.clear()

# 하위 호환성 별칭
ROISelector = ROISelectorWidget
