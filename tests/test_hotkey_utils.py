import unittest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from src.hotkey_utils import (
    parse_hotkey_string, normalize_hotkey_string,
    MOD_CONTROL, MOD_ALT, MOD_SHIFT, MOD_WIN, HotkeyCaptureButton
)
from src.inplace_translator import GlobalHotkeyWorker

app = QApplication.instance() or QApplication([])

class TestHotkeyUtils(unittest.TestCase):
    def test_default_f4(self):
        vk, mod = parse_hotkey_string("F4")
        self.assertEqual(vk, 0x73)
        self.assertEqual(mod, 0)
        self.assertEqual(normalize_hotkey_string("F4"), "F4")

    def test_ctrl_f4(self):
        vk, mod = parse_hotkey_string("Ctrl+F4")
        self.assertEqual(vk, 0x73)
        self.assertEqual(mod, MOD_CONTROL)
        self.assertEqual(normalize_hotkey_string("Ctrl+F4"), "Ctrl+F4")

    def test_ctrl_shift_s(self):
        vk, mod = parse_hotkey_string("Ctrl+Shift+S")
        self.assertEqual(vk, ord('S'))
        self.assertEqual(mod, MOD_CONTROL | MOD_SHIFT)
        self.assertEqual(normalize_hotkey_string("Shift+Ctrl+S"), "Ctrl+Shift+S")

    def test_f9_and_pause(self):
        vk, mod = parse_hotkey_string("F9")
        self.assertEqual(vk, 0x78)
        self.assertEqual(mod, 0)
        self.assertEqual(normalize_hotkey_string("f9"), "F9")

        vk_p, mod_p = parse_hotkey_string("Pause")
        self.assertEqual(vk_p, 0x13)
        self.assertEqual(mod_p, 0)

    def test_invalid_fallback(self):
        vk, mod = parse_hotkey_string("INVALID_KEY_XYZ")
        self.assertEqual(vk, 0x73)  # Fallback to F4
        self.assertEqual(mod, 0)

    def test_hotkey_capture_button_interaction(self):
        btn = HotkeyCaptureButton("F4")
        self.assertEqual(btn.get_hotkey(), "F4")
        self.assertEqual(btn.text(), "⌨️ 단축키 설정")

        # Start recording
        btn._on_clicked()
        self.assertTrue(btn.is_recording)
        self.assertIn("키 입력 대기", btn.text())

        # Simulate pressing F9
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F9, Qt.KeyboardModifier.NoModifier)
        btn.keyPressEvent(event)
        self.assertFalse(btn.is_recording)
        self.assertEqual(btn.get_hotkey(), "F9")
        self.assertEqual(btn.text(), "⌨️ 단축키 설정")

        # Start recording again and simulate Ctrl+F4
        btn._on_clicked()
        self.assertTrue(btn.is_recording)
        event_ctrl_f4 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F4, Qt.KeyboardModifier.ControlModifier)
        btn.keyPressEvent(event_ctrl_f4)
        self.assertFalse(btn.is_recording)
        self.assertEqual(btn.get_hotkey(), "Ctrl+F4")
        self.assertEqual(btn.text(), "⌨️ 단축키 설정")

        # Cancel with Escape
        btn._on_clicked()
        self.assertTrue(btn.is_recording)
        event_esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        btn.keyPressEvent(event_esc)
        self.assertFalse(btn.is_recording)
        self.assertEqual(btn.get_hotkey(), "Ctrl+F4")  # Unchanged
        self.assertEqual(btn.text(), "⌨️ 단축키 설정")

    def test_global_hotkey_worker_initialization(self):
        worker = GlobalHotkeyWorker(hotkey_str="Ctrl+F4")
        self.assertEqual(worker.hotkey_str, "Ctrl+F4")
        self.assertEqual(worker.vk_code, 0x73)
        self.assertEqual(worker.modifiers, MOD_CONTROL)

if __name__ == '__main__':
    unittest.main()
