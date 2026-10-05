"""화면 문구. 한국어 제품은 한국어로 고정하고, 글로벌 제품은 ui_lang을 따른다."""
from src.product import is_global
from src.ui_strings import CATALOGS, UI_LANGS

GLOBAL_PRESET_COPY = {
    "low_spec": {
        "name": "🌱 Low-spec (CPU)",
        "short_name": "🌱 Low-spec",
        "desc": "Translation: Google | STT: Whisper Small, auto-detect | Tempo: Smart",
    },
    "live": {
        "name": "⚡ Low latency",
        "short_name": "⚡ Live",
        "desc": "Translation: Tencent Hy-MT2 1.8B | STT: Whisper Large Turbo, auto-detect | Tempo: YouTube",
    },
    "balance": {
        "name": "⚖️ Smart balance",
        "short_name": "⚖️ Balance",
        "desc": "Translation: Tencent Hy-MT2 1.8B | STT: Whisper Large Turbo, auto-detect | Tempo: Smart",
    },
    "cinema": {
        "name": "🎬 Film and drama",
        "short_name": "🎬 Cinema",
        "desc": "Translation: TranslateGemma 4B | STT: Whisper Large Turbo, auto-detect | Tempo: Cinema",
    },
}

SUPPORTED_UI_LANGUAGES = {
    "ko": "한국어",
    "en": "English",
}

UI_LANGUAGE_NAMES = {
    "ko": "한국어",
    "en": "English",
    "ja": "日本語",
    "zh": "中文",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "ru": "Русский",
    "it": "Italiano",
    "pt": "Português",
    "vi": "Tiếng Việt",
    "th": "ไทย",
    "id": "Bahasa Indonesia",
    "ar": "العربية",
    "hi": "हिन्दी",
}

_forced_lang = None


def detect_system_ui_language() -> str:
    """Windows OS 언어를 감지하여 'ko' 또는 'en'을 반환한다."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85) > 0:
            loc = buf.value.lower()
            if loc.startswith("ko"):
                return "ko"
    except Exception:
        pass
    try:
        import locale
        loc = (locale.getlocale()[0] or "").lower()
        if loc.startswith("ko") or loc.startswith("korean"):
            return "ko"
    except Exception:
        pass
    return "en"


def supported_ui_languages():
    return ("ko", "en")


def normalize_ui_language(code: str) -> str:
    raw = str(code or "").strip().lower().split("-")[0]
    if raw in CATALOGS:
        return raw
    return "en"


def set_ui_language(code):
    """None이면 제품 기본값으로 되돌린다."""
    global _forced_lang
    if code is None:
        _forced_lang = None
        return
    _forced_lang = normalize_ui_language(code)


def ui_language() -> str:
    if _forced_lang:
        return _forced_lang
    if not is_global():
        return "ko"
    return "en"


def tr(_key: str, /, **fmt) -> str:
    lang = ui_language()
    table = CATALOGS.get(lang) or CATALOGS["en"]
    text = table.get(_key)
    if text is None:
        text = CATALOGS["en"].get(_key) or CATALOGS["ko"].get(_key) or _key
    if fmt:
        text = text.format(**fmt)
    return text


def ask(parent, title_key: str, body_key: str, **fmt):
    from PyQt6.QtWidgets import QMessageBox
    return QMessageBox.question(
        parent,
        tr(title_key),
        tr(body_key, **fmt),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )


def is_cancel_message(message) -> bool:
    text = str(message or "").lower()
    return "취소" in text or "cancel" in text


def tell(parent, title_key: str, body_key: str, kind: str = "info", **fmt):
    from PyQt6.QtWidgets import QMessageBox
    show = QMessageBox.warning if kind == "warn" else QMessageBox.information
    return show(parent, tr(title_key), tr(body_key, **fmt))


def bind(widget, key: str, **fmt):
    widget.setProperty("i18n_key", key)
    widget.setProperty("i18n_fmt", dict(fmt) if fmt else {})
    widget.setText(tr(key, **fmt))
    return widget


def refresh_texts(root):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QWidget

    direction = Qt.LayoutDirection.RightToLeft if ui_language() == "ar" else Qt.LayoutDirection.LeftToRight
    if isinstance(root, QWidget):
        root.setLayoutDirection(direction)
    widgets = [root]
    if hasattr(root, "findChildren"):
        widgets.extend(root.findChildren(QWidget))
    for widget in widgets:
        key = widget.property("i18n_key") if hasattr(widget, "property") else None
        if not key:
            continue
        fmt = widget.property("i18n_fmt") or {}
        if not isinstance(fmt, dict):
            fmt = {}
        widget.setText(tr(str(key), **fmt))
