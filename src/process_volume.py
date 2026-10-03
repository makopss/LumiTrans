"""
Windows Core Audio (WASAPI) Process Volume Control & Real-time Audio Ducking
순수 Python ctypes 기반 무설치 Windows 볼륨 믹서 제어 및 오디오 덕킹 모듈
"""

import os
import sys
import time
import threading
import ctypes
from ctypes import wintypes, HRESULT, POINTER, Structure, c_float, c_void_p, cast, byref
import psutil

ole32 = ctypes.windll.ole32

def _safe_co_init() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        hr = ole32.CoInitialize(None)
        return hr == 0
    except Exception:
        return False

def _safe_co_uninit(need_uninit: bool):
    if need_uninit and sys.platform.startswith("win"):
        try:
            ole32.CoUninitialize()
        except Exception:
            pass


# PID -> (original_name, lower_name, timestamp) 단기 캐시 (페이딩 중 초당 수십 회 psutil 중복 쿼리 제거)
_PID_NAME_CACHE = {}
_PID_CACHE_TTL = 10.0

def _get_cached_process_name(pid: int) -> tuple[str, str]:
    """PID에 대응하는 프로세스명(original_name, lower_name)을 10초간 캐시하여 psutil 중복 쿼리 제거"""
    now = time.time()
    cached = _PID_NAME_CACHE.get(pid)
    if cached and (now - cached[2]) < _PID_CACHE_TTL:
        return cached[0], cached[1]
    try:
        orig = psutil.Process(pid).name()
        low = orig.lower()
        _PID_NAME_CACHE[pid] = (orig, low, now)
        return orig, low
    except Exception:
        return "", ""

class GUID(Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8)
    ]
    def __init__(self, guid_str=None):
        super().__init__()
        if guid_str:
            ole32.CLSIDFromString(ctypes.c_wchar_p(guid_str), byref(self))

CLSID_MMDeviceEnumerator = GUID('{BCDE0395-E52F-467C-8E3D-C4579291692E}')
IID_IMMDeviceEnumerator = GUID('{A95664D2-9614-4F35-A746-DE8DB63617E6}')
IID_IAudioSessionManager2 = GUID('{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}')
IID_IAudioSessionControl2 = GUID('{bfb7ff88-7239-4fc9-8fa2-07c950be9c6d}')
IID_ISimpleAudioVolume = GUID('{87CE5498-68D6-44E5-9215-6DA47EF883D8}')

class IUnknownVtbl(Structure):
    _fields_ = [
        ('QueryInterface', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))),
        ('AddRef', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('Release', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
    ]

class IMMDeviceEnumeratorVtbl(Structure):
    _fields_ = [
        ('QueryInterface', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))),
        ('AddRef', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('Release', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('EnumAudioEndpoints', c_void_p),
        ('GetDefaultAudioEndpoint', ctypes.WINFUNCTYPE(HRESULT, c_void_p, wintypes.DWORD, wintypes.DWORD, POINTER(c_void_p))),
    ]

class IMMDeviceVtbl(Structure):
    _fields_ = [
        ('QueryInterface', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))),
        ('AddRef', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('Release', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('Activate', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p))),
    ]

class IAudioSessionManager2Vtbl(Structure):
    _fields_ = [
        ('QueryInterface', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))),
        ('AddRef', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('Release', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('GetAudioSessionControl', c_void_p),
        ('GetSimpleAudioVolume', c_void_p),
        ('GetSessionEnumerator', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p))),
    ]

class IAudioSessionEnumeratorVtbl(Structure):
    _fields_ = [
        ('QueryInterface', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))),
        ('AddRef', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('Release', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('GetCount', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(ctypes.c_int))),
        ('GetSession', ctypes.WINFUNCTYPE(HRESULT, c_void_p, ctypes.c_int, POINTER(c_void_p))),
    ]

class IAudioSessionControl2Vtbl(Structure):
    _fields_ = [
        ('QueryInterface', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))),
        ('AddRef', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('Release', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('GetState', c_void_p),
        ('GetDisplayName', c_void_p),
        ('SetDisplayName', c_void_p),
        ('GetIconPath', c_void_p),
        ('SetIconPath', c_void_p),
        ('GetGroupingParam', c_void_p),
        ('SetGroupingParam', c_void_p),
        ('RegisterAudioSessionNotification', c_void_p),
        ('UnregisterAudioSessionNotification', c_void_p),
        ('GetSessionIdentifier', c_void_p),
        ('GetSessionInstanceIdentifier', c_void_p),
        ('GetProcessId', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(wintypes.DWORD))),
        ('IsSystemSoundsSession', c_void_p),
        ('SetDuckingPreference', c_void_p),
    ]

