"""Offline checks for pause/resume across dubbing source and playback boundaries."""
import queue
import importlib.util
import sys
import threading
import time
import types
import unittest

# The CI Python used for these state tests has no audio device libraries.
if importlib.util.find_spec("edge_tts") is None:
    sys.modules.setdefault("edge_tts", types.ModuleType("edge_tts"))
if importlib.util.find_spec("pygame") is None and "pygame" not in sys.modules:
    pygame = types.ModuleType("pygame")
    pygame.mixer = types.SimpleNamespace(Sound=object)
    sys.modules["pygame"] = pygame

from src.dubbing_engine import DubbingEngine


class FakeChannel:
    def __init__(self):
        self.plays = 0
        self.stops = 0

    def play(self, sound):
        self.plays += 1

    def stop(self):
        self.stops += 1

    def fadeout(self, ms):
        self.stops += 1

    def set_volume(self, volume):
        pass

    def get_busy(self):
        return False


class PauseLifecycleTests(unittest.TestCase):
    def make_engine(self):
        engine = DubbingEngine.__new__(DubbingEngine)
        engine.config = {"dubbing_enabled": True, "dubbing_source_audio": True,
                         "dubbing_source_screen": True, "dubbing_echo_cancellation": False}
        engine.speaker_identifier = None
        engine.text_queue = queue.Queue(maxsize=500)
        engine.playback_queue = queue.Queue(maxsize=500)
        engine.lock = threading.RLock()
        engine._generation = 0
        engine._source_generations = {"audio": 0, "screen": 0}
        engine._source_active = {"audio": True, "screen": True}
        engine._current_playing_source = None
        engine._current_synthesizing_item = None
        engine._stop_playback_requested = False
        engine._is_playing = False
        engine._current_speaking_text = ""
        engine._mixer_initialized = True
        engine._current_volume = 1.0
        engine.channel = FakeChannel()
        engine.recent_dubbed_history = []
        engine.playback_callbacks = []
        engine.is_running = True
        return engine

    def test_audio_pause_discards_only_audio_and_resume_accepts_new_work(self):
        engine = self.make_engine()
        engine.enqueue("첫 번째 문장", source="audio")
        engine.enqueue("화면 문장", source="screen")
        engine.set_source_active("audio", False)
        self.assertEqual([x["source"] for x in list(engine.text_queue.queue)], ["screen"])
        engine.enqueue("정지 중 문장", source="audio")
        self.assertEqual(engine.text_queue.qsize(), 1)
        engine.set_source_active("audio", True)
        engine.enqueue("다시 시작한 문장", source="audio")
        self.assertEqual([x["source"] for x in list(engine.text_queue.queue)],
                         ["screen", "audio"])

    def test_global_dubbing_off_clears_both_queues_and_playback(self):
        engine = self.make_engine()
        engine.enqueue("첫 번째 문장", source="audio")
        engine.playback_queue.put({"source": "screen"})
        engine._current_playing_source = "audio"
        engine.set_enabled(False)
        self.assertTrue(engine.text_queue.empty())
        self.assertTrue(engine.playback_queue.empty())
        self.assertGreater(engine.channel.stops, 0)
        engine.set_enabled(True)
        engine.enqueue("다시 시작한 문장", source="audio")
        self.assertEqual(engine.text_queue.qsize(), 1)

    def test_source_checkbox_off_invalidates_queued_audio(self):
        engine = self.make_engine()
        engine.enqueue("이전 문장", source="audio")
        previous = engine.text_queue.queue[0]
        engine.set_source_enabled("audio", False)
        engine.set_source_enabled("audio", True)
        self.assertFalse(engine._item_is_current(previous))
        self.assertTrue(engine.text_queue.empty())
        engine.enqueue("새 문장", source="audio")
        self.assertEqual(engine.text_queue.qsize(), 1)

    def test_screen_pause_stops_screen_voice_and_keeps_audio_queue(self):
        engine = self.make_engine()
        engine.enqueue("화면의 문장", source="screen")
        engine.enqueue("음성의 문장", source="audio")
        engine._current_playing_source = "screen"
        engine.set_source_active("screen", False)
        self.assertGreater(engine.channel.stops, 0)
        self.assertEqual([x["source"] for x in list(engine.text_queue.queue)], ["audio"])

    def test_enqueue_started_before_pause_cannot_enter_after_resume(self):
        engine = self.make_engine()

        def clean_then_pause(text):
            engine.set_source_active("audio", False)
            engine.set_source_active("audio", True)
            return text

        engine._clean_korean_text = clean_then_pause
        engine.enqueue("늦게 들어온 문장", source="audio")
        self.assertTrue(engine.text_queue.empty())

    def test_inflight_synthesis_is_not_replayed_after_resume(self):
        engine = self.make_engine()
        entered, release = threading.Event(), threading.Event()
        engine.enqueue("합성 중인 문장", source="audio")
        engine.resolve_voice_and_pitch = lambda *args: ("mock", "+0Hz")
        engine.calculate_adaptive_speed = lambda *args: "+0%"

        def synthesize(*args):
            entered.set()
            release.wait(2)
            return b"audio"

        engine._synthesize_audio = synthesize
        worker = threading.Thread(target=engine._synth_loop, daemon=True)
        worker.start()
        self.assertTrue(entered.wait(2))
        engine.set_source_active("audio", False)
        engine.set_source_active("audio", True)
        release.set()
        time.sleep(0.05)
        engine.is_running = False
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(engine.playback_queue.empty())

    def test_pause_during_sound_preparation_prevents_play_after_resume(self):
        engine = self.make_engine()
        entered, release = threading.Event(), threading.Event()
        engine.playback_queue.put({"text": "준비 중인 문장", "orig_text": "original",
            "voice": "mock", "speed": "+0%", "pitch": "+0Hz", "audio_data": b"audio",
            "speaker_display": "", "source": "audio", "region_idx": 0,
            "_generation": 0, "_source_generation": 0})

        def create_sound(data):
            entered.set()
            release.wait(2)
            return object(), 0.01

        engine._create_trimmed_sound = create_sound
        worker = threading.Thread(target=engine._playback_loop, daemon=True)
        worker.start()
        self.assertTrue(entered.wait(2))
        engine.set_source_active("audio", False)
        engine.set_source_active("audio", True)
        release.set()
        time.sleep(0.05)
        engine.is_running = False
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(engine.channel.plays, 0)


if __name__ == "__main__":
    unittest.main()
