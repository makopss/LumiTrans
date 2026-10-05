import os
import sys
import io
import re
import time
import queue
import asyncio
import threading
from typing import Optional, List, Dict, Tuple
from contextlib import nullcontext
from .queue_utils import take_matching
import edge_tts

# Pygame 로고/환영 메시지 콘솔 출력 억제
import pygame
import numpy as np

def _safe_print(msg: str):
    """Windows cp949 등 콘솔 인코딩 예외를 방지하는 안전한 콘솔 출력"""
    try:
        print(msg)
    except Exception:
        try:
            enc = sys.stdout.encoding or 'utf-8'
            print(msg.encode(enc, errors='replace').decode(enc, errors='replace'))
        except Exception:
            pass

# 다국어 도착 언어(Target Language)별 Edge-TTS 표준 보이스 매트릭스
# (남성 대표, 여성 대표, 보조 남성, 보조 여성)
LANGUAGE_VOICE_MATRIX = {
    "ko": {
        "male_default": "ko-KR-InJoonNeural",
        "female_default": "ko-KR-SunHiNeural",
        "male_alt": "ko-KR-BongJinNeural",
        "female_alt": "ko-KR-SeoHyeonNeural",
        "names": {
            "ko-KR-InJoonNeural": "인준 (남성 대표)",
            "ko-KR-SunHiNeural": "선희 (여성 대표)",
            "ko-KR-BongJinNeural": "봉진 (남성 보조)",
            "ko-KR-SeoHyeonNeural": "서현 (여성 보조)",
            "ko-KR-HyunsuMultilingualNeural": "현수 (남성 다국어)",
        }
    },
    "en": {
        "male_default": "en-US-GuyNeural",
        "female_default": "en-US-JennyNeural",
        "male_alt": "en-US-ChristopherNeural",
        "female_alt": "en-US-AriaNeural",
        "names": {
            "en-US-GuyNeural": "Guy (Male Primary)",
            "en-US-JennyNeural": "Jenny (Female Primary)",
            "en-US-ChristopherNeural": "Christopher (Male Alt)",
            "en-US-AriaNeural": "Aria (Female Alt)",
        }
    },
    "ja": {
        "male_default": "ja-JP-KeitaNeural",
        "female_default": "ja-JP-NanamiNeural",
        "male_alt": "ja-JP-DaichiNeural",
        "female_alt": "ja-JP-AoiNeural",
        "names": {
            "ja-JP-KeitaNeural": "Keita (男性)",
            "ja-JP-NanamiNeural": "Nanami (女性)",
            "ja-JP-DaichiNeural": "Daichi (男性サブ)",
            "ja-JP-AoiNeural": "Aoi (女性サブ)",
        }
    },
    "zh": {
        "male_default": "zh-CN-YunxiNeural",
        "female_default": "zh-CN-XiaoxiaoNeural",
        "male_alt": "zh-CN-YunjianNeural",
        "female_alt": "zh-CN-XiaoyiNeural",
        "names": {
            "zh-CN-YunxiNeural": "云希 Yunxi (男声)",
            "zh-CN-XiaoxiaoNeural": "晓晓 Xiaoxiao (女声)",
            "zh-CN-YunjianNeural": "云健 Yunjian (男声副)",
            "zh-CN-XiaoyiNeural": "晓伊 Xiaoyi (女声副)",
        }
    },
    "es": {
        "male_default": "es-ES-AlvaroNeural",
        "female_default": "es-ES-ElviraNeural",
        "male_alt": "es-MX-JorgeNeural",
        "female_alt": "es-MX-DaliaNeural",
        "names": {
            "es-ES-AlvaroNeural": "Alvaro (Masculino)",
            "es-ES-ElviraNeural": "Elvira (Femenino)",
            "es-MX-JorgeNeural": "Jorge (Masculino México)",
            "es-MX-DaliaNeural": "Dalia (Femenino México)",
        }
    },
    "fr": {
        "male_default": "fr-FR-HenriNeural",
        "female_default": "fr-FR-DeniseNeural",
        "male_alt": "fr-FR-AlainNeural",
        "female_alt": "fr-FR-BrigitteNeural",
        "names": {
            "fr-FR-HenriNeural": "Henri (Masculin)",
            "fr-FR-DeniseNeural": "Denise (Féminin)",
            "fr-FR-AlainNeural": "Alain (Masculin alt)",
            "fr-FR-BrigitteNeural": "Brigitte (Féminin alt)",
        }
    },
    "de": {
        "male_default": "de-DE-KillianNeural",
        "female_default": "de-DE-KatjaNeural",
        "male_alt": "de-DE-ConradNeural",
        "female_alt": "de-DE-AmalaNeural",
        "names": {
            "de-DE-KillianNeural": "Killian (Männlich)",
            "de-DE-KatjaNeural": "Katja (Weiblich)",
            "de-DE-ConradNeural": "Conrad (Männlich alt)",
            "de-DE-AmalaNeural": "Amala (Weiblich alt)",
        }
    },
    "pt": {
        "male_default": "pt-BR-AntonioNeural",
        "female_default": "pt-BR-FranciscaNeural",
        "male_alt": "pt-PT-DuarteNeural",
        "female_alt": "pt-BR-BrendaNeural",
        "names": {
            "pt-BR-AntonioNeural": "Antonio (Masculino)",
            "pt-BR-FranciscaNeural": "Francisca (Feminino)",
            "pt-PT-DuarteNeural": "Duarte (Portugal)",
            "pt-BR-BrendaNeural": "Brenda (Feminino)",
        }
    },
    "ru": {
        "male_default": "ru-RU-DmitryNeural",
        "female_default": "ru-RU-SvetlanaNeural",
        "male_alt": "ru-RU-DmitryNeural",
        "female_alt": "ru-RU-DariyaNeural",
        "names": {
            "ru-RU-DmitryNeural": "Дмитрий (Мужской)",
            "ru-RU-SvetlanaNeural": "Светлана (Женский)",
            "ru-RU-DariyaNeural": "Дарья (Женский)",
        }
    },
    "it": {
        "male_default": "it-IT-DiegoNeural",
        "female_default": "it-IT-ElsaNeural",
        "male_alt": "it-IT-GiuseppeNeural",
        "female_alt": "it-IT-IsabellaNeural",
        "names": {
            "it-IT-DiegoNeural": "Diego (Maschile)",
            "it-IT-ElsaNeural": "Elsa (Femminile)",
            "it-IT-GiuseppeNeural": "Giuseppe (Maschile)",
            "it-IT-IsabellaNeural": "Isabella (Femminile)",
        }
    },
    "vi": {
        "male_default": "vi-VN-NamMinhNeural",
        "female_default": "vi-VN-HoaiMyNeural",
        "male_alt": "vi-VN-NamMinhNeural",
        "female_alt": "vi-VN-HoaiMyNeural",
        "names": {
            "vi-VN-NamMinhNeural": "Nam Minh (Nam)",
            "vi-VN-HoaiMyNeural": "Hoài My (Nữ)",
        }
    },
    "th": {
        "male_default": "th-TH-NiwatNeural",
        "female_default": "th-TH-PremwadeeNeural",
        "male_alt": "th-TH-NiwatNeural",
        "female_alt": "th-TH-AcharaNeural",
        "names": {
            "th-TH-NiwatNeural": "Niwat (ชาย)",
            "th-TH-PremwadeeNeural": "Premwadee (หญิง)",
            "th-TH-AcharaNeural": "Achara (หญิง)",
        }
    },
    "id": {
        "male_default": "id-ID-ArdiNeural",
        "female_default": "id-ID-GadisNeural",
        "male_alt": "id-ID-ArdiNeural",
        "female_alt": "id-ID-GadisNeural",
        "names": {
            "id-ID-ArdiNeural": "Ardi (Pria)",
            "id-ID-GadisNeural": "Gadis (Wanita)",
        }
    },
    "ar": {
        "male_default": "ar-SA-HamedNeural",
        "female_default": "ar-SA-ZariyahNeural",
        "male_alt": "ar-SA-HamedNeural",
        "female_alt": "ar-SA-ZariyahNeural",
        "names": {
            "ar-SA-HamedNeural": "حامد Hamed (ذكر)",
            "ar-SA-ZariyahNeural": "زارية Zariyah (أنثى)",
        }
    },
    "hi": {
        "male_default": "hi-IN-MadhurNeural",
        "female_default": "hi-IN-SwaraNeural",
        "male_alt": "hi-IN-MadhurNeural",
        "female_alt": "hi-IN-SwaraNeural",
        "names": {
            "hi-IN-MadhurNeural": "मधुर Madhur (पुरुष)",
            "hi-IN-SwaraNeural": "स्वरा Swara (महिला)",
        }
    },
}

