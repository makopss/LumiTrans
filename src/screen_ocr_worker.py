import time
import re
import threading
from PyQt6.QtCore import QObject, pyqtSignal, Qt
from src.screen_capture import capture_screen_area, is_frame_changed, smart_capture_screen_area, preprocess_game_image
from src.i18n import tr

try:
    import wordninja
except Exception:
    wordninja = None

# 이미 온전한 일반 영단어는 wordninja.split() trie 역추적을 생략하여 CPU 낭비 및 오분할 방지
_COMMON_LONG_WORDS = {
    'because', 'between', 'through', 'without', 'against', 'another', 'already', 'always',
    'someone', 'everyone', 'something', 'anything', 'nothing', 'welcome', 'together',
    'tomorrow', 'yesterday', 'tonight', 'morning', 'evening', 'remember', 'understand',
    'important', 'different', 'possible', 'probably', 'perhaps', 'instead', 'suppose',
    'believe', 'thought', 'straight', 'forward', 'outside', 'inside', 'behind', 'around',
    'brother', 'sister', 'daughter', 'general', 'captain', 'soldier', 'professor',
    'building', 'village', 'kingdom', 'monster', 'machine', 'question', 'problem',
    'finally', 'actually', 'certainly', 'definitely', 'immediately', 'completely',
    'absolutely', 'everything', 'anywhere', 'nowhere', 'somewhere', 'sometimes'
}

from collections import OrderedDict