class ISimpleAudioVolumeVtbl(Structure):
    _fields_ = [
        ('QueryInterface', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))),
        ('AddRef', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('Release', ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ('SetMasterVolume', ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_float, POINTER(GUID))),
        ('GetMasterVolume', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_float))),
        ('SetMute', ctypes.WINFUNCTYPE(HRESULT, c_void_p, wintypes.BOOL, POINTER(GUID))),
        ('GetMute', ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(wintypes.BOOL))),
    ]

class ComObject:
    def __init__(self, ptr, vtbl_cls):
        self.ptr = ptr
        self.vtbl = cast(cast(ptr, POINTER(c_void_p)).contents, POINTER(vtbl_cls)).contents

    def Release(self):
        if self.ptr:
            try:
                self.vtbl.Release(self.ptr)
            except Exception:
                pass
            self.ptr = None


def set_process_volume(target_name_or_pid, volume: float) -> bool:
    """
    Windows 볼륨 믹서 레벨에서 특정 앱(whale.exe, chrome.exe 등)의 사운드 볼륨을 0.0 ~ 1.0으로 직접 조절
    """
    if not sys.platform.startswith("win"):
        return False

    volume = max(0.0, min(1.0, float(volume)))
    need_uninit = _safe_co_init()
    try:
        enumerator_ptr = c_void_p()
        hr = ole32.CoCreateInstance(
            byref(CLSID_MMDeviceEnumerator), None, 1,
            byref(IID_IMMDeviceEnumerator), byref(enumerator_ptr)
        )
        if hr != 0 or not enumerator_ptr:
            return False

        enumerator = ComObject(enumerator_ptr, IMMDeviceEnumeratorVtbl)
        device_ptr = c_void_p()
        hr = enumerator.vtbl.GetDefaultAudioEndpoint(enumerator.ptr, 0, 1, byref(device_ptr))
        if hr != 0 or not device_ptr:
            enumerator.Release()
            return False

        device = ComObject(device_ptr, IMMDeviceVtbl)
        mgr_ptr = c_void_p()
        hr = device.vtbl.Activate(device.ptr, byref(IID_IAudioSessionManager2), 23, None, byref(mgr_ptr))
        if hr != 0 or not mgr_ptr:
            device.Release()
            enumerator.Release()
            return False

        mgr = ComObject(mgr_ptr, IAudioSessionManager2Vtbl)
        session_enum_ptr = c_void_p()
        hr = mgr.vtbl.GetSessionEnumerator(mgr.ptr, byref(session_enum_ptr))
        if hr != 0 or not session_enum_ptr:
            mgr.Release()
            device.Release()
            enumerator.Release()
            return False

        session_enum = ComObject(session_enum_ptr, IAudioSessionEnumeratorVtbl)
        count = ctypes.c_int()
        session_enum.vtbl.GetCount(session_enum.ptr, byref(count))

        target_str = str(target_name_or_pid or "default").lower()
        if target_str.startswith("process:"):
            target_str = target_str.replace("process:", "")

        is_all_non_system = (target_str in ("default", "all", ""))
        my_pid = os.getpid()
        matched_count = 0

        for i in range(count.value):
            sess_ctrl_ptr = c_void_p()
            if session_enum.vtbl.GetSession(session_enum.ptr, i, byref(sess_ctrl_ptr)) == 0 and sess_ctrl_ptr:
                sess_ctrl = ComObject(sess_ctrl_ptr, IUnknownVtbl)
                ctrl2_ptr = c_void_p()
                if sess_ctrl.vtbl.QueryInterface(sess_ctrl.ptr, byref(IID_IAudioSessionControl2), byref(ctrl2_ptr)) == 0 and ctrl2_ptr:
                    ctrl2 = ComObject(ctrl2_ptr, IAudioSessionControl2Vtbl)
                    pid = wintypes.DWORD()
                    ctrl2.vtbl.GetProcessId(ctrl2.ptr, byref(pid))
                    
                    is_match = False
                    if is_all_non_system:
                        # LumiTrans 자체(더빙 출력)는 제외하고 나머지 미디어 앱 감쇄
                        if pid.value != 0 and pid.value != my_pid:
                            is_match = True
                    elif str(target_name_or_pid) == str(pid.value):
                        is_match = True
                    else:
                        _, p_name = _get_cached_process_name(pid.value)
                        if p_name and (target_str in p_name or p_name in target_str):
                            is_match = True

                    if is_match:
                        vol_ptr = c_void_p()
                        if sess_ctrl.vtbl.QueryInterface(sess_ctrl.ptr, byref(IID_ISimpleAudioVolume), byref(vol_ptr)) == 0 and vol_ptr:
                            vol = ComObject(vol_ptr, ISimpleAudioVolumeVtbl)
                            vol.vtbl.SetMasterVolume(vol.ptr, c_float(volume), None)
                            matched_count += 1
                            vol.Release()

                    ctrl2.Release()
                sess_ctrl.Release()

        session_enum.Release()
        mgr.Release()
        device.Release()
        enumerator.Release()
        return matched_count > 0
    except Exception:
        return False
    finally:
        _safe_co_uninit(need_uninit)


