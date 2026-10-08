"""Offline behavioral regressions; no model downloads, capture or paid APIs."""
import copy
import os
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from src.i18n import set_ui_language
set_ui_language('ko')
from src.speaker_identifier import SpeakerIdentifier
from src.speaker_tracking import SpeakerAudioWindow, partition_segments, align_transcript

A, B, C = np.eye(3, dtype=np.float32)
UNKNOWN = (0, '화자 미확정', '#AAB2C0')


def wav(seconds, value=0.1):
    return np.full(round(seconds * 16000), value, dtype=np.float32)


def segments(*turns):
    return [SimpleNamespace(start=a, end=b, speaker=label) for a, b, label in turns]


def identifier(embeddings=()):
    obj = SpeakerIdentifier({'speaker_diarization_enabled': False,
                             'speaker_similarity_threshold': .65, 'speaker_max_count': 2})
    obj.is_enabled = True
    obj._ensure_model_loaded = Mock(return_value=True)
    obj.extractor = Mock(dim=3)
    obj.extractor.compute.side_effect = list(embeddings)
    obj.diarizer_loaded = True
    obj.diarizer = Mock()
    return obj


class RecognitionTests(unittest.TestCase):
    def test_short_new_voice_is_pending_not_previous_person(self):
        obj = identifier([A, B])
        self.assertEqual(obj.identify_speaker(wav(1.5))[0], 1)
        self.assertEqual(obj.identify_speaker(wav(.6))[0], 0)
        self.assertEqual(obj.last_decision['state'], 'pending')
        self.assertFalse(obj.suggest_ocr_name('Wrong person'))

    def test_known_short_response_can_match(self):
        obj = identifier([A, B, A])
        ids = [obj.identify_speaker(wav(d))[0] for d in [1.5, 1.5, .6]]
        self.assertEqual(ids, [1, 2, 1])

    def test_limit_does_not_force_foreign_voice(self):
        obj = identifier([A, B, C])
        self.assertEqual([obj.identify_speaker(wav(1.5))[0] for _ in range(3)], [1, 2, 0])

    def test_weak_match_does_not_pollute_reference(self):
        obj = identifier([A, [.70, .7141428, 0]])
        obj.identify_speaker(wav(1.5))
        before = obj.speaker_profiles_data['화자 1']['centroid'].copy()
        self.assertEqual(obj.identify_speaker(wav(1.5))[0], 1)
        np.testing.assert_array_equal(obj.speaker_profiles_data['화자 1']['centroid'], before)
        self.assertEqual(len(obj.speaker_profiles_data['화자 1']['exemplars']), 1)

    def test_ambiguous_match_has_no_forced_winner(self):
        obj = identifier([A, B, [1, 1, 0]])
        obj.identify_speaker(wav(1.5))
        obj.identify_speaker(wav(1.5))
        self.assertEqual(obj.identify_speaker(wav(1.5))[0], 0)

    def test_failed_model_is_unknown(self):
        obj = identifier()
        obj._ensure_model_loaded.return_value = False
        self.assertEqual(obj.segment_audio_by_speaker(wav(1))[0][1][0], 0)

    def test_failed_segmentation_cannot_claim_single_speaker(self):
        obj = identifier([A])
        obj.diarizer_loaded = False
        self.assertEqual(obj.segment_audio_by_speaker(wav(1.5))[0][1][0], 0)
        obj.extractor.compute.assert_not_called()

    def test_segmentation_exception_preserves_every_sample(self):
        obj = identifier()
        obj.diarizer.process.side_effect = RuntimeError('broken')
        audio = wav(1)
        output = obj.segment_audio_by_speaker(audio)
        np.testing.assert_array_equal(output[0][0], audio)
        self.assertEqual(output[0][1][0], 0)

    def test_local_distinct_voices_do_not_collapse(self):
        obj = identifier([A, A])
        obj.diarizer.process.return_value.sort_by_start_time.return_value = segments((0, 1.2, 0), (1.2, 2.4, 1))
        output = obj.segment_audio_by_speaker(wav(2.4))
        self.assertEqual([info[0] for _, info in output], [1, 0])

    def test_short_interjection_and_gaps_are_not_removed(self):
        obj = identifier([A])
        obj.diarizer.process.return_value.sort_by_start_time.return_value = segments((.1, .7, 0), (.8, 1, 1))
        audio = wav(1.2)
        output = obj.segment_audio_by_speaker(audio)
        np.testing.assert_array_equal(np.concatenate([a for a, _ in output]), audio)
        self.assertTrue(any(len(a) == 3200 for a, _ in output))

    def test_overlap_is_not_duplicated_or_used_as_reference(self):
        obj = identifier()
        obj.diarizer.process.return_value.sort_by_start_time.return_value = segments((0, 1, 0), (0, 1, 1))
        output = obj.segment_audio_by_speaker(wav(1))
        self.assertEqual(sum(len(a) for a, _ in output), 16000)
        self.assertEqual(output[0][1][1], '겹친 음성')
        obj.extractor.compute.assert_not_called()

    def test_accumulated_short_same_voice_can_register(self):
        obj = identifier([A, A])
        obj.diarizer.process.return_value.sort_by_start_time.return_value = segments((0, .6, 3))
        first = obj.segment_audio_by_speaker(wav(.6))
        obj.diarizer.process.return_value.sort_by_start_time.return_value = segments((0, 1.2, 7))
        second = obj.segment_audio_by_speaker(wav(.6))
        self.assertEqual(first[0][1][0], 0)
        self.assertEqual(second[0][1][0], 1)
        self.assertEqual(sum(len(a) for a, _ in second), 9600)
        self.assertEqual(len(obj.diarizer.process.call_args.args[0]), 19200)

    def test_local_labels_can_permute_without_global_id_swap(self):
        obj = identifier([A, B, B, A])
        obj.diarizer.process.return_value.sort_by_start_time.return_value = segments((0, 1.2, 0), (1.2, 2.4, 1))
        first = obj.segment_audio_by_speaker(wav(2.4))
        obj.diarizer.process.return_value.sort_by_start_time.return_value = segments((0, 1.2, 8), (1.2, 2.4, 7), (2.4, 3.6, 8))
        # Evidence iteration follows chronological appearance: 8=A, 7=B.
        obj.extractor.compute.side_effect = [A, B]
        second = obj.segment_audio_by_speaker(wav(1.2))
        self.assertEqual([x[1][0] for x in first], [1, 2])
        self.assertEqual([x[1][0] for x in second], [1])

    def test_reset_discards_window_and_profiles(self):
        obj = identifier([A])
        obj.identify_speaker(wav(1.5))
        obj._window.append(wav(1), 16000)
        obj.extractor = None
        obj.reset()
        self.assertFalse(obj.speaker_profiles_data)
        self.assertEqual(len(obj._window.audio), 0)


