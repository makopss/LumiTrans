"""Unit test for screen dubbing toggle behavior and isolation."""
import os
import sys
import unittest
import threading
import queue

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.dubbing_engine import DubbingEngine
from src.screen_ocr_worker import ScreenOCRWorker


class DummySignal:
    def __init__(self):
        self.emitted = []

    def emit(self, *args):
        self.emitted.append(args)

    def connect(self, slot):
        pass


class DummyTranslator:
    def __init__(self):
        pass

    def update_config(self, cfg):
        pass


class ScreenDubbingToggleTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "dubbing_enabled": True,
            "dubbing_source_audio": True,
            "dubbing_source_screen": False,
            "screen_translate_enabled": True,
            "screen_rois": [[100, 100, 300, 100]],
            "screen_snap_to_roi": False,
            "screen_clean_text_mode": False,
            "translation_engine": "google",
            "source_lang": "en",
            "target_lang": "ko",
            "dubbing_volume": 80,
            "dubbing_speed": "+0%",
            "dubbing_interrupt": False,
            "dubbing_echo_cancellation": False,
        }
        self.dubbing_engine = DubbingEngine(self.config)
        self.screen_worker = ScreenOCRWorker(
            config=self.config,
            translator=DummyTranslator(),
            dubbing_engine=self.dubbing_engine
        )
        self.screen_worker.is_paused = False

    def tearDown(self):
        self.dubbing_engine.stop()
        self.screen_worker.is_running = False

    def test_screen_dubbing_toggle_and_delivery(self):
        # 1. 초기 상태: dubbing_source_audio=True, dubbing_source_screen=False
        # 오디오는 허용, 화면은 차단되어야 함
        self.dubbing_engine.enqueue("오디오 문장 1", source="audio")
        self.assertEqual(self.dubbing_engine.text_queue.qsize(), 1)
        self.dubbing_engine.clear_queue()

        # 화면 번역 결과 전달 시도 -> dubbing_source_screen이 False이므로 큐에 들어가지 않아야 함
        token = self.screen_worker._begin_request(self.screen_worker._regions(), 0, False)
        self.screen_worker._deliver_result((token, "Hello world", "안녕하세요 세상", "Google"))
        self.assertEqual(self.dubbing_engine.text_queue.qsize(), 0)

        # 2. 사용자 조작: 화면 번역 더빙 ON, 음성 번역 더빙 OFF
        self.config["dubbing_source_screen"] = True
        self.dubbing_engine.set_source_enabled("screen", True)
        self.screen_worker.update_config(self.config)

        self.config["dubbing_source_audio"] = False
        self.dubbing_engine.set_source_enabled("audio", False)

        # 3. 음성 더빙 전달 시도 -> 차단되어야 함
        self.dubbing_engine.enqueue("오디오 문장 2", source="audio")
        self.assertEqual(self.dubbing_engine.text_queue.qsize(), 0)

        # 4. 화면 번역 결과 전달 시도 -> 정상적으로 큐에 들어가야 함!
        token2 = self.screen_worker._begin_request(self.screen_worker._regions(), 0, False)
        self.screen_worker._deliver_result((token2, "Welcome to the game", "게임에 오신 것을 환영합니다", "Google"))
        self.assertEqual(self.dubbing_engine.text_queue.qsize(), 1)
        item = self.dubbing_engine.text_queue.get_nowait()
        self.assertEqual(item["source"], "screen")
        self.assertEqual(item["text"], "게임에 오신 것을 환영합니다")

    def test_instant_capture_dubbing_when_paused(self):
        # 화면 연속 번역이 일시정지 상태일 때 즉시 캡처(1회 번역)는 force_active로 더빙 큐에 들어가야 함
        self.dubbing_engine.set_source_enabled("screen", True)
        self.dubbing_engine.set_source_active("screen", False)  # 일시정지 시뮬레이션

        # 일반 연속 번역 토큰 (instant=False) -> 차단됨
        token_normal = (
            self.screen_worker._generation,
            self.screen_worker._regions(),
            0,
            self.screen_worker._latest_requests.get(0, 0),
            False,
            self.screen_worker._translation_signature()
        )
        # _is_current가 paused 체크하므로 직접 enqueue 호출로 엔진 검증
        self.dubbing_engine.enqueue("일반 번역 텍스트", source="screen", force_active=False)
        self.assertEqual(self.dubbing_engine.text_queue.qsize(), 0)

        # 즉시 캡처 (force_active=True) -> 일시정지 상태여도 허용됨!
        self.dubbing_engine.enqueue("즉시 캡처 텍스트", source="screen", force_active=True)
        self.assertEqual(self.dubbing_engine.text_queue.qsize(), 1)
        item = self.dubbing_engine.text_queue.get_nowait()
        self.assertEqual(item["text"], "즉시 캡처 텍스트")


if __name__ == "__main__":
    unittest.main()
