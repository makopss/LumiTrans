"""Behavioral checks for the local/Groq and Deepgram STT routing boundary."""
import queue
import unittest
from unittest.mock import Mock, patch

import numpy as np

from src.audio_chunk import CapturedAudio
from src.stt_engine import STTWorker


class _OnePacketQueue:
    def __init__(self, packet):
        self.packet = packet
        self.worker = None

    def get(self, timeout=None):
        if self.packet is not None:
            packet, self.packet = self.packet, None
            return packet
        self.worker.running = False
        raise queue.Empty


class _RecordingQueue(queue.Queue):
    def __init__(self, worker):
        super().__init__()
        self.worker = worker
        self.was_running_when_queued = []

    def put(self, item, *args, **kwargs):
        self.was_running_when_queued.append(self.worker.running)
        return super().put(item, *args, **kwargs)


class DecouplingVerification(unittest.TestCase):
    def _run_one_chunk(self, provider, text, speech_end=True):
        packet = CapturedAudio(np.ones(1600, dtype=np.float32), True,
                               speech_end=speech_end, stt_provider=provider)
        audio_queue = _OnePacketQueue(packet)
        with patch.object(STTWorker, '_load_model'), patch.object(STTWorker, '_init_deepgram_streamer'):
            worker = STTWorker(audio_queue, config={
                'stt_provider': provider, 'sentence_mode': True,
                'translation_trace_enabled': False})
        audio_queue.worker = worker
        worker.trans_worker = Mock()
        worker.trans_queue = _RecordingQueue(worker)
        worker._transcribe_with_speakers = Mock(return_value=[
            (text, 'Groq (Turbo)' if provider == 'groq' else 'CPU', None, 0.5)])
        worker._segmenter.accept = Mock(side_effect=AssertionError(
            'Local/Groq must bypass SpeechSegmenter'))
        worker.run()
        return worker

    def test_short_completed_local_and_groq_chunks_queue_before_shutdown(self):
        for provider in ('local', 'groq'):
            for utterance in ('Good morning.', 'Yes.'):
                with self.subTest(provider=provider, utterance=utterance):
                    worker = self._run_one_chunk(provider, utterance)
                    self.assertEqual(worker.trans_queue.qsize(), 1)
                    self.assertEqual(worker.trans_queue.was_running_when_queued, [True])
                    self.assertIsNone(worker.trans_queue.get_nowait()[3])
                    worker._segmenter.accept.assert_not_called()

    def test_thank_you_example_is_filtered_as_a_hallucination(self):
        for provider in ('local', 'groq'):
            with self.subTest(provider=provider):
                worker = self._run_one_chunk(provider, 'Thank you.')
                self.assertTrue(worker.trans_queue.empty())

    def test_dangling_speech_end_is_not_an_immediate_flush(self):
        worker = self._run_one_chunk('local', 'I want to')
        # It is released only by the run-loop shutdown fallback in this fixture.
        self.assertEqual(worker.trans_queue.was_running_when_queued, [False])

    def test_deepgram_event_queues_a_segment_object(self):
        with patch.object(STTWorker, '_load_model'), patch.object(STTWorker, '_init_deepgram_streamer'):
            worker = STTWorker(queue.Queue(), config={
                'stt_provider': 'deepgram', 'translation_trace_enabled': False})
        worker._speech_events.put({
            'type': 'Results', 'session_id': 'verify', 'is_final': True,
            'speech_final': True, 'start': 0.0, 'duration': 0.4,
            'channel': {'alternatives': [{'transcript': 'We should go now.',
                'words': [{'word': word.rstrip('.'), 'punctuated_word': word,
                           'start': i * .1, 'end': (i + 1) * .1}
                          for i, word in enumerate('We should go now.'.split())]}]}})
        worker._consume_speech_events()
        self.assertEqual(worker.trans_queue.qsize(), 1)
        self.assertIsNotNone(worker.trans_queue.get_nowait()[3])


if __name__ == '__main__':
    unittest.main()
