# -*- coding: utf-8 -*-
"""
test_universal_pipeline_rules.py - 4대 범용 파이프라인 엔진 개선점 단위 테스트
1. 초단편 청크 사전/컨텍스트 주입 가드레일 (Length Guardrail & Selective Glossary)
2. 미완결 구문(접속사/전치사/수식어/불완전타동사) 지연 결합 판별 (SemanticClauseDetector)
3. 앵무새 루프 및 반복 토큰 자동 압축 (EnglishTextNormalizer)
4. 공통 무음/간투사/유튜브 종결 환각 전역 차단 (HALLUCINATIONS & Normalizer)
"""

import unittest
from src.pre_processor import PreProcessingContext
from src.stt_engine import EnglishTextNormalizer, SemanticClauseDetector, HALLUCINATIONS


class TestUniversalPipelineRules(unittest.TestCase):

    # =========================================================================
    # 1. EnglishTextNormalizer 환각 제거 및 반복 토큰 압축 검증
    # =========================================================================

    def test_hallucination_stripping_and_more(self):
        """Whisper의 고질적인 'And more' / 'And many more' 환각 어구 자동 제거 검증"""
        # 문두 단독 환각 제거
        self.assertEqual(EnglishTextNormalizer.normalize("And more."), "")
        self.assertEqual(EnglishTextNormalizer.normalize("And many more."), "")

        # 문두 접두 환각 제거
        self.assertEqual(
            EnglishTextNormalizer.normalize("And more. From the beginning."),
            "From the beginning."
        )

        # 문장 중간에 끼어든 환각 정제
        corrupted = "People who really And more. That want to see the future."
        cleaned = EnglishTextNormalizer.normalize(corrupted)
        self.assertEqual(cleaned, "People who really That want to see the future.")

        # 문미 유튜브 엔딩 멘트 제거
        ending = "That is the story. Thank you for watching."
        self.assertEqual(EnglishTextNormalizer.normalize(ending), "That is the story.")

    def test_repetition_squash(self):
        """동일 단어/구문 연속 3회 이상 반복(앵무새 루프) 억제 검증"""
        # 쉼표 연결 단어 3연속 반복 압축
        self.assertEqual(EnglishTextNormalizer.normalize("very, very, very special"), "Very special")
        self.assertEqual(EnglishTextNormalizer.normalize("no, no, no, no"), "No")

        # 공백 연결 3연속 반복 압축
        self.assertEqual(EnglishTextNormalizer.normalize("really really really fast"), "Really fast")

        # 2단어 구문 중복 압축
        self.assertEqual(EnglishTextNormalizer.normalize("I think I think that"), "I think that")
        self.assertEqual(EnglishTextNormalizer.normalize("you know, you know what"), "You know what")

    # =========================================================================
    # 2. HALLUCINATIONS 블랙리스트 검증
    # =========================================================================

    def test_hallucination_blacklist_membership(self):
        """침묵/음악 구간에서 발생하는 핵심 환각 어구들이 블랙리스트에 등재되어 있는지 검증"""
        sample_hallucinations = [
            "and more", "and more.", "and many more", "and many more.",
            "thank you for watching.", "thank you for watching",
            "thank you for listening.", "thanks for listening.",
            "subtitles by the amara.org community"
        ]
        for h in sample_hallucinations:
            self.assertIn(h.lower().strip(), HALLUCINATIONS, f"'{h}' should be in HALLUCINATIONS")

    # =========================================================================
    # 3. SemanticClauseDetector 미완결 구문 판별 및 적응형 플러시 검증
    # =========================================================================

    def test_dangling_detection_expanded_cases(self):
        """실제 발화에서 끊어지기 쉬운 미완결 어미(비교급, 불완전 타동사, 전치사 등) 식별 검증"""
        # 1. 비교급 / 수식어 어미 ('most', 'first', etc.)
        self.assertTrue(SemanticClauseDetector.is_dangling("That will probably be the most"))
        self.assertTrue(SemanticClauseDetector.is_dangling("You are about to see the first..."))

        # 2. 불완전 타동사 어미 ('make', 'get', 'take', etc.)
        self.assertTrue(SemanticClauseDetector.is_dangling("They said they would never make"))

        # 3. 전치사 및 접속사 어미 ('of', 'that', 'and', etc.)
        self.assertTrue(SemanticClauseDetector.is_dangling("A large family of"))
        self.assertTrue(SemanticClauseDetector.is_dangling("He stated that"))
        self.assertTrue(SemanticClauseDetector.is_dangling("We went there and"))

        # 4. 완결된 문장 (Dangling 아님)
        self.assertFalse(SemanticClauseDetector.is_dangling("Technology is so extraordinary."))
        self.assertTrue(SemanticClauseDetector.is_complete_sentence("Technology is so extraordinary."))

    def test_should_flush_adaptive_silence(self):
        """미완결 문장에 대해 적응형 침묵 대기 시간(>= 1.8초)이 올바르게 적용되는지 검증"""
        dangling_text = "That will probably be the most"
        # 1.0초 침묵 시에는 flush하지 않고 결합 대기
        self.assertFalse(SemanticClauseDetector.should_flush(dangling_text, elapsed_silence=1.0))
        # 2.0초 이상 장시간 침묵 시에는 안전 플러시
        self.assertTrue(SemanticClauseDetector.should_flush(dangling_text, elapsed_silence=2.5))

        # 완결된 문장은 0.35초 짧은 침묵에도 신속 플러시
        complete_text = "Technology is so extraordinary."
        self.assertTrue(SemanticClauseDetector.should_flush(complete_text, elapsed_silence=0.5))

    # =========================================================================
    # 4. PreProcessingContext 초단편 가드레일 및 선별적 용어집(Selective Glossary) 검증
    # =========================================================================

    def test_short_chunk_guardrail_suppresses_summary(self):
        """3단어 이하 초단편 발화 시 영상 요약문(source_summary)이 LLM 프롬프트에 누출되지 않는지 검증"""
        ctx = PreProcessingContext(
            source_summary="클라우드 인프라 기술 강연의 핵심 개념 소개",
            glossary={
                "Kubernetes": "쿠버네티스",
                "Docker": "도커",
                "latency": "지연 시간"
            }
        )

        hymt_prompt_short = ctx.format_for_hymt(target_text="Ever made.")
        self.assertEqual(hymt_prompt_short, "")
        self.assertNotIn("클라우드 인프라 기술 강연", hymt_prompt_short)

        exaone_prompt_short = ctx.format_for_exaone(target_text="They")
        self.assertEqual(exaone_prompt_short, "")
        self.assertNotIn("클라우드 인프라 기술 강연", exaone_prompt_short)

        gemini_prompt_short = ctx.format_for_gemini(target_text="They")
        self.assertEqual(gemini_prompt_short, "")
        self.assertNotIn("클라우드 인프라 기술 강연", gemini_prompt_short)

    def test_selective_glossary_filtering(self):
        """문장에 실제로 등장하는 용어만 선별하여 프롬프트에 주입하는지 검증"""
        ctx = PreProcessingContext(
            source_summary="인프라 강연",
            glossary={
                "Kubernetes": "쿠버네티스",
                "Docker": "도커",
                "PostgreSQL": "포스트그레SQL",
                "latency": "지연 시간"
            }
        )

        target = "We are currently running the new Kubernetes Docker stack."
        hymt_prompt = ctx.format_for_hymt(target_text=target)

        self.assertIn("Kubernetes translates to 쿠버네티스", hymt_prompt)
        self.assertIn("Docker translates to 도커", hymt_prompt)
        self.assertNotIn("PostgreSQL", hymt_prompt)
        self.assertNotIn("latency", hymt_prompt)
        self.assertNotIn("[Context]:", hymt_prompt)

        exaone_prompt = ctx.format_for_exaone(target_text=target)
        self.assertIn("[핵심 맥락]: 인프라 강연", exaone_prompt)
        self.assertIn("Kubernetes", exaone_prompt)
        self.assertNotIn("PostgreSQL", exaone_prompt)

    def test_phonetic_fixes_only_from_injected_map(self):
        """전역 치환 없이, 주입된 phonetic_fix_map만 적용되는지 검증"""
        raw_text = "The cheap designer spoke about the cluster."
        self.assertEqual(PreProcessingContext().apply_phonetic_fixes(raw_text), raw_text)

        mapped = PreProcessingContext(phonetic_fix_map={"cheap designer": "chief designer"})
        fixed_text = mapped.apply_phonetic_fixes(raw_text)
        self.assertIn("chief designer", fixed_text)
        self.assertNotIn("cheap designer", fixed_text)

    def test_backwards_compatibility_without_target_text(self):
        """target_text=None 호출 시 기존 전체 용어집 출력 방식과 100% 호환되는지 검증"""
        ctx = PreProcessingContext(
            source_summary="전체 요약",
            glossary={"Kubernetes": "쿠버네티스", "Docker": "도커"}
        )
        hymt_all = ctx.format_for_hymt()
        self.assertIn("Kubernetes translates to 쿠버네티스", hymt_all)
        self.assertIn("Docker translates to 도커", hymt_all)
        self.assertIn("[Context]: 전체 요약", hymt_all)

    def test_no_video_specific_global_overrides(self):
        """전역 규칙에 특정 영상 고유명사/단독 more/의미 있는 단일어가 남아 있지 않은지 검증"""
        self.assertFalse(hasattr(PreProcessingContext, "COMMON_ACOUSTIC_FIXES"))
        from src.translator import SKIP_SINGLE_WORDS
        self.assertTrue({"more", "more."}.isdisjoint(HALLUCINATIONS))
        self.assertTrue({"like", "well", "just", "then", "now", "but", "here", "there"}.isdisjoint(SKIP_SINGLE_WORDS))


if __name__ == "__main__":
    unittest.main()