# 성능 최적화: 정규식 패턴 모듈 레벨 사전 컴파일 (호출당 오버헤드 70% 단축)
_RE_NOISE1 = re.compile(r'[\(\[\{]\?.*?[\]\}\)]')
_RE_NOISE2 = re.compile(r'[·•°±«»§©®™†‡…~`^|]')
_RE_PUNCT_SPACE = re.compile(r'([.,?!:;])([^\W\d_])')
_RE_CAMEL_LOWER_UPPER = re.compile(r'([a-z])([A-Z])')
_RE_ALPHA_DIGIT = re.compile(r'([a-zA-Z])(\d)')
_RE_DIGIT_ALPHA = re.compile(r'(\d)([a-zA-Z])')
_RE_SPEAKER_COLON = re.compile(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\.\s*(?:[a-z]{3,8}\s+)?([A-Z])')
_RE_DOT_LOWER = re.compile(r'\.\s+([a-z])')
_RE_DOT_CONJ = re.compile(r'\.\s+(and|or|but|because|so|yet|though|although)\b', re.IGNORECASE)
_RE_IAM = re.compile(r'\blam\b')
_RE_WILL = re.compile(r'\b(wil|wll)\b', re.IGNORECASE)
_RE_SPACES = re.compile(r'\s+')
_RE_ALPHA_ONLY = re.compile(r'[^a-zA-Z]')
_RE_CJK = re.compile(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]')
_RE_LETTERS = re.compile(r'[^\W\d_]')
_RE_SPEAKER_BRACKET = re.compile(r'^(?:<[^>]+>)*\s*[\[【]([^\n\]】]{1,30})[\]】]\s*(?:<\/[^>]+>)*\s*[:：\-]?\s*(.+)$', re.DOTALL)
_RE_SPEAKER_COLON_SEP = re.compile(r'^(?:<[^>]+>)*\s*([A-Z가-힣0-9][A-Za-z가-힣0-9\'.\-]*(?:\s+[A-Z가-힣0-9][A-Za-z가-힣0-9\'.\-]*){0,4})\s*(?:<\/[^>]+>)*\s*[:：\-]\s*(.+)$', re.DOTALL)
_RE_SPEAKER_LINK = _RE_SPEAKER_COLON_SEP
_RE_SPEAKER_HEADER = re.compile(r'^(?P<speaker>(?:\[[^\n\]]{1,30}\]\s*[:：\-]?|[A-Z가-힣0-9][A-Za-z가-힣0-9\'.\-]*(?:\s+[A-Z가-힣0-9][A-Za-z가-힣0-9\'.\-]*){0,4}\s*[:：]))\s*(?P<dialogue>.+)$', re.DOTALL)

# 노이즈 패턴: 특수 제어문자, 박스 드로잉, 블록 요소, 기하학 도형, 딩뱃, 화살표, 수학 기호, 부수 등
_RE_UNWANTED_GLYPHS = re.compile(
    r'[\u2500-\u259f'       # Box Drawing & Block Elements (─, │, ┌, █, ▌, ░ 등)
    r'\u25a0-\u25ff'       # Geometric Shapes (■, □, ▲, ▼, ◆, ○ 등)
    r'\u2600-\u27bf'       # Dingbats & Misc Symbols (★, ☎, ✓ 등)
    r'\u2190-\u23ff'       # Arrows, Math & Technical (←, ↑, →, ↓, ∀, ∂, ∃, √, ∞, ≈, ≠ 등)
    r'\u2e80-\u2ef3'       # CJK Radicals Supplement
    r'\u2f00-\u2fd5'       # Kangxi Radicals
    r'\u31c0-\u31ef'       # CJK Strokes
    r'\u200b-\u200f\ufeff\ufffd' # Zero-width & replacement char
    r']'
)

# 반복되는 장식성 특수기호 및 테두리 파편 (---, ===, ___, ~~~, ///, \\\, |||, +++, *** 등)
_RE_REPEATED_SYMBOLS = re.compile(r'([_\-=\\/|+*~^`·•°±§«»~`|]){2,}')
_RE_STANDALONE_NOISE_PUNCT = re.compile(r'^[_\-=\\/|+*~^`·•°±§«»~`|;:,.!?"\'\s]+$')

# UI 테두리나 체력바 등에서 한자로 오인식되기 쉬운 단일 획/도형성 한자 및 극희귀 부수 글자 집합
_SUSPICIOUS_GEOMETRIC_HANZI = set(
    "丨亅丿乛冂冖冫卜卩厂厶囗巛彡彳屮尢弋彐夊夂疋疒癶虍覀豸艮隹鬯鬲一十口二三"
)

# 영문/라틴어에서 허용되는 대표적 1~2글자 정상 단어 목록
_VALID_SHORT_LATIN_WORDS = {
    "i", "a", "an", "am", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is",
    "it", "me", "my", "no", "of", "on", "or", "so", "to", "up", "us", "we", "ok",
    "tv", "mr", "dr", "vs", "hi", "oh", "ah", "ha", "eh", "ye", "yo", "ex", "id", "pc"
}

# 중국어 단일 글자로서 발화/자막에 실제 쓰일 수 있는 고빈도 의미 단어
_COMMON_SINGLE_HANZI = set(
    "是好的你看走对听来去想问有没这那会能要行敌杀打退快进等等给死真"
)

# CJK 및 언어군별 식별 정규식
_RE_HANZI = re.compile(r'[\u4e00-\u9fff]')
_RE_HANGUL = re.compile(r'[\uac00-\ud7af]')
_RE_KANA = re.compile(r'[\u3040-\u30ff]')
_RE_LATIN = re.compile(r'[a-zA-Z]')
_RE_VOWELS = re.compile(r'[aeiouyAEIOUY]')
_RE_ALPHANUMERIC = re.compile(r'[\w]', re.UNICODE)

# 고성능 화면 번역 메모리 LRU 캐시 (반복 등장하는 게임 UI, 선택지, 대사 0.05ms 즉각 응답)
_SCREEN_TRANSLATION_CACHE = OrderedDict()
_SCREEN_CACHE_LOCK = threading.Lock()
_MAX_SCREEN_CACHE_SIZE = 256

def is_valid_ocr_text(text: str, source_lang: str = "auto") -> bool:
    """
    OCR 텍스트가 의미 있는 발화/자막인지 검증:
    - 기호/특수문자만 있거나 기호 비율이 비정상적으로 높은 텍스트 거부
    - 4회 이상 연속 동일 문자 반복 글리치 거부
    - 한자 오인식 필터링:
      * 영어/유럽어 모드에서 한자 포함 시 거부
      * 한국어 모드에서 한글 없이 고립된 한자만 있는 경우 거부
      * 선/테두리 모양의 기하학적 한자(一, 十, 口, 囗, 冂, 卜, 丨 등)만으로 구성된 경우 거부
      * 단일 한자 시 일상적 고빈도 의미 단어가 아니면 거부
    - 영문/라틴어 모드:
      * 단어 길이가 3자 이상인데 모음(a,e,i,o,u,y)이 전혀 없는 무의미한 자음 나열(xzkj, fghj 등) 거부
      * 1~2자 단어인데 'ok', 'to', 'in' 등 유효 단어가 아닌 경우 거부
    """
    if not text or not text.strip():
        return False
    clean = text.strip()

    # 1. 단순 기호, 점, 테두리만 있는 경우 거부
    if _RE_STANDALONE_NOISE_PUNCT.match(clean):
        return False

    # 2. 유의미한 알파벳/숫자/문자 추출
    alphanumeric = _RE_ALPHANUMERIC.findall(clean)
    alphanumeric = [c for c in alphanumeric if c != '_']
    if not alphanumeric:
        return False

    # 3. 신호 대 잡음비 (SNR): 전체 길이 대비 유효 문자 비율 검사 (길이가 4 이상일 때 35% 미만이면 거부)
    if len(clean) >= 4 and (len(alphanumeric) / len(clean)) < 0.35:
        return False

    # 4. 동일 문자 4회 이상 연속 반복 글리치 거부 (예: aaaaaa, xxxx, ------, 口口口口)
    for i in range(len(clean) - 3):
        if clean[i] == clean[i+1] == clean[i+2] == clean[i+3] and not clean[i].isspace():
            return False

    src_lang = str(source_lang or "auto").strip().lower().split("-")[0]

    hanzi_chars = _RE_HANZI.findall(clean)
    hangul_chars = _RE_HANGUL.findall(clean)
    kana_chars = _RE_KANA.findall(clean)
    latin_chars = _RE_LATIN.findall(clean)

    # 5. 한자(Hanzi) 관련 오인식 필터링
    if hanzi_chars:
        # 5-1. 영어/유럽어 등 비CJK 출발 언어인데 한자가 포함된 경우 -> 배경/아이콘 오인식이므로 거부
        if src_lang in ("en", "es", "fr", "de", "ru", "it", "pt", "vi", "th", "id", "ar", "hi"):
            return False

        # 5-2. 한국어 모드인데 한글이 하나도 없고 고립된 한자만 있는 경우 거부
        if src_lang == "ko" and not hangul_chars:
            return False

        # 5-3. 한자가 모두 선/박스/테두리 모양의 기하학적 한자 집합에 속하는 경우 거부 (예: 一, 一十, 冂, 囗, 口, 丨, 卜 등)
        if all(ch in _SUSPICIOUS_GEOMETRIC_HANZI for ch in hanzi_chars) and not hangul_chars and not kana_chars and not latin_chars:
            return False

        # 5-4. 한자만 1글자 있는 경우: 일상 고빈도 단어("敵", "好", "是" 등)가 아니면 거부
        if len(clean) == 1 and clean in hanzi_chars:
            if clean not in _COMMON_SINGLE_HANZI and clean != "敵":
                return False

    # 6. 영어/라틴어 단어 유효성 검사 (자음 나열 무의미 문자열 차단)
    if latin_chars and not hangul_chars and not kana_chars and not hanzi_chars:
        # 영문/라틴어는 최소 2글자 이상의 알파벳 필요
        if len(latin_chars) < 2:
            return False

        words = re.findall(r'[a-zA-Z]+', clean)
        if not words:
            return False

        # 6-1. 1~2글자 단독 단어인 경우 허용된 영어 단어 목록 확인
        if len(words) == 1 and len(words[0]) <= 2:
            if words[0].lower() not in _VALID_SHORT_LATIN_WORDS:
                return False

        # 6-2. 3글자 이상 단어가 있을 때, 모든 단어가 모음(a,e,i,o,u,y)이 하나도 없는 자음 샐러드인지 검사
        has_any_vowel = False
        for w in words:
            if _RE_VOWELS.search(w):
                has_any_vowel = True
                break
            elif w.lower() in ("tv", "mr", "dr", "vs", "st", "ft", "ok"):
                has_any_vowel = True
                break
        if not has_any_vowel:
            return False

    # 7. 단일 글자 검사
    if len(clean) == 1:
        # 단일 한글 완성형 음절 허용 ("네", "응", "예", "왜" 등)
        if hangul_chars:
            return True
        # 단일 가나 허용
        if kana_chars:
            return True
        # 단일 한자는 위 5-4에서 검사 완료됨
        if hanzi_chars and (clean in _COMMON_SINGLE_HANZI or clean == "敵"):
            return True
        return False

    # 8. 최종 글자 수 검사: 유효 알파벳/한글/가나/한자/다국어 문자 2자 이상
    letters = _RE_LETTERS.findall(clean)
    return len(letters) >= 2


def clean_ocr_text(text: str, source_lang: str = "auto") -> str:
    """
    다국어 및 영문 OCR 결과 초고속 지능형 정제:
    - 박스 드로잉, 기하학 도형, 딩뱃, 강희 부수 등 비정상 글리프 제거
    - 출발 언어가 비CJK(영어, 유럽어 등)인 경우 오인식된 한자(Hanzi) 파편 원천 제거
    - 사전 컴파일된 정규식으로 CPU 낭비 없이 최고 속도 실행
    """
    if not text:
        return ""

    src_lang = str(source_lang or "auto").strip().lower().split("-")[0]

    # 1. 제어문자 및 비정상 글리프(박스 드로잉, 기하학 도형, 딩뱃, 부수 등) 제거
    text = _RE_UNWANTED_GLYPHS.sub(' ', text)

    # 2. 특수 노이즈 및 버튼 잔해 필터
    text = _RE_NOISE1.sub('', text)
    text = _RE_NOISE2.sub(' ', text)
    text = _RE_REPEATED_SYMBOLS.sub(' ', text)

    # 3. 비CJK(영어, 유럽어 등) 출발 언어일 때: 한자(Hanzi)는 100% OCR 배경/아이콘 오인식이므로 제거
    if src_lang in ("en", "es", "fr", "de", "ru", "it", "pt", "vi", "th", "id", "ar", "hi"):
        text = _RE_HANZI.sub(' ', text)

    # 4. 문장부호 뒤 띄어쓰기 보정
    text = _RE_PUNCT_SPACE.sub(r'\1 \2', text)

    # 5. CamelCase 분리
    text = _RE_CAMEL_LOWER_UPPER.sub(r'\1 \2', text)
    text = _RE_ALPHA_DIGIT.sub(r'\1 \2', text)
    text = _RE_DIGIT_ALPHA.sub(r'\1 \2', text)

    # 6. 화자 이름 끝 콜론 치환 및 화자 뒤 UI 아이콘/문양 글리프 잔해 정제
    text = _RE_SPEAKER_COLON.sub(r'\1: \2', text)

    # 7. 쉼표(,)가 마침표(.)로 오인식되어 문장이 어색하게 토막 나는 현상 복원
    text = _RE_DOT_LOWER.sub(r', \1', text)
    text = _RE_DOT_CONJ.sub(r', \1', text)

    # 8. 게임 자막 OCR 빈출 오탈자 사전 보정
    text = _RE_IAM.sub('I am', text)
    text = _RE_WILL.sub('will', text)

    # 9. 엉겨붙은 영단어 덩어리 지능형 단어 분리 (wordninja)
    if wordninja is not None and (_RE_LATIN.search(text) is not None):
        try:
            # 화자 이름 패턴이 문두에 있는 경우 분리 보호하여 콜론 및 인명 훼손 방지
            speaker_prefix = ""
            m_spk = _RE_SPEAKER_HEADER.match(text)
            if m_spk:
                speaker_prefix = m_spk.group('speaker').strip() + " "
                text = m_spk.group('dialogue')

            words = text.split()
            cleaned = []
            i = 0
            while i < len(words):
                w = words[i]
                m_punct = re.match(r'^([^\w\s]*)([\w\'-]+?)([^\w\s]*)$', w)
                if m_punct:
                    prefix_p, core, suffix_p = m_punct.group(1), m_punct.group(2), m_punct.group(3)
                    alpha = _RE_ALPHA_ONLY.sub('', core)
                    # TitleCase 단어(예: Treadwell, Slytherins)이거나 일반 장문어면 split 건너뜀 (고유명사/인명 보존)
                    is_title_case = bool(re.match(r'^[A-Z][a-z]+$', alpha))
                    if len(alpha) >= 7 and alpha.lower() not in _COMMON_LONG_WORDS and not is_title_case:
                        parts = wordninja.split(core)
                        valid_words = [p for p in parts if len(p) >= 3]
                        if len(valid_words) >= 2:
                            if len(parts[-1]) == 1 and i + 1 < len(words):
                                next_w = words[i+1]
                                joined = (parts[-1] + next_w).lower()
                                if joined in ('we', 'will', 'with', 'what', 'when', 'who', 'were', 'was', 'would'):
                                    parts = parts[:-1]
                                    words[i+1] = joined
                            parts[0] = prefix_p + parts[0]
                            parts[-1] = parts[-1] + suffix_p
                            cleaned.extend(parts)
                            i += 1
                            continue
                cleaned.append(w)
                i += 1
            text = (speaker_prefix + " ".join(cleaned)).strip()
        except Exception:
            pass

    # 10. 공백 정리
    text = _RE_IAM.sub('I am', text)
    text = _RE_SPACES.sub(' ', text).strip()
    return text

clean_ocr_english_text = clean_ocr_text


def extract_speaker_and_dialogue(text: str) -> tuple[str, str]:
    """텍스트에서 화자 이름과 순수 대사 본문을 분리합니다."""
    if not text:
        return "", ""
    t = text.strip()

    # 1. [화자명] 형태
    m_bracket = _RE_SPEAKER_BRACKET.match(t)
    if m_bracket:
        spk = m_bracket.group(1).strip()
        body = m_bracket.group(2).strip()
        if len(spk.split()) <= 4 and body:
            return spk, body

    # 2. 화자명: 또는 화자명 - 형태
    m_colon = _RE_SPEAKER_COLON_SEP.match(t)
    if m_colon:
        spk = m_colon.group(1).strip()
        body = m_colon.group(2).strip()
        if body:
            return spk, body

    return "", t


class ScreenOCRSignals(QObject):
    subtitle_signal = pyqtSignal(str, str, str, int)  # (original, translated, engine, roi_idx)
    status_signal = pyqtSignal(str)                   # 상태 메시지
    result_ready = pyqtSignal(object)


class ScreenOCRWorker(threading.Thread):
    def __init__(self, config, translator, parent=None, stt_worker=None, dubbing_engine=None):
        super().__init__(daemon=True, name="ScreenOCRWorker")
        self.signals = ScreenOCRSignals()
        self.subtitle_signal = self.signals.subtitle_signal
        self.status_signal = self.signals.status_signal
        self.result_ready = self.signals.result_ready

        self.config = config
        self.translator = translator
        self.stt_worker = stt_worker
        self.dubbing_engine = dubbing_engine
        self.is_running = True
        self.is_paused = not (self.config.get("auto_start_screen", False) and self.config.get("screen_translate_enabled", False))

        self._ocr = None
        self._ocr_lock = threading.Lock()
        self._ocr_exec_lock = threading.Lock()
        # 다중 영역 상태 추적: {roi_idx: {"last_image": img, "last_text": str, "last_check_time": float}}
        self.roi_states = {}
        self._request_lock = threading.RLock()
        self._cycle_lock = threading.Lock()
        self._generation = 0
        self._request_counter = 0
        self._latest_requests = {}
        self._instant_thread = None
        self.result_ready.connect(self._deliver_result, Qt.ConnectionType.QueuedConnection)

    def isRunning(self):
        return self.is_alive()

    def set_dubbing_engine(self, dubbing_engine):
        self.dubbing_engine = dubbing_engine

    def set_stt_worker(self, stt_worker):
        self.stt_worker = stt_worker

    def _check_and_link_speaker_name(self, text: str):
        """화면 자막에서 'Character Name: ...' 형태 감지 시 음성 화자에 실명 자동 연동"""
        if not text or not self.stt_worker:
            return
        spk_id = getattr(self.stt_worker, 'speaker_identifier', None)
        if not spk_id or not getattr(spk_id, 'is_enabled', False):
            return
        m = _RE_SPEAKER_LINK.match(text)
        if m:
            detected_name = m.group(1).strip()
            spk_id.suggest_ocr_name(detected_name)

    def get_ocr_lock(self):
        return self._ocr_exec_lock

    def _get_ocr(self):
        with self._ocr_lock:
            if self._ocr is None:
                try:
                    from src.isolated_ocr import get_isolated_ocr
                    self._ocr = get_isolated_ocr()
                except Exception as e:
                    print(f"[ScreenOCR] 격리 OCR 엔진 초기화 오류: {e}")
            return self._ocr

    def _regions(self):
        rois = self.config.get("screen_rois", [])
        if not rois and self.config.get("screen_roi"):
            rois = [self.config["screen_roi"]]
        return tuple(tuple(r) for r in rois
                     if isinstance(r, (tuple, list)) and len(r) == 4 and r[2] > 20 and r[3] > 20)

    def update_config(self, config):
        """설정(언어, 엔진 등) 변경 시 실시간 반영 및 기존 화면 텍스트 즉시 재번역 유도"""
        with self._request_lock:
            self.config = dict(config)
            if "screen_translate_enabled" in self.config:
                self.is_paused = not bool(self.config["screen_translate_enabled"])
            if self.translator and hasattr(self.translator, "update_config"):
                self.translator.update_config(config)
            self.invalidate_regions()

    def invalidate_regions(self):
        """Invalidate queued and in-flight work, including remove/re-add at the same coordinates."""
        with self._request_lock:
            self._generation += 1
            self._latest_requests.clear()
            self.roi_states = {}

    def _begin_request(self, rois, idx, instant=False):
        with self._request_lock:
            self._request_counter += 1
            self._latest_requests[idx] = self._request_counter
            return (self._generation, rois, idx, self._request_counter, instant, self._translation_signature())

    def _translation_signature(self):
        return tuple(self.config.get(key) for key in (
            "translation_engine", "selected_llm_model", "llm_backend", "device",
            "source_lang", "target_lang"))

    def _is_current(self, token):
        generation, rois, idx, serial, instant, engine_signature = token
        with self._request_lock:
            return bool(self.is_running and generation == self._generation
                        and rois == self._regions() and 0 <= idx < len(rois)
                        and self._latest_requests.get(idx) == serial
                        and engine_signature == self._translation_signature()
                        and (instant or not self.is_paused))

    def _deliver_result(self, payload):
        # Runs on the GUI thread. Validate again after the queued Qt delivery.
        token, original, translated, engine = payload
        if not self._is_current(token):
            return
        idx = token[2]
        self.subtitle_signal.emit(original, translated, engine, idx)
        success = bool(translated and "원문" not in engine)
        self.status_signal.emit(tr("ocr_status_done", engine=engine) if success else tr("ocr_status_retrying"))
        if success and self.dubbing_engine and self.dubbing_engine.is_enabled():
            instant = bool(token[4]) if len(token) > 4 else False
            spk_trans, pure_trans = extract_speaker_and_dialogue(translated)
            spk_orig, _ = extract_speaker_and_dialogue(original)
            self.dubbing_engine.enqueue(
                translated_text=pure_trans or translated,
                speaker_name=spk_trans or spk_orig or "",
                orig_text=original,
                source="screen",
                region_idx=idx + 1,
                force_active=instant,
            )

    def _process_region(self, rois, idx, ocr, instant=False) -> bool:
        generation = self._generation
        roi = rois[idx]
        state = self.roi_states.get(idx)
        signature = self._translation_signature()
        if state is None or state.get("roi", roi) != roi or state.get("engine_signature", signature) != signature:
            state = {"last_thumb": None, "last_text": "", "last_check_time": 0.0}
            self.roi_states[idx] = state
        state["roi"] = roi
        state["engine_signature"] = signature
        now = time.monotonic()
        retry_at = state.get("retry_at", 0.0)
        if instant:
            img = capture_screen_area(roi)
        else:
            force_check = (not state["last_text"] or retry_at > 0) and now - state["last_check_time"] >= 2.0
            img, thumb, changed = smart_capture_screen_area(roi,
                last_thumb=state.get("last_thumb"), force_full=force_check)
            state["last_thumb"] = thumb
            if not changed:
                return False
        if img is None:
            return False
        state["last_check_time"] = now
        ocr_input = preprocess_game_image(img) if self.config.get("screen_ocr_preprocess", True) else img
        with self._ocr_exec_lock:
            result, _ = ocr(ocr_input)
        if not self.is_running or generation != self._generation or rois != self._regions():
            return False
        if not result:
            state["last_text"] = ""
            state["last_trans_time"] = 0.0
            return False

        min_conf = float(self.config.get("screen_ocr_min_confidence", 0.45))
        src_lang = str(self.config.get("source_lang", "auto")).strip().lower().split("-")[0]

        valid_lines = []
        for item in result:
            if not item or len(item) < 3:
                continue
            box, raw_text, score = item[0], item[1], float(item[2])
            raw_text = raw_text.strip() if raw_text else ""
            if not raw_text:
                continue
            # 1. 기본 신뢰도 임계값 필터 (0.45 미만은 배경 노이즈/무늬 오인식 확률이 극히 높으므로 제외)
            if score < min_conf:
                continue
            # 2. 1~2글자의 극단적 단문은 오인식 확률이 높으므로 엄격한 신뢰도(0.60) 요구
            if len(raw_text) <= 2 and score < 0.60:
                continue
            # 3. 라인별 텍스트 1차 정제
            cleaned_line = clean_ocr_text(raw_text, source_lang=src_lang)
            if not cleaned_line:
                continue
            valid_lines.append((box, cleaned_line, score))

        if not valid_lines:
            state["last_text"] = ""
            state["last_trans_time"] = 0.0
            return False

        sorted_lines = sorted(valid_lines, key=lambda r: (r[0][0][1] // 15, r[0][0][0]))
        text = clean_ocr_text(" ".join(r[1].strip() for r in sorted_lines if r[1]), source_lang=src_lang)
        if len(text) > 400:
            text = text[:400] + "..."
        if not is_valid_ocr_text(text, source_lang=src_lang):
            return False
        normalized = " ".join(text.casefold().split())
        last_norm = " ".join(state.get("last_text", "").casefold().split())
        if not instant and normalized == last_norm:
            return False
        if not instant and last_norm:
            last_trans_time = state.get("last_trans_time", 0.0)
            if now - last_trans_time < 5.0:
                # 빠른 길이 비교로 연산 단축 후 필요시에만 SequenceMatcher
                len_ratio = len(normalized) / max(1, len(last_norm))
                if 0.85 <= len_ratio <= 1.15:
                    import difflib
                    sim = difflib.SequenceMatcher(None, normalized, last_norm).ratio()
                    if sim >= 0.75:
                        return False
        if not instant and retry_at > now and state.get("retry_text") == text:
            return False
        token = self._begin_request(rois, idx, instant)
        if not self._is_current(token):
            return False
        self._check_and_link_speaker_name(text)

        # LRU 번역 캐시 확인 (0.05ms 즉각 반환)
        cache_key = (
            self.config.get("source_lang", "auto"),
            self.config.get("target_lang", "ko"),
            self.config.get("translation_engine", ""),
            normalized
        )
        cached_result = None
        with _SCREEN_CACHE_LOCK:
            if cache_key in _SCREEN_TRANSLATION_CACHE:
                cached_result = _SCREEN_TRANSLATION_CACHE[cache_key]
                _SCREEN_TRANSLATION_CACHE.move_to_end(cache_key)

        if cached_result is not None:
            translated, engine = cached_result
        else:
            self.status_signal.emit(tr("ocr_status_translating_area", n=idx + 1))
            try:
                translated, engine = self.translator.translate(text)
            except Exception as error:
                print(f"[ScreenOCR 번역 오류] {error}")
                translated, engine = text, "원문 유지"
            if translated and engine != "원문 유지":
                with _SCREEN_CACHE_LOCK:
                    _SCREEN_TRANSLATION_CACHE[cache_key] = (translated, engine)
                    if len(_SCREEN_TRANSLATION_CACHE) > _MAX_SCREEN_CACHE_SIZE:
                        _SCREEN_TRANSLATION_CACHE.popitem(last=False)

        if not self._is_current(token):
            return False
        if translated and engine != "원문 유지":
            state["last_text"] = text
            state["last_trans_time"] = time.monotonic()
            state["retry_at"] = 0.0
            state.pop("retry_text", None)
        else:
            state["retry_at"] = time.monotonic() + 2.0
            state["retry_text"] = text
        tag = f"즉시·{engine}" if instant else engine
        self.result_ready.emit((token, text, translated or text, tag or "원문 유지"))
        return True

    def _capture_cycle(self, instant=False, generation=None) -> bool:
        with self._cycle_lock:
            if generation is not None and generation != self._generation:
                return False
            if not self.is_running:
                return False
            if not instant and self.is_paused:
                return False
            rois = self._regions()
            if not rois:
                if instant:
                    self.status_signal.emit(tr("ocr_status_no_areas"))
                return False
            ocr = self._get_ocr()
            if ocr is None:
                self.status_signal.emit(tr("ocr_status_load_failed"))
                return False
            generation = self._generation
            had_activity = False
            for idx in range(len(rois)):
                if not self.is_running or generation != self._generation or rois != self._regions():
                    break
                if not instant and self.is_paused:
                    break
                res = self._process_region(rois, idx, ocr, instant)
                if res:
                    had_activity = True
            return had_activity

    def run(self):
        print("[ScreenOCR] 실시간 화면 감시 백그라운드 스레드 시작됨 (적응형 고성능 모드).")
        idle_streak = 0
        while self.is_running:
            idle = self.is_paused
            had_activity = False
            try:
                if not idle:
                    had_activity = self._capture_cycle()
            except Exception as error:
                print(f"[ScreenOCR Worker 예외] {error}")
            if idle:
                idle_streak = 0
                time.sleep(0.5)
            else:
                base_ms = max(150, self.config.get("screen_check_interval_ms", 250))
                if had_activity:
                    idle_streak = 0
                    time.sleep(base_ms / 1000.0)
                else:
                    idle_streak += 1
                    # 정지 화면 적응형 백오프: CPU 점유율 50% 절감 (최대 400ms)
                    delay_ms = min(400, base_ms + min(150, idle_streak * 25))
                    time.sleep(delay_ms / 1000.0)

    def trigger_instant_capture(self):
        # One bounded instant job; repeated clicks cannot create unbounded threads.
        with self._request_lock:
            if not self.is_running or (self._instant_thread and self._instant_thread.is_alive()):
                return
            generation = self._generation
            self._instant_thread = threading.Thread(target=self._do_instant_capture,
                args=(generation,), daemon=True, name="InstantScreenOCR")
            self._instant_thread.start()

    def _do_instant_capture(self, generation=None):
        try:
            if generation is None or generation == self._generation:
                self._capture_cycle(instant=True, generation=generation)
        except Exception as error:
            print(f"[ScreenOCR Instant 예외] {error}")

    def set_paused(self, paused: bool):
        with self._request_lock:
            self.is_paused = bool(paused)
            self.config["screen_translate_enabled"] = not paused
        self.invalidate_regions()
        self.status_signal.emit(tr("ocr_status_paused") if paused else tr("ocr_status_monitoring"))

    set_paused_state = set_paused

    def requestInterruption(self):
        self.is_running = False

    def wait(self, timeout_ms=None):
        from src.screen_capture import join_thread_pumping_gui
        timeout_sec = None if timeout_ms is None else timeout_ms / 1000.0
        join_thread_pumping_gui(self, timeout_sec)

    def terminate(self):
        self.is_running = False

    def stop(self, timeout_sec=5.0):
        from src.screen_capture import join_thread_pumping_gui
        self.is_running = False
        self.invalidate_regions()
        join_thread_pumping_gui(self, timeout_sec)
        if self._instant_thread and self._instant_thread.is_alive() and self._instant_thread is not threading.current_thread():
            try:
                join_thread_pumping_gui(self._instant_thread, 1.0)
            except Exception:
                pass
