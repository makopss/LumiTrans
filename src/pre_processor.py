# -*- coding: utf-8 -*-
"""
pre_processor.py - 도메인 사전 분석, Whisper 힌트 주입 및 STT/LLM 음운·용어 사전 교정 엔진
LumiTrans 프로젝트용 고정밀 실시간 자막 전처리 모듈
"""

from dataclasses import dataclass, field
import json
import os
import re
from typing import Dict, Optional
import requests


@dataclass
class PreProcessingContext:
    """도메인 사전 및 STT/번역 교정 메타데이터 컨테이너"""
    initial_prompt_tokens: str = ""                # Whisper STT 인식 유도 힌트 (고유명사 목록)
    phonetic_fix_map: Dict[str, str] = field(default_factory=dict)  # STT 음운 오인식 -> 올바른 단어 맵
    glossary: Dict[str, str] = field(default_factory=dict)          # 번역 용어집 (원문 영어 -> 공식 한국어 번역)
    tone_and_style: str = ""                       # 화자 발화 어조 및 자막 스타일
    source_summary: str = ""                       # 영상 핵심 주제 요약

    def is_empty(self) -> bool:
        return not bool(self.initial_prompt_tokens or self.phonetic_fix_map or self.glossary)

    def apply_phonetic_fixes(self, text: str) -> str:
        """
        영상별 phonetic_fix_map만 적용합니다. 전역 고유명사/대사 치환은 두지 않습니다.
        영문 토큰은 단어 경계(\\b)로 매칭해 부분 일치 왜곡을 막습니다.
        (예: 'part' -> 'Pod' 규칙이 있어도 'participate'는 그대로 둡니다)
        """
        if not text or not self.phonetic_fix_map:
            return text or ""

        result = text
        for wrong, correct in self.phonetic_fix_map.items():
            if not wrong or not correct or wrong.strip().lower() == correct.strip().lower():
                continue

            # 영문 알파벳/숫자로 구성된 단어는 단어 경계(\\b)를 적용하여 오치환(부분 일치) 방지
            # 예: 'part' -> 'Pod' 치환 시 'participate'가 'Podicipate'로 왜곡되는 현상 차단
            if re.fullmatch(r"[a-zA-Z0-9_\- ']+", wrong):
                pattern = r"\b" + re.escape(wrong.strip()) + r"\b"
                result = re.sub(pattern, correct.strip(), result, flags=re.IGNORECASE)
            else:
                # 한글 또는 기호 혼합 시 단순 치환
                result = result.replace(wrong, correct)

        return result

    # --- 각 LLM 아키텍처별 맞춤형 프롬프트 생성기 및 가드레일 ---

    def _filter_glossary_for_text(self, text: Optional[str]) -> Dict[str, str]:
        """주어진 텍스트에 실제로 존재하는 도메인 용어만 선별하여 추출 (단어 경계 매칭)"""
        if not text or not self.glossary:
            return {}
        matched = {}
        for term, trans in self.glossary.items():
            if not term:
                continue
            if re.fullmatch(r"[a-zA-Z0-9_\- ']+", term):
                pattern = r"\b" + re.escape(term.strip()) + r"\b"
                if re.search(pattern, text, flags=re.IGNORECASE):
                    matched[term] = trans
            else:
                if term.lower() in text.lower():
                    matched[term] = trans
        return matched

    def _should_suppress_summary_and_style(self, target_text: Optional[str]) -> bool:
        """3단어 이하의 초단편 텍스트인 경우 LLM의 문맥 누수/환각 방지를 위해 배경 요약 억제"""
        if not target_text:
            return False
        words = target_text.strip().split()
        return len(words) <= 3

    def format_for_translategemma(self, target_text: Optional[str] = None, source_lang: str = "en", target_lang: str = "ko") -> str:
        """TranslateGemma 4B용: 단일 User 턴 내 영문 지시 블록"""
        glossary_items = self._filter_glossary_for_text(target_text) if target_text is not None else self.glossary
        if not glossary_items:
            return ""
        lines = ["[Glossary & Terminology Guide - Strictly follow these translations]:"]
        for term, trans in list(glossary_items.items())[:30]:
            lines.append(f"- {term} -> {trans}")
        return "\n".join(lines)

    def format_for_exaone(self, target_text: Optional[str] = None, source_lang: str = "en", target_lang: str = "ko") -> str:
        """EXAONE 3.5용: System 역할 내 Markdown 테이블 형식"""
        blocks = []
        suppress_ctx = self._should_suppress_summary_and_style(target_text)
        is_tgt_ko = str(target_lang or "ko").strip().lower() == "ko"
        ctx_label = "[핵심 맥락]" if is_tgt_ko else "[Context]"
        style_label = "[자막 스타일]" if is_tgt_ko else "[Style]"
        if self.source_summary and not suppress_ctx:
            blocks.append(f"{ctx_label}: {self.source_summary}")
        if self.tone_and_style and not suppress_ctx:
            blocks.append(f"{style_label}: {self.tone_and_style}")
        glossary_items = self._filter_glossary_for_text(target_text) if target_text is not None else self.glossary
        if glossary_items:
            if str(source_lang or "").strip().lower() in ("auto", "none", ""):
                src_name = "원문" if is_tgt_ko else "Source"
            elif source_lang.lower() == "en":
                src_name = "영어" if is_tgt_ko else "English"
            else:
                src_name = source_lang.upper()
            tgt_name = "한국어" if is_tgt_ko else target_lang.upper()
            glossary_title = "[필수 준수 용어집 (Glossary)]:" if is_tgt_ko else "[Mandatory Domain Glossary]:"
            term_header = f"원문 용어 ({src_name})" if is_tgt_ko else f"Source Term ({src_name})"
            trans_header = f"공식 {tgt_name} 번역" if is_tgt_ko else f"Official {tgt_name} Translation"
            table = [
                glossary_title,
                f"| {term_header} | {trans_header} |",
                "|---|---|",
            ]
            for term, trans in list(glossary_items.items())[:35]:
                t_clean = str(term).replace("|", r"\|")
                tr_clean = str(trans).replace("|", r"\|")
                table.append(f"| {t_clean} | {tr_clean} |")
            blocks.append("\n".join(table))
        return "\n\n".join(blocks)

    def format_for_hymt(self, target_text: Optional[str] = None, source_lang: str = "en", target_lang: str = "ko") -> str:
        """Tencent Hy-MT2용: 공식 Reference Translation(참고 번역) 개입 형식"""
        blocks = []
        if self.source_summary and target_text is None:
            blocks.append(f"[Context]: {self.source_summary}")
        glossary_items = self._filter_glossary_for_text(target_text) if target_text is not None else self.glossary
        if glossary_items:
            lines = ["Reference the following translations:"]
            for term, trans in list(glossary_items.items())[:20]:
                lines.append(f"{term} translates to {trans}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def format_for_groq(self, target_text: Optional[str] = None, source_lang: str = "en", target_lang: str = "ko") -> str:
        """Groq (Qwen / Llama)용: 시스템 프롬프트 주입용 표준 용어집 형식"""
        blocks = []
        suppress_ctx = self._should_suppress_summary_and_style(target_text)
        if self.source_summary and not suppress_ctx:
            blocks.append(f"[Context]: {self.source_summary}")
        if self.tone_and_style and not suppress_ctx:
            blocks.append(f"[Style]: {self.tone_and_style}")
        glossary_items = self._filter_glossary_for_text(target_text) if target_text is not None else self.glossary
        if glossary_items:
            lines = ["[Mandatory Domain Glossary - Consistently follow these terms]:"]
            for term, trans in list(glossary_items.items())[:35]:
                lines.append(f"- {term} -> {trans}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def format_for_gemini(self, target_text: Optional[str] = None, source_lang: str = "en", target_lang: str = "ko") -> str:
        """Gemini용: 구조화된 가이드라인 형식 (도착 언어 감응형 헤더)"""
        blocks = []
        suppress_ctx = self._should_suppress_summary_and_style(target_text)
        is_tgt_ko = str(target_lang or "ko").strip().lower() == "ko"
        ctx_label = "[영상 배경 요약]" if is_tgt_ko else "[Video Context Summary]"
        rules_label = "[도메인 전문 용어 번역 규칙]:" if is_tgt_ko else "[Mandatory Domain Terminology Rules]:"

        if self.source_summary and not suppress_ctx:
            blocks.append(f"{ctx_label}: {self.source_summary}")
        glossary_items = self._filter_glossary_for_text(target_text) if target_text is not None else self.glossary
        if glossary_items:
            lines = [rules_label]
            for term, trans in list(glossary_items.items())[:35]:
                lines.append(f"- {term}: {trans}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def save_json(self, path: str):
        """컨텍스트 데이터를 JSON 파일로 직렬화 저장"""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, ensure_ascii=False, indent=2)

    @classmethod
    def load_json(cls, path: str) -> Optional["PreProcessingContext"]:
        """JSON 파일에서 컨텍스트 복원"""
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return cls(**data)
        except Exception as e:
            print(f"[PreProcessingContext] JSON 로드 실패 ({path}): {e}")
            return None


class GeminiPreProcessor:
    """Gemini Flash/Lite 1회 호출로 구조화된 도메인 사전 컨텍스트를 생성하는 분석기"""

    DEFAULT_MODELS = [
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-flash-latest",
    ]

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
        candidates = []
        if model and model.strip():
            candidates.append(model.strip())
        candidates.extend(self.DEFAULT_MODELS)
        # 중복 제거하되 순서 보존
        seen = set()
        self.candidate_models = [m for m in candidates if not (m in seen or seen.add(m))]
        self.model = self.candidate_models[0]

    def _call_gemini_json(self, prompt: str, system_instruction: str) -> Optional[dict]:
        if not self.api_key:
            print("[PreProcessor] Gemini API 키가 설정되지 않아 사전 생성을 건너뜁니다.")
            return None

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}

        last_error = None
        for model_name in self.candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            try:
                res = requests.post(url, json=payload, headers=headers, timeout=20.0)
                if res.status_code == 200:
                    data = res.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    # 마크다운 코드블록 정제
                    raw_text = re.sub(r"^```json\s*", "", raw_text, flags=re.IGNORECASE)
                    raw_text = re.sub(r"\s*```$", "", raw_text)
                    return json.loads(raw_text)
                else:
                    last_error = f"HTTP {res.status_code}: {res.text[:120]}"
                    # 404/429/503 등 발생 시 다음 모델로 순환
                    print(f"[PreProcessor] Gemini [{model_name}] 오류 (HTTP {res.status_code}), 다음 모델로 대체합니다.")
            except Exception as e:
                last_error = str(e)
                print(f"[PreProcessor] Gemini [{model_name}] 요청 실패: {e}, 다음 모델로 대체합니다.")

        print(f"[PreProcessor] 모든 Gemini 모델 호출 실패. 마지막 오류: {last_error}")
        return None

    def analyze_metadata(self, title: str, additional_topic: str = "", source_lang: str = "en", target_lang: str = "ko") -> PreProcessingContext:
        """영상 제목이나 키워드로부터 사전 생성 (실시간 라이브/간이 모드용, 다국어 지원)"""
        from src.translator import get_language_name
        src_code = str(source_lang or "en").strip().lower().split("-")[0]
        tgt_code = str(target_lang or "ko").strip().lower().split("-")[0]

        if tgt_code == "ko":
            src_name = get_language_name(src_code, native=True) if src_code not in ("auto", "none", "") else "원문"
            tgt_name = "한국어"
            system_instruction = (
                "당신은 영상 음성인식(STT) 및 자막 번역 파이프라인의 언어 분석 전문가입니다. "
                "주어진 영상 제목과 정보로부터 STT 오인식 방지 힌트 및 번역 모델용 용어집을 JSON으로 출력하세요."
            )
            prompt = f"""영상 정보:
제목: {title}
추가 정보: {additional_topic}

요구사항:
1. "source_summary": 영상 핵심 주제 1문장 요약
2. "tone_and_style": 원문 말투를 살린 {tgt_name} 자막 어조 (존댓말·반말·격식을 영상에 맞게)
3. "whisper_initial_prompt": Whisper STT 인식을 유도할 핵심 {src_name} 고유명사 15~25개 (쉼표 구분 단어열)
4. "phonetic_fix_map": Whisper가 발음 혼동으로 잘못 표기하기 쉬운 오인식 -> 올바른 단어 매핑 (5~15개)
5. "glossary": 번역 모델이 반드시 일관되게 따라야 할 핵심 {src_name} 용어 -> {tgt_name} 번역 매핑 (15~30개)

반드시 아래 JSON 스키마로만 출력하세요:
{{
  "source_summary": "...",
  "tone_and_style": "...",
  "whisper_initial_prompt": "term1, term2, term3",
  "phonetic_fix_map": {{"wrong_word": "CorrectWord"}},
  "glossary": {{"Term": "공식번역어"}}
}}"""
        else:
            src_name = get_language_name(src_code, native=False) if src_code not in ("auto", "none", "") else "source language"
            tgt_name = get_language_name(tgt_code, native=False)
            system_instruction = (
                "You are an expert audio-visual language engineer specialized in speech-to-text (STT) and subtitle translation pipelines. "
                "Analyze the video information and produce STT recognition hints, phonetic correction mappings, and an official translation glossary as JSON."
            )
            prompt = f"""Video Information:
Title: {title}
Additional Info: {additional_topic}

Requirements:
1. "source_summary": 1-sentence concise summary of the core video topic.
2. "tone_and_style": Natural subtitle tone and style in {tgt_name}.
3. "whisper_initial_prompt": Key proper nouns and terminology in {src_name} to guide Whisper STT (15~25 comma-separated terms).
4. "phonetic_fix_map": Common acoustic/phonetic misspellings -> correct words for Whisper (5~15 mappings).
5. "glossary": Key {src_name} terms -> official {tgt_name} translations that the translation engine must strictly follow (15~30 mappings).

Output strictly in the following JSON schema:
{{
  "source_summary": "...",
  "tone_and_style": "...",
  "whisper_initial_prompt": "term1, term2, term3",
  "phonetic_fix_map": {{"wrong_word": "CorrectWord"}},
  "glossary": {{"SourceTerm": "TargetTranslation"}}
}}"""
        res = self._call_gemini_json(prompt, system_instruction)
        if not res:
            return PreProcessingContext(initial_prompt_tokens=title, source_summary=title)

        return PreProcessingContext(
            initial_prompt_tokens=res.get("whisper_initial_prompt", ""),
            phonetic_fix_map=res.get("phonetic_fix_map", {}),
            glossary=res.get("glossary", {}),
            tone_and_style=res.get("tone_and_style", ""),
            source_summary=res.get("source_summary", "")
        )

    def analyze_full_script(self, transcript_text: str, title: str = "", source_lang: str = "en", target_lang: str = "ko") -> PreProcessingContext:
        """자막 스크립트 전문(Ground-Truth)을 분석하여 고정밀 교정 사전 생성 (다국어 지원)"""
        from src.translator import get_language_name
        src_code = str(source_lang or "en").strip().lower().split("-")[0]
        tgt_code = str(target_lang or "ko").strip().lower().split("-")[0]

        sample_text = transcript_text
        if len(sample_text) > 30000:
            sample_text = sample_text[:15000] + "\n...[중략]...\n" + sample_text[-15000:]

        if tgt_code == "ko":
            src_name = get_language_name(src_code, native=True) if src_code not in ("auto", "none", "") else "원문"
            tgt_name = "한국어"
            system_instruction = (
                "당신은 영상 원본 스크립트 전문을 감사하여 실제 발화된 전문용어와 STT 오류 가능성을 추출하는 언어 전문가입니다."
            )
            prompt = f"""영상 제목: {title}
영상 스크립트(Ground-Truth):
{sample_text}

요구사항:
1. "source_summary": 영상의 핵심 주제 요약 (1~2문장)
2. "tone_and_style": 화자의 발화 스타일 및 적절한 자막 번역체
3. "whisper_initial_prompt": 본문에 실제 등장한 핵심 고유명사, 인명, 기술용어 20~30개 (쉼표 구분)
4. "phonetic_fix_map": 자동 자막이나 STT에서 발음 혼동으로 오인식되기 쉬운 오기 단어 -> 정답 단어 매핑 (10~25개)
5. "glossary": 본문의 전문용어/고유명사 -> 일관된 공식 {tgt_name} 번역 매핑 (20~40개)

반드시 JSON 형식으로만 반환하세요:
{{
  "source_summary": "...",
  "tone_and_style": "...",
  "whisper_initial_prompt": "term1, term2",
  "phonetic_fix_map": {{"misheard": "ActualTerm"}},
  "glossary": {{"Term": "{tgt_name}번역"}}
}}"""
        else:
            src_name = get_language_name(src_code, native=False) if src_code not in ("auto", "none", "") else "source language"
            tgt_name = get_language_name(tgt_code, native=False)
            system_instruction = (
                "You are an expert language engineer auditing an official video transcript to extract spoken domain terminology and potential STT misrecognitions."
            )
            prompt = f"""Video Title: {title}
Transcript (Ground-Truth):
{sample_text}

Requirements:
1. "source_summary": 1~2 sentence summary of the core video topic.
2. "tone_and_style": Speaker's communication style and natural subtitle style in {tgt_name}.
3. "whisper_initial_prompt": Key proper nouns, names, technical terms in {src_name} from the text (20~30 terms, comma-separated).
4. "phonetic_fix_map": Acoustically ambiguous words likely to be misheard by STT -> correct word mappings (10~25 pairs).
5. "glossary": Key terminology from text -> official {tgt_name} translations (20~40 pairs).

Output strictly in JSON format:
{{
  "source_summary": "...",
  "tone_and_style": "...",
  "whisper_initial_prompt": "term1, term2",
  "phonetic_fix_map": {{"misheard": "ActualTerm"}},
  "glossary": {{"Term": "{tgt_name} Translation"}}
}}"""
        res = self._call_gemini_json(prompt, system_instruction)
        if not res:
            return PreProcessingContext(source_summary=title)

        return PreProcessingContext(
            initial_prompt_tokens=res.get("whisper_initial_prompt", ""),
            phonetic_fix_map=res.get("phonetic_fix_map", {}),
            glossary=res.get("glossary", {}),
            tone_and_style=res.get("tone_and_style", ""),
            source_summary=res.get("source_summary", "")
        )
