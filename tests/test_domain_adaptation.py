# -*- coding: utf-8 -*-
"""
test_domain_adaptation.py - 3대 최적화 기능(LLM 예열, 도메인 사전/STT 교정, 유튜브 헬퍼) 단위 테스트
"""

import unittest
from unittest.mock import Mock, patch
from src.pre_processor import PreProcessingContext, GeminiPreProcessor
from src.youtube_helper import extract_youtube_id, fetch_youtube_metadata
from src.translator import RealtimeTranslator


class TestDomainAdaptation(unittest.TestCase):

    def test_phonetic_fixes_word_boundaries(self):
        """단어 경계(\\b)가 올바르게 적용되어 부분 일치 왜곡이 방지되는지 검증"""
        ctx = PreProcessingContext(
            phonetic_fix_map={
                "part": "Pod",
                "cube or net ease": "Kubernetes",
                "post gre": "PostgreSQL",
                "lay ten see": "latency",
            }
        )

        # 1. 독립 단어 치환 검증
        orig = "we deployed on part in cube or net ease yesterday."
        corrected = ctx.apply_phonetic_fixes(orig)
        self.assertEqual(corrected, "we deployed on Pod in Kubernetes yesterday.")

        # 2. 부분 일치 단어 보존 검증 (participate -> Podicipate로 왜곡되지 않아야 함)
        no_mangle = "I want to participate in this project."
        self.assertEqual(ctx.apply_phonetic_fixes(no_mangle), no_mangle)

        # 3. 다중 어절 치환 검증
        multi_word = "The delay comes from post gre and lay ten see in vicinity."
        self.assertEqual(ctx.apply_phonetic_fixes(multi_word), "The delay comes from PostgreSQL and latency in vicinity.")

    def test_glossary_formatters(self):
        """각 LLM 아키텍처별 프롬프트 블록이 규격에 맞게 생성되는지 검증"""
        ctx = PreProcessingContext(
            source_summary="Open source infrastructure conference talk",
            tone_and_style="원문 말투를 살린 자연스러운 자막",
            glossary={
                "Kubernetes": "쿠버네티스",
                "PostgreSQL": "포스트그레SQL",
                "latency": "지연 시간"
            }
        )

        # EXAONE Markdown Table 검증
        exaone_fmt = ctx.format_for_exaone()
        self.assertIn("| 원문 용어 (영어) | 공식 한국어 번역 |", exaone_fmt)
        self.assertIn("| Kubernetes | 쿠버네티스 |", exaone_fmt)
        self.assertIn("[핵심 맥락]: Open source infrastructure conference talk", exaone_fmt)

        # TranslateGemma 포맷 검증
        gemma_fmt = ctx.format_for_translategemma()
        self.assertIn("[Glossary & Terminology Guide", gemma_fmt)
        self.assertIn("- Kubernetes -> 쿠버네티스", gemma_fmt)

        # Hy-MT2 참고 번역 포맷 검증
        hymt_fmt = ctx.format_for_hymt()
        self.assertIn("Reference the following translations:", hymt_fmt)
        self.assertIn("Kubernetes translates to 쿠버네티스", hymt_fmt)

        # Groq / Qwen 포맷 검증
        groq_fmt = ctx.format_for_groq()
        self.assertIn("[Mandatory Domain Glossary", groq_fmt)
        self.assertIn("- PostgreSQL -> 포스트그레SQL", groq_fmt)

    def test_youtube_url_extraction(self):
        """다양한 형태의 YouTube URL에서 11자리 비디오 ID가 정상 추출되는지 검증"""
        samples = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/live/dQw4w9WgXcQ?feature=share", "dQw4w9WgXcQ"),
            ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://example.com/not-youtube", None),
        ]
        for url, expected in samples:
            self.assertEqual(extract_youtube_id(url), expected, f"Failed on: {url}")

    def test_translator_pre_context_injection(self):
        """RealtimeTranslator에 pre_context 주입 및 프롬프트 반영 검증"""
        translator = RealtimeTranslator({'translation_engine': 'hymt'})
        ctx = PreProcessingContext(
            glossary={"Kubernetes": "쿠버네티스"}
        )
        translator.set_pre_context(ctx)
        self.assertEqual(translator.pre_context, ctx)

    def test_warmup_1token_dummy_call(self):
        """preload_engine 호출 시 가중치 로드 직후 1-Token 더미 추론이 호출되는지 검증"""
        translator = RealtimeTranslator({'translation_engine': 'hymt', 'llm_backend': 'embedded'})
        mock_model = Mock()
        translator._get_hymt = Mock(return_value=mock_model)

        translator.preload_engine('hymt')

        # getter가 호출되었는지
        translator._get_hymt.assert_called_once()
        # 1-Token 더미 추론("hi", max_tokens=1)이 실행되었는지
        mock_model.assert_called_once_with("hi", max_tokens=1, temperature=0.0)

    def test_stt_worker_pre_context_and_phonetic_fixes(self):
        """STTWorker에 pre_context 주입 시 음운 교정 및 translator 전파가 일어나는지 검증"""
        from src.stt_engine import STTWorker
        import queue
        worker = STTWorker(
            audio_queue=queue.Queue(),
            config={'translation_engine': 'google', 'device': 'cpu'}
        )
        ctx = PreProcessingContext(
            initial_prompt_tokens="Kubernetes, PostgreSQL",
            phonetic_fix_map={"cube or net ease": "Kubernetes"}
        )
        worker.set_pre_context(ctx)

        # STTWorker와 하위 translator 양쪽에 전달되었는지
        self.assertEqual(worker.pre_context, ctx)
        self.assertEqual(worker.translator.pre_context, ctx)

        # 음운 교정 메서드 정상 동작
        self.assertEqual(worker.pre_context.apply_phonetic_fixes("look at that cube or net ease"), "look at that Kubernetes")

    def test_youtube_monitor_resilient_to_notification_error(self):
        """on_notify 콜백이 예외(인자 불일치 등)를 발생시켜도 사전 생성 및 STT 반영이 중단되지 않는지 검증"""
        from src.youtube_monitor import YouTubeMonitor

        broken_notify = Mock(side_effect=TypeError("signal has 2 argument(s) but 1 provided"))
        mock_stt_worker = Mock()

        monitor = YouTubeMonitor(
            config={"gemini_api_key": "fake-key", "auto_youtube_detect": True},
            stt_worker=mock_stt_worker,
            on_notify=broken_notify
        )

        dummy_ctx = PreProcessingContext(glossary={"Test": "테스트"})

        with patch("src.youtube_monitor.fetch_youtube_full_data") as mock_fetch, \
             patch("src.youtube_monitor.GeminiPreProcessor") as mock_prep_cls:

            mock_fetch.return_value = {
                "title": "Test Sci-Fi Video",
                "has_transcript": True,
                "transcript": "Hello and welcome to this long sci-fi story about space and galaxies and future technology. " * 3,
                "author": "SciFi Channel"
            }
            mock_prep_instance = Mock()
            mock_prep_instance.analyze_full_script.return_value = dummy_ctx
            mock_prep_instance.analyze_metadata.return_value = dummy_ctx
            mock_prep_cls.return_value = mock_prep_instance

            # 실행: 예외가 발생하더라도 _process_video가 정상 완주해야 함
            monitor._process_video("0g97kzzldgw", "https://www.youtube.com/watch?v=0g97kzzldgw")

            # stt_worker에 사전이 정상 주입되었는지 확인
            mock_stt_worker.set_pre_context.assert_called_once_with(dummy_ctx)
            # broken_notify가 호출되었으나 예외가 흡수되어 중단되지 않았는지 확인
            self.assertTrue(broken_notify.called)

    def test_deferred_gpu_warmup_on_translate(self):
        """gpu_warmup_on_startup=False일 때 시작 시 예열 스킵 및 번역 시 지연 예열 검증"""
        translator = RealtimeTranslator({'translation_engine': 'hymt', 'llm_backend': 'embedded', 'gpu_warmup_on_startup': False})
        mock_model = Mock()
        mock_model.return_value = {"choices": [{"text": "안녕", "finish_reason": "stop"}]}
        translator._get_hymt = Mock(return_value=mock_model)

        # 시작 시에는 _warmed_up_engines가 비어있어야 함
        self.assertNotIn('hymt', translator._warmed_up_engines)

        # translate 호출 시 1-Token 예열이 선행 수행되고 _warmed_up_engines에 등록되어야 함
        translator.translate("hello world this is a test")
        self.assertIn('hymt', translator._warmed_up_engines)
        # 1-Token 더미 호출과 실제 번역 호출 총 2회 발생 확인
        self.assertGreaterEqual(mock_model.call_count, 2)
        mock_model.assert_any_call("hi", max_tokens=1, temperature=0.0)

    def test_youtube_monitor_process_url_manually(self):
        """process_url_manually 호출 시 URL 파싱 후 수동 비동기 작업이 정상 가동되는지 검증"""
        from src.youtube_monitor import YouTubeMonitor
        import time

        mock_stt = Mock()
        monitor = YouTubeMonitor(
            config={"gemini_api_key": "test", "auto_youtube_detect": True},
            stt_worker=mock_stt
        )

        with patch.object(monitor, "_process_video", return_value=("Test Title", PreProcessingContext())) as mock_proc:
            # 1. 올바르지 않은 URL
            self.assertFalse(monitor.process_url_manually("https://example.com/not-youtube"))

            # 2. 올바른 URL
            done_signal = []
            ret = monitor.process_url_manually(
                "https://youtu.be/0g97kzzldgw",
                on_done=lambda ok, title, ctx: done_signal.append((ok, title))
            )
            self.assertTrue(ret)
            # 워커 스레드 완료 대기
            time.sleep(0.15)
            mock_proc.assert_called_once_with("0g97kzzldgw", "https://youtu.be/0g97kzzldgw")
            self.assertEqual(done_signal, [(True, "Test Title")])

    def test_youtube_monitor_lazy_activation_lifecycle(self):
        """초기 기동 시 비활성 상태 유지 및 번역 시작 시점에만 즉시 감지 및 비동기 분석 가동 검증"""
        from src.youtube_monitor import YouTubeMonitor

        mock_stt = Mock()
        monitor = YouTubeMonitor(
            config={"gemini_api_key": "test", "auto_youtube_detect": True},
            stt_worker=mock_stt
        )

        # 1. 초기 기동 시점: is_active=False이어야 하며, 자동 분석을 실행하지 않음
        self.assertFalse(monitor.is_active)

        # 2. 번역 시작 시점: on_translation_started 호출 시 활성화 및 즉시 감지 비동기 트리거
        with patch.object(monitor, "trigger_immediate_detection") as mock_trigger:
            monitor.on_translation_started()
            self.assertTrue(monitor.is_active)
            mock_trigger.assert_called_once()

        # 3. 번역 중지 시점: set_active(False) 호출 시 비활성화
        monitor.set_active(False)
        self.assertFalse(monitor.is_active)

    def test_youtube_monitor_skips_when_no_gemini_api_key(self):
        """Gemini API 키가 없으면 auto_youtube_detect=True여도 브라우저 감지 및 사전 생성을 완전히 스킵하는지 검증"""
        from src.youtube_monitor import YouTubeMonitor

        mock_stt = Mock()
        # gemini_api_key가 빈 문자열인 config
        monitor = YouTubeMonitor(
            config={"gemini_api_key": "", "auto_youtube_detect": True},
            stt_worker=mock_stt
        )

        with patch("src.youtube_monitor.auto_detect_youtube_url") as mock_detect:
            monitor._check_and_process_once()
            # API 키가 없으므로 브라우저 감지 함수조차 호출되지 않고 즉시 반환되어야 함
            mock_detect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
