"""자막 오버레이 상태 배지에 표시할 음성인식/번역 엔진 이름 해석.

STT 엔진은 "Deepgram (nova-3)", "Groq (Turbo)", "GPU", "CPU (로컬 폴백)" 같은 라벨을,
번역기는 "EXAONE 3.5 7.8B (내장 GGUF)", "Google (exaone7b 폴백)", "MyMemory", "Ollama (tag)", "원문 유지" 같은
이름을 넘긴다. 오디오 자막창과 화면 번역창이 같은 규칙으로 표시하도록 여기서만 해석한다.
"""

from src.i18n import tr

_STT_KEYWORDS = (
    ("deepgram", "Deepgram"),
    ("groq", "Groq"),
    ("parakeet", "Parakeet"),
    ("sensevoice", "SenseVoice"),
    ("moonshine", "Moonshine"),
    ("cpu", "CPU"),
    ("gpu", "GPU"),
    ("cuda", "GPU"),
)

_TRANS_KEYWORDS = (
    ("hy-mt", "Hy-MT2"),
    ("hymt", "Hy-MT2"),
    ("gemma", "Gemma"),
    ("exaone", "EXAONE"),
    ("deepl", "DeepL"),
    ("gemini", "Gemini"),
    ("groq", "Groq"),
    ("mymemory", "MyMemory"),
    ("원문", "원문"),
    ("original", "원문"),
    ("google", "Google"),
)

_CONFIG_TRANS = {
    "google": "Google", "deepl": "DeepL", "gemini": "Gemini", "groq": "Groq",
    "exaone": "EXAONE", "exaone7b": "EXAONE", "gemma": "Gemma", "hymt": "Hy-MT2",
}


def configured_stt_label(config) -> str:
    """설정 기준 STT 표시 이름. 클라우드 STT 는 model_size(로컬 모델 설정)보다 우선한다."""
    config = config or {}
    provider = config.get("stt_provider", "local")
    if provider == "deepgram":
        return "Deepgram"
    if provider == "groq":
        return "Groq"
    model = str(config.get("model_size", ""))
    for prefix, name in (("parakeet", "Parakeet"), ("sensevoice", "SenseVoice"), ("moonshine", "Moonshine")):
        if model.startswith(prefix):
            return name
    return "CPU" if config.get("device") == "cpu" else "GPU"


def configured_translation_label(config) -> str:
    key = str((config or {}).get("translation_engine", "google")).lower()
    if key.startswith("ollama:"):
        # 컨트롤 패널은 Ollama 모델을 "ollama:<태그>" 로 저장한다
        tag = key.split(":", 1)[1]
        return next((disp for k, disp in _TRANS_KEYWORDS if k in tag), "Ollama")
    return _CONFIG_TRANS.get(key, key.capitalize() or "Google")


def stt_badge(raw: str, config) -> tuple:
    """(표시 이름, 폴백 여부)"""
    raw = raw or ""
    low = raw.lower()
    for key, name in _STT_KEYWORDS:
        if key in low:
            return name, "폴백" in raw or "fallback" in low
    return configured_stt_label(config), False


def translation_badge(raw: str, config) -> tuple:
    """(표시 이름, 폴백 여부). 선택한 엔진과 다른 엔진이 번역했으면 폴백으로 본다."""
    raw = raw or ""
    configured = configured_translation_label(config)
    head = raw.split("(")[0].strip().lower()
    if head.startswith("ollama"):
        head = raw.lower()   # Ollama 는 괄호 안 모델 태그로 판단
    name = next((disp for key, disp in _TRANS_KEYWORDS if key in head), None)
    if name is None:
        return configured, False
    fallback = "폴백" in raw or "fallback" in raw.lower() or name == "원문" or name != configured
    display_name = tr("original") if name == "원문" else name
    return display_name, fallback
