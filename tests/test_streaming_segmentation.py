import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.speech_segmenter import SpeechSegmenter


def result(text, start=0.0, speaker=0, final=True, endpoint=False, session='test'):
    words = [{'word': t.rstrip('.?!,'), 'punctuated_word': t,
              'start': start + i * .1, 'end': start + (i + 1) * .1,
              'speaker': speaker, 'confidence': .95}
             for i, t in enumerate(text.split())]
    return {'type': 'Results', 'session_id': session, 'is_final': final,
            'speech_final': endpoint, 'start': start, 'duration': len(words) * .1,
            'channel': {'alternatives': [{'transcript': text, 'words': words}]}}


class SegmenterTests(unittest.TestCase):
    def test_local_vad_endpoint_commits_unpunctuated_utterance(self):
        segmenter = SpeechSegmenter()
        event = {'type': 'Results', 'session_id': 'local:GPU',
                 'is_final': True, 'speech_final': True,
                 'channel': {'alternatives': [{'transcript': 'We should leave now'}]}}
        self.assertEqual(segmenter.accept(event, now=0), [])
        self.assertEqual([s.text for s in segmenter.tick(now=.34)], [])
        self.assertEqual([s.text for s in segmenter.tick(now=.36)],
                         ['We should leave now'])

    def test_complete_sentence_leaves_first_word_of_next(self):
        s = SpeechSegmenter()
        out = s.accept(result('That is the answer. I'), now=0)
        self.assertEqual([x.text for x in out], ['That is the answer.'])
        self.assertEqual(s.render(s.pending), 'I')
        out = s.accept(result('think we should leave.', start=.5), now=.1)
        self.assertEqual([x.text for x in out], ['I think we should leave.'])

    def test_never_and_thought_remain_together(self):
        s = SpeechSegmenter()
        self.assertEqual(s.accept(result('I never'), now=0), [])
        out = s.accept(result("Thought you'd start out that way.", start=.2), now=.2)
        self.assertEqual([x.text for x in out], ["I never Thought you'd start out that way."])

    def test_come_out_remains_together(self):
        s = SpeechSegmenter()
        self.assertEqual(s.accept(result('And you see it come'), now=0), [])
        self.assertEqual(s.tick(now=.7), [])
        out = s.accept(result("Out, and you can't help but make the noise.", start=.5), now=.8)
        self.assertEqual(len(out), 1)
        self.assertIn('come Out,', out[0].text)

    def test_short_reactions_combine_but_not_other_speakers(self):
        s = SpeechSegmenter()
        self.assertEqual(s.accept(result('Wow. Really?'), now=0), [])
        self.assertEqual([x.text for x in s.tick(now=.36)], ['Wow. Really?'])
        s.accept(result('Yes.', start=1), now=1)
        out = s.accept(result('No.', start=2, speaker=1), now=1.1)
        out += s.tick(now=1.5)
        self.assertEqual([(x.text, x.speaker) for x in out], [('Yes.', 0), ('No.', 1)])

    def test_unknown_single_word_waits_for_endpoint(self):
        s = SpeechSegmenter()
        self.assertEqual(s.accept(result('Page.'), now=0), [])
        self.assertEqual(s.tick(now=.5), [])
        out = s.accept({'type':'UtteranceEnd', 'session_id':'test', 'last_word_end':.1}, now=1)
        self.assertEqual([x.text for x in out], ['Page.'])

    def test_independent_short_sentences_not_banned_by_last_word(self):
        for text in ('I know.', 'I grew up.', 'Stop!', 'Hello.', 'Why?'):
            with self.subTest(text=text):
                s = SpeechSegmenter()
                out = s.accept(result(text), now=0) + s.tick(now=.36)
                self.assertEqual([x.text for x in out], [text])

    def test_punctuation_exceptions_and_closing_quotes(self):
        s = SpeechSegmenter()
        text = 'Dr. Smith paid 3.14 dollars in the U.S. today. "We should go now!"'
        out = s.accept(result(text), now=0)
        self.assertEqual([x.text for x in out], [
            'Dr. Smith paid 3.14 dollars in the U.S. today.', '"We should go now!"'])

    def test_internal_clause_extracted_not_entire_buffer(self):
        s = SpeechSegmenter(target_words=12)
        text = 'The team finally completed the difficult report, but the client asked for'
        out = s.accept(result(text), now=0)
        self.assertEqual([x.text for x in out], ['The team finally completed the difficult report,'])
        self.assertEqual(s.render(s.pending), 'but the client asked for')

    def test_arrival_gap_is_not_silence(self):
        s = SpeechSegmenter()
        s.accept(result('We need to understand this important issue'), now=0)
        self.assertEqual(s.tick(now=.7), [])

    def test_speech_endpoint_is_honored_and_not_duplicated(self):
        s = SpeechSegmenter()
        event = result('We need to understand this important issue', endpoint=True)
        self.assertEqual(s.accept(event, now=0), [])
        self.assertEqual(len(s.tick(now=.36)), 1)
        self.assertEqual(s.accept({'type': 'UtteranceEnd', 'session_id': 'test',
                                   'last_word_end': .7}, now=1), [])

    def test_empty_speech_final_flushes_prior_final(self):
        s = SpeechSegmenter()
        s.accept(result('We should consider another option'), now=0)
        s.accept(result('', start=.5, endpoint=True), now=.1)
        self.assertEqual([x.text for x in s.tick(now=.5)], ['We should consider another option'])

    def test_stale_utterance_end_cannot_clear_new_speech(self):
        s = SpeechSegmenter()
        s.accept(result('This is finished now.'), now=0)
        s.accept(result('I never', start=2), now=.1)
        for marker in (-1, .4):
            self.assertEqual(s.accept({'type':'UtteranceEnd', 'session_id':'test',
                                      'last_word_end':marker}, now=.2), [])
        self.assertEqual(s.render(s.pending), 'I never')

    def test_resumed_interim_prevents_late_endpoint_flushing_negative(self):
        s = SpeechSegmenter()
        s.accept(result('I never', endpoint=True), now=0)
        s.accept(result('thought it would work', start=.2, final=False), now=.2)
        s.accept({'type':'UtteranceEnd', 'session_id':'test', 'last_word_end':.2}, now=.3)
        self.assertEqual(s.tick(now=1.2), [])
        self.assertEqual(s.render(s.pending), 'I never')

    def test_replayed_empty_endpoint_does_not_flush_later_words(self):
        s = SpeechSegmenter()
        s.accept(result('That is the answer.'), now=0)
        s.accept(result('I never', start=2), now=.1)
        s.accept(result('', start=0, endpoint=True), now=.2)
        self.assertEqual(s.tick(now=1.3), [])
        self.assertEqual(s.render(s.pending), 'I never')

    def test_interim_revisions_are_preview_only(self):
        s = SpeechSegmenter()
        s.accept(result('I have a fan.', final=False), now=0)
        s.accept(result('I am a fan.', final=False), now=.1)
        self.assertEqual(s.pending, [])
        out = s.accept(result('I am a fan.'), now=.2)
        self.assertEqual([x.text for x in out], ['I am a fan.'])

    def test_same_text_different_times_preserved_replay_deduped(self):
        s = SpeechSegmenter()
        e = result('Yes.')
        s.accept(e, now=0)
        s.accept(e, now=.1)
        out = s.tick(now=.4)
        out += s.accept(result('Yes.', start=1), now=.5)
        out += s.tick(now=.9)
        self.assertEqual([x.text for x in out], ['Yes.', 'Yes.'])

    def test_speaker_changes_inside_one_result(self):
        s = SpeechSegmenter()
        e = result('Yes. No. Right.')
        for w, sp in zip(e['channel']['alternatives'][0]['words'], [0, 1, 0]):
            w['speaker'] = sp
        out = s.accept(e, now=0) + s.tick(now=.4)
        self.assertEqual([(x.text, x.speaker) for x in out], [('Yes.', 0), ('No.', 1), ('Right.', 0)])

    def test_incomplete_phrase_does_not_split_on_speaker_jitter(self):
        s = SpeechSegmenter()
        self.assertEqual(s.accept(result('I never'), now=0), [])
        second = result("Thought you'd start out that way.", start=.2, speaker=1)
        out = s.accept(second, now=.2)
        self.assertEqual([x.text for x in out], ["I never Thought you'd start out that way."])
        self.assertEqual(out[0].speaker, 0)

    def test_incomplete_clause_joins_despite_speaker_change(self):
        s = SpeechSegmenter()
        s.accept(result('which is world'), now=0)
        out = s.accept(result('building.', start=.4, speaker=1), now=.2)
        self.assertEqual([x.text for x in out], ['which is world building.'])
        self.assertEqual(out[0].speaker, 0)

    def test_reconnection_resets_word_clock_and_preserves_tail(self):
        s = SpeechSegmenter()
        s.accept(result('unfinished old words', start=50, session='old'), now=0)
        out = s.accept(result('This is new speech.', session='new'), now=.1)
        self.assertEqual([x.text for x in out], ['unfinished old words', 'This is new speech.'])
        self.assertEqual(out[1].session, 'new')

    def test_long_run_has_bounded_segments_and_preserves_tokens(self):
        s = SpeechSegmenter()
        text = ' '.join(f'word{i}' for i in range(75)) + '.'
        out = s.accept(result(text), now=0) + s.flush(now=1)
        self.assertEqual(' '.join(x.text for x in out), text)
        self.assertTrue(all(len(x.text.split()) <= 28 for x in out))

    def test_hard_age_does_not_reset_on_each_final(self):
        s = SpeechSegmenter()
        out = []
        for i in range(7):
            out += s.accept(result(f'word{i}', start=i*.1), now=i)
        self.assertTrue(out)
        self.assertEqual(out[0].reason, 'deadline')

    def test_packetization_does_not_change_normal_sentence_boundaries(self):
        text = 'That is the answer. I never thought it would work. We found the solution.'
        expected = ['That is the answer.', 'I never thought it would work.', 'We found the solution.']
        for chunk_size in (1, 3, 7, 100):
            s, out = SpeechSegmenter(), []
            words = text.split()
            for i in range(0, len(words), chunk_size):
                out += s.accept(result(' '.join(words[i:i+chunk_size]), start=i*.1), now=i*.01)
            out += s.flush(now=1)
            self.assertEqual([x.text for x in out], expected)

    def test_provided_log_words_conserved_and_critical_phrases_joined(self):
        path = Path(__file__).resolve().parents[1] / 'output/segmentation-review-2026-09-17/provided-log-pairs.json'
        pairs = json.loads(path.read_text(encoding='utf-8'))['pairs']
        s, output, position = SpeechSegmenter(), [], 0
        for i, pair in enumerate(pairs):
            text = pair['original']
            output += s.accept(result(text, start=position*.1), now=i*.1)
            position += len(text.split())
        output += s.flush(now=3)
        self.assertEqual(' '.join(x.text for x in output), ' '.join(x['original'] for x in pairs))
        self.assertTrue(any('I never Thought' in x.text for x in output))
        self.assertTrue(any('come Out,' in x.text for x in output))


