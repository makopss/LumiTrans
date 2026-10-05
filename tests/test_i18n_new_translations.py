import unittest
from src.i18n import set_ui_language, ui_language, tr, get_model_desc
from src.config import tempo_preset_desc
from src.audio_capture import AudioLoopbackCapture


class TestI18nNewTranslations(unittest.TestCase):
    def setUp(self):
        self._orig_lang = ui_language()

    def tearDown(self):
        set_ui_language(self._orig_lang)

    def test_model_descriptions_localized(self):
        stt_model = {"id": "tiny.en", "desc": "초경량 테스트/저사양용, 초저지연 (영어 전용)"}
        llm_model = {"tag": "translategemma:4b", "desc": "로컬 최고 품질 | 원작 뉘앙스/문맥 번역 종결자"}

        set_ui_language("ko")
        self.assertIn("초경량", get_model_desc(stt_model))
        self.assertIn("로컬 최고 품질", get_model_desc(llm_model))

        set_ui_language("en")
        self.assertIn("Ultra-light", get_model_desc(stt_model))
        self.assertIn("Top local quality", get_model_desc(llm_model))
        # By string fallback
        self.assertIn("Ultra-light", get_model_desc("초경량 테스트/저사양용, 초저지연 (영어 전용)"))

    def test_inplace_translator_strings_localized(self):
        set_ui_language("ko")
        self.assertEqual(tr("inplace_banner_title"), "인플레이스 번역")
        self.assertEqual(tr("inplace_text_only"), "텍스트만")
        self.assertEqual(tr("inplace_with_bg"), "배경포함")
        self.assertEqual(tr("inplace_font_default"), "기본")
        self.assertIn("원문", tr("inplace_original"))
        self.assertIn("신뢰도", tr("inplace_ocr_confidence"))

        set_ui_language("en")
        self.assertEqual(tr("inplace_banner_title"), "In-Place Translation")
        self.assertEqual(tr("inplace_text_only"), "Text Only")
        self.assertEqual(tr("inplace_with_bg"), "With Background")
        self.assertEqual(tr("inplace_font_default"), "Default")
        self.assertEqual(tr("inplace_original"), "Original")
        self.assertEqual(tr("inplace_ocr_confidence"), "OCR Confidence")

    def test_tempo_status_and_descriptions_localized(self):
        set_ui_language("ko")
        desc_ko = tempo_preset_desc("smart", {"device": "cpu"})
        self.assertIn("발화 속도", desc_ko)
        self.assertIn("빠른 템포", tr("tempo_status_fast", wpm=180))
        self.assertIn("차분한 템포", tr("tempo_status_calm", wpm=100))
        self.assertIn("균형 템포", tr("tempo_status_balanced", wpm=140))
        self.assertIn("Deepgram 분절은 독립", tr("tempo_status_smart_deepgram", dub_speed="+15%"))

        set_ui_language("en")
        desc_en = tempo_preset_desc("smart", {"device": "cpu"})
        self.assertIn("speaker", desc_en.lower())
        self.assertIn("Fast Tempo", tr("tempo_status_fast", wpm=180))
        self.assertIn("Calm Tempo", tr("tempo_status_calm", wpm=100))
        self.assertIn("Balanced Tempo", tr("tempo_status_balanced", wpm=140))
        self.assertIn("Deepgram segmentation is independent", tr("tempo_status_smart_deepgram", dub_speed="+15%"))

    def test_youtube_glossary_status_localized(self):
        set_ui_language("ko")
        self.assertIn("도메인 사전 활성화", tr("yt_glossary_active"))
        self.assertIn("도메인 사전을 생성하지 못했습니다", tr("yt_glossary_failed_key"))
        self.assertIn("사전 생성 실패", tr("yt_glossary_failed_error", error="test"))

        set_ui_language("en")
        self.assertIn("Domain Glossary Active", tr("yt_glossary_active"))
        self.assertIn("Failed to generate domain glossary", tr("yt_glossary_failed_key"))
        self.assertIn("Failed to build glossary", tr("yt_glossary_failed_error", error="test"))

    def test_screen_ocr_worker_status_localized(self):
        set_ui_language("ko")
        self.assertEqual(tr("ocr_status_done", engine="Google"), "번역 완료 (Google)")
        self.assertEqual(tr("ocr_status_retrying"), "번역 연결 확인 중 · 자동 재시도")
        self.assertEqual(tr("ocr_status_translating_area", n=1), "영역 1 번역 중...")
        self.assertEqual(tr("ocr_status_no_areas"), "영역 없음")
        self.assertEqual(tr("ocr_status_load_failed"), "OCR 로드 실패")
        self.assertEqual(tr("ocr_status_paused"), "일시정지됨")
        self.assertEqual(tr("ocr_status_monitoring"), "감시 중")

        set_ui_language("en")
        self.assertEqual(tr("ocr_status_done", engine="Google"), "Translation complete (Google)")
        self.assertEqual(tr("ocr_status_retrying"), "Checking translation connection · Retrying automatically")
        self.assertEqual(tr("ocr_status_translating_area", n=1), "Translating area 1...")
        self.assertEqual(tr("ocr_status_no_areas"), "No areas")
        self.assertEqual(tr("ocr_status_load_failed"), "OCR load failed")
        self.assertEqual(tr("ocr_status_paused"), "Paused")
        self.assertEqual(tr("ocr_status_monitoring"), "Monitoring")

    def test_model_download_progress_localized(self):
        set_ui_language("ko")
        self.assertIn("다운로드 준비 중", tr("model_download_preparing", repo="repo"))
        self.assertIn("가중치 다운로드 중", tr("model_download_weights", size="10MB", pct=50, speed=""))
        self.assertIn("무결성 검증 완료", tr("model_download_verified"))
        self.assertIn("Ollama 연결 중", tr("ollama_connecting", tag="tag"))
        self.assertIn("HuggingFace 연결 중", tr("hf_connecting", filename="file"))
        self.assertIn("CUDA 가속 팩 서버 연결 중", tr("cuda_pack_connecting"))

        set_ui_language("en")
        self.assertIn("Preparing download", tr("model_download_preparing", repo="repo"))
        self.assertIn("Downloading weights", tr("model_download_weights", size="10MB", pct=50, speed=""))
        self.assertIn("integrity verification complete", tr("model_download_verified"))
        self.assertIn("Connecting to Ollama", tr("ollama_connecting", tag="tag"))
        self.assertIn("Connecting to HuggingFace", tr("hf_connecting", filename="file"))
        self.assertIn("Connecting to CUDA pack server", tr("cuda_pack_connecting"))

    def test_audio_capture_tags_and_known_apps_localized(self):
        set_ui_language("ko")
        self.assertEqual(tr("audio_app_tag"), "앱")
        self.assertEqual(tr("audio_pending_tag"), "실행 대기")
        self.assertIn("네이버 웨일", AudioLoopbackCapture.get_known_app_label("whale.exe"))
        self.assertIn("팟플레이어", AudioLoopbackCapture.get_known_app_label("potplayer64.exe"))
        self.assertIn("스포티파이", AudioLoopbackCapture.get_known_app_label("spotify.exe"))
        self.assertIn("디스코드", AudioLoopbackCapture.get_known_app_label("discord.exe"))

        set_ui_language("en")
        self.assertEqual(tr("audio_app_tag"), "App")
        self.assertEqual(tr("audio_pending_tag"), "Pending")
        self.assertEqual(AudioLoopbackCapture.get_known_app_label("whale.exe"), "Naver Whale")
        self.assertEqual(AudioLoopbackCapture.get_known_app_label("potplayer64.exe"), "PotPlayer 64-bit")
        self.assertEqual(AudioLoopbackCapture.get_known_app_label("spotify.exe"), "Spotify")
        self.assertEqual(AudioLoopbackCapture.get_known_app_label("discord.exe"), "Discord")


if __name__ == "__main__":
    unittest.main()
