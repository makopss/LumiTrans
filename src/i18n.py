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

UI_LANGUAGE_NAMES = {
    "en": "English",
    "ko": "한국어",
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


def supported_ui_languages():
    return UI_LANGS


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
    if not is_global():
        return "ko"
    if _forced_lang:
        return _forced_lang
    return "en"


def tr(key: str, **fmt) -> str:
    lang = ui_language()
    table = CATALOGS.get(lang) or CATALOGS["en"]
    text = table.get(key)
    if text is None:
        text = CATALOGS["en"].get(key) or CATALOGS["ko"].get(key) or key
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