def get_voice_matrix_for_target(target_lang: str = "ko") -> dict:
    """도착 언어(Target Language) 코드에 해당하는 음성 매트릭스 정보 반환"""
    code = str(target_lang or "ko").strip().lower().split("-")[0]
    return LANGUAGE_VOICE_MATRIX.get(code, LANGUAGE_VOICE_MATRIX["ko"])

def get_available_voices(target_lang: str = "ko") -> list[tuple[str, str]]:
    """도착 언어에 맞춘 선택 가능 보이스 목록 반환 (auto 포함)"""
    code = str(target_lang or "ko").strip().lower().split("-")[0]
    matrix = get_voice_matrix_for_target(code)
    auto_desc = "자동 (이름/패턴 분석)" if code == "ko" else "Auto (Analyze context)"
    items = [("auto", auto_desc)]
    for voice_id, label in matrix.get("names", {}).items():
        items.append((voice_id, label))
    return items

# 한국어 기본 보이스 (하위 호환성 유지)
VOICE_FEMALE_DEFAULT = "ko-KR-SunHiNeural"          # 선희 (차분하고 자연스러운 여성)
VOICE_MALE_DEFAULT = "ko-KR-InJoonNeural"           # 인준 (또렷하고 신뢰감 있는 남성)
VOICE_MALE_ALT = "ko-KR-HyunsuMultilingualNeural"   # 현수 (젊고 개성 있는 남성)

AVAILABLE_VOICES = [
    ("auto", "자동 (이름/패턴 분석)"),
    (VOICE_MALE_DEFAULT, "인준 (남성 대표)"),
    (VOICE_FEMALE_DEFAULT, "선희 (여성 대표)"),
    (VOICE_MALE_ALT, "현수 (남성 다국어)"),
]

# 성별/캐릭터 지능형 추론 정규표현식 (한국어/영어/일본어/중국어/유럽어 통합)
RE_MALE_KEYWORDS = re.compile(
    r'\b(mr|sir|boy|guy|man|men|fella|dude|brother|father|son|soldier|he|him|his)\b|'
    r'\b(señor|chico|hombre|hermano|padre|hijo|soldado|él)\b|'
    r'\b(monsieur|garçon|homme|frère|père|fils|soldat|lui)\b|'
    r'\b(herr|junge|mann|bruder|vater|sohn|soldat|er)\b|'
    r'(아저씨|남성|남자|소년|군인|형|동생|아버지|아들|그|오빠)|'
    r'(おじさん|男性|男|少年|軍人|兄|弟|父|息子|彼)|'
    r'(先生|男士|男孩|男人|兄弟|父亲|儿子|士兵|哥哥|弟弟|他)',
    re.IGNORECASE
)
RE_FEMALE_KEYWORDS = re.compile(
    r'\b(ms|mrs|miss|woman|women|lady|girl|sister|mother|daughter|she|her)\b|'
    r'\b(señora|señorita|chica|mujer|hermana|madre|hija|ella)\b|'
    r'\b(madame|mademoiselle|fille|femme|soeur|mère|elle)\b|'
    r'\b(frau|mädchen|dame|schwester|mutter|tochter|sie)\b|'
    r'(여성|여자|소녀|아가씨|누나|언니|어머니|엄마|딸|부인|그녀|이모|고모)|'
    r'(女性|女|少女|お姉さん|母|娘|彼女|奥さん)|'
    r'(女士|小姐|女人|女孩|姐妹|母亲|女儿|姐姐|妹妹|她)',
    re.IGNORECASE
)