def get_active_audio_processes() -> list:
    """
    Windows Core Audio (WASAPI) 세션을 순회하여
    현재 오디오 세션이 열려 있는 프로세스 목록을 반환.
    """
    if not sys.platform.startswith("win"):
        return []

    results = []
    seen_names = set()
    try:
        my_pid = os.getpid()
    except Exception:
        my_pid = 0

    need_uninit = _safe_co_init()
    try:
        enumerator_ptr = c_void_p()
        hr = ole32.CoCreateInstance(
            byref(CLSID_MMDeviceEnumerator), None, 1,
            byref(IID_IMMDeviceEnumerator), byref(enumerator_ptr)
        )
        if hr != 0 or not enumerator_ptr:
            return []

        enumerator = ComObject(enumerator_ptr, IMMDeviceEnumeratorVtbl)
        device_ptr = c_void_p()
        hr = enumerator.vtbl.GetDefaultAudioEndpoint(enumerator.ptr, 0, 1, byref(device_ptr))
        if hr != 0 or not device_ptr:
            enumerator.Release()
            return []

        device = ComObject(device_ptr, IMMDeviceVtbl)
        mgr_ptr = c_void_p()
        hr = device.vtbl.Activate(device.ptr, byref(IID_IAudioSessionManager2), 23, None, byref(mgr_ptr))
        if hr != 0 or not mgr_ptr:
            device.Release()
            enumerator.Release()
            return []

        mgr = ComObject(mgr_ptr, IAudioSessionManager2Vtbl)
        session_enum_ptr = c_void_p()
        hr = mgr.vtbl.GetSessionEnumerator(mgr.ptr, byref(session_enum_ptr))
        if hr != 0 or not session_enum_ptr:
            mgr.Release()
            device.Release()
            enumerator.Release()
            return []

        session_enum = ComObject(session_enum_ptr, IAudioSessionEnumeratorVtbl)
        count = ctypes.c_int()
        session_enum.vtbl.GetCount(session_enum.ptr, byref(count))

        for i in range(count.value):
            sess_ctrl_ptr = c_void_p()
            if session_enum.vtbl.GetSession(session_enum.ptr, i, byref(sess_ctrl_ptr)) == 0 and sess_ctrl_ptr:
                sess_ctrl = ComObject(sess_ctrl_ptr, IUnknownVtbl)
                ctrl2_ptr = c_void_p()
                if sess_ctrl.vtbl.QueryInterface(sess_ctrl.ptr, byref(IID_IAudioSessionControl2), byref(ctrl2_ptr)) == 0 and ctrl2_ptr:
                    ctrl2 = ComObject(ctrl2_ptr, IAudioSessionControl2Vtbl)
                    pid = wintypes.DWORD()
                    ctrl2.vtbl.GetProcessId(ctrl2.ptr, byref(pid))
                    
                    if pid.value != 0 and pid.value != my_pid:
                        p_name, p_lower = _get_cached_process_name(pid.value)
                        if p_lower and p_lower not in seen_names:
                            seen_names.add(p_lower)
                            results.append({
                                "pid": pid.value,
                                "name": p_lower,
                                "original_name": p_name
                            })
                    ctrl2.Release()
                sess_ctrl.Release()

        session_enum.Release()
        mgr.Release()
        device.Release()
        enumerator.Release()
        return results
    except Exception:
        return results
    finally:
        _safe_co_uninit(need_uninit)


