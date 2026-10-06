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
        "desc": "Translation: Tencent Hy-MT2 1.8B | STT: Whisper Small, auto-detect | Tempo: YouTube",
    },
    "balance": {
        "name": "⚖️ Smart balance",
        "short_name": "⚖️ Balance",
        "desc": "Translation: Tencent Hy-MT2 1.8B | STT: Whisper Small, auto-detect | Tempo: Smart",
    },
    "cinema": {
        "name": "🎬 Film and drama",
        "short_name": "🎬 Cinema",
        "desc": "Translation: TranslateGemma 4B | STT: Whisper Large Turbo, auto-detect | Tempo: Cinema",
    },
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

SUPPORTED_UI_LANGUAGES = UI_LANGUAGE_NAMES

_forced_lang = None


def detect_system_ui_language() -> str:
    """Windows OS 언어를 감지하여 일치하는 15개국 언어 코드를 반환한다 (기본값 'en', 한국어 OS는 'ko')."""
    raw_loc = ""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85) > 0:
            raw_loc = buf.value.lower()
    except Exception:
        pass
    if not raw_loc:
        try:
            import locale
            raw_loc = (locale.getlocale()[0] or "").lower()
        except Exception:
            pass

    if raw_loc:
        code = raw_loc.split("-")[0].split("_")[0]
        if code in CATALOGS:
            return code
        if code.startswith("zh"):
            return "zh"

    from src.product import is_global as _check_global
    if not _check_global():
        return "ko"
    return "en"


def supported_ui_languages():
    return tuple(UI_LANGUAGE_NAMES.keys())


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


_DESC_TO_KEY = {
    "초경량 테스트/저사양용, 초저지연 (영어 전용)": "model_desc_tiny.en",
    "초경량 다국어(한국어 포함) 지원 모델": "model_desc_tiny",
    "경량 기본 모델, 빠른 반응 (영어 전용)": "model_desc_base.en",
    "경량 다국어(한국어 포함) 기본 모델": "model_desc_base",
    "가성비 및 속도-정확도 균형 표준 (영어 전용)": "model_desc_small.en",
    "가성비 및 속도-정확도 균형 표준 (다국어/한국어 지원)": "model_desc_small",
    "고품질 영어 전사 (권장 VRAM 4GB+ · GPU 권장)": "model_desc_medium.en",
    "고품질 다국어(한국어 포함) 전사 (권장 VRAM 4GB+ · GPU 권장)": "model_desc_medium",
    "검증된 대규모 다국어 플래그십 (CUDA GPU 필수)": "model_desc_large-v2",
    "최고의 음성 인식 정확도 (한국어/다국어 · CUDA GPU 필수)": "model_desc_large-v3",
    "최신 공식 Turbo 8배 가속 모델 (CUDA GPU 권장)": "model_desc_large-v3-turbo",
    "★ 기본 내장 번들 모델 · 5배 가속 초경량 증류 모델 (CPU 최적화)": "model_desc_distil-small.en",
    "고속 중간 크기 증류 모델 (CPU 원활 / 지연시간 단축)": "model_desc_distil-medium.en",
    "대규모 영어 데이터 증류 모델 (CUDA GPU 권장)": "model_desc_distil-large-v2",
    "지연시간을 50% 단축한 고속 대형 증류 모델 (CUDA GPU 권장)": "model_desc_distil-large-v3",
    "최신 고정밀 증류 모델 (영어 전용 · CUDA GPU 권장)": "model_desc_distil-large-v3.5",
    "Groq LPU 초고속 전사 (한국어/다국어 지원, $0.04/h)": "model_desc_whisper-large-v3-turbo",
    "Groq LPU 고정밀 전사 (한국어/다국어 지원, $0.111/h)": "model_desc_whisper-large-v3",
    "Deepgram 차세대 플래그십 (최고 정확도 · 0.15s 초저지연)": "model_desc_nova-3",
    "검증된 고정밀 글로벌 음향 모델": "model_desc_nova-2",
    "다양한 억양 및 소음 환경 최적화": "model_desc_nova-2-general",
    "로컬 최고 품질 | 원작 뉘앙스/문맥 번역 종결자": "model_desc_translategemma:4b",
    "로컬 최고 품질 | 원작 뉘앙스/문맥 번역 종결자 (GGUF)": "model_desc_translategemma-4b",
    "로컬 균형형 | LG 한국어 특화 자연스러운 문체": "model_desc_exaone3.5:2.4b",
    "로컬 균형형 | LG 한국어 특화 자연스러운 문체 (GGUF)": "model_desc_exaone-3.5-2.4b",
    "로컬 최고 지능 | LG 국산 7.8B 고품질 심층 번역 및 문맥 추론": "model_desc_exaone3.5:7.8b",
    "로컬 최고 지능 | LG 국산 7.8B 고품질 심층 번역 (GGUF)": "model_desc_exaone-3.5-7.8b",
    "초경량 번역 특화 | VRAM 1.4GB 텐센트 차세대 IFMT 전문 번역": "model_desc_tencent/hy-mt2:1.8b",
    "초경량 번역 특화 | 텐센트 공식 GGUF 차세대 IFMT 전문 번역 (GGUF)": "model_desc_hymt-2-1.8b",
}


def get_model_desc(model_info_or_desc) -> str:
    """Return localized description for STT / LLM models."""
    if isinstance(model_info_or_desc, dict):
        m_id = str(model_info_or_desc.get("id") or model_info_or_desc.get("tag") or "").strip()
        key = f"model_desc_{m_id}"
        val = tr(key)
        if val != key:
            return val
        raw_desc = str(model_info_or_desc.get("desc") or "").strip()
        if raw_desc in _DESC_TO_KEY:
            return tr(_DESC_TO_KEY[raw_desc])
        return raw_desc
    elif isinstance(model_info_or_desc, str):
        s = model_info_or_desc.strip()
        if s in _DESC_TO_KEY:
            return tr(_DESC_TO_KEY[s])
        key = f"model_desc_{s}"
        val = tr(key)
        if val != key:
            return val
        return model_info_or_desc
    return str(model_info_or_desc or "")

