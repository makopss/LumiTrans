import queue
import threading
import time
import io
import re
import requests
import numpy as np
from scipy.io import wavfile
from faster_whisper import WhisperModel
from .translator import RealtimeTranslator
from .speech_segmenter import SpeechSegmenter
from .pipeline_trace import PipelineTrace
from .audio_chunk import CapturedAudio, offer_queue
from .speaker_tracking import align_transcript
from .stt_model_manager import get_hf_hub_cache_dir, STTModelManager
from src.i18n import tr

HALLUCINATIONS = {
    "you", "thank you", "thank you.", "thank you very much.", "thanks for watching!",
    "thanks for watching.", "thanks for watching", "thank you for watching.", "thank you for watching", "bye.", "bye bye.", "subscribe", "subtitles by",
    "please subscribe", "see you next time", "thank you so much.", "the end.",
    "subtitles", "transcript", "watching", "like and subscribe", "like and subscribe.",
    "i'll see you in the next one.", "i'll see you in the next one",
    "see you in the next one.", "see you in the next one",
    "thanks for listening.", "thanks for listening", "thank you for listening.", "thank you for listening",
    "thank you for coming.", "thank you for coming",
    "music", "[music]", "(music)", "translated by", "all rights reserved.",
    # 공통 침묵/간투사/유튜브 종결 환각 (Whisper 대규모 자막 학습 편향 방지)
    "and more", "and more.", "and many more", "and many more.",
    "and...", "...and", "and so on", "and so on.",
    "please like and subscribe", "please like and subscribe.",
    "don't forget to like and subscribe", "don't forget to like and subscribe.",
    "subtitles by the amara.org community", "subtitles by the amara.org community.",
    "i will see you in the next video", "i will see you in the next video.",
    "you're welcome", "you're welcome.",
    "and read the text", "and read the text.", "read the text", "read the text.",
}

SENTENCE_ENDINGS = ('.', '?', '!')

def normalize_whisper_model_id(raw_model: str) -> str:
    """faster-whisper 모델 식별자 정규화 (외부 API 모델명 및 오타 방지)"""
    if not raw_model:
        return "distil-small.en"
    raw = str(raw_model).strip()
    mapping = {
        "whisper-large-v3-turbo": "large-v3-turbo",
        "whisper-large-v3": "large-v3",
        "whisper-large-v2": "large-v2",
        "distil-whisper-large-v3-en": "distil-large-v3",
        "distil-whisper-large-v3": "distil-large-v3",
        "distil-whisper-large-v2": "distil-large-v2",
        "distil-whisper-medium-en": "distil-medium.en",
        "distil-whisper-small-en": "distil-small.en",
        "distil-large-v3.5": "distil-whisper/distil-large-v3.5-ct2",
        "whisper-medium.en": "medium.en",
        "whisper-medium": "medium",
        "whisper-small.en": "small.en",
        "whisper-small": "small",
        "whisper-base.en": "base.en",
        "whisper-base": "base",
        "whisper-tiny.en": "tiny.en",
        "whisper-tiny": "tiny",
    }
    if raw in mapping:
        return mapping[raw]
    if raw.startswith("whisper-"):
        clean = raw.replace("whisper-", "")
        return mapping.get(clean, clean)
    return raw

def _resolve_local_model_target(model_id: str) -> tuple[str, str]:
    """
    model_id에 대해 로컬 디스크(번들 폴더 또는 캐시) 상의 실제 스냅샷 경로를 탐색합니다.
    반환값: (load_target_path_or_id, hub_cache_dir)
    """
    import os
    hub_cache = get_hf_hub_cache_dir()
    for m in STTModelManager.get_available_models():
        if m["id"] == model_id or m.get("hf_id") == model_id:
            folder = STTModelManager.get_model_folder_path(m["hf_id"])
            if folder:
                model_hub = os.path.dirname(folder)
                snap_dir = os.path.join(folder, "snapshots")
                if os.path.isdir(snap_dir) and os.listdir(snap_dir):
                    snaps = sorted(os.listdir(snap_dir), reverse=True)
                    for snap_name in snaps:
                        chosen_snap = os.path.join(snap_dir, snap_name)
                        if os.path.isdir(chosen_snap):
                            STTModelManager.heal_snapshot_symlinks(chosen_snap)
                            m_bin = os.path.join(chosen_snap, "model.bin")
                            if os.path.isfile(m_bin) and os.path.getsize(m_bin) > 10 * 1024 * 1024:
                                return chosen_snap, model_hub
                m_bin_direct = os.path.join(folder, "model.bin")
                if os.path.isfile(m_bin_direct) and os.path.getsize(m_bin_direct) > 10 * 1024 * 1024:
                    return folder, model_hub
            break
    return model_id, hub_cache

def is_cuda_installed() -> bool:
    """화면 표시·버튼 분기용: NVIDIA GPU 와 STT 가속 팩 파일이 있는지만 본다 (CUDA 를 초기화하지 않는다).
    실제 로드 가능 여부는 모델을 올릴 때 is_cuda_available() 로 검증하고, 실패하면 CPU 로 폴백한다."""
    try:
        from src.cuda_utils import is_cublas_installed
        return is_cublas_installed()
    except Exception as e:
        print(f"[STT] CUDA 설치 확인 중 오류: {e}")
        return False


def is_cuda_available() -> bool:
    """NVIDIA CUDA 가속 지원 여부 확인 (cuBLAS 12 유효성 및 ctranslate2/torch 종합 검증)"""
    try:
        from src.cuda_utils import is_stt_cuda_available, register_cuda_dll_directories
        register_cuda_dll_directories()
        return is_stt_cuda_available()
    except Exception as e:
        print(f"[STT] CUDA 가용성 검증 중 오류: {e}")
        return False

