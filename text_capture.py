"""
文本捕获模块
-----------
通过模拟 Ctrl+C 并读取剪贴板来获取选中文本。
使用 Windows SendInput API（替代已弃用的 keybd_event）。
"""

import ctypes
from ctypes import wintypes
import time
import datetime
import os

# ── 调试日志 ────────────────────────────────────────────
_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.log")


def _log(msg: str) -> None:
    """写入调试日志"""
    try:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass


# ── Windows API 常量 ────────────────────────────────────
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
VK_CONTROL = 0x11
VK_MENU = 0x12             # Alt 键
VK_C = 0x43

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_KEYDOWN = 0x0000

# ── SendInput 结构体定义 ────────────────────────────────


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulong),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("ki", KEYBDINPUT),
    ]


# ── 初始化 DLL ──────────────────────────────────────────
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# 修复 64 位指针返回类型
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalAlloc.restype = ctypes.c_void_p
_kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
_kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
_kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
_kernel32.GlobalFree.argtypes = [ctypes.c_void_p]

_user32.GetClipboardData.restype = ctypes.c_void_p
_user32.GetClipboardData.argtypes = [ctypes.c_uint]
_user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
_user32.OpenClipboard.argtypes = [ctypes.c_void_p]
_user32.EmptyClipboard.argtypes = []
_user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]


def _are_modifiers_up() -> bool:
    """
    检查 Ctrl 和 Alt 是否都已松开。

    使用 GetAsyncKeyState（不依赖 keyboard 库的内部状态），
    直接查询物理按键状态。最高位为 1 表示当前按下。
    """
    ctrl = _user32.GetAsyncKeyState(VK_CONTROL) & 0x8000
    alt = _user32.GetAsyncKeyState(VK_MENU) & 0x8000
    return not (ctrl or alt)


def _wait_modifiers_released(timeout: float = 2.0) -> bool:
    """
    等待用户松开 Ctrl 和 Alt 键。

    在热键触发后调用——用户按下热键后手指还没松开，
    如果此时注入 Ctrl+C，注入的 Ctrl 会和物理按下的 Ctrl 冲突，
    导致 keyboard 库的内部状态混乱。

    Returns:
        True 如果按键已松开，False 如果超时
    """
    _log("waiting for modifier keys release...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _are_modifiers_up():
            _log("modifiers released")
            return True
        time.sleep(0.02)
    _log("WARNING: timeout waiting for modifiers release")
    return False


def _send_ctrl_c() -> None:
    """
    使用 SendInput API 模拟 Ctrl+C。

    SendInput 是 keybd_event 的现代替代品，注入的按键事件
    在系统底层排队，不会与 keyboard 库的钩子线程产生死锁。
    """
    inputs = (INPUT * 4)()

    # 按下 Ctrl
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].ki.wVk = VK_CONTROL
    # 按下 C
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].ki.wVk = VK_C
    # 释放 C
    inputs[2].type = INPUT_KEYBOARD
    inputs[2].ki.wVk = VK_C
    inputs[2].ki.dwFlags = KEYEVENTF_KEYUP
    # 释放 Ctrl
    inputs[3].type = INPUT_KEYBOARD
    inputs[3].ki.wVk = VK_CONTROL
    inputs[3].ki.dwFlags = KEYEVENTF_KEYUP

    # 直接传数组，ctypes 会自动转为指向首元素的 LPINPUT 指针
    sent = _user32.SendInput(4, inputs, ctypes.sizeof(INPUT))
    _log(f"SendInput: {sent}/4 events injected")


def _get_clipboard_text() -> str:
    """读取 Windows 剪贴板 Unicode 文本"""
    _log("_get_clipboard_text: opening clipboard...")
    if not _user32.OpenClipboard(None):
        _log("_get_clipboard_text: OpenClipboard FAILED")
        return ""

    try:
        h_data = _user32.GetClipboardData(CF_UNICODETEXT)
        if not h_data:
            _log("_get_clipboard_text: GetClipboardData returned NULL")
            return ""

        p_data = _kernel32.GlobalLock(h_data)
        if not p_data:
            _log("_get_clipboard_text: GlobalLock returned NULL")
            return ""

        try:
            result = ctypes.wstring_at(p_data)
            _log(f"_get_clipboard_text: got {len(result)} chars")
            return result
        finally:
            _kernel32.GlobalUnlock(h_data)
    finally:
        _user32.CloseClipboard()


def _set_clipboard_text(text: str) -> None:
    """设置 Windows 剪贴板文本"""
    _log(f"_set_clipboard_text: setting {len(text)} chars")

    if not _user32.OpenClipboard(None):
        _log("_set_clipboard_text: OpenClipboard FAILED")
        return

    try:
        _user32.EmptyClipboard()

        utf16_bytes = text.encode("utf-16-le")
        byte_size = len(utf16_bytes) + 2  # +2 for null terminator

        h_mem = _kernel32.GlobalAlloc(GMEM_MOVEABLE, byte_size)
        if not h_mem:
            _log("_set_clipboard_text: GlobalAlloc FAILED")
            return

        p_mem = _kernel32.GlobalLock(h_mem)
        if not p_mem:
            _kernel32.GlobalFree(h_mem)
            return

        try:
            ctypes.memmove(p_mem, utf16_bytes, len(utf16_bytes))
        finally:
            _kernel32.GlobalUnlock(h_mem)

        _user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        _log("_set_clipboard_text: OK")
    finally:
        _user32.CloseClipboard()


def capture_selected_text() -> str:
    """
    捕获当前用户选中的文本。

    1. 保存当前剪贴板
    2. 模拟 Ctrl+C
    3. 读取选中文本
    4. 恢复原始剪贴板
    """
    _log("=== capture_selected_text START ===")

    # 1. 备份
    original = _get_clipboard_text()
    _log(f"backup clipboard: {len(original)} chars")

    # 2. 等用户松开 Ctrl+Alt（关键！否则注入的 Ctrl 会和物理按键冲突）
    _wait_modifiers_released(timeout=2.0)

    # 3. 再等一小会儿，确保焦点稳定
    time.sleep(0.05)

    # 4. Ctrl+C
    _send_ctrl_c()

    # 5. 等待剪贴板更新
    time.sleep(0.2)

    # 6. 读取
    text = _get_clipboard_text()
    _log(f"captured text: {len(text)} chars")

    # 7. 恢复
    if original and original != text:
        try:
            _set_clipboard_text(original)
        except (UnicodeError, OSError):
            _log("restore clipboard SKIPPED (encoding error)")

    _log(f"=== capture_selected_text END (got {len(text)} chars) ===")
    return text