class IntegrationTests(unittest.TestCase):
    def test_audio_pause_stops_deepgram_and_discards_waiting_work(self):
        from src.stt_engine import STTWorker
        worker = STTWorker.__new__(STTWorker)
        worker._paused = False
        worker._pause_generation = 0
        worker.sentence_buffer = ['Unfinished old speech']
        worker.current_sentence_speaker = (1, 'Old speaker', '#fff')
        worker.trans_queue = queue.Queue()
        worker.trans_queue.put(('old speech', 'Deepgram', None))
        streamer = Mock()
        worker.deepgram_streamer = streamer
        worker._init_deepgram_streamer = Mock()
        worker.set_paused_state(True)
        self.assertTrue(worker._paused)
        self.assertEqual(worker._pause_generation, 1)
        self.assertTrue(worker.trans_queue.empty())
        self.assertEqual(worker.sentence_buffer, [])
        self.assertIsNone(worker.current_sentence_speaker)
        streamer.stop.assert_called_once_with(flush=False)
        self.assertIsNone(worker.deepgram_streamer)
        worker.set_paused_state(False)
        worker._init_deepgram_streamer.assert_called_once()

    def test_pause_during_translation_suppresses_late_subtitle(self):
        from src.stt_engine import STTWorker
        worker = STTWorker.__new__(STTWorker)
        worker.running = False
        worker._draining = False
        worker._paused = False
        worker._pause_generation = 0
        worker.deepgram_streamer = None
        worker.trans_queue = queue.Queue()
        worker.trans_queue.put(('Old utterance.', 'CPU', None, None, 0))
        worker.speaker_identifier = None
        worker.config = {}
        worker._record = Mock()
        worker.subtitle_callback = Mock()
        worker.dubbing_engine = None
        worker.translator = Mock()

        def finish_after_pause(text):
            worker.set_paused_state(True)
            return '늦은 번역', 'mock'

        worker.translator.translate.side_effect = finish_after_pause
        worker._translation_loop()
        worker.subtitle_callback.assert_not_called()

    def test_google_html_parser_accepts_class_variants(self):
        from src.translator import RealtimeTranslator
        translator = RealtimeTranslator({'translation_engine': 'google'})
        translator.session.post = Mock(return_value=Mock(
            status_code=200,
            text="<div data-x='1' class='other result-container'><strong>안녕</strong>하세요</div>"))
        self.assertEqual(translator._translate_google_mobile('Hello'), '안녕하세요')

    def test_google_rate_limit_waits_before_retry(self):
        from src.translator import RealtimeTranslator
        translator = RealtimeTranslator({'translation_engine': 'google'})
        translator.session.post = Mock(return_value=Mock(
            status_code=429, headers={'Retry-After': '30'}))
        self.assertEqual(translator._translate_google_mobile('Hello'), '')
        self.assertEqual(translator._translate_google_mobile('Hello again'), '')
        translator.session.post.assert_called_once()

    def test_exaone_choice_overrides_stale_selected_model(self):
        from src.translator import RealtimeTranslator
        translator = RealtimeTranslator({'translation_engine': 'exaone',
                                         'llm_backend': 'ollama',
                                         'selected_llm_model': 'exaone3.5:7.8b'})
        translator._translate_ollama = Mock(return_value='번역 완료')
        translator._translate_exaone = Mock(return_value='')
        self.assertEqual(translator.translate('Translation test.')[0], '번역 완료')
        translator._translate_ollama.assert_called_once_with(
            'Translation test.', 'exaone3.5:2.4b')
        translator._translate_exaone.assert_not_called()

    def test_exaone_embedded_fallback_uses_selected_engine_size(self):
        from src.translator import RealtimeTranslator
        translator = RealtimeTranslator({'translation_engine': 'exaone',
                                         'llm_backend': 'ollama',
                                         'selected_llm_model': 'exaone3.5:7.8b'})
        translator._translate_ollama = Mock(return_value='')
        translator._translate_exaone = Mock(return_value='내장 번역')
        self.assertEqual(translator.translate('Translation test.')[0], '내장 번역')
        translator._translate_exaone.assert_called_once_with(
            'Translation test.', model_id='exaone-3.5-2.4b')

    def test_ollama_request_uses_live_service_without_install_cache(self):
        from src.translator import RealtimeTranslator
        translator = RealtimeTranslator({'translation_engine': 'ollama:exaone3.5:2.4b'})
        translator.session.post = Mock(return_value=Mock(
            status_code=200, json=Mock(return_value={'response': '안녕하세요.'})))
        translated, engine = translator.translate('Hello.')
        self.assertEqual(translated, '안녕하세요.')
        self.assertEqual(engine, 'Ollama (exaone3.5:2.4b)')
        self.assertEqual(translator.session.post.call_args.kwargs['json']['model'],
                         'exaone3.5:2.4b')

    def test_missing_gguf_does_not_start_background_download(self):
        import sys
        import types
        from src.translator import RealtimeTranslator
        model_manager = types.ModuleType('src.llm_model_manager')
        model_manager.LLMModelManager = type('Manager', (), {
            'get_gguf_file_path': staticmethod(lambda *args: None)})
        model_manager.RECOMMENDED_GGUF_MODELS = [{
            'id': 'exaone-3.5-7.8b', 'filename': 'missing.gguf'}]
        llama = types.ModuleType('llama_cpp')
        llama.Llama = Mock()
        translator = RealtimeTranslator({'translation_engine': 'exaone7b'})
        with patch.dict(sys.modules, {'src.llm_model_manager': model_manager,
                                      'llama_cpp': llama}):
            with self.assertRaises(FileNotFoundError):
                translator._get_exaone('exaone-3.5-7.8b')
        llama.Llama.assert_not_called()

    def test_google_failure_prefers_configured_translation_before_mymemory(self):
        from src.translator import RealtimeTranslator
        translator = RealtimeTranslator({'translation_engine': 'google',
                                         'groq_api_key': 'placeholder'})
        translator._translate_google_mobile = Mock(return_value='')
        translator._translate_groq = Mock(return_value='번역되었습니다.')
        translator._translate_mymemory = Mock(return_value='낮은 우선순위 번역')
        translated, engine = translator.translate('The selected engine failed.')
        self.assertEqual(translated, '번역되었습니다.')
        self.assertEqual(engine, 'Groq Qwen (Google 폴백)')
        translator._translate_mymemory.assert_not_called()

    def test_adapter_dispatches_actual_received_messages(self):
        from src.deepgram_streamer import DeepgramLiveStreamer
        received = []
        streamer = DeepgramLiveStreamer('placeholder', on_event=received.append)
        values = [result('Yes.'), result('Yes.'), result('Yes.', start=1, speaker=1),
                  result('', start=2, endpoint=True), {'type':'UtteranceEnd', 'last_word_end':1.1}]
        for value in values:
            streamer._handle_message(json.loads(json.dumps(value)))
        self.assertEqual(len(received), 4)
        self.assertEqual(received[1]['channel']['alternatives'][0]['words'][0]['speaker'], 1)
        self.assertTrue(received[2]['speech_final'])
        self.assertEqual(received[3]['type'], 'UtteranceEnd')

    def test_adapter_dispatches_blank_endpoint_after_repeated_range(self):
        from src.deepgram_streamer import DeepgramLiveStreamer
        events = []
        s = DeepgramLiveStreamer('placeholder', on_event=events.append)
        e = result('Some unfinished idea')
        s._handle_message(e)
        s._handle_message(dict(e, speech_final=True))
        self.assertEqual(len(events), 2)
        self.assertTrue(events[-1]['speech_final'])
        self.assertEqual(events[-1]['channel']['alternatives'][0]['words'], [])

    def test_groq_context_cache_and_multiline_output(self):
        from src.translator import RealtimeTranslator
        t = RealtimeTranslator({'translation_engine':'groq', 'groq_api_key':'placeholder'})
        response = Mock(status_code=200)
        response.json.return_value = {'model':'actual-model', 'choices':[
            {'finish_reason':'stop', 'message':{'content':'첫 문장입니다.\n둘째 문장입니다.'}}]}
        t.session.post = Mock(return_value=response)
        t._post_process_korean = lambda text: text
        a = t.translate_segment('It worked.', ['A device was tested.'])
        t.translate_segment('It worked.', ['A device was tested.'])
        t.translate_segment('It worked.', ['A plan was tested.'])
        self.assertEqual(t.session.post.call_count, 2)
        self.assertEqual(a[0], '첫 문장입니다. 둘째 문장입니다.')
        payload = t.session.post.call_args.kwargs['json']
        body = json.loads(payload['messages'][1]['content'])
        self.assertEqual(body['current_segment'], 'It worked.')
        self.assertEqual(body['reference_context'], ['A plan was tested.'])
        self.assertGreaterEqual(payload['max_tokens'], 192)
        self.assertEqual(t._reference_context, [])

    def test_truncated_groq_output_is_not_published(self):
        from src.translator import RealtimeTranslator
        t = RealtimeTranslator()
        responses = []
        for finish, text in [('length', '잘린 번'), ('stop', '완전한 번역입니다.')]:
            r = Mock(status_code=200)
            r.json.return_value = {'choices':[{'finish_reason':finish, 'message':{'content':text}}]}
            responses.append(r)
        t.session.post = Mock(side_effect=responses)
        self.assertEqual(t._translate_groq('This is a sentence.', 'placeholder'), '완전한 번역입니다.')

    def test_valid_short_responses_reach_translator(self):
        from src.translator import RealtimeTranslator
        t = RealtimeTranslator()
        t._translate_google_mobile = Mock(return_value='네.')
        for word in ('Okay.', 'Yeah.', 'Right.', 'Yes.', 'No.'):
            self.assertTrue(t.translate(word)[0])
        self.assertEqual(t._translate_google_mobile.call_count, 5)

    def test_committed_short_number_and_fragment_are_not_silently_dropped(self):
        from src.translator import RealtimeTranslator
        t = RealtimeTranslator()
        t._translate_google_mobile = Mock(return_value='보존됨')
        for text in ('5', 'A', 'And'):
            self.assertEqual(t.translate_segment(text, partial=True)[0], '보존됨')

    def test_worker_stop_drains_last_socket_final(self):
        from src.stt_engine import STTWorker
        from threading import Event
        with patch.object(STTWorker, '_load_model'), patch.object(STTWorker, '_init_deepgram_streamer'):
            w = STTWorker(queue.Queue(), config={'stt_provider': 'deepgram',
                                                  'translation_trace_enabled': False})
        started = Event()
        w.deepgram_streamer = Mock()
        w.deepgram_streamer.stop.side_effect = lambda: w._speech_events.put(result('I never thought it would work.'))
        w.translator.translate_segment = Mock(return_value=('끝까지 번역', 'mock'))
        original_consume = w._consume_speech_events
        def consume():
            started.set()
            original_consume()
        w._consume_speech_events = consume
        w.start()
        self.assertTrue(started.wait(2))
        w.stop()
        self.assertFalse(w.is_alive())
        self.assertFalse(w.trans_worker.is_alive())
        w.translator.translate_segment.assert_called_once()

    def test_pipeline_trace_rotation_and_no_config_credentials(self):
        from src.pipeline_trace import PipelineTrace
        with tempfile.TemporaryDirectory() as directory:
            # 기본값은 꺼짐: 사용자가 켜기 전에는 파일을 만들지 않는다.
            disabled = PipelineTrace(directory=directory)
            disabled.record('segment', id='x:0', session='x', text='Hidden.')
            disabled.close()
            self.assertFalse((Path(directory)/'translation.jsonl').exists())

            trace = PipelineTrace(enabled=True, directory=directory)
            trace.record('segment', id='x:1', session='x', text='Hello.')
            trace.close()
            value = json.loads((Path(directory)/'translation.jsonl').read_text(encoding='utf-8'))
            self.assertEqual(value['session'], 'x')
            self.assertIn('trace_session', value)
            self.assertNotIn('api_key', value)

    def test_worker_queues_only_committed_segments_and_never_remerges(self):
        from src.stt_engine import STTWorker
        with patch.object(STTWorker, '_load_model'), patch.object(STTWorker, '_init_deepgram_streamer'):
            w = STTWorker(queue.Queue(), config={'stt_provider': 'deepgram',
                                                  'speaker_diarization_enabled': False})
        w._speech_events.put(result('That is the answer. I'))
        w._consume_speech_events()
        w._speech_events.put(result('think we should leave.', start=.5))
        w._consume_speech_events()
        self.assertEqual(w.trans_queue.qsize(), 2)
        w.translator.translate_segment = Mock(return_value=('번역', 'mock'))
        w._translation_loop()
        self.assertEqual([c.args[0] for c in w.translator.translate_segment.call_args_list],
                         ['That is the answer.', 'I think we should leave.'])


if __name__ == '__main__':
    unittest.main()
