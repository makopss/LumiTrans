# -*- coding: utf-8 -*-
"""
youtube_helper.py - 유튜브 자동 감지 및 초고속 자막/메타데이터 추출 모듈
Windows UI Automation을 통한 브라우저(Whale, Chrome, Edge 등) 주소창 탐색 및 youtube-transcript-api 연동
"""

import os
import re
import threading
import ctypes
from typing import Optional, Dict, Any
import requests

_HTTP_SESSION = requests.Session()
_HTTP_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})


def extract_youtube_id(url_or_id: str) -> Optional[str]:
    """다양한 유튜브 URL 형식(watch, shorts, live, embed, youtu.be, 순수 ID) 정규화"""
    if not url_or_id:
        return None
    cleaned = url_or_id.strip()
    if re.fullmatch(r"[a-zA-Z0-9_\-]{11}", cleaned):
        return cleaned

    patterns = [
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/|\/live\/)([a-zA-Z0-9_\-]{11})",
        r"[?&]v=([a-zA-Z0-9_\-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, cleaned)
        if m:
            return m.group(1)
    return None


def fetch_youtube_metadata(video_id: str) -> Dict[str, str]:
    """oEmbed API를 통해 영상 제목 및 채널명을 약 150ms 만에 조회 (TCP/TLS 커넥션 재사용)"""
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        res = _HTTP_SESSION.get(url, timeout=4.0)
        if res.status_code == 200:
            data = res.json()
            return {"title": data.get("title", "").strip(), "author": data.get("author_name", "").strip()}
    except Exception as e:
        print(f"[YouTubeHelper] oEmbed 메타데이터 조회 예외: {e}")
    return {"title": "", "author": ""}


def transcript_language_order(source_lang: str = "en") -> list:
    """인식 언어를 먼저 두고, 없을 때만 영어 자막으로 내려간다."""
    raw = (source_lang or "en").strip()
    if raw.lower() in ("", "auto", "none"):
        raw = "en"
    primary = raw.split("-")[0].lower()
    region = raw.split("-", 1)[1].upper() if "-" in raw else ""
    codes = [primary]
    if region:
        codes.append(f"{primary}-{region}")
    if primary == "en":
        codes.extend(["en-US", "en-GB"])
    else:
        codes.extend(["en", "en-US", "en-GB"])
    ordered = []
    for code in codes:
        if code not in ordered:
            ordered.append(code)
    return ordered


