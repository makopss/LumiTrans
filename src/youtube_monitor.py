# -*- coding: utf-8 -*-
"""
youtube_monitor.py - 백그라운드 유튜브 영상 실시간 감시 및 Ground-Truth 도메인 사전 자동 주입기
브라우저 재생 중인 유튜브를 감지하여 0.5초 만에 자막을 추출하고,
Gemini Flash를 통해 STT/번역기용 고정밀 사전을 자동 핫스왑합니다.
"""

import threading
import time
from typing import Optional, Callable
from src.youtube_helper import auto_detect_youtube_url, fetch_youtube_full_data, extract_youtube_id
from src.pre_processor import GeminiPreProcessor, PreProcessingContext
from src.i18n import tr


class YouTubeMonitor(threading.Thread):
    """브라우저의 유튜브 재생 상태를 감시하고 사전을 자동 생성/주입하는 백그라운드 워커"""

    def __init__(
        self,
        config: dict,
        stt_worker=None,
        on_notify: Optional[Callable[[str], None]] = None,
        check_interval: float = 4.0
    ):
        super().__init__(daemon=True, name="YouTubeMonitorThread")
        self.config = config
        self.stt_worker = stt_worker
        self.on_notify = on_notify
        self.check_interval = max(2.0, check_interval)
        self.running = False
        self.is_active = False  # 초기 기동 시에는 분석 미실행 (번역 시작 시 활성화)
        self.last_video_id = None
        self._analyzing = False
        self._trigger_event = threading.Event()

    def set_active(self, active: bool):
        """번역 시작/중지 상태에 따라 유튜브 감시 워커 활성/비활성 전환"""
        self.is_active = active
        if active:
            self._trigger_event.set()

    def on_translation_started(self):
        """번역 시작을 누르는 순간: 즉시 브라우저 유튜브 감지 및 비동기 사전 분석 트리거 (자막은 지연 없이 즉시 시작)"""
        self.set_active(True)
        self.trigger_immediate_detection()

    def trigger_immediate_detection(self):
        """비동기로 즉시 1회 감지 수행 (메인 스레드나 자막 표출을 블로킹하지 않음)"""
        t = threading.Thread(target=self._check_and_process_once, daemon=True, name="YTImmediateCheck")
        t.start()

    def stop(self):
        self.running = False
        self.is_active = False
        self._trigger_event.set()

    def _check_and_process_once(self):
        """현재 열린 브라우저에서 유튜브 URL을 감지하고 새 영상일 경우 백그라운드 사전 생성 착수"""
        if not self.config.get("auto_youtube_detect", False):
            return
        if not self.config.get("gemini_api_key", "").strip():
            return
        if self._analyzing:
            return
        try:
            detected_url = auto_detect_youtube_url()
            if detected_url and not self._analyzing:
                vid = extract_youtube_id(detected_url)
                if vid and vid != self.last_video_id:
                    self.last_video_id = vid
                    # 비동기 사전 생성 태스크 시작 (자막/번역은 이미 실시간 진행 중)
                    t = threading.Thread(
                        target=self._process_video,
                        args=(vid, detected_url),
                        daemon=True,
                        name="YTProcessVideo"
                    )
                    t.start()
        except Exception as e:
            print(f"[YouTubeMonitor] 감시 감지 예외: {e}")

    def run(self):
        self.running = True
        try:
            print("[YouTubeMonitor] [서비스 준비] 유튜브 도메인 사전 서비스 대기 중 (번역 시작 시 자동 감지)")
        except Exception:
            pass

        while self.running:
            try:
                # 1. 초기 기동 시에는 분석 미수행 (번역이 시작되고, 토글이 켜져 있으며, Gemini 키가 설정된 경우에만 백그라운드 감시 루프 가동)
                if (
                    not self.is_active
                    or not self.config.get("auto_youtube_detect", False)
                    or not self.config.get("gemini_api_key", "").strip()
                ):
                    self._trigger_event.wait(timeout=1.0)
                    self._trigger_event.clear()
                    continue

                # 2. 번역 실행 중일 때 브라우저 주소창에서 유튜브 URL 감지
                self._check_and_process_once()

            except Exception as e:
                print(f"[YouTubeMonitor] 감시 루프 예외: {e}")

            self._trigger_event.wait(timeout=self.check_interval)
            self._trigger_event.clear()

    def _process_video(self, vid: str, url: str):
        """감지된 유튜브 영상 데이터 수집 및 사전 자동 생성"""
        self._analyzing = True
        try:
            print(f"[YouTubeMonitor] [새 영상 감지] https://www.youtube.com/watch?v={vid}")
            yt_data = fetch_youtube_full_data(vid, source_lang=self.config.get("stt_language", "en"))
            title = yt_data.get("title", "") or f"YouTube Video ({vid})"
            has_transcript = yt_data.get("has_transcript", False)
            transcript = yt_data.get("transcript", "")

            status_msg = f"[YouTube 감지] {title[:25]}... ({'자막 전문 확보' if has_transcript else '제목 메타데이터'})"
            try:
                print(f"[YouTubeMonitor] {status_msg}")
            except Exception:
                pass
            if self.on_notify:
                try:
                    self.on_notify(status_msg)
                except Exception as ne:
                    print(f"[YouTubeMonitor] 알림 콜백 예외: {ne}")

            # Gemini API Key 확인
            api_key = self.config.get("gemini_api_key", "").strip()
            preprocessor = GeminiPreProcessor(api_key=api_key)

            try:
                print(f"[YouTubeMonitor] [사전 생성 중] 도메인 사전 & STT 음운 교정 맵 생성 중 (Gemini Flash)...")
            except Exception:
                pass
            # 영상 원문 언어 자동 감별 (설정 언어 우선, 그 외 스크립트 정규식 분석)
            import re
            stt_pref = str(self.config.get("stt_language") or "").strip().lower()
            if stt_pref and stt_pref not in ("auto", "none"):
                video_src_lang = stt_pref.split("-")[0]
            else:
                sample_text = f"{title} {transcript[:1000]}"
                if re.search(r'[\u3040-\u30ff]', sample_text):
                    video_src_lang = "ja"
                elif re.search(r'[\uac00-\ud7a3]', sample_text):
                    video_src_lang = "ko"
                elif re.search(r'[\u4e00-\u9fff]', sample_text):
                    video_src_lang = "zh"
                elif re.search(r'[\u0400-\u04ff]', sample_text):
                    video_src_lang = "ru"
                elif re.search(r'[\u0600-\u06ff]', sample_text):
                    video_src_lang = "ar"
                else:
                    video_src_lang = "en"

            video_tgt_lang = str(self.config.get("target_lang") or self.config.get("target") or "ko").strip().lower().split("-")[0]

            if has_transcript and len(transcript) > 100:
                ctx = preprocessor.analyze_full_script(transcript, title=title, source_lang=video_src_lang, target_lang=video_tgt_lang)
            else:
                ctx = preprocessor.analyze_metadata(title, additional_topic=f"채널: {yt_data.get('author', '')}", source_lang=video_src_lang, target_lang=video_tgt_lang)

            if ctx and not ctx.is_empty():
                # STT 및 번역기에 즉시 사전 핫스왑 적용
                if self.stt_worker:
                    self.stt_worker.set_pre_context(ctx)

                success_msg = tr("yt_glossary_active_detail", title=title[:20], terms=len(ctx.glossary), fixes=len(ctx.phonetic_fix_map))
                try:
                    print(f"[YouTubeMonitor] {success_msg}")
                except Exception:
                    pass
                if self.on_notify:
                    try:
                        self.on_notify(success_msg)
                    except Exception as ne:
                        print(f"[YouTubeMonitor] 알림 콜백 예외: {ne}")

                return title, ctx

            return title, None

        except Exception as e:
            print(f"[YouTubeMonitor] 사전 생성 오류: {e}")
            return None
        finally:
            self._analyzing = False

    def process_url_manually(self, url: str, on_done=None) -> bool:
        """사용자가 직접 입력한 YouTube URL로부터 사전을 즉시 생성 (비동기 스레드 실행)"""
        vid = extract_youtube_id(url)
        if not vid:
            return False

        self.last_video_id = vid

        def _worker():
            try:
                res = self._process_video(vid, url)
                if on_done:
                    if res:
                        on_done(True, res[0], res[1])
                    else:
                        on_done(False, "사전 생성에 실패했습니다.", None)
            except Exception as e:
                if on_done:
                    on_done(False, str(e), None)

        t = threading.Thread(target=_worker, daemon=True, name="ManualYouTubeWorker")
        t.start()
        return True