class TimelineTests(unittest.TestCase):
    def test_partition_conserves_samples_and_marks_overlap(self):
        spans = partition_segments(segments((.1, .6, 0), (.4, .8, 1)), 16000, 16000)
        self.assertEqual(sum(s.end - s.start for s in spans), 16000)
        self.assertEqual([len(s.speakers) for s in spans], [0, 1, 2, 1, 0])

    def test_silence_gap_uses_capture_positions(self):
        window = SpeakerAudioWindow()
        window.append(wav(1), 16000, 0, 'capture')
        audio, offset = window.append(wav(1, .2), 16000, 32000, 'capture')
        self.assertEqual(offset, 32000)
        self.assertTrue(np.all(audio[16000:32000] == 0))

    def test_window_is_bounded_and_does_not_trim_new_audio(self):
        window = SpeakerAudioWindow()
        window.append(wav(4), 16000)
        audio, offset = window.append(wav(3), 16000)
        self.assertEqual((len(audio), offset), (80000, 32000))
        audio, offset = window.append(wav(6), 16000)
        self.assertEqual((len(audio), offset), (96000, 0))

    def test_new_session_or_backward_timestamp_resets_context(self):
        window = SpeakerAudioWindow()
        window.append(wav(2), 16000, 0, 'old')
        _, offset = window.append(wav(1), 16000, 0, 'new')
        self.assertEqual(offset, 0)
        _, offset = window.append(wav(1), 16000, 0, 'new')
        self.assertEqual(offset, 0)


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = (1, 'A', '#fff'), (2, 'B', '#000')
        self.slices = [(wav(1), self.a), (wav(1), self.b), (wav(1), self.a)]

    def test_a_b_a_word_alignment_preserves_order(self):
        words = [dict(word=w, start=t, end=t+.2) for w, t in [('Hello.', .2), ('Yes.', 1.2), ('Good.', 2.2)]]
        result = align_transcript('Hello. Yes. Good.', words, self.slices)
        self.assertEqual([r[1][0] for r in result], [1, 2, 1])
        self.assertEqual(' '.join(r[0] for r in result), 'Hello. Yes. Good.')

    def test_word_straddling_boundary_stays_unknown(self):
        result = align_transcript('Maybe', [dict(word='Maybe', start=.9, end=1.1)], self.slices)
        self.assertEqual(result[0][1][0], 0)

    def test_missing_words_keep_complete_text_unknown(self):
        words = [dict(word='Hello', start=.2, end=.4)]
        result = align_transcript('Hello there, yes.', words, self.slices)
        self.assertEqual(result[0][:2], ('Hello there, yes.', UNKNOWN))

    def test_missing_timing_single_voice_can_use_interval(self):
        result = align_transcript('Hello there.', [], [(wav(2), self.a), (wav(.2, 0), UNKNOWN)])
        self.assertEqual(result[0][1], self.a)

    def test_invalid_timing_preserves_text(self):
        result = align_transcript('Hello', [dict(word='Hello', start=float('nan'), end=1)], self.slices)
        self.assertEqual(result[0][:2], ('Hello', UNKNOWN))


