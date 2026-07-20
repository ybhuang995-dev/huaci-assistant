"""
文本捕获模块
-----------
通过 Windows API 模拟 Ctrl+C 并从剪贴板获取选中的文本。
不依赖 pyperclip，直接用 ctypes 调 Windows API，避免额外依赖。
"""

import ctypes
import ctypes.wintypes
import time

# ── Windows API 常量 ────────────────────────────────────
CF_UNICODETEXT = 13          # Unicode 文本格式
GMEM_MOVEABLE = 0x0002       # 可移动全局内存
VK_CONTROL = 0x11            # Ctrl 键虚拟码
VK_C = 0x43                  # C 键虚拟码
KEYEVENTF_KEYUP = 0x0002     # 按键释放标志

# ── 修复 64 位 Windows 上的指针返回类型 ───────────────
# ctypes 默认把返回值当 32 位 int，64 位下需显式指定
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

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


def _send_ctrl_c() -> None:
    """
    使用 Windows API keybd_event 模拟 Ctrl+C 组合键。

    比起 keyboard.send()，直接调用系统 API 的好处是：
    不会与 keyboard 库的全局钩子产生冲突。
    """
    # 按下 Ctrl
    _user32.keybd_event(VK_CONTROL, 0, 0, 0)
    # 按下 C
    _user32.keybd_event(VK_C, 0, 0, 0)
    # 释放 C
    _user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    # 释放 Ctrl
    _user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def _get_clipboard_text() -> str:
    """
    读取 Windows 剪贴板中的 Unicode 文本。
    ...
    Returns:
        剪贴板文本，失败返回空字符串
    """
    # 打开剪贴板（参数为 None/NULL 表示当前进程）
    if not _user32.OpenClipboard(None):
        return ""

    try:
        # 获取 Unicode 文本数据句柄
        h_data = _user32.GetClipboardData(CF_UNICODETEXT)
        if not h_data:
            return ""

        # 锁定全局内存，获取数据指针
        p_data = _kernel32.GlobalLock(h_data)
        if not p_data:
            return ""

        try:
            # 从指针读取 UTF-16 字符串
            return ctypes.wstring_at(p_data)
        finally:
            _kernel32.GlobalUnlock(h_data)
    finally:
        _user32.CloseClipboard()


def _set_clipboard_text(text: str) -> None:
    """
    设置 Windows 剪贴板文本。
    ...
    """
    if not _user32.OpenClipboard(None):
        return

    try:
        _user32.EmptyClipboard()

        # 编码为 UTF-16 LE 字节（正确处理 BMP 外字符如 emoji）
        utf16_bytes = text.encode("utf-16-le")
        byte_size = len(utf16_bytes) + 2  # +2 留给结尾 null

        h_mem = _kernel32.GlobalAlloc(GMEM_MOVEABLE, byte_size)
        if not h_mem:
            return

        p_mem = _kernel32.GlobalLock(h_mem)
        if not p_mem:
            _kernel32.GlobalFree(h_mem)
            return

        try:
            # 复制 UTF-16 字节（null 终止符已由 GlobalAlloc 零初始化）
            ctypes.memmove(p_mem, utf16_bytes, len(utf16_bytes))
        finally:
            _kernel32.GlobalUnlock(h_mem)

        # 将内存句柄交给剪贴板
        _user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        # 注意：不要 GlobalFree(h_mem)，剪贴板现在拥有它
    finally:
        _user32.CloseClipboard()


def capture_selected_text() -> str:
    """
    捕获当前用户选中的文本。

    工作流程：
    1. 保存当前剪贴板内容（后面恢复）
    2. 短暂等待，确保热键组合完全释放
    3. 模拟 Ctrl+C 复制选中文本
    4. 等待剪贴板更新
    5. 读取剪贴板 → 这就是选中的文本
    6. 恢复原始剪贴板内容

    Returns:
        用户选中的文本字符串。如果没有选中任何文字，返回空字符串。
    """
    # 1. 备份当前剪贴板
    original = _get_clipboard_text()

    # 2. 等待热键完全释放（避免键盘状态残留）
    time.sleep(0.05)

    # 3. 模拟 Ctrl+C
    _send_ctrl_c()

    # 4. 等剪贴板更新（给目标应用一点反应时间）
    time.sleep(0.15)

    # 5. 读取选中文本
    text = _get_clipboard_text()

    # 6. 恢复原始剪贴板（前提是确实变了、且原本有内容）
    if original and original != text:
        try:
            _set_clipboard_text(original)
        except (UnicodeError, OSError):
            pass  # 无法编码恢复（如原始内容含损坏的代理对），放弃恢复

    return text
