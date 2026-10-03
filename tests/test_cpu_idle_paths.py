"""대기 상태에서도 CPU를 붙잡던 루프가 장치를 열거나 화면을 훑지 않는지 확인한다."""
import threading
import time
import unittest
from unittest.mock import Mock, patch

from src.audio_capture import AudioLoopbackCapture
from src.outline_effect import outline_stamp_offsets
from src.process_volume import ducking_poll_interval
from src.screen_ocr_worker import ScreenOCRWorker
import src.youtube_helper as youtube_helper


class CpuIdlePathTests(unittest.TestCase):
    def test_paused_audio_capture_does_not_open_device(self):
        capture = AudioLoopbackCapture.__new__(AudioLoopbackCapture)
        capture.paused = True
        capture.running = False
        capture._device_switch_requested = False
        capture.capture_device = "process:whale.exe"
        capture.active_capture_mode = "inactive"
        capture.active_capture_device_id = None
        capture.passthrough_thread = Mock()
        opened = []
        capture._run_process_capture = lambda app: opened.append(app)
        capture._run_device_capture = lambda: opened.append("device")

        def stop_soon():
            time.sleep(0.35)
            capture.running = False

        threading.Thread(target=stop_soon, daemon=True).start()
        capture.run()
        self.assertEqual(opened, [])
        capture.passthrough_thread.start.assert_called_once()

    def test_ducking_poll_slows_down_when_volume_is_stable(self):
        self.assertEqual(ducking_poll_interval(False), 0.35)
        self.assertEqual(ducking_poll_interval(True), 0.025)

    def test_outline_stamps_stay_on_eight_directions(self):
        sharp, shadow = outline_stamp_offsets(1, 4)
        self.assertLessEqual(len(sharp), 8)
        self.assertLessEqual(len(shadow), 16)
        self.assertIn((1, 1), sharp)
        self.assertNotIn((2, 0), sharp)

    def test_screen_ocr_idle_does_not_capture(self):
        worker = ScreenOCRWorker(config={"screen_translate_enabled": False}, translator=Mock())
        worker.is_running = True
        worker.is_paused = True
        worker._capture_cycle = Mock()

        def stop_after_sleep(_seconds):
            worker.is_running = False

        with patch("src.screen_ocr_worker.time.sleep", side_effect=stop_after_sleep) as sleep:
            worker.run()
        worker._capture_cycle.assert_not_called()
        sleep.assert_called_once_with(0.5)

    def test_youtube_scan_is_single_flight_and_cached_by_title(self):
        youtube_helper._youtube_title_cache["titles"] = None
        youtube_helper._youtube_title_cache["url"] = None
        if youtube_helper._youtube_scan_lock.locked():
            youtube_helper._youtube_scan_lock.release()

        entered = threading.Event()
        release = threading.Event()
        calls = []

        def slow_read(_hwnds):
            calls.append(1)
            entered.set()
            release.wait(2)
            return "https://www.youtube.com/watch?v=abcdefghijk"

        windows = [(1, "Talk - YouTube - Whale")]
        with patch("src.youtube_helper._collect_youtube_windows", return_value=windows), \
             patch("src.youtube_helper._read_youtube_url_from_windows", side_effect=slow_read):
            first = threading.Thread(
                target=lambda: youtube_helper.find_youtube_url_from_browser(timeout=2.0),
                daemon=True,
            )
            first.start()
            self.assertTrue(entered.wait(1.0))
            cached_during_scan = youtube_helper.find_youtube_url_from_browser(timeout=0.2)
            self.assertIsNone(cached_during_scan)
            self.assertEqual(len(calls), 1)
            release.set()
            first.join(2.0)

            again = youtube_helper.find_youtube_url_from_browser(timeout=0.2)
        self.assertEqual(again, "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