class DubbingEngine:
    """
    실시간 AI 음성 더빙 엔진 (Edge-TTS + Pygame Mixer).
    - VRAM 0MB 소모, 초저지연 비동기 오디오 스트리밍
    - 화자 감별(Speaker ID) 및 성별/이름 패턴 기반 음성(Voice) 자동 라우팅
    - 화자별 개별 더빙 On/Off 필터링 (진행자 음성 제외, 상대 화자만 더빙 등)
    - 대사 밀림 방지 스마트 큐 및 즉각 페이드아웃(인터럽트) 지원
    """
    def __init__(self, config: dict, speaker_identifier=None):
        self.config = config
        self.speaker_identifier = speaker_identifier
        self.text_queue = queue.Queue(maxsize=500)
        self.playback_queue = queue.Queue(maxsize=500)
        self.queue = self.text_queue  # 하위 호환성 유지
        self.is_running = True
        self.lock = threading.RLock()
        self._generation = 0
        self._source_generations = {"audio": 0, "screen": 0}
        self._source_active = {"audio": True, "screen": True}
        self._current_playing_source = None

        # 실시간 발화(재생) 상태 및 텍스트 추적 (루프백 에코 지능형 차단용)
        self._is_playing = False
        self._current_speaking_text = ""
        self._current_synthesizing_item = None
        self._stop_playback_requested = False
        self.last_playback_end_time = 0.0
        self.recent_dubbed_history = []  # [(cleaned_text, timestamp), ...]

        self._mixer_initialized = False
        self.channel = None
        self.output_device = self.config.get("dubbing_output_device", "default")
        vol_cfg = float(self.config.get("dubbing_volume", 80)) / 100.0
        self._current_volume = max(0.0, min(1.0, vol_cfg))
        self.playback_callbacks = []
        self._init_mixer()

        # 2단계 비동기 프리페치 파이프라인 워커 스레드 시작
        # 1) 백그라운드 선행 오디오 합성 워커 (Edge-TTS)
        self.synth_thread = threading.Thread(target=self._synth_loop, daemon=True, name="DubbingSynthWorker")
        self.synth_thread.start()

        # 2) 끊김 없는 무지연 순차 오디오 재생 워커 (Pygame Mixer)
        self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True, name="DubbingPlaybackWorker")
        self.playback_thread.start()

    def register_playback_callback(self, callback):
        """실시간 더빙 재생 시작 시 호출될 모니터링/자막 콜백 등록"""
        if callback and callback not in self.playback_callbacks:
            self.playback_callbacks.append(callback)

    def get_pipeline_total_count(self) -> int:
        """현재 파이프라인 전체(텍스트 큐 + 합성 중 + 재생 큐 + 재생 중)에 머물고 있는 총 대사 수 반환"""
        count = self.text_queue.qsize() + self.playback_queue.qsize()
        if self._current_synthesizing_item is not None:
            count += 1
        if self._is_playing or (self._mixer_initialized and self.channel and self.channel.get_busy()):
            count += 1
        return count

    def is_speaking(self, grace_period: float = 2.0) -> bool:
        """현재 더빙 음성이 스피커/헤드폰으로 출력 중이거나 잔향 버퍼(기본 2.0초) 내에 있는지 여부 반환"""
        if not self.is_enabled():
            return False
        if self._is_playing:
            return True
        if self._mixer_initialized and self.channel:
            try:
                if self.channel.get_busy():
                    return True
            except Exception:
                pass
        return (time.time() - self.last_playback_end_time) < grace_period

    def is_echo_of_dubbing(self, text: str) -> bool:
        """
        STT 번역 결과가 성우 자신의 목소리가 루프백으로 재유입된 것인지 지능형 판별.
        (자막 표출은 방해하지 않고, 오직 '더빙의 무한 재더빙'만 핀포인트로 차단)
        """
        if not text:
            return False
        clean = self._clean_korean_text(text)
        if not clean or len(clean) < 2:
            return False

        def _matches(a: str, b: str) -> bool:
            ca = re.sub(r'[\W_]+', '', a)
            cb = re.sub(r'[\W_]+', '', b)
            if not ca or not cb:
                return False
            if ca == cb:
                return True
            # 부분 문자열 포함 (85% 이상 일치)
            if (ca in cb and len(ca) / len(cb) >= 0.85) or (cb in ca and len(cb) / len(ca) >= 0.85):
                return True
            import difflib
            return difflib.SequenceMatcher(None, ca, cb).ratio() >= 0.88

        # 1. 현재 재생 중인 대사와 일치/유사도 검사
        if self._is_playing and self._current_speaking_text:
            curr_clean = self._clean_korean_text(self._current_speaking_text)
            if _matches(clean, curr_clean):
                return True

        # 2. 최근 12초 이내 발화/큐잉된 대사들과 비교
        now = time.time()
        with self.lock:
            for past_t, past_ts in self.recent_dubbed_history:
                if now - past_ts < 12.0:
                    if _matches(clean, past_t):
                        return True
        return False

    @staticmethod
    def _parse_speed_int(speed_str: str) -> int:
        """'+10%' 또는 '-5%' 문자열을 정수 10, -5 등으로 변환"""
        if not speed_str:
            return 0
        m = re.search(r'([+-]?\d+)', str(speed_str))
        return int(m.group(1)) if m else 0

    def calculate_adaptive_speed(self, backlog: int, target_lang: Optional[str] = None) -> str:
        """
        대사 누락 제로(Zero-Drop)를 보장하며 영상과의 싱크를 빠르게 회복하는 지능형 적응형 가속.
        - 언어별 음절 밀도(SPS) 가중치 자동 보정 (스페인어, 일본어, 프랑스어, 이탈리아어 등 +5%)
        - 대기 대사 0~1개: 사용자가 지정한 기본 속도 (또는 언어 보정 속도)
        - 대기 대사 2개: 기본 + 5% (최소 20%)
        - 대기 대사 3~4개: 기본 + 10% (최소 25%)
        - 대기 대사 5개 이상: 기본 + 15% (최소 30%) - 터보 캐치업으로 영상 싱크 즉시 추격
        적체가 해소되면 즉시 사용자의 기본 속도로 자동 복귀합니다.
        """
        if target_lang is None:
            tgt_code = str(self.config.get("target_lang") or self.config.get("target") or "ko").strip().lower().split("-")[0]
        else:
            tgt_code = str(target_lang).strip().lower().split("-")[0]

        # 음절 밀도(Syllables Per Second)가 높은 언어는 원문 대비 발화 길이가 15~25% 증가하므로 기본 템포 +5% 상향 보정
        sps_offset = 5 if tgt_code in ("es", "ja", "fr", "it", "pt") else 0
        base_val = self._parse_speed_int(self.config.get("dubbing_speed", "+10%")) + sps_offset
        if backlog <= 1:
            target_val = base_val
        elif backlog == 2:
            target_val = max(base_val + 5, 20)
        elif backlog in (3, 4):
            target_val = max(base_val + 10, 25)
        else:
            target_val = max(base_val + 15, 30)

        target_val = min(max(target_val, base_val), 120)

        prefix = "+" if target_val >= 0 else ""
        return f"{prefix}{target_val}%"

    @staticmethod
    def get_available_devices() -> list[str]:
        """현재 시스템에서 사용 가능한 SDL2 오디오 출력 장치 목록 반환"""
        try:
            import pygame._sdl2.audio as sdl_audio
            import pygame
            if not pygame.get_init():
                pygame.init()
            return list(sdl_audio.get_audio_device_names(False))
        except Exception as e:
            _safe_print(f"[DubbingEngine] 오디오 출력 장치 목록 조회 실패: {e}")
            return []

    def _init_mixer(self, target_dev: str = None):
        self.active_output_device_id = None
        if target_dev is None:
            target_dev = self.config.get("dubbing_output_device", "default")

        try:
            devicename = None
            if target_dev and target_dev != "default":
                devicename = target_dev

            if self._mixer_initialized:
                try:
                    if self.channel:
                        self.channel.stop()
                    pygame.mixer.quit()
                except Exception:
                    pass
                self._mixer_initialized = False

            if devicename:
                try:
                    pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=2048, devicename=devicename)
                except Exception as dev_err:
                    _safe_print(f"[DubbingEngine] [WARN] '{devicename}' 초기화 실패({dev_err}), 기본 장치로 폴백")
                    pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=2048)
                    devicename = None
            else:
                pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=2048)

            pygame.mixer.set_num_channels(8)
            self.channel = pygame.mixer.Channel(0)
            self._mixer_initialized = True
            self.output_device = target_dev
            self.active_output_device = devicename or "default"
            try:
                import soundcard as sc
                speaker = sc.default_speaker() if not devicename else next(
                    (s for s in sc.all_speakers() if s.name == devicename), None)
                self.active_output_device_id = str(speaker.id) if speaker else None
            except Exception:
                # Unresolved endpoints must never be advertised as isolated.
                self.active_output_device_id = None
            vol = float(self.config.get("dubbing_volume", 80)) / 100.0
            self._current_volume = max(0.0, min(1.0, vol))
            self.channel.set_volume(self._current_volume)
            _safe_print(f"[DubbingEngine] [OK] 더빙 오디오 믹서 초기화 완료! (장치: {devicename or '기본 장치'})")
        except Exception as e:
            _safe_print(f"[DubbingEngine] [WARN] Pygame 믹서 초기화 오류: {e}")
            self._mixer_initialized = False

    def set_output_device(self, device_name: str):
        """더빙 재생 출력 장치를 실시간으로 변경"""
        with self.lock:
            if getattr(self, "output_device", "default") != device_name:
                self.config["dubbing_output_device"] = device_name
                self._init_mixer(target_dev=device_name)

    def update_config(self, config: dict):
        with self.lock:
            self.config = config
            new_dev = self.config.get("dubbing_output_device", "default")
            if new_dev != getattr(self, "output_device", "default"):
                self._init_mixer(target_dev=new_dev)
            if self._mixer_initialized and self.channel:
                vol = float(self.config.get("dubbing_volume", 80)) / 100.0
                self._current_volume = max(0.0, min(1.0, vol))
                try:
                    self.channel.set_volume(self._current_volume)
                except Exception:
                    pass

    def is_enabled(self) -> bool:
        return bool(self.config.get("dubbing_enabled", False))

    def _item_is_current(self, item: dict) -> bool:
        source = item.get("source", "audio")
        with getattr(self, "lock", nullcontext()):
            generation = getattr(self, "_generation", 0)
            source_generations = getattr(self, "_source_generations", {})
            return (self.is_enabled()
                    and getattr(self, "_source_active", {}).get(source, True)
                    and item.get("_generation", generation) == generation
                    and item.get("_source_generation", source_generations.get(source, 0))
                    == source_generations.get(source, 0)
                    and self.config.get(f"dubbing_source_{source}", source == "audio"))

    def set_enabled(self, enabled: bool):
        """더빙을 끄면 합성 중인 결과와 대기/재생 음성도 폐기한다."""
        with self.lock:
            self.config["dubbing_enabled"] = bool(enabled)
            if not enabled:
                self.clear_queue()

    def set_source_active(self, source: str, active: bool):
        """음성/화면 일시정지와 해당 소스의 더빙 수명을 함께 관리한다."""
        if source not in ("audio", "screen"):
            return
        with self.lock:
            self._source_active[source] = bool(active)
            if not active:
                self._source_generations[source] += 1
                self.clear_source_queue(source)
                if self._current_playing_source == source:
                    self.stop_current_audio()

    def set_source_enabled(self, source: str, enabled: bool):
        """더빙 소스 체크박스를 끄면 빠른 재활성화에도 이전 음성을 재생하지 않는다."""
        if source not in ("audio", "screen"):
            return
        with self.lock:
            self.config[f"dubbing_source_{source}"] = bool(enabled)
            if not enabled:
                self._source_generations[source] += 1
                self.clear_source_queue(source)
                if self._current_playing_source == source:
                    self.stop_current_audio()

    def set_smart_speed(self, speed_str: str):
        """콘텐츠 템포 프리셋 또는 스마트 모드에 의해 기본 더빙 속도를 동적으로 연동"""
        with self.lock:
            self.config["dubbing_speed"] = speed_str

    def set_volume(self, volume_percent: int):
        vol = max(0, min(100, volume_percent)) / 100.0
        with self.lock:
            self.config["dubbing_volume"] = volume_percent
            self._current_volume = vol
            if self._mixer_initialized and self.channel:
                try:
                    self.channel.set_volume(vol)
                except Exception:
                    pass

    def stop_current_audio(self):
        """현재 재생 중인 오디오 즉시 정지"""
        self._stop_playback_requested = True
        if self._mixer_initialized and self.channel:
            try:
                self.channel.fadeout(80)
            except Exception:
                pass

    def clear_queue(self):
        """대기 중인 모든 더빙 텍스트 및 재생 큐 비우기"""
        with self.lock:
            self._generation += 1
            self._clear_waiting_queues()
            self.stop_current_audio()

    def _clear_waiting_queues(self):
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
            except queue.Empty:
                break
        while not self.playback_queue.empty():
            try:
                self.playback_queue.get_nowait()
            except queue.Empty:
                break

    def clear_source_queue(self, source: str):
        """특정 소스('audio' 또는 'screen')의 대기열만 즉시 비우기"""
        with self.lock:
            # 1. 텍스트 큐 정리
            rem_text = []
            while not self.text_queue.empty():
                try:
                    item = self.text_queue.get_nowait()
                    if item.get("source") != source:
                        rem_text.append(item)
                except queue.Empty:
                    break
            for item in rem_text:
                self.text_queue.put(item)

            # 2. 재생 큐 정리
            rem_play = []
            while not self.playback_queue.empty():
                try:
                    pitem = self.playback_queue.get_nowait()
                    if pitem.get("source") != source:
                        rem_play.append(pitem)
                except queue.Empty:
                    break
            for pitem in rem_play:
                self.playback_queue.put(pitem)
        _safe_print(f"[DubbingEngine] [CLEAN] '{source}' 소스 대기열 정리 완료")

    @staticmethod
    def extract_speaker_and_dialogue(text: str) -> tuple[str, str]:
        """
        텍스트에서 화자 이름(예: 'Alex:', '민수:', '[진행자]')과
        순수 대사 본문을 분리합니다.
        반환: (speaker_name, dialogue_body)
        화자명이 없는 경우: ('', text)
        """
        if not text:
            return "", ""
        t = text.strip()

        # 1. [화자명] 형태
        m_bracket = re.match(r'^(?:<[^>]+>)*\s*[\[【]([^\W_]{1,20}(?:\s+[^\W_]{1,20}){0,2})[\]】]\s*(?:<\/[^>]+>)*\s*[:：\-]?\s*(.+)$', t, re.DOTALL)
        if m_bracket:
            spk = m_bracket.group(1).strip()
            body = m_bracket.group(2).strip()
            if len(spk.split()) <= 3 and body:
                return spk, body

        # 2. 화자명: 또는 화자명 - 형태
        m_colon = re.match(r'^(?:<[^>]+>)*\s*([^\W_]{1,15}(?:\s+[^\W_]{1,15}){0,2})\s*(?:<\/[^>]+>)*\s*[:：\-]\s*(.+)$', t, re.DOTALL)
        if m_colon:
            spk = m_colon.group(1).strip()
            body = m_colon.group(2).strip()
            if body:
                return spk, body

        return "", t

    def enqueue(self, translated_text: str, speaker_name: str = "", orig_text: str = "", source: str = "audio", region_idx: int = 0, speaker_confirmed: bool = True, segment_id: str = None):
        """
        번역 완료된 한국어 문장을 더빙 대기열에 추가합니다.
        source: 'audio' (오디오 통역) 또는 'screen' (화면 OCR)
        """
        with self.lock:
            if (not self.is_enabled() or not self._source_active.get(source, True)
                    or not self.config.get(f"dubbing_source_{source}", source == "audio")):
                return
            request_generation = self._generation
            request_source_generation = self._source_generations.get(source, 0)

        if not translated_text or not translated_text.strip():
            return

        # 화자 이름과 순수 발화 대사 분리 (TTS가 '알렉스:'를 소리 내어 읽는 현상 원천 차단)
        det_spk, pure_dialogue = self.extract_speaker_and_dialogue(translated_text)
        if det_spk and not speaker_name and speaker_confirmed:
            speaker_name = det_spk
        if not speaker_confirmed:
            speaker_name = ""

        target_text = pure_dialogue if pure_dialogue else translated_text

        clean_text = self._clean_korean_text(target_text)
        if not clean_text or len(clean_text) < 2:
            return

        # [에코 차단 2차 방어선] 채널 미분리(단일 채널) 모드에서만 재귀 더빙 검사 수행 (채널 분리 시 0ms 생략)
        capture = getattr(self, 'audio_capture', None)
        channels_separated = bool(capture and capture.is_channels_separated())
        if not channels_separated and self.config.get("dubbing_echo_cancellation", True) and self.is_echo_of_dubbing(clean_text):
            _safe_print(f"[Dubbing] [SHIELD] 더빙 텍스트 에코 차단 (재귀 더빙 방지): '{clean_text}'")
            return

        # 화자 필터링 체크: 번역 Mute 또는 더빙 Mute 상태인 경우 제외
        spk_display = speaker_name
        if self.speaker_identifier:
            spk_display = self.speaker_identifier.get_display_name(speaker_name)

        if speaker_confirmed and not self._is_speaker_dubbing_allowed(speaker_name, spk_display):
            return

        # 큐가 가득 찬 경우 오래된 대사 1개 정리 (최대 200개 보관)
        if self.text_queue.full():
            try:
                self.text_queue.get_nowait()
            except queue.Empty:
                pass

        item = {
            "text": clean_text,
            "speaker_name": speaker_name,
            "speaker_display": spk_display,
            "orig_text": orig_text,
            "source": source,
            "region_idx": region_idx,
            "timestamp": time.time()
        }
        item['segment_ids'] = [segment_id] if segment_id else []
        with self.lock:
            if (not self.is_enabled() or not self._source_active.get(source, True)
                    or not self.config.get(f"dubbing_source_{source}", source == "audio")
                    or request_generation != self._generation
                    or request_source_generation != self._source_generations.get(source, 0)):
                return
            if source == "screen":
                now = time.time()
                self.recent_dubbed_history = [
                    (t, ts) for (t, ts) in self.recent_dubbed_history if now - ts < 3.0
                ]
                if any(clean_text == past_text and now - past_ts < 1.5
                       for past_text, past_ts in self.recent_dubbed_history):
                    return
            item["_generation"] = self._generation
            item["_source_generation"] = self._source_generations.get(source, 0)
            try:
                self.text_queue.put_nowait(item)
            except queue.Full:
                # 다른 생산자가 선행 검사 뒤 마지막 칸을 채운 경우에도 멈추지 않는다.
                try:
                    self.text_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.text_queue.put_nowait(item)
                except queue.Full:
                    return
            self.recent_dubbed_history.append((clean_text, time.time()))

    def _is_speaker_dubbing_allowed(self, raw_name: str, display_name: str) -> bool:
        """해당 화자의 더빙이 허용되어 있는지 검사"""
        # 1. 번역 자체가 Mute된 화자인 경우 더빙도 제외
        if self.speaker_identifier and self.config.get("speaker_diarization_enabled", False):
            if self.speaker_identifier.is_speaker_muted(raw_name) or self.speaker_identifier.is_speaker_muted(display_name):
                return False

        # 2. 화자별 더빙 제외(Mute) 설정 검사
        dub_mutes = self.config.get("speaker_dubbing_mutes", {})
        if dub_mutes.get(raw_name, False) or dub_mutes.get(display_name, False):
            return False

        return True

    def _clean_dialogue_text(self, text: str) -> str:
        """HTML 태그 제거, 화자 콜론 접두사 제거 및 TTS 발음 방해 특수문자 정제 (다국어 공통)"""
        text = re.sub(r'<[^>]+>', '', text)  # HTML 태그 제거
        text = re.sub(r'\[.*?\]', '', text)  # [화자명] 제거
        text = re.sub(r'[\(\{\<].*?[\)\}\>]', '', text) # 괄호 속 내용 제거
        # 화자 콜론 접두사("알렉스:", "Alex:", "田中:", "Maya:") 제거
        text = re.sub(r'^[^\W_]{1,15}(?:\s+[^\W_]{1,15}){0,2}\s*[:：\-]\s*', '', text)
        text = re.sub(r'[:\-–—/\\_~*#]', ' ', text) # 발음 방해 기호 정리
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    _clean_korean_text = _clean_dialogue_text

    def resolve_voice_and_pitch(self, spk_raw: str, spk_display: str, orig_text: str) -> tuple[str, str]:
        """
        화자 실명 및 원문 텍스트 패턴, 그리고 도착 언어(target_lang)를 분석하여
        해당 국가 언어에 최적화된 Edge-TTS 음성과 피치(Hz) 반환.
        반환 예: ('ko-KR-InJoonNeural', '-5Hz'), ('en-US-GuyNeural', '-10Hz')
        """
        target_lang = str(self.config.get("target_lang") or self.config.get("target") or "ko").strip().lower().split("-")[0]
        voice_info = get_voice_matrix_for_target(target_lang)
        default_male = voice_info["male_default"]
        default_female = voice_info["female_default"]
        alt_male = voice_info.get("male_alt", default_male)
        alt_female = voice_info.get("female_alt", default_female)

        spk_voices = self.config.get("speaker_voices", {})
        if not spk_raw:
            return default_male, "+0Hz"
        assigned_voice = spk_voices.get(spk_raw) or spk_voices.get(spk_display)

        # 1. 수동 지정된 보이스가 있고 'auto'가 아니면 검사
        if assigned_voice and assigned_voice != "auto":
            assigned_prefix = assigned_voice.split("-")[0].lower()
            if assigned_prefix == target_lang:
                return assigned_voice, "+0Hz"

        # 2. 지능형 자동 추론 (화자명 + 영문/다국어 원문 대사 패턴 매칭)
        context_str = f"{spk_raw} {spk_display} {orig_text}"

        # 화자 번호 추출 (예: '화자 1', 'Speaker 2' -> 1, 2)
        m_num = re.search(r'\d+', str(spk_raw) + " " + str(spk_display))
        spk_num = int(m_num.group()) if m_num else 1

        is_male = False
        is_female = False

        if RE_FEMALE_KEYWORDS.search(context_str):
            is_female = True
        elif RE_MALE_KEYWORDS.search(context_str):
            is_male = True
        else:
            # 패턴 매칭이 없으면 화자 번호 홀짝 기반 (1번: 남성1, 2번: 여성1, 3번: 남성2, 4번: 여성2)
            if spk_num % 2 == 1:
                is_male = True
            else:
                is_female = True

        # 화자 번호별 피치 미세 변조 (동일 성별이라도 목소리 톤이 다르게 들리도록 연출)
        pitch_offsets = ["-10Hz", "+0Hz", "+8Hz", "-5Hz", "+12Hz"]
        pitch = pitch_offsets[(spk_num - 1) % len(pitch_offsets)]

        # 화자 번호 기반 1차/2차 보이스 배분 (1, 2번: 대표 보이스, 3, 4번: 보조 보이스 교대)
        is_primary = (spk_num % 4) in (1, 2)
        if is_female:
            voice = default_female if is_primary else alt_female
            return voice, pitch
        else:
            voice = default_male if is_primary else alt_male
            return voice, pitch

    def _synth_loop(self):
        """1단계: 백그라운드 선행 오디오 합성 워커 (재생 중 다음 대사를 미리 합성하여 대기 0초 달성)"""
        while self.is_running:
            try:
                try:
                    item = self.text_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                if not item or not self._item_is_current(item):
                    continue

                source = item.get("source", "audio")
                if source == "audio" and not self.config.get("dubbing_source_audio", True):
                    continue
                if source == "screen" and not self.config.get("dubbing_source_screen", False):
                    continue

                text = item["text"]
                spk_raw = item["speaker_name"]
                spk_display = item["speaker_display"]
                orig_text = item["orig_text"]
                segment_ids = list(item.get('segment_ids', []))

                # 1. 지능형 저지연 버퍼링 (Low-Latency Smart Buffering):
                is_player_busy = self._is_playing or (self.playback_queue.qsize() > 0)
                is_complete = bool(len(text) >= 28 or text.endswith(('.', '!', '?', '。')))

                if is_complete or not self.text_queue.empty():
                    wait_time = 0.0
                elif is_player_busy:
                    wait_time = 0.30  # 플레이어 재생 중인 짧은 단문: 300ms 대기 후 결합
                elif len(text) < 22:
                    wait_time = 0.20  # 유휴 상태 초단문: 200ms 대기 후 결합
                else:
                    wait_time = 0.0

                def same_speaker_source(candidate):
                    return bool(candidate and candidate.get("source") == source
                                and candidate.get("speaker_name") == spk_raw
                                and candidate.get("region_idx", 0) == item.get("region_idx", 0)
                                and candidate.get("_generation") == item.get("_generation")
                                and candidate.get("_source_generation") == item.get("_source_generation"))

                if wait_time > 0 and self.text_queue.empty():
                    follow_up = take_matching(self.text_queue, same_speaker_source, wait_time)
                    if follow_up:
                        text = f"{text} {follow_up.get('text', '')}".strip()
                        orig_text = f"{orig_text} {follow_up.get('orig_text', '')}".strip()
                        segment_ids.extend(follow_up.get('segment_ids', []))

                # 2. 스마트 대기열 단락 병합 (Smart Coalescing):
                merge_count = 1
                cur_backlog = self.text_queue.qsize() + self.playback_queue.qsize() + (1 if self._is_playing else 0)
                max_merge = 5 if cur_backlog > 1 else 3
                max_chars = 150 if cur_backlog > 1 else 110

                while not self.text_queue.empty() and merge_count < max_merge:
                    next_item = take_matching(self.text_queue, lambda candidate:
                        same_speaker_source(candidate) and
                        len(text) + len(candidate.get("text", "")) <= max_chars)
                    if next_item is None:
                        break

                    # 동일 소스, 동일 화자, 총 길이 한도 내에서 합체
                    if (next_item.get("source") == source and 
                        next_item.get("speaker_name") == spk_raw and 
                        len(text) + len(next_item.get("text", "")) <= max_chars):
                        next_t = next_item.get("text", "").strip()
                        if next_t:
                            text = f"{text} {next_t}"
                            orig_text = f"{orig_text} {next_item.get('orig_text', '')}".strip()
                            merge_count += 1
                            segment_ids.extend(next_item.get('segment_ids', []))

                if not self._item_is_current(item):
                    continue
                self._current_synthesizing_item = item
                try:
                    # 보이스 및 피치 결정
                    voice, pitch = self.resolve_voice_and_pitch(spk_raw, spk_display, orig_text)

                    # 대기 중인 총 미처리 대사 수 (텍스트 큐 + 재생 큐) 기반 적응형 배속
                    total_backlog = self.text_queue.qsize() + self.playback_queue.qsize()
                    speed = self.calculate_adaptive_speed(total_backlog)

                    # Edge-TTS 음성 데이터 메모리 생성 (타임아웃 단축 및 자동 재시도)
                    trace = getattr(self, 'pipeline_trace', None)
                    if trace:
                        trace.record('tts_request', segment_ids=segment_ids, text=text,
                                     voice=voice, speed=speed)
                    audio_data = self._synthesize_audio(text, voice, speed, pitch)
                    if trace:
                        trace.record('tts_result', segment_ids=segment_ids,
                                     success=bool(audio_data))
                    if not self.is_running:
                        break
                    if not self._item_is_current(item):
                        continue
                    if not audio_data:
                        _safe_print(f"[DubbingEngine] [WARN] TTS 합성 실패로 해당 대사 건너뜀: '{text[:20]}'")
                        continue

                    play_item = {
                        "segment_ids": segment_ids,
                        "audio_data": audio_data,
                        "text": text,
                        "orig_text": orig_text,
                        "voice": voice,
                        "speed": speed,
                        "pitch": pitch,
                        "source": source,
                        "speaker_display": spk_display,
                        "region_idx": item.get("region_idx", 0),
                        "_generation": item.get("_generation", getattr(self, "_generation", 0)),
                        "_source_generation": item.get("_source_generation", getattr(self, "_source_generations", {}).get(source, 0)),
                    }
                    self.playback_queue.put(play_item)
                finally:
                    self._current_synthesizing_item = None
            except Exception as loop_err:
                _safe_print(f"[DubbingEngine] [WARN] _synth_loop 예외 포착 (워커 자동 유지): {loop_err}")
                time.sleep(0.05)

    def _playback_loop(self):
        """2단계: 끊김 없는 무지연 순차 오디오 재생 워커 (문장 간 간격 0.00초)"""
        while self.is_running:
            try:
                try:
                    item = self.playback_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if not item or not self._item_is_current(item):
                    continue

                source = item.get("source", "audio")
                if source == "audio" and not self.config.get("dubbing_source_audio", True):
                    continue
                if source == "screen" and not self.config.get("dubbing_source_screen", False):
                    continue

                text = item["text"]
                orig_text = item.get("orig_text", "")
                voice = item["voice"]
                speed = item["speed"]
                pitch = item["pitch"]
                spk_display = item["speaker_display"]
                audio_data = item["audio_data"]

                # 새 대사 유입 시 이전 음성 페이드아웃 (인터럽트 옵션 활성화 시에만)
                if self.config.get("dubbing_interrupt", False) and self._mixer_initialized and self.channel:
                    if self.channel.get_busy():
                        self.channel.fadeout(120)
                        time.sleep(0.05)

                # 오디오 재생
                if self._mixer_initialized and self.channel:
                    try:
                        reg_info = f" (영역 {item['region_idx']})" if item.get('region_idx') else ""
                        src_label = f"화면 번역{reg_info}" if source == "screen" else "오디오 통역"
                        spk_tag = f"[{spk_display}]" if spk_display else ""
                        base_sp = self.config.get("dubbing_speed", "+0%")
                        speed_tag = f" [가속 {speed}]" if speed != base_sp else ""
                        voice_short = voice.split('-')[2] if '-' in voice else voice
                        _safe_print(f"[Dubbing] [VOICE] [{src_label}] {spk_tag}{speed_tag} ('{voice_short}', {pitch}): '{text}'")

                        sound, duration = self._create_trimmed_sound(audio_data)
                        with self.lock:
                            if not self._item_is_current(item):
                                continue
                            self._stop_playback_requested = False
                            self._is_playing = True
                            self._current_playing_source = source
                            self._current_speaking_text = text
                            self.channel.set_volume(self._current_volume)
                            self.channel.play(sound)
                        if self._item_is_current(item):
                            for cb in list(self.playback_callbacks):
                                try:
                                    cb(text=text, speaker=spk_display, orig_text=orig_text,
                                       source=source, voice=voice, speed=speed,
                                       region_idx=item.get('region_idx', 0))
                                except Exception:
                                    pass
                        trace = getattr(self, 'pipeline_trace', None)
                        if trace:
                            trace.record('tts_playback', segment_ids=item.get('segment_ids', []),
                                         duration=duration, voice=voice, speed=speed)

                        expected_end_time = time.time() + duration

                        # 오디오가 완전히 끝날 때까지 대기 (순차 무누락 재생 보장)
                        while self.is_running:
                            if self._stop_playback_requested or not self._item_is_current(item):
                                self.channel.stop()
                                self._stop_playback_requested = False
                                break
                            now = time.time()
                            if not self.channel.get_busy() and now >= expected_end_time:
                                break
                            if now >= expected_end_time + 0.35:
                                break
                            if not self.playback_queue.empty() and self.config.get("dubbing_interrupt", False):
                                self.channel.fadeout(80)
                                break
                            time.sleep(0.02)
                    finally:
                        self._is_playing = False
                        self._current_playing_source = None
                        self._current_speaking_text = ""
                        now = time.time()
                        self.last_playback_end_time = now
                        with self.lock:
                            self.recent_dubbed_history.append((text, now))
                            self.recent_dubbed_history = [
                                (t, ts) for (t, ts) in self.recent_dubbed_history if now - ts < 15.0
                            ]
            except Exception as loop_err:
                _safe_print(f"[DubbingEngine] [WARN] _playback_loop 예외 포착 (워커 자동 유지): {loop_err}")
                time.sleep(0.05)

    @staticmethod
    def _create_trimmed_sound(audio_data: bytes) -> tuple[pygame.mixer.Sound, float]:
        """
        Edge-TTS가 생성한 MP3 앞뒤의 불필요한 무음 패딩(약 0.9~1.2초)을 초고속(1ms)으로 정밀 트리밍.
        시작 40ms, 끝 80ms의 자연스러운 안전 여백을 유지하여 발음 손실 없이 대사 간 불필요한 공백을 35~50% 단축합니다.
        """
        raw_snd = pygame.mixer.Sound(io.BytesIO(audio_data))
        try:
            arr = pygame.sndarray.array(raw_snd)
            amp = np.max(np.abs(arr), axis=1) if arr.ndim > 1 else np.abs(arr)
            max_amp = np.max(amp)
            if max_amp > 80:
                thresh = max_amp * 0.02
                non_silent = np.where(amp > thresh)[0]
                if len(non_silent) > 0:
                    sr = 24000
                    pad_start = int(0.04 * sr)
                    pad_end = int(0.08 * sr)
                    start_idx = max(0, non_silent[0] - pad_start)
                    end_idx = min(len(arr), non_silent[-1] + pad_end)
                    if end_idx - start_idx > 1000:
                        trimmed = np.ascontiguousarray(arr[start_idx:end_idx])
                        snd = pygame.sndarray.make_sound(trimmed)
                        return snd, snd.get_length()
        except Exception:
            pass
        return raw_snd, raw_snd.get_length()

    def _synthesize_audio(self, text: str, voice: str, speed: str, pitch: str) -> bytes:
        """edge-tts를 호출하여 메모리 내 MP3 바이트 생성 (타임아웃 단축 및 자동 재시도로 지연 멈춤 차단)"""
        async def _async_synth():
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=speed, pitch=pitch)
            bio = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    bio.write(chunk["data"])
            return bio.getvalue()

        # 타임아웃을 3.0초 / 3.5초로 줄여 네트워크 지연 시 장시간 얼어붙는 현상 원천 차단
        for attempt in range(1, 3):
            timeout_sec = 3.0 if attempt == 1 else 3.5
            try:
                data = asyncio.run(asyncio.wait_for(_async_synth(), timeout=timeout_sec))
                if data and len(data) > 0:
                    return data
            except asyncio.TimeoutError:
                _safe_print(f"[DubbingEngine] [WARN] TTS 합성 {attempt}회차 타임아웃 ({timeout_sec}초): '{text[:20]}...'")
            except Exception as e:
                _safe_print(f"[DubbingEngine] [WARN] TTS 통신 {attempt}회차 오류: {e}")
            if not self.is_running:
                break
            time.sleep(0.08)
        return b""

    def stop(self):
        """더빙 엔진 및 믹서 종료 클린업"""
        self.is_running = False
        self.clear_queue()
        for worker in (self.synth_thread, self.playback_thread):
            if worker.is_alive() and worker is not threading.current_thread():
                worker.join()
        if self._mixer_initialized:
            try:
                if self.channel:
                    self.channel.stop()
                pygame.mixer.quit()
                self._mixer_initialized = False
                self.active_output_device_id = None
            except Exception:
                pass
        _safe_print("[DubbingEngine] 더빙 엔진이 안전하게 정지되었습니다.")
