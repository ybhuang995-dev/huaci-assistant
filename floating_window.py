"""
悬浮窗 UI 模块
-------------
借鉴 OpenAI Translator 的设计：
- 模式标签栏（翻译 | 提问 | 润色 | 总结），点击切换模式
- 原文预览区
- 结果显示区（滚动）
- 底部操作栏（复制 / 重试 / 关闭）
- 无边框 + 置顶 + 可拖拽
"""

import tkinter as tk
from config import MODES, MODE_TITLES, DEFAULT_MODE

FONT = "Microsoft YaHei UI"

# 白色主题
C = {
    "bg": "#ffffff",            # 主背景
    "surface": "#f3f4f6",       # 标签栏 / 操作栏
    "text": "#1f2937",          # 正文
    "subtext": "#9ca3af",       # 次要文字
    "accent": "#3b82f6",        # 蓝 — 翻译
    "accent_green": "#10b981",  # 绿 — 润色
    "accent_purple": "#8b5cf6", # 紫 — 提问
    "accent_yellow": "#f59e0b", # 黄 — 总结
    "hover": "#ef4444",         # 关闭按钮 hover
    "scroll_bg": "#e5e7eb",    # 滚动条
    "tab_active": "#ffffff",    # 激活标签背景
    "tab_inactive": "#f3f4f6",      # 非激活标签背景（与 bar 同色）
    "border": "#e5e7eb",        # 边框
}

# 模式对应的强调色
MODE_ACCENT = {
    "translate": C["accent"],
    "ask": C["accent_purple"],
    "polish": C["accent_green"],
    "summarize": C["accent_yellow"],
}


