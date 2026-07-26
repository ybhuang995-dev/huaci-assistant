"""
设置面板模块 (pywebview 版)
-------------------------
用 Windows WebView2 直接渲染 HTML 原型，100% 还原 CSS 视觉效果。
通过 JS bridge (SettingsApi) 与 Python 后端通信。
"""

import json as _json
import threading
import webview
from pathlib import Path
from config import (Config, MODES, DEFAULT_MODE,
                     MODE_ENABLED, FILTERS_ENABLED,
                     _FACTORY_MODE_PROMPTS, _FACTORY_MODE_ENABLED,
                     _FACTORY_FILTERS)

_HTML_PATH = str(Path(__file__).parent / "prototypes" / "settings-panel.html")

# ── JS → Python 字段名映射（简单字段） ──
_KEY_MAP = {
    "windowWidth": "WINDOW_WIDTH",
    "windowHeight": "WINDOW_HEIGHT",
    "defaultMode": "DEFAULT_MODE",
    "font": "FONT",
    "autoStart": "AUTO_START",
    "autoDict": "AUTO_DICT",
    "autoRoute": "AUTO_ROUTE",
    "hotkeyPause": "HOTKEY_PAUSE",
    "provider": "PROVIDER",
    "apiKey": "DEEPSEEK_API_KEY",
    "baseUrl": "DEEPSEEK_BASE_URL",
    "model": "DEEPSEEK_MODEL",
    "pollInterval": "POLL_INTERVAL",
}

# ── 字典类型字段：JS camelCase → .env UPPER_SNAKE_CASE ──
_DICT_MAP = {
    "modeEnabled": "MODE_ENABLED",
    "modePrompts": "MODE_PROMPTS",
    "filters": "FILTERS",
}

# 反向映射
_KEY_MAP_REV = {v: k for k, v in _KEY_MAP.items()}


