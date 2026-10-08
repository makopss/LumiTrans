# -*- coding: utf-8 -*-
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("WISE_PRODUCT", "kr")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

app = QApplication.instance()
if not app:
    app = QApplication([])

from src.config import DEFAULT_CONFIG
from src.control_panel import ControlPanel


class TestSimpleMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._ducking = patch("src.process_volume.AudioDuckingManager", autospec=True)
        cls._ducking.start()

    @classmethod
    def tearDownClass(cls):
        cls._ducking.stop()

    def setUp(self):
        self._src = patch(
            "src.audio_capture.AudioLoopbackCapture.get_available_capture_sources",
            return_value=[{"id": "default", "type": "device", "name": "default"}],
        )
        self._speakers = patch("soundcard.all_speakers", return_value=[])
        self._src.start()
        self._speakers.start()
        self.addCleanup(self._src.stop)
        self.addCleanup(self._speakers.stop)

        self.panel = ControlPanel(
            copy.deepcopy(DEFAULT_CONFIG),
            overlay=None,
            audio_thread=None,
            stt_thread=None,
            save_config_cb=lambda c: None,
        )

    def tearDown(self):
        self.panel.close()

    def test_default_is_full_mode(self):
        self.assertFalse(self.panel._is_simple_mode)
        self.assertTrue(self.panel.content_container.isVisibleTo(self.panel))
        self.assertTrue(self.panel.header_widget.isVisibleTo(self.panel))
        self.assertTrue(self.panel.btn_full_pin.isVisibleTo(self.panel))
        self.assertTrue(self.panel.btn_switch_to_simple.isVisibleTo(self.panel))
        self.assertTrue(self.panel.tab_stack.isVisibleTo(self.panel))
        self.assertTrue(self.panel.bottom_bar.isVisibleTo(self.panel))
        self.assertFalse(self.panel.simple_container.isVisibleTo(self.panel))
        self.assertEqual(self.panel.minimumHeight(), 800)

    def test_toggle_to_simple_mode_and_back(self):
        # 1. Switch to Simple Mode
        self.panel.set_simple_mode(True)
        self.assertTrue(self.panel._is_simple_mode)
        self.assertFalse(self.panel.content_container.isVisibleTo(self.panel))
        self.assertFalse(self.panel.header_widget.isVisibleTo(self.panel))
        self.assertFalse(self.panel.tab_stack.isVisibleTo(self.panel))
        self.assertFalse(self.panel.bottom_bar.isVisibleTo(self.panel))
        self.assertTrue(self.panel.simple_container.isVisibleTo(self.panel))
        self.assertTrue(self.panel.btn_simple_pin.isVisibleTo(self.panel))
        self.assertTrue(self.panel.btn_simple_expand.isVisibleTo(self.panel))
        self.assertEqual(self.panel.minimumHeight(), 240)
        self.assertEqual(self.panel.config.get("ui_mode"), "simple")

        # 2. Switch back to Full Mode
        self.panel.set_simple_mode(False)
        self.assertFalse(self.panel._is_simple_mode)
        self.assertTrue(self.panel.content_container.isVisibleTo(self.panel))
        self.assertTrue(self.panel.header_widget.isVisibleTo(self.panel))
        self.assertTrue(self.panel.btn_full_pin.isVisibleTo(self.panel))
        self.assertTrue(self.panel.btn_switch_to_simple.isVisibleTo(self.panel))
        self.assertTrue(self.panel.tab_stack.isVisibleTo(self.panel))
        self.assertTrue(self.panel.bottom_bar.isVisibleTo(self.panel))
        self.assertFalse(self.panel.simple_container.isVisibleTo(self.panel))
        self.assertEqual(self.panel.minimumHeight(), 800)
        self.assertEqual(self.panel.config.get("ui_mode"), "full")

    def test_simple_mode_audio_toggle_sync(self):
        self.panel.set_simple_mode(True)
        # Initially audio is inactive
        self.assertFalse(self.panel._is_audio_active)
        self.assertFalse(self.panel.btn_simple_audio.isChecked())

        # Click simple audio button
        self.panel.btn_simple_audio.click()
        self.assertTrue(self.panel._is_audio_active)
        self.assertTrue(self.panel.btn_simple_audio.isChecked())
        self.assertTrue(self.panel.btn_bottom_audio.isChecked())

        # Toggle off
        self.panel.btn_simple_audio.click()
        self.assertFalse(self.panel._is_audio_active)
        self.assertFalse(self.panel.btn_simple_audio.isChecked())
        self.assertFalse(self.panel.btn_bottom_audio.isChecked())

    def test_simple_mode_screen_toggle_sync(self):
        self.panel.set_simple_mode(True)
        # Initially screen translation is inactive
        self.assertFalse(self.panel._is_screen_active)
        self.assertFalse(self.panel.btn_simple_screen.isChecked())

        # Click simple screen button
        self.panel.btn_simple_screen.click()
        self.assertTrue(self.panel._is_screen_active)
        self.assertTrue(self.panel.btn_simple_screen.isChecked())
        self.assertTrue(self.panel.btn_bottom_screen.isChecked())

        # Toggle off
        self.panel.btn_simple_screen.click()
        self.assertFalse(self.panel._is_screen_active)
        self.assertFalse(self.panel.btn_simple_screen.isChecked())
        self.assertFalse(self.panel.btn_bottom_screen.isChecked())

    def test_simple_mode_dubbing_toggle_sync(self):
        self.panel.set_simple_mode(True)
        self.assertFalse(self.panel.config.get("dubbing_enabled", False))
        self.assertFalse(self.panel.btn_simple_dubbing.isChecked())

        # Click simple dubbing button
        self.panel.btn_simple_dubbing.click()
        self.assertTrue(self.panel.config.get("dubbing_enabled", False))
        self.assertTrue(self.panel.btn_simple_dubbing.isChecked())
        self.assertTrue(self.panel.btn_bottom_dubbing.isChecked())

        # Toggle off
        self.panel.btn_simple_dubbing.click()
        self.assertFalse(self.panel.config.get("dubbing_enabled", False))
        self.assertFalse(self.panel.btn_simple_dubbing.isChecked())
        self.assertFalse(self.panel.btn_bottom_dubbing.isChecked())

    def test_simple_mode_dubbing_volume_slider_sync(self):
        self.panel.set_simple_mode(True)
        self.panel.slider_simple_dubbing_vol.setValue(85)
        self.assertEqual(self.panel.config.get("dubbing_volume"), 85)
        self.assertEqual(self.panel.slider_dubbing_vol.value(), 85)
        self.assertEqual(self.panel.lbl_simple_dubbing_vol_val.text(), "85%")

    def test_simple_mode_pin_toggle(self):
        self.panel.set_simple_mode(True)
        self.assertFalse(self.panel._simple_pinned)

        self.panel.toggle_simple_pin()
        self.assertTrue(self.panel._simple_pinned)
        self.assertTrue(self.panel.config.get("simple_stays_on_top"))

        self.panel.toggle_simple_pin()
        self.assertFalse(self.panel._simple_pinned)
        self.assertFalse(self.panel.config.get("simple_stays_on_top"))

    def test_frame_icon_buttons_and_pin_sync(self):
        # 1. Verify frame icon buttons use crisp vector SVGs (not raw unicode fallback text)
        self.assertFalse(self.panel.btn_switch_to_simple.icon().isNull())
        self.assertFalse(self.panel.btn_simple_expand.icon().isNull())
        self.assertFalse(self.panel.btn_full_pin.icon().isNull())
        self.assertFalse(self.panel.btn_simple_pin.icon().isNull())

        # 2. Pin toggling from full mode
        self.panel.set_simple_mode(False)
        self.panel.btn_full_pin.click()
        self.assertTrue(self.panel._simple_pinned)

        # Switch to simple mode: stays pinned
        self.panel.set_simple_mode(True)
        self.assertTrue(self.panel._simple_pinned)

        # Unpin from simple mode
        self.panel.btn_simple_pin.click()
        self.assertFalse(self.panel._simple_pinned)

    def test_startup_in_simple_mode(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["ui_mode"] = "simple"
        p = ControlPanel(
            cfg,
            overlay=None,
            audio_thread=None,
            stt_thread=None,
            save_config_cb=lambda c: None,
        )
        try:
            self.assertTrue(p._is_simple_mode)
            self.assertTrue(p.simple_container.isVisibleTo(p))
            self.assertFalse(p.content_container.isVisibleTo(p))
        finally:
            p.close()

    def test_close_in_simple_mode_saves_config(self):
        saved = {}
        def _cb(c):
            saved.clear()
            saved.update(c)

        self.panel.save_config_cb = _cb
        self.panel.set_simple_mode(True)
        self.assertEqual(saved.get("ui_mode"), "simple")

        # Simulate closing while in simple mode
        self.panel.save_all_settings_before_exit()
        self.assertEqual(saved.get("ui_mode"), "simple")


if __name__ == "__main__":
    unittest.main()
