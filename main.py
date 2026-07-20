"""
划词助手 — 主入口
=================
Windows 全局划词翻译 + AI 提问工具。

启动后常驻系统托盘，监听全局热键：
  Ctrl+Alt+T  →  翻译选中文本
  Ctrl+Alt+Q  →  AI 问答

架构说明：
  - 主线程：tkinter 消息循环
  - 托盘线程：pystray 系统托盘图标
  - 钩子线程：keyboard 库内部线程，监听热键
  - 热键回调在钩子线程执行 → 通过 root.after() 切回主线程更新 UI
"""

import threading
import tkinter as tk
from tkinter import messagebox
import keyboard
import pystray
from PIL import Image, ImageDraw

from config import Config
from text_capture import capture_selected_text
from deepseek_client import client as ai_client
from floating_window import FloatingWindow

# ── 全局状态 ──────────────────────────────────────────────
_exit_flag = threading.Event()  # 退出信号，线程安全


# ═══════════════════════════════════════════════════════════
# 系统托盘
# ═══════════════════════════════════════════════════════════

def _create_tray_icon_image() -> Image.Image:
    """
    用 Pillow 生成系统托盘图标。

    图标是一个蓝色圆形 + 白色对话气泡的简单图案，
    在 16×16 的托盘区域中也能辨认。

    Returns:
        64×64 的 RGBA 图标
    """
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 蓝色圆形背景
    draw.ellipse([4, 4, 60, 60], fill="#4A90D9")

    # 白色对话气泡（圆角矩形 + 底部小三角）
    draw.rounded_rectangle([14, 16, 50, 40], radius=4, fill="white")
    # 气泡尾巴
    draw.polygon([(28, 40), (36, 40), (32, 48)], fill="white")

    return img


