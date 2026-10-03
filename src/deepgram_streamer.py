import asyncio
import json
import queue
import threading
import time
import urllib.parse
import uuid
import inspect
from typing import Callable, Optional
import aiohttp
import numpy as np


class DeepgramLiveStreamer:
    """
    Deepgram WebSocket 실시간 라이브 스트리밍 어댑터 (1단계).
    
    [아키텍처 원칙: 무간섭 & 플러그앤플레이]
    - 이 파일 하나에만 모든 WebSocket 통신, 패킷 직렬화, 수신 비동기 루프가 완전히 캡슐화됩니다.
    - 언제든 이 모듈을 비활성화하거나 삭제해도 기존 STT 파이프라인(Groq / 로컬 Whisper)은
      100% 정상 작동합니다.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "nova-3",
        keywords: str = "",
        diarize: bool = False,
        endpointing: int = 600,
        on_interim: Optional[Callable] = None,
        on_final: Optional[Callable] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_event: Optional[Callable] = None,
        no_delay: bool = False,
    ):
        self.api_key = api_key.strip()
        self.model = model or "nova-3"
        self.keywords = keywords or ""
        self.diarize = bool(diarize)
        self.endpointing = int(endpointing)
        self.on_interim = on_interim
        self.on_final = on_final
        self.on_error = on_error
        self.on_event = on_event
        self.no_delay = bool(no_delay)

        self._audio_queue: queue.Queue = queue.Queue(maxsize=100)
        self._running = False
        self._connected = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_final_text = ""
        self._last_active_time = time.time()
        self._control_queue = queue.Queue()
        self._closing = False
        self._session_id = uuid.uuid4().hex
        self._seen_finals = set()
        self._last_finalize = -10.0

    def is_connected(self) -> bool:
        return self._connected and self._running

    def start(self):
        """백그라운드 비동기 WebSocket 워커 스레드 시작"""
        if self._running:
            return
        self._running = True
        self._closing = False
        self._thread = threading.Thread(
            target=self._run_event_loop,
            daemon=True,
            name="DeepgramLiveStreamerThread"
        )
        self._thread.start()

    def stop(self, flush=True):
        """WebSocket 연결 정상 종료 및 스레드 정리"""
        self._closing = True
        if flush and self.is_connected():
            # CloseStream flushes remaining audio and returns final results before close.
            self._control_queue.put({'type': 'CloseStream'})
            if self._thread and self._thread is not threading.current_thread():
                self._thread.join(timeout=2.0)
        self._running = False
        self._connected = False
        if self._loop and self._loop.is_running():
            def _cancel_all():
                for task in asyncio.all_tasks(self._loop):
                    task.cancel()
            self._loop.call_soon_threadsafe(_cancel_all)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._loop = None

    def request_finalize(self):
        now = time.monotonic()
        if self.is_connected() and now - self._last_finalize >= 2.0:
            self._last_finalize = now
            self._control_queue.put({'type': 'Finalize'})

    def send_audio(self, audio_data: np.ndarray):
        """
        16kHz float32 오디오 버퍼를 16-bit PCM 바이트로 변환 후 전송 큐에 삽입.
        논블로킹으로 동작하여 메인 STT 루프에 지연을 주지 않음.
        """
        if not self._running or self._closing:
            return
        try:
            if audio_data is None or len(audio_data) == 0:
                return
            # float32 [-1.0, 1.0] -> 16-bit Signed Integer PCM
            clipped = np.clip(audio_data, -1.0, 1.0)
            int16_bytes = (clipped * 32767).astype(np.int16).tobytes()
            self._audio_queue.put_nowait(int16_bytes)
        except queue.Full:
            # 큐 과적 방지 (가장 오래된 프레임 드롭)
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(int16_bytes)
                self._event({'type': 'AudioGap', 'reason': 'send_queue_overflow'})
            except Exception:
                pass
        except Exception as e:
            if self.on_error:
                self.on_error(e)

    def _build_ws_url(self) -> str:
        base_url = "wss://api.deepgram.com/v1/listen"
        params = [
            ("model", self.model),
            ("language", "en"),
            ("smart_format", "true"),
            ("interim_results", "true"),
            ("vad_events", "true"),
            ("endpointing", str(self.endpointing)),        # 기본 600ms로 완화하여 쉼표 조각남 방지
            ("utterance_end_ms", "1000"),  # 1000ms 단어 간격 시 UtteranceEnd 이벤트
            ("encoding", "linear16"),
            ("sample_rate", "16000"),
            ("channels", "1"),
        ]
        if self.no_delay:
            params.append(("no_delay", "true"))
        if self.diarize:
            params.append(("diarize", "true"))
        if self.keywords:
            is_nova3 = "nova-3" in self.model
            for kw in self.keywords.split(","):
                kw_s = kw.strip()
                if not kw_s:
                    continue
                if is_nova3:
                    term = kw_s.split(":")[0].strip()
                    if term:
                        params.append(("keyterm", term))
                else:
                    params.append(("keywords", kw_s))

        query_string = urllib.parse.urlencode(params)
        return f"{base_url}?{query_string}"

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._worker_lifecycle())
        except (asyncio.CancelledError, Exception) as e:
            if self._running and self.on_error:
                self.on_error(e)
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            self._loop.close()

    async def _worker_lifecycle(self):
        ws_url = self._build_ws_url()
        headers = {
            "Authorization": f"Token {self.api_key}"
        }

        retry_count = 0
        while self._running and not self._closing:
            try:
                timeout = aiohttp.ClientTimeout(total=None, connect=5.0)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.ws_connect(ws_url, headers=headers) as ws:
                        self._connected = True
                        self._session_id = uuid.uuid4().hex
                        self._seen_finals.clear()
                        self._event({'type': 'Connected'})
                        retry_count = 0
                        print(f"[Deepgram WS] [OK] WebSocket 실시간 연결 성공! (모델: {self.model})")

                        # 송신 태스크와 수신 태스크를 병렬 실행
                        send_task = asyncio.create_task(self._send_loop(ws))
                        recv_task = asyncio.create_task(self._recv_loop(ws))

                        done, pending = await asyncio.wait(
                            [send_task, recv_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        for t in pending:
                            t.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        self._connected = False
                        self._event({'type': 'Disconnected'})
                        if self._running and not self._closing:
                            await asyncio.sleep(0.5)

            except Exception as e:
                self._connected = False
                self._event({'type': 'Disconnected'})
                if not self._running or self._closing:
                    break
                retry_count += 1
                wait_sec = min(5.0, 1.0 * retry_count)
                print(f"[Deepgram WS] 연결 끊김 또는 오류: {e} ({wait_sec:.1f}초 후 재시도...)")
                if self.on_error:
                    self.on_error(e)
                await asyncio.sleep(wait_sec)

        self._connected = False

    async def _send_loop(self, ws: aiohttp.ClientWebSocketResponse):
        """오디오 큐에서 바이트를 꺼내 WebSocket으로 연속 스트리밍"""
        last_sent = time.monotonic()
        while self._running and not ws.closed:
            try:
                # 블로킹 큐를 비동기식으로 논블로킹 폴링
                try:
                    chunk_bytes = self._audio_queue.get_nowait()
                except queue.Empty:
                    try:
                        control = self._control_queue.get_nowait()
                    except queue.Empty:
                        control = None
                    if control:
                        await ws.send_json(control)
                        last_sent = time.monotonic()
                        if control['type'] == 'CloseStream':
                            # Keep receiving the final transcript; lifecycle cancels this task.
                            await asyncio.Future()
                    elif time.monotonic() - last_sent >= 3.0:
                        await ws.send_json({'type': 'KeepAlive'})
                        last_sent = time.monotonic()
                    await asyncio.sleep(0.015)
                    continue

                await ws.send_bytes(chunk_bytes)
                last_sent = time.monotonic()
                # Finalize must also be serviced during continuous audio, not just silence.
                if not self._control_queue.empty() and not self._closing:
                    await ws.send_json(self._control_queue.get_nowait())
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Deepgram WS] 오디오 전송 오류: {e}")
                break

    def _event(self, data):
        if self.on_event:
            event = dict(data, session_id=self._session_id, received_at=time.monotonic(),
                         model=self.model)
            self.on_event(event)

    @staticmethod
    def _dispatch(callback, text, speaker):
        if not callback:
            return
        try:
            inspect.signature(callback).bind(text, speaker)
        except TypeError:
            callback(text)
        else:
            callback(text, speaker)

    def _handle_message(self, data):
        kind = data.get('type')
        if kind == 'Results':
            alternatives = data.get('channel', {}).get('alternatives') or [{}]
            alt = alternatives[0]
            transcript = alt.get('transcript', '').strip()
            if data.get('is_final') and 'start' in data and 'duration' in data:
                key = (tuple(data.get('channel_index', [0, 1])), data['start'], data['duration'])
                if key in self._seen_finals:
                    # The same range may later carry an endpoint; preserve that control signal.
                    if data.get('speech_final'):
                        self._event(dict(data, channel={'alternatives': [{'transcript': '', 'words': []}]}))
                    return
                self._seen_finals.add(key)
                if len(self._seen_finals) > 4096:
                    self._seen_finals = {key}
            self._event(data)  # Includes blank results, timestamps, confidence and flags.
            # Structured consumers exclusively own segmentation. Legacy callbacks remain usable.
            if self.on_event or not transcript:
                return
            words = alt.get('words') or []
            speaker = words[0].get('speaker') if words else None
            callback = self.on_final if data.get('is_final') else self.on_interim
            self._dispatch(callback, transcript, speaker)
        elif kind in {'UtteranceEnd', 'SpeechStarted', 'Metadata'}:
            self._event(data)

    async def _recv_loop(self, ws: aiohttp.ClientWebSocketResponse):
        async for msg in ws:
            if not self._running:
                break
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    self._handle_message(json.loads(msg.data))
                except Exception as error:
                    print(f'[Deepgram WS] 메시지 처리 오류: {error}')
                    if self.on_error:
                        self.on_error(error)
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break
