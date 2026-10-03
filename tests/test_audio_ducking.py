import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import time
import unittest
from unittest.mock import MagicMock
from src.process_volume import AudioDuckingManager


class MockDubbingEngine:
    def __init__(self):
        self._enabled = True
        self._speaking = False
        self._current_synthesizing_item = None
        self.playback_queue = MagicMock()
        self.playback_queue.qsize.return_value = 0
        self.text_queue = MagicMock()
        self.text_queue.qsize.return_value = 0

    def is_enabled(self):
        return self._enabled

    def is_speaking(self, grace_period=0.4):
        return self._speaking


class TestAudioDuckingManager(unittest.TestCase):
    def setUp(self):
        self.mock_engine = MockDubbingEngine()
        self.config = {
            "original_volume": 80,
            "audio_ducking_volume": 20,
            "audio_ducking_enabled": True,
            "audio_capture_device": "default",
        }
        self.mgr = AudioDuckingManager(self.mock_engine, self.config, "test_app.exe")

    def tearDown(self):
        self.mgr.stop()

    def test_pipeline_active_detection(self):
        # 1. Initially inactive
        self.assertFalse(self.mgr._is_pipeline_active())

        # 2. Speaking active
        self.mock_engine._speaking = True
        self.assertTrue(self.mgr._is_pipeline_active())
        self.mock_engine._speaking = False

        # 3. Playback queue has items
        self.mock_engine.playback_queue.qsize.return_value = 1
        self.assertTrue(self.mgr._is_pipeline_active())
        self.mock_engine.playback_queue.qsize.return_value = 0

        # 4. Synthesizer is synthesizing
        self.mock_engine._current_synthesizing_item = {"text": "hello"}
        self.assertTrue(self.mgr._is_pipeline_active())
        self.mock_engine._current_synthesizing_item = None

        # 5. Text queue has items
        self.mock_engine.text_queue.qsize.return_value = 2
        self.assertTrue(self.mgr._is_pipeline_active())
        self.mock_engine.text_queue.qsize.return_value = 0

        # 6. Back to inactive
        self.assertFalse(self.mgr._is_pipeline_active())

    def test_ducking_volume_boundaries(self):
        self.assertEqual(self.mgr.original_volume, 0.8)
        self.assertEqual(self.mgr.ducking_volume, 0.2)

        # Update ducking volume
        self.mgr.set_ducking_volume(35)
        self.assertAlmostEqual(self.mgr.ducking_volume, 0.35)

        # Update original volume
        self.mgr.set_original_volume(60)
        self.assertAlmostEqual(self.mgr.original_volume, 0.60)

    def test_fade_towards_interpolates_smoothly(self):
        self.mgr.current_volume = 0.8
        # Step down smoothly towards 0.2
        self.mgr._fade_towards(0.2, step=0.1)
        self.assertAlmostEqual(self.mgr.current_volume, 0.7, places=2)

        self.mgr._fade_towards(0.2, step=0.1)
        self.assertAlmostEqual(self.mgr.current_volume, 0.6, places=2)

        # Step up smoothly towards 0.8
        self.mgr._fade_towards(0.8, step=0.05)
        self.assertAlmostEqual(self.mgr.current_volume, 0.65, places=2)

    def test_reset_to_original(self):
        self.mgr.is_ducked = True
        self.mgr.current_volume = 0.2
        self.mgr._last_active_time = time.time()

        self.mgr.reset_to_original()

        self.assertFalse(self.mgr.is_ducked)
        self.assertEqual(self.mgr.current_volume, self.mgr.original_volume)
        self.assertEqual(self.mgr._last_active_time, 0.0)

    def test_ducking_volume_independent_of_original_volume(self):
        # When ducked, target is ducking_volume directly (based on 100% scale)
        self.mgr.is_ducked = True
        self.mgr.set_original_volume(80)
        self.mgr.set_ducking_volume(25)
        self.assertAlmostEqual(self.mgr.current_volume, 0.25)

        # Changing original volume while ducked should keep ducking volume intact
        self.mgr.set_original_volume(50)
        self.assertAlmostEqual(self.mgr.current_volume, 0.25)

        # If original volume is 0 (muted), target should be 0.0
        self.mgr.set_original_volume(0)
        self.assertAlmostEqual(self.mgr.current_volume, 0.0)

    def test_ducking_toggle_disables_and_restores(self):
        self.mgr.is_ducked = True
        self.mgr.current_volume = 0.2
        self.mgr.set_ducking_enabled(False)

        self.assertFalse(self.mgr.ducking_enabled)
        self.assertFalse(self.mgr.is_ducked)
        self.assertEqual(self.mgr.current_volume, self.mgr.original_volume)


if __name__ == "__main__":
    unittest.main()