class LifecycleTests(unittest.TestCase):
    def test_segmentation_retries_without_reloading_embedding(self):
        obj = SpeakerIdentifier({'speaker_diarization_enabled': False})
        obj.is_enabled = True
        sherpa = Mock()
        hub = Mock()
        hub.hf_hub_download.return_value = 'cached.onnx'
        sherpa.OfflineSpeakerDiarization.side_effect = [RuntimeError('unavailable'), Mock()]
        with patch.dict('sys.modules', sherpa_onnx=sherpa, huggingface_hub=hub), \
             patch('src.speaker_recognition.time.monotonic', side_effect=[10, 11, 16]):
            self.assertTrue(obj._ensure_model_loaded())
            self.assertFalse(obj.diarizer_loaded)
            self.assertTrue(obj._ensure_model_loaded())
            self.assertEqual(sherpa.OfflineSpeakerDiarization.call_count, 1)
            self.assertTrue(obj._ensure_model_loaded())
            self.assertTrue(obj.diarizer_loaded)
        self.assertEqual(sherpa.SpeakerEmbeddingExtractor.call_count, 1)
        self.assertEqual(sherpa.FastClusteringConfig.call_args.kwargs['threshold'], .5)

    def test_embedding_failure_is_throttled(self):
        obj = SpeakerIdentifier({'speaker_diarization_enabled': False})
        hub = Mock()
        hub.hf_hub_download.side_effect = RuntimeError('offline')
        with patch.dict('sys.modules', sherpa_onnx=Mock(), huggingface_hub=hub), \
             patch('src.speaker_recognition.time.monotonic', side_effect=[10, 11]):
            self.assertFalse(obj._ensure_model_loaded())
        # 1회 시도 시 local_files_only 시도 후 온라인 다운로드 재시도로 총 2회 호출되며,
        # 이후 5초간 스로틀링되어 2번째 _ensure_model_loaded 호출 시에는 hub 호출이 0회여야 함
        self.assertEqual(hub.hf_hub_download.call_count, 2)

    def test_runtime_cluster_change_invalidates_only_diarizer(self):
        obj = identifier()
        obj.model_loaded = True
        cfg = dict(obj.config, speaker_diarization_enabled=True, speaker_cluster_distance_threshold=.35)
        with patch('src.speaker_identifier.threading.Thread'):
            obj.update_config(cfg)
        self.assertFalse(obj.diarizer_loaded)
        self.assertTrue(obj.model_loaded)
        self.assertEqual(obj.cluster_threshold, .35)
        self.assertEqual(obj.threshold, .65)