class SettingsApi:
    """暴露给 JS 的 API 对象（pywebview js_api）"""

    def __init__(self, settings: "SettingsWindow"):
        self._s = settings

    def getConfig(self) -> dict:
        """JS 初始化时调用，返回当前所有配置值"""
        return {
            "windowWidth": Config.WINDOW_WIDTH,
            "windowHeight": Config.WINDOW_HEIGHT,
            "defaultMode": DEFAULT_MODE,
            "font": Config.FONT,
            "autoStart": Config.AUTO_START,
            "autoDict": Config.AUTO_DICT,
            "autoRoute": Config.AUTO_ROUTE,
            "hotkeyPause": Config.HOTKEY_PAUSE,
            "provider": Config.PROVIDER,
            "apiKey": Config.DEEPSEEK_API_KEY,
            "baseUrl": Config.DEEPSEEK_BASE_URL,
            "model": Config.DEEPSEEK_MODEL,
            "pollInterval": int(Config.POLL_INTERVAL * 1000),
            "modeEnabled": dict(MODE_ENABLED),
            "modePrompts": {mk: MODES[mk].get("system_prompt", "") for mk in MODES},
            "filters": dict(FILTERS_ENABLED),
        }

    def save(self, data: dict) -> None:
        """JS 点击保存时调用，写入 .env 并触发主程序回调"""
        self._s._apply_save(data)

    def testConnection(self, apiKey: str, baseUrl: str, model: str) -> dict:
        """JS 测试连接按钮，返回 {success, message}"""
        try:
            from engine import engine
            engine.test_connection(api_key=apiKey, base_url=baseUrl, model=model)
            return {"success": True, "message": "连接成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def resetAll(self) -> dict:
        """JS 恢复全部默认，返回出厂预设值供前端回填（保留 API 配置）"""
        return {
            "windowWidth": 800,
            "windowHeight": 600,
            "defaultMode": "translate",
            "font": "Microsoft YaHei UI",
            "autoStart": False,
            "autoDict": True,
            "autoRoute": False,
            "hotkeyPause": "ctrl+shift+p",
            # API 配置保留当前值，不随"恢复默认"清除
            "provider": Config.PROVIDER,
            "apiKey": Config.DEEPSEEK_API_KEY,
            "baseUrl": Config.DEEPSEEK_BASE_URL,
            "model": Config.DEEPSEEK_MODEL,
            "pollInterval": 400,
            "modeEnabled": dict(_FACTORY_MODE_ENABLED),
            "modePrompts": dict(_FACTORY_MODE_PROMPTS),
            "filters": dict(_FACTORY_FILTERS),
        }

    def resetPrompts(self) -> dict:
        """JS 恢复 Prompt 为出厂预设，返回 {mode_key: original_prompt}"""
        return dict(_FACTORY_MODE_PROMPTS)

    def close(self) -> None:
        """JS 关闭窗口"""
        self._s.hide()


class SettingsWindow:
    """设置面板 — pywebview 窗口管理器"""

    def __init__(self, root, on_save: callable = None):
        self.root = root       # tkinter root，保持兼容
        self._on_save = on_save
        self._window: webview.Window | None = None

    # ══════════════════════════════════════════════════════════
    # 公共 API（main.py 调用）
    # ══════════════════════════════════════════════════════════

    def show(self) -> None:
        """启动 pywebview 窗口。

        pywebview 要求在主线程调用 start()。如果当前不在主线程
        （例如 pystray 托盘回调），通过 tkinter after 调度到主线程。
        """
        if self._window is not None:
            return  # 已经打开

        if threading.current_thread() is not threading.main_thread():
            # 从非主线程调用（托盘菜单等）→ 委托给 tkinter 主线程
            self.root.after(0, self._do_show)
            return

        self._do_show()

    def _do_show(self) -> None:
        """在主线程上执行的实际窗口启动逻辑"""
        if self._window is not None:
            return  # 已在 _do_show 调度期间被其他路径打开

        api = SettingsApi(self)
        self._window = webview.create_window(
            title="设置 — 划词助手",
            url=_HTML_PATH,
            js_api=api,
            frameless=True,
            width=620,
            height=560,
            on_top=True,
        )
        # webview.start() 阻塞当前线程（主线程），窗口关闭后返回
        webview.start()
        self._window = None

    def hide(self) -> None:
        """关闭 webview 窗口"""
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None

    # ══════════════════════════════════════════════════════════
    # 内部方法
    # ══════════════════════════════════════════════════════════

    def _apply_save(self, data: dict) -> None:
        """将 JS 传来的数据写入 .env 并回调 main.py"""
        env_path = Path(__file__).parent / ".env"

        # ── 简单字段：JS camelCase → Python UPPER_CASE ──
        values = {}
        for js_key, py_key in _KEY_MAP.items():
            val = data.get(js_key)
            if val is not None:
                if py_key == "POLL_INTERVAL":
                    val = str(int(val) / 1000)           # ms → s
                elif isinstance(val, bool):
                    val = "true" if val else "false"    # bool → str
                values[py_key] = str(val)

        # ── 字典字段：JSON 序列化写入 ──
        for js_key, py_key in _DICT_MAP.items():
            val = data.get(js_key)
            if val is not None:
                values[py_key] = _json.dumps(val, ensure_ascii=False)

        # ── 写入 .env ──
        existing_lines = []
        if env_path.exists():
            existing_lines = env_path.read_text(encoding="utf-8").splitlines()

        new_lines = []
        seen_keys = set()
        for line in existing_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                matched = False
                for py_key in values:
                    if stripped.startswith(f"{py_key}="):
                        new_lines.append(f"{py_key}={values[py_key]}")
                        seen_keys.add(py_key)
                        matched = True
                        break
                if not matched:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        for py_key, val in values.items():
            if py_key not in seen_keys:
                new_lines.append(f"{py_key}={val}")

        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        # ── 构建回调数据，传给 main.py _on_settings_saved ──
        def _ev(py_key, default=""):
            return values.get(py_key, default)

        callback_values = {
            # 窗口
            "windowWidth": _ev("WINDOW_WIDTH", str(Config.WINDOW_WIDTH)),
            "windowHeight": _ev("WINDOW_HEIGHT", str(Config.WINDOW_HEIGHT)),
            # API
            "apiKey": _ev("DEEPSEEK_API_KEY", Config.DEEPSEEK_API_KEY),
            "baseUrl": _ev("DEEPSEEK_BASE_URL", Config.DEEPSEEK_BASE_URL),
            "model": _ev("DEEPSEEK_MODEL", Config.DEEPSEEK_MODEL),
            "pollInterval": str(int(float(
                _ev("POLL_INTERVAL", str(Config.POLL_INTERVAL))) * 1000)),
            # 通用
            "defaultMode": _ev("DEFAULT_MODE", DEFAULT_MODE),
            "font": _ev("FONT", Config.FONT),
            "autoDict": _ev("AUTO_DICT", str(Config.AUTO_DICT)),
            "autoRoute": _ev("AUTO_ROUTE", str(Config.AUTO_ROUTE)),
            "hotkeyPause": _ev("HOTKEY_PAUSE", Config.HOTKEY_PAUSE),
            "autoStart": _ev("AUTO_START", str(Config.AUTO_START)),
            "provider": _ev("PROVIDER", Config.PROVIDER),
            # 字典字段（传原始 dict，main.py 用它们更新 MODES 等）
            "modePrompts": data.get("modePrompts", {}),
            "modeEnabled": data.get("modeEnabled", {}),
            "filters": data.get("filters", {}),
        }

        if self._on_save:
            self._on_save(callback_values)

    def _reset_all(self) -> None:
        """重置为默认值（仅用于 JS resetAll 调用；不写盘）"""
        pass  # 默认值由 getConfig() 返回 hardcoded 默认


# ── 全局兼容别名 ──
# main.py 用 from settings_window import SettingsWindow
# 确保无论哪种实现，对外接口一致
