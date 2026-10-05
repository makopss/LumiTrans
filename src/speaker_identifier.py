import os
import sys
import re
import time
import threading
import numpy as np
from PyQt6.QtCore import QObject
from src.i18n import tr
from .speaker_recognition import SpeakerRecognition

def _safe_print(msg: str):
    """Windows 콘솔 cp949 인코딩 안전 출력"""
    try:
        print(msg)
    except Exception:
        try:
            enc = sys.stdout.encoding or 'utf-8'
            print(msg.encode(enc, errors='replace').decode(enc, errors='replace'))
        except Exception:
            pass

def localize_speaker_status(status_str: str) -> str:
    if not status_str:
        return ""
    mapping = {
        "화자 모델 준비 중": "speaker_model_prep",
        "화자 분리 꺼짐": "speaker_off",
        "화자 음성 모델 준비 중": "speaker_voice_prep",
        "화자 교대 모델 준비 중": "speaker_segmentation_prep",
        "화자 교대 분석 작동 중": "speaker_segmentation_active",
        "단일 발화 판정 · 교대 분석 꺼짐": "speaker_single_speech_mode",
    }
    for ko_text, key in mapping.items():
        if ko_text in status_str:
            return tr(key)
    return status_str

# 화자별 고유 테마 색상 (어두운 배경/밝은 배경 모두에서 뛰어난 가독성)
SPEAKER_COLORS = [
    "#00E5FF",  # 화자 1: 네온 사이언 (고대비 청록)
    "#FFD54F",  # 화자 2: 웜 골드 (부드러운 황금빛)
    "#69F0AE",  # 화자 3: 민트 그린 (상쾌한 연두)
    "#B388FF",  # 화자 4: 소프트 퍼플 (연보라)
    "#FF8A80",  # 화자 5: 코랄 핑크 (화사한 산호분홍)
    "#80D8FF",  # 화자 6: 라이트 블루 (스카이 블루)
    "#FFD180",  # 화자 7: 웜 오렌지 (살구빛)
    "#EA80FC",  # 화자 8: 네온 마젠타 (선명한 자주)
]

