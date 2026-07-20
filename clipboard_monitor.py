"""
剪贴板监听模块
-------------
后台轮询剪贴板变更 → 智能过滤 → 回调通知。
"""

import ctypes
import datetime
import os
import threading
import time

from config import FILTER_RULES, Config

# ── 调试日志 ────────────────────────────────────────────
_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.log")


def _log(msg: str) -> None:
    try:
        stamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {msg}\n")
    except Exception:
        pass


# ── Windows API ──────────────────────────────────────────
CF_UNICODETEXT = 13

_kernel32 = ctypes.windll.kernel32
_user32 = ctypes.windll.user32

_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
_kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

_user32.GetClipboardData.restype = ctypes.c_void_p
_user32.GetClipboardData.argtypes = [ctypes.c_uint]
_user32.OpenClipboard.argtypes = [ctypes.c_void_p]


def _read_clipboard() -> str:
    """读取 Windows 剪贴板 Unicode 文本"""
    if not _user32.OpenClipboard(None):
        _log("_read_clipboard: OpenClipboard FAILED")
        return ""

    try:
        h_data = _user32.GetClipboardData(CF_UNICODETEXT)
        if not h_data:
            # 剪贴板可能是空的，或者是非文本内容（如图片）
            return ""

        p_data = _kernel32.GlobalLock(h_data)
        if not p_data:
            _log("_read_clipboard: GlobalLock FAILED")
            return ""

        try:
            result = ctypes.wstring_at(p_data)
            return result
        finally:
            _kernel32.GlobalUnlock(h_data)
    finally:
        _user32.CloseClipboard()


def should_trigger(text: str) -> bool:
    """智能过滤：判断剪贴板内容是否应触发弹窗"""
    t = text.strip()
    if not t:
        return False

    for pattern, rule_name in FILTER_RULES:
        if pattern.match(t):
            _log(f"FILTER: skipped [{rule_name}]: {t[:60]}")
            return False

    return True


class ClipboardMonitor:
    """后台轮询剪贴板，变更+过滤通过后回调 on_text"""

    def __init__(self, on_text: callable):
        self._callback = on_text
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_text = ""
        self._last_triggered = ""

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        # 读取当前剪贴板作为基准，避免把启动前的内容当"变更"
        try:
            self._last_text = _read_clipboard()
            _log(f"monitor start, baseline clipboard: [{self._last_text[:80]}]")
        except Exception as e:
            _log(f"monitor start, baseline read error: {e}")

        self._thread = threading.Thread(
            target=self._poll_loop, name="ClipboardMonitor", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def mark_as_seen(self, text: str) -> None:
        """标记文本为'已见'，避免重复触发"""
        self._last_text = text
        self._last_triggered = text
        _log(f"mark_as_seen: [{text[:60]}]")

    def _poll_loop(self) -> None:
        _log("poll loop started")
        while self._running:
            try:
                text = _read_clipboard()
            except Exception as e:
                _log(f"poll: read error: {e}")
                time.sleep(Config.POLL_INTERVAL)
                continue

            # 去重：没变化
            if text == self._last_text:
                time.sleep(Config.POLL_INTERVAL)
                continue

            _log(f"poll: clipboard changed, len={len(text)}, preview=[{text[:80]}]")
            self._last_text = text

            # 去重：和上次触发的相同
            if text == self._last_triggered:
                _log("poll: same as last triggered, skip")
                time.sleep(Config.POLL_INTERVAL)
                continue

            # 智能过滤
            if not should_trigger(text):
                time.sleep(Config.POLL_INTERVAL)
                continue

            # 通过！
            self._last_triggered = text
            _log(f"poll: TRIGGER! len={len(text)}")
            try:
                self._callback(text)
            except Exception as e:
                _log(f"poll: callback error: {e}")

            time.sleep(Config.POLL_INTERVAL)
