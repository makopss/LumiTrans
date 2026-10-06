import sys
import os
import json
import stat
import threading
import time

def get_config_file_path() -> str:
    """설정 파일(config.json)의 실제 저장 경로 반환
    
    1. 개발 환경: 프로젝트 루트의 config.json
    2. 배포(frozen) 환경:
       - 포터블 모드: exe와 같은 폴더에 portable.txt가 있거나 exe 폴더에 쓰기가 가능한 경우
       - 설치(Program Files 등) 모드: %APPDATA%/LumiTrans/config.json 사용 (권한 에러 및 업데이트 덮어쓰기 방지)
         이전 이름(%APPDATA%/WiseEinstein) 폴더가 있으면 자동으로 옮긴다.
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        portable_flag = os.path.join(exe_dir, "portable.txt")
        if os.path.exists(portable_flag):
            return os.path.join(exe_dir, "config.json")

        from src.app_paths import roaming_data_dir
        user_cfg_dir = roaming_data_dir()
        user_cfg = os.path.join(user_cfg_dir, "config.json")

        # exe 디렉터리 쓰기 가능 여부 테스트 (C:\Program Files 설치 등 권한 제한 감지)
        try:
            test_file = os.path.join(exe_dir, ".perm_test")
            with open(test_file, "w") as f:
                f.write("1")
            os.remove(test_file)
            is_exe_writable = True
        except Exception:
            is_exe_writable = False

        if not is_exe_writable or os.path.exists(user_cfg):
            os.makedirs(user_cfg_dir, exist_ok=True)
            return user_cfg

        # exe 폴더가 쓰기 가능하더라도 일반 설치형인 경우 안전하게 APPDATA 사용 (업데이트 덮어쓰기 방지)
        os.makedirs(user_cfg_dir, exist_ok=True)
        return user_cfg
    else:
        from src.product import is_global
        filename = "config.global.json" if is_global() else "config.json"
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), filename)

CONFIG_FILE = get_config_file_path()

DEFAULT_CONFIG = {
    "last_active_tab": 0,            # 마지막으로 활성화되었던 탭 인덱스 (0: 음성 번역)
    "model_size": "distil-small.en", # 기본 내장 번들 모델 (distil-small.en)
    "stt_language": "en",            # STT 인식 언어 ("en": 영어 전용, "auto": 99개 언어 자동감지)
    "source_lang": "en",             # 번역 출발 언어. "auto"면 인식 결과가 번역기 source를 갱신한다.
    "target_lang": "ko",             # 번역 도착 언어. 한국어 제품은 ko로 고정한다.
    "ui_lang": "ko",                 # 화면 언어. 한국어 제품은 ko, 글로벌은 사용자가 고른다.
    "device": "cpu",                 # 초기 기본 연산 디바이스: CPU
    "compute_type": "int8",          # 초기 기본 연산 타입: int8 (CPU 초경량 저지연)
    "vad_threshold": 0.006,          # RMS 에너지 임계값
    "silence_duration_sec": 0.45,    # 침묵 감지 시간 (0.45초: 자연스러운 발화 호흡 유지 및 문장 단절 방지)
    "max_buffer_sec": 2.5,           # 최대 음성 버퍼 시간 (2.5초마다 실시간 분할)
    "show_original": True,           # 영어 원문 병기 여부
    "font_size": 22,                 # 자막 폰트 크기
    "overlay_bg_opacity": 0.75,      # 자막 배경 불투명도
    "text_color": "#FFFFFF",         # 한글 텍스트 색상
    "original_color": "#BBBBBB",     # 영어 텍스트 색상
    "sentence_mode": True,           # 문장 단위 완결형 번역 모드
    "translation_engine": "google",  # 저사양 호환 기본값 (google, deepl, gemini, groq, exaone, gemma, hymt)
    "google_api_key": "",            # Google Cloud Translation API v2 Key (선택 사항, 공식 API 키)
    "deepl_api_key": "",             # DeepL Free/Pro API Key
    "gemini_api_key": "",            # Google Gemini Flash API Key
    "stt_provider": "local",         # local (Whisper), groq (Cloud LPU), deepgram (Cloud Nova-3)
    "groq_api_key": "",              # Groq Cloud API Key
    "groq_model": "whisper-large-v3-turbo",# Groq Cloud LPU 전용 모델 (whisper-large-v3-turbo, whisper-large-v3)
    "deepgram_api_key": "",          # Deepgram Cloud API Key
    "deepgram_model": "nova-3",      # Deepgram Nova 전용 모델 (nova-3, nova-2, nova-2-general)
    "deepgram_endpointing_ms": 500,
    "deepgram_no_delay": False,
    "translation_trace_enabled": False,  # 원문·번역문 진단 로그. 켤 때만 output/logs/translation.jsonl
    "deepgram_keywords": "",         # Deepgram 고유명사 키워드 부스팅 (예: "TermA:2.0, TermB:2.0")
    "click_through": False,          # 마우스 클릭 통과 여부
    "show_engine_badge": True,       # 상단 실시간 엔진 뱃지 표시 여부
    "show_speaker": True,            # 자막 표시창 화자(이름) 태그 표시 여부
    "use_context_prompt": False,     # 이전 문맥 프롬프트 보정 (옵션, 기본 OFF)
    "use_pre_padding": False,        # 발화 시작 0.2초 사전 버퍼링 (옵션, 기본 OFF)
    "window_geometry": [200, 680, 900, 240], # x, y, width, height
    "screen_translate_enabled": False,       # 화면 번역 감시 활성화 여부
    "screen_roi": None,                      # [x, y, width, height] 화면 감시 관심 영역 (단일 호환)
    "screen_rois": [],                       # [[x, y, width, height], ...] 다중 감시 관심 영역 목록
    "screen_check_interval_ms": 250,         # 화면 캡처 주기 (ms)
    "screen_overlay_geometry": [200, 500, 900, 230], # 화면 번역 자막 창 위치
    "screen_click_through": False,           # 화면 자막 창 마우스 관통 여부
    "screen_snap_to_roi": False,             # 관심 영역 주변 자동 밀착(Snap) 모드 여부
    "screen_ocr_preprocess": True,           # 게임 폰트 CLAHE 적응형 대비 강화 전처리 활성화 여부
    "screen_subtitle_duration": 0,           # 화면 자막 유지 시간 (초, 0=새 자막 감지 시까지 무제한 영구 유지)
    "subtitle_stroke_width": 0,              # 자막 글씨 외곽선/효과 (0=기본 순수 소프트 섀도우 시스템 부하 0%, 1~5=외곽선 스트로크)
    "letter_spacing": 2.0,                   # 자막 글자 자간 간격 (px, 0.0~4.0, 2.0=외곽선 뭉침 방지 가독성 최적화)
    "screen_clean_box": True,                # 클린 텍스트 모드에서 자막 뒤 은은한 반투명 라운드 박스 표시 여부 (테두리 라인 없음)
    "subtitle_alignment": "center",          # 자막 정렬 방식 ("center": 영문·한글 가운데 정렬)
    "typewriter_effect": False,              # 한국어 번역문 타자기 효과 (사용하지 않음, 완성 문장 즉시 표시)
    "control_panel_geometry": [80, 40, 1080, 680], # 컨트롤 패널 창 기본 크기 및 위치 (노트북/데스크톱 최적화 컴팩트 규격)
    "auto_start_audio": False,               # 프로그램 실행 시 오디오 통역 자동 시작 여부 (기본: 정지 상태)
    "auto_start_screen": False,              # 프로그램 실행 시 화면 실시간 번역 자동 시작 여부 (기본: 정지 상태)
    "audio_overlay_visible": True,           # 오디오 자막 오버레이 창 표시 여부
    "screen_overlay_visible": True,          # 화면 번역 자막 오버레이 창 표시 여부
    "screen_show_roi_border": False,         # 화면 번역 감시 관심 영역(ROI) 외곽 엣지(테두리) 오버랩 표시 여부
    "speaker_diarization_enabled": False,    # 실시간 다중 화자 분리(음색 지문 감별) 활성화 여부
    "speaker_segmentation_enabled": True,    # 2단계: Pyannote 3.0 초경량(6MB) 발화 세그멘테이션 결합 여부
    "speaker_similarity_threshold": 0.42,    # 화자 분리 유사도 임계값 (0.25 ~ 0.65, 기본 0.42)
    "speaker_cluster_distance_threshold": 0.5,  # 교대 군집 거리: 화자 유사도와 독립
    "speaker_match_margin": 0.08,           # 1위/2위 후보 점수차가 작으면 미확정
    "speaker_min_register_sec": 1.0,        # 같은 로컬 화자의 누적 단독 발화 길이
    "speaker_window_sec": 5.0,              # 최근 음성 문맥, 새 캡처 청크마다 분석
    "speaker_max_count": 2,                  # 최대 화자 수 (2: 2인 대화/인터뷰 고정, 3: 트리오, 4: 패널, 8: 다인원)
    "speaker_aliases": {},                   # 화자 실명/별칭 매핑 {"화자 1": "진행자", "화자 2": "게스트"}
    "speaker_mutes": {},                     # 화자별 번역 제외 여부 {"화자 1": True(번역제외/뮤트), "화자 2": False}
    "speaker_ocr_auto_mapping": True,        # 화면 OCR 대화 화자명 감지 시 음성 화자 자동 매핑 여부
    "dubbing_enabled": False,                # 실시간 AI 음성 더빙(Edge-TTS) 활성화 여부
    "dubbing_volume": 80,                    # 더빙 음성 볼륨 (0 ~ 100)
    "dubbing_speed": "+10%",                 # 더빙 음성 속도 (+0%, +10%, +20% 등)
    "dubbing_interrupt": False,              # 새 대사 유입 시 이전 음성 즉각 끊기 여부 (False: 끝까지 온전히 순차 재생)
    "dubbing_source_audio": True,            # 오디오 음성 번역 더빙 출력 여부
    "dubbing_source_screen": False,          # 화면 OCR 번역 더빙 출력 여부
    "speaker_dubbing_mutes": {},             # 화자별 더빙 제외 여부 {"화자 1": True(더빙제외), "화자 2": False}
    "speaker_voices": {},                    # 화자별 음성 매핑 {"화자 1": "auto", "화자 2": "ko-KR-SunHiNeural"}
    "dubbing_echo_cancellation": True,       # 더빙 음성이 마이크/루프백으로 재유입되어 무한 번역되는 에코 루프 자동 차단
    "audio_capture_device": "default",       # 오디오 캡처 루프백 장치 ("default" 또는 특정 장치명)
    "dubbing_output_device": "default",      # 더빙 오디오 출력 장치 ("default" 또는 특정 장치명)
    "dubbing_echo_threshold": 0.72,          # 순수 TTS 에코 차단 임계값 (0.72: 순수 TTS(0.81+) 차단, 혼합 원문(0.52) 보존)
    "audio_passthrough_enabled": True,       # 가상 채널 분리 시 원본 사운드를 헤드폰으로 실시간 패스스루
    "audio_passthrough_volume": 100,         # 원본 사운드 패스스루 기본 볼륨 (0 ~ 100%)
    "original_volume": 100,                  # 원본 사운드(앱/브라우저) 볼륨 (0 ~ 100%)
    "audio_ducking_enabled": True,           # 더빙 발화 시 원본 사운드 볼륨 자동 감소 (오디오 덕킹)
    "audio_ducking_volume": 25,              # 더빙 발화 중 원본 사운드 감쇄 볼륨 (0 ~ 100%, 기본 25%)
    "content_tempo_preset": "smart",         # 콘텐츠 템포 프리셋 ("smart", "youtube", "news", "interview", "movie", "documentary")
    "custom_presets": {},                    # 사용자 정의 커스텀 프리셋 {"preset_id": {"name": "...", "desc": "...", "config": {...}}}
    "llm_backend": "embedded",                 # 로컬 LLM 백엔드: "embedded" (내장 GGUF Standalone 기본) 또는 "ollama" (Ollama 호환 연동)
    "selected_llm_model": "exaone-3.5-2.4b", # 현재 선택된 로컬 LLM 모델 태그/파일
    "custom_model_dir": "D:\\AI_Models",     # 공용 모델 저장 폴더 (GGUF 및 HuggingFace 캐시 우선 탐색)
    "domain_glossary_enabled": True,         # AI 도메인 용어집 및 STT 사전 음운 교정 활성화
    "auto_youtube_detect": False,            # 브라우저 재생 중인 유튜브 영상 자동 감지 및 Ground-Truth 사전 자동 생성 (기본값 OFF)
    "gpu_warmup_on_startup": True,           # 프로그램 구동 시 GPU 로컬 LLM 1-Token 즉시 예열 (False: 번역 시작 시 예열)
    "inplace_hotkey": "F4",                  # 화면 제자리 즉시 번역(In-Place Snapshot AR) 전역 단축키
}

CONTENT_TEMPO_PRESETS = {
    "smart": {
        "name": "🧠 스마트 자동 적응 (Smart Adaptive)",
        "short_name": "🧠 스마트 자동",
        "desc": "로컬·Groq STT 호흡과 더빙 속도를 발화 WPM에 맞춥니다",
        "silence_duration_sec": 0.45,
        "max_buffer_sec": 2.5,
        "dubbing_speed": "+10%",
        "vad_threshold": 0.006,
    },
    "youtube": {
        "name": "⚡ 유튜브 / 스트리밍 (Fast & Casual)",
        "short_name": "⚡ 유튜브 / 방송",
        "desc": "짧은 호흡과 빠른 더빙. 로컬 STT 침묵 0.30초",
        "silence_duration_sec": 0.30,
        "max_buffer_sec": 1.8,
        "dubbing_speed": "+25%",
        "vad_threshold": 0.005,
    },
    "news": {
        "name": "📰 뉴스 / 브리핑 (Formal & Crisp)",
        "short_name": "📰 뉴스 / 발표",
        "desc": "또박또박한 전달과 빠른 더빙. 로컬 STT 침묵 0.40초",
        "silence_duration_sec": 0.40,
        "max_buffer_sec": 2.2,
        "dubbing_speed": "+15%",
        "vad_threshold": 0.006,
    },
    "interview": {
        "name": "🎙️ 인터뷰 / 팟캐스트 (Conversational)",
        "short_name": "🎙️ 인터뷰 / 대담",
        "desc": "대화 호흡을 보존합니다. 로컬 STT 침묵 0.50초",
        "silence_duration_sec": 0.50,
        "max_buffer_sec": 2.5,
        "dubbing_speed": "+10%",
        "vad_threshold": 0.006,
    },
    "movie": {
        "name": "🎬 영화 / 드라마 (Cinematic)",
        "short_name": "🎬 영화 / 드라마",
        "desc": "BGM에 둔감하고 여운을 남깁니다. 로컬 STT 침묵 0.60초",
        "silence_duration_sec": 0.60,
        "max_buffer_sec": 3.0,
        "dubbing_speed": "+5%",
        "vad_threshold": 0.008,
    },
    "documentary": {
        "name": "🌿 다큐멘터리 / 강의 (Narrative)",
        "short_name": "🌿 다큐 / 강의",
        "desc": "긴 서술문을 로컬 STT에서 완결합니다. 침묵 0.75초",
        "silence_duration_sec": 0.75,
        "max_buffer_sec": 3.8,
        "dubbing_speed": "+0%",
        "vad_threshold": 0.007,
    },
}

BUILTIN_PRESETS = {
    "low_spec": {
        "key": "low_spec",
        "icon": "🌱",
        "name": "🌱 저사양 호환 (CPU)",
        "short_name": "🌱 저사양",
        "desc": "번역: Google 번역 (무설치/무키 즉시 번역) | 디바이스: CPU (int8 초경량) | 템포: 스마트 자동적응",
        "device": "cpu",
        "compute_type": "int8",
        "stt_provider": "local",
        "model_size": "distil-small.en",
        "stt_language": "en",
        "translation_engine": "google",
        "content_tempo_preset": "smart",
        "requires_model": None,
        "requires_api_key": None,
    },
    "live": {
        "key": "live",
        "icon": "⚡",
        "name": "⚡ 초저지연 라이브",
        "short_name": "⚡ 초저지연",
        "desc": "번역: Tencent Hy-MT2 1.8B (초고속 로컬 SLM) | STT: distil-small.en | 템포: 유튜브 (0.3s)",
        "device": "cuda",
        "compute_type": "float16",
        "stt_provider": "local",
        "model_size": "distil-small.en",
        "stt_language": "en",
        "translation_engine": "hymt",
        "content_tempo_preset": "youtube",
        "requires_model": "hymt",
        "requires_api_key": None,
    },
    "balance": {
        "key": "balance",
        "icon": "⚖️",
        "name": "⚖️ 스마트 밸런스",
        "short_name": "⚖️ 밸런스",
        "desc": "번역: LG EXAONE 3.5 2.4B (한국어특화) | STT: distil-small.en | 템포: 스마트 WPM 자동적응",
        "device": "cuda",
        "compute_type": "float16",
        "stt_provider": "local",
        "model_size": "distil-small.en",
        "stt_language": "en",
        "translation_engine": "exaone",
        "content_tempo_preset": "smart",
        "requires_model": "exaone",
        "requires_api_key": None,
    },
    "cinema": {
        "key": "cinema",
        "icon": "🎬",
        "name": "🎬 영화 · 드라마",
        "short_name": "🎬 영화·드라마",
        "desc": "번역: TranslateGemma 4B (초월번역) | 템포: 시네마 (0.6s & BGM필터) | STT: CUDA",
        "device": "cuda",
        "compute_type": "float16",
        "stt_provider": "local",
        "model_size": "distil-large-v3.5",
        "stt_language": "en",
        "translation_engine": "gemma",
        "content_tempo_preset": "movie",
        "requires_model": "translategemma",
        "requires_api_key": None,
    },
    "masterpiece": {
        "key": "masterpiece",
        "icon": "🔮",
        "name": "🔮 로컬 마스터피스 (7.8B)",
        "short_name": "🔮 마스터피스",
        "desc": "번역: LG EXAONE 3.5 7.8B (최고지능 심층번역) | 템포: 인터뷰 (0.5s) | STT: CUDA",
        "device": "cuda",
        "compute_type": "float16",
        "stt_provider": "local",
        "model_size": "distil-large-v3.5",
        "stt_language": "en",
        "translation_engine": "exaone7b",
        "content_tempo_preset": "interview",
        "requires_model": "exaone7b",
        "requires_api_key": None,
    },
    "global": {
        "key": "global",
        "icon": "🌐",
        "name": "🌐 글로벌 다국어 (99개 언어)",
        "short_name": "🌐 다국어",
        "desc": "STT: Whisper Large Turbo (99개 언어 자동감지) | 번역: Tencent Hy-MT2 1.8B | 일·중·영·다국어 실시간 통역",
        "device": "cuda",
        "compute_type": "float16",
        "stt_provider": "local",
        "model_size": "large-v3-turbo",
        "stt_language": "auto",
        "translation_engine": "hymt",
        "content_tempo_preset": "smart",
        "requires_model": "hymt",
        "requires_api_key": None,
    },
}


def _build_global_presets():
    """글로벌 제품 프리셋. 표시 문구는 i18n.GLOBAL_PRESET_COPY가 단일 출처다."""
    from src.i18n import GLOBAL_PRESET_COPY
    specs = {
        "low_spec": {
            "key": "low_spec",
            "icon": "🌱",
            "device": "cpu",
            "compute_type": "int8",
            "stt_provider": "local",
            "model_size": "small",
            "stt_language": "auto",
            "translation_engine": "google",
            "content_tempo_preset": "smart",
            "requires_model": None,
            "requires_api_key": None,
        },
        "live": {
            "key": "live",
            "icon": "⚡",
            "device": "cuda",
            "compute_type": "float16",
            "stt_provider": "local",
            "model_size": "small",
            "stt_language": "auto",
            "translation_engine": "hymt",
            "content_tempo_preset": "youtube",
            "requires_model": "hymt",
            "requires_api_key": None,
        },
        "balance": {
            "key": "balance",
            "icon": "⚖️",
            "device": "cuda",
            "compute_type": "float16",
            "stt_provider": "local",
            "model_size": "small",
            "stt_language": "auto",
            "translation_engine": "hymt",
            "content_tempo_preset": "smart",
            "requires_model": "hymt",
            "requires_api_key": None,
        },
        "cinema": {
            "key": "cinema",
            "icon": "🎬",
            "device": "cuda",
            "compute_type": "float16",
            "stt_provider": "local",
            "model_size": "large-v3-turbo",
            "stt_language": "auto",
            "translation_engine": "gemma",
            "content_tempo_preset": "movie",
            "requires_model": "translategemma",
            "requires_api_key": None,
        },
    }
    presets = {}
    for key, spec in specs.items():
        item = dict(spec)
        item.update(GLOBAL_PRESET_COPY[key])
        presets[key] = item
    return presets


GLOBAL_PRESETS = _build_global_presets()


def active_builtin_presets():
    """지금 제품 라인의 빌트인 프리셋."""
    from src.product import is_global
    return GLOBAL_PRESETS if is_global() else BUILTIN_PRESETS


def uses_local_tempo_vad(config=None):
    """Deepgram live uses server VAD + SpeechSegmenter; local tempo VAD is Groq/Whisper only."""
    return (config or {}).get("stt_provider") != "deepgram"


def tempo_scope_caption(config=None):
    from src.i18n import tr
    if uses_local_tempo_vad(config):
        return tr("tempo_scope_local")
    return tr("tempo_scope_deepgram")


def tempo_deepgram_notice(config=None):
    from src.i18n import tr
    if uses_local_tempo_vad(config):
        return tr("tempo_notice_deepgram_sub")
    return tr("tempo_notice_deepgram")


def tempo_preset_desc(preset_key, config=None):
    from src.i18n import tr
    preset = CONTENT_TEMPO_PRESETS.get(preset_key) or CONTENT_TEMPO_PRESETS["smart"]
    desc_key = f"tempo_{preset_key}_desc"
    desc = tr(desc_key)
    if desc == desc_key:
        desc = preset.get("desc", "")
    if uses_local_tempo_vad(config):
        return desc
    return tr("tempo_desc_deepgram_suffix", desc=desc)

def _apply_hardware_and_model_detection(cfg: dict):
    """
    초기 설치 후 최초 실행 시:
    - 기존 로컬 모델들을 자동 감지하여 상태를 갱신/로깅하되,
    - 한국어 제품은 '저사양 호환 (CPU)' 프리셋으로 시작한다.
    - 글로벌 제품은 다국어 Whisper small과 영어 자막으로 시작한다.
    """
    from src.product import is_global
    cfg["device"] = "cpu"
    cfg["compute_type"] = "int8"
    cfg["translation_engine"] = "google"
    cfg["content_tempo_preset"] = "smart"
    if is_global():
        cfg["model_size"] = "small"
        cfg["stt_language"] = "auto"
        cfg["source_lang"] = "auto"
        cfg["target_lang"] = "en"
        cfg["ui_lang"] = "en"
        label = "글로벌 에디션 (Whisper small, 자동 감지, 자막 언어 en)"
    else:
        cfg["model_size"] = "distil-small.en"
        cfg["stt_language"] = "en"
        cfg["source_lang"] = "en"
        cfg["target_lang"] = "ko"
        cfg["ui_lang"] = "ko"
        label = "저사양 호환 (CPU)"

    try:
        from src.stt_model_manager import STTModelManager, AVAILABLE_STT_MODELS
        detected = [m["id"] for m in AVAILABLE_STT_MODELS if STTModelManager.is_model_installed(m["id"])]
        print(f"[Config] 초기 실행: '{label}' 프리셋 적용 완료. (감지된 기설치 모델: {detected})")
    except Exception as e:
        print(f"[Config] 기설치 모델 감지 중 오류: {e}")


def _lock_product_languages(cfg: dict, raw: dict | None = None):
    """한국어 제품의 도착 언어는 ko다. 글로벌은 저장되지 않은 도착 언어를 en으로 둔다."""
    from src.i18n import detect_system_ui_language, normalize_ui_language
    from src.product import is_global

    saved = raw or {}

    saved_ui = saved.get("ui_lang")
    if saved_ui:
        cfg["ui_lang"] = normalize_ui_language(saved_ui)
    elif is_global():
        cfg["ui_lang"] = detect_system_ui_language()
    else:
        cfg["ui_lang"] = "ko"

    if not is_global():
        cfg["target_lang"] = "ko"
        return cfg
    if cfg.get("model_size") == "distil-small.en":
        cfg["model_size"] = "small"
    if not saved.get("target_lang"):
        cfg["target_lang"] = "en"
    if not saved.get("source_lang"):
        cfg["source_lang"] = "auto"
    return cfg


def _consume_clean_install_marker(target_file):
    """설치 프로그램이 '기존 설정 초기화'로 설치했으면, 그 설치 이후 첫 실행에서 이 사용자의 설정을 지운다.
    관리자 권한 설치는 설치 프로그램이 다른 계정의 AppData 를 보게 되어 실제 사용자 설정을 못 지울 수 있다.
    Program Files 에서는 표식을 지울 수 없으므로, 처리한 설치 ID 를 사용자 폴더에 기록해 한 번만 적용한다."""
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    try:
        with open(os.path.join(exe_dir, "clean_install.id"), "r", encoding="utf-8", errors="ignore") as f:
            install_id = f.read().strip()
    except OSError:
        return
    if not install_id:
        return
    user_dir = os.path.dirname(target_file)
    done_file = os.path.join(user_dir, "clean_install.done")
    try:
        with open(done_file, "r", encoding="utf-8") as f:
            if f.read().strip() == install_id:
                return
    except OSError:
        pass
    for path in (target_file, os.path.join(exe_dir, "config.json")):
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"[Config] 클린 설치: 이전 설정 삭제 ({path})")
        except OSError as e:
            print(f"[Config] 클린 설치: 이전 설정 삭제 실패 ({path}): {e}")
    try:
        os.makedirs(user_dir, exist_ok=True)
        with open(done_file, "w", encoding="utf-8") as f:
            f.write(install_id)
    except OSError:
        pass


def load_config(config_file=None):
    global CONFIG_FILE
    target_file = config_file or get_config_file_path()
    CONFIG_FILE = target_file

    if getattr(sys, "frozen", False) and not config_file:
        _consume_clean_install_marker(target_file)

    # 배포 환경에서 APPDATA 설정 파일이 아직 없으면 exe 폴더의 템플릿 복사
    if not os.path.exists(target_file) and getattr(sys, "frozen", False) and not config_file:
        exe_cfg = os.path.join(os.path.dirname(sys.executable), "config.json")
        if os.path.exists(exe_cfg) and os.path.abspath(exe_cfg) != os.path.abspath(target_file):
            try:
                import shutil
                os.makedirs(os.path.dirname(target_file), exist_ok=True)
                shutil.copy2(exe_cfg, target_file)
            except Exception as e:
                print(f"[Config] 초기 템플릿 복사 실패: {e}")

    if os.path.exists(target_file):
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                merged.update(cfg)

                # screen_rois와 screen_roi 상호 동기화 (유효한 좌표만 유지)
                if "screen_rois" in cfg and isinstance(cfg["screen_rois"], list):
                    merged["screen_rois"] = [r for r in cfg["screen_rois"] if len(r) == 4 and r[2] > 20 and r[3] > 20]
                elif "screen_roi" in cfg and cfg["screen_roi"] and len(cfg["screen_roi"]) == 4:
                    merged["screen_rois"] = [cfg["screen_roi"]]
                else:
                    merged["screen_rois"] = []

                merged["screen_roi"] = merged["screen_rois"][0] if merged["screen_rois"] else None
                return _lock_product_languages(merged, cfg)
        except Exception as e:
            print(f"[Config] 설정 파일 로드 실패, 기본값 사용: {e}")

    # 새 설치 또는 설정 파일 부재 시: 저사양 호환 (CPU) 프리셋으로 초기 생성
    cfg = DEFAULT_CONFIG.copy()
    _apply_hardware_and_model_detection(cfg)
    _lock_product_languages(cfg, {})
    try:
        save_config(cfg, target_file)
    except Exception:
        pass
    return cfg

_config_save_lock = threading.Lock()


def _replace_with_retry(src, dst, attempts=8, delay=0.05):
    """Windows에서 대상 파일이 잠시 잠기면 os.replace가 WinError 5로 실패한다."""
    last_error = None
    for attempt in range(attempts):
        try:
            if os.path.exists(dst):
                try:
                    os.chmod(dst, stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
            os.replace(src, dst)
            return
        except PermissionError as e:
            last_error = e
            if attempt + 1 < attempts and delay:
                time.sleep(delay * (attempt + 1))
    if last_error is not None:
        raise last_error


def _restrict_config_permissions(path):
    """설정 파일은 현재 사용자만 읽게 한다. API 키가 들어 있다."""
    try:
        if os.name == "nt":
            user = os.environ.get("USERNAME")
            if not user:
                return
            import subprocess
            subprocess.run(
                ["icacls", path, "/inheritance:r", "/grant:r", f"{user}:(R,W)"],
                capture_output=True,
                timeout=3,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def _write_json_atomic(path, cfg, attempts=8, delay=0.05):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_file = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    try:
        _replace_with_retry(tmp_file, path, attempts=attempts, delay=delay)
        _restrict_config_permissions(path)
    except PermissionError:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        _restrict_config_permissions(path)
    finally:
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except OSError:
                pass


def save_config(cfg, config_file=None):
    global CONFIG_FILE
    target_file = config_file or get_config_file_path()
    CONFIG_FILE = target_file
    with _config_save_lock:
        try:
            _write_json_atomic(target_file, cfg)
        except Exception as e:
            print(f"[Config] 설정 파일 저장 실패: {e}")
            if config_file:
                raise
            try:
                from src.app_paths import roaming_data_dir
                fallback_file = os.path.join(roaming_data_dir(), "config.json")
                if os.path.abspath(fallback_file) == os.path.abspath(target_file):
                    print("[Config] 폴백 설정 파일 저장 실패: 원본 경로와 동일합니다.")
                    return
                _write_json_atomic(fallback_file, cfg)
                CONFIG_FILE = fallback_file
            except Exception as e2:
                print(f"[Config] 폴백 설정 파일 저장 실패: {e2}")