def get_process_volume(target_name_or_pid) -> float:
    """특정 프로세스의 현재 마스터 볼륨 (0.0 ~ 1.0) 조회"""
    if not sys.platform.startswith("win"):
        return 1.0

    need_uninit = _safe_co_init()
    try:
        enumerator_ptr = c_void_p()
        hr = ole32.CoCreateInstance(
            byref(CLSID_MMDeviceEnumerator), None, 1,
            byref(IID_IMMDeviceEnumerator), byref(enumerator_ptr)
        )
        if hr != 0 or not enumerator_ptr:
            return 1.0

        enumerator = ComObject(enumerator_ptr, IMMDeviceEnumeratorVtbl)
        device_ptr = c_void_p()
        hr = enumerator.vtbl.GetDefaultAudioEndpoint(enumerator.ptr, 0, 1, byref(device_ptr))
        if hr != 0 or not device_ptr:
            enumerator.Release()
            return 1.0

        device = ComObject(device_ptr, IMMDeviceVtbl)
        mgr_ptr = c_void_p()
        hr = device.vtbl.Activate(device.ptr, byref(IID_IAudioSessionManager2), 23, None, byref(mgr_ptr))
        if hr != 0 or not mgr_ptr:
            device.Release()
            enumerator.Release()
            return 1.0

        mgr = ComObject(mgr_ptr, IAudioSessionManager2Vtbl)
        session_enum_ptr = c_void_p()
        hr = mgr.vtbl.GetSessionEnumerator(mgr.ptr, byref(session_enum_ptr))
        if hr != 0 or not session_enum_ptr:
            mgr.Release()
            device.Release()
            enumerator.Release()
            return 1.0

        session_enum = ComObject(session_enum_ptr, IAudioSessionEnumeratorVtbl)
        count = ctypes.c_int()
        session_enum.vtbl.GetCount(session_enum.ptr, byref(count))

        target_str = str(target_name_or_pid or "default").lower()
        if target_str.startswith("process:"):
            target_str = target_str.replace("process:", "")

        val = 1.0
        for i in range(count.value):
            sess_ctrl_ptr = c_void_p()
            if session_enum.vtbl.GetSession(session_enum.ptr, i, byref(sess_ctrl_ptr)) == 0 and sess_ctrl_ptr:
                sess_ctrl = ComObject(sess_ctrl_ptr, IUnknownVtbl)
                ctrl2_ptr = c_void_p()
                if sess_ctrl.vtbl.QueryInterface(sess_ctrl.ptr, byref(IID_IAudioSessionControl2), byref(ctrl2_ptr)) == 0 and ctrl2_ptr:
                    ctrl2 = ComObject(ctrl2_ptr, IAudioSessionControl2Vtbl)
                    pid = wintypes.DWORD()
                    ctrl2.vtbl.GetProcessId(ctrl2.ptr, byref(pid))
                    
                    is_match = False
                    if str(target_name_or_pid) == str(pid.value):
                        is_match = True
                    else:
                        _, p_name = _get_cached_process_name(pid.value)
                        if p_name and (target_str in p_name or p_name in target_str):
                            is_match = True

                    if is_match:
                        vol_ptr = c_void_p()
                        if sess_ctrl.vtbl.QueryInterface(sess_ctrl.ptr, byref(IID_ISimpleAudioVolume), byref(vol_ptr)) == 0 and vol_ptr:
                            vol = ComObject(vol_ptr, ISimpleAudioVolumeVtbl)
                            cur_vol = c_float(1.0)
                            vol.vtbl.GetMasterVolume(vol.ptr, byref(cur_vol))
                            val = float(cur_vol.value)
                            vol.Release()
                            ctrl2.Release()
                            sess_ctrl.Release()
                            break

                    ctrl2.Release()
                sess_ctrl.Release()

        session_enum.Release()
        mgr.Release()
        device.Release()
        enumerator.Release()
        return val
    except Exception:
        return 1.0
    finally:
        _safe_co_uninit(need_uninit)


def ducking_poll_interval(fading: bool) -> float:
    """볼륨이 움직이는 동안만 40Hz로 보간하고, 멈춘 뒤에는 저속 대기로 CPU를 놓는다."""
    return 0.025 if fading else 0.35


