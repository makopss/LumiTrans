import sys
import os
import queue

# 실행 파일(frozen) 환경에서 앱 설치 경로로 작업 디렉터리 고정 및 기본 디렉터리 보장
if getattr(sys, "frozen", False):
    base_dir = os.path.dirname(os.path.abspath(sys.executable))
    os.chdir(base_dir)

# 모든 환경(frozen/소스 실행/Lite/Full)에서 CUDA, cuBLAS, llama_cpp 등 GPU 가속 필수 DLL 경로 통합 등록
try:
    from src.cuda_utils import register_cuda_dll_directories, configure_llama_backend
    register_cuda_dll_directories()
    configure_llama_backend()
except Exception as _e:
    pass

try:
    from src.app_paths import roaming_data_dir
    _LOG_DIR = roaming_data_dir()
except Exception:
    app_data = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    _LOG_DIR = os.path.join(app_data, "LumiTrans")
    os.makedirs(_LOG_DIR, exist_ok=True)
_CRASH_LOG = os.path.join(_LOG_DIR, "crash.log")

# 배포판은 콘솔 없이(GUI 모드) 실행되어 sys.stdout/stderr 가 None 이다. 이때 로그는 파일로 남긴다.
# "--console" 옵션(시작 메뉴의 '디버그 모드' 바로가기)으로 실행하면 콘솔 창을 새로 열어 실시간 로그도 보여 준다.
_CONSOLE_MODE = "--console" in sys.argv
if _CONSOLE_MODE:
    sys.argv = [a for a in sys.argv if a != "--console"]


def _open_log(name):
    path = os.path.join(_LOG_DIR, name)
    try:
        # 계속 쌓이지 않도록 5MB 를 넘으면 한 세대만 보관하고 새로 시작한다.
        if os.path.exists(path) and os.path.getsize(path) > 5_000_000:
            os.replace(path, path + ".1")
        return open(path, "a", encoding="utf-8", buffering=1)
    except Exception:
        return open(os.devnull, "w", encoding="utf-8")