class PipelineTests(unittest.TestCase):
    def worker(self):
        from src.stt_engine import STTWorker
        from src.config import DEFAULT_CONFIG
        config = copy.deepcopy(DEFAULT_CONFIG)
        config.update(speaker_diarization_enabled=True, dubbing_enabled=True)
        with patch.object(STTWorker, '_load_model'), patch.object(SpeakerIdentifier, '_ensure_model_loaded', return_value=False):
            obj = STTWorker(queue.Queue(), config=config, dubbing_engine=Mock())
        return obj

    def test_unknown_turns_do_not_merge_or_inherit_mute(self):
        obj = self.worker()
        obj.speaker_identifier.set_speaker_muted('화자 0', True)
        obj.speaker_identifier.set_speaker_muted('화자 1', True)
        obj.trans_queue.put(('This is the first response.', 'mock', UNKNOWN))
        obj.trans_queue.put(('This is the second response.', 'mock', UNKNOWN))
        seen, displayed = [], []
        def translate(text):
            seen.append(text)
            if obj.trans_queue.empty():
                obj.running = False
            return '번역', 'mock'
        obj.translator.translate = translate
        obj.subtitle_callback = lambda *args: displayed.append(args)
        obj.running = True
        obj._translation_loop()
        self.assertEqual(len(seen), 2)
        self.assertTrue(all('화자 미확정' in row[0] and '화자 0' not in row[0] for row in displayed))
        self.assertTrue(all(not c.kwargs['speaker_confirmed'] for c in obj.dubbing_engine.enqueue.call_args_list))

    def test_asr_runs_once_on_whole_audio_then_splits_text(self):
        obj = self.worker()
        audio = wav(2)
        def transcribe(samples):
            np.testing.assert_array_equal(samples, audio)
            obj._last_transcript_words = [dict(word='Hello.', start=.2, end=.6), dict(word='Yes.', start=1.2, end=1.5)]
            return 'Hello. Yes.', 'mock'
        obj._transcribe_audio_chunk = Mock(side_effect=transcribe)
        output = obj._transcribe_with_speakers(audio, [(audio[:16000], (1, 'A', '#fff')), (audio[16000:], (2, 'B', '#000'))])
        self.assertEqual([row[2][0] for row in output], [1, 2])
        obj._transcribe_audio_chunk.assert_called_once()

    def test_groq_requests_word_timestamps_and_keeps_them(self):
        obj = self.worker()
        response = Mock(status_code=200)
        response.json.return_value = dict(text='Hello.', words=[dict(word='Hello.', start=0, end=.4)])
        with patch('src.stt_engine.requests.post', return_value=response) as post:
            result = obj._transcribe_groq(wav(.5), 'dummy-not-a-real-key')
        self.assertEqual(result[0], 'Hello.')
        self.assertEqual(post.call_args.kwargs['data']['timestamp_granularities[]'], 'word')
        self.assertEqual(len(obj._last_transcript_words), 1)

    def test_unknown_dubbing_uses_default_voice_without_gender_guess(self):
        from src.dubbing_engine import DubbingEngine, VOICE_MALE_DEFAULT
        obj = DubbingEngine.__new__(DubbingEngine)
        obj.config = {}
        self.assertEqual(obj.resolve_voice_and_pitch('', '', 'She is the queen.'), (VOICE_MALE_DEFAULT, '+0Hz'))


class ExternalSpeakerCapTests(unittest.TestCase):
    def test_deepgram_speakers_stop_at_max_count(self):
        obj = identifier()
        obj.max_speakers = 3
        confirmed = [obj.map_external_speaker(i, confirmed=True) for i in range(7)]
        self.assertEqual([info[0] for info in confirmed[:3]], [1, 2, 3])
        self.assertEqual([info[1] for info in confirmed[:3]], ['화자 1', '화자 2', '화자 3'])
        self.assertTrue(all(info[0] == 0 for info in confirmed[3:]))
        self.assertEqual(
            [s['raw_name'] for s in obj.get_all_known_speakers()],
            ['화자 1', '화자 2', '화자 3'],
        )

    def test_lowering_max_prunes_already_registered_speakers(self):
        obj = identifier()
        obj.max_speakers = 8
        for i in range(7):
            obj.map_external_speaker(i, confirmed=True)
        self.assertEqual(len(obj.get_all_known_speakers()), 7)
        obj.apply_max_speakers(3)
        self.assertEqual(
            [s['raw_name'] for s in obj.get_all_known_speakers()],
            ['화자 1', '화자 2', '화자 3'],
        )
        overflow = obj.map_external_speaker(6, confirmed=True)
        self.assertEqual(overflow[0], 0)
        self.assertNotIn('화자 7', [s['raw_name'] for s in obj.get_all_known_speakers()])

    def test_stt_maps_deepgram_overflow_to_unknown(self):
        from src.stt_engine import STTWorker
        worker = STTWorker.__new__(STTWorker)
        worker.config = {'speaker_diarization_enabled': True, 'speaker_max_count': 3}
        worker.speaker_identifier = identifier()
        worker.speaker_identifier.max_speakers = 3
        self.assertEqual(worker._map_deepgram_speaker(0, confirmed=True)[1], '화자 1')
        self.assertEqual(worker._map_deepgram_speaker(1, confirmed=True)[1], '화자 2')
        self.assertEqual(worker._map_deepgram_speaker(2, confirmed=True)[1], '화자 3')
        self.assertEqual(worker._map_deepgram_speaker(3, confirmed=True)[0], 0)
        self.assertEqual(len(worker.speaker_identifier.get_all_known_speakers()), 3)


if __name__ == '__main__':
    unittest.main()
