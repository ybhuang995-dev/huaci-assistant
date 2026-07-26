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
from pynput import keyboard as pynput_keyboard

from config import Config, DEFAULT_MODE, MODES, MODE_ENABLED, FILTERS_ENABLED, is_single_english_word
from clipboard_monitor import ClipboardMonitor, _log
from engine import engine
from floating_window import FloatingWindow
from settings_window import SettingsWindow

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

# ── 全局热键 ──────────────────────────────────────────────
_hotkey_listener: pynput_keyboard.GlobalHotKeys | None = None


def _parse_hotkey(hotkey_str: str) -> str:
    """将用户可读的热键字符串转为 pynput 格式。

    "ctrl+shift+p"  →  "<ctrl>+<shift>+p"
    "Ctrl+Shift+P"  →  "<ctrl>+<shift>+p"
    "alt+f1"        →  "<alt>+<f1>"
    "ctrl+space"    →  "<ctrl>+<space>"
    """
    _SPECIAL = {
        "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10",
        "f11", "f12", "f13", "f14", "f15", "f16", "f17", "f18", "f19",
        "f20", "f21", "f22", "f23", "f24",
        "up", "down", "left", "right",
        "home", "end", "page_up", "page_down", "pageup", "pagedown",
        "enter", "space", "tab", "esc", "escape",
        "backspace", "delete", "insert",
        "caps_lock", "num_lock", "scroll_lock",
        "print_screen", "pause", "menu",
    }
    parts = [p.strip() for p in hotkey_str.split("+")]
    out = []
    for p in parts:
        low = p.lower()
        if low in ("ctrl", "control"):
            out.append("<ctrl>")
        elif low == "shift":
            out.append("<shift>")
        elif low == "alt":
            out.append("<alt>")
        elif low in ("cmd", "win", "windows", "super"):
            out.append("<cmd>")
        elif low in _SPECIAL:
            out.append(f"<{low}>")
        else:
            out.append(low)
    return "+".join(out)


def _start_hotkey_listener() -> None:
    """启动全局热键监听（在 daemon 线程中运行）"""
    global _hotkey_listener
    _stop_hotkey_listener()

    hotkey_str = Config.HOTKEY_PAUSE.strip()
    if not hotkey_str:
        _log("HOTKEY: empty config, skip")
        return

    try:
        combo = _parse_hotkey(hotkey_str)
    except Exception as e:
        _log(f"HOTKEY: parse error: {e}")
        return

    def _on_toggle():
        """热键回调 — 切换暂停/恢复（运行在 pynput 线程）"""
        if _monitor_ref is None:
            return
        if _monitor_ref.is_paused():
            _monitor_ref.resume()
            _log("HOTKEY: resumed")
        else:
            _monitor_ref.pause()
            _log("HOTKEY: paused")
        # 更新托盘菜单文本
        try:
            if _tray_icon is not None:
                _tray_icon.menu = _build_tray_menu()
                _tray_icon.update_menu()
        except Exception:
            pass

    try:
        _hotkey_listener = pynput_keyboard.GlobalHotKeys({combo: _on_toggle})
        _hotkey_listener.start()
        _log(f"HOTKEY: registered [{hotkey_str}] → [{combo}]")
    except Exception as e:
        _log(f"HOTKEY: register error: {e}")


def _stop_hotkey_listener() -> None:
    """停止全局热键监听"""
    global _hotkey_listener
    if _hotkey_listener is not None:
        try:
            _hotkey_listener.stop()
        except Exception:
            pass
        _hotkey_listener = None


# ── 托盘图标 + 菜单 ──────────────────────────────────────

_tray_icon = None
_monitor_ref = None      # 由 main() 设置
_window_ref = None        # 由 main() 设置，供 _on_settings_saved 调 resize
_settings_window = None   # 由 main() 设置


def _create_tray_icon() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill="#4A90D9")
    draw.rounded_rectangle([14, 16, 50, 40], radius=4, fill="white")
    draw.polygon([(28, 40), (36, 40), (32, 48)], fill="white")
    return img