class AudioDuckingManager(threading.Thread):
    """
    더빙 음성(TTS) 발화 상태를 실시간 모니터링하여 원본 사운드 볼륨을 자동 감쇄(Ducking) 및 복원하는 매니저
    - 텍스트 큐, 선행 합성 중 상태, 재생 대기열, 오디오 채널을 통합 모니터링하여 문장 간 출렁임(Fluttering) 원천 방지
    - 급격한 볼륨 점프 대신 부드러운 선형 페이드(Fade Attack ~80ms, Fade Release ~280ms) 적용
    - 발화 완료 후 1.0초 홀드 타임(Hysteresis)으로 자연스러운 문장 간 호흡 보존
    """
    def __init__(self, dubbing_engine, config, target_name_or_pid=None):
        super().__init__(daemon=True, name="AudioDuckingManager")
        self.dubbing_engine = dubbing_engine
        self.config = config
        self.running = True
        self.target_process = target_name_or_pid or self.config.get("audio_capture_device", "default")
        self.original_volume = max(0.0, min(1.0, float(self.config.get("original_volume", 100)) / 100.0))
        self.ducking_volume = max(0.0, min(1.0, float(self.config.get("audio_ducking_volume", 20)) / 100.0))
        self.ducking_enabled = self.config.get("audio_ducking_enabled", True)
        self.current_volume = self.original_volume
        self.is_ducked = False
        self._last_active_time = 0.0
        self._sync_counter = 0
        self._last_volume_sync = 0.0
        self._lock = threading.Lock()

        # 시작 즉시 브라우저/미디어의 볼륨을 사용자가 지정한 original_volume으로 강제 동기화
        # (이전 세션의 비정상 종료나 20% 등 감쇄 상태에서 고착되어 시작되는 현상 방지)
        set_process_volume(self.target_process, self.original_volume)

    def reset_to_original(self):
        """새 영상 전환, 브라우저 새로고침, 또는 사용자 초기화 시 즉시 원본 볼륨으로 복원하고 덕킹 상태 리셋"""
        with self._lock:
            self.is_ducked = False
            self.current_volume = self.original_volume
            self._last_active_time = 0.0
            self._sync_counter = 0
            self._last_volume_sync = 0.0
            set_process_volume(self.target_process, self.original_volume)

    def set_target_process(self, proc_name_or_id):
        with self._lock:
            if self.target_process != proc_name_or_id:
                if self.is_ducked:
                    set_process_volume(self.target_process, self.original_volume)
                    self.is_ducked = False
                self.target_process = proc_name_or_id
                self.current_volume = self.original_volume
                set_process_volume(self.target_process, self.original_volume)

    def set_original_volume(self, vol_pct: int):
        with self._lock:
            self.original_volume = max(0.0, min(1.0, float(vol_pct) / 100.0))
            if not self.is_ducked:
                self.current_volume = self.original_volume
                set_process_volume(self.target_process, self.original_volume)
            else:
                target_duck = self.ducking_volume if self.original_volume > 0 else 0.0
                self.current_volume = target_duck
                set_process_volume(self.target_process, target_duck)

    def set_normal_volume(self, vol_pct: int):
        self.set_original_volume(vol_pct)

    def set_ducking_volume(self, vol_pct: int):
        with self._lock:
            self.ducking_volume = max(0.0, min(1.0, float(vol_pct) / 100.0))
            if self.is_ducked:
                target_duck = self.ducking_volume if self.original_volume > 0 else 0.0
                self.current_volume = target_duck
                set_process_volume(self.target_process, target_duck)

    def set_ducking_ratio(self, ratio_pct: int):
        """하위 호환성 유지"""
        self.set_ducking_volume(ratio_pct)

    def set_ducking_enabled(self, enabled: bool):
        with self._lock:
            self.ducking_enabled = bool(enabled)
            if not self.ducking_enabled and self.is_ducked:
                self.is_ducked = False
                self.current_volume = self.original_volume
                set_process_volume(self.target_process, self.original_volume)

    def stop(self):
        self.running = False
        with self._lock:
            set_process_volume(self.target_process, self.original_volume)

    def _is_pipeline_active(self) -> bool:
        """
        더빙 파이프라인 전체(재생 중, 재생 큐 대기, TTS 합성 중, 번역 텍스트 대기)의 활성 상태 통합 검사.
        이를 통해 대사 간 합성 지연(0.2~0.6초) 동안 원본 볼륨이 갑자기 튀어 오르는 현상을 완벽 차단.
        """
        if not self.dubbing_engine or not getattr(self.dubbing_engine, 'is_enabled', lambda: False)():
            return False

        # 1. 오디오 재생 중이거나 직후 잔향
        if self.dubbing_engine.is_speaking(grace_period=0.4):
            return True

        # 2. 재생 대기열에 오디오 존재
        pq = getattr(self.dubbing_engine, 'playback_queue', None)
        if pq and pq.qsize() > 0:
            return True

        # 3. 선행 합성 워커가 현재 TTS 합성 중
        if getattr(self.dubbing_engine, '_current_synthesizing_item', None) is not None:
            return True

        # 4. 텍스트 대기열에 대기 중인 대사 존재
        tq = getattr(self.dubbing_engine, 'text_queue', None)
        if tq and tq.qsize() > 0:
            return True

        return False

    def run(self):
        need_uninit = _safe_co_init()
        try:
            while self.running:
                try:
                    if not self.running:
                        break

                    fading = False
                    with self._lock:
                        ducking_on = (
                            self.ducking_enabled
                            and self.dubbing_engine
                            and getattr(self.dubbing_engine, 'is_enabled', lambda: False)()
                        )
                        if not ducking_on:
                            if self.is_ducked or abs(self.current_volume - self.original_volume) > 0.01:
                                self.is_ducked = False
                                self._fade_towards(self.original_volume, step=0.08)
                                fading = abs(self.current_volume - self.original_volume) > 0.01
                        else:
                            pipeline_active = self._is_pipeline_active()
                            now = time.time()

                            if pipeline_active:
                                self._last_active_time = now
                                self.is_ducked = True
                            else:
                                # 모든 파이프라인이 비어있더라도 1.0초 동안은 홀드하여 단문 간 볼륨 급변 방지
                                if self.is_ducked and (now - self._last_active_time) >= 1.0:
                                    self.is_ducked = False

                            # 목표 볼륨 결정
                            if self.is_ducked:
                                # 감쇄 목표는 100% 원본 스케일 기준 독립적인 절대 볼륨으로 작동 (원본 음량이 0이면 음소거 유지)
                                target_vol = self.ducking_volume if self.original_volume > 0 else 0.0
                                fade_step = 0.12  # 덕킹 진입: 약 60~80ms 신속하고 매끄러운 감쇄
                            else:
                                target_vol = self.original_volume
                                fade_step = 0.05  # 덕킹 복귀: 약 250~300ms 부드럽고 자연스러운 복원

                            self._fade_towards(target_vol, step=fade_step)
                            fading = abs(self.current_volume - target_vol) > 0.01

                            # 브라우저 새 탭, 새로고침, 새 영상 로드 시 WASAPI 세션 재생성/볼륨 불일치 자동 감지
                            # 안정 상태에서는 세션 전체를 매 25ms가 아니라 1초 간격으로만 조회한다.
                            if now - self._last_volume_sync >= 1.0:
                                self._last_volume_sync = now
                                actual_vol = get_process_volume(self.target_process)
                                if abs(actual_vol - self.current_volume) > 0.05:
                                    set_process_volume(self.target_process, self.current_volume)

                    # 덕킹이 꺼져 있고 볼륨이 안정되면 40Hz 폴링을 멈춘다.
                    # 덕킹이 켜져 있으면 발화 반응을 위해 25ms를 유지한다.
                    time.sleep(ducking_poll_interval(fading or ducking_on))

                except Exception:
                    time.sleep(0.05)
        finally:
            _safe_co_uninit(need_uninit)

    def _fade_towards(self, target_vol: float, step: float = 0.05):
        """현재 볼륨을 목표 볼륨으로 부드럽게 점진적 보간"""
        diff = target_vol - self.current_volume
        if abs(diff) <= 0.01:
            if self.current_volume != target_vol:
                self.current_volume = target_vol
                set_process_volume(self.target_process, self.current_volume)
            return

        if diff > 0:
            self.current_volume = min(target_vol, self.current_volume + step)
        else:
            self.current_volume = max(target_vol, self.current_volume - step)

        set_process_volume(self.target_process, self.current_volume)
