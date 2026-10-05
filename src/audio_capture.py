import sys
import time
import threading
import queue
import warnings
import uuid
from contextlib import nullcontext
import numpy as np
import soundcard as sc
from scipy.signal import butter, sosfilt
from .audio_chunk import CapturedAudio, offer_queue
from src.i18n import tr

# Soundcard 버퍼 불연속(WASAPI 드롭) 경고 억제 (콘솔 I/O 지연 및 UI 프리징 원천 방지)
try:
    warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)
except Exception:
    pass
warnings.filterwarnings("ignore", message=".*data discontinuity in recording.*")

class AudioLoopbackCapture(threading.Thread):
    def __init__(self, audio_queue: queue.Queue, level_callback=None, config=None, dubbing_engine=None):
        super().__init__(daemon=True)
        self.audio_queue = audio_queue
        self.level_callback = level_callback
        self.config = config or {}
        self.dubbing_engine = dubbing_engine
        
        self.sample_rate = 16000
        self.chunk_size = 1600  # 100ms
        self.running = False
        self.paused = not self.config.get("auto_start_audio", False)
        self._pause_lock = threading.Lock()
        
        self.capture_device = self.config.get("audio_capture_device", "default")
        self._device_switch_requested = False
        self.active_capture_mode = "inactive"
        self.active_capture_device_id = None
        self.capture_error = ""
        self.status_callback = None
        self._capture_cursor = 0
        self._capture_session = None
        self._timeline_reset_requested = False
        if dubbing_engine is not None:
            dubbing_engine.audio_capture = self

        # 기본 감도 및 저지연 버퍼 파라미터 (콘텐츠 템포 프리셋 연동)
        from src.config import CONTENT_TEMPO_PRESETS
        preset_key = self.config.get("content_tempo_preset", "smart")
        preset = CONTENT_TEMPO_PRESETS.get(preset_key, CONTENT_TEMPO_PRESETS["smart"])
        self.vad_threshold = float(self.config.get("vad_threshold", preset.get("vad_threshold", 0.006)))
        self.silence_duration_sec = float(self.config.get("silence_duration_sec", preset.get("silence_duration_sec", 0.45)))
        self.max_buffer_sec = float(self.config.get("max_buffer_sec", preset.get("max_buffer_sec", 2.5)))
        
        # 80Hz Butterworth 하이패스 필터 (BGM 서브 베이스 럼블 제거 - float32 단일 정밀도 최적화)
        self.sos = butter(4, 80, 'hp', fs=self.sample_rate, output='sos').astype(np.float32)
        self.filter_state = np.zeros((self.sos.shape[0], 2), dtype=np.float32)

        # 실시간 모니터링 패스스루 & 스마트 오디오 덕킹 설정
        self.passthrough_queue = queue.Queue(maxsize=30)
        self.passthrough_enabled = self.config.get("audio_passthrough_enabled", True)
        self.passthrough_volume = float(self.config.get("audio_passthrough_volume", 100)) / 100.0
        self.ducking_enabled = self.config.get("audio_ducking_enabled", True)
        self.ducking_volume = float(self.config.get("audio_ducking_volume", 30)) / 100.0
        self._current_gain = 1.0

        # 패스스루 백그라운드 워커 스레드 시작
        self.passthrough_thread = threading.Thread(target=self._passthrough_loop, daemon=True, name="AudioPassthroughWorker")

    KNOWN_MEDIA_APPS_I18N = {
        "whale.exe": {"ko": "네이버 웨일 (Whale)", "en": "Naver Whale"},
        "chrome.exe": {"ko": "Google Chrome", "en": "Google Chrome"},
        "msedge.exe": {"ko": "Microsoft Edge", "en": "Microsoft Edge"},
        "brave.exe": {"ko": "Brave 브라우저", "en": "Brave Browser"},
        "firefox.exe": {"ko": "Mozilla Firefox", "en": "Mozilla Firefox"},
        "opera.exe": {"ko": "Opera 브라우저", "en": "Opera Browser"},
        "vivaldi.exe": {"ko": "Vivaldi 브라우저", "en": "Vivaldi Browser"},
        "potplayer64.exe": {"ko": "팟플레이어 64-bit", "en": "PotPlayer 64-bit"},
        "potplayermini64.exe": {"ko": "팟플레이어 64-bit", "en": "PotPlayer 64-bit"},
        "potplayermini.exe": {"ko": "팟플레이어 32-bit", "en": "PotPlayer 32-bit"},
        "vlc.exe": {"ko": "VLC 미디어 플레이어", "en": "VLC Media Player"},
        "wmplayer.exe": {"ko": "Windows 미디어 플레이어", "en": "Windows Media Player"},
        "spotify.exe": {"ko": "스포티파이 (Spotify)", "en": "Spotify"},
        "discord.exe": {"ko": "디스코드 (Discord)", "en": "Discord"},
        "zoom.exe": {"ko": "줌 (Zoom)", "en": "Zoom"},
    }
    KNOWN_MEDIA_APPS = {k: v["ko"] for k, v in KNOWN_MEDIA_APPS_I18N.items()}

    @classmethod
    def get_known_app_label(cls, p_name: str) -> str:
        key = str(p_name or "").lower()
        info = cls.KNOWN_MEDIA_APPS_I18N.get(key)
        if not info:
            return cls.KNOWN_MEDIA_APPS.get(key, p_name)
        from src.i18n import ui_language
        lang = ui_language()
        return info.get(lang) or info.get("en") or info.get("ko") or p_name

    @classmethod
    def find_root_pid(cls, app_name: str):
        """지정된 프로세스명(예: whale.exe)의 메인 부모 PID 탐색 (KeyError 방지 및 안전 조회)"""
        if not app_name:
            return None
        matches = []
        try:
            import psutil
            for p in psutil.process_iter(['pid', 'name', 'ppid', 'create_time']):
                try:
                    p_info = p.info
                    name = p_info.get('name')
                    if name and name.lower() == app_name.lower():
                        if p_info.get('pid'):
                            matches.append(p)
                except Exception:
                    pass
        except Exception as e:
            print(f"[Audio] 프로세스 탐색 오류: {e}")
            return None

        if not matches:
            return None

        pids = {p.info.get('pid') for p in matches if p.info.get('pid') is not None}
        root_candidates = [p for p in matches if p.info.get('ppid') not in pids]
        if root_candidates:
            root_candidates.sort(key=lambda p: p.info.get('create_time', 0.0) or 0.0)
            return root_candidates[0].info.get('pid')
        matches.sort(key=lambda p: p.info.get('create_time', 0.0) or 0.0)
        return matches[0].info.get('pid')

    @classmethod
    def get_available_capture_sources(cls, current_selected: str = None):
        """캡처 가능한 오디오 소스 목록 반환 (무설치 앱 캡처 + 윈도우 사운드 장치)"""
        sources = [
            {
                "id": "default",
                "type": "device",
                "name": f"🔊 {tr('audio_default')}"
            }
        ]

        detected_apps = {}

        # 1. Windows Core Audio 세션 기반 실제 오디오 활성 프로세스 탐지 (게임, 플레이어, 메신저 등)
        try:
            from src.process_volume import get_active_audio_processes
            active_procs = get_active_audio_processes()
            for proc in active_procs:
                p_name = proc["name"]
                orig_name = proc.get("original_name", p_name)
                p_name_lower = p_name.lower()
                # 알려진 미디어 앱 라벨 매칭
                if p_name_lower in cls.KNOWN_MEDIA_APPS:
                    label = cls.get_known_app_label(p_name_lower)
                    name_display = f"🌐 {label} ({orig_name})"
                else:
                    tag = tr("audio_app_tag")
                    name_display = f"🎮 [{tag}] {orig_name}"
                detected_apps[p_name] = {
                    "id": f"process:{p_name}",
                    "type": "process",
                    "app_name": p_name,
                    "name": name_display,
                    "pid": proc["pid"]
                }
        except Exception:
            pass

        # 2. 실행 중인 브라우저 및 미디어 앱 자동 탐지 (미리 실행된 브라우저 등, 아직 소리를 내지 않았더라도 포함)
        try:
            import psutil
            for p in psutil.process_iter(['pid', 'name', 'create_time']):
                try:
                    name = p.info['name']
                    if not name:
                        continue
                    name_lower = name.lower()
                    if name_lower in cls.KNOWN_MEDIA_APPS and name_lower not in detected_apps:
                        label = cls.get_known_app_label(name_lower)
                        detected_apps[name_lower] = {
                            "id": f"process:{name_lower}",
                            "type": "process",
                            "app_name": name_lower,
                            "name": f"🌐 {label} ({name})",
                            "pid": p.info['pid']
                        }
                except Exception:
                    pass
        except Exception as e:
            print(f"[Audio] 앱 목록 검색 오류: {e}")

        # 3. 만약 사용자가 현재 선택 중인 프로세스가 실행 대기 중(미실행) 상태라면 목록에 '대기 중'으로 유지
        if current_selected and str(current_selected).startswith("process:"):
            target_app = str(current_selected).split(":", 1)[1].lower()
            if target_app not in detected_apps:
                label = cls.get_known_app_label(target_app)
                pending_tag = tr("audio_pending_tag")
                detected_apps[target_app] = {
                    "id": f"process:{target_app}",
                    "type": "process",
                    "app_name": target_app,
                    "name": f"⏳ [{pending_tag}] {label}",
                    "pid": None
                }

        # 프로세스 소스 추가 (알려진 앱 우선, 그 다음 일반 앱 정렬)
        for app_info in sorted(detected_apps.values(), key=lambda x: (0 if "🌐" in x["name"] else (2 if "⏳" in x["name"] else 1), x["name"])):
            sources.append(app_info)

        # 4. 물리/가상 사운드카드 장치 목록 (Soundcard Loopback)
        try:
            for s in sc.all_speakers():
                sources.append({
                    "id": s.name,
                    "type": "device",
                    "name": f"🎧 {s.name}"
                })
        except Exception as e:
            print(f"[Audio] 장치 열거 오류: {e}")

        return sources

    @staticmethod
    def get_available_devices():
        """현재 시스템에서 루프백 캡처 가능한 모든 스피커/출력 장치 목록 반환"""
        devices = []
        try:
            for s in sc.all_speakers():
                devices.append({
                    "id": s.id,
                    "name": s.name
                })
        except Exception as e:
            print(f"[Audio] 장치 열거 오류: {e}")
        return devices

    def set_capture_device(self, device_name: str):
        """캡처 장치(또는 프로세스)를 실시간으로 변경"""
        if self.capture_device != device_name:
            self.capture_device = device_name
            self.config["audio_capture_device"] = device_name
            self._device_switch_requested = True
            self.active_capture_mode = "inactive"
            self.active_capture_device_id = None
            print(f"[Audio] 캡처 장치/앱 변경 요청: '{device_name}'")

    # 기존/외부 호출 호환용 에일리어스
    switch_device = set_capture_device


    def _get_loopback_mic(self):
        """설정된 capture_device에 맞는 루프백 마이크 획득"""
        if self.capture_device and self.capture_device != "default":
            try:
                speakers = sc.all_speakers()
                target_spk = None
                for s in speakers:
                    if self.capture_device == s.name or self.capture_device == s.id or (self.capture_device in s.name):
                        target_spk = s
                        break
                if target_spk:
                    mic = sc.get_microphone(id=str(target_spk.name), include_loopback=True)
                    print(f"[Audio] 지정된 루프백 장치 연결 성공: {mic.name}")
                    return mic
                else:
                    print(f"[Audio] 지정된 장치 '{self.capture_device}'를 찾을 수 없어 기본 장치로 대체합니다.")
            except Exception as e:
                print(f"[Audio] 지정 루프백 장치 획득 실패: {e}")

        # 기본 장치 루프백
        try:
            default_speaker = sc.default_speaker()
            mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
            print(f"[Audio] 기본 루프백 장치 연결 성공: {mic.name}")
            return mic
        except Exception as e:
            print(f"[Audio] 기본 스피커 획득 실패: {e}, 대체 장치 검색 중...")
            mics = sc.all_microphones(include_loopback=True)
            loopback_mics = [m for m in mics if m.isloopback]
            if loopback_mics:
                print(f"[Audio] 대체 루프백 연결: {loopback_mics[0].name}")
                return loopback_mics[0]
            raise RuntimeError("루프백 가능한 사운드 장치를 찾을 수 없습니다.")

    def is_channels_separated(self) -> bool:
        """Only a successfully opened capture/output pair can prove isolation."""
        if not getattr(self, 'running', False) or getattr(self, 'paused', False):
            return False
        if getattr(self, 'active_capture_mode', None) == "process":
            return True
        capture_id = getattr(self, 'active_capture_device_id', None)
        engine = getattr(self, 'dubbing_engine', None)
        output_id = getattr(engine, 'active_output_device_id', None)
        return bool(getattr(self, 'active_capture_mode', None) == "device"
                    and capture_id and output_id and capture_id != output_id
                    and getattr(engine, '_mixer_initialized', False))

    def _capture_failed(self, message):
        self.active_capture_mode = "error"
        self.active_capture_device_id = None
        self.capture_error = message
        print(f"[Audio] {message}")
        callback = getattr(self, 'status_callback', None)
        if callback:
            callback("error", message)

    def _enqueue_audio(self, samples, speech_end=False):
        with getattr(self, '_pause_lock', nullcontext()):
            if getattr(self, 'paused', False):
                return
            cursor = getattr(self, '_capture_cursor', None)
            start = max(0, cursor - len(samples)) if cursor is not None else None
            offer_queue(self.audio_queue, CapturedAudio(samples, self.is_channels_separated(),
                                              start, getattr(self, '_capture_session', None), speech_end,
                                              getattr(self, 'config', {}).get("stt_provider", "local")))

    def _start_timeline(self):
        self._capture_cursor = 0
        self._capture_session = uuid.uuid4().hex
        self._timeline_reset_requested = False

    def _get_passthrough_speaker(self):
        """더빙 출력 장치에 대응하는 스피커 객체 획득"""
        dub_dev = self.config.get("dubbing_output_device", "default")
        if dub_dev and dub_dev != "default":
            try:
                for s in sc.all_speakers():
                    if dub_dev == s.name or dub_dev == s.id:
                        return s
            except Exception:
                pass
        try:
            return sc.default_speaker()
        except Exception:
            return None

    def _passthrough_loop(self):
        """가상 채널 소리를 헤드폰으로 실시간 패스스루하며, 성우 더빙 시 부드럽게 감쇄(Ducking)"""
        while self.running:
            try:
                chunk = self.passthrough_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            cap_dev = str(self.config.get("audio_capture_device", "default"))
            if cap_dev.startswith("process:"):
                # 앱 단독 캡처 시에는 브라우저/플레이어가 이미 윈도우 스피커로 재생 중이므로
                # 패스스루 중복 믹싱을 방지하기 위해 대기
                time.sleep(0.05)
                continue

            if not self.passthrough_enabled or not self.is_channels_separated():
                time.sleep(0.05)
                continue

            target_speaker = self._get_passthrough_speaker()
            if not target_speaker:
                time.sleep(0.2)
                continue

            try:
                with target_speaker.player(samplerate=self.sample_rate, channels=1) as player:
                    while self.running and not self._device_switch_requested:
                        if not self.passthrough_enabled or not self.is_channels_separated():
                            break

                        # 성우 더빙 발화 여부 실시간 감지
                        is_dubbing_speaking = False
                        if self.dubbing_engine and self.dubbing_engine.is_speaking(grace_period=0.3):
                            is_dubbing_speaking = True

                        if is_dubbing_speaking and self.ducking_enabled:
                            target_gain = self.ducking_volume * self.passthrough_volume
                        else:
                            target_gain = 1.0 * self.passthrough_volume

                        # 리니어 스무딩 보간 (클릭/팝 노이즈 원천 방지)
                        if abs(self._current_gain - target_gain) > 1e-4:
                            gain_curve = np.linspace(self._current_gain, target_gain, len(chunk), dtype=np.float32)
                            self._current_gain = target_gain
                        else:
                            gain_curve = target_gain

                        ducked_chunk = (chunk * gain_curve).astype(np.float32)
                        player.play(ducked_chunk)

                        try:
                            chunk = self.passthrough_queue.get(timeout=0.15)
                        except queue.Empty:
                            break
            except Exception as e:
                time.sleep(0.1)

    def set_dubbing_engine(self, dubbing_engine):
        self.dubbing_engine = dubbing_engine
        
    def update_config(self, config):
        self.config = config
        new_dev = self.config.get("audio_capture_device", "default")
        if new_dev != self.capture_device:
            self.set_capture_device(new_dev)
        from src.config import CONTENT_TEMPO_PRESETS
        preset_key = self.config.get("content_tempo_preset", "smart")
        preset = CONTENT_TEMPO_PRESETS.get(preset_key, CONTENT_TEMPO_PRESETS["smart"])
        self.vad_threshold = float(self.config.get("vad_threshold", preset.get("vad_threshold", 0.006)))
        self.silence_duration_sec = float(self.config.get("silence_duration_sec", preset.get("silence_duration_sec", 0.45)))
        self.max_buffer_sec = float(self.config.get("max_buffer_sec", preset.get("max_buffer_sec", 2.5)))
        self.passthrough_enabled = self.config.get("audio_passthrough_enabled", True)
        self.passthrough_volume = float(self.config.get("audio_passthrough_volume", 100)) / 100.0
        self.ducking_enabled = self.config.get("audio_ducking_enabled", True)
        self.ducking_volume = float(self.config.get("audio_ducking_volume", 30)) / 100.0

    def set_tempo_params(self, silence_sec: float = None, max_buffer_sec: float = None, vad_threshold: float = None):
        """스마트 모드 또는 프리셋에 의해 오디오 수음 루프 파라미터를 실시간 동적 갱신"""
        if silence_sec is not None:
            self.silence_duration_sec = float(silence_sec)
        if max_buffer_sec is not None:
            self.max_buffer_sec = float(max_buffer_sec)
        if vad_threshold is not None:
            self.vad_threshold = float(vad_threshold)

    def pause(self):
        with self._pause_lock:
            self.paused = True
            while True:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break

    def resume(self):
        with self._pause_lock:
            while True:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break
            self._timeline_reset_requested = True
            self.paused = False

    def stop(self):
        self.running = False
        self.active_capture_mode = "inactive"
        for worker in (self, self.passthrough_thread):
            if worker.is_alive() and worker is not threading.current_thread():
                worker.join(timeout=3.0)

    def run(self):
        self.running = True
        self.passthrough_thread.start()
        print("[Audio] 오디오 캡처 스레드 가동 (하이패스 필터 & 고감도 저지연 모드)")

        while self.running:
            # 통역이 꺼져 있으면 WASAPI/프로세스 루프백을 열지 않는다.
            # 브라우저 단독 캡처를 대기 상태로 유지하면 오디오 엔진이 계속 CPU를 쓴다.
            if self.paused:
                self.active_capture_mode = "inactive"
                self.active_capture_device_id = None
                time.sleep(0.25)
                continue

            self._device_switch_requested = False
            cur_cap = str(self.capture_device)

            try:
                if cur_cap.startswith("process:"):
                    app_name = cur_cap.split(":", 1)[1]
                    self._run_process_capture(app_name)
                else:
                    self._run_device_capture()
            except Exception as e:
                if self.running and not self._device_switch_requested:
                    print(f"[Audio] 오디오 캡처 스레드 일시 오류 복구 중: {e}")
                    time.sleep(0.5)
            finally:
                self.active_capture_mode = "inactive"
                self.active_capture_device_id = None

        print("[Audio] 오디오 캡처 스레드 정상 종료")

    def _run_device_capture(self):
        """윈도우 사운드 장치/스피커 루프백 캡처 루프"""
        if self.paused:
            return
        self._start_timeline()
        try:
            loopback_mic = self._get_loopback_mic()
        except Exception as e:
            print(f"[Audio] 루프백 장치 초기화 실패: {e}")
            time.sleep(1.0)
            return

        speech_chunks = []
        silence_chunks_count = 0
        is_speaking = False

        try:
            with loopback_mic.recorder(samplerate=self.sample_rate, channels=1) as recorder:
                self.active_capture_mode = "device"
                self.active_capture_device_id = str(loopback_mic.id)
                self.capture_error = ""
                while self.running and not self._device_switch_requested:
                    if self.paused:
                        break

                    if self._timeline_reset_requested:
                        self._start_timeline()
                        speech_chunks = []
                        silence_chunks_count = 0
                        is_speaking = False

                    try:
                        # 100ms 오디오 녹음
                        data = recorder.record(numframes=self.chunk_size)
                        raw_audio = data[:, 0].astype(np.float32)

                        # 80Hz 하이패스 필터링 (float32 직접 연산으로 메모리 대역폭 50% 절감 및 배열 할당 제거)
                        filtered_audio, self.filter_state = sosfilt(self.sos, raw_audio, zi=self.filter_state)
                        self._capture_cursor += len(filtered_audio)

                        # RMS 에너지 계산 (np.dot 기반 무할당 고속 연산)
                        rms = float(np.sqrt(np.dot(filtered_audio, filtered_audio) / len(filtered_audio)))

                        # UI 볼륨 레벨 전달
                        if self.level_callback:
                            self.level_callback(rms)

                        # 가상 채널 분리 시 헤드폰으로 원본 사운드 실시간 패스스루 큐잉
                        if self.passthrough_enabled and self.is_channels_separated():
                            try:
                                self.passthrough_queue.put_nowait(filtered_audio)
                            except queue.Full:
                                pass

                        # Deepgram 등 실시간 WebSocket 스트리밍 엔진 모드: 100ms 프레임을 청크 버퍼링 없이 즉시 스트리밍
                        if self.config.get("stt_provider") == "deepgram":
                            speech_chunks = []
                            silence_chunks_count = 0
                            is_speaking = False
                            self._enqueue_audio(filtered_audio)
                            continue

                        max_chunks = int(self.max_buffer_sec * self.sample_rate / self.chunk_size)
                        silence_chunks_threshold = int(self.silence_duration_sec * self.sample_rate / self.chunk_size)

                        # 음성 감지 판별
                        if rms >= self.vad_threshold:
                            is_speaking = True
                            speech_chunks.append(filtered_audio)
                            silence_chunks_count = 0

                            # 긴 발화의 경우 2.2초마다 쪼개어 실시간 전송
                            if len(speech_chunks) >= max_chunks:
                                full_audio = np.concatenate(speech_chunks).astype(np.float32)
                                self._enqueue_audio(full_audio)
                                speech_chunks = []
                                is_speaking = True
                                silence_chunks_count = 0
                        else:
                            if is_speaking:
                                speech_chunks.append(filtered_audio)
                                silence_chunks_count += 1

                                # 문장 종료 침묵(약 0.35초) 감지 시 STT 큐로 전송
                                if silence_chunks_count >= silence_chunks_threshold:
                                    full_audio = np.concatenate(speech_chunks).astype(np.float32)
                                    if len(full_audio) >= int(0.05 * self.sample_rate):
                                        self._enqueue_audio(full_audio, speech_end=True)
                                    speech_chunks = []
                                    is_speaking = False
                                    silence_chunks_count = 0
                            else:
                                speech_chunks = []
                                silence_chunks_count = 0

                    except Exception as e:
                        if self.running and not self._device_switch_requested:
                            print(f"[Audio] 오디오 캡처 루프 예외: {e}")
                        time.sleep(0.05)
        except Exception as e:
            if self.running and not self._device_switch_requested:
                print(f"[Audio] 오디오 레코더 초기화 오류: {e}")
                time.sleep(0.5)

    def _run_process_capture(self, app_name: str):
        """지정 프로세스 단독 오디오 캡처 루프 (WASAPI Process Loopback)"""
        self._start_timeline()
        self.active_capture_mode = "inactive"
        self.active_capture_device_id = None
        try:
            import proctap
            from scipy.signal import resample_poly
        except ImportError as e:
            self._capture_failed(f"앱 전용 캡처를 시작할 수 없습니다: {e}. 입력 장치 또는 설치 상태를 확인하세요.")
            time.sleep(1.0)
            return

        if self.paused:
            return
        print(f"[Audio] [START] 무설치 프로세스 오디오 캡처 시작: {app_name}")
        pid = self.find_root_pid(app_name)
        if not pid:
            print(f"[Audio] [WARN] '{app_name}' 프로세스를 찾을 수 없습니다. 프로그램 실행 대기 중...")
            while self.running and not self._device_switch_requested and not self.paused:
                time.sleep(1.5)
                pid = self.find_root_pid(app_name)
                if pid:
                    print(f"[Audio] [OK] '{app_name}' 프로세스 감지 완료 (PID: {pid})")
                    break

        if not self.running or self._device_switch_requested or not pid or self.paused:
            return

        tap = None
        try:
            tap = proctap.ProcessAudioCapture(pid=pid)
            tap.start()
            self.active_capture_mode = "process"
            self.capture_error = ""
            print(f"[Audio] [OK] WASAPI Process Loopback 가동 성공! (PID: {pid}, 대상: {app_name})")

            speech_chunks = []
            silence_chunks_count = 0
            is_speaking = False
            accum_buf = np.empty((0,), dtype=np.float32)

            while self.running and not self._device_switch_requested:
                if self.paused:
                    break

                if self._timeline_reset_requested:
                    self._start_timeline()
                    speech_chunks = []
                    silence_chunks_count = 0
                    is_speaking = False
                    accum_buf = np.empty((0,), dtype=np.float32)

                try:
                    raw_bytes = tap.read(timeout=0.1)
                    if not raw_bytes:
                        time.sleep(0.03)
                        continue

                    # 48kHz, 2채널(스테레오) float32 -> 모노 다운믹스
                    data = np.frombuffer(raw_bytes, dtype=np.float32).reshape(-1, 2)
                    mono_48k = data.mean(axis=1)

                    if len(mono_48k) < 3:
                        continue

                    # 48kHz -> 16kHz 다운샘플링 (1:3 정밀 폴리페이즈 필터링)
                    mono_16k = resample_poly(mono_48k, 1, 3).astype(np.float32)
                    accum_buf = np.concatenate((accum_buf, mono_16k))

                    # 버퍼 과적 방지 (최대 3초분 유지)
                    if len(accum_buf) > self.sample_rate * 3:
                        # The skipped samples break continuity with a partial utterance.
                        if speech_chunks:
                            self._enqueue_audio(np.concatenate(speech_chunks).astype(np.float32))
                        self._capture_cursor += len(accum_buf) - self.sample_rate * 3
                        speech_chunks = []
                        silence_chunks_count = 0
                        is_speaking = False
                        accum_buf = accum_buf[-self.sample_rate * 3:]

                    # 100ms (1600 샘플) 단위로 슬라이싱하여 일관된 VAD 및 STT 처리
                    while len(accum_buf) >= self.chunk_size:
                        raw_chunk = accum_buf[:self.chunk_size]
                        accum_buf = accum_buf[self.chunk_size:]

                        # 80Hz 하이패스 필터링 (float32 직접 연산으로 메모리 대역폭 50% 절감 및 배열 할당 제거)
                        filtered_audio, self.filter_state = sosfilt(self.sos, raw_chunk, zi=self.filter_state)
                        self._capture_cursor += len(filtered_audio)

                        # RMS 에너지 계산 (np.dot 기반 무할당 고속 연산)
                        rms = float(np.sqrt(np.dot(filtered_audio, filtered_audio) / len(filtered_audio)))

                        # UI 볼륨 레벨 전달
                        if self.level_callback:
                            self.level_callback(rms)

                        # Deepgram 등 실시간 WebSocket 스트리밍 엔진 모드: 100ms 프레임을 청크 버퍼링 없이 즉시 스트리밍
                        if self.config.get("stt_provider") == "deepgram":
                            speech_chunks = []
                            silence_chunks_count = 0
                            is_speaking = False
                            self._enqueue_audio(filtered_audio)
                            continue

                        max_chunks = int(self.max_buffer_sec * self.sample_rate / self.chunk_size)
                        silence_chunks_threshold = int(self.silence_duration_sec * self.sample_rate / self.chunk_size)

                        # 음성 감지 판별
                        if rms >= self.vad_threshold:
                            is_speaking = True
                            speech_chunks.append(filtered_audio)
                            silence_chunks_count = 0

                            # 긴 발화의 경우 2.2초마다 쪼개어 실시간 전송
                            if len(speech_chunks) >= max_chunks:
                                full_audio = np.concatenate(speech_chunks).astype(np.float32)
                                self._enqueue_audio(full_audio)
                                speech_chunks = []
                                is_speaking = True
                                silence_chunks_count = 0
                        else:
                            if is_speaking:
                                speech_chunks.append(filtered_audio)
                                silence_chunks_count += 1

                                # 문장 종료 침묵(약 0.3초) 감지 시 STT 큐로 즉각 전송
                                if silence_chunks_count >= silence_chunks_threshold:
                                    full_audio = np.concatenate(speech_chunks).astype(np.float32)
                                    if len(full_audio) >= int(0.05 * self.sample_rate):
                                        self._enqueue_audio(full_audio, speech_end=True)
                                    speech_chunks = []
                                    is_speaking = False
                                    silence_chunks_count = 0
                            else:
                                speech_chunks = []
                                silence_chunks_count = 0

                except Exception as e:
                    if self.running and not self._device_switch_requested:
                        print(f"[Audio] 프로세스 캡처 루프 예외: {e}")
                    time.sleep(0.05)

        except Exception as e:
            hint = ""
            try:
                # 프로그램별 캡처(WASAPI Process Loopback)는 Windows 10 2004(빌드 19041) 이상에서만 지원된다.
                if sys.platform == "win32" and sys.getwindowsversion().build < 19041:
                    hint = " (프로그램별 캡처는 Windows 10 2004 이상이 필요합니다. 오디오 장치를 '기본 장치'로 바꿔 사용하세요.)"
            except Exception:
                pass
            self._capture_failed(f"프로세스 루프백 초기화 오류: {e}{hint}")
            time.sleep(1.0)
        finally:
            self.active_capture_mode = "inactive"
            if tap:
                try:
                    tap.stop()
                    print(f"[Audio] 프로세스 캡처 정지: {app_name} (PID: {pid})")
                except Exception:
                    pass