class SpeakerIdentifier(SpeakerRecognition, QObject):
    """CPU speaker recognition with persistent names, aliases and mute controls."""
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.lock = threading.RLock()
        self.is_enabled = self.config.get("speaker_diarization_enabled", False)
        self.threshold = float(self.config.get("speaker_similarity_threshold", 0.42))
        self.max_speakers = int(self.config.get("speaker_max_count", 2))
        self.speaker_aliases = dict(self.config.get("speaker_aliases", {}))
        # Existing aliases without provenance are conservatively treated as manual.
        self.alias_sources = dict(self.config.get("speaker_alias_sources", {}))
        self.speaker_mutes = dict(self.config.get("speaker_mutes", {}))
        self.ocr_auto_mapping = self.config.get("speaker_ocr_auto_mapping", True)
        self.segmentation_enabled = self.config.get("speaker_segmentation_enabled", True)

        self.extractor = None
        self.manager = None
        self.diarizer = None
        self.model_loaded = False
        self.diarizer_loaded = False
        self.current_speaker_count = 0
        self.speaker_color_map = {}  # {speaker_name: color_hex}
        self.speaker_profiles_data = {} # {spk_name: {"centroid": np.ndarray, "exemplars": list[np.ndarray]}}
        self.external_speakers = set()  # Deepgram에서 확정된 화자 ID (음성 임베딩과 별개)
        self._external_id_map = {}  # Deepgram 0-based id -> 로컬 화자 번호(1..max)
        self.last_active_speaker = None
        self.last_active_time = 0.0
        self.speaker_updated_callback = None
        self._tts_refs = None
        self._init_recognition()

        # 화자 감별 모델은 실제 다중 화자 분리가 활성화(is_enabled)되었을 때만 지연 로딩 (시작 지연 0초)
        if self.is_enabled:
            threading.Thread(target=self._ensure_model_loaded, daemon=True).start()

    @property
    def similarity_threshold(self) -> float:
        return self.threshold

    @similarity_threshold.setter
    def similarity_threshold(self, val: float):
        with self.lock:
            self.threshold = float(val)
            self.config["speaker_similarity_threshold"] = float(val)

    def is_tts_echo(self, audio_data: np.ndarray, sample_rate: int = 16000, threshold: float = 0.48) -> tuple[bool, float, str]:
        """
        오디오 청크의 음성 지문이 사전 등록된 Edge-TTS 한국어 보이스(인준, 선희, 현수)와 일치하는지 판별.
        반환: (is_echo, similarity, matched_voice_name)
        """
        if not self.model_loaded:
            return False, 0.0, ""

        if audio_data is None or len(audio_data) < int(sample_rate * 0.25):
            return False, 0.0, ""

        if not self._ensure_model_loaded():
            return False, 0.0, ""

        # TTS 참조 임베딩 사전 로드
        if self._tts_refs is None:
            ref_path = os.path.join(os.path.dirname(__file__), "tts_voice_embeddings.npy")
            if not os.path.exists(ref_path) and getattr(sys, "frozen", False):
                base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
                for candidate in [
                    os.path.join(base, "src", "tts_voice_embeddings.npy"),
                    os.path.join(base, "tts_voice_embeddings.npy"),
                    os.path.join(os.path.dirname(sys.executable), "src", "tts_voice_embeddings.npy"),
                    os.path.join(os.path.dirname(sys.executable), "tts_voice_embeddings.npy")
                ]:
                    if os.path.exists(candidate):
                        ref_path = candidate
                        break
            if os.path.exists(ref_path):
                try:
                    self._tts_refs = np.load(ref_path, allow_pickle=True).item()
                except Exception as e:
                    _safe_print(f"[SpeakerID] TTS 참조 임베딩 로드 오류: {e}")
                    self._tts_refs = {}
            else:
                self._tts_refs = {}

        if not self._tts_refs:
            return False, 0.0, ""

        audio_flat = np.asarray(audio_data, dtype=np.float32).flatten()
        rms = np.sqrt(np.mean(audio_flat ** 2))
        if rms < 0.005:
            return False, 0.0, ""

        with self.lock:
            try:
                stream = self.extractor.create_stream()
                stream.accept_waveform(sample_rate, audio_flat)
                stream.input_finished()

                emb = np.array(self.extractor.compute(stream), dtype=np.float32)
                norm = np.linalg.norm(emb)
                if norm > 0:
                    emb = emb / norm
                else:
                    return False, 0.0, ""

                best_sim = -1.0
                best_voice = ""
                for voice_name, ref_emb in self._tts_refs.items():
                    sim = float(np.dot(emb, ref_emb))
                    if sim > best_sim:
                        best_sim = sim
                        best_voice = voice_name

                is_echo = (best_sim >= threshold)
                return is_echo, best_sim, best_voice
            except Exception as e:
                _safe_print(f"[SpeakerID] TTS 에코 판별 오류: {e}")
                return False, 0.0, ""

    def update_config(self, config: dict):
        with self.lock:
            self.config = config
            self.is_enabled = bool(config.get("speaker_diarization_enabled", False))
            self.threshold = float(config.get("speaker_similarity_threshold", 0.42))
            self.max_speakers = max(1, int(config.get("speaker_max_count", 2)))
            self.speaker_aliases = dict(config.get("speaker_aliases", {}))
            self.alias_sources = dict(config.get("speaker_alias_sources", {}))
            self.speaker_mutes = dict(config.get("speaker_mutes", {}))
            self.ocr_auto_mapping = config.get("speaker_ocr_auto_mapping", True)
            self.segmentation_enabled = config.get("speaker_segmentation_enabled", True)
            self._configure_recognition()
            self._prune_speakers_over_limit()
        if self.is_enabled:
            threading.Thread(target=self._ensure_model_loaded, daemon=True).start()

    def set_speaker_alias(self, spk_raw_name: str, alias: str):
        """화자 실명 또는 별칭(Alias) 설정 (예: '화자 1' -> '진행자')"""
        with self.lock:
            alias = alias.strip()
            if alias:
                self.speaker_aliases[spk_raw_name] = alias
                self.alias_sources[spk_raw_name] = "manual"
            else:
                self.speaker_aliases.pop(spk_raw_name, None)
                self.alias_sources.pop(spk_raw_name, None)
            self.config["speaker_aliases"] = dict(self.speaker_aliases)
            self.config["speaker_alias_sources"] = dict(self.alias_sources)
        self._notify_speaker_updated()

    def get_display_name(self, spk_raw_name: str) -> str:
        """화자 번호/이름에 매핑된 실명 반환 (없으면 언어별 기본 화자명 반환)"""
        with self.lock:
            alias = self.speaker_aliases.get(spk_raw_name, "")
            if alias:
                return alias
            if spk_raw_name in ("화자 미확정", "Unconfirmed Speaker", "Speaker Unconfirmed"):
                return tr("speaker_unconfirmed")
            if spk_raw_name in ("화자 확인 중", "Checking Speaker"):
                return tr("speaker_pending")
            if spk_raw_name in ("겹친 음성", "Overlapping Speech"):
                return tr("speaker_overlap")
            num = self._extract_speaker_number(spk_raw_name)
            if num > 0:
                return tr("speaker_num", n=num)
            return spk_raw_name

    def map_external_speaker(self, deepgram_index, confirmed=False):
        """Deepgram 0-based 화자 ID를 최대 인원 안의 로컬 화자로 옮긴다.

        한도를 넘는 ID는 목록에 올리지 않고 미확정으로 돌린다.
        """
        from .speaker_recognition import UNKNOWN_COLOR
        if not self.is_enabled or deepgram_index is None:
            return None
        try:
            dg = int(deepgram_index)
        except (TypeError, ValueError):
            return None
        if dg < 0:
            return None

        local = dg + 1
        unknown = (0, tr('speaker_unconfirmed'), UNKNOWN_COLOR)
        is_new = False
        with self.lock:
            if local > self.max_speakers:
                return unknown
            raw_name = f"화자 {local}"
            self._external_id_map[dg] = local
            if confirmed:
                is_new = raw_name not in self.external_speakers
                self.external_speakers.add(raw_name)
                self.last_active_speaker = raw_name
                self.last_active_time = time.time()
                if raw_name not in self.speaker_color_map:
                    self.speaker_color_map[raw_name] = SPEAKER_COLORS[(local - 1) % len(SPEAKER_COLORS)]
            display = self.speaker_aliases.get(raw_name) or self.get_display_name(raw_name)
            color = self.speaker_color_map.get(raw_name, SPEAKER_COLORS[(local - 1) % len(SPEAKER_COLORS)])
        if confirmed and is_new:
            self._notify_speaker_updated()
        return local, display, color

    def register_external_speaker(self, number: int):
        """Deepgram의 확정 화자를 관리 목록과 OCR 연결 대상으로 등록한다."""
        if not isinstance(number, int):
            return None
        # 과거 API는 1-based 화자 번호를 받았다.
        return self.map_external_speaker(number - 1, confirmed=True)

    def apply_max_speakers(self, count: int):
        """최대 인원 한도를 적용하고, 한도를 넘는 등록 화자를 정리한다."""
        with self.lock:
            self.max_speakers = max(1, int(count))
            self.config["speaker_max_count"] = self.max_speakers
            self._prune_speakers_over_limit()
        self._notify_speaker_updated()

    def _prune_speakers_over_limit(self):
        limit = max(1, int(self.max_speakers))
        self._external_id_map = {dg: slot for dg, slot in getattr(self, "_external_id_map", {}).items()
                                 if 1 <= slot <= limit}
        extra_names = []
        for raw in list(self.external_speakers):
            if self._extract_speaker_number(raw) > limit:
                extra_names.append(raw)
                self.external_speakers.discard(raw)
        for raw in list(self.speaker_profiles_data):
            if self._extract_speaker_number(raw) > limit:
                extra_names.append(raw)
                self.speaker_profiles_data.pop(raw, None)
        for raw in extra_names:
            self.speaker_color_map.pop(raw, None)
        if self.current_speaker_count > limit:
            self.current_speaker_count = limit
        last = self.last_active_speaker
        if last and self._extract_speaker_number(last) > limit:
            self.last_active_speaker = None
            self.last_active_time = 0.0

    def set_speaker_muted(self, spk_raw_name: str, is_muted: bool):
        """특정 화자 번역 제외(Mute) 상태 설정 (True: 번역 제외, False: 번역 출력)"""
        with self.lock:
            self.speaker_mutes[spk_raw_name] = bool(is_muted)
            self.config["speaker_mutes"] = dict(self.speaker_mutes)
        self._notify_speaker_updated()

    def is_speaker_muted(self, spk_name: str) -> bool:
        """해당 화자의 번역이 제외(Mute) 상태인지 확인 (원본ID 또는 실명 전달 가능)"""
        if not self.is_enabled or not spk_name:
            return False
        with self.lock:
            if self.speaker_mutes.get(spk_name, False):
                return True
            for raw, alias in self.speaker_aliases.items():
                if alias == spk_name and self.speaker_mutes.get(raw, False):
                    return True
            return False

    def suggest_ocr_name(self, ocr_name: str) -> bool:
        """화면 OCR에서 대화 화자명 감지 시 최근 발화 화자에게 실명 자동 매핑"""
        if not self.is_enabled or not self.ocr_auto_mapping:
            return False
        if not ocr_name:
            return False
        ocr_clean = re.sub(r'[\(\[\{].*?[\]\}\)]', '', ocr_name).strip()
        ocr_clean = re.sub(r'[:\-–—]$', '', ocr_clean).strip()
        if len(ocr_clean) < 2 or len(ocr_clean) > 30:
            return False
        # 시스템 키워드/UI 텍스트 오인식 방지
        ignore_words = {'quest', 'press', 'select', 'level', 'item', 'warning', 'notice', 'hint', 'area', 'map', 'menu', 'system'}
        if ocr_clean.lower() in ignore_words:
            return False

        with self.lock:
            if not self.last_active_speaker:
                return False
            # 최근 2.5초 이내에 발화한 화자만 매핑
            if time.time() - self.last_active_time > 2.5:
                return False
            raw_target = self.last_active_speaker
            current_alias = self.speaker_aliases.get(raw_target, "")
            if current_alias and self.alias_sources.get(raw_target, "manual") == "manual":
                return False
            if current_alias == ocr_clean:
                return False
            self.speaker_aliases[raw_target] = ocr_clean
            self.alias_sources[raw_target] = "ocr"
            self.config["speaker_alias_sources"] = dict(self.alias_sources)
            self.config["speaker_aliases"] = dict(self.speaker_aliases)
            _safe_print(f"[SpeakerID] [LINK] 화면 OCR 대화명 지능형 자동 연동: '{raw_target}' -> '{ocr_clean}'")

        self._notify_speaker_updated()
        return True

    def get_all_known_speakers(self) -> list:
        """현재 등록되거나 설정된 모든 화자의 상태 목록 반환"""
        speakers = []
        with self.lock:
            all_raw_keys = set()
            all_raw_keys.update(self.speaker_profiles_data)
            all_raw_keys.update(self.external_speakers)
            all_raw_keys.update(self.speaker_aliases.keys())
            all_raw_keys.update(self.speaker_mutes.keys())

            def sort_key(k):
                num = self._extract_speaker_number(k)
                return num

            for raw in sorted(all_raw_keys, key=sort_key):
                num = self._extract_speaker_number(raw)
                if num < 1 or num > self.max_speakers:
                    continue
                alias = self.speaker_aliases.get(raw, "")
                display = alias if alias else self.get_display_name(raw)
                color = self.speaker_color_map.get(raw, SPEAKER_COLORS[(num - 1) % len(SPEAKER_COLORS)])
                muted = self.speaker_mutes.get(raw, False)
                speakers.append({
                    "num": num,
                    "raw_name": raw,
                    "alias": alias,
                    "display_name": display,
                    "color": color,
                    "muted": muted
                })
        return speakers

    @property
    def speaker_profiles(self) -> dict:
        """하위 호환성용 화자 프로필 딕셔너리 반환"""
        with self.lock:
            res = {}
            for i in range(1, self.current_speaker_count + 1):
                res[f"화자 {i}"] = self.speaker_aliases.get(f"화자 {i}", self.get_display_name(f"화자 {i}"))
            for k, v in self.speaker_aliases.items():
                res[k] = v
            return res

    def _notify_speaker_updated(self):
        if self.speaker_updated_callback:
            try:
                self.speaker_updated_callback()
            except Exception:
                pass

    def reset(self, clear_aliases: bool = True):
        """등록된 모든 화자 기억 및 실명 목록 초기화 (1번 화자부터 다시 시작)"""
        with self.lock:
            if self.extractor is not None:
                import sherpa_onnx
                self.manager = sherpa_onnx.SpeakerEmbeddingManager(self.extractor.dim)
            self._window.clear()
            self._audio_context = (None, None)
            self.speaker_profiles_data.clear()
            self.external_speakers.clear()
            self._external_id_map.clear()
            self.current_speaker_count = 0
            self.speaker_color_map.clear()
            self.last_active_speaker = None
            self.last_active_time = 0.0
            if clear_aliases:
                self.speaker_aliases.clear()
                self.alias_sources.clear()
                self.config["speaker_alias_sources"] = {}
                self.speaker_mutes.clear()
                self.config["speaker_aliases"] = {}
                self.config["speaker_mutes"] = {}
            _safe_print("[SpeakerID] [RESET] 모든 화자 기억이 초기화되었습니다. (1번부터 다시 시작)")
        self._notify_speaker_updated()

    def reset_speakers(self):
        """reset(clear_aliases=True)의 하위 호환 별칭"""
        return self.reset(clear_aliases=True)

    def remove_speaker(self, spk_raw_name: str):
        """특정 화자 설정 및 등록 정보 제거"""
        with self.lock:
            self.speaker_profiles_data.pop(spk_raw_name, None)
            self.external_speakers.discard(spk_raw_name)
            self.speaker_aliases.pop(spk_raw_name, None)
            self.alias_sources.pop(spk_raw_name, None)
            self.config["speaker_alias_sources"] = dict(self.alias_sources)
            self.speaker_mutes.pop(spk_raw_name, None)
            self.config["speaker_aliases"] = dict(self.speaker_aliases)
            self.config["speaker_mutes"] = dict(self.speaker_mutes)
        self._notify_speaker_updated()

    def _extract_speaker_number(self, name: str) -> int:
        match = re.search(r'\d+', name)
        return int(match.group()) if match else 1