class _Tee:
    """콘솔과 로그 파일에 동시에 기록한다."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
            except Exception:
                pass
        return len(data)

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    @property
    def encoding(self):
        return "utf-8"

    def fileno(self):
        # faulthandler 등 OS 수준 핸들이 필요한 라이브러리는 로그 파일에 기록한다.
        return self._streams[-1].fileno()

    def __getattr__(self, name):
        return getattr(self._streams[-1], name)


_console_stream = None
if _CONSOLE_MODE and sys.platform == "win32" and sys.stdout is None:
    try:
        import ctypes
        ctypes.windll.kernel32.AllocConsole()
        ctypes.windll.kernel32.SetConsoleTitleW("LumiTrans 디버그 콘솔 (이 창을 닫으면 앱도 종료됩니다)")
        _console_stream = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        _console_stream = None

if sys.stdout is None:
    _out = _open_log("stdout.log")
    sys.stdout = _Tee(_console_stream, _out) if _console_stream else _out
if sys.stderr is None:
    _err = _open_log("stderr.log")
    sys.stderr = _Tee(_console_stream, _err) if _console_stream else _err

# ONNX Runtime 및 OpenMP 연산 스레드 상한 제한 (CPU 90% 폭주 방지 및 안정화)
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["ORT_NUM_THREADS"] = "2"

# Windows 콘솔 UTF-8 출력 보장 (cp949 터미널에서도 특수문자/이모지로 인한 UnicodeEncodeError 원천 방지)
if sys.platform == "win32":
    for _stream_name in ("stdout", "stderr"):
        _s = getattr(sys, _stream_name, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
            except Exception:
                pass

# HF_HOME 환경변수 동기화 (Windows 레지스트리 / 공용 모델 저장소 우선 연동)
if not os.environ.get("HF_HOME") and sys.platform == "win32":
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            hf_val, _ = winreg.QueryValueEx(key, "HF_HOME")
            if hf_val and os.path.exists(hf_val):
                os.environ["HF_HOME"] = hf_val
    except Exception:
        pass

# 프로그램 비정상 종료 시 에러 원인을 명확히 출력하고 crash.log에 기록하는 글로벌 예외 핸들러
def _global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    import traceback
    import datetime
    try:
        print("\n[CRITICAL ERROR] 심각한 예외 발생", file=sys.stderr)
        traceback.print_exception(exc_type, exc_value, exc_traceback)
    except Exception:
        pass
    try:
        with open(_CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] [CRITICAL] 메인 스레드 심각한 예외:\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    except Exception:
        pass

sys.excepthook = _global_exception_handler

import threading
def _thread_exception_handler(args):
    import traceback
    import datetime
    try:
        print(f"\n[THREAD ERROR] 스레드 예외 발생: {args.thread.name}", file=sys.stderr)
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    except Exception:
        pass
    try:
        with open(_CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] [THREAD ERROR] 스레드({args.thread.name}) 예외:\n")
            traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=f)
    except Exception:
        pass

threading.excepthook = _thread_exception_handler

# 1. Qt 애플리케이션을 최우선 초기화 (COM 스레드 충돌 경고 방지)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

app = QApplication(sys.argv)
app.setFont(QFont("Malgun Gothic", 11))

# 다크 퓨전 팔레트 및 프리미엄 QSS 전역 적용
from src.ui_theme import apply_dark_theme
apply_dark_theme(app)

# 마우스 휠 스크롤로 인한 풀다운(QComboBox) 옵션 변경 전역 원천 차단
from src.no_wheel_combobox import NoWheelFilter
app.installEventFilter(NoWheelFilter(app))

# 2. 프리미엄 스플래시 스크린 즉시 표시
from src.splash_screen import LumiSplashScreen
splash = LumiSplashScreen()
splash.show()
splash.set_message("화면을 준비하는 중...", 5)

# 3. 오디오 및 AI 모듈 로드
splash.set_message("설정 모듈을 불러오는 중...", 12)
from src.config import load_config, save_config
splash.set_message("음성인식 라이브러리를 불러오는 중...", 20)
from src.audio_capture import AudioLoopbackCapture
from src.stt_engine import STTWorker
splash.set_message("자막·화면 번역 모듈을 불러오는 중...", 28)
from src.overlay_window import SubtitleOverlay
from src.screen_overlay_manager import ScreenOverlayManager
from src.screen_ocr_worker import ScreenOCRWorker
from src.screen_capture import _ensure_gui_bridge
_ensure_gui_bridge()
from src.inplace_translator import InPlaceTranslatorManager
from src.control_panel import ControlPanel
from src.roi_border_overlay import ROIBorderManager
from src.dubbing_engine import DubbingEngine

def main():
    print("=" * 60)
    print("[START] 루미트랜스 (LumiTrans) - AI 실시간 음성 & 화면 번역 시작 중...")
    print("=" * 60)

    # 설정 로드
    splash.set_message("환경 설정을 불러오는 중...", 34)
    config = load_config()
    from src.i18n import set_ui_language
    set_ui_language(config.get("ui_lang", "ko"))

    # 오디오 큐 생성
    audio_queue = queue.Queue(maxsize=32)

    # 1. 오디오 자막 오버레이 창 생성
    splash.set_message("자막 오버레이를 준비하는 중...", 40)
    overlay = SubtitleOverlay(config, on_config_change=save_config)

    # 2. 화면 번역 전용 자막 오버레이 통합 관리자 생성 (다중 ROI 1:1 독립 자막창 및 밀착 지원)
    splash.set_message("화면 자막 창을 준비하는 중...", 46)
    screen_overlay = ScreenOverlayManager(config, on_config_change=save_config)

    # 2-1. 관심 영역 외곽 테두리(엣지) 화면 오버랩 관리자 생성
    roi_border_manager = ROIBorderManager(config)

    # 3. STT & 오디오 번역 워커 스레드 초기화
    splash.set_message("음성인식 엔진을 준비하는 중...", 52)
    stt_worker = STTWorker(
        audio_queue=audio_queue,
        subtitle_callback=overlay.update_subtitle_signal.emit,
        preview_callback=overlay.update_preview_signal.emit,
        config=config,
        progress_callback=splash.set_message
    )

    # 3-1. 실시간 AI 음성 더빙 엔진 초기화 (Edge-TTS 비동기 스트리밍)
    splash.set_message("더빙 엔진을 준비하는 중...", 72)
    dubbing_engine = DubbingEngine(
        config=config,
        speaker_identifier=getattr(stt_worker, 'speaker_identifier', None)
    )
    stt_worker.set_dubbing_engine(dubbing_engine)

    # 4. 실시간 화면 OCR 번역 워커 스레드 초기화 (동일한 RealtimeTranslator 엔진 공유)
    splash.set_message("화면 번역 워커를 준비하는 중...", 76)
    screen_worker = ScreenOCRWorker(
        config=config,
        translator=stt_worker.translator,
        stt_worker=stt_worker,
        dubbing_engine=dubbing_engine
    )
    screen_worker.subtitle_signal.connect(screen_overlay.display_subtitle)
    screen_worker.status_signal.connect(screen_overlay.display_status)

    # 4-1. 원클릭 전체화면 인플레이스 스냅샷 번역기 (F4 단축키 및 제자리 말풍선)
    # 스냅샷 캡처 시 자막창 잔상 및 컨트롤 패널 창이 찍히지 않도록 오버레이 리스트 숨김 콜백 전달
    def _get_overlays_to_hide_for_snapshot():
        return screen_overlay.get_overlays() + [overlay] + roi_border_manager.get_overlays()

    inplace_manager = InPlaceTranslatorManager(
        config=config,
        translator=stt_worker.translator,
        get_ocr_cb=screen_worker._get_ocr,
        ocr_lock=screen_worker.get_ocr_lock(),
        get_overlays_to_hide=_get_overlays_to_hide_for_snapshot
    )

    # 5. 컨트롤 패널 생성
    splash.set_message("컨트롤 패널을 만드는 중...", 84)
    control_panel = ControlPanel(
        config=config,
        overlay=overlay,
        audio_thread=None,
        stt_thread=stt_worker,
        save_config_cb=save_config,
        screen_worker=screen_worker,
        screen_overlay=screen_overlay,
        inplace_manager=inplace_manager,
        roi_border_manager=roi_border_manager,
        dubbing_engine=dubbing_engine
    )
    screen_worker.status_signal.connect(control_panel.update_screen_worker_status)

    # 오디오 캡처 스레드 초기화
    splash.set_message("오디오 캡처를 준비하는 중...", 90)
    audio_capture = AudioLoopbackCapture(
        audio_queue=audio_queue,
        level_callback=control_panel.audio_level_signal.emit,
        config=config,
        dubbing_engine=dubbing_engine
    )
    control_panel.audio_thread = audio_capture
    audio_capture.status_callback = control_panel.engine_status_signal.emit
    stt_worker.set_audio_capture(audio_capture)

    # 초기 오디오/화면 활성 상태 명시적 동기화 (기본: 정지 상태 시작, 자동 시작 옵션 켜짐 시에만 즉시 동작)
    init_audio = config.get("auto_start_audio", False)
    control_panel.set_audio_active_state(init_audio)
    init_screen = config.get("auto_start_screen", False) and config.get("screen_translate_enabled", False)
    control_panel.set_screen_active_state(init_screen)


    # 오버레이 퀵 컨트롤러와 메인 컨트롤 패널 연동
    overlay.set_external_handlers(
        on_toggle_pause=control_panel.toggle_translation,
        on_change_engine=control_panel.set_engine_by_key,
        on_open_settings=control_panel.open_from_overlay,
        on_sync_opacity=control_panel.sync_opacity_from_overlay,
        on_sync_font=control_panel.sync_font_from_overlay,
        on_visibility_change=control_panel.sync_audio_overlay_visibility,
        on_sync_click_through=control_panel.sync_click_through_from_overlay,
        on_sync_clean_text=control_panel.sync_clean_text_from_overlay,
        on_sync_show_speaker=control_panel.sync_show_speaker_from_overlay
    )

    # 화면 번역 오버레이 퀵 컨트롤러 연동
    def _toggle_screen_pause_from_overlay():
        control_panel.toggle_screen_translation()
        return not config.get("screen_translate_enabled", False)

    screen_overlay.set_external_handlers(
        on_toggle_pause=_toggle_screen_pause_from_overlay,
        on_trigger_roi=control_panel.open_roi_selector,
        on_trigger_instant=control_panel.trigger_instant_screen_ocr,
        on_trigger_inplace=lambda: control_panel.trigger_inplace_translate(from_button=True),
        on_open_settings=control_panel.open_from_overlay,
        on_sync_snap=control_panel.sync_snap_from_overlay,
        on_visibility_change=control_panel.sync_screen_overlay_visibility,
        on_sync_font=control_panel.sync_font_from_overlay,
        on_sync_opacity=control_panel.sync_opacity_from_overlay,
        on_toggle_border=control_panel.toggle_roi_border,
        on_sync_click_through=control_panel.sync_click_through_from_overlay,
        on_sync_clean_text=control_panel.sync_clean_text_from_overlay,
        on_sync_show_speaker=control_panel.sync_show_speaker_from_overlay
    )

    # 백그라운드 스레드 시작
    splash.set_message("통역 파이프라인을 시작하는 중...", 96)
    stt_worker.start()
    audio_capture.start()
    screen_worker.start()

    # 유튜브 자동 감지 및 Ground-Truth 도메인 사전 백그라운드 모니터 시작
    from src.youtube_monitor import YouTubeMonitor
    youtube_monitor = YouTubeMonitor(
        config=config,
        stt_worker=stt_worker,
        on_notify=lambda msg: overlay.update_preview_signal.emit(str(msg), "YouTube") if hasattr(overlay, 'update_preview_signal') else None
    )
    youtube_monitor.start()
    control_panel.youtube_monitor = youtube_monitor

    # 프로그램 종료 시 모든 백그라운드 스레드 및 QThread 안전 종료 통합 핸들러
    _shutdown_done = False
    def _graceful_shutdown():
        nonlocal _shutdown_done
        if _shutdown_done:
            return
        _shutdown_done = True
        print("\n[Main] 프로그램 안전 종료 처리 중 (모든 백그라운드 스레드 및 QThread 정리)...")
        try:
            control_panel.save_all_settings_before_exit()
        except Exception:
            pass
        try:
            screen_worker.stop()
        except Exception:
            pass
        try:
            inplace_manager.stop()
        except Exception:
            pass
        try:
            roi_border_manager.close()
        except Exception:
            pass
        try:
            youtube_monitor.stop()
        except Exception:
            pass
        try:
            audio_capture.stop()
        except Exception:
            pass
        try:
            stt_worker.stop()
        except Exception:
            pass
        try:
            dubbing_engine.stop()
        except Exception:
            pass
        try:
            if hasattr(control_panel, '_active_stt_worker') and control_panel._active_stt_worker:
                control_panel._active_stt_worker.stop()
            if hasattr(control_panel, '_active_worker') and control_panel._active_worker:
                control_panel._active_worker.stop()
        except Exception:
            pass
        print("[Main] 모든 백그라운드 작업 정상 정지 완료.")

    app.aboutToQuit.connect(_graceful_shutdown)

    # UI 창 표시 (가시성 및 활성 상태 반영)
    if config.get("audio_overlay_visible", True):
        overlay.show()
    else:
        overlay.hide()

    if config.get("screen_overlay_visible", True):
        screen_overlay.show()
    else:
        screen_overlay.hide()

    control_panel.show()
    control_panel.raise_()
    control_panel.activateWindow()
    splash.finish()

    print("\n[OK] LumiTrans 준비 완료! (무설치 앱 단독 캡처 & 실시간 AI 통역 가동)\n")

    # 이벤트 루프 실행
    exit_code = app.exec()

    # 종료 클린업 보장
    _graceful_shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        import datetime
        try:
            with open(_CRASH_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.datetime.now()}] [CRITICAL] main() unhandled exception:\n")
                traceback.print_exc(file=f)
        except Exception:
            pass
        sys.exit(1)