def _build_tray_menu():
    """根据暂停状态动态构建托盘菜单"""
    is_paused = _monitor_ref.is_paused() if _monitor_ref else False
    hotkey_hint = Config.HOTKEY_PAUSE.strip()
    if hotkey_hint:
        hotkey_hint = hotkey_hint.replace("+", " + ").title()
    return pystray.Menu(
        pystray.MenuItem("划词助手 — 复制即翻译", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            f"🔊 恢复监听  ({hotkey_hint})" if is_paused
            else f"🔇 暂停监听  ({hotkey_hint})",
            _on_toggle_pause,
        ) if hotkey_hint else pystray.MenuItem(
            "🔊 恢复监听" if is_paused else "🔇 暂停监听",
            _on_toggle_pause,
        ),
        pystray.MenuItem("⚙️ 设置", _on_open_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", _on_tray_exit),
    )


def _on_toggle_pause(icon, item=None) -> None:
    """暂停/恢复切换"""
    if _monitor_ref is None:
        return
    if _monitor_ref.is_paused():
        _monitor_ref.resume()
    else:
        _monitor_ref.pause()
    icon.menu = _build_tray_menu()
    icon.update_menu()


def _run_tray() -> None:
    global _tray_icon
    icon = pystray.Icon("划词助手", _create_tray_icon(),
                        "划词助手 — Ctrl+C 复制文字自动弹出",
                        _build_tray_menu())
    _tray_icon = icon
    icon.run()


def _on_tray_exit(icon, item) -> None:
    _exit_flag.set()
    icon.stop()


def _on_open_settings(icon=None, item=None) -> None:
    """打开设置面板"""
    if _settings_window is not None:
        _settings_window.show()


def _on_settings_saved(values: dict) -> None:
    """设置保存后的回调：重新加载引擎配置"""
    global _monitor_ref
    _log(f"SETTINGS: saved, reloading config")
    # 更新全局 Config 对象
    try:
        Config.WINDOW_WIDTH = int(values.get("windowWidth", 500))
        Config.WINDOW_HEIGHT = int(values.get("windowHeight", 400))
        Config.DEEPSEEK_API_KEY = values.get("apiKey", "")
        Config.DEEPSEEK_BASE_URL = values.get("baseUrl", "")
        Config.DEEPSEEK_MODEL = values.get("model", "deepseek-chat")
        Config.POLL_INTERVAL = float(int(values.get("pollInterval", 400)) / 1000)
        Config.DEFAULT_MODE = values.get("defaultMode", "translate")
        Config.FONT = values.get("font", "Microsoft YaHei UI")
        Config.AUTO_DICT = values.get("autoDict", "true").lower() == "true"
        Config.AUTO_START = values.get("autoStart", "false").lower() == "true"
        Config.AUTO_ROUTE = values.get("autoRoute", "false").lower() == "true"
        Config.HOTKEY_PAUSE = values.get("hotkeyPause", "ctrl+shift+p")
        Config.PROVIDER = values.get("provider", "DeepSeek")
    except Exception as e:
        _log(f"SETTINGS: error reloading config: {e}")

    # 更新引擎实例
    engine.api_key = Config.DEEPSEEK_API_KEY
    engine.base_url = Config.DEEPSEEK_BASE_URL.rstrip("/")
    engine.model = Config.DEEPSEEK_MODEL

    # 更新模式 Prompt（热生效，无需重启）
    mode_prompts = values.get("modePrompts", {})
    if mode_prompts:
        for mk, prompt in mode_prompts.items():
            if mk in MODES:
                MODES[mk]["system_prompt"] = prompt
        _log(f"SETTINGS: updated prompts for {list(mode_prompts.keys())}")

    # 更新模式启用状态
    mode_enabled = values.get("modeEnabled", {})
    if mode_enabled:
        MODE_ENABLED.clear()
        MODE_ENABLED.update(mode_enabled)
        _log(f"SETTINGS: mode enabled updated")

    # 更新过滤器开关
    filters = values.get("filters", {})
    if filters:
        FILTERS_ENABLED.clear()
        FILTERS_ENABLED.update(filters)
        _log(f"SETTINGS: filters updated")

    # 更新模块级 DEFAULT_MODE
    import config as _cfg
    _cfg.DEFAULT_MODE = Config.DEFAULT_MODE

    # 热更新悬浮窗尺寸（如果窗口当前可见）
    if _window_ref is not None:
        try:
            _window_ref.resize(
                width=Config.WINDOW_WIDTH,
                height=Config.WINDOW_HEIGHT,
            )
            _window_ref.refresh_tabs()
            _log(f"SETTINGS: window resized to {Config.WINDOW_WIDTH}x{Config.WINDOW_HEIGHT}")
        except Exception as e:
            _log(f"SETTINGS: resize failed: {e}")

    # 热更新全局快捷键
    _start_hotkey_listener()

    # 更新托盘菜单（快捷键提示可能变化）
    try:
        if _tray_icon is not None:
            _tray_icon.menu = _build_tray_menu()
            _tray_icon.update_menu()
    except Exception:
        pass

    _log("SETTINGS: config reloaded")


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
    """工作线程：处理 API 查询 / 追问（SSE 流式）"""
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
                stream = engine.follow_up_stream(original, previous, text, mode)
            else:
                stream = engine.query_stream(text, mode)

            accumulated = ""
            for chunk in stream:
                with _query_lock:
                    if query_id != _query_counter:
                        _log(f"WORKER: stream aborted (stale query {query_id})")
                        accumulated = ""  # 丢弃累积
                        break
                accumulated += chunk
                # lambda 默认参数捕获当前值，避免闭包延迟绑定
                root.after(0, lambda r=accumulated: window.update_result(r))

        except Exception as e:
            root.after(0, lambda e=e: window.update_result(f"❌ 查询出错：{e}"))

        if accumulated:
            _log(f"WORKER: stream done, total len={len(accumulated)}")


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
    """显示窗口 + 发起 API 查询（支持自动路由）"""
    global _query_counter

    # 单词检测（快速路径，不触发 LLM 分类）
    if is_single_english_word(text) and Config.AUTO_DICT:
        initial_mode = "dict"
        auto_route = False
    else:
        initial_mode = DEFAULT_MODE
        auto_route = Config.AUTO_ROUTE

    _log(f"MAIN: show window for [{text[:60]}], "
         f"mode={initial_mode}, auto_route={auto_route}")

    # 显示悬浮窗（加载状态）
    window.show(text, "⏳ 正在处理，请稍候...", mode=initial_mode)

    if auto_route:
        # 后台分类，完成后自动切换模式 + 发起查询
        window.set_route_hint("🤖 自动识别中…")
        threading.Thread(
            target=_classify_and_dispatch,
            args=(root, window, text, initial_mode),
            daemon=True,
        ).start()
    else:
        # 直接发起查询（当前行为）
        with _query_lock:
            _query_counter += 1
            qid = _query_counter
        _work_queue.put((text, initial_mode, qid, None))


def _classify_and_dispatch(root: tk.Tk, window: FloatingWindow,
                           text: str, initial_mode: str) -> None:
    """后台线程：LLM 分类 → 主线程更新 UI + 发起查询"""
    global _query_counter
    try:
        classified_mode = engine.classify(text)
    except Exception as e:
        _log(f"ROUTE: classify error: {e}")
        classified_mode = initial_mode

    _log(f"ROUTE: [{text[:40]}...] → {classified_mode}")

    # 在外层拿 qid（_apply 闭包里 += 会触发 UnboundLocalError）
    with _query_lock:
        _query_counter += 1
        qid = _query_counter

    def _apply() -> None:
        if window.window is None:
            _log("ROUTE: window closed before dispatch")
            return
        try:
            mode_label = MODES[classified_mode]["label"]
        except KeyError:
            mode_label = classified_mode
        try:
            window.set_route_hint(f"🤖 自动识别为：{mode_label}")
            window.apply_classified_mode(classified_mode)
            _work_queue.put((text, classified_mode, qid, None))
            _log(f"ROUTE: dispatched [{mode_label}] qid={qid}")
        except Exception as e:
            _log(f"ROUTE: dispatch error: {e}")

    root.after(0, _apply)


# ═══════════════════════════════════════════════════════════
# 主循环中的剪贴板事件处理 + 退出检查
# ═══════════════════════════════════════════════════════════

def _schedule_main_loop(root: tk.Tk, window: FloatingWindow,
                        monitor: ClipboardMonitor) -> None:
    """定期处理剪贴板队列中的事件"""

    def _tick():
        if _exit_flag.is_set():
            _stop_hotkey_listener()
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
    global _window_ref
    window = FloatingWindow(root)
    _window_ref = window

    # 设置面板
    global _settings_window
    _settings_window = SettingsWindow(root, on_save=_on_settings_saved)

    # 剪贴板监听
    global _monitor_ref
    monitor = ClipboardMonitor(on_text=_on_clipboard_change)
    _monitor_ref = monitor

    # 悬浮窗回调
    window.set_on_mode_switch(_make_mode_switch_handler(window))
    window.set_on_retry(_make_retry_handler(window))
    window.set_on_copy(lambda text: monitor.mark_as_seen(text))
    window.set_on_follow_up(_make_follow_up_handler(window))
    window.set_on_settings(lambda: _settings_window.show())

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

    # 启动全局热键
    _start_hotkey_listener()

    hotkey_display = Config.HOTKEY_PAUSE.replace("+", " + ").title()
    print("[OK] 划词助手已启动（剪贴板监听模式）", flush=True)
    print("   复制任意文字（Ctrl+C）即可触发翻译", flush=True)
    print(f"   {hotkey_display} 暂停/恢复监听", flush=True)
    print("   右键托盘图标可退出", flush=True)

    # 主循环定期检查
    _schedule_main_loop(root, window, monitor)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        _exit_flag.set()
        _stop_hotkey_listener()
        monitor.stop()
        print("[BYE] 划词助手已退出", flush=True)


if __name__ == "__main__":
    main()