class EnglishTextNormalizer:
    """영문 STT 텍스트 전처리: 말더듬/반복 단어 제거, N-gram 구 반복 환각 박멸, 필러 워드 정제, 구두점 교정"""
    LEADING_FILLERS = re.compile(r'^(?:(?:um|uh|ah|er|hmm|mhm|oh)\b[,\s]*)+', re.IGNORECASE)

    @classmethod
    def deduplicate_repeats(cls, text: str) -> str:
        """
        임의 길이(1~12단어)의 모든 단어 및 구 반복 환각을 원문 손실 없이 완벽히 제거하는 N-gram 압축 엔진.
        예:
        - 'Ready, right? Right? Right? Right?' -> 'Ready, right?'
        - 'And at the end of each pipe, and at the end of each pipe...' -> 'And at the end of each pipe'
        - 'some of the smooth, some of the smooth, some...' -> 'some of the smooth'
        - 'Yeah, I'm, yeah, I'm, I'm, I'm, I'm...' -> 'Yeah, I'm'
        """
        if not text or not text.strip():
            return ""

        original = text.strip()

        # 1. 단어(아포스트로피 및 구두점 포함) 연속 중복 강력 압축 ("Right? Right? Right?" -> "Right?")
        s = re.sub(
            r"\b([A-Za-z0-9']+)[.,?!;:]*(?:\s+(?i:\1)[.,?!;:]*){2,}",
            r"\1",
            original
        )

        # 2. 토큰 리스트 기반 슬라이딩 윈도우 N-gram 반복 제거 (N: 12 down to 1)
        tokens = re.findall(r"\S+", s)
        if not tokens:
            return s

        def norm_token(t):
            return re.sub(r"[^\w']", "", t).lower()

        norm_keys = [norm_token(t) for t in tokens]

        changed = True
        iteration = 0
        while changed and iteration < 6:
            changed = False
            iteration += 1
            n_max = min(12, len(tokens) // 2)
            for n in range(n_max, 0, -1):
                i = 0
                new_tokens = []
                new_norm = []
                while i < len(tokens):
                    if i + 2 * n <= len(tokens):
                        pattern_keys = norm_keys[i : i + n]
                        if any(pattern_keys):
                            match_count = 1
                            while (
                                i + (match_count + 1) * n <= len(tokens)
                                and norm_keys[i + match_count * n : i + (match_count + 1) * n] == pattern_keys
                            ):
                                match_count += 1
                            if match_count > 1:
                                matched_chunk = list(tokens[i : i + n])
                                matched_chunk[-1] = matched_chunk[-1].rstrip(",")
                                new_tokens.extend(matched_chunk)
                                new_norm.extend(norm_keys[i : i + n])
                                i += match_count * n
                                changed = True
                                continue
                    new_tokens.append(tokens[i])
                    new_norm.append(norm_keys[i])
                    i += 1
                tokens = new_tokens
                norm_keys = new_norm
                if changed:
                    break

        # 3. 문미 불완전 부분 반복(partial prefix repetition) 감지 및 정리 (예: "...some of the smooth, some" -> "...some of the smooth")
        if len(tokens) >= 3:
            for n in range(min(6, len(tokens) - 1), 1, -1):
                target_pattern = norm_keys[-n - 1 : -1]
                last_token = norm_keys[-1]
                if target_pattern and last_token == target_pattern[0]:
                    tokens = tokens[:-1]
                    norm_keys = norm_keys[:-1]
                    break

        result = " ".join(tokens).strip()

        # 4. 말더듬 접속사/전치사 고립 꼬리 반복 정리 (예: ", and", ", or", ", of", ", at each, and")
        for _ in range(3):
            result = re.sub(
                r"[,;:\s]+(?:and|or|of|to|in|at|but|the|a|an|for|with|as|at\s+each|for\s+all|it\s+turns)\b[,;:\s]*$",
                "",
                result,
                flags=re.IGNORECASE
            ).strip()
            result = re.sub(
                r"[,;:]+\s*that\b[,;:\s]*$",
                "",
                result,
                flags=re.IGNORECASE
            ).strip()
            result = re.sub(r"[,;:\s]+[A-Za-z][,;:\s]*$", "", result).strip()
            result = re.sub(r"[,;:\s]+$", "", result).strip()

        # 5. 문두 쉼표/구두점 정리
        result = re.sub(r"^[,;:\s]+", "", result).strip()

        # 6. 문장 종결 부호 보존
        if original.endswith("?") and not result.endswith("?"):
            result += "?"
        elif original.endswith(".") and not result.endswith((".", "!", "?")):
            result += "."

        return result

    @classmethod
    def normalize(cls, text: str) -> str:
        if not text:
            return ""
        text = text.strip()
        # 1. 문두 단순 감탄사/필러 제거
        text = cls.LEADING_FILLERS.sub('', text).strip()
        if not text:
            return ""

        # 2. 문두/문미/문중 고질적 환각 어구("And more", "Thank you for watching" 등) 정제
        text = re.sub(r'^(?:and\s+(?:many\s+)?more\b[.,\s]*)+', '', text, flags=re.IGNORECASE).strip()
        text = re.sub(r'(?:[.,\s]*\band\s+(?:many\s+)?more\b[.,\s]*)+$', '', text, flags=re.IGNORECASE).strip()
        text = re.sub(r'\s*\band\s+(?:many\s+)?more[.,\s]+', ' ', text, flags=re.IGNORECASE).strip()
        text = re.sub(r'(?:(?:thank\s+you\s+(?:very\s+much\s+)?|thanks\s+)for\s+(?:watching|listening|coming)[.,\s]*)+$', '', text, flags=re.IGNORECASE).strip()
        text = re.sub(r'(?:[.,\s]*\b(?:and\s+)?read\s+the\s+text\b[.,\s]*)+$', '', text, flags=re.IGNORECASE).strip()
        text = re.sub(r'^(?:(?:and\s+)?read\s+the\s+text\b[.,\s]*)+', '', text, flags=re.IGNORECASE).strip()

        if not text:
            return ""

        # 3. 고성능 N-gram 토큰 단위 반복 환각 완벽 압축 (1~12단어 구, 구두점 통합)
        text = cls.deduplicate_repeats(text)

        # 4. Whisper 말더듬/웃음소리 반복 환각 필터 (예: "H-h-h-h-h-h...", "ha ha ha ha ha...")
        text = re.sub(r'\b([a-zA-Z])(?:-[a-zA-Z])+\b', r'\1', text)
        text = re.sub(r'(?:[a-zA-Z][- ]){4,}[a-zA-Z]?', '', text).strip()
        text = re.sub(r'([a-zA-Z])\1{4,}', r'\1', text).strip()

        # 5. 구두점 앞 공백 제거 (예: "word ." -> "word.")
        text = re.sub(r'\s+([,.:;?!])', r'\1', text)
        # 6. 연속 공백 정리
        text = re.sub(r'\s+', ' ', text).strip()
        # 7. 첫 글자 대문자화
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        return text


class SemanticClauseDetector:
    """언어학적 의미 단위(Clause) 및 문장 경계 판별기 (로컬/Groq STT 전용 고속 검사)"""
    STANDALONE_SHORT_WORDS = {
        'yes', 'yeah', 'yep', 'no', 'nope', 'nah',
        'okay', 'ok', 'sure', 'right', 'alright',
        'hello', 'hi', 'hey', 'bye', 'goodbye',
        'thanks', 'thank you', 'please', 'welcome',
        'exactly', 'correct', 'true', 'false', 'indeed',
        'sorry', 'pardon', 'wow', 'cool', 'great'
    }

    DANGLING_ENDINGS = {
        'of', 'to', 'in', 'for', 'with', 'on', 'at', 'from', 'by', 'about',
        'into', 'through', 'after', 'over', 'between', 'out', 'against',
        'during', 'without', 'before', 'under', 'around', 'among',
        'and', 'but', 'or', 'nor', 'yet', 'so', 'because', 'although',
        'since', 'while', 'where', 'if', 'unless', 'until', 'as', 'than',
        'whether', 'that', 'which', 'like', 'such',
        'a', 'an', 'the', 'my', 'your', 'his', 'her', 'our', 'their',
        'this', 'these', 'those', 'whose',
        'i', 'he', 'she', 'we', 'they',
        'not', 'just', 'then', 'also', 'more', 'even', 'up', 'down',
        'definitely', 'probably', 'certainly', 'actually', 'basically', 'really', 'simply', 'completely', 'absolutely',
        'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did',
        'will', 'would', 'shall', 'should', 'can', 'could', 'may', 'might', 'must',
        "i'm", "you're", "we're", "they're", "he's", "she's", "it's", "that's", "what's", "there's",
        "'m", "'re", "'s", "'ve", "'ll", "'d",
        'need', 'needs', 'want', 'wants', 'wanna', 'gonna', 'gotta',
        'ask', 'asked', 'tell', 'told', 'give', 'know', 'shows', 'say', 'says', 'said',
        'called', 'calls', 'call',
        # 미완결 형용사/수량사/서수/비교급 (뒤에 명사/보어가 필수적인 수식어)
        'most', 'first', 'second', 'last', 'best', 'worst',
        'all', 'some', 'any', 'every', 'each', 'both', 'either', 'neither',
        'many', 'few', 'little', 'much', 'less',
        # 목적어가 누락되기 쉬운 종결 타동사
        'make', 'makes', 'made', 'get', 'gets', 'got', 'take', 'takes', 'took',
        'put', 'puts', 'find', 'finds', 'found', 'think', 'thinks', 'thought',
        'felt', 'feel', 'show', 'shows', 'showed'
    }

    TERMINAL_PUNCT = ('.', '?', '!')

    @classmethod
    def get_last_word(cls, text: str) -> str:
        words = re.findall(r"[a-zA-Z']+", text)
        return words[-1].lower() if words else ""

    @classmethod
    def is_standalone_word(cls, text: str) -> bool:
        """Yes, No, Okay 등 단독으로 완결된 의미를 갖는 단문인지 판별"""
        clean = re.sub(r'[^\w\s]', '', text).strip().lower()
        return clean in cls.STANDALONE_SHORT_WORDS

    @classmethod
    def is_dangling(cls, text: str) -> bool:
        """문장의 마지막 단어가 미완결 품사(전치사, 접속사, 쉼표 등)인지 검사"""
        t_clean = text.strip()
        if not t_clean:
            return False
        if t_clean.endswith((',', ':', ';', '-', '—', '...', '..')):
            return True
        words = re.findall(r"[a-zA-Z']+", text)
        if not words:
            return False
        last_word = words[-1].lower()
        if last_word in cls.DANGLING_ENDINGS:
            return True
        has_terminal = any(t_clean.endswith(p) for p in cls.TERMINAL_PUNCT)
        if not has_terminal and len(words) >= 2:
            if words[-2].lower() in ('and', 'or', 'but', 'nor', 'so', 'because'):
                return True
        return False

    @classmethod
    def is_complete_sentence(cls, text: str) -> bool:
        """마침표/물음표/느낌표로 종결되었으며 내용이 완결되었는지 판별"""
        text = text.strip()
        if not text:
            return False
        has_terminal = any(text.endswith(p) for p in cls.TERMINAL_PUNCT)
        if not has_terminal:
            return False
        if cls.is_dangling(text):
            return False
        words = text.split()
        if len(words) < 4 and not cls.is_standalone_word(text):
            return False
        return True

    @classmethod
    def should_flush(cls, text: str, elapsed_silence: float, base_silence: float = 0.45) -> bool:
        """적응형 침묵 타이밍(Adaptive Silence Timeout) 판별"""
        text = text.strip()
        if not text:
            return False
        word_count = len(text.split())
        scale = max(0.5, min(2.0, base_silence / 0.45))
        if word_count <= 2 and cls.is_standalone_word(text):
            return elapsed_silence >= max(0.30, 0.55 * scale)
        if cls.is_dangling(text):
            return elapsed_silence >= max(1.8, 2.2 * scale)
        if word_count < 4:
            return elapsed_silence >= max(1.8, 2.2 * scale)
        if cls.is_complete_sentence(text):
            return elapsed_silence >= max(0.25, base_silence)
        if word_count >= 6:
            return elapsed_silence >= max(0.38, 0.65 * scale)
        return elapsed_silence >= max(0.48, 0.80 * scale)

    @classmethod
    def check_clause_boundary(cls, accumulated: str, latest_chunk: str, max_words: int = 24) -> bool:
        """실시간 발화 중 문장이 길어질 때 의미 단위(절 경계)에서 분할할지 판별"""
        words = accumulated.split()
        word_count = len(words)
        if word_count < 4:
            return False
        if cls.is_complete_sentence(accumulated):
            return True
        mid_1 = max(5, int(max_words * 0.42))
        mid_2 = max(7, int(max_words * 0.58))
        high = max(10, int(max_words * 0.78))
        if word_count >= mid_1 and not cls.is_dangling(accumulated):
            if any(accumulated.rstrip().endswith(end) for end in (',', ';', ':', '--', '—')):
                return True
        if word_count >= mid_2 and not cls.is_dangling(accumulated):
            clause_markers = [', and ', ', but ', ', so ', ', because ', ', while ', ', although ', ' because ', ' although ']
            if any(marker in accumulated.lower() for marker in clause_markers):
                return True
        if word_count >= high and not cls.is_dangling(accumulated):
            return True
        if word_count >= max_words:
            return True
        return False


class STTWorker(threading.Thread):
    def __init__(self, audio_queue: queue.Queue, subtitle_callback=None, preview_callback=None, config=None, dubbing_engine=None, progress_callback=None):
        super().__init__(daemon=True)
        self.audio_queue = audio_queue
        self.subtitle_callback = subtitle_callback
        self.preview_callback = preview_callback
        self.config = config or {}
        self._active_stt_provider = self.config.get("stt_provider", "local")
        self.dubbing_engine = dubbing_engine
        self._progress_callback = progress_callback
        
        self.model_size = self.config.get("model_size", "distil-small.en")
        self.device = self.config.get("device", "cuda")
        self.compute_type = self.config.get("compute_type", "float16")
        self.sentence_mode = self.config.get("sentence_mode", True)
        self.use_context_prompt = self.config.get("use_context_prompt", False)
        self.stt_language = self.config.get("stt_language", "en")
        
        # 다중 엔진 번역기 초기화
        self.translator = RealtimeTranslator(config=self.config, source="en", target="ko")
        self.model = None
        # 설정(self.device)과 달리 실제로 모델이 올라간 장치. CUDA 요청이 CPU 로 떨어진 상태를 구분한다.
        self._loaded_device = None
        self._last_stt_name = None
        self.sensevoice_model = None
        self.moonshine_model = None
        self.parakeet_model = None
        self.running = False
        self._groq_cooldowns = {}
        self._local_model_loading = False

        # 초경량 3D-Speaker AI 화자 감별기 (화자 분리 옵션 켤 때만 지연 로딩, 시작 지연 0초)
        self.speaker_identifier = None
        if self.config.get("speaker_diarization_enabled", False):
            try:
                self._report_load_progress(tr("splash_prep_diarization"), 52)
                from .speaker_identifier import SpeakerIdentifier
                self.speaker_identifier = SpeakerIdentifier(config=self.config)
            except Exception as e:
                print(f"[STT] SpeakerIdentifier 초기화 예외: {e}")
                self.speaker_identifier = None
        self.current_sentence_speaker = None
        
        # 비동기 번역 큐 및 워커 스레드
        self.trans_queue = queue.Queue(maxsize=32)
        self.trans_worker = threading.Thread(target=self._translation_loop, daemon=True)
        
        # 문장 누적 버퍼 및 동적 문맥 프롬프트 (옵션 켰을 때만 사용)
        self.sentence_buffer = []
        self.last_speech_time = time.time()
        self.last_context_prompt = ""

        # 콘텐츠 템포 및 스마트 적응 변수
        self.audio_capture = None
        self.tempo_callback = None
        from src.config import CONTENT_TEMPO_PRESETS
        self.content_tempo_preset = self.config.get("content_tempo_preset", "smart")
        preset = CONTENT_TEMPO_PRESETS.get(self.content_tempo_preset, CONTENT_TEMPO_PRESETS["smart"])
        self.silence_duration_sec = float(preset.get("silence_duration_sec", 0.45))
        self.max_buffer_sec = float(preset.get("max_buffer_sec", 2.5))
        self.estimated_wpm = 135.0  # 기본 일반 대화 WPM 기준값
        self.last_tempo_desc = ""

        # Deepgram 실시간 WebSocket 라이브 스트리머 (플러그앤플레이 독립 모듈)
        self.deepgram_streamer = None
        self._speech_events = queue.Queue()
        self._segmenter = SpeechSegmenter()
        self._segment_source = ''
        self._trace = None
        self._draining = False
        self._paused = False
        self._pause_generation = 0
        self._model_reload_requested = False
        self.pre_context = None
        self._init_deepgram_streamer()

        self._load_model()

    def set_pre_context(self, context):
        """도메인 사전 및 STT/LLM 교정 컨텍스트 설정 및 번역기에 전파"""
        self.pre_context = context
        if hasattr(self, "translator") and self.translator:
            self.translator.set_pre_context(context)
        # Deepgram 키워드 파라미터 갱신 적용
        if context and context.initial_prompt_tokens:
            self._init_deepgram_streamer()
        if context and not context.is_empty():
            try:
                print(f"[STT] [도메인 사전] 인식 힌트 및 음운 교정 맵 적용 완료 ({len(context.phonetic_fix_map)}개 규칙)")
            except Exception:
                pass

    def _report_load_progress(self, message: str, progress: int):
        callback = getattr(self, "_progress_callback", None)
        if callback:
            callback(message, progress)

    def _init_deepgram_streamer(self):
        key = self.config.get('deepgram_api_key', '').strip()
        model = self.config.get('deepgram_model', 'nova-3')
        keywords = self.config.get('deepgram_keywords', '').strip()
        # 도메인 사전 키워드 병합 주입
        if self.pre_context and self.pre_context.initial_prompt_tokens:
            extra_kw = self.pre_context.initial_prompt_tokens
            keywords = f"{keywords},{extra_kw}".strip(",") if keywords else extra_kw

        diarize = bool(self.config.get('speaker_diarization_enabled', False))
        endpointing = int(self.config.get('deepgram_endpointing_ms', 500))
        no_delay = bool(self.config.get('deepgram_no_delay', False))
        old = getattr(self, 'deepgram_streamer', None)
        enabled = self.config.get('stt_provider') == 'deepgram' and bool(key) and not self._paused
        if old and enabled and (old.api_key, old.model, old.keywords, old.diarize,
                               old.endpointing, old.no_delay) == (
                key, model, keywords, diarize, endpointing, no_delay):
            return
        if old:
            old.stop()
            self.deepgram_streamer = None
        if not enabled:
            return
        try:
            from .deepgram_streamer import DeepgramLiveStreamer
            self.deepgram_streamer = DeepgramLiveStreamer(
                api_key=key, model=model, keywords=keywords, diarize=diarize,
                endpointing=endpointing, no_delay=no_delay,
                on_event=self._speech_events.put)
            self.deepgram_streamer.start()
        except Exception as error:
            print(f'[STT] Deepgram 초기화 오류: {error}')
            self.deepgram_streamer = None

    def _map_deepgram_speaker(self, number, confirmed=False):
        if number is None or not self.config.get('speaker_diarization_enabled', False):
            return None
        identifier = getattr(self, 'speaker_identifier', None)
        if identifier:
            return identifier.map_external_speaker(number, confirmed=confirmed)
        from .speaker_identifier import SPEAKER_COLORS
        try:
            local = int(number) + 1
        except (TypeError, ValueError):
            return None
        max_n = max(1, int(self.config.get('speaker_max_count', 2)))
        if local < 1:
            return None
        if local > max_n:
            return 0, tr('speaker_unconfirmed'), '#AAB2C0'
        name = f'화자 {local}'
        return local, name, SPEAKER_COLORS[(local - 1) % len(SPEAKER_COLORS)]

    def _record(self, kind, **fields):
        if self._trace:
            self._trace.record(kind, **fields)

    def _queue_segments(self, segments):
        if self._paused:
            return
        for segment in segments:
            info = segment.speaker
            if isinstance(info, int):
                info = self._map_deepgram_speaker(info, confirmed=True)
            self._record('segment', **segment.as_dict(), stt=self._segment_source)
            offer_queue(self.trans_queue, (segment.text, self._segment_source, info, segment,
                                  self._pause_generation))

    def _consume_speech_events(self):
        # Called exclusively by STT.run, including shutdown. Socket callbacks only enqueue.
        for _ in range(256):
            try:
                event = self._speech_events.get_nowait()
            except queue.Empty:
                break
            if self._paused or self._active_stt_provider != 'deepgram':
                continue
            kind = event.get('type')
            self._record('deepgram', payload=event)
            source = f"Deepgram ({event.get('model', 'nova-3')})"
            if self._segment_source and self._segment_source != source:
                self._queue_segments(self._segmenter.flush('source_change'))
            self._segment_source = source
            if kind == 'Results':
                alt = (event.get('channel', {}).get('alternatives') or [{}])[0]
                if not event.get('is_final') and self.preview_callback:
                    text = alt.get('transcript', '')
                    if text:
                        words = alt.get('words') or []
                        speaker = self._map_deepgram_speaker(words[0].get('speaker')) if words else None
                        if speaker:
                            text = f"<span style='color: {speaker[2]}; font-weight: bold;'>[{speaker[1]}]</span> {text}"
                        self.preview_callback(text, f"{source} + {self.config.get('translation_engine', '')}")
            self._queue_segments(self._segmenter.accept(event))
        if self._paused:
            return
        self._queue_segments(self._segmenter.tick())
        since = self._segmenter.interim_since
        if since is not None and time.monotonic() - since >= 5.0 and self.deepgram_streamer:
            self.deepgram_streamer.request_finalize()

    def set_paused_state(self, paused):
        paused = bool(paused)
        if paused == self._paused:
            return
        self._paused = paused
        self._pause_generation += 1
        if paused:
            # 로컬/Groq의 미완성 발화가 재개 후 새 발화와 합쳐지지 않도록 폐기한다.
            self.sentence_buffer = []
            self.current_sentence_speaker = None
            self.last_speech_time = time.time()
            if self.deepgram_streamer:
                try:
                    self.deepgram_streamer.stop(flush=False)
                except Exception as error:
                    print(f'[STT] Deepgram 일시정지 종료 오류: {error}')
                finally:
                    self.deepgram_streamer = None
            while True:
                try:
                    self.trans_queue.get_nowait()
                except queue.Empty:
                    break
        else:
            self._init_deepgram_streamer()

    def set_audio_capture(self, audio_capture):
        self.audio_capture = audio_capture
        self._push_local_vad(self.silence_duration_sec, self.max_buffer_sec)

    def set_dubbing_engine(self, dubbing_engine):
        self.dubbing_engine = dubbing_engine

    def _uses_local_vad(self):
        from src.config import uses_local_tempo_vad
        return uses_local_tempo_vad(self.config)

    def _push_local_vad(self, silence_sec, max_buf, vad_threshold=None):
        if not self._uses_local_vad():
            return
        capture = getattr(self, 'audio_capture', None)
        if capture and hasattr(capture, 'set_tempo_params'):
            kwargs = {'silence_sec': silence_sec, 'max_buffer_sec': max_buf}
            if vad_threshold is not None:
                kwargs['vad_threshold'] = vad_threshold
            capture.set_tempo_params(**kwargs)

    def _emit_tempo_status(self, desc):
        if self.tempo_callback and desc != self.last_tempo_desc:
            self.last_tempo_desc = desc
            self.tempo_callback(desc)

    def _update_speech_tempo(self, instant_wpm: float, duration: float):
        """실시간 발화 속도(WPM) 갱신 및 스마트 모드 시 파라미터 자동 변속"""
        clamped_wpm = max(40.0, min(320.0, instant_wpm))
        alpha = 0.35
        self.estimated_wpm = (1 - alpha) * self.estimated_wpm + alpha * clamped_wpm

        preset_key = self.config.get("content_tempo_preset", "smart")
        if preset_key == "smart":
            self._apply_smart_adaptation()
        else:
            self._apply_fixed_preset(preset_key)

    def _apply_smart_adaptation(self):
        """스마트 모드: 로컬 STT 침묵/버퍼와 더빙 속도를 WPM에 맞춰 적응. Deepgram 분절은 건드리지 않음."""
        wpm = self.estimated_wpm
        if wpm >= 170.0:
            silence_sec = 0.30
            max_buf = 1.8
            dub_speed = "+25%"
            tempo_desc = tr("tempo_status_fast", wpm=int(wpm))
        elif wpm <= 115.0:
            silence_sec = 0.70
            max_buf = 3.6
            dub_speed = "+0%"
            tempo_desc = tr("tempo_status_calm", wpm=int(wpm))
        else:
            ratio = (wpm - 115.0) / (170.0 - 115.0)  # 0.0 ~ 1.0
            silence_sec = round(0.70 - ratio * (0.70 - 0.30), 2)
            max_buf = round(3.6 - ratio * (3.6 - 1.8), 1)
            dub_speed = "+15%" if wpm >= 145 else "+10%"
            tempo_desc = tr("tempo_status_balanced", wpm=int(wpm))

        self.silence_duration_sec = silence_sec
        self.max_buffer_sec = max_buf
        self._push_local_vad(silence_sec, max_buf)

        if self.dubbing_engine and hasattr(self.dubbing_engine, 'set_smart_speed'):
            self.dubbing_engine.set_smart_speed(dub_speed)

        if not self._uses_local_vad():
            tempo_desc = tr("tempo_status_smart_deepgram", dub_speed=dub_speed)
        self._emit_tempo_status(tempo_desc)

    def _apply_fixed_preset(self, preset_key: str):
        """고정 프리셋: 로컬 VAD/더빙만 적용. Deepgram endpointing과 SpeechSegmenter는 고정."""
        from src.config import CONTENT_TEMPO_PRESETS
        preset = CONTENT_TEMPO_PRESETS.get(preset_key, CONTENT_TEMPO_PRESETS["smart"])
        silence_sec = float(preset["silence_duration_sec"])
        max_buf = float(preset["max_buffer_sec"])
        dub_speed = preset["dubbing_speed"]

        self.silence_duration_sec = silence_sec
        self.max_buffer_sec = max_buf
        self._push_local_vad(silence_sec, max_buf, vad_threshold=preset.get("vad_threshold"))

        if self.dubbing_engine and hasattr(self.dubbing_engine, 'set_smart_speed'):
            self.dubbing_engine.set_smart_speed(dub_speed)

        short_key = f"tempo_{preset_key}"
        short = tr(short_key)
        if short == short_key:
            short = preset.get("short_name", preset["name"])
        if self._uses_local_vad():
            desc = tr("tempo_status_fixed_local", short=short, silence=silence_sec, buf=max_buf, speed=dub_speed)
        else:
            desc = tr("tempo_status_fixed_deepgram", short=short, speed=dub_speed)
        self._emit_tempo_status(desc)

    def apply_tempo_preset(self, preset_key: str):
        """컨트롤 패널 등 외부 인터페이스용 템포 프리셋 적용 공개 메서드"""
        self.config["content_tempo_preset"] = preset_key
        self.content_tempo_preset = preset_key
        if preset_key == "smart":
            return self._apply_smart_adaptation()
        return self._apply_fixed_preset(preset_key)

    def _ensure_local_model(self):
        """Groq 모드에서 429 한도 초과 또는 통신 장애 시, 백업용 로컬 STT 모델을 즉시 지연 로드"""
        if self.model or self.sensevoice_model or self.moonshine_model or self.parakeet_model:
            return True
        if getattr(self, '_local_model_loading', False):
            return False

        self._local_model_loading = True
        try:
            # 대안 2: 사용자가 설정/보유한 로컬 기본 STT 모델(model_size)을 우선 연동, 미지정 시 distil-small.en
            configured_model = self.config.get("model_size", "distil-small.en")
            if configured_model in ("parakeet-tdt-0.6b", "sensevoice-small", "moonshine-tiny"):
                target_model_id = "distil-small.en"
            else:
                target_model_id = normalize_whisper_model_id(configured_model)

            load_target, hub_cache = _resolve_local_model_target(target_model_id)
            target_device = "cuda" if (self.device == "cuda" and is_cuda_available()) else "cpu"

            comp = "float16" if target_device == "cuda" else "int8"
            print(f"[STT] Groq 429 한도 대비 로컬 백업 STT 모델({target_model_id})을 준비합니다... [대상: {load_target}]")
            self.model = WhisperModel(
                load_target,
                device=target_device,
                compute_type=comp,
                cpu_threads=4,
                download_root=hub_cache
            )
            print(f"[STT] 로컬 백업 STT 모델({target_model_id} {target_device.upper()}) 준비 완료!")
            return True
        except Exception as e:
            print(f"[STT] 로컬 백업 모델({target_model_id}) 로드 실패({e}), distil-small.en CPU int8 모드로 대체합니다...")
            try:
                fb_target, fb_hub = _resolve_local_model_target("distil-small.en")
                self.model = WhisperModel(
                    fb_target,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=4,
                    download_root=fb_hub
                )
                print("[STT] 로컬 백업 STT 모델(distil-small.en CPU) 준비 완료!")
                return True
            except Exception as e2:
                print(f"[STT] 로컬 백업 모델 준비 최종 실패: {e2}")
                return False
        finally:
            self._local_model_loading = False

    def _load_model(self):
        self.sensevoice_model = None
        self.moonshine_model = None
        self.parakeet_model = None
        self.model = None
        self._loaded_device = self.device
        self._last_stt_name = None

        # 1. 클라우드 STT 활성 시 무거운 로컬 가중치 로딩 건너뜀 (초고속 시작, GPU 0%)
        if self.config.get("stt_provider") == "deepgram" and self.config.get("deepgram_api_key"):
            dg_m = self.config.get("deepgram_model", "nova-3")
            self._report_load_progress(tr("splash_prep_deepgram", model=dg_m), 62)
            print(f"[STT] Deepgram Nova 클라우드 모드 가동 완료! (API 모델: {dg_m})")
            return
        if self.config.get("stt_provider") == "groq" and self.config.get("groq_api_key"):
            groq_m = self.config.get("groq_model", "whisper-large-v3-turbo")
            self._report_load_progress(tr("splash_prep_groq", model=groq_m), 62)
            print(f"[STT] Groq Cloud LPU 모드 가동 완료! (API 모델: {groq_m}, GPU 0%, 지연 0.05s)")
            return

        model_id = normalize_whisper_model_id(self.model_size)
        if not (STTModelManager.is_model_installed(model_id) or STTModelManager.is_bundled_model(model_id)) and self.model_size not in ("sensevoice-small", "moonshine-tiny", "parakeet-tdt-0.6b"):
            print(f"[STT] '{model_id}' 모델이 로컬에 설치되어 있지 않아 기본 번들 모델(distil-small.en)로 안전하게 대체합니다 (모델 관리창에서 다운로드 가능).")
            self.model_size = "distil-small.en"
            self.config["model_size"] = "distil-small.en"
            model_id = normalize_whisper_model_id(self.model_size)

        print(f"[STT] 모델 로드 중: {self.model_size} (디바이스: {self.device}, 타입: {self.compute_type})...")
        self._report_load_progress(tr("splash_loading_stt", model=self.model_size), 58)

        if self.model_size == "parakeet-tdt-0.6b":
            try:
                import sherpa_onnx
                import os
                from huggingface_hub import snapshot_download
                path = snapshot_download('csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8')
                self.parakeet_model = sherpa_onnx.OfflineRecognizer.from_transducer(
                    encoder=os.path.join(path, 'encoder.int8.onnx'),
                    decoder=os.path.join(path, 'decoder.int8.onnx'),
                    joiner=os.path.join(path, 'joiner.int8.onnx'),
                    tokens=os.path.join(path, 'tokens.txt'),
                    model_type='nemo_transducer',
                    num_threads=4,
                    provider='cpu'
                )
                print("[STT] NVIDIA Parakeet-TDT 0.6B 모델 준비 완료! (리더보드 1위)")
                self._report_load_progress(tr("splash_loaded_parakeet"), 70)
                return
            except Exception as e:
                print(f"[STT] Parakeet 로드 실패({e}), Whisper로 폴백...")
                self.model_size = "small.en"

        elif self.model_size == "sensevoice-small":
            try:
                import sherpa_onnx
                import os
                from huggingface_hub import snapshot_download
                path = snapshot_download('csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17', allow_patterns=['model.onnx', 'tokens.txt'])
                self.sensevoice_model = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                    model=os.path.join(path, 'model.onnx'),
                    tokens=os.path.join(path, 'tokens.txt'),
                    num_threads=4,
                    use_itn=True
                )
                print("[STT] SenseVoice-Small 초고속 병렬 모델 준비 완료! (GPU 0%, 0.1초대)")
                self._report_load_progress(tr("splash_loaded_sensevoice"), 70)
                return
            except Exception as e:
                print(f"[STT] SenseVoice 로드 실패({e}), Whisper로 폴백...")
                self.model_size = "small.en"

        elif self.model_size == "moonshine-tiny":
            try:
                import sherpa_onnx
                import os
                from huggingface_hub import snapshot_download
                path = snapshot_download('csukuangfj/sherpa-onnx-moonshine-tiny-en-int8', allow_patterns=['*.onnx', 'tokens.txt'])
                self.moonshine_model = sherpa_onnx.OfflineRecognizer.from_moonshine(
                    preprocessor=os.path.join(path, 'preprocess.onnx'),
                    encoder=os.path.join(path, 'encode.int8.onnx'),
                    uncached_decoder=os.path.join(path, 'uncached_decode.int8.onnx'),
                    cached_decoder=os.path.join(path, 'cached_decode.int8.onnx'),
                    tokens=os.path.join(path, 'tokens.txt'),
                    num_threads=4
                )
                print("[STT] Moonshine 초저지연 스트리밍 모델 준비 완료! (0.12초)")
                self._report_load_progress(tr("splash_loaded_moonshine"), 70)
                return
            except Exception as e:
                print(f"[STT] Moonshine 로드 실패({e}), Whisper로 폴백...")
                self.model_size = "small.en"

        # 디바이스 및 모델 식별자 안전 정규화
        try:
            from src.cuda_utils import register_cuda_dll_directories, preload_cuda_dlls
            register_cuda_dll_directories(force=True)
            if self.device == "cuda":
                preload_cuda_dlls()
        except Exception:
            pass
        target_device = "cuda" if (self.device == "cuda" and is_cuda_available()) else "cpu"
        if self.device == "cuda" and target_device == "cpu":
            print("[STT] CUDA를 요청했지만 cuBLAS 또는 ctranslate2 CUDA 장치를 찾지 못해 CPU int8로 로드합니다. 가속 팩을 설치하면 GPU로 다시 로드합니다.")

        model_id = normalize_whisper_model_id(self.model_size)
        load_target, hub_cache = _resolve_local_model_target(model_id)
        self._loaded_device = "cpu"
        try:
            if target_device == "cpu":
                self.model = WhisperModel(
                    load_target,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=4,
                    download_root=hub_cache
                )
                print(f"[STT] AMD/Intel CPU 초경량(INT8) 모델 로드 완료! ({model_id}) [대상: {load_target}]")
                self._report_load_progress(tr("splash_loaded_stt", model=model_id), 70)
            else:
                self.model = WhisperModel(
                    load_target,
                    device="cuda",
                    compute_type="float16",
                    download_root=hub_cache
                )
                # CUDA 런타임(cuBLAS) 바인딩 즉각 검증 (라이브러리 누락/VRAM 부족 시 안전하게 포착하여 CPU 폴백)
                try:
                    import numpy as np
                    list(self.model.transcribe(np.zeros(1600, dtype=np.float32))[0])
                except Exception as warm_err:
                    raise RuntimeError(f"CUDA STT 연산 초기화 실패 ({warm_err})")
                self._loaded_device = "cuda"
                print(f"[STT] NVIDIA CUDA 가속 모델 준비 완료! ({model_id}) [대상: {load_target}]")
                self._report_load_progress(tr("splash_loaded_stt", model=model_id), 70)
        except Exception as e:
            print(f"[STT] {target_device} 로드 실패({e}), CPU int8 모드로 폴백...")
            try:
                self.device = "cpu"
                self.compute_type = "int8"
                fallback_id = normalize_whisper_model_id(model_id)
                fb_target, fb_hub = _resolve_local_model_target(fallback_id)
                self.model = WhisperModel(
                    fb_target,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=4,
                    download_root=fb_hub
                )
                print(f"[STT] CPU int8 폴백 완료! ({fallback_id}) [대상: {fb_target}]")
                self._report_load_progress(tr("splash_loaded_stt", model=fallback_id), 70)
            except Exception as e2:
                print(f"[STT] CPU 폴백 실패: {e2}. 기본 내장 번들 모델(distil-small.en)로 최종 폴백...")
                try:
                    def_target, def_hub = _resolve_local_model_target("distil-small.en")
                    self.model = WhisperModel(
                        def_target,
                        device="cpu",
                        compute_type="int8",
                        cpu_threads=4,
                        download_root=def_hub
                    )
                    print(f"[STT] distil-small.en 기본 내장 모델 최종 폴백 완료! [대상: {def_target}]")
                except Exception as e3:
                    print(f"[STT] 로컬 모델 초기화 최종 실패: {e3}")
                    self.model = None

    def _cuda_fallback_recoverable(self) -> bool:
        """CUDA 설정인데 CPU 로 떨어져 있고, 지금은 CUDA 를 쓸 수 있게 된 상태인지"""
        return self.device == "cuda" and self._loaded_device == "cpu" and is_cuda_available()

    def change_device(self, new_device):
        """GPU <-> CPU 전환. 실행 중인 워커에서는 STT 스레드가 다음 루프에서 모델을 다시 로드한다."""
        if self.device == new_device and self._loaded_device == new_device:
            return
        self.device = new_device
        self.compute_type = "float16" if new_device == "cuda" else "int8"
        if self.running:
            self._model_reload_requested = True
        else:
            self._load_model()

    def change_model(self, model_size):
        if self.model_size != model_size:
            self.model_size = model_size
            self._load_model()

    def update_config(self, cfg):
        previous_provider = self._active_stt_provider
        previous_device = self.device
        previous_model = self.model_size
        self.config = cfg
        self.stt_language = cfg.get("stt_language", "en")
        self._active_stt_provider = cfg.get("stt_provider", "local")
        if self._active_stt_provider != previous_provider:
            self._last_stt_name = None
        self.device = cfg.get("device", self.device)
        self.model_size = cfg.get("model_size", self.model_size)
        self.compute_type = "float16" if self.device == "cuda" else "int8"
        self.sentence_mode = cfg.get("sentence_mode", True)
        self.use_context_prompt = cfg.get("use_context_prompt", False)
        if not self.use_context_prompt:
            self.last_context_prompt = ""
        self.translator.update_config(cfg)

        new_preset = cfg.get("content_tempo_preset", "smart")
        self.content_tempo_preset = new_preset
        if new_preset == "smart":
            self._apply_smart_adaptation()
        else:
            self._apply_fixed_preset(new_preset)

        if cfg.get("speaker_diarization_enabled", False):
            if not getattr(self, 'speaker_identifier', None):
                try:
                    from .speaker_identifier import SpeakerIdentifier
                    self.speaker_identifier = SpeakerIdentifier(config=cfg)
                except Exception:
                    self.speaker_identifier = None
            else:
                self.speaker_identifier.update_config(cfg)
        else:
            if getattr(self, 'speaker_identifier', None):
                self.speaker_identifier.update_config(cfg)
        if self.dubbing_engine:
            self.dubbing_engine.speaker_identifier = self.speaker_identifier

        if hasattr(self, '_init_deepgram_streamer'):
            self._init_deepgram_streamer()
        if cfg.get("stt_provider", "local") == "local" and (
                previous_provider != "local" or previous_device != self.device or
                previous_model != self.model_size or self._cuda_fallback_recoverable()):
            self._model_reload_requested = True

    def stop(self):
        self._draining = True
        if self.deepgram_streamer:
            self.deepgram_streamer.stop()
            self.deepgram_streamer = None
        self.running = False
        if self.is_alive() and self is not threading.current_thread():
            self.join(timeout=3.0)
        self._draining = False
        if self.trans_worker.is_alive() and self.trans_worker is not threading.current_thread():
            self.trans_worker.join(timeout=3.0)
        if self._trace:
            self._trace.close()

    def _transcribe_groq(self, audio_data, api_key: str):
        """Groq LPU 초고속 클라우드 STT (듀얼 모델 로테이션 40 RPM 지원 및 429 자동 감지)"""
        try:
            import io
            from scipy.io import wavfile
            int16_data = (audio_data * 32767).clip(-32768, 32767).astype(np.int16)
            buf = io.BytesIO()
            wavfile.write(buf, 16000, int16_data)
            wav_bytes = buf.getvalue()

            headers = {"Authorization": f"Bearer {api_key}"}
            primary_m = self.config.get("groq_model", "whisper-large-v3-turbo")
            secondary_m = "whisper-large-v3" if "turbo" in primary_m else "whisper-large-v3-turbo"

            now = time.time()
            models_to_try = []

            p_cooldown = self._groq_cooldowns.get(primary_m, 0.0)
            s_cooldown = self._groq_cooldowns.get(secondary_m, 0.0)

            if now >= p_cooldown:
                models_to_try.append(primary_m)
                if now >= s_cooldown:
                    models_to_try.append(secondary_m)
            elif now >= s_cooldown:
                print(f"[Groq LPU] [INFO] 기본 모델({primary_m}) 429 쿨다운 중 -> 보조 모델({secondary_m})로 즉각 우회 요청합니다.")
                models_to_try.append(secondary_m)
            else:
                remaining = max(0.1, min(p_cooldown, s_cooldown) - now)
                print(f"[Groq LPU] [WARN] 듀얼 모델(총 40 RPM) 모두 분당 한도 도달! (남은 쿨다운: {remaining:.1f}초) -> 로컬 STT 엔진으로 즉각 대체합니다.")
                return None

            stt_lang = getattr(self, "stt_language", None) or self.config.get("stt_language", "en")
            for m in models_to_try:
                data = {"model": m, "temperature": "0.0"}
                if stt_lang and str(stt_lang).lower() not in ("auto", "none"):
                    data["language"] = str(stt_lang).strip().lower()
                if self.config.get("speaker_diarization_enabled", False):
                    data.update(response_format="verbose_json", **{"timestamp_granularities[]": "word"})
                if self.use_context_prompt and self.last_context_prompt:
                    data["prompt"] = self.last_context_prompt[-220:]

                files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
                resp = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=2.5
                )

                if resp.status_code == 200:
                    payload = resp.json()
                    txt = payload.get("text", "").strip()
                    self._last_transcript_words = payload.get("words", []) if txt else []
                    return (txt, m)
                elif resp.status_code == 429:
                    # 429 Rate Limit 감지!
                    self._groq_cooldowns[m] = time.time() + 4.0  # 4초 쿨다운 설정
                    alt = secondary_m if m == primary_m else primary_m
                    print(f"[Groq LPU] [WARN] '{m}' 분당 한도(20 RPM) 도달! 보조 모델 '{alt}'(으)로 즉시 전환합니다.")
                    continue
                else:
                    print(f"[Groq 오류] 상태 코드 {resp.status_code} ({m}): {resp.text[:120]}")

        except Exception as e:
            print(f"[Groq 오류] {e}, 로컬 모델로 폴백합니다.")
        return None

    def _transcribe_deepgram(self, audio_data: np.ndarray, api_key: str):
        """Deepgram Nova REST API를 통한 초저지연(0.15~0.2초) 음성인식 전사"""
        try:
            import io
            import wave
            import requests

            audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_int16.tobytes())
            wav_bytes = buf.getvalue()

            model = self.config.get("deepgram_model", "nova-3")
            stt_lang = getattr(self, "stt_language", None) or self.config.get("stt_language", "en")
            dg_lang = "multi" if str(stt_lang).lower() in ("auto", "none") else str(stt_lang).strip().lower()
            params = [
                ("model", model),
                ("language", dg_lang),
                ("smart_format", "true"),
                ("punctuate", "true"),
            ]
            keywords = self.config.get("deepgram_keywords", "").strip()
            if keywords:
                is_nova3 = "nova-3" in model
                for kw in keywords.split(","):
                    kw_s = kw.strip()
                    if not kw_s:
                        continue
                    if is_nova3:
                        term = kw_s.split(":")[0].strip()
                        if term:
                            params.append(("keyterm", term))
                    else:
                        params.append(("keywords", kw_s))

            headers = {
                "Authorization": f"Token {api_key}",
                "Content-Type": "audio/wav"
            }
            resp = requests.post(
                "https://api.deepgram.com/v1/listen",
                params=params,
                headers=headers,
                data=wav_bytes,
                timeout=2.5
            )
            if resp.status_code == 200:
                data = resp.json()
                channels = data.get("results", {}).get("channels", [])
                if channels:
                    alts = channels[0].get("alternatives", [])
                    if alts:
                        txt = alts[0].get("transcript", "").strip()
                        self._last_transcript_words = alts[0].get("words", []) if txt else []
                        return (txt, model)
            else:
                print(f"[Deepgram 오류] 상태 코드 {resp.status_code} ({model}): {resp.text[:120]}")
        except requests.exceptions.Timeout:
            print("[Deepgram 타임아웃] 일시적 응답 지연(>2.5s), 백업 엔진(Groq/Local)으로 즉시 전환합니다.")
        except Exception as e:
            print(f"[Deepgram 예외] {e}")
        return None

    def _local_stt_label(self) -> str:
        """로컬 STT 표시 이름. 설정(self.device)이 아니라 실제로 모델이 올라간 장치를 쓴다 (CUDA 요청이 CPU 로 폴백된 경우)."""
        if self.sensevoice_model:
            return "SenseVoice"
        if self.moonshine_model:
            return "Moonshine"
        if self.parakeet_model:
            return "Parakeet"
        return "GPU" if (self._loaded_device or self.device) == "cuda" else "CPU"

    def _current_stt_label(self) -> str:
        """방금 인식한 엔진 이름. 아직 인식 전이면 설정 기준 이름."""
        if getattr(self, "_last_stt_name", None):
            return self._last_stt_name
        provider = self.config.get("stt_provider", "local")
        if provider == "deepgram":
            return f"Deepgram ({self.config.get('deepgram_model', 'nova-3')})"
        if provider == "groq":
            return "Groq"
        return self._local_stt_label()

    def _transcribe_audio_chunk(self, audio_data: np.ndarray) -> tuple[str, str]:
        """단일 오디오 청크/슬라이스에 대해 활성화된 STT 엔진으로 텍스트 추출"""
        chunk_text, stt_name = self._transcribe_audio_chunk_impl(audio_data)
        if chunk_text:
            self._last_stt_name = stt_name
        return chunk_text, stt_name

    def _transcribe_audio_chunk_impl(self, audio_data: np.ndarray) -> tuple[str, str]:
        chunk_text = ""
        self._last_transcript_words = []
        stt_name = self._local_stt_label()

        # 1. Deepgram Nova 클라우드 모드 우선 확인
        if self.config.get("stt_provider") == "deepgram":
            dg_key = self.config.get("deepgram_api_key", "").strip()
            if dg_key:
                res = self._transcribe_deepgram(audio_data, dg_key)
                if res is not None:
                    chunk_text, used_model = res
                    if chunk_text:
                        stt_name = f"Deepgram ({used_model})"
            # Deepgram 실패 또는 키 미등록 시 Groq로 클라우드 상호 폴백!
            if not chunk_text and self.config.get("groq_api_key"):
                res = self._transcribe_groq(audio_data, self.config.get("groq_api_key", "").strip())
                if res is not None:
                    chunk_text, used_model = res
                    if chunk_text:
                        stt_name = f"Groq (폴백 - {'Turbo' if 'turbo' in used_model else 'V3'})"

        # 2. Groq LPU 클라우드 모드 우선 확인 (듀얼 모델 로테이션 40 RPM 지원)
        elif self.config.get("stt_provider") == "groq":
            groq_key = self.config.get("groq_api_key", "").strip()
            if groq_key:
                res = self._transcribe_groq(audio_data, groq_key)
                if res is not None:
                    chunk_text, used_model = res
                    if chunk_text:
                        stt_name = f"Groq ({'Turbo' if 'turbo' in used_model else 'V3'})"
            # Groq 429 쿨다운 시 Deepgram 키가 있으면 Deepgram으로 클라우드 상호 폴백!
            if not chunk_text and self.config.get("deepgram_api_key"):
                res = self._transcribe_deepgram(audio_data, self.config.get("deepgram_api_key", "").strip())
                if res is not None:
                    chunk_text, used_model = res
                    if chunk_text:
                        stt_name = f"Deepgram (폴백 - {used_model})"

        # 3. 로컬 STT 추론 (SenseVoice / Moonshine / Whisper) - 클라우드 실패 또는 한도 시 즉각 로컬 안전망 폴백!
        if not chunk_text:
            if not (self.sensevoice_model or self.moonshine_model or self.parakeet_model or self.model):
                self._ensure_local_model()

            if self.sensevoice_model:
                try:
                    s = self.sensevoice_model.create_stream()
                    s.accept_waveform(16000, audio_data)
                    self.sensevoice_model.decode_stream(s)
                    chunk_text = s.result.text.strip()
                    stt_name = "SenseVoice"
                except Exception as e:
                    print(f"[SenseVoice 추론 오류] {e}")
            elif self.moonshine_model:
                try:
                    s = self.moonshine_model.create_stream()
                    s.accept_waveform(16000, audio_data)
                    self.moonshine_model.decode_stream(s)
                    chunk_text = s.result.text.strip()
                    stt_name = "Moonshine"
                except Exception as e:
                    print(f"[Moonshine 추론 오류] {e}")
            elif self.parakeet_model:
                try:
                    s = self.parakeet_model.create_stream()
                    s.accept_waveform(16000, audio_data)
                    self.parakeet_model.decode_stream(s)
                    chunk_text = s.result.text.strip()
                    stt_name = "Parakeet"
                except Exception as e:
                    print(f"[Parakeet 추론 오류] {e}")
            elif self.model:
                base_hint = self.pre_context.initial_prompt_tokens if (self.pre_context and not self.pre_context.is_empty()) else ""
                if base_hint:
                    hw = [w.strip() for w in base_hint.split(",") if w.strip()]
                    if len(hw) > 8:
                        base_hint = ", ".join(hw[:8])
                prev_ctx = (self.last_context_prompt[-220:] if self.last_context_prompt else "") if self.use_context_prompt else ""
                if base_hint and prev_ctx:
                    init_prompt = f"{base_hint}. {prev_ctx}"[-350:]
                else:
                    init_prompt = (base_hint or prev_ctx) or None

                # 캡처 레벨에서 이미 RMS 에너지 기반 음성 구간 분할이 완료되었으므로,
                # 화자 분리(Diarization)나 명시적 옵션이 아닌 경우 중복 Silero VAD 신경망 연산을 생략하여 전사 레이턴시 20~30ms 단축
                use_whisper_vad = bool(self.config.get("whisper_vad_filter", False)) or bool(self.config.get("speaker_diarization_enabled", False))
                # 실시간 스트리밍에서는 Greedy Decoding(beam_size=1)으로 지연 시간 및 GPU VRAM 부하를 최소화하여 TDR 충돌 방지
                beam_sz = int(self.config.get("whisper_beam_size", 1))
                best_of_val = int(self.config.get("whisper_best_of", 1))

                # STT 언어 파라미터 결정: .en 및 distil 영문 모델은 "en" 고정, 다국어 모델에서 "auto"면 None(99개 언어 자동감지)
                stt_lang = getattr(self, "stt_language", None) or self.config.get("stt_language", "en")
                from src.stt_model_manager import STTModelManager
                if not STTModelManager.is_multilingual_model(self.model_size, "local"):
                    lang_param = "en"
                elif not stt_lang or str(stt_lang).lower() in ("auto", "none"):
                    lang_param = None
                else:
                    lang_param = str(stt_lang).strip().lower()

                segments, info = self.model.transcribe(
                    audio_data,
                    language=lang_param,
                    beam_size=beam_sz,
                    best_of=best_of_val,
                    temperature=0.0,
                    repetition_penalty=1.25,
                    no_repeat_ngram_size=3,
                    vad_filter=use_whisper_vad,
                    vad_parameters=dict(min_silence_duration_ms=250, speech_pad_ms=200) if use_whisper_vad else None,
                    condition_on_previous_text=False,
                    word_timestamps=bool(self.config.get("speaker_diarization_enabled", False)),
                    initial_prompt=init_prompt,
                    no_speech_threshold=0.6,
                    compression_ratio_threshold=2.4,
                    log_prob_threshold=-1.0,
                    hallucination_silence_threshold=2.0
                )

                parts = []
                for seg in segments:
                    txt = seg.text.strip()
                    if txt:
                        parts.append(txt)
                        for word in getattr(seg, 'words', None) or []:
                            self._last_transcript_words.append(dict(word=word.word, start=word.start, end=word.end))

                # CJK(일본어/중국어) 세그먼트 간 결합 시 자연스러운 결합 보존
                if parts:
                    chunk_parts = [parts[0]]
                    for next_part in parts[1:]:
                        prev = chunk_parts[-1]
                        if re.search(r'[\u3040-\u30ff\u4e00-\u9fff]$', prev) and re.search(r'^[\u3040-\u30ff\u4e00-\u9fff]', next_part):
                            chunk_parts.append(next_part)
                        else:
                            chunk_parts.append(" " + next_part)
                    chunk_text = "".join(chunk_parts).strip()
                else:
                    chunk_text = ""

                # 자동 언어 감지 결과 피드백:
                # Whisper 오인식 보정 및 텍스트 문자 체계(Script) 기반 정밀 판정
                detected_lang = getattr(info, "language", None)
                if chunk_text:
                    if re.search(r'[\u3040-\u30ff]', chunk_text):
                        detected_lang = "ja"
                    elif re.search(r'[\uac00-\ud7af\u1100-\u11ff]', chunk_text):
                        detected_lang = "ko"
                    elif re.search(r'[\u0400-\u04ff]', chunk_text):
                        detected_lang = detected_lang if detected_lang in ("ru", "uk", "bg", "be", "sr") else "ru"
                    elif re.search(r'[\u0600-\u06ff]', chunk_text):
                        detected_lang = detected_lang if detected_lang in ("ar", "fa", "ur") else "ar"
                    elif re.search(r'[\u0e00-\u0e7f]', chunk_text):
                        detected_lang = "th"
                    elif re.search(r'[\u0900-\u097f]', chunk_text):
                        detected_lang = "hi"
                    elif re.search(r'[\u4e00-\u9fff]', chunk_text) and detected_lang in ("zh", "yue", "en", None):
                        detected_lang = "zh"

                if detected_lang and getattr(self, "translator", None):
                    is_auto = getattr(self.translator, "is_auto_source", False) or lang_param is None
                    if is_auto and getattr(self.translator, "source", "") != detected_lang:
                        self.translator.source = detected_lang

                if chunk_text:
                    stt_name = self._local_stt_label()

            # 클라우드 STT 를 선택했는데 로컬 모델이 인식한 경우
            if chunk_text and self.config.get("stt_provider") in ("groq", "deepgram"):
                stt_name = f"{stt_name} (로컬 폴백)"

        return chunk_text, stt_name

    def _transcribe_with_speakers(self, audio_data, slices):
        # ASR retains full utterance context. Alignment splits TEXT, not audio.
        self._last_transcript_words = []
        text, engine = self._transcribe_audio_chunk(audio_data)
        if not text:
            return []
        if not self.config.get('speaker_diarization_enabled', False):
            return [(text, engine, None, len(audio_data) / 16000.0)]
        return [(part, engine, info, duration) for part, info, duration in
                align_transcript(text, self._last_transcript_words, slices)]

    def _translation_loop(self):
        """확정 segment 순서와 경계를 보존하는 독립 비동기 번역 워커."""
        context_key, reference = None, []
        context_generation = self._pause_generation
        while self.running or self._draining or not self.trans_queue.empty():
            try:
                item = self.trans_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if item is None:
                continue
            generation = item[4] if len(item) >= 5 else self._pause_generation
            if self._paused or generation != self._pause_generation:
                continue
            if context_generation != generation:
                context_key, reference = None, []
                context_generation = generation

            segment = item[3] if len(item) >= 4 else None
            if len(item) >= 3:
                orig_text, stt_name, spk_info = item[:3]
            else:
                orig_text, stt_name = item
                spk_info = None

            # 화자 필터링 (Mute 검사): 제외된 화자의 발화는 번역 및 자막 출력 생략
            if spk_info and spk_info[0] > 0 and self.speaker_identifier and self.config.get("speaker_diarization_enabled", False):
                spk_name = f"화자 {spk_info[0]}"
                if self.speaker_identifier.is_speaker_muted(spk_name):
                    continue

            # 영문 텍스트 정제 (말더듬/중복구문 제거, 필러 워드 정리)
            # Deepgram's confirmed words must not be stripped as Whisper repetitions.
            normalized_text = (re.sub(r'\s+', ' ', orig_text).strip() if segment
                               else EnglishTextNormalizer.normalize(orig_text))

            # 도메인 사전 기반 STT 음운 오인식 교정 적용 (Phonetic Fix Map)
            pre_ctx = getattr(self, 'pre_context', None)
            if pre_ctx and not pre_ctx.is_empty():
                normalized_text = pre_ctx.apply_phonetic_fixes(normalized_text)

            if not normalized_text:
                continue

            try:
                key = (segment.session, spk_info[0] if spk_info else None) if segment else None
                if key != context_key:
                    reference = []
                    context_key = key
                self._record('translation_request', segment_id=segment.id if segment else None,
                             original=normalized_text, context=reference, stt=stt_name,
                             selected_engine=self.config.get('translation_engine', 'google'))
                started = time.monotonic()
                if segment:
                    translated, trans_name = self.translator.translate_segment(
                        normalized_text, context=reference, partial=segment.partial)
                    reference = (reference + [normalized_text])[-2:]
                else:
                    translated, trans_name = self.translator.translate(normalized_text)
                if self._paused or generation != self._pause_generation:
                    continue
                self._record('translation_result', segment_id=segment.id if segment else None,
                             original=normalized_text, translated=translated, engine=trans_name,
                             seconds=time.monotonic() - started,
                             response=getattr(self.translator, 'last_response_metadata', {}))
                if translated:
                    engine_tag = f"{stt_name} + {trans_name}"

                    # 화자 분리 서식 적용 (옵션 활성화 시)
                    display_orig = normalized_text
                    display_trans = translated
                    if spk_info and self.config.get("speaker_diarization_enabled", False):
                        spk_num, spk_name, spk_color = spk_info[:3]
                        raw_name = f"화자 {spk_num}"
                        latest_display_name = self.speaker_identifier.get_display_name(raw_name) if self.speaker_identifier and spk_num > 0 else (self.speaker_identifier.get_display_name(spk_name) if self.speaker_identifier else spk_name)
                        display_orig = f"<span style='color: {spk_color}; font-weight: bold;'>[{latest_display_name}]</span> {normalized_text}"
                        display_trans = f"<span style='color: {spk_color}; font-weight: bold;'>[{latest_display_name}]</span> {translated}"

                    print(f"[영문 원문 | {stt_name}] {normalized_text}", flush=True)
                    print(f"[완결 번역 | {engine_tag}] {translated}\n", flush=True)
                    if self.subtitle_callback:
                        self.subtitle_callback(display_orig, display_trans, engine_tag)

                    # 실시간 AI 음성 더빙 대기열 추가 (Edge-TTS, 오디오 통역 더빙 켜짐 시에만)
                    if self.dubbing_engine and self.config.get("dubbing_enabled", False) and self.config.get("dubbing_source_audio", True):
                        speaker_name_for_dub = f"화자 {spk_info[0]}" if spk_info and spk_info[0] > 0 else ""
                        self.dubbing_engine.enqueue(
                            translated_text=translated,
                            speaker_name=speaker_name_for_dub,
                            speaker_confirmed=not spk_info or spk_info[0] > 0,
                            orig_text=normalized_text,
                            source="audio",
                            segment_id=segment.id if segment else None
                        )
            except Exception as e:
                print(f"[번역 예외] {e}", flush=True)

    def run(self):
        self.running = True
        self._trace = PipelineTrace(enabled=self.config.get('translation_trace_enabled', False))
        if self.dubbing_engine:
            self.dubbing_engine.pipeline_trace = self._trace
        if self._trace.path:
            print(f'[기록] 번역 진단 로그: {self._trace.path}')
        self.trans_worker.start()
        print("[STT] 실시간 통역 엔진 준비 완료! (비동기 번역 & 문장 완결 버퍼링)")

        # 로컬 번역 모델 사전 로딩 (사용자가 명시적으로 켠 경우에만 수행, 기본값 False로 CUDA 컨텍스트 충돌 원천 차단)
        cur_eng = self.config.get("translation_engine", "")
        if self.config.get("gpu_warmup_on_startup", False) and cur_eng in ("gemma", "exaone", "exaone7b", "hymt"):
            threading.Thread(target=self.translator.preload_engine, args=(cur_eng,), daemon=True).start()
        
        seen_pause_generation = self._pause_generation
        while self.running:
            try:
                if seen_pause_generation != self._pause_generation:
                    self._segmenter = SpeechSegmenter()
                    self._segment_source = ''
                    self.sentence_buffer = []
                    self.current_sentence_speaker = None
                    seen_pause_generation = self._pause_generation
                if self._model_reload_requested and self._active_stt_provider == "local":
                    self._model_reload_requested = False
                    self._load_model()
                if self._paused:
                    try:
                        self.audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        pass
                    self._consume_speech_events()
                    continue
                self._consume_speech_events()
                try:
                    audio_data = self.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    if self._active_stt_provider == "deepgram":
                        self._queue_segments(self._segmenter.tick())
                    else:
                        # 로컬 STT / Groq: 동적 적응형 침묵 타이밍(Adaptive Silence Timeout) 완결 플러시
                        if self.sentence_buffer:
                            elapsed = time.time() - self.last_speech_time
                            full_sentence = " ".join(self.sentence_buffer).strip()
                            if SemanticClauseDetector.should_flush(full_sentence, elapsed, base_silence=getattr(self, 'silence_duration_sec', 0.45)):
                                self.sentence_buffer = []
                                clean_check = re.sub(r'[\W_]+', '', full_sentence.lower())
                                if clean_check and clean_check not in ('um', 'uh', 'hmm', 'ah', 'eh', 'er', 'mhm', 'oh'):
                                    cur_stt = self._current_stt_label()
                                    offer_queue(self.trans_queue, (full_sentence, cur_stt, getattr(self, 'current_sentence_speaker', None), None, self._pause_generation))
                                self.current_sentence_speaker = None
                    continue

                channels_separated = False
                capture_start, capture_session = None, None
                speech_end = False
                if isinstance(audio_data, CapturedAudio):
                    if (audio_data.stt_provider and
                            audio_data.stt_provider != self._active_stt_provider):
                        continue
                    capture_start, capture_session = audio_data.start_sample, audio_data.session_id
                    speech_end = audio_data.speech_end
                    channels_separated = audio_data.channels_separated
                    audio_data = audio_data.samples
                if audio_data is None or len(audio_data) == 0:
                    continue

                audio_data = np.asarray(audio_data, dtype=np.float32)
                if audio_data.ndim > 1:
                    audio_data = audio_data[:, 0]

                # 사운드 채널 분리(WASAPI Process Loopback 또는 가상 케이블) 시에는
                # 더빙 음성이 STT 입력으로 유입되지 않으므로 에코 차단 필터를 0ms로 즉각 생략
                if not channels_separated and self.dubbing_engine and self.dubbing_engine.is_speaking(grace_period=2.0) and self.config.get("dubbing_echo_cancellation", True):
                    if hasattr(self, 'speaker_identifier') and self.speaker_identifier and getattr(self.speaker_identifier, 'model_loaded', False):
                        try:
                            echo_threshold = float(self.config.get("dubbing_echo_threshold", 0.72))
                            is_echo, sim, matched_v = self.speaker_identifier.is_tts_echo(audio_data, threshold=echo_threshold)
                            if is_echo:
                                print(f"[STT] [MUTE] 순수 더빙 에코 자동 차단 (TTS 음색 일치도: {sim:.2f} >= {echo_threshold} [{matched_v}])", flush=True)
                                continue
                        except Exception:
                            pass

                # Deepgram 실시간 WebSocket 라이브 스트리밍 어댑터 (1단계 연결 시 청크 분할 및 로컬 VAD 생략하고 즉시 전송)
                if self._paused or seen_pause_generation != self._pause_generation:
                    continue
                if getattr(self, 'deepgram_streamer', None) and self.deepgram_streamer.is_connected():
                    self.deepgram_streamer.send_audio(audio_data)
                    continue

                # 최근 캡처 음성으로 화자 교대 분석. 미확정도 원음을 보존한다.
                segments_to_process = [(audio_data, None)]
                if hasattr(self, 'speaker_identifier') and self.speaker_identifier and self.speaker_identifier.is_enabled:
                    try:
                        self.speaker_identifier.set_audio_context(capture_start, capture_session)
                        segments_to_process = self.speaker_identifier.segment_audio_by_speaker(audio_data)
                    except Exception as e:
                        try:
                            spk_fallback = self.speaker_identifier._get_fallback_speaker()
                            segments_to_process = [(audio_data, spk_fallback)]
                        except Exception:
                            segments_to_process = [(audio_data, None)]

                for chunk_text, stt_name, spk_info, seg_dur_sec in self._transcribe_with_speakers(audio_data, segments_to_process):
                    if self._paused or seen_pause_generation != self._pause_generation:
                        break
                    if not chunk_text:
                        continue

                    # 1. 영문 텍스트 1차 정규화 (말더듬/중복 단어 정제)
                    chunk_text = EnglishTextNormalizer.normalize(chunk_text)
                    if not chunk_text:
                        continue

                    # 2. 환각 필터링 (원문 및 특수기호 제거 정제문 모두 대조)
                    clean_check = re.sub(r'[^\w\s]', '', chunk_text).strip().lower()
                    if chunk_text.lower().strip() in HALLUCINATIONS or clean_check in HALLUCINATIONS:
                        continue

                    # 말하는 속도(WPM) 실시간 측정 및 템포 동적 적응 (CJK 문자 띄어쓰기 부재 보정)
                    is_cjk = bool(re.search(r'[\u3040-\u30ff\u4e00-\u9fff]', chunk_text))
                    if is_cjk:
                        cjk_chars = len(re.findall(r'[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7a3a-zA-Z0-9]', chunk_text))
                        words_in_chunk = max(1, int(cjk_chars / 2.2))
                    else:
                        words_in_chunk = len(chunk_text.split())
                    if seg_dur_sec > 0.4 and words_in_chunk > 0:
                        inst_wpm = (words_in_chunk / seg_dur_sec) * 60.0
                        self._update_speech_tempo(inst_wpm, seg_dur_sec)

                    # 3. 음성 감지 시각 갱신
                    self.last_speech_time = time.time()

                    # 문맥 프롬프트 옵션이 켜져 있을 때만 직전 문맥 계승 (기본 OFF)
                    if self.use_context_prompt:
                        now = time.time()
                        if now - self.last_speech_time > 8.0:
                            self.last_context_prompt = ""
                        self.last_context_prompt = (self.last_context_prompt + " " + chunk_text).strip()[-280:]
                    else:
                        self.last_context_prompt = ""

                    print(f"[실시간 인식 | {stt_name}] {chunk_text}", flush=True)

                    if not self.sentence_mode:
                        offer_queue(self.trans_queue, (chunk_text, stt_name, spk_info, None,
                                              self._pause_generation))
                    else:
                        if self._active_stt_provider == "deepgram":
                            if self._segment_source and self._segment_source != stt_name:
                                self._queue_segments(self._segmenter.flush('source_change'))
                            self._segment_source = stt_name
                            event = {'type': 'Results', 'session_id': f'local:{stt_name}',
                                     'is_final': True, 'speech_final': speech_end, 'speaker': spk_info,
                                     'channel': {'alternatives': [{'transcript': chunk_text}]}}
                            self._queue_segments(self._segmenter.accept(event))
                            if self.preview_callback and self._segmenter.pending:
                                self.preview_callback(self._segmenter.render(self._segmenter.pending), stt_name)
                        else:
                            # 로컬 STT / Groq 전용: SpeechSegmenter 대기 없이 즉각/완결형 플러시 (0ms 오버헤드)
                            diar_enabled = bool(self.config.get("speaker_diarization_enabled", False))
                            if diar_enabled and self.sentence_buffer and getattr(self, 'current_sentence_speaker', None) and spk_info:
                                cur_spk_num = self.current_sentence_speaker[0]
                                new_spk_num = spk_info[0]
                                if cur_spk_num != new_spk_num or cur_spk_num <= 0 or new_spk_num <= 0:
                                    prev_sentence = " ".join(self.sentence_buffer).strip()
                                    clean_prev = re.sub(r'[\W_]+', '', prev_sentence.lower())
                                    if clean_prev and clean_prev not in ('um', 'uh', 'hmm', 'ah', 'eh', 'er', 'mhm', 'oh'):
                                        offer_queue(self.trans_queue, (prev_sentence, stt_name, self.current_sentence_speaker, None, self._pause_generation))
                                    self.sentence_buffer = []
                                    self.current_sentence_speaker = spk_info

                            if not self.sentence_buffer and spk_info:
                                self.current_sentence_speaker = spk_info
                            elif spk_info and not getattr(self, 'current_sentence_speaker', None):
                                self.current_sentence_speaker = spk_info

                            self.sentence_buffer.append(chunk_text)
                            accumulated = " ".join(self.sentence_buffer).strip()

                            # 실시간 타이핑 프리뷰 표시
                            if self.preview_callback:
                                cur_spk = getattr(self, 'current_sentence_speaker', None)
                                is_muted = False
                                if cur_spk and cur_spk[0] > 0 and self.speaker_identifier and self.config.get("speaker_diarization_enabled", False):
                                    s_name = f"화자 {cur_spk[0]}"
                                    is_muted = self.speaker_identifier.is_speaker_muted(s_name)

                                if not is_muted:
                                    cur_trans = self.config.get("translation_engine", "google")
                                    preview_text = accumulated
                                    if cur_spk and self.config.get("speaker_diarization_enabled", False):
                                        _, s_name, s_col = cur_spk[:3]
                                        latest_name = self.speaker_identifier.get_display_name(f"화자 {cur_spk[0]}") if self.speaker_identifier and cur_spk[0] > 0 else (self.speaker_identifier.get_display_name(s_name) if self.speaker_identifier else s_name)
                                        preview_text = f"<span style='color: {s_col}; font-weight: bold;'>[{latest_name}]</span> {accumulated}"
                                    self.preview_callback(preview_text, f"{stt_name} + {cur_trans}")

                            # 문장 완결 판단
                            is_complete = SemanticClauseDetector.check_clause_boundary(
                                accumulated, chunk_text, max_words=getattr(self, 'max_clause_words', 24)
                            )
                            # VAD 침묵에 도달해 발화가 종결된 청크인 경우 즉각 완결
                            if speech_end and not SemanticClauseDetector.is_dangling(accumulated):
                                is_complete = True

                            if is_complete:
                                offer_queue(self.trans_queue, (accumulated, stt_name, getattr(self, 'current_sentence_speaker', None), None, self._pause_generation))
                                self.sentence_buffer = []
                                self.current_sentence_speaker = None

            except Exception as e:
                print(f"[STT 루프 오류] {e}")

        while not self._speech_events.empty():
            self._consume_speech_events()
        if self._active_stt_provider == "deepgram":
            self._queue_segments(self._segmenter.flush('stop'))
        elif self.sentence_buffer:
            full_sentence = " ".join(self.sentence_buffer).strip()
            self.sentence_buffer = []
            if full_sentence:
                cur_stt = self._current_stt_label()
                offer_queue(self.trans_queue, (full_sentence, cur_stt, getattr(self, 'current_sentence_speaker', None), None, self._pause_generation))
