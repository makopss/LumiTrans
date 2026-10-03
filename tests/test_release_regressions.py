"""Offline regression tests for release review findings. No model/audio side effects."""
import ast
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

from src.translator import RealtimeTranslator
from src.stt_engine import STTWorker
from src.dubbing_engine import DubbingEngine
from src.audio_capture import AudioLoopbackCapture
from src.speaker_identifier import SpeakerIdentifier
from src.screen_overlay_manager import ScreenOverlayManager
from src.screen_ocr_worker import ScreenOCRWorker
from src.config import DEFAULT_CONFIG


class ReleaseContracts(unittest.TestCase):
    def setUp(self):
        patches = [patch.object(SpeakerIdentifier, '_ensure_model_loaded', return_value=False),
                   patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))]
        for guard in patches:
            guard.start()
            self.addCleanup(guard.stop)

    def make_ocr_worker(self):
        worker = ScreenOCRWorker(config={'screen_translate_enabled': True,
            'screen_rois': [[0, 0, 100, 100]], 'screen_ocr_preprocess': False}, translator=Mock())
        worker.is_paused = False
        worker.translator.translate.return_value = ('번역됨', 'mock')
        worker._check_and_link_speaker_name = Mock()
        return worker

    def test_roi_replacement_with_same_index_discards_result(self):
        worker = self.make_ocr_worker()
        token = worker._begin_request(worker._regions(), 0)
        received = []
        worker.subtitle_signal.connect(lambda *args: received.append(args))
        worker.config['screen_rois'] = [[200, 0, 100, 100]]
        worker._deliver_result((token, 'old', '오래된 번역', 'mock'))
        self.assertEqual(received, [])

    def test_roi_remove_readd_invalidates_same_coordinates(self):
        worker = self.make_ocr_worker()
        token = worker._begin_request(worker._regions(), 0)
        worker.invalidate_regions()
        self.assertFalse(worker._is_current(token))

    def test_pause_invalidates_queued_result_but_allows_instant(self):
        worker = self.make_ocr_worker()
        token = worker._begin_request(worker._regions(), 0)
        worker.set_paused(True)
        self.assertFalse(worker._is_current(token))
        manual = worker._begin_request(worker._regions(), 0, instant=True)
        self.assertTrue(worker._is_current(manual))

    def test_valid_roi_result_reaches_subtitle_and_dubbing(self):
        worker = self.make_ocr_worker()
        worker.config.update(dubbing_enabled=True, dubbing_source_screen=True)
        worker.dubbing_engine = Mock()
        received = []
        worker.subtitle_signal.connect(lambda *args: received.append(args))
        token = worker._begin_request(worker._regions(), 0)
        worker._deliver_result((token, 'Alice: Hello.', '앨리스: 안녕하세요.', 'mock'))
        self.assertEqual(len(received), 1)
        worker.dubbing_engine.enqueue.assert_called_once()

    def test_stale_roi_never_enters_dubbing_queue(self):
        worker = self.make_ocr_worker()
        worker.config.update(dubbing_enabled=True, dubbing_source_screen=True)
        worker.dubbing_engine = Mock()
        token = worker._begin_request(worker._regions(), 0)
        worker.invalidate_regions()
        worker._deliver_result((token, 'Hello.', '안녕하세요.', 'mock'))
        worker.dubbing_engine.enqueue.assert_not_called()

    def test_static_ocr_retries_after_translation_failure(self):
        worker = self.make_ocr_worker()
        text = 'Please open the door.'
        worker._get_ocr = lambda: lambda _: ([([[0, 0]], text, 1.0)], None)
        worker.translator.translate.side_effect = [(text, '원문 유지'), ('문을 열어주세요.', 'Google')]
        now = [10.0]
        captures = []
        def capture(*args, **kwargs):
            captures.append(kwargs['force_full'])
            return object(), None, kwargs['force_full']
        with patch('src.screen_ocr_worker.time.monotonic', side_effect=lambda: now[0]), \
             patch('src.screen_ocr_worker.smart_capture_screen_area', side_effect=capture), \
             patch('src.screen_ocr_worker.clean_ocr_english_text', side_effect=lambda s: s):
            worker._capture_cycle()
            self.assertEqual(worker.roi_states[0]['last_text'], '')
            now[0] = 10.5
            worker._capture_cycle()
            self.assertEqual(worker.translator.translate.call_count, 1)
            now[0] = 12.1
            worker._capture_cycle()
        self.assertEqual(worker.translator.translate.call_count, 2)
        self.assertEqual(worker.roi_states[0]['last_text'], text)
        self.assertEqual(captures, [True, False, True])

    def test_ocr_negation_change_is_not_deduplicated(self):
        worker = self.make_ocr_worker()
        worker.roi_states[0] = {'last_thumb': None, 'last_text': 'You can enter the castle.', 'last_check_time': 0}
        text = 'You cannot enter the castle.'
        worker._get_ocr = lambda: lambda _: ([([[0, 0]], text, 1.0)], None)
        with patch('src.screen_ocr_worker.smart_capture_screen_area', return_value=(object(), None, True)), \
             patch('src.screen_ocr_worker.clean_ocr_english_text', side_effect=lambda s: s):
            worker._capture_cycle()
        worker.translator.translate.assert_called_once_with(text)

    def test_device_isolation_requires_live_distinct_endpoints(self):
        cap = AudioLoopbackCapture.__new__(AudioLoopbackCapture)
        cap.running, cap.paused = True, False
        cap.active_capture_mode = 'device'
        cap.active_capture_device_id = 'endpoint-a'
        cap.dubbing_engine = SimpleNamespace(active_output_device_id='endpoint-a', _mixer_initialized=True)
        self.assertFalse(cap.is_channels_separated())
        cap.dubbing_engine.active_output_device_id = 'endpoint-b'
        self.assertTrue(cap.is_channels_separated())
        cap.dubbing_engine._mixer_initialized = False
        self.assertFalse(cap.is_channels_separated())

    def test_capture_metadata_survives_later_device_switch(self):
        from src.audio_chunk import CapturedAudio
        cap = AudioLoopbackCapture.__new__(AudioLoopbackCapture)
        cap.audio_queue = queue.Queue()
        cap.running, cap.paused = True, False
        cap.active_capture_mode = 'device'
        cap._enqueue_audio('original-samples')
        cap.active_capture_mode = 'process'
        item = cap.audio_queue.get_nowait()
        self.assertIsInstance(item, CapturedAudio)
        self.assertFalse(item.channels_separated)
        self.assertTrue(cap.is_channels_separated())

    def test_legacy_alias_survives_ocr_after_reload(self):
        cfg = {'speaker_diarization_enabled': True, 'speaker_aliases': {'화자 1': 'Alice'}}
        speaker = SpeakerIdentifier(cfg)
        speaker.last_active_speaker, speaker.last_active_time = '화자 1', time.time()
        self.assertFalse(speaker.suggest_ocr_name('Bob'))
        self.assertEqual(speaker.get_display_name('화자 1'), 'Alice')

    def test_automatic_alias_remains_editable_and_manual_override_is_persisted(self):
        cfg = {'speaker_diarization_enabled': True}
        speaker = SpeakerIdentifier(cfg)
        speaker.last_active_speaker, speaker.last_active_time = '화자 1', time.time()
        self.assertTrue(speaker.suggest_ocr_name('Alice'))
        self.assertTrue(speaker.suggest_ocr_name('Bob'))
        speaker.set_speaker_alias('화자 1', 'Manual')
        reloaded = SpeakerIdentifier(cfg)
        reloaded.last_active_speaker, reloaded.last_active_time = '화자 1', time.time()
        self.assertFalse(reloaded.suggest_ocr_name('Carol'))

    def test_model_device_switch_invalidates_loaded_model_and_cache(self):
        cfg = {'translation_engine': 'exaone', 'device': 'cuda'}
        translator = RealtimeTranslator(cfg)
        translator._exaone_llm = object()
        translator.cache['old'] = ('번역', 'mock')
        cfg['device'] = 'cpu'
        with patch.object(translator, 'preload_engine'):
            translator.update_config(cfg)
        self.assertIsNone(getattr(translator, '_exaone_llm', None))
        self.assertEqual(translator.cache, {})

    def test_preload_waits_for_inference_lock_and_ignores_obsolete_engine(self):
        translator = RealtimeTranslator({'translation_engine': 'exaone'})
        translator._get_exaone = Mock()
        started = threading.Event()
        def preload():
            started.set()
            translator.preload_engine('exaone')
        with translator._lock:
            thread = threading.Thread(target=preload)
            thread.start()
            self.assertTrue(started.wait(1))
            translator._get_exaone.assert_not_called()
            translator.config['translation_engine'] = 'google'
        thread.join(2)
        self.assertFalse(thread.is_alive())
        translator._get_exaone.assert_not_called()

    def test_temporary_fallback_retries_preferred_engine_after_ttl(self):
        translator = RealtimeTranslator({'translation_engine': 'deepl', 'deepl_api_key': 'test-placeholder'})
        translator._translate_deepl = Mock(side_effect=['', '딥엘 복구'])
        translator._translate_google_mobile = Mock(return_value='구글 임시 번역')
        translator._post_process_korean = lambda t: t
        with patch('src.translator.time.monotonic', return_value=10):
            self.assertIn('폴백', translator.translate('Open the door.')[1])
        with patch('src.translator.time.monotonic', return_value=11):
            translator.translate('Open the door.')
        self.assertEqual(translator._translate_deepl.call_count, 1)
        with patch('src.translator.time.monotonic', return_value=26):
            self.assertEqual(translator.translate('Open the door.'), ('딥엘 복구', 'DeepL'))

    def test_queue_lookahead_preserves_order_and_waits_for_matching_head(self):
        from src.queue_utils import take_matching
        q = queue.Queue()
        q.put('Bob')
        q.put('Alice')
        self.assertIsNone(take_matching(q, lambda name: name == 'Alice'))
        self.assertEqual(q.get_nowait(), 'Bob')
        self.assertEqual(take_matching(q, lambda name: name == 'Alice'), 'Alice')
        thread = threading.Thread(target=lambda: (time.sleep(.02), q.put('Alice')))
        thread.start()
        self.assertEqual(take_matching(q, lambda name: name == 'Alice', .5), 'Alice')
        thread.join()

    def test_short_followup_cannot_merge_a_different_speaker(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg['speaker_diarization_enabled'] = True
        with patch.object(STTWorker, '_load_model'):
            worker = STTWorker(queue.Queue(), config=cfg)
        worker.trans_queue.put(('Wait please', 'CPU', (1, 'Alice', '#fff')))
        followup = threading.Thread(target=lambda: (time.sleep(.03), worker.trans_queue.put(
            ('I must leave right now.', 'CPU', (2, 'Bob', '#fff')))))
        texts = []
        def translate(text):
            texts.append(text)
            if len(texts) == 2:
                worker.running = False
            return '번역', 'mock'
        worker.translator.translate = translate
        worker.running = True
        followup.start()
        worker._translation_loop()
        followup.join()
        self.assertEqual(texts, ['Wait please', 'I must leave right now.'])

    def test_alias_change_does_not_bypass_queued_speaker_mute(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg['speaker_diarization_enabled'] = True
        with patch.object(STTWorker, '_load_model'):
            worker = STTWorker(queue.Queue(), config=cfg)
        speaker = worker.speaker_identifier
        speaker.set_speaker_alias('화자 1', 'New Alice')
        speaker.set_speaker_muted('화자 1', True)
        worker.trans_queue.put(('This old alias is muted.', 'CPU', (1, 'Old Alice', '#fff')))
        worker.trans_queue.put(('This other person is heard.', 'CPU', (2, 'Bob', '#fff')))
        texts = []
        def translate(text):
            texts.append(text)
            worker.running = False
            return '번역', 'mock'
        worker.translator.translate = translate
        worker.running = True
        worker._translation_loop()
        self.assertEqual(texts, ['This other person is heard.'])

    def test_exaone_7b_is_released_on_cloud_switch(self):
        cfg = {'translation_engine': 'exaone7b', 'selected_llm_model': 'exaone-3.5-7.8b'}
        translator = RealtimeTranslator(cfg)
        translator._exaone7b_llm = object()
        cfg['translation_engine'] = 'google'
        translator.update_config(cfg)
        self.assertIsNone(getattr(translator, '_exaone7b_llm', None))

    def test_exaone_size_switch_releases_previous_weights(self):
        cfg = {'translation_engine': 'exaone', 'selected_llm_model': 'exaone-3.5-2.4b'}
        translator = RealtimeTranslator(cfg)
        translator._exaone_llm = object()
        cfg['selected_llm_model'] = 'exaone-3.5-7.8b'
        with patch.object(translator, 'preload_engine'):
            translator.update_config(cfg)
        self.assertIsNone(getattr(translator, '_exaone_llm', None))

    def test_all_configured_engines_keep_their_dispatch(self):
        cases = [('google', '_translate_google_mobile'), ('deepl', '_translate_deepl'),
                 ('gemini', '_translate_gemini'), ('groq', '_translate_groq'),
                 ('exaone', '_translate_exaone'),
                 ('exaone7b', '_translate_exaone'), ('gemma', '_translate_gemma'),
                 ('ollama:exaone3.5:7.8b', '_translate_ollama')]
        for engine, method in cases:
            with self.subTest(engine=engine):
                translator = RealtimeTranslator({'translation_engine': engine,
                    'deepl_api_key': 'placeholder', 'gemini_api_key': 'placeholder',
                    'groq_api_key': 'placeholder'})
                mock = Mock(return_value='정상 번역')
                setattr(translator, method, mock)
                translator._post_process_korean = lambda t: t
                result, used = translator.translate('Please open the door.')
                self.assertEqual(result, '정상 번역')
                self.assertNotEqual(used, '원문 유지')
                mock.assert_called_once()
                if engine == 'exaone7b':
                    self.assertEqual(mock.call_args.kwargs['model_id'], 'exaone-3.5-7.8b')

    def test_pending_ocr_is_invalid_after_model_switch(self):
        worker = self.make_ocr_worker()
        token = worker._begin_request(worker._regions(), 0)
        worker.config['selected_llm_model'] = 'exaone-3.5-7.8b'
        self.assertFalse(worker._is_current(token))

    def test_shared_ui_config_cannot_mutate_active_inference_snapshot(self):
        cfg = {'translation_engine': 'google', 'device': 'cuda'}
        translator = RealtimeTranslator(cfg)
        cfg['device'] = 'cpu'
        self.assertEqual(translator.config['device'], 'cuda')
        translator._translate_google_mobile = Mock(return_value='번역됨')
        translator._post_process_korean = lambda t: t
        translator.translate('A useful sentence.')
        self.assertEqual(translator.config['device'], 'cpu')

    def test_screen_stop_waits_until_worker_has_finished(self):
        worker = self.make_ocr_worker()
        entered = threading.Event()
        release = threading.Event()
        worker._capture_cycle = lambda: (entered.set(), release.wait(3))
        worker.start()
        self.assertTrue(entered.wait(1))
        timer = threading.Timer(1.1, release.set)
        timer.start()
        try:
            worker.stop()
            self.assertFalse(worker.isRunning())
        finally:
            release.set()
            worker.wait(3000)
            timer.join()

    def test_separate_speakers_remain_separate_in_translation(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg['speaker_diarization_enabled'] = True
        with patch.object(STTWorker, '_load_model'):
            worker = STTWorker(queue.Queue(), config=cfg)
        worker.trans_queue.put(('I will open the door.', 'CPU', (1, 'Alice', '#ffffff')))
        worker.trans_queue.put(('Please wait for me here.', 'CPU', (2, 'Bob', '#ffffff')))
        translated_inputs = []
        def translate(text):
            translated_inputs.append(text)
            if worker.trans_queue.empty():
                worker.running = False
            return '번역 결과', 'mock'
        worker.translator.translate = translate
        worker.running = True
        worker._translation_loop()
        self.assertEqual(translated_inputs, ['I will open the door.', 'Please wait for me here.'])

    def test_dubbing_preserves_a_b_a_order(self):
        engine = DubbingEngine.__new__(DubbingEngine)
        engine.config = {'dubbing_enabled': True, 'dubbing_source_audio': True}
        engine.is_running = True
        engine.text_queue = queue.Queue()
        engine.playback_queue = queue.Queue()
        engine._is_playing = False
        for speaker, text in [('Alice', '첫 번째 대사.'), ('Bob', '두 번째 대사.'), ('Alice', '세 번째 대사.')]:
            engine.text_queue.put(dict(text=text, speaker_name=speaker,
                speaker_display=speaker, orig_text=text, source='audio'))
        engine.resolve_voice_and_pitch = lambda *args: ('mock', '+0Hz')
        engine.calculate_adaptive_speed = lambda *args: '+0%'
        synthesized = []
        def synthesize(text, *args):
            synthesized.append(text)
            if engine.text_queue.empty():
                engine.is_running = False
            return b'mocked-audio'
        engine._synthesize_audio = synthesize
        engine._synth_loop()
        self.assertEqual(synthesized, ['첫 번째 대사.', '두 번째 대사.', '세 번째 대사.'])

    def test_failed_translation_retries_after_recovery(self):
        translator = RealtimeTranslator({'translation_engine': 'google'})
        translator._translate_google_mobile = Mock(side_effect=['', '복구된 번역'])
        translator._translate_mymemory = Mock(return_value='')
        translator._post_process_korean = lambda text: text
        self.assertEqual(translator.translate('Please open the door.')[1], '원문 유지')
        result = translator.translate('Please open the door.')
        self.assertEqual(result, ('복구된 번역', 'Google'))

    def test_ui_engine_switch_unloads_local_model(self):
        cfg = {'translation_engine': 'exaone'}
        translator = RealtimeTranslator(cfg)
        translator._exaone_llm = object()
        # Same shared-config mutation used by ControlPanel.set_engine_by_key.
        cfg['translation_engine'] = 'google'
        translator.update_config(cfg)
        self.assertIsNone(getattr(translator, '_exaone_llm', None))

    def test_ocr_does_not_overwrite_manual_alias(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg['speaker_diarization_enabled'] = True
        speaker = SpeakerIdentifier(cfg)
        speaker.set_speaker_alias('화자 1', 'Manual Alice')
        speaker.last_active_speaker = '화자 1'
        speaker.last_active_time = time.time()
        speaker.suggest_ocr_name('Screen Bob')
        self.assertEqual(speaker.get_display_name('화자 1'), 'Manual Alice')

    def test_removed_roi_result_is_discarded(self):
        overlay = Mock()
        manager = SimpleNamespace(overlays=[overlay], config={'screen_rois': [[0, 0, 100, 100]]})
        ScreenOverlayManager.display_subtitle(manager, 'old region', '이전 영역', 'mock', 1)
        overlay.display_subtitle.assert_not_called()

    def test_missing_process_capture_does_not_claim_isolation(self):
        capture = AudioLoopbackCapture.__new__(AudioLoopbackCapture)
        capture.config = {'audio_capture_device': 'process:game.exe', 'dubbing_output_device': 'default'}
        observed_isolation = []
        capture._run_device_capture = lambda: observed_isolation.append(capture.is_channels_separated())
        with patch.dict(sys.modules, {'proctap': None}):
            capture._run_process_capture('game.exe')
        self.assertNotIn(True, observed_isolation)

    def test_ocr_number_change_is_translated(self):
        worker = ScreenOCRWorker(config={
            'screen_translate_enabled': True,
            'screen_rois': [[0, 0, 100, 100]],
            'screen_ocr_preprocess': False,
        }, translator=Mock())
        worker.is_paused = False
        worker.is_running = True
        worker.roi_states[0] = {'last_thumb': None, 'last_text': 'You need 100 gold to enter.', 'last_check_time': 0}
        def ocr(_):
            return [([[0, 0], [100, 0], [100, 20], [0, 20]], 'You need 900 gold to enter.', 1.0)], None
        worker._get_ocr = lambda: ocr
        worker._check_and_link_speaker_name = lambda text: None
        worker.translator.translate.return_value = ('입장에 900골드가 필요합니다.', 'mock')
        with patch('src.screen_ocr_worker.smart_capture_screen_area', return_value=(object(), None, True)), \
             patch('src.screen_ocr_worker.clean_ocr_english_text', side_effect=lambda text: text), \
             patch('src.screen_ocr_worker.threading.Thread'), \
             patch('src.screen_ocr_worker.time.sleep'):
            worker._capture_cycle()
        worker.translator.translate.assert_called_once_with('You need 900 gold to enter.')

    def test_cloud_mutual_fallback_chains(self):
        cfg = {
            'translation_engine': 'groq',
            'groq_api_key': 'gsk-test',
            'gemini_api_key': 'gem-test',
            'deepl_api_key': 'dp-test'
        }
        # 1. Groq -> Gemini fallback
        translator_groq = RealtimeTranslator(cfg)
        translator_groq._post_process_korean = lambda t: t
        translator_groq._translate_groq = Mock(return_value='')
        translator_groq._translate_gemini = Mock(return_value='Gemini 번역')
        res, used = translator_groq.translate('Hello')
        self.assertEqual(res, 'Gemini 번역')
        self.assertIn('Groq 폴백', used)

        # 2. Gemini -> Groq fallback
        cfg_gemini = dict(cfg, translation_engine='gemini')
        translator_gem = RealtimeTranslator(cfg_gemini)
        translator_gem._post_process_korean = lambda t: t
        translator_gem._translate_gemini = Mock(return_value='')
        translator_gem._translate_groq = Mock(return_value='Groq 번역')
        res, used = translator_gem.translate('Hello')
        self.assertEqual(res, 'Groq 번역')
        self.assertIn('Gemini 폴백', used)

        # 3. DeepL -> Groq fallback
        cfg_deepl = dict(cfg, translation_engine='deepl')
        translator_dl = RealtimeTranslator(cfg_deepl)
        translator_dl._post_process_korean = lambda t: t
        translator_dl._translate_deepl = Mock(return_value='')
        translator_dl._translate_groq = Mock(return_value='Groq 번역')
        res, used = translator_dl.translate('Hello')
        self.assertEqual(res, 'Groq 번역')
        self.assertIn('DeepL 폴백', used)