def fetch_youtube_transcript(video_id: str, source_lang: str = "en") -> Optional[str]:
    """영상 원문 언어의 자막을 우선 추출하고, 없으면 영어 자막을 사용한다."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        languages = transcript_language_order(source_lang)
        primary = languages[0]

        try:
            snippets = api.fetch(video_id, languages=languages)
        except Exception:
            try:
                transcripts = list(api.list(video_id))
                snippets = None
                for prefix in (primary, "en"):
                    for transcript in transcripts:
                        if str(getattr(transcript, "language_code", "")).lower().startswith(prefix):
                            snippets = transcript.fetch()
                            break
                    if snippets:
                        break
                if not snippets and transcripts:
                    snippets = transcripts[0].fetch()
            except Exception:
                snippets = None

        if not snippets:
            return None

        clean_lines = []
        for s in snippets:
            raw_t = getattr(s, "text", "") if hasattr(s, "text") else s.get("text", "")
            # 특수 효과음, 음악 기호([Music], [♪] 등) 정제
            filtered = re.sub(r"^\[.*?\]$", "", raw_t.strip())
            filtered = re.sub(r"^[♪♩♫♬].*?[♪♩♫♬]$", "", filtered.strip())
            filtered = filtered.replace("\n", " ").strip()
            if filtered:
                clean_lines.append(filtered)

        full_text = " ".join(clean_lines)
        return full_text[:40000] if len(full_text) > 40000 else full_text
    except Exception as e:
        print(f"[YouTubeHelper] 자막 추출 안내: {e}")
        return None


def fetch_youtube_full_data(url_or_id: str, source_lang: str = "en") -> Dict[str, Any]:
    """영상 ID, 제목, 채널명, 자막 전문 일괄 취득"""
    vid = extract_youtube_id(url_or_id)
    if not vid:
        return {"success": False, "error": "유효하지 않은 URL"}

    meta = fetch_youtube_metadata(vid)
    transcript = fetch_youtube_transcript(vid, source_lang=source_lang)

    return {
        "success": True,
        "video_id": vid,
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "transcript": transcript or "",
        "has_transcript": bool(transcript)
    }


# 같은 유튜브 창 제목이면 UI Automation 트리 순회를 반복하지 않는다.
# Chromium 접근성 트리는 한 번 훑는 동안에도 CPU를 크게 쓴다.
_youtube_title_cache = {"titles": None, "url": None}
_youtube_scan_lock = threading.Lock()


def _collect_youtube_windows():
    """보이는 브라우저 창 중 제목에 youtube가 있는 창만 (hwnd, title)로 모은다."""
    if os.name != "nt":
        return []
    windows = []
    try:
        user32 = ctypes.windll.user32
        fg_hwnd = user32.GetForegroundWindow()

        def enum_cb(h, _):
            if user32.IsWindowVisible(h):
                length = user32.GetWindowTextLengthW(h)
                if length > 4:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buf, length + 1)
                    title = buf.value
                    title_lower = title.lower()
                    # 타이틀에 youtube가 없는 일반 브라우저 창의 UIA DOM 순회는 하지 않는다.
                    if "youtube" in title_lower and any(b in title_lower for b in ("whale", "chrome", "edge", "firefox", "brave", "youtube")):
                        if h == fg_hwnd:
                            windows.insert(0, (h, title))
                        else:
                            windows.append((h, title))
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    except Exception:
        return []
    return windows


def _read_youtube_url_from_windows(hwnds) -> Optional[str]:
    """후보 창의 주소창만 UI Automation으로 읽는다."""
    if not hwnds or os.name != "nt":
        return None
    try:
        ctypes.windll.ole32.CoInitialize(None)
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation, TreeScope_Descendants

        uia = comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
        cond_edit = uia.CreatePropertyCondition(30003, 50004)  # UIA_EditControlTypeId
        cond_ff = uia.CreatePropertyCondition(30011, "urlbar-input")  # Firefox
        or_cond = uia.CreateOrCondition(cond_edit, cond_ff)

        for hwnd in hwnds:
            try:
                elem = uia.ElementFromHandle(hwnd)
                if not elem:
                    continue
                first = elem.FindFirst(TreeScope_Descendants, or_cond)
                if first:
                    for prop_id in (30045, 30092, 30005):  # Value, Name, HelpText
                        try:
                            val = first.GetCurrentPropertyValue(prop_id)
                            if val and isinstance(val, str) and "youtube" in val.lower():
                                vid = extract_youtube_id(val)
                                if vid:
                                    return f"https://www.youtube.com/watch?v={vid}"
                        except Exception:
                            pass
            except Exception:
                continue
    except Exception:
        return None
    finally:
        try:
            ctypes.windll.ole32.CoUninitialize()
        except Exception:
            pass
    return None


def find_youtube_url_from_browser(timeout: float = 1.0) -> Optional[str]:
    """Windows UI Automation을 통해 브라우저(Whale, Chrome, Edge, Firefox 등) 주소창의 YouTube URL 감지"""
    if os.name != "nt":
        return None

    windows = _collect_youtube_windows()
    titles = tuple(sorted(title for _hwnd, title in windows))
    if titles == _youtube_title_cache["titles"]:
        return _youtube_title_cache["url"]

    hwnds = [hwnd for hwnd, _title in windows]
    if not hwnds:
        _youtube_title_cache["titles"] = titles
        _youtube_title_cache["url"] = None
        return None

    # 이전 주소창 순회가 아직 끝나지 않았으면 또 시작하지 않는다.
    if not _youtube_scan_lock.acquire(blocking=False):
        return _youtube_title_cache["url"]

    result = [None]

    def _worker():
        try:
            result[0] = _read_youtube_url_from_windows(hwnds)
            _youtube_title_cache["titles"] = titles
            _youtube_title_cache["url"] = result[0]
        finally:
            _youtube_scan_lock.release()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        return _youtube_title_cache["url"]
    return result[0]


def get_clipboard_youtube_url() -> Optional[str]:
    """클립보드에서 유튜브 URL 감지"""
    text = ""
    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if user32.OpenClipboard(0):
                try:
                    h_glb = user32.GetClipboardData(13)  # CF_UNICODETEXT
                    if h_glb:
                        kernel32.GlobalLock.restype = ctypes.c_void_p
                        ptr = kernel32.GlobalLock(h_glb)
                        if ptr:
                            text = ctypes.wstring_at(ptr).strip()
                            kernel32.GlobalUnlock(h_glb)
                finally:
                    user32.CloseClipboard()
        except Exception:
            pass

    # 일반 텍스트(영단어, 임의 문자열 등)의 오인식을 방지하기 위해 유튜브 도메인이 포함된 경우에만 클립보드 감지
    if text and any(domain in text.lower() for domain in ("youtube.com", "youtu.be")):
        vid = extract_youtube_id(text)
        if vid:
            return f"https://www.youtube.com/watch?v={vid}"
    return None


def auto_detect_youtube_url() -> Optional[str]:
    """브라우저 주소창만 본다. 백그라운드 감시가 클립보드를 열지 않는다."""
    return find_youtube_url_from_browser(timeout=1.0)
