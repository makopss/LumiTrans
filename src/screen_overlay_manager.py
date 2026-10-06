from PyQt6.QtCore import QObject, QPoint, QRect, QTimer
from PyQt6.QtWidgets import QApplication
from src.screen_overlay import ScreenSubtitleOverlay
from src.i18n import tr

class ScreenOverlayManager(QObject):
    """
    다중 영역(Multi-ROI)에 따른 독립 자막창(ScreenSubtitleOverlay)들의 생명주기와
    신호 라우팅을 총괄하는 관리자 클래스.
    - N개 영역 지정 시 N개의 독립 오버레이 창 생성
    - 각 영역 번역 결과(roi_idx)를 해당 자막창으로 1:1 라우팅
    - 각 자막창이 자신의 ROI에 고정 밀착되어 화면 점프 현상 원천 차단
    - 폰트 크기, 투명도, 클린 텍스트 모드 등 설정 일괄 동기화
    """
    def __init__(self, config, on_config_change=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.on_config_change = on_config_change
        self.overlays = []
        self.ext_handlers = {}
        self._paused = False
        self.sync_rois()

    def sync_rois(self):
        """설정된 ROI 개수에 맞추어 오버레이 인스턴스 동기화 및 밀착 배치"""
        was_visible = self.is_visible()
        rois = [r for r in self.config.get("screen_rois", []) if len(r) == 4 and r[2] > 20 and r[3] > 20]
        if not rois:
            single = self.config.get("screen_roi")
            if single and len(single) == 4 and single[2] > 20 and single[3] > 20:
                rois = [single]

        count = max(1, len(rois))

        # 잉여 오버레이 숨김 및 제거
        while len(self.overlays) > count:
            extra = self.overlays.pop()
            extra.hide()
            extra.deleteLater()

        # 부족하면 새로 생성 (count개 만큼만)
        while len(self.overlays) < count:
            idx = len(self.overlays)
            overlay = ScreenSubtitleOverlay(self.config, on_config_change=self._on_sub_config_changed, roi_idx=idx)
            self._apply_handlers_to(overlay)
            overlay.set_paused_state(self._paused)
            self.overlays.append(overlay)

        is_multi = len(self.overlays) > 1
        is_snap = self.config.get("screen_snap_to_roi", False)
        geo_map = self.config.get("screen_overlay_geometries", {})

        for idx, overlay in enumerate(self.overlays):
            overlay.assigned_roi_idx = idx
            overlay.is_multi = is_multi
            title = f"👁️ {tr('screen_translation')} #{idx + 1}" if is_multi else f"👁️ {tr('screen_translation')}"
            overlay.title_label.setText(title)
            if idx < len(rois):
                overlay.assigned_roi = rois[idx]
            else:
                overlay.assigned_roi = None

            target_screen = self._target_screen(overlay.assigned_roi)

            idx_key = str(idx)
            has_saved_geo = isinstance(geo_map, dict) and idx_key in geo_map and len(geo_map[idx_key]) == 4
            if has_saved_geo and target_screen:
                geo = geo_map[idx_key]
                if not target_screen.geometry().contains(QRect(*map(int, geo)).center()):
                    # 과거 모니터의 좌표를 현재 ROI/선택 모니터에 재사용하지 않는다.
                    geo_map.pop(idx_key, None)
                    has_saved_geo = False
                    overlay.is_user_positioned = False

            # 다중 영역 밀착 배치 또는 개별 좌표 적용
            if is_snap and overlay.assigned_roi and not getattr(overlay, 'is_user_positioned', False):
                overlay.snap_to_roi(overlay.assigned_roi)
            elif has_saved_geo:
                geo = geo_map[idx_key]
                overlay.setGeometry(geo[0], geo[1], geo[2], geo[3])
                overlay.base_geometry = list(geo)
                overlay.is_user_positioned = True
            elif idx > 0 and not getattr(overlay, 'is_user_positioned', False):
                if overlay.assigned_roi:
                    overlay.snap_to_roi(overlay.assigned_roi)
                else:
                    prev_geo = self.overlays[idx - 1].geometry()
                    new_y = prev_geo.bottom() + 15
                    overlay.setGeometry(prev_geo.x(), new_y, prev_geo.width(), prev_geo.height())
                    overlay.base_geometry = [prev_geo.x(), new_y, prev_geo.width(), prev_geo.height()]

            if target_screen and not target_screen.geometry().contains(overlay.geometry().center()):
                self._move_to_target_screen(overlay, target_screen)
                if isinstance(geo_map, dict):
                    geo_map.pop(idx_key, None)

        # 다중 오버레이 간 겹침(Collision) 방지: 수동 배치하지 않은 오버레이끼리 겹칠 경우 아래로 오프셋
        for idx in range(1, len(self.overlays)):
            cur_o = self.overlays[idx]
            if not getattr(cur_o, 'is_user_positioned', False):
                for prev_idx in range(idx):
                    prev_o = self.overlays[prev_idx]
                    if cur_o.geometry().intersects(prev_o.geometry()):
                        cg = cur_o.geometry()
                        pg = prev_o.geometry()
                        new_y = pg.bottom() + 15
                        cur_o.move(cg.x(), new_y)
                        cur_o.base_geometry = [cg.x(), new_y, cg.width(), cg.height()]

            target_screen = self._target_screen(cur_o.assigned_roi)
            if target_screen and not target_screen.geometry().contains(cur_o.geometry().center()):
                self._move_to_target_screen(cur_o, target_screen)

        if was_visible and self.config.get("screen_overlay_visible", True):
            for overlay in self.overlays:
                if not overlay.isVisible():
                    screen = self._target_screen(overlay.assigned_roi)
                    overlay.is_auto_resizing = True
                    try:
                        if screen:
                            overlay.winId()
                            handle = overlay.windowHandle()
                            if handle and handle.screen() is not screen:
                                handle.setScreen(screen)
                        overlay.show()
                    finally:
                        overlay.is_auto_resizing = False

    def _target_screen(self, roi=None):
        app = QApplication.instance()
        if not app:
            return None
        screens = app.screens()
        if roi and len(roi) == 4:
            x, y, width, height = map(int, roi)
            found = app.screenAt(QPoint(x + width // 2, y + height // 2))
            if found:
                return found
        selected = self.config.get("screen_display_index", -1)
        if isinstance(selected, int) and 0 <= selected < len(screens):
            return screens[selected]
        return app.primaryScreen() or (screens[0] if screens else None)

    @staticmethod
    def _move_to_target_screen(overlay, screen):
        roi = overlay.assigned_roi
        if roi and screen.geometry().contains(QPoint(int(roi[0]) + int(roi[2]) // 2,
                                                    int(roi[1]) + int(roi[3]) // 2)):
            overlay.is_user_positioned = False
            overlay.snap_to_roi(roi)
            geo = overlay.geometry()
            overlay.base_geometry = [geo.x(), geo.y(), geo.width(), geo.height()]
            return
        bounds = screen.availableGeometry()
        geo = overlay.geometry()
        width = min(max(250, geo.width()), max(250, bounds.width() - 30))
        height = min(max(120, geo.height()), max(120, bounds.height() - 30))
        x = bounds.x() + (bounds.width() - width) // 2
        y = bounds.y() + bounds.height() - height - 15
        overlay.is_auto_resizing = True
        try:
            overlay.setGeometry(x, y, width, height)
            overlay.base_geometry = [x, y, width, height]
            overlay.is_user_positioned = False
        finally:
            overlay.is_auto_resizing = False

    def _on_sub_config_changed(self, cfg, source_overlay=None):
        # 모든 오버레이 인스턴스에 설정 동기화 반영 (위치/지오메트리 덮어쓰기 방지)
        for o in self.overlays:
            if o is source_overlay:
                continue
            o._apply_config(apply_geometry=False)
        if self.on_config_change:
            self.on_config_change(cfg)

    def set_external_handlers(self, on_toggle_pause=None, on_trigger_roi=None,
                              on_trigger_instant=None, on_trigger_inplace=None, on_open_settings=None,
                              on_sync_snap=None, on_visibility_change=None,
                              on_sync_font=None, on_sync_opacity=None,
                              on_toggle_border=None, on_sync_click_through=None,
                              on_sync_clean_text=None, on_sync_show_speaker=None):
        self.ext_handlers = {
            "on_toggle_pause": on_toggle_pause,
            "on_trigger_roi": on_trigger_roi,
            "on_trigger_instant": on_trigger_instant,
            "on_trigger_inplace": on_trigger_inplace,
            "on_open_settings": on_open_settings,
            "on_sync_snap": on_sync_snap,
            "on_visibility_change": on_visibility_change,
            "on_sync_font": on_sync_font,
            "on_sync_opacity": on_sync_opacity,
            "on_toggle_border": on_toggle_border,
            "on_sync_click_through": on_sync_click_through,
            "on_sync_clean_text": on_sync_clean_text,
            "on_sync_show_speaker": on_sync_show_speaker
        }
        for o in self.overlays:
            self._apply_handlers_to(o)

    def _apply_handlers_to(self, overlay):
        overlay.set_external_handlers(
            on_toggle_pause=self.ext_handlers.get("on_toggle_pause"),
            on_trigger_roi=self.ext_handlers.get("on_trigger_roi"),
            on_trigger_instant=self.ext_handlers.get("on_trigger_instant"),
            on_trigger_inplace=self.ext_handlers.get("on_trigger_inplace"),
            on_open_settings=self.ext_handlers.get("on_open_settings"),
            on_sync_snap=self.ext_handlers.get("on_sync_snap"),
            on_visibility_change=self._notify_visibility_change,
            on_sync_font=self.ext_handlers.get("on_sync_font"),
            on_sync_opacity=self.ext_handlers.get("on_sync_opacity"),
            on_toggle_border=self.ext_handlers.get("on_toggle_border"),
            on_sync_click_through=self.ext_handlers.get("on_sync_click_through"),
            on_sync_clean_text=self.ext_handlers.get("on_sync_clean_text"),
            on_sync_show_speaker=self.ext_handlers.get("on_sync_show_speaker")
        )

    def update_inplace_hotkey_tooltip(self, hotkey_str: str):
        for o in self.overlays:
            if hasattr(o, 'update_inplace_hotkey_tooltip'):
                o.update_inplace_hotkey_tooltip(hotkey_str)

    def _notify_visibility_change(self, _visible):
        handler = self.ext_handlers.get("on_visibility_change")
        if handler:
            QTimer.singleShot(0, lambda: handler(self.is_visible()))

    def set_paused_state(self, is_paused: bool):
        self._paused = bool(is_paused)
        for o in self.overlays:
            o.set_paused_state(is_paused)

    def set_click_through(self, enabled: bool):
        for o in self.overlays:
            o.set_click_through(enabled)

    def display_subtitle(self, orig: str, trans: str, engine: str = "", roi_idx: int = 0):
        """특정 ROI 인덱스에 해당하는 자막창으로 직배송 라우팅"""
        if getattr(self, "_paused", False) and not str(engine).startswith("즉시·"):
            return
        if 0 <= roi_idx < len(self.overlays):
            target = self.overlays[roi_idx]
        else:
            return

        rois = self.config.get("screen_rois", [])
        target_roi = rois[roi_idx] if (0 <= roi_idx < len(rois)) else getattr(target, 'assigned_roi', None)
        target_screen = self._target_screen(target_roi)
        if target_screen and not target_screen.geometry().contains(target.geometry().center()):
            self._move_to_target_screen(target, target_screen)
        target.display_subtitle(orig, trans, engine, target_roi=target_roi)
        if self.config.get("screen_overlay_visible", True) and not target.isVisible():
            target.is_auto_resizing = True
            try:
                if target_screen:
                    target.winId()
                    handle = target.windowHandle()
                    if handle and handle.screen() is not target_screen:
                        handle.setScreen(target_screen)
                target.show()
            finally:
                target.is_auto_resizing = False
        if target_screen and not target_screen.geometry().contains(target.geometry().center()):
            self._move_to_target_screen(target, target_screen)

    @staticmethod
    def _is_paused_status_text(status: str) -> bool:
        if not status:
            return False
        clean = str(status).strip()
        paused_variants = {
            "일시정지됨", "일시정지", "Paused", "一時停止中", "一時停止", "已暂停",
            "En pausa", "En pause", "Pausiert", "Em pausa", "На паузе", "Пауза",
            "In pausa", "Đang tạm dừng", "หยุดชั่วคราว", "Dijeda", "متوقف مؤقتًا", "متوقف", "रुका हुआ"
        }
        return clean in paused_variants or "일시정지" in clean or "pause" in clean.lower()

    def display_status(self, status: str):
        if self._paused and not self._is_paused_status_text(status):
            return
        for o in self.overlays:
            o.display_status(status)

    def set_clean_mode(self, enabled: bool):
        for o in self.overlays:
            o.set_clean_mode(enabled)

    def set_clean_text_mode(self, enabled: bool):
        """별칭 지원: set_clean_mode와 동일"""
        self.set_clean_mode(enabled)

    def set_show_original(self, enabled: bool):
        """관리 중인 모든 화면 자막 오버레이 창에 영문 원문 표시 여부 동기화"""
        self.config["show_original"] = bool(enabled)
        for o in self.overlays:
            if hasattr(o, "set_show_original"):
                o.set_show_original(enabled)
            else:
                o.config["show_original"] = bool(enabled)
                if hasattr(o, "label_original"):
                    o.label_original.setVisible(bool(enabled))
                o.update()

    def apply_config(self, apply_geometry=False):
        for o in self.overlays:
            o._apply_config(apply_geometry=apply_geometry)

    def _apply_ui_language(self):
        is_multi = len(self.overlays) > 1
        for idx, o in enumerate(self.overlays):
            o.assigned_roi_idx = idx
            o.is_multi = is_multi
            if self._paused:
                o.is_paused = True
                if hasattr(o, "live_badge") and o.live_badge:
                    o.live_badge.setText(tr("ocr_status_paused"))
            if hasattr(o, "_apply_ui_language"):
                o._apply_ui_language()
            elif hasattr(o, "title_label") and o.title_label:
                title = f"👁️ {tr('screen_translation')} #{idx + 1}" if is_multi else f"👁️ {tr('screen_translation')}"
                o.title_label.setText(title)

    def update(self):
        for o in self.overlays:
            o.update()

    def set_stroke_width(self, val: int):
        for o in self.overlays:
            o.set_stroke_width(val)

    def set_letter_spacing(self, val: float):
        for o in self.overlays:
            o.set_letter_spacing(val)

    update_stroke_width = set_stroke_width
    update_letter_spacing = set_letter_spacing

    def set_badge_visible(self, visible: bool):
        self.config["show_engine_badge"] = visible
        for o in self.overlays:
            if hasattr(o, "set_badge_visible"):
                o.set_badge_visible(visible)
            elif hasattr(o, "live_badge"):
                o.live_badge.setVisible(visible)

    def set_clean_box(self, enabled: bool):
        self.config["screen_clean_box"] = bool(enabled)
        for o in self.overlays:
            if hasattr(o, "set_clean_box"):
                o.set_clean_box(enabled)
            else:
                o.config["screen_clean_box"] = bool(enabled)
                o.update()

    def set_show_speaker(self, enabled: bool):
        self.config["show_speaker"] = bool(enabled)
        for o in self.overlays:
            if hasattr(o, "set_show_speaker"):
                o.set_show_speaker(enabled)

    def set_speaker_diarization_enabled(self, enabled: bool):
        self.config["speaker_diarization_enabled"] = bool(enabled)
        for o in self.overlays:
            if hasattr(o, "set_speaker_diarization_enabled"):
                o.set_speaker_diarization_enabled(enabled)

    def update_font_size(self, val: int):
        self.config["font_size"] = val
        for o in self.overlays:
            if hasattr(o, "update_font_size"):
                o.update_font_size(val)
            else:
                o._apply_config(apply_geometry=False)

    set_font_size = update_font_size

    def update_opacity(self, pct: float):
        val = pct / 100.0 if float(pct) > 1.0 else float(pct)
        self.config["overlay_bg_opacity"] = max(0.0, min(1.0, val))
        for o in self.overlays:
            if hasattr(o, "update_opacity"):
                o.update_opacity(self.config["overlay_bg_opacity"])
            else:
                o._apply_config(apply_geometry=False)

    set_bg_opacity = update_opacity

    def update_snap_button_style(self):
        for o in self.overlays:
            o._update_snap_button_style()

    def set_snap_to_roi(self, enabled: bool):
        self.config["screen_snap_to_roi"] = bool(enabled)
        for o in self.overlays:
            if hasattr(o, "set_snap_to_roi"):
                o.set_snap_to_roi(enabled)
            elif hasattr(o, "toggle_snap_to_roi"):
                if o.config.get("screen_snap_to_roi", False) != enabled:
                    o.toggle_snap_to_roi()

    def update_border_button_style(self):
        for o in self.overlays:
            o._update_border_button_style()

    def snap_all_to_rois(self):
        rois = self.config.get("screen_rois", [])
        if not rois:
            single = self.config.get("screen_roi")
            if single:
                rois = [single]
        for idx, overlay in enumerate(self.overlays):
            if idx < len(rois):
                overlay.assigned_roi = rois[idx]
                overlay.assigned_roi_idx = idx
                overlay.snap_to_roi(rois[idx])

    def show(self):
        self.sync_rois()
        for o in self.overlays:
            screen = self._target_screen(o.assigned_roi)
            o.is_auto_resizing = True
            try:
                if screen:
                    o.winId()
                    handle = o.windowHandle()
                    if handle and handle.screen() is not screen:
                        handle.setScreen(screen)
                o.show()
            finally:
                o.is_auto_resizing = False
            if screen and not screen.geometry().contains(o.geometry().center()):
                self._move_to_target_screen(o, screen)

    def hide(self):
        for o in self.overlays:
            o.hide()

    def raise_(self):
        for o in self.overlays:
            o.raise_()

    def isVisible(self):
        return any(o.isVisible() for o in self.overlays)

    def is_visible(self):
        """별칭 지원: isVisible과 동일"""
        return self.isVisible()

    def set_visible(self, visible: bool):
        """전체 오버레이 창 표시/숨김 일괄 제어"""
        if visible:
            self.show()
        else:
            self.hide()

    def get_overlays(self):
        """스냅샷 캡처 시 일시 숨김을 위한 모든 자막창 리스트 반환"""
        return list(self.overlays)

    def get_all_geometries(self):
        """모든 관리 대상 오버레이 창들의 현재 좌표 및 크기 딕셔너리 반환"""
        geo_map = {}
        for idx, o in enumerate(self.overlays):
            g = o.geometry()
            geo_map[str(idx)] = [g.x(), g.y(), g.width(), g.height()]
        return geo_map

    def close(self):
        """모든 관리 대상 오버레이 창 닫기"""
        for o in self.overlays:
            o.close()

    def reset_geometry(self):
        """모든 관리 대상 화면 번역 오버레이 창들의 위치 및 크기를 기본값으로 초기화"""
        default_geo = [200, 520, 850, 130]
        self.config["screen_overlay_geometry"] = list(default_geo)
        self.config["screen_overlay_geometries"] = {}
        for idx, overlay in enumerate(self.overlays):
            y_offset = default_geo[1] + (idx * (default_geo[3] + 15))
            overlay.setGeometry(default_geo[0], y_offset, default_geo[2], default_geo[3])
            overlay.base_geometry = [default_geo[0], y_offset, default_geo[2], default_geo[3]]
            overlay.is_user_positioned = False
            overlay.is_user_sized = False
            if hasattr(overlay, '_notify_config_change'):
                overlay._notify_config_change()
        if self.on_config_change:
            self.on_config_change(self.config)
