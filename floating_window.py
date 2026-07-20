"""
悬浮窗 UI 模块
-------------
基于 tkinter 的无边框、置顶悬浮窗，用于显示翻译/问答结果。

功能：
- 无边框 + 置顶显示
- 标题栏可拖拽移动
- 滚动文本区域（只读）
- Esc 关闭 / Enter 复制结果
- Catppuccin Mocha 暗色主题
"""

import tkinter as tk
from tkinter import font as tkfont


class FloatingWindow:
    """翻译/问答结果悬浮窗"""

    def __init__(self, root: tk.Tk):
        """
        Args:
            root: tkinter 根窗口（隐藏），用于承载 Toplevel
        """
        self.root = root
        self.window: tk.Toplevel | None = None
        self.result_text = ""
        self._drag_x = 0
        self._drag_y = 0

        # ── 配色方案：Catppuccin Mocha ────────────────────
        self.colors = {
            "bg": "#1e1e2e",           # 窗口背景
            "title_bg": "#181825",      # 标题栏背景
            "text_bg": "#1e1e2e",       # 文本区背景
            "text_fg": "#cdd6f4",       # 文本前景
            "accent": "#89b4fa",        # 强调色（蓝）
            "status_bg": "#181825",      # 状态栏背景
            "status_fg": "#6c7086",     # 状态栏文字
            "close_hover": "#f38ba8",   # 关闭按钮悬停色
            "scroll_bg": "#313244",     # 滚动条背景
        }

    # ── 公共 API ────────────────────────────────────────────

    def show(
        self, title: str, text: str, x: int = None, y: int = None
    ) -> None:
        """
        显示 / 刷新悬浮窗。

        每次调用会先销毁旧窗口，再创建新窗口。这样保证了：
        - 多次热键触发不会产生多个窗口
        - "加载中..." 到最终结果可以平滑过渡

        Args:
            title: 标题栏文字（如 "🈳 翻译"）
            text: 要显示的内容
            x: 窗口左上角 X 坐标（None 则跟随鼠标）
            y: 窗口左上角 Y 坐标（None 则跟随鼠标）
        """
        # 先清理旧窗口
        self.hide()

        self.result_text = text

        # ── 创建无边框窗口 ──
        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(True)   # 去掉系统标题栏
        self.window.attributes("-topmost", True)  # 始终置顶

        # 窗口尺寸
        width, height = 520, 380

        # 默认位置：鼠标附近居中
        if x is None or y is None:
            x = self.window.winfo_pointerx() - width // 2
            y = self.window.winfo_pointery() + 20

        # 确保窗口不超出屏幕
        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        x = max(0, min(x, screen_w - width))
        y = max(0, min(y, screen_h - height))

        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.configure(bg=self.colors["bg"])

        # ── 构建三块区域 ──
        self._build_title_bar(title)
        self._build_text_area()
        self._build_status_bar()

        # ── 全局快捷键（绑定到窗口） ──
        self.window.bind("<Escape>", lambda e: self.hide())
        self.window.bind("<Return>", lambda e: self._copy_result())
        # 注意：不绑定 FocusOut 自动关闭，让用户主动按 Esc

        self.window.focus_force()

    def hide(self, event=None) -> None:
        """关闭悬浮窗"""
        if self.window:
            try:
                self.window.destroy()
            except tk.TclError:
                pass  # 窗口已经被销毁
            self.window = None

    # ── UI 构建子方法 ─────────────────────────────────────

    def _build_title_bar(self, title: str) -> None:
        """构建标题栏：图标 + 标题文字 + 关闭按钮"""
        bar = tk.Frame(self.window, bg=self.colors["title_bg"], height=38)
        bar.pack(fill=tk.X, side=tk.TOP)
        bar.pack_propagate(False)  # 保持固定高度

        # 标题标签
        title_lbl = tk.Label(
            bar,
            text=f"  {title}",
            bg=self.colors["title_bg"],
            fg=self.colors["accent"],
            font=("Microsoft YaHei UI", 11, "bold"),
            anchor="w",
        )
        title_lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        # 关闭按钮
        close_btn = tk.Button(
            bar,
            text="✕",
            bg=self.colors["title_bg"],
            fg=self.colors["text_fg"],
            font=("Microsoft YaHei UI", 14),
            bd=0,
            activebackground=self.colors["close_hover"],
            activeforeground="#1e1e2e",
            cursor="hand2",
            command=self.hide,
        )
        close_btn.pack(side=tk.RIGHT, padx=2, pady=2)

        # —— 拖拽支持：在标题栏上按住鼠标左键可移动窗口 ——
        for widget in (bar, title_lbl):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)

    def _build_text_area(self) -> None:
        """构建带滚动条的结果文本显示区"""
        container = tk.Frame(self.window, bg=self.colors["text_bg"])
        container.pack(fill=tk.BOTH, expand=True, padx=2, pady=1)

        # 文本区域
        self.text_widget = tk.Text(
            container,
            bg=self.colors["text_bg"],
            fg=self.colors["text_fg"],
            insertbackground=self.colors["text_fg"],  # 光标颜色
            font=("Microsoft YaHei UI", 11),
            wrap=tk.WORD,                    # 按词换行
            bd=0,
            padx=16,
            pady=12,
            selectbackground="#585b70",
            selectforeground=self.colors["text_fg"],
            relief=tk.FLAT,
            state=tk.NORMAL,
        )
        self.text_widget.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # 插入文本内容
        self.text_widget.insert("1.0", self.result_text)
        self.text_widget.configure(state=tk.DISABLED)  # 设为只读

        # 滚动条
        scrollbar = tk.Scrollbar(
            container,
            command=self.text_widget.yview,
            bg=self.colors["scroll_bg"],
            troughcolor=self.colors["bg"],
            activebackground=self.colors["status_fg"],
        )
        scrollbar.pack(fill=tk.Y, side=tk.RIGHT)
        self.text_widget.configure(yscrollcommand=scrollbar.set)

    def _build_status_bar(self) -> None:
        """构建底部状态栏：显示快捷键提示"""
        bar = tk.Frame(self.window, bg=self.colors["status_bg"], height=30)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        lbl = tk.Label(
            bar,
            text="  Esc 关闭  |  Enter 复制结果  |  拖拽标题栏可移动窗口",
            bg=self.colors["status_bg"],
            fg=self.colors["status_fg"],
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        )
        lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

    # ── 交互逻辑 ──────────────────────────────────────────

    def _copy_result(self) -> None:
        """将结果显示文本复制到剪贴板"""
        if self.result_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.result_text)
            # 短暂闪烁状态栏作为反馈
            self._flash_feedback()

    def _flash_feedback(self) -> None:
        """
        复制成功的视觉反馈：标题栏短暂变色后恢复。

        原理：利用 tkinter 的 after 方法实现延迟调用。
        100ms 后恢复背景色，给用户一个"已确认"的微交互。
        """
        if not self.window:
            return

        # 找到所有子控件中的标题栏和状态栏
        for child in self.window.winfo_children():
            if isinstance(child, tk.Frame):
                # 检查是否为状态栏（通过高度判断）
                try:
                    if child.winfo_height() <= 32:
                        # 找到状态栏中的 Label
                        for sub in child.winfo_children():
                            if isinstance(sub, tk.Label):
                                original_text = sub.cget("text")
                                sub.configure(
                                    text="  ✅ 已复制到剪贴板！",
                                    fg="#a6e3a1",  # 绿色
                                )
                                # 1.5 秒后恢复
                                self.window.after(
                                    1500,
                                    lambda: sub.configure(
                                        text=original_text,
                                        fg=self.colors["status_fg"],
                                    ),
                                )
                except Exception:
                    pass

    # ── 窗口拖拽 ──────────────────────────────────────────

    def _start_drag(self, event) -> None:
        """记录拖拽起始偏移"""
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag(self, event) -> None:
        """拖拽移动窗口"""
        if self.window:
            dx = event.x - self._drag_x
            dy = event.y - self._drag_y
            x = self.window.winfo_x() + dx
            y = self.window.winfo_y() + dy
            self.window.geometry(f"+{x}+{y}")
