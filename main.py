"""
划词助手 — 主入口（剪贴板监听版）
================================
借鉴 OpenAI Translator 的核心设计：监听剪贴板变更，复制即翻译。

流程：
  用户 Ctrl+C → 剪贴板监听 → 智能过滤 → 悬浮窗 → API 调用 → 显示结果

架构：
  - 主线程：tkinter 消息循环 + UI 更新
  - 监听线程：ClipboardMonitor 轮询剪贴板
  - 工作线程：API 调用（不阻塞 UI）

  关键：使用两个独立队列避免互相干扰
  - _clip_queue：剪贴板事件（主线程 _tick 处理 → 显示窗口）
  - _work_queue：API 查询（工作线程处理 → 更新窗口）
"""

import queue
import threading
import tkinter as tk
import pystray
from PIL import Image, ImageDraw

from config import Config, DEFAULT_MODE
from clipboard_monitor import ClipboardMonitor, _log
from engine import engine
from floating_window import FloatingWindow

# ── 清空日志 ──────────────────────────────────────────────
import os as _os
_log_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "app.log")
try:
    with open(_log_path, "w", encoding="utf-8") as f:
        f.write("")
except Exception:
    pass
_log("===== 划词助手启动 =====")

# ── 全局状态 ──────────────────────────────────────────────
_exit_flag = threading.Event()

# 两个独立队列：剪贴板事件（主线程处理） + API 查询（工作线程处理）
_clip_queue: queue.Queue = queue.Queue()
_work_queue: queue.Queue = queue.Queue()

_query_counter = 0
_query_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════
# 系统托盘
# ═══════════════════════════════════════════════════════════

def _create_tray_icon() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill="#4A90D9")
    draw.rounded_rectangle([14, 16, 50, 40], radius=4, fill="white")
    draw.polygon([(28, 40), (36, 40), (32, 48)], fill="white")
    return img


