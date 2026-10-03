"""Frameless overlay window geometry helpers.

Windows Aero Snap and per-monitor DPI changes can suddenly maximize, dock to a
corner, or inflate a small subtitle overlay. These helpers lock the user size
while the window is being dragged and restore it after screen changes.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, QTimer, Qt
from PyQt6.QtGui import QCursor, QFontMetrics, QGuiApplication
from PyQt6.QtWidgets import QComboBox, QPushButton


class OverlayGeometryMixin:
    """Mixin for frameless always-on-top overlay widgets."""

    def _init_geometry_lock(self):
        self._size_locked = False
        self._locked_w = 0
        self._locked_h = 0
        self._screen_changed_bound = False
        self._enforcing_size = False
        self._restore_scheduled = False
        self._handling_state = False
        self._handling_screen = False
        self._geometry_ready = False
        self._drag_hotspot = None
        self._applying_text_height = False

    def _bind_screen_changed(self):
        handle = self.windowHandle()
        if not handle:
            return
        try:
            handle.screenChanged.disconnect(self._handle_screen_changed)
        except Exception:
            pass
        self._geometry_ready = True
        handle.screenChanged.connect(self._handle_screen_changed)
        self._screen_changed_bound = True

    def _current_user_size(self):
        if hasattr(self, "base_geometry") and len(self.base_geometry) == 4:
            w, h = int(self.base_geometry[2]), int(self.base_geometry[3])
            if w > 0 and h > 0 and not self._looks_like_snap_size(w, h):
                return w, h
        return max(self.minimumWidth(), self.width()), max(self.minimumHeight(), self.height())

    def _begin_user_move(self):
        w, h = self._current_user_size()
        self._locked_w = max(self.minimumWidth(), w)
        self._locked_h = max(self.minimumHeight(), h)
        self._size_locked = True
        self._capture_drag_hotspot()

    def _capture_drag_hotspot(self):
        self._drag_hotspot = QCursor.pos() - self.pos()

    def _move_following_cursor(self):
        hotspot = getattr(self, "_drag_hotspot", None)
        if hotspot is None:
            return
        self.move(QCursor.pos() - hotspot)

    @staticmethod
    def _normalize_bg_opacity(value, default=0.75) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return default
        if v > 1.0:
            v = v / 100.0
        return max(0.0, min(1.0, v))

    def _interactive_chrome_at(self, pos: QPoint) -> bool:
        child = self.childAt(pos)
        while child is not None and child is not self:
            if isinstance(child, (QPushButton, QComboBox)):
                return True
            child = child.parentWidget()
        return False

    def _begin_user_resize(self):
        self._size_locked = False

    def _end_user_interaction(self):
        if self._size_locked:
            self._enforce_locked_size()
        self._size_locked = False
        self._drag_hotspot = None

    def _rebase_drag_origin(self):
        """Reset drag hotspot after a screen/DPI jump so the window does not teleport."""
        if not getattr(self, "is_moving", False):
            return
        self._capture_drag_hotspot()

    def _looks_like_snap_size(self, w: int, h: int) -> bool:
        """True when width/height match a full, half, or quarter screen dock."""
        if w < 380 or h < 220:
            return False
        screen = None
        try:
            screen = self.screen()
        except Exception:
            screen = None
        if screen is None:
            app = QGuiApplication.instance()
            if app:
                try:
                    screen = app.screenAt(self.pos()) or app.primaryScreen()
                except Exception:
                    screen = None
        if screen is None:
            return False

        rects = (screen.availableGeometry(), screen.geometry())
        candidates = []
        for geo in rects:
            candidates.extend((
                (geo.width(), geo.height()),
                (geo.width() // 2, geo.height()),
                (geo.width(), geo.height() // 2),
                (geo.width() // 2, geo.height() // 2),
            ))
        for cw, ch in candidates:
            if abs(w - cw) <= 48 and abs(h - ch) <= 48:
                return True
        if hasattr(self, "base_geometry") and len(self.base_geometry) == 4:
            bw, bh = int(self.base_geometry[2]), int(self.base_geometry[3])
            if bw >= 200 and bh >= 40:
                if w > bw * 1.45 or h > bh * 1.45:
                    if w >= 500 or h >= 280:
                        return True
        return False

    def _schedule_size_restore(self, callback):
        if getattr(self, "_restore_scheduled", False) or getattr(self, "_enforcing_size", False):
            return
        self._restore_scheduled = True

        def _run():
            self._restore_scheduled = False
            try:
                callback()
            except Exception:
                pass

        QTimer.singleShot(0, _run)

    def _reject_unwanted_resize(self) -> bool:
        """True when a resize came from snap/DPI/move and must not be saved."""
        if getattr(self, "_enforcing_size", False):
            return True
        if getattr(self, "is_moving", False) or getattr(self, "_size_locked", False):
            w = int(getattr(self, "_locked_w", 0) or 0)
            h = int(getattr(self, "_locked_h", 0) or 0)
            if w > 0 and h > 0 and (abs(self.width() - w) > 1 or abs(self.height() - h) > 1):
                self._schedule_size_restore(self._enforce_locked_size)
            return True
        if not getattr(self, "_geometry_ready", False):
            return False
        if not getattr(self, "is_auto_resizing", False) and getattr(self, "active_resize_edge", 0) == 0:
            if self._looks_like_snap_size(self.width(), self.height()):
                self._schedule_size_restore(self._restore_user_size)
                return True
        return False

    def _force_size(self, w: int, h: int) -> bool:
        if getattr(self, "_enforcing_size", False):
            return False
        w = max(self.minimumWidth(), int(w))
        h = max(self.minimumHeight(), int(h))
        if w <= 0 or h <= 0:
            return False
        if abs(self.width() - w) <= 16 and abs(self.height() - h) <= 24:
            return False
        layout = self.layout()
        if layout is not None:
            try:
                from PyQt6.QtWidgets import QLayout
                layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            except Exception:
                pass
        self._enforcing_size = True
        self.is_auto_resizing = True
        try:
            geo = self.geometry()
            self.setGeometry(geo.x(), geo.y(), w, h)
        except Exception:
            return False
        finally:
            self.is_auto_resizing = False
            self._enforcing_size = False
        return abs(self.width() - w) <= 2 and abs(self.height() - h) <= 2

    def _enforce_locked_size(self) -> bool:
        if getattr(self, "_enforcing_size", False):
            return False
        if not getattr(self, "_size_locked", False):
            return False
        return self._force_size(self._locked_w, self._locked_h)

    def _restore_user_size(self) -> bool:
        if getattr(self, "_enforcing_size", False):
            return False
        w, h = self._current_user_size()
        if getattr(self, "_size_locked", False) and self._locked_w > 0 and self._locked_h > 0:
            w, h = self._locked_w, self._locked_h
        return self._force_size(w, h)

    def _handle_screen_changed(self, new_screen):
        """Keep the user size after a monitor/DPI change; do not save the jump."""
        if not new_screen or getattr(self, "_handling_screen", False):
            return
        if not getattr(self, "_geometry_ready", False):
            return
        self._handling_screen = True
        try:
            if getattr(self, "is_moving", False):
                return
            self._schedule_size_restore(self._restore_user_size)
        finally:
            self._handling_screen = False

    def _undo_maximized_state(self):
        if getattr(self, "_handling_state", False):
            return
        self._handling_state = True
        try:
            if self.windowState() & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen):
                self.setWindowState(Qt.WindowState.WindowNoState)
            self._restore_user_size()
        except Exception:
            pass
        finally:
            self._handling_state = False

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() != QEvent.Type.WindowStateChange:
            return
        if getattr(self, "_handling_state", False):
            return
        if self.windowState() & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen):
            QTimer.singleShot(0, self._undo_maximized_state)

    def moveEvent(self, event):
        super().moveEvent(event)

    def _set_header_chrome_opacity(self, value: float):
        if not hasattr(self, "header_opacity_effect"):
            return
        value = max(0.0, min(1.0, float(value)))
        self.header_opacity_effect.setOpacity(value)
        # QGraphicsOpacityEffect swallows mouse hits below 1.0, so disable it while clicking controls.
        self.header_opacity_effect.setEnabled(value < 0.99)

    def _two_line_label_min_height(self, label, extra=18) -> int:
        """영문/한글 각각 두 줄이 잘리지 않을 라벨 최소 높이."""
        if label is None:
            return 0
        try:
            label.ensurePolished()
        except Exception:
            pass
        fm = label.fontMetrics() if hasattr(label, "fontMetrics") else QFontMetrics(label.font())
        line = max(fm.lineSpacing(), fm.height() + max(2, fm.descent()))
        margins = label.contentsMargins()
        pad = margins.top() + margins.bottom()
        return int(line * 2 + fm.descent() + extra + pad)

    def _preferred_two_line_overlay_height(self) -> int:
        """헤더+영문 2줄+한글 2줄+그립이 들어갈 자막창 높이."""
        layout = self.layout()
        margins = 16
        spacing = 4
        if layout is not None:
            cm = layout.contentsMargins()
            margins = cm.top() + cm.bottom()
            spacing = max(0, layout.spacing())
        header_h = self.header_widget.height() if hasattr(self, "header_widget") else 32
        show_orig = bool(getattr(self, "config", {}).get("show_original", True))
        orig_h = 0
        if show_orig and hasattr(self, "label_original"):
            orig_h = self._two_line_label_min_height(self.label_original, extra=16)
        trans_h = 0
        if hasattr(self, "label_translated"):
            trans_h = self._two_line_label_min_height(self.label_translated, extra=20)
        grip_h = 14
        n_gaps = 3 if orig_h else 2
        return int(header_h + orig_h + trans_h + grip_h + margins + spacing * n_gaps)

    def _apply_two_line_overlay_height(self, follow_font=False):
        """폰트 크기에 맞춰 자막창 높이를 두 줄 여유로 맞춘다. 잘리지 않도록 부족하면 키운다."""
        if getattr(self, "_applying_text_height", False):
            return
        if getattr(self, "is_moving", False) or getattr(self, "_size_locked", False):
            return
        if getattr(self, "active_resize_edge", 0):
            return
        if not hasattr(self, "label_translated"):
            return

        self._applying_text_height = True
        try:
            show_orig = bool(getattr(self, "config", {}).get("show_original", True))
            if hasattr(self, "label_original"):
                en_h = self._two_line_label_min_height(self.label_original, extra=16)
                self.label_original.setMinimumHeight(en_h if show_orig else 0)
            ko_h = self._two_line_label_min_height(self.label_translated, extra=20)
            self.label_translated.setMinimumHeight(ko_h)

            preferred = max(120, self._preferred_two_line_overlay_height())
            self.setMinimumSize(max(250, self.minimumWidth()), preferred)

            geo = self.geometry()
            width = geo.width() if geo.width() > 0 else (
                self.base_geometry[2] if getattr(self, "base_geometry", None) and len(self.base_geometry) == 4 else 900
            )
            if follow_font:
                new_h = preferred
            else:
                new_h = max(preferred, geo.height() if geo.height() > 0 else preferred)
            if abs(geo.height() - new_h) < 2 and geo.height() >= preferred:
                if hasattr(self, "base_geometry") and len(self.base_geometry) == 4:
                    self.base_geometry[3] = max(self.base_geometry[3], new_h)
                return

            new_y = geo.y()
            try:
                screen = self.screen()
                if screen is not None:
                    avail = screen.availableGeometry()
                    bottom = avail.y() + avail.height()
                    if new_y + new_h > bottom - 4:
                        new_y = max(avail.y() + 4, bottom - new_h - 4)
            except Exception:
                pass

            self.is_auto_resizing = True
            try:
                self.setGeometry(geo.x(), new_y, max(self.minimumWidth(), width), new_h)
                if hasattr(self, "base_geometry"):
                    self.base_geometry = [geo.x(), new_y, max(self.minimumWidth(), width), new_h]
            finally:
                self.is_auto_resizing = False
        finally:
            self._applying_text_height = False
