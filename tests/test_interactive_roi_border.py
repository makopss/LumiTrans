import unittest
import sys
from PyQt6.QtCore import Qt, QPoint, QRect, QPointF
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QMouseEvent
from src.config import DEFAULT_CONFIG
from src.roi_border_overlay import (
    SingleROIBorderWidget, ROIBorderManager,
    EDGE_NONE, EDGE_LEFT, EDGE_RIGHT, EDGE_TOP, EDGE_BOTTOM,
    EDGE_MARGIN, CORNER_MARGIN
)

class TestInteractiveROIBorder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_edge_detection(self):
        roi = [100, 100, 400, 300]
        w = SingleROIBorderWidget(roi, roi_idx=0)
        
        # 1. 뱃지 영역 판정
        badge_rect = w._get_badge_rect()
        badge_pos = badge_rect.center()
        self.assertEqual(w._get_resize_edge(badge_pos), EDGE_NONE)

        # 2. 4개 모서리 판정
        self.assertEqual(w._get_resize_edge(QPoint(5, 5)), EDGE_LEFT | EDGE_TOP)
        self.assertEqual(w._get_resize_edge(QPoint(395, 5)), EDGE_RIGHT | EDGE_TOP)
        self.assertEqual(w._get_resize_edge(QPoint(5, 295)), EDGE_LEFT | EDGE_BOTTOM)
        self.assertEqual(w._get_resize_edge(QPoint(395, 295)), EDGE_RIGHT | EDGE_BOTTOM)

        # 3. 4개 변 판정
        self.assertEqual(w._get_resize_edge(QPoint(200, 3)), EDGE_TOP)
        self.assertEqual(w._get_resize_edge(QPoint(200, 297)), EDGE_BOTTOM)
        self.assertEqual(w._get_resize_edge(QPoint(3, 150)), EDGE_LEFT)
        self.assertEqual(w._get_resize_edge(QPoint(397, 150)), EDGE_RIGHT)

        # 4. 중앙 영역 (내부 관통 구멍) 판정
        self.assertEqual(w._get_resize_edge(QPoint(200, 150)), EDGE_NONE)
        w.close()

    def test_drag_move_logic(self):
        roi = [100, 100, 400, 300]
        adjusted_history = []
        def on_adj(idx, new_roi, is_final):
            adjusted_history.append((idx, list(new_roi), is_final))

        w = SingleROIBorderWidget(roi, roi_idx=0, on_adjusted=on_adj)
        badge_pos = w._get_badge_rect().center()
        badge_global = w.mapToGlobal(badge_pos)

        # 마우스 누름
        press_ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(badge_pos),
            QPointF(badge_global),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        w.mousePressEvent(press_ev)
        self.assertTrue(w.is_moving)

        # 마우스 드래그 (X+50, Y+30 이동)
        move_global = badge_global + QPoint(50, 30)
        move_ev = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(badge_pos + QPoint(50, 30)),
            QPointF(move_global),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        w.mouseMoveEvent(move_ev)
        self.assertEqual(w.x(), 150)
        self.assertEqual(w.y(), 130)
        self.assertEqual(adjusted_history[-1], (0, [150, 130, 400, 300], False))

        # 마우스 놓기
        rel_ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(badge_pos + QPoint(50, 30)),
            QPointF(move_global),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier
        )
        w.mouseReleaseEvent(rel_ev)
        self.assertFalse(w.is_moving)
        self.assertEqual(adjusted_history[-1], (0, [150, 130, 400, 300], True))
        w.close()

    def test_drag_resize_logic(self):
        roi = [100, 100, 400, 300]
        adjusted_history = []
        def on_adj(idx, new_roi, is_final):
            adjusted_history.append((idx, list(new_roi), is_final))

        w = SingleROIBorderWidget(roi, roi_idx=0, on_adjusted=on_adj)
        br_pos = QPoint(395, 295)
        br_global = w.mapToGlobal(br_pos)

        # 마우스 누름 (우하단 모서리)
        press_ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(br_pos),
            QPointF(br_global),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        w.mousePressEvent(press_ev)
        self.assertTrue(w.is_resizing)
        self.assertEqual(w.active_resize_edge, EDGE_RIGHT | EDGE_BOTTOM)

        # 마우스 드래그 (가로 +40, 세로 +20 확장)
        move_global = br_global + QPoint(40, 20)
        move_ev = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(br_pos + QPoint(40, 20)),
            QPointF(move_global),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        w.mouseMoveEvent(move_ev)
        self.assertEqual(w.width(), 440)
        self.assertEqual(w.height(), 320)
        self.assertEqual(adjusted_history[-1], (0, [100, 100, 440, 320], False))

        # 마우스 놓기
        rel_ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(br_pos + QPoint(40, 20)),
            QPointF(move_global),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier
        )
        w.mouseReleaseEvent(rel_ev)
        self.assertFalse(w.is_resizing)
        self.assertEqual(adjusted_history[-1], (0, [100, 100, 440, 320], True))
        w.close()

    def test_roi_border_manager_sync(self):
        cfg = DEFAULT_CONFIG.copy()
        cfg["screen_rois"] = [[100, 100, 300, 200], [500, 200, 400, 250]]
        cfg["screen_show_roi_border"] = True

        called_changes = []
        mgr = ROIBorderManager(cfg, on_rois_changed=lambda rois, is_final: called_changes.append((list(rois), is_final)))
        self.assertEqual(len(mgr.widgets), 2)

        # 1번 위젯 조정 시뮬레이션
        w2 = mgr.widgets[1]
        w2.roi = [520, 210, 450, 280]
        w2.on_adjusted(1, w2.roi, True)

        self.assertEqual(cfg["screen_rois"][1], [520, 210, 450, 280])
        self.assertEqual(called_changes[-1][0][1], [520, 210, 450, 280])
        self.assertTrue(called_changes[-1][1])
        mgr.close()

if __name__ == "__main__":
    unittest.main()
