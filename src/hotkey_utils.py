"""
전역 단축키 파싱, Win32 Virtual-Key(VK) 매핑 및 인터랙티브 키 캡처 위젯 모듈.
"""

import re
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QApplication
from PyQt6.QtGui import QKeyEvent, QColor, QFont

# Win32 RegisterHotKey Modifiers
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# Win32 Virtual Key Codes
VK_MAP = {
    # Function keys (F1 ~ F24)
    **{f"F{i}": 0x70 + (i - 1) for i in range(1, 25)},
    # Letters (A ~ Z)
    **{chr(c): c for c in range(ord('A'), ord('Z') + 1)},
    # Digits (0 ~ 9)
    **{str(i): ord('0') + i for i in range(10)},
    # Numpad (Num0 ~ Num9)
    **{f"NUM{i}": 0x60 + i for i in range(10)},
    "NUM*": 0x6A,
    "NUM+": 0x6B,
    "NUM-": 0x6D,
    "NUM.": 0x6E,
    "NUM/": 0x6F,
    # Navigation / Control keys
    "PAUSE": 0x13,
    "SCROLLLOCK": 0x91,
    "SCROLL": 0x91,
    "PRINTSCREEN": 0x2C,
    "SNAPSHOT": 0x2C,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "SPACE": 0x20,
    "TAB": 0x09,
    # OEM Symbols
    "`": 0xC0,
    "~": 0xC0,
    "-": 0xBD,
    "=": 0xBB,
    "+": 0xBB,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
    ";": 0xBA,
    "'": 0xDE,
    ",": 0xBC,
    ".": 0xBE,
    "/": 0xBF,
}

MOD_NAME_MAP = {
    "CTRL": MOD_CONTROL,
    "CONTROL": MOD_CONTROL,
    "ALT": MOD_ALT,
    "SHIFT": MOD_SHIFT,
    "WIN": MOD_WIN,
    "META": MOD_WIN,
}

# PyQt6 Key -> 정규화된 키 이름
QT_KEY_TO_NAME = {
    # Function keys
    **{getattr(Qt.Key, f"Key_F{i}"): f"F{i}" for i in range(1, 25) if hasattr(Qt.Key, f"Key_F{i}")},
    # Letters
    **{getattr(Qt.Key, f"Key_{chr(c)}"): chr(c) for c in range(ord('A'), ord('Z') + 1) if hasattr(Qt.Key, f"Key_{chr(c)}")},
    # Digits
    **{getattr(Qt.Key, f"Key_{i}"): str(i) for i in range(10) if hasattr(Qt.Key, f"Key_{i}")},
    # Navigation / Special
    Qt.Key.Key_Pause: "Pause",
    Qt.Key.Key_ScrollLock: "ScrollLock",
    Qt.Key.Key_Print: "PrintScreen",
    Qt.Key.Key_Insert: "Insert",
    Qt.Key.Key_Delete: "Delete",
    Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End",
    Qt.Key.Key_PageUp: "PageUp",
    Qt.Key.Key_PageDown: "PageDown",
    Qt.Key.Key_Space: "Space",
    Qt.Key.Key_Tab: "Tab",
    Qt.Key.Key_QuoteLeft: "`",
    Qt.Key.Key_AsciiTilde: "`",
    Qt.Key.Key_Minus: "-",
    Qt.Key.Key_Equal: "=",
    Qt.Key.Key_BracketLeft: "[",
    Qt.Key.Key_BracketRight: "]",
    Qt.Key.Key_Backslash: "\\",
    Qt.Key.Key_Semicolon: ";",
    Qt.Key.Key_Apostrophe: "'",
    Qt.Key.Key_Comma: ",",
    Qt.Key.Key_Period: ".",
    Qt.Key.Key_Slash: "/",
}


def parse_hotkey_string(hotkey_str: str) -> tuple[int, int]:
    """
    사람이 읽을 수 있는 단축키 문자열(예: 'F4', 'Ctrl+F4', 'Ctrl+Shift+S', 'Pause')을
    Win32 (vk_code, modifiers) 튜플로 변환합니다.
    유효하지 않은 경우 기본값인 ('F4' -> (0x73, 0)) 반환.
    """
    if not hotkey_str or not isinstance(hotkey_str, str):
        return 0x73, 0  # Default: F4, no modifiers

    tokens = [t.strip().upper() for t in re.split(r'[\+\-\s]', hotkey_str) if t.strip()]
    if not tokens:
        return 0x73, 0

    modifiers = 0
    main_key = None

    for token in tokens:
        if token in MOD_NAME_MAP:
            modifiers |= MOD_NAME_MAP[token]
        else:
            main_key = token

    if not main_key:
        return 0x73, 0

    vk_code = VK_MAP.get(main_key)
    if vk_code is None:
        return 0x73, 0

    return vk_code, modifiers