def _run_tray() -> None:
    """
    运行系统托盘图标（在后台线程中调用）。

    提供右键菜单：
    - 快捷键提示（不可点击）
    - 退出
    """
    menu = pystray.Menu(
        pystray.MenuItem(
            "🈳 划词翻译  (Ctrl+Alt+T)",
            lambda: None,
            enabled=False,
        ),
        pystray.MenuItem(
            "🤖 AI 提问  (Ctrl+Alt+Q)",
            lambda: None,
            enabled=False,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", _on_tray_exit),
    )

    icon = pystray.Icon(
        "划词助手",
        _create_tray_icon_image(),
        "划词助手 — 选中文字 + 快捷键",
        menu,
    )
    # run() 会阻塞当前线程直到 icon.stop() 被调用
    icon.run()


def _on_tray_exit(icon, item) -> None:
    """托盘「退出」菜单回调"""
    _exit_flag.set()
    icon.stop()


# ═══════════════════════════════════════════════════════════
# 热键处理
# ═══════════════════════════════════════════════════════════

def _handle_translate(root: tk.Tk, window: FloatingWindow) -> None:
    """
    Ctrl+Alt+T 热键回调。

    执行流程（在 keyboard 钩子线程中）：
    1. 模拟 Ctrl+C 捕获选中文本
    2. 显示加载状态（通过 root.after 切回主线程）
    3. 调用 DeepSeek API 翻译
    4. 显示结果

    整个流程在钩子线程中串行执行。
    API 调用期间钩子线程被阻塞，但不会影响 UI 响应
    （tkinter 主循环仍然正常运行）。
    """
    try:
        # 1. 捕获选中文本
        text = capture_selected_text()

        if not text.strip():
            root.after(
                0,
                lambda: window.show(
                    "🈳 翻译",
                    "⚠️ 未选中任何文字\n\n"
                    "请先用鼠标选中要翻译的文字，再按 Ctrl+Alt+T。",
                ),
            )
            return

        # 2. 显示加载状态（切回主线程更新 UI）
        root.after(
            0,
            lambda: window.show("🈳 翻译", "⏳ 正在翻译，请稍候..."),
        )

        # 3. 调用 API（在钩子线程中，不阻塞主线程）
        result = ai_client.translate(text)

        # 4. 显示结果（切回主线程）
        root.after(0, lambda: window.show(f"🈳 翻译", result))

    except Exception as e:
        root.after(
            0,
            lambda: window.show("🈳 翻译", f"❌ 出错了：{e}"),
        )


def _handle_ask(root: tk.Tk, window: FloatingWindow) -> None:
    """
    Ctrl+Alt+Q 热键回调。

    与翻译流程相同，只是调用 ai_client.ask() 而非 translate()。
    """
    try:
        text = capture_selected_text()

        if not text.strip():
            root.after(
                0,
                lambda: window.show(
                    "🤖 AI 问答",
                    "⚠️ 未选中任何文字\n\n"
                    "请先用鼠标选中文字，再按 Ctrl+Alt+Q。",
                ),
            )
            return

        root.after(
            0,
            lambda: window.show("🤖 AI 问答", "⏳ AI 正在思考，请稍候..."),
        )

        result = ai_client.ask(text)

        root.after(0, lambda: window.show(f"🤖 AI 问答", result))

    except Exception as e:
        root.after(
            0,
            lambda: window.show("🤖 AI 问答", f"❌ 出错了：{e}"),
        )


# ═══════════════════════════════════════════════════════════
# 退出检查
# ═══════════════════════════════════════════════════════════

def _schedule_exit_check(root: tk.Tk) -> None:
    """
    定期（200ms）检查退出信号。

    当用户点击托盘「退出」时，_exit_flag 被设置。
    检测到信号后：
    1. 卸载所有键盘钩子
    2. 销毁 tkinter 窗口 → mainloop 退出 → 程序结束
    """

    def _check():
        if _exit_flag.is_set():
            keyboard.unhook_all()  # 清理 hotkey 钩子
            root.destroy()         # 退出 tkinter 主循环
        else:
            root.after(200, _check)

    root.after(200, _check)


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════

def main() -> None:
    """应用程序入口"""

    # ── 启动前检查 ──
    if not Config.DEEPSEEK_API_KEY:
        # 用 tkinter 弹窗提示（用户体验更好）
        # 但 tkinter root 还没创建，先用 print
        print("=" * 50)
        print("⚠️  未配置 DEEPSEEK_API_KEY！")
        print()
        print("请按以下步骤操作：")
        print("1. 复制 .env.example → .env")
        print("2. 打开 .env，填入你的 DeepSeek API Key")
        print("3. 获取 Key：https://platform.deepseek.com/api_keys")
        print("=" * 50)

    # ── 创建 Tkinter 根窗口（隐藏） ──
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口，只有悬浮窗/Toplevel 可见
    root.title("划词助手")

    # ── 初始化悬浮窗管理器 ──
    floating_window = FloatingWindow(root)

    # ── 启动系统托盘（独立线程） ──
    tray_thread = threading.Thread(
        target=_run_tray, name="TrayThread", daemon=True
    )
    tray_thread.start()

    # ── 注册全局热键 ──
    try:
        keyboard.add_hotkey(
            Config.TRANSLATE_HOTKEY,
            lambda: _handle_translate(root, floating_window),
            suppress=False,  # 不吞掉按键，允许其他程序正常响应
        )
        keyboard.add_hotkey(
            Config.ASK_HOTKEY,
            lambda: _handle_ask(root, floating_window),
            suppress=False,
        )
        print(f"✅ 划词助手已启动")
        print(f"   翻译：{Config.TRANSLATE_HOTKEY}")
        print(f"   提问：{Config.ASK_HOTKEY}")
        print(f"   右键托盘图标可退出")
    except Exception as e:
        print(f"❌ 注册全局热键失败：{e}")
        print("   请确认没有其他程序占用相同快捷键。")

    # ── 启动退出检查 ──
    _schedule_exit_check(root)

    # ── 进入 Tkinter 主循环（阻塞，直到 root.destroy()） ──
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        keyboard.unhook_all()
        print("👋 划词助手已退出")


if __name__ == "__main__":
    main()
