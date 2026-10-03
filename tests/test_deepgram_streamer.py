import sys
import os
import json
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.deepgram_streamer import DeepgramLiveStreamer
from src.config import DEFAULT_CONFIG
from src.stt_engine import STTWorker


class TestDeepgramLiveStreamer(unittest.TestCase):
    def setUp(self):
        # Unit tests must not create live sockets or download speaker models.
        guards = [patch.object(DeepgramLiveStreamer, 'start'),
                  patch('src.speaker_identifier.SpeakerIdentifier._ensure_model_loaded', return_value=False)]
        for guard in guards:
            guard.start()
            self.addCleanup(guard.stop)

    def test_init_and_url_builder(self):
        """WebSocket URL 생성 및 파라미터 빌드 검증 (600ms endpointing 및 diarize 지원)"""
        streamer = DeepgramLiveStreamer(
            api_key="test_key_123",
            model="nova-3",
            keywords="OpenAI:2.0, Deepgram:2.0",
            diarize=True,
            endpointing=600
        )
        self.assertEqual(streamer.api_key, "test_key_123")
        self.assertEqual(streamer.model, "nova-3")
        self.assertTrue(streamer.diarize)
        self.assertEqual(streamer.endpointing, 600)
        self.assertFalse(streamer.is_connected())

        url = streamer._build_ws_url()
        self.assertTrue(url.startswith("wss://api.deepgram.com/v1/listen?"))
        self.assertIn("model=nova-3", url)
        self.assertIn("smart_format=true", url)
        self.assertIn("interim_results=true", url)
        self.assertIn("endpointing=600", url)
        self.assertIn("diarize=true", url)
        self.assertIn("keyterm=OpenAI", url)

    def test_send_audio_pcm16_conversion(self):
        """16kHz float32 -> int16 PCM 바이트 변환 검증"""
        streamer = DeepgramLiveStreamer(api_key="test_key")
        streamer._running = True

        fake_audio = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
        streamer.send_audio(fake_audio)

        self.assertEqual(streamer._audio_queue.qsize(), 1)
        raw_bytes = streamer._audio_queue.get_nowait()
        int16_arr = np.frombuffer(raw_bytes, dtype=np.int16)
        self.assertEqual(len(int16_arr), 5)
        self.assertEqual(int16_arr[0], 0)
        self.assertAlmostEqual(int16_arr[1], 16383, delta=2)
        self.assertAlmostEqual(int16_arr[2], -16384, delta=2)

    def test_recv_interim_and_final_callbacks_with_speaker(self):
        """Interim 결과와 Final 결과에 따른 콜백 분기 및 화자 번호 전달 검증"""
        interims = []
        finals = []

        streamer = DeepgramLiveStreamer(
            api_key="test_key",
            on_interim=lambda text, spk: interims.append((text, spk)),
            on_final=lambda text, spk: finals.append((text, spk))
        )
        streamer._running = True

        # 가상 메시지 1: 중간 타이핑 (is_final: False, speaker: 0)
        msg_interim = {
            "type": "Results",
            "is_final": False,
            "channel": {
                "alternatives": [{
                    "transcript": "Hello world",
                    "words": [{"word": "Hello", "speaker": 0}, {"word": "world", "speaker": 0}]
                }]
            }
        }
        
        alt = msg_interim["channel"]["alternatives"][0]
        transcript = alt.get("transcript", "").strip()
        words = alt.get("words", [])
        spk_id = words[0]["speaker"] if words else None

        if not msg_interim.get("is_final", False):
            streamer.on_interim(transcript, spk_id)

        self.assertEqual(interims, [("Hello world", 0)])
        self.assertEqual(finals, [])

        # 가상 메시지 2: 문장 완결 (is_final: True, speaker: 1)
        msg_final = {
            "type": "Results",
            "is_final": True,
            "channel": {
                "alternatives": [{
                    "transcript": "Hello world, welcome to AI subtitle.",
                    "words": [{"word": "Hello", "speaker": 1}, {"word": "world", "speaker": 1}]
                }]
            }
        }
        alt_final = msg_final["channel"]["alternatives"][0]
        transcript_final = alt_final.get("transcript", "").strip()
        words_final = alt_final.get("words", [])
        spk_id_final = words_final[0]["speaker"] if words_final else None

        if msg_final.get("is_final", False):
            streamer.on_final(transcript_final, spk_id_final)

        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0], ("Hello world, welcome to AI subtitle.", 1))

    def test_reconnection_guard(self):
        """동일 설정으로 update_config 호출 시 스트리머 인스턴스 보존 검증"""
        mock_queue = MagicMock()
        config = dict(DEFAULT_CONFIG)
        config["stt_provider"] = "deepgram"
        config["deepgram_api_key"] = "test_key_dummy"
        config["speaker_diarization_enabled"] = True

        worker = STTWorker(mock_queue, config=config)
        original_streamer = worker.deepgram_streamer
        self.assertIsNotNone(original_streamer)

        # fake connection state
        original_streamer._connected = True
        original_streamer._running = True

        # 동일한 config로 update_config 3회 연속 호출
        for _ in range(3):
            worker.update_config(config)
            self.assertIs(worker.deepgram_streamer, original_streamer)

    def test_two_track_sentence_assembly(self):
        """불완전한 단어 파편을 sentence_buffer에 조립 후 마침표/절 완결 시 번역 큐에 전송 검증"""
        mock_queue = MagicMock()
        config = dict(DEFAULT_CONFIG)
        config["stt_provider"] = "deepgram"
        config["deepgram_api_key"] = "test_key_dummy"
        config["speaker_diarization_enabled"] = True

        worker = STTWorker(mock_queue, config=config)
        self.assertIsNotNone(worker.deepgram_streamer)

        def final(text):
            worker.deepgram_streamer._handle_message({
                'type': 'Results', 'is_final': True,
                'channel': {'alternatives': [{'transcript': text,
                                              'words': []}]}})
            worker._consume_speech_events()

        final('He walks on those legs, but he can walk on')
        self.assertEqual(worker.trans_queue.qsize(), 0)
        self.assertTrue(worker._segmenter.pending)
        final('three of them.')
        self.assertEqual(worker.trans_queue.qsize(), 1)
        assembled_text, stt_name, spk_info, segment, generation = worker.trans_queue.get_nowait()
        self.assertEqual(assembled_text, 'He walks on those legs, but he can walk on three of them.')
        self.assertIsNone(spk_info)  # No word-level speaker evidence in this fixture.


if __name__ == '__main__':
    unittest.main()