def normalize_hotkey_string(hotkey_str: str) -> str:
    """
    단축키 문자열을 표준화된 순서('Ctrl+Alt+Shift+Key')로 정규화합니다.
    """
    vk, mod = parse_hotkey_string(hotkey_str)
    # Parse back to normalized display
    parts = []
    if mod & MOD_CONTROL:
        parts.append("Ctrl")
    if mod & MOD_ALT:
        parts.append("Alt")
    if mod & MOD_SHIFT:
        parts.append("Shift")
    if mod & MOD_WIN:
        parts.append("Win")

    # Find name for vk
    name = "F4"
    for k_name, k_vk in VK_MAP.items():
        if k_vk == vk:
            name = k_name
            # Capitalize nicely
            if name.startswith("F") and name[1:].isdigit():
                name = name
            elif len(name) > 1:
                name = name.capitalize()
            break

    parts.append(name)
    return "+".join(parts)


class HotkeyCaptureButton(QPushButton):
    """
    사용자가 직접 키보드를 눌러 단축키를 지정할 수 있는 인터랙티브 UI 버튼.
    - 클릭 시 '⌨️ 키 입력 대기 중... (Esc: 취소)' 상태로 전환
    - 임의의 키(F1~F12, Pause 등) 또는 조합키(Ctrl+F4 등) 감지
    - Esc 입력 시 편집 취소
    - Alt+F4 등 OS 예약 단축키 감지 시 자동 보호
    - hotkey_changed(new_hotkey_str) 시그널 방출
    """
    hotkey_changed = pyqtSignal(str)
    recording_state_changed = pyqtSignal(bool)

    def __init__(self, current_hotkey="F4", parent=None):
        super().__init__(parent)
        self.current_hotkey = normalize_hotkey_string(current_hotkey)
        self.is_recording = False
        self._setup_style()
        self._update_text()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._on_clicked)

    def _setup_style(self):
        self.setFixedHeight(28)
        self.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))
        self._apply_normal_style()

    def _apply_normal_style(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #38BDF8;
                border: 1px solid #0EA5E9;
                border-radius: 6px;
                padding: 4px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0369A1;
                color: #FFFFFF;
            }
        """)

    def _apply_recording_style(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #7C3AED;
                color: #FFFFFF;
                border: 1.5px solid #C084FC;
                border-radius: 6px;
                padding: 4px 12px;
                font-weight: bold;
            }
        """)

    def _update_text(self):
        if self.is_recording:
            self.setText("⌨️ 키 입력 대기 중...")
        else:
            self.setText("⌨️ 단축키 설정")
            self.setToolTip(f"현재 단축키: {self.current_hotkey} (클릭하여 단축키 변경, Esc: 취소)")

    def set_hotkey(self, hotkey_str: str):
        """외부에서 단축키 값을 설정"""
        self.current_hotkey = normalize_hotkey_string(hotkey_str)
        if self.is_recording:
            self.is_recording = False
            self.recording_state_changed.emit(False)
        self._apply_normal_style()
        self._update_text()

    def get_hotkey(self) -> str:
        return self.current_hotkey

    def _on_clicked(self):
        if not self.is_recording:
            self.is_recording = True
            self._apply_recording_style()
            self._update_text()
            self.recording_state_changed.emit(True)
            self.setFocus(Qt.FocusReason.MouseFocusReason)
        else:
            # Re-clicking cancels recording
            self.is_recording = False
            self._apply_normal_style()
            self._update_text()
            self.recording_state_changed.emit(False)

    def keyPressEvent(self, event: QKeyEvent):
        if not self.is_recording:
            super().keyPressEvent(event)
            return

        key = event.key()

        # 1. Esc는 취소
        if key == Qt.Key.Key_Escape:
            self.is_recording = False
            self.recording_state_changed.emit(False)
            self._apply_normal_style()
            self._update_text()
            event.accept()
            return

        # 2. 수정자 키 단독 입력 시 중간 상태 표시 (예: "Ctrl + ...")
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            parts = []
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ControlModifier:
                parts.append("Ctrl")
            if mods & Qt.KeyboardModifier.AltModifier:
                parts.append("Alt")
            if mods & Qt.KeyboardModifier.ShiftModifier:
                parts.append("Shift")
            if mods & Qt.KeyboardModifier.MetaModifier:
                parts.append("Win")
            self.setText(f"⌨️ {' + '.join(parts)} + ...")
            event.accept()
            return

        # 3. 메인 키 이름 판별
        key_name = QT_KEY_TO_NAME.get(key)
        if not key_name:
            # Fallback for text character
            text = event.text().strip().upper()
            if text and text in VK_MAP:
                key_name = text

        if not key_name:
            # 알 수 없는 키
            event.accept()
            return

        # 조합키(Modifiers) 분석
        parts = []
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")

        # Alt+F4는 Windows 창 닫기 단축키이므로 방어
        if "Alt" in parts and key_name == "F4":
            self.setText("⚠️ Alt+F4는 Windows 창 닫기 전용입니다!")
            QApplication.beep()
            event.accept()
            return

        parts.append(key_name)
        new_hotkey = "+".join(parts)
        self.current_hotkey = new_hotkey
        self.is_recording = False
        self.recording_state_changed.emit(False)
        self._apply_normal_style()
        self._update_text()
        self.clearFocus()
        self.hotkey_changed.emit(new_hotkey)
        event.accept()

    def focusOutEvent(self, event):
        if self.is_recording:
            self.is_recording = False
            self.recording_state_changed.emit(False)
            self._apply_normal_style()
            self._update_text()
        super().focusOutEvent(event)