class FloatingWindow:
    """
    翻译 / AI 结果悬浮窗。

    窗口结构：
    ┌─────────────────────────────────┐
    │ [翻译] [提问] [润色] [总结]  [✕]│  ← 模式标签栏
    ├─────────────────────────────────┤
    │ 原文：Hello world...            │  ← 原文预览（单行）
    ├─────────────────────────────────┤
    │                                 │
    │ 你好，世界！                     │  ← 结果区域（滚动）
    │                                 │
    ├─────────────────────────────────┤
    │ [📋 复制]  [🔄 重试]  Esc 关闭  │  ← 操作栏
    └─────────────────────────────────┘
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.window: tk.Toplevel | None = None
        self._inner: tk.Frame | None = None
        self._tab_widgets: dict | None = None
        self.preview_label: tk.Label | None = None
        self.result_area: tk.Text | None = None
        self._drag_x = 0
        self._drag_y = 0

        # 状态
        self.current_mode = DEFAULT_MODE
        self.original_text = ""
        self.result_text = ""

        # 回调（由 main.py 设置）
        self._on_mode_switch: callable | None = None
        self._on_retry: callable | None = None
        self._on_copy: callable | None = None
        self._on_follow_up: callable | None = None

        # 追问气泡
        self._bubble: tk.Toplevel | None = None

    # ── 辅助方法 ────────────────────────────────────────

    @staticmethod
    def _add_separator(parent: tk.Widget, side: str) -> None:
        """添加 1px 分隔线"""
        sep = tk.Frame(parent, bg=C["border"], height=1)
        sep.pack(fill=tk.X, side=side)

    # ── 公共 API ────────────────────────────────────────

    def show(self, text: str, result: str = "", mode: str = None,
             x: int = None, y: int = None) -> None:
        """
        显示 / 刷新悬浮窗。

        Args:
            text: 用户复制的原文
            result: 初始结果（可为空，表示加载中）
            mode: 初始模式（默认 translate）
            x, y: 窗口位置
        """
        self.hide()
        self.original_text = text
        self.result_text = result
        if mode is not None:
            self.current_mode = mode

        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)

        w, h = 500, 400
        if x is None or y is None:
            x = self.window.winfo_pointerx() - w // 2
            y = self.window.winfo_pointery() + 20
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))

        self.window.geometry(f"{w}x{h}+{x}+{y}")
        self.window.configure(bg=C["border"])

        # 内层容器（白色，1px 边框效果）
        self._inner = tk.Frame(self.window, bg=C["bg"])
        self._inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        self._build_tab_bar()
        self._build_original_preview()
        self._build_result_area()
        self._build_action_bar()

        # 快捷键
        self.window.bind("<Escape>", lambda e: self.hide())
        self.window.bind("<Control-Return>", lambda e: self._copy_result())
        self.window.focus_force()

    def update_result(self, result: str) -> None:
        """更新结果区域（API 返回后调用）"""
        self.result_text = result
        if self.window is None:
            return
        try:
            self.result_area.configure(state=tk.NORMAL)
            self.result_area.delete("1.0", tk.END)
            self.result_area.insert("1.0", result)
            self.result_area.configure(state=tk.DISABLED)
        except tk.TclError:
            pass

    def set_on_mode_switch(self, callback: callable) -> None:
        """设置模式切换回调：callback(mode_key)"""
        self._on_mode_switch = callback

    def set_on_retry(self, callback: callable) -> None:
        """设置重试回调：callback()"""
        self._on_retry = callback

    def set_on_copy(self, callback: callable) -> None:
        """设置复制回调：callback(text) — 传入被复制的结果文本"""
        self._on_copy = callback

    def set_on_follow_up(self, callback: callable) -> None:
        """设置追问回调：callback(selected, original, previous, mode)"""
        self._on_follow_up = callback

    def hide(self, event=None) -> None:
        self._hide_follow_up_bubble()
        if self.window:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
            self._inner = None
            self._tab_widgets = None
            self.preview_label = None
            self.result_area = None

    # ── 标签栏 ──────────────────────────────────────────

    def _build_tab_bar(self) -> None:
        """构建模式标签栏：[翻译] [提问] [润色] [总结] [✕]"""
        bar = tk.Frame(self._inner, bg=C["surface"], height=36)
        bar.pack(fill=tk.X, side=tk.TOP)
        bar.pack_propagate(False)

        self._tab_widgets = {}

        for mode_key in MODES:
            label_text = MODES[mode_key]["label"]
            tab = tk.Label(
                bar, text=label_text,
                bg=C["tab_inactive"], fg=C["subtext"],
                font=(FONT, 10), padx=12, pady=6,
                cursor="hand2",
            )
            tab.pack(side=tk.LEFT, padx=(4, 0), pady=4)
            tab.bind("<Button-1>", lambda e, m=mode_key: self._switch_mode(m))
            # 悬停效果
            tab.bind("<Enter>", lambda e, t=tab: t.configure(bg=C["tab_active"], fg=C["text"]))
            tab.bind("<Leave>", lambda e, t=tab, m=mode_key: self._restyle_tab(t, m))
            self._tab_widgets[mode_key] = tab

        # 关闭按钮
        close = tk.Button(bar, text="✕", bg=C["surface"], fg=C["subtext"],
                          font=(FONT, 12), bd=0, cursor="hand2",
                          activebackground=C["hover"], activeforeground="#ffffff",
                          command=self.hide)
        close.pack(side=tk.RIGHT, padx=6, pady=2)

        # 高亮当前模式
        self._highlight_active_tab()

        # 标签栏下方分隔线
        self._add_separator(self._inner, tk.TOP)

        # 拖拽：标题栏
        bar.bind("<Button-1>", self._start_drag)
        bar.bind("<B1-Motion>", self._drag)

    def _switch_mode(self, mode_key: str) -> None:
        """切换模式标签"""
        if mode_key == self.current_mode:
            return
        self.current_mode = mode_key
        self._highlight_active_tab()

        # 显示加载状态
        self.update_result("⏳ 正在处理，请稍候...")

        # 通知外部（main.py 会重新调用 API）
        if self._on_mode_switch:
            self._on_mode_switch(mode_key)

    def _highlight_active_tab(self) -> None:
        """高亮当前激活的标签"""
        for mk, tab in self._tab_widgets.items():
            self._restyle_tab(tab, mk)

    def _restyle_tab(self, tab: tk.Label, mode_key: str) -> None:
        """根据模式状态设置标签样式"""
        if mode_key == self.current_mode:
            accent = MODE_ACCENT.get(mode_key, C["accent"])
            tab.configure(bg=C["tab_active"], fg=accent)
        else:
            tab.configure(bg=C["tab_inactive"], fg=C["subtext"])

    # ── 原文预览 ────────────────────────────────────────

    def _build_original_preview(self) -> None:
        """构建原文预览行"""
        frame = tk.Frame(self._inner, bg=C["bg"], height=28)
        frame.pack(fill=tk.X, side=tk.TOP, padx=10, pady=(2, 0))
        frame.pack_propagate(False)

        preview = self.original_text[:60] + "…" if len(self.original_text) > 60 else self.original_text
        # 去掉换行符，单行显示
        preview = preview.replace("\n", " ↵ ")

        self.preview_label = tk.Label(
            frame, text=f"原文：{preview}",
            bg=C["bg"], fg=C["subtext"], font=(FONT, 9), anchor="w",
        )
        self.preview_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # ── 结果区域 ────────────────────────────────────────

    def _build_result_area(self) -> None:
        """构建滚动结果区域"""
        container = tk.Frame(self._inner, bg=C["bg"])
        container.pack(fill=tk.BOTH, expand=True, padx=2, pady=(2, 0))

        self.result_area = tk.Text(
            container, bg=C["bg"], fg=C["text"],
            insertbackground=C["text"], font=(FONT, 11),
            wrap=tk.WORD, bd=0, padx=14, pady=10,
            selectbackground="#bfdbfe", selectforeground=C["text"],
            exportselection=False,  # 失焦不丢选中（配合追问气泡）
            relief=tk.FLAT,
        )
        self.result_area.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # 选中文本时弹出追问气泡
        self.result_area.bind("<<Selection>>", self._on_result_select)

        # 滚动条
        sb = tk.Scrollbar(container, command=self.result_area.yview,
                          bg=C["scroll_bg"], troughcolor=C["bg"],
                          activebackground=C["subtext"])
        sb.pack(fill=tk.Y, side=tk.RIGHT)
        self.result_area.configure(yscrollcommand=sb.set)

        # 插入初始内容
        if self.result_text:
            self.result_area.insert("1.0", self.result_text)
        self.result_area.configure(state=tk.DISABLED)

    # ── 操作栏 ──────────────────────────────────────────

    def _build_action_bar(self) -> None:
        """构建底部操作栏"""
        bar = tk.Frame(self._inner, bg=C["surface"], height=34)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        # 操作栏上方分隔线（pack 在 bar 之后 → 在 bar 上方）
        self._add_separator(self._inner, tk.BOTTOM)

        btn_frame = tk.Frame(bar, bg=C["surface"])
        btn_frame.pack(side=tk.LEFT, padx=8)

        # 复制按钮
        copy_btn = tk.Button(
            btn_frame, text="📋 复制", bg=C["surface"], fg=C["text"],
            font=(FONT, 9), bd=0, cursor="hand2", padx=8,
            activebackground=C["border"], activeforeground=C["accent"],
            command=self._copy_result,
        )
        copy_btn.pack(side=tk.LEFT, padx=(0, 4))

        # 重试按钮
        retry_btn = tk.Button(
            btn_frame, text="🔄 重试", bg=C["surface"], fg=C["text"],
            font=(FONT, 9), bd=0, cursor="hand2", padx=8,
            activebackground=C["border"], activeforeground=C["accent"],
            command=self._retry,
        )
        retry_btn.pack(side=tk.LEFT, padx=(0, 4))

        # 快捷键提示
        hint = tk.Label(bar, text="Esc 关闭  |  Enter 复制",
                        bg=C["surface"], fg=C["subtext"], font=(FONT, 9))
        hint.pack(side=tk.RIGHT, padx=10)

    # ── 交互 ────────────────────────────────────────────

    def _copy_result(self) -> None:
        """复制结果到剪贴板"""
        if self.result_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.result_text)
            # 通知监视器：这是我主动写入的，别当成新内容触发弹窗
            if self._on_copy:
                self._on_copy(self.result_text)

    def _retry(self) -> None:
        """重试当前模式"""
        self.update_result("⏳ 正在重新处理，请稍候...")
        if self._on_retry:
            self._on_retry()

    # ── 追问（选中结果文字 → 气泡弹窗） ──────────────

    def _on_result_select(self, event=None) -> None:
        """检测结果区文本选中 → 显示追问气泡"""
        try:
            sel = self.result_area.get(tk.SEL_FIRST, tk.SEL_LAST)
            if sel and sel.strip():
                self._show_follow_up_bubble()
                return
        except tk.TclError:
            pass
        self._hide_follow_up_bubble()

    def _show_follow_up_bubble(self) -> None:
        """显示追问气泡（选中文下方弹出的小按钮）"""
        if self._bubble is not None:
            return  # 已显示

        # 计算气泡位置（选中位置下方）
        try:
            bbox = self.result_area.bbox("sel.first")
            if bbox:
                x = self.result_area.winfo_rootx() + bbox[0]
                y = self.result_area.winfo_rooty() + bbox[1] + bbox[3] + 6
            else:
                x = self.window.winfo_pointerx()
                y = self.window.winfo_pointery() + 16
        except tk.TclError:
            x = self.window.winfo_pointerx()
            y = self.window.winfo_pointery() + 16

        bubble = tk.Toplevel(self.root)
        bubble.overrideredirect(True)
        bubble.attributes("-topmost", True)
        bubble.configure(bg=C["accent"])

        btn = tk.Label(bubble, text="💬 追问", bg=C["accent"], fg="#ffffff",
                       font=(FONT, 10), padx=10, pady=3, cursor="hand2")
        btn.pack()
        btn.bind("<Button-1>", lambda e: self._do_follow_up())

        bubble.geometry(f"+{x}+{y}")
        bubble.bind("<FocusOut>", lambda e: self._hide_follow_up_bubble())
        self._bubble = bubble

    def _hide_follow_up_bubble(self) -> None:
        """关闭追问气泡"""
        if self._bubble is not None:
            try:
                self._bubble.destroy()
            except tk.TclError:
                pass
            self._bubble = None

    def _do_follow_up(self) -> None:
        """执行追问"""
        try:
            selected = self.result_area.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return
        if not selected or not selected.strip():
            return

        self._hide_follow_up_bubble()

        # 显示加载状态
        self.update_result("⏳ 正在追问，请稍候...")

        # 通知外部
        if self._on_follow_up:
            self._on_follow_up(
                selected.strip(),
                self.original_text,
                self.result_text,
                self.current_mode,
            )

    # ── 拖拽 ────────────────────────────────────────────

    def _start_drag(self, event) -> None:
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag(self, event) -> None:
        if self.window:
            self.window.geometry(
                f"+{self.window.winfo_x() + event.x - self._drag_x}"
                f"+{self.window.winfo_y() + event.y - self._drag_y}"
            )