def _run_tray() -> None:
    menu = pystray.Menu(
        pystray.MenuItem("划词助手 — 复制即翻译", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", _on_tray_exit),
    )
    icon = pystray.Icon("划词助手", _create_tray_icon(),
                        "划词助手 — Ctrl+C 复制文字自动弹出", menu)
    icon.run()


def _on_tray_exit(icon, item) -> None:
    _exit_flag.set()
    icon.stop()


# ═══════════════════════════════════════════════════════════
# 剪贴板回调（监听线程 → 放入 _clip_queue）
# ═══════════════════════════════════════════════════════════

def _on_clipboard_change(text: str) -> None:
    """剪贴板变更回调 — 放入剪贴板队列（去重由 ClipboardMonitor 保证）"""
    _clip_queue.put(text)


# ═══════════════════════════════════════════════════════════
# 工作线程（API 调用 — 从 _work_queue 取任务）
# ═══════════════════════════════════════════════════════════

def _worker(root: tk.Tk, window: FloatingWindow) -> None:
    """工作线程：处理 API 查询 / 追问"""
    while not _exit_flag.is_set():
        try:
            task = _work_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        text, mode, query_id, follow_up_data = task
        _log(f"WORKER: query [{mode}] len={len(text)}"
             + (" [追问]" if follow_up_data else ""))
        try:
            if follow_up_data:
                original, previous = follow_up_data
                result = engine.follow_up(original, previous, text, mode)
            else:
                result = engine.query(text, mode)
        except Exception as e:
            result = f"❌ 查询出错：{e}"

        # 检查是否已被更新的查询取代
        with _query_lock:
            if query_id != _query_counter:
                _log(f"WORKER: result discarded (stale query {query_id})")
                continue

        _log(f"WORKER: result ready, len={len(result)}")
        root.after(0, lambda r=result: window.update_result(r))


# ═══════════════════════════════════════════════════════════
# 模式切换 / 重试回调
# ═══════════════════════════════════════════════════════════

def _make_mode_switch_handler(window: FloatingWindow):
    def handler(mode: str) -> None:
        global _query_counter
        with _query_lock:
            _query_counter += 1
            qid = _query_counter
        _log(f"UI: mode switch to [{mode}], qid={qid}")
        _work_queue.put((window.original_text, mode, qid, None))
    return handler


def _make_retry_handler(window: FloatingWindow):
    def handler() -> None:
        global _query_counter
        with _query_lock:
            _query_counter += 1
            qid = _query_counter
        _log(f"UI: retry [{window.current_mode}], qid={qid}")
        _work_queue.put((window.original_text, window.current_mode, qid, None))
    return handler


def _make_follow_up_handler(window: FloatingWindow):
    def handler(selected: str, original: str, previous: str, mode: str) -> None:
        global _query_counter
        with _query_lock:
            _query_counter += 1
            qid = _query_counter
        _log(f"UI: follow_up [{mode}] selected=[{selected[:40]}]")
        _work_queue.put((selected, mode, qid, (original, previous)))
    return handler


# ═══════════════════════════════════════════════════════════
# 主线程：处理剪贴板事件
# ═══════════════════════════════════════════════════════════

def _start_query_for_text(root: tk.Tk, window: FloatingWindow,
                          text: str) -> None:
    """显示窗口 + 发起 API 查询"""
    global _query_counter
    with _query_lock:
        _query_counter += 1
        qid = _query_counter

    _log(f"MAIN: show window for [{text[:60]}], qid={qid}")

    # 显示悬浮窗（加载状态）
    window.show(text, "⏳ 正在处理，请稍候...", mode=DEFAULT_MODE)

    # 放入工作队列
    _work_queue.put((text, DEFAULT_MODE, qid, None))


# ═══════════════════════════════════════════════════════════
# 主循环中的剪贴板事件处理 + 退出检查
# ═══════════════════════════════════════════════════════════

def _schedule_main_loop(root: tk.Tk, window: FloatingWindow,
                        monitor: ClipboardMonitor) -> None:
    """定期处理剪贴板队列中的事件"""

    def _tick():
        if _exit_flag.is_set():
            monitor.stop()
            root.destroy()
            return

        # 批量处理剪贴板事件（每次最多取 3 个，避免阻塞主循环）
        try:
            for _ in range(3):
                text = _clip_queue.get_nowait()
                _start_query_for_text(root, window, text)
        except queue.Empty:
            pass

        root.after(100, _tick)

    root.after(100, _tick)


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════

def main() -> None:
    if not Config.DEEPSEEK_API_KEY:
        print("=" * 50, flush=True)
        print("[WARN] 未配置 DEEPSEEK_API_KEY！", flush=True)
        print("请复制 .env.example 为 .env 并填入 Key", flush=True)
        print("=" * 50, flush=True)

    # Tkinter 根窗口（隐藏）
    root = tk.Tk()
    root.withdraw()
    root.title("划词助手")

    # 悬浮窗
    window = FloatingWindow(root)

    # 剪贴板监听
    monitor = ClipboardMonitor(on_text=_on_clipboard_change)

    # 悬浮窗回调
    window.set_on_mode_switch(_make_mode_switch_handler(window))
    window.set_on_retry(_make_retry_handler(window))
    window.set_on_copy(lambda text: monitor.mark_as_seen(text))
    window.set_on_follow_up(_make_follow_up_handler(window))

    # 系统托盘
    tray_thread = threading.Thread(target=_run_tray, name="Tray", daemon=True)
    tray_thread.start()

    # 工作线程
    worker_thread = threading.Thread(
        target=_worker, args=(root, window), name="Worker", daemon=True,
    )
    worker_thread.start()

    # 启动剪贴板监听
    monitor.start()

    print("[OK] 划词助手已启动（剪贴板监听模式）", flush=True)
    print("   复制任意文字（Ctrl+C）即可触发翻译", flush=True)
    print("   右键托盘图标可退出", flush=True)

    # 主循环定期检查
    _schedule_main_loop(root, window, monitor)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        _exit_flag.set()
        monitor.stop()
        print("[BYE] 划词助手已退出", flush=True)


if __name__ == "__main__":
    main()
