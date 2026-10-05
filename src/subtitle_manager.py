import time
import datetime
import html
import re
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Union


def format_srt_time(seconds: float) -> str:
    """초 단위 실수를 SRT 타임코드 포맷(HH:MM:SS,mmm)으로 변환"""
    seconds = max(0.0, float(seconds))
    hrs = int(seconds // 3600)
    rem = seconds % 3600
    mins = int(rem // 60)
    sec_rem = rem % 60
    secs = int(sec_rem)
    millis = int(round((sec_rem - secs) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    if secs >= 60:
        mins += 1
        secs -= 60
    if mins >= 60:
        hrs += 1
        mins -= 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def format_display_time(timestamp: float) -> str:
    """절대 유닉스 타임스탬프를 보기 쉬운 시:분:초 포맷으로 변환"""
    dt = datetime.datetime.fromtimestamp(timestamp)
    return dt.strftime("%H:%M:%S")


def clean_html_tags(text: str) -> str:
    """HTML 서식 태그(<span ...>, <b> 등) 제거 및 엔티티 언이스케이프"""
    if not text:
        return ""
    t = re.sub(r'<\s*br\s*/?\s*>', ' ', text, flags=re.IGNORECASE)
    t = re.sub(r'<[^>]+>', '', t)
    return html.unescape(t).strip()


def _format_srt_line(text: str, speaker: str = "") -> str:
    """화자 중복 표기 방지 및 정돈된 자막 한 줄 서식화"""
    if not text:
        return ""
    txt = text.strip()
    spk = (speaker or "").strip()
    if spk and not spk.lower().startswith("roi"):
        if not re.match(rf'^\[{re.escape(spk)}\]\s*', txt, flags=re.IGNORECASE) and \
           not re.match(rf'^{re.escape(spk)}\s*[:：]\s*', txt, flags=re.IGNORECASE):
            txt = f"[{spk}] {txt}"
    return txt


_SPEAKER_PREFIX = re.compile(r'^\[([A-Za-z가-힣0-9\s]{1,20})\]\s*')
_SPEAKER_COLON = re.compile(r'^([A-Za-z가-힣0-9\s]{1,20})\s*[:：]\s*')


def plain_dialogue_text(text: str, speaker: str = "") -> str:
    """실시간 대화창용: HTML과 앞쪽 화자 표기를 걷어내고 대사만 남긴다."""
    plain = html.unescape(clean_html_tags(text or ""))
    plain = re.sub(r'\s+', ' ', plain).strip()
    if speaker:
        escaped = re.escape(speaker.strip())
        plain = re.sub(rf'^\[{escaped}\]\s*', '', plain, flags=re.IGNORECASE)
        plain = re.sub(rf'^{escaped}\s*[:：]\s*', '', plain, flags=re.IGNORECASE)
    plain = _SPEAKER_PREFIX.sub('', plain)
    return plain.strip()


_TAG_PLACEHOLDER = re.compile(r'\x00T(\d+)\x00')
_HTML_TAG = re.compile(r'<[^>]+>')
_SENTENCE_SPLIT_RE = re.compile(
    r'(?<![.。\d])([.?!。？！]|(?:\.{2,}|。{2,}|…))([\"\'”’\)」』]*)(?:\s+|(?=[가-힣A-Za-z“\"\'(]))'
)
_ABBREVIATIONS = {
    'mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'sr.', 'jr.', 'vs.',
    'etc.', 'e.g.', 'i.e.', 'st.', 'u.s.', 'co.', 'ltd.', 'inc.'
}


def smart_break_sentences(text: str, linebreak: str = "<br>", max_lines: int = 2) -> str:
    """한글 및 영문 자막에서 짧은 맞장구나 단문(응., 네., Yes. 등)이 과도하게 줄바꿈되지 않도록
    의미 단위와 문장 길이를 고려하여 지능적으로 줄을 나눈다 (최대 max_lines 줄 보장).
    """
    if not text:
        return text

    # 1. HTML 서식 태그 임시 보호
    placeholders = []
    def _protect(match):
        placeholders.append(match.group(0))
        return f"\x00T{len(placeholders) - 1}\x00"

    protected = _HTML_TAG.sub(_protect, text)

    # 2. 문장 부호 뒤 분할 후보 추출 (약어 및 소수점 보호)
    splits = []
    last_idx = 0
    for m in _SENTENCE_SPLIT_RE.finditer(protected):
        token_before = protected[last_idx:m.end(1)].split()
        if token_before:
            last_token = token_before[-1].lower()
            if last_token in _ABBREVIATIONS:
                continue
            if re.fullmatch(r'(?:[a-za-z]\.)+', last_token):
                continue

        end_pos = m.end()
        piece = protected[last_idx:end_pos].strip()
        if piece:
            splits.append(piece)
        last_idx = end_pos

    remainder = protected[last_idx:].strip()
    if remainder:
        splits.append(remainder)

    def _restore(match):
        return placeholders[int(match.group(1))]

    if len(splits) <= 1:
        return _TAG_PLACEHOLDER.sub(_restore, protected)

    # 3. 스마트 라인 조립
    # 짧은 감탄사나 1~2어절 단문은 앞뒤 문장과 자연스럽게 같은 줄에 유지
    lines = []
    current_line = []

    def line_metrics(tokens):
        raw = " ".join(tokens)
        clean = re.sub(r'\x00T\d+\x00|[^\w가-힣]', '', raw)
        words = [w for w in raw.split() if not _TAG_PLACEHOLDER.fullmatch(w)]
        return len(clean), len(words)

    def is_substantial(chars, words):
        # 순수 글자 7자 이상이거나 3단어 이상이면 독립된 문장 분량으로 인정
        return chars >= 7 or words >= 3

    for seg in splits:
        if not current_line:
            current_line.append(seg)
            continue

        cur_chars, cur_words = line_metrics(current_line)
        seg_chars, seg_words = line_metrics([seg])

        can_break = (
            len(lines) + 1 < max_lines and
            is_substantial(cur_chars, cur_words) and
            is_substantial(seg_chars, seg_words)
        )

        if can_break:
            lines.append(" ".join(current_line))
            current_line = [seg]
        else:
            current_line.append(seg)

    if current_line:
        lines.append(" ".join(current_line))

    # 4. 결합 및 태그 복원
    joined = linebreak.join(lines)
    return _TAG_PLACEHOLDER.sub(_restore, joined)


def break_korean_sentences(text: str, linebreak: str = "<br>") -> str:
    """기존 호환 함수: 스마트 줄바꿈 적용"""
    return smart_break_sentences(text, linebreak=linebreak)


def break_plain_sentences(text: str, linebreak: str = "<br>", max_lines: int = 2) -> str:
    """한국어가 아닌 자막은 마침표·물음표·느낌표 뒤에서만 줄을 나눈다."""
    if not text:
        return text
    parts = [part.strip() for part in re.split(r'(?<=[.!?])\s+', text.strip()) if part.strip()]
    if len(parts) <= 1:
        return text
    if len(parts) > max_lines:
        parts = parts[: max_lines - 1] + [" ".join(parts[max_lines - 1 :])]
    return linebreak.join(parts)


def break_subtitle_text(text: str, target_lang: str = "ko", linebreak: str = "<br>") -> str:
    """도착 언어가 한국어일 때만 한국어 줄바꿈을 쓴다."""
    code = str(target_lang or "ko").strip().lower().split("-")[0]
    if code == "ko":
        return break_korean_sentences(text, linebreak=linebreak)
    return break_plain_sentences(text, linebreak=linebreak)


def subtitle_export_filename(
    filter_mode: str,
    extension: str,
    source_lang: str = "en",
    target_lang: str = "ko",
    product: str = "kr",
) -> str:
    """내보내기 기본 파일명. 한국어 제품은 english_/korean_ 이름을 유지한다."""
    ext = extension.lstrip(".").lower() or "srt"
    kind = "transcript" if ext == "txt" else "subtitles"
    if filter_mode == "orig_only":
        if product != "global":
            stem = "english_transcript" if ext == "txt" else "english_subtitles"
        else:
            code = _export_lang_code(source_lang, "source")
            stem = f"{code}_{kind}"
    elif filter_mode == "trans_only":
        if product != "global":
            stem = "korean_transcript" if ext == "txt" else "korean_subtitles"
        else:
            code = _export_lang_code(target_lang, "target")
            stem = f"{code}_{kind}"
    elif filter_mode == "dub_only":
        stem = "dubbing_transcript" if ext == "txt" else "dubbing_speech_only"
    elif filter_mode in ("all", "audio", "screen", "dubbing"):
        prefix = "subtitles_all" if filter_mode == "all" else f"{filter_mode}_subtitles"
        if ext == "txt" and filter_mode == "dubbing":
            stem = "dubbing_subtitles"
        elif ext == "txt" and filter_mode == "all":
            stem = "subtitles_all"
        else:
            stem = prefix
    else:
        stem = "subtitles"
    return f"{stem}.{ext}"


def _export_lang_code(code: str, fallback: str) -> str:
    raw = str(code or "").strip().lower().split("-")[0]
    if not raw or raw in ("auto", "none"):
        return fallback
    cleaned = re.sub(r"[^a-z0-9]", "", raw)
    return cleaned or fallback


break_sentences = smart_break_sentences


def dialogue_speaker_name(speaker: str, orig_text: str = "", trans_text: str = "") -> str:
    """ROI 번호가 아니라 실제 화자명만 반환한다."""
    name = (speaker or "").strip()
    if name.lower().startswith("roi"):
        name = ""
    if name:
        return name
    for raw in (orig_text, trans_text):
        plain = html.unescape(clean_html_tags(raw or ""))
        matched = _SPEAKER_PREFIX.match(plain) or _SPEAKER_COLON.match(plain)
        if matched:
            return matched.group(1).strip()
    return ""


@dataclass
class SubtitleEntry:
    id: int
    timestamp: float                       # 발화 시각 절대 timestamp (time.time())
    start_sec: float                       # 세션 시작 기준 상대 시작 초
    end_sec: float                         # 세션 시작 기준 상대 종료 초
    source: str                            # 'audio', 'screen', 'dubbing'
    speaker: str = ""                      # 화자 표시명 (예: '화자 1', 'Alex')
    speaker_color: str = "#00E5FF"         # 화자 고유 컬러
    orig_text: str = ""                    # ① STT 영문 원문 (또는 화면 OCR)
    trans_text: str = ""                   # ② 한국어 번역문
    dub_text: str = ""                     # ③ AI 음성 더빙문
    engine: str = ""                       # STT+번역 엔진 명 (예: 'GPU + DeepL')
    region_idx: int = 0                    # 화면 번역의 경우 관심 영역 인덱스 (1, 2...)
    voice: str = ""                        # 더빙인 경우 사용된 보이스 (선희, 인준 등)
    speed: str = "+0%"                     # 더빙 배속
    dub_status: str = "none"               # 'none', 'waiting', 'done'

    @property
    def clean_orig(self) -> str:
        return clean_html_tags(self.orig_text)

    @property
    def clean_trans(self) -> str:
        return clean_html_tags(self.trans_text)

    @property
    def clean_dub(self) -> str:
        return clean_html_tags(self.dub_text)


def recent_screen_dialogues(entries: List[SubtitleEntry], limit: int = 2) -> list[tuple[str, str, str]]:
    """화면 번역 탭에 표시할 최근 OCR 대화만 원문/번역 쌍으로 반환한다."""
    rows = []
    for entry in entries:
        if entry.source != "screen":
            continue
        speaker = dialogue_speaker_name(entry.speaker, entry.orig_text, entry.trans_text)
        original = plain_dialogue_text(entry.orig_text, speaker)
        translated = plain_dialogue_text(entry.trans_text, speaker)
        if original or translated:
            rows.append((speaker, original, translated))
    return rows[-max(0, limit):] if limit > 0 else []


class SubtitleHistoryManager:
    """
    실시간 음성 번역(STT 원문 + 한글 번역), 화면 번역(OCR 영문 + 한글 번역), AI 음성 더빙 대사를
    통합 기록하고 SRT 자막 및 TXT 텍스트로 내보내는 스레드 안전 매니저.
    """
    def __init__(self):
        self.entries: List[SubtitleEntry] = []
        self.lock = threading.Lock()
        self.session_start_time = time.time()
        self._next_id = 1

    def reset_session_timer(self):
        """세션 상대 타임코드 기준점 초기화"""
        with self.lock:
            self.session_start_time = time.time()

    def add_entry(self, source: str, trans_text: str, orig_text: str = "",
                  speaker: str = "", speaker_color: str = "#00E5FF",
                  engine: str = "", region_idx: int = 0, voice: str = "", speed: str = "+0%",
                  dub_text: str = "", dub_status: str = "none") -> SubtitleEntry:
        """
        신규 자막 항목 추가 (스레드 안전)
        """
        now = time.time()
        with self.lock:
            # 첫 번째 자막 진입 시 세션 시작 시간을 첫 자막 시각으로 자연스럽게 보정
            if not self.entries:
                self.session_start_time = now

            rel_start = max(0.0, now - self.session_start_time)
            
            # 대사 길이에 기반한 자연스러운 자막 표시 시간 산출 (최소 2.0초 ~ 최대 7.0초)
            char_len = max(len(clean_html_tags(trans_text)), len(clean_html_tags(orig_text)))
            duration = max(2.2, min(7.0, char_len * 0.14 + 1.2))
            rel_end = rel_start + duration

            # 이전 자막의 종료 시간이 현재 자막 시작 시간을 넘어가면 겹치지 않게 매끄럽게 조정
            if self.entries:
                prev = self.entries[-1]
                if prev.end_sec > rel_start:
                    prev.end_sec = max(prev.start_sec + 0.5, rel_start - 0.05)

            # 화자명 자동 추출 보정
            clean_s = speaker
            if not clean_s:
                m = re.match(r'^(?:<[^>]+>)*\s*\[([A-Za-z가-힣0-9\s]{1,20})\]', trans_text) or re.match(r'^(?:<[^>]+>)*\s*\[([A-Za-z가-힣0-9\s]{1,20})\]', orig_text)
                if m:
                    clean_s = m.group(1).strip()
                else:
                    m2 = re.match(r'^([A-Za-z가-힣0-9\s]{1,20}):', trans_text) or re.match(r'^([A-Za-z가-힣0-9\s]{1,20}):', orig_text)
                    if m2:
                        clean_s = m2.group(1).strip()

            entry = SubtitleEntry(
                id=self._next_id,
                timestamp=now,
                start_sec=rel_start,
                end_sec=rel_end,
                source=source,
                speaker=clean_s,
                speaker_color=speaker_color,
                orig_text=orig_text.strip(),
                trans_text=trans_text.strip(),
                dub_text=dub_text.strip(),
                engine=engine.strip(),
                region_idx=region_idx,
                voice=voice.strip(),
                speed=speed,
                dub_status=dub_status
            )
            self._next_id += 1
            self.entries.append(entry)
            return entry

    def update_or_add_dubbing(self, dub_text: str, speaker: str = "", orig_text: str = "",
                              voice: str = "", speed: str = "+0%", region_idx: int = 0,
                              source: str = "dubbing", **kwargs) -> SubtitleEntry:
        """
        더빙 음성 발화 시 기존 번역 항목을 찾아 3섹션 더빙 대사 및 상태(done) 실시간 갱신.
        (매칭되는 항목이 없으면 신규 더빙 항목으로 등록)
        """
        clean_d = clean_html_tags(dub_text)
        clean_o = clean_html_tags(orig_text)
        matched_entries = []

        def _compact(s: str) -> str:
            return re.sub(r'[\W_]+', '', s).lower()

        c_dub = _compact(clean_d)
        c_orig = _compact(clean_o)

        with self.lock:
            recent_candidates = self.entries[-40:]
            # 1차: 아직 더빙 완료되지 않고 대기 중인 항목(waiting) 우선 탐색
            waiting_candidates = [e for e in recent_candidates if e.dub_status == "waiting"]
            search_pool = waiting_candidates if waiting_candidates else recent_candidates

            for entry in reversed(search_pool):
                e_orig = _compact(entry.clean_orig)
                e_trans = _compact(entry.clean_trans)

                # 1. 영문 원문 일치 또는 번역문 포함 검사
                matched = False
                if c_orig and e_orig and (c_orig in e_orig or e_orig in c_orig):
                    matched = True
                elif c_dub and e_trans and (e_trans in c_dub or c_dub in e_trans):
                    matched = True

                if matched:
                    matched_entries.append(entry)

            # 만약 텍스트 정규화 불일치로 매칭되지 않았더라도, 대기 중인 항목이 있다면 가장 오래된 대기 항목에 자동 매칭 (영구 ⏳ 대기 방지)
            if not matched_entries and waiting_candidates:
                matched_entries.append(waiting_candidates[0])

            if matched_entries:
                chronological = list(reversed(matched_entries))
                if len(chronological) == 1:
                    entry = chronological[0]
                    entry.dub_text = clean_d
                    entry.voice = voice or entry.voice
                    entry.speed = speed or entry.speed
                    entry.dub_status = "done"
                    if speaker and not entry.speaker:
                        entry.speaker = speaker
                else:
                    # 다중 문장이 하나의 발화로 결합(Coalesced)된 경우:
                    # 각 행에 합체 대사 전체를 중복 표시하지 않고, 각 행 고유의 대사로 분배하여 중복 표시 방지
                    for entry in chronological:
                        clean_part = re.sub(r'\[.*?\]', '', entry.clean_trans).strip()
                        clean_part = re.sub(r'^[A-Za-z가-힣0-9\s]{1,15}[:：\-]\s*', '', clean_part).strip()
                        entry.dub_text = clean_part if clean_part else clean_d
                        entry.voice = voice or entry.voice
                        entry.speed = speed or entry.speed
                        entry.dub_status = "done"
                        if speaker and not entry.speaker:
                            entry.speaker = speaker
                return chronological[0]

        # 매칭되는 이전 STT 항목이 없으면 신규 더빙 항목 생성
        return self.add_entry(
            source="dubbing",
            trans_text=dub_text,
            orig_text=orig_text,
            speaker=speaker,
            voice=voice,
            speed=speed,
            dub_text=dub_text,
            dub_status="done",
            region_idx=region_idx
        )

    def get_entries(self, source_filter: Optional[str] = None, keyword: str = "") -> List[SubtitleEntry]:
        """필터 조건에 맞는 자막 항목 반환"""
        with self.lock:
            result = list(self.entries)

        if source_filter and source_filter != "all":
            if source_filter == "audio":
                result = [e for e in result if e.source == "audio"]
            elif source_filter == "screen":
                result = [e for e in result if e.source == "screen"]
            elif source_filter == "dubbing":
                # AI 음성 더빙 관련 항목 (더빙 대사가 있거나 더빙 완료/대기 상태인 항목)
                result = [e for e in result if bool(e.clean_dub or e.dub_status in ("waiting", "done") or e.source == "dubbing")]
            elif source_filter == "orig_only":
                # 영어 원문만
                result = [e for e in result if bool(e.clean_orig)]
            elif source_filter == "trans_only":
                # 한국어 번역문만
                result = [e for e in result if bool(e.clean_trans)]
            elif source_filter == "dub_only":
                # 더빙 발화문만 (실제 발화 대사가 존재하는 항목)
                result = [e for e in result if bool(e.clean_dub or (e.source == "dubbing" and e.clean_trans))]
            else:
                result = [e for e in result if e.source == source_filter]

        if keyword:
            kw = keyword.lower().strip()
            result = [
                e for e in result
                if kw in e.clean_trans.lower() or kw in e.clean_orig.lower() or kw in e.clean_dub.lower() or kw in e.speaker.lower()
            ]

        return result

    def clear(self):
        """누적된 모든 자막 기록 초기화"""
        with self.lock:
            self.entries.clear()
            self._next_id = 1
            self.session_start_time = time.time()

    def count(self) -> int:
        with self.lock:
            return len(self.entries)

    def export_to_srt(self, filepath: Optional[str] = None, include_original: bool = True,
                      source_filter: Optional[str] = None, keyword: Optional[str] = None) -> Union[bool, str]:
        """
        표준 SubRip (.srt) 파일로 저장 (UTF-8 with BOM 인코딩으로 윈도우/팟플레이어/VLC 한글 완벽 호환)
        filepath가 지정되지 않으면 문자열 형태로 반환
        선택된 필터 범위(원문/번역문/더빙문/오디오/화면 등) 및 키워드에 맞춰 타겟 자막 대사만 정밀 출력
        """
        entries = self.get_entries(source_filter=source_filter, keyword=keyword)
        if not entries:
            if filepath:
                with open(filepath, "w", encoding="utf-8-sig") as f:
                    f.write("")
                return True
            return ""

        blocks = []
        seq_idx = 1
        for e in entries:
            s_time = format_srt_time(e.start_sec)
            e_time = format_srt_time(e.end_sec)
            spk = e.speaker
            lines = []

            if source_filter == "orig_only":
                if e.clean_orig:
                    lines.append(_format_srt_line(e.clean_orig, spk))
            elif source_filter == "trans_only":
                if e.clean_trans:
                    lines.append(_format_srt_line(e.clean_trans, spk))
            elif source_filter in ("dub_only", "dubbing"):
                dub_txt = e.clean_dub or (e.clean_trans if e.source == "dubbing" else "")
                if dub_txt:
                    lines.append(_format_srt_line(dub_txt, spk))
            else:
                # 전체(all), 오디오(audio), 화면(screen) 등
                # 주 자막: 한국어 번역문 (또는 더빙문)
                primary_txt = e.clean_trans or e.clean_dub
                if primary_txt:
                    lines.append(_format_srt_line(primary_txt, spk))

                # 보조 자막: 영문 원문 (옵션)
                if include_original and e.clean_orig:
                    if not lines:
                        lines.append(_format_srt_line(e.clean_orig, spk))
                    else:
                        # 이미 주 자막에 화자가 표기되었으면 원문에는 화자 없이 본문만 추가
                        orig_text = e.clean_orig
                        if spk and re.match(rf'^\[{re.escape(spk)}\]\s*', orig_text, flags=re.IGNORECASE):
                            orig_text = re.sub(rf'^\[{re.escape(spk)}\]\s*', '', orig_text, flags=re.IGNORECASE)
                        lines.append(orig_text)

            if not lines:
                continue

            block = f"{seq_idx}\n{s_time} --> {e_time}\n" + "\n".join(lines) + "\n"
            blocks.append(block)
            seq_idx += 1

        content = "\n".join(blocks)
        if not filepath:
            return content
        try:
            with open(filepath, "w", encoding="utf-8-sig") as f:
                f.write(content)
            return True
        except Exception as err:
            print(f"[SubtitleHistory] SRT 파일 저장 실패: {err}")
            return False

    def export_to_txt(self, filepath: Optional[str] = None, include_timestamps: bool = True,
                      source_filter: Optional[str] = None, keyword: Optional[str] = None) -> Union[bool, str]:
        """
        가독성 높은 텍스트(.txt) 대본 형식으로 저장
        filepath가 지정되지 않으면 문자열 형태로 반환
        선택된 필터 및 키워드에 맞춤 서식 적용 (영문 원문만, 번역문만, 더빙문만, 또는 3단 비교)
        """
        entries = self.get_entries(source_filter=source_filter, keyword=keyword)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        src_desc = {
            "all": "전체 보기 (3단 비교)",
            "audio": "음성 번역 (원문+번역+더빙)",
            "screen": "화면 번역 (원문+번역+더빙)",
            "dubbing": "AI 음성 더빙 완료 항목",
            "orig_only": "🔤 원문만 (STT / OCR)",
            "trans_only": "🌐 번역문만",
            "dub_only": "🎙️ AI 더빙 발화문만"
        }.get(source_filter or "all", "전체")

        kw_desc = f" (검색어: '{keyword}')" if keyword else ""
        lines = [
            "=" * 64,
            f"📝 실시간 AI 통역 및 번역 대본 기록 ({now_str})",
            f"필터 범위: {src_desc}{kw_desc} | 총 대사 수: {len(entries)}개",
            "=" * 64,
            ""
        ]

        source_labels = {
            "audio": "오디오",
            "screen": "화면",
            "dubbing": "더빙"
        }

        for e in entries:
            src_lbl = source_labels.get(e.source, e.source.upper())
            if e.region_idx > 0 and e.source == "screen":
                src_lbl += f" (영역 {e.region_idx})"

            spk_info = f"[{e.speaker}] " if e.speaker and not e.speaker.lower().startswith("roi") else ""
            eng_info = f" | {e.engine}" if e.engine else ""
            t_str = f"[{format_display_time(e.timestamp)}]" if include_timestamps else ""

            if source_filter == "orig_only":
                if e.clean_orig:
                    orig_disp = e.clean_orig
                    if e.speaker and orig_disp.startswith(f"[{e.speaker}]"):
                        orig_disp = orig_disp[len(f"[{e.speaker}]"):].strip()
                    prefix = f"{t_str} [{src_lbl}{eng_info}] {spk_info}".strip()
                    lines.append(f"{prefix} {orig_disp}".strip())
            elif source_filter == "trans_only":
                if e.clean_trans:
                    trans_disp = e.clean_trans
                    if e.speaker and trans_disp.startswith(f"[{e.speaker}]"):
                        trans_disp = trans_disp[len(f"[{e.speaker}]"):].strip()
                    prefix = f"{t_str} [{src_lbl}{eng_info}] {spk_info}".strip()
                    lines.append(f"{prefix} {trans_disp}".strip())
            elif source_filter in ("dub_only", "dubbing"):
                dub_txt = e.clean_dub or (e.clean_trans if e.source == "dubbing" else "")
                if dub_txt:
                    if e.speaker and dub_txt.startswith(f"[{e.speaker}]"):
                        dub_txt = dub_txt[len(f"[{e.speaker}]"):].strip()
                    voice_str = f"[{e.voice} {e.speed}] " if e.voice else ""
                    prefix = f"{t_str} [{src_lbl}] {voice_str}{spk_info}".strip()
                    lines.append(f"{prefix} {dub_txt}".strip())
            else:
                # all, audio, screen
                if include_timestamps:
                    time_header = f"[{format_display_time(e.timestamp)} / +{int(e.start_sec)}s]"
                    lines.append(f"{time_header} [{src_lbl}{spk_info}{eng_info}]")
                else:
                    lines.append(f"[{src_lbl}{spk_info}{eng_info}]")

                if e.clean_orig:
                    lines.append(f"  [원문]    {e.clean_orig}")
                if e.clean_trans:
                    lines.append(f"  [번역]    {e.clean_trans}")
                if e.clean_dub:
                    voice_str = f"[{e.voice} {e.speed}] " if e.voice else ""
                    lines.append(f"  [AI 더빙 발화] {voice_str}{e.clean_dub}")
                elif e.source == "dubbing":
                    voice_str = f"[{e.voice} {e.speed}] " if e.voice else ""
                    lines.append(f"  [AI 더빙 발화] {voice_str}{e.clean_trans}")
                lines.append("")

        content = "\n".join(lines).strip()
        if not filepath:
            return content
        try:
            with open(filepath, "w", encoding="utf-8-sig") as f:
                f.write(content)
            return True
        except Exception as err:
            print(f"[SubtitleHistory] TXT 파일 저장 실패: {err}")
            return False


    @classmethod
    def format_html_table(cls, entries: List[SubtitleEntry], filter_mode: str = "all") -> str:
        """3개 섹션(① STT 영어 원문 | ② 한국어 번역문 | ③ AI 음성 더빙문) 가로 비교 또는 선택형 단독 뷰 렌더링"""
        if not entries:
            msg = "대화 또는 화면 텍스트가 유입되면 실시간 자막이 여기에 기록됩니다."
            if filter_mode and filter_mode != "all":
                msg = "현재 필터 조건에 일치하는 자막 항목이 없습니다."
            return f"<div style='color: #78909C; font-size: 12px; text-align: center; padding: 30px;'>{msg}</div>"

        # 1. 영문 원문만 단독 보기 모드
        if filter_mode == "orig_only":
            rows = []
            for idx, e in enumerate(entries):
                bg_col = "#0D131A" if idx % 2 == 0 else "#111822"
                time_tag = format_display_time(e.timestamp)
                spk_badge = ""
                if e.speaker:
                    col = e.speaker_color or "#00E5FF"
                    spk_badge = f"<span style='color: {col}; font-weight: bold; margin-left: 6px;'>[{e.speaker}]</span>"
                src_tag = "🖥️ 화면" if e.source == "screen" else "🎙️ 오디오"
                reg_tag = f" (영역 {e.region_idx})" if e.region_idx else ""
                
                rows.append(f"""
                <tr style='background-color: {bg_col};'>
                    <td style='vertical-align: top; padding: 9px 12px; border-bottom: 1px solid #1E2933;'>
                        <div style='color: #78909C; font-size: 10px; margin-bottom: 4px; font-family: Consolas, monospace;'>
                            [{time_tag}] <span style='color: #90A4AE;'>{src_tag}{reg_tag}</span>{spk_badge}
                        </div>
                        <div style='color: #80DEEA; font-size: 13px; line-height: 1.5;'>
                            {e.clean_orig if e.clean_orig else '<span style=\"color: #546E7A;\">-</span>'}
                        </div>
                    </td>
                </tr>
                """)
            return f"""
            <table width='100%' cellpadding='0' cellspacing='0' style='border-collapse: collapse; font-family: \"Segoe UI\", \"Malgun Gothic\", sans-serif;'>
                <thead>
                    <tr style='background-color: #121A22; border-bottom: 2px solid #00ACC1;'>
                        <th style='color: #00E5FF; font-size: 11px; font-weight: bold; text-align: left; padding: 7px 12px;'>
                            ① STT / OCR 원문
                        </th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
            """

        # 2. 한국어 번역문만 단독 보기 모드
        if filter_mode == "trans_only":
            rows = []
            for idx, e in enumerate(entries):
                bg_col = "#0D131A" if idx % 2 == 0 else "#111822"
                time_tag = format_display_time(e.timestamp)
                spk_badge = ""
                if e.speaker:
                    col = e.speaker_color or "#00E5FF"
                    spk_badge = f"<span style='color: {col}; font-weight: bold; margin-left: 6px;'>[{e.speaker}]</span>"
                src_tag = "🖥️ 화면" if e.source == "screen" else "🎙️ 오디오"
                eng_tag = f"<span style='color: #78909C; font-size: 10px; margin-left: 6px;'>[{e.engine}]</span>" if e.engine else ""
                
                rows.append(f"""
                <tr style='background-color: {bg_col};'>
                    <td style='vertical-align: top; padding: 9px 12px; border-bottom: 1px solid #1E2933;'>
                        <div style='color: #78909C; font-size: 10px; margin-bottom: 4px; font-family: Consolas, monospace;'>
                            [{time_tag}] <span style='color: #90A4AE;'>{src_tag}</span>{spk_badge}{eng_tag}
                        </div>
                        <div style='color: #FFFFFF; font-size: 13px; font-weight: bold; line-height: 1.5;'>
                            {e.clean_trans if e.clean_trans else '<span style=\"color: #546E7A;\">-</span>'}
                        </div>
                    </td>
                </tr>
                """)
            return f"""
            <table width='100%' cellpadding='0' cellspacing='0' style='border-collapse: collapse; font-family: \"Segoe UI\", \"Malgun Gothic\", sans-serif;'>
                <thead>
                    <tr style='background-color: #121A22; border-bottom: 2px solid #00E676;'>
                        <th style='color: #00E676; font-size: 11px; font-weight: bold; text-align: left; padding: 7px 12px;'>
                            ② 번역문
                        </th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
            """

        # 3. AI 음성 더빙문만 단독 보기 모드
        if filter_mode == "dub_only":
            rows = []
            for idx, e in enumerate(entries):
                bg_col = "#0D131A" if idx % 2 == 0 else "#111822"
                time_tag = format_display_time(e.timestamp)
                spk_badge = ""
                if e.speaker:
                    col = e.speaker_color or "#00E5FF"
                    spk_badge = f"<span style='color: {col}; font-weight: bold; margin-left: 6px;'>[{e.speaker}]</span>"
                voice_short = e.voice.split('-')[2] if '-' in e.voice else (e.voice or "성우")
                voice_badge = f"<span style='background-color: #6A1B9A; color: #FFFFFF; font-size: 10px; font-weight: bold; padding: 1px 5px; border-radius: 3px; margin-left: 6px;'>{voice_short} {e.speed}</span>"
                
                dub_txt = e.clean_dub or (e.clean_trans if e.source == "dubbing" else "")
                rows.append(f"""
                <tr style='background-color: {bg_col};'>
                    <td style='vertical-align: top; padding: 9px 12px; border-bottom: 1px solid #1E2933;'>
                        <div style='color: #78909C; font-size: 10px; margin-bottom: 4px; font-family: Consolas, monospace;'>
                            [{time_tag}]{spk_badge}{voice_badge}
                        </div>
                        <div style='color: #E1BEE7; font-size: 13px; font-weight: bold; line-height: 1.5;'>
                            🗣️ {dub_txt if dub_txt else '<span style=\"color: #546E7A;\">-</span>'}
                        </div>
                    </td>
                </tr>
                """)
            return f"""
            <table width='100%' cellpadding='0' cellspacing='0' style='border-collapse: collapse; font-family: \"Segoe UI\", \"Malgun Gothic\", sans-serif;'>
                <thead>
                    <tr style='background-color: #121A22; border-bottom: 2px solid #BA68C8;'>
                        <th style='color: #BA68C8; font-size: 11px; font-weight: bold; text-align: left; padding: 7px 12px;'>
                            ③ AI 음성 더빙 발화문
                        </th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
            """

        # 4. 전체 보기 모드 (시간 | 소스 | 영어 원문 | 한국어 번역 | 실제 더빙 5단 그리드 테이블)
        rows = []
        for idx, e in enumerate(entries):
            rows.append(cls.format_html_row(e, is_even=(idx % 2 == 0)))

        return f"""
        <table width='100%' cellpadding='8' cellspacing='0' style='border-collapse: collapse; font-family: \"Malgun Gothic\", \"맑은 고딕\", \"Segoe UI\", sans-serif;'>
            <thead>
                <tr style='background-color: #101726; border-bottom: 2px solid #1E2A42;'>
                    <th width='12%' style='color: #94A3B8; font-size: 11px; font-weight: bold; text-align: left; padding: 9px 12px;'>시간</th>
                    <th width='15%' style='color: #94A3B8; font-size: 11px; font-weight: bold; text-align: left; padding: 9px 12px;'>소스</th>
                    <th width='28%' style='color: #94A3B8; font-size: 11px; font-weight: bold; text-align: left; padding: 9px 12px;'>원문</th>
                    <th width='25%' style='color: #94A3B8; font-size: 11px; font-weight: bold; text-align: left; padding: 9px 12px;'>번역</th>
                    <th width='20%' style='color: #94A3B8; font-size: 11px; font-weight: bold; text-align: left; padding: 9px 12px;'>실제 더빙</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        """

    @classmethod
    def format_html_row(cls, e: SubtitleEntry, is_even: bool = True) -> str:
        """컨셉 03-transcripts.png와 100% 일치하는 5열 행(tr) 렌더링"""
        bg_col = "#0D1322" if is_even else "#11182A"
        time_tag = format_display_time(e.timestamp)

        # 소스 배지 스타일링
        if e.source == "audio":
            src_badge = "<span style='background-color: rgba(99,102,241,0.25); color: #818CF8; font-size: 10px; font-weight: bold; padding: 3px 8px; border-radius: 4px;'>● 오디오</span>"
            sub_lbl = e.speaker or "화자"
        elif e.source == "screen":
            src_badge = "<span style='background-color: rgba(16,185,129,0.25); color: #34D399; font-size: 10px; font-weight: bold; padding: 3px 8px; border-radius: 4px;'>● 화면</span>"
            sub_lbl = e.speaker or f"영역 {e.region_idx+1}"
        else:
            src_badge = "<span style='background-color: rgba(236,72,153,0.25); color: #F472B6; font-size: 10px; font-weight: bold; padding: 3px 8px; border-radius: 4px;'>● 더빙</span>"
            sub_lbl = e.voice.split('-')[2] if '-' in e.voice else (e.speaker or "내레이션")

        # 실제 더빙 텍스트
        dub_txt = e.clean_dub or (e.clean_trans if e.source == "dubbing" else "")
        if dub_txt:
            dub_col = f"<span style='color: #EC4899; margin-right: 4px;'>●</span> <span style='color: #F8FAFC;'>{dub_txt}</span>"
        else:
            dub_col = "<span style='color: #475569;'>-</span>"

        return f"""
        <tr style='background-color: {bg_col}; border-bottom: 1px solid #1A2438;'>
            <td style='vertical-align: middle; padding: 10px 12px; color: #64748B; font-size: 11px; font-family: Consolas, monospace;'>
                {time_tag}
            </td>
            <td style='vertical-align: middle; padding: 10px 12px;'>
                <div>{src_badge}</div>
                <div style='color: #94A3B8; font-size: 10px; margin-top: 3px; font-weight: 500;'>{sub_lbl}</div>
            </td>
            <td style='vertical-align: middle; padding: 10px 12px; color: #F1F5F9; font-size: 12px;'>
                {e.clean_orig if e.clean_orig else '<span style=\"color: #475569;\">-</span>'}
            </td>
            <td style='vertical-align: middle; padding: 10px 12px; color: #F8FAFC; font-size: 12px; font-weight: 600;'>
                {e.clean_trans if e.clean_trans else '<span style=\"color: #475569;\">-</span>'}
            </td>
            <td style='vertical-align: middle; padding: 10px 12px; font-size: 12px;'>
                {dub_col}
            </td>
        </tr>
        """

    @classmethod
    def format_html_entry(cls, e: SubtitleEntry) -> str:
        """단일 카드 뷰 또는 개별 행 호환 렌더링"""
        return cls.format_html_row(e, is_even=True)
