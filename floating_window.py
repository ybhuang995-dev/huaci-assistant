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
import markdown
from tkinterweb import HtmlFrame
from config import Config, MODES, MODE_TITLES, DEFAULT_MODE, MODE_ENABLED

FONT = Config.FONT

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
    "dict": "#ec4899",  # 粉色
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
        self.result_area: HtmlFrame | None = None
        self._drag_x = 0
        self._drag_y = 0

        # 状态
        self.current_mode = DEFAULT_MODE
        self.original_text = ""

        # 对话树
        self._tree_nodes: list[dict] = []  # [{id, type, text, result, mode, parent_id, depth, is_last}]
        self._next_node_id = 0
        self._active_node_id: int | None = None  # 当前结果区显示的节点

        # 回调（由 main.py 设置）
        self._on_mode_switch: callable | None = None
        self._on_retry: callable | None = None
        self._on_copy: callable | None = None
        self._on_follow_up: callable | None = None
        self._on_settings: callable | None = None

        # 右键菜单
        self._context_menu: tk.Menu | None = None

        # 分支树侧边栏
        self._sidebar_visible = False
        self._sidebar_canvas: tk.Canvas | None = None
        self._collapsed_nodes: set = set()  # 已折叠的节点 ID

        # 追问输入框
        self._input_entry: tk.Entry | None = None
        self._input_placeholder = "✏️ 输入追问内容，Enter 发送…"

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
        if mode is not None:
            self.current_mode = mode

        # 初始化对话树：根节点
        self._tree_nodes = []
        self._next_node_id = 0
        self._add_node("query", text, result, mode or self.current_mode)

        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)

        w, h = Config.WINDOW_WIDTH, Config.WINDOW_HEIGHT
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
        self._build_action_bar()      # BOTTOM 先 pack，抢在 expand 之前占位
        self._build_input_bar()       # BOTTOM（在操作栏上方）
        self._build_result_area()     # TOP expand 后 pack，吃剩余空间

        # 快捷键
        self.window.bind("<Escape>", lambda e: self.hide())
        self.window.bind("<Control-Return>", lambda e: self._copy_result())
        self.window.focus_force()

    def update_result(self, result: str) -> None:
        """更新最后一个节点的结果（API 返回后调用）"""
        if self._tree_nodes:
            self._tree_nodes[-1]["result"] = result
        if self.window is not None:
            self._render_tree()

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

    def set_on_settings(self, callback: callable) -> None:
        """设置设置按钮回调：callback()"""
        self._on_settings = callback

    def resize(self, width: int = None, height: int = None) -> None:
        """运行时调整窗口大小"""
        if not self.window:
            return
        w = width if width is not None else self.window.winfo_width()
        h = height if height is not None else self.window.winfo_height()
        x = self.window.winfo_x()
        y = self.window.winfo_y()
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
        self.window.geometry(f"{w}x{h}+{x}+{y}")

    def refresh_tabs(self) -> None:
        """热刷新标签栏（MODE_ENABLED 变更后调用）"""
        if not self._tab_widgets:
            return
        # 全部撤销
        for tab in self._tab_widgets.values():
            tab.pack_forget()
        # 按 MODES 顺序重新 pack 已启用的
        for mode_key in MODES:
            tab = self._tab_widgets.get(mode_key)
            if tab is not None and MODE_ENABLED.get(mode_key, True):
                tab.pack(side=tk.LEFT, padx=(4, 0), pady=4)
        # 如果当前模式被禁用，切到第一个可用模式
        if not MODE_ENABLED.get(self.current_mode, True):
            for mk in MODES:
                if MODE_ENABLED.get(mk, True):
                    self.current_mode = mk
                    break
        self._highlight_active_tab()

    def set_route_hint(self, text: str) -> None:
        """显示/更新自动路由提示文字"""
        if hasattr(self, "_route_hint") and self._route_hint is not None:
            try:
                self._route_hint.configure(text=text)
            except tk.TclError:
                pass

    def apply_classified_mode(self, mode_key: str) -> None:
        """自动路由结果：更新 UI 模式，清空占位节点（不触发 _on_mode_switch）"""
        self.current_mode = mode_key
        self._highlight_active_tab()
        self._tree_nodes = []
        self._next_node_id = 0
        self._add_node("query", self.original_text, "⏳ 正在处理，请稍候...", mode_key)

    def hide(self, event=None) -> None:
        self._hide_context_menu()
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
            self._sidebar_canvas = None
            self._sidebar_btn = None
            self._sidebar_visible = False
            self._collapsed_nodes = set()
            self._active_node_id = None
            self._input_entry = None
            self._route_hint = None

    # ── 标签栏 ──────────────────────────────────────────

    def _build_tab_bar(self) -> None:
        """构建模式标签栏：[翻译] [提问] [润色] [总结] [✕]"""
        bar = tk.Frame(self._inner, bg=C["surface"], height=36)
        bar.pack(fill=tk.X, side=tk.TOP)
        bar.pack_propagate(False)

        self._tab_widgets = {}

        for mode_key in MODES:
            if not MODE_ENABLED.get(mode_key, True):
                continue
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

        # 齿轮按钮（设置）
        gear = tk.Label(bar, text="⚙", bg=C["surface"], fg=C["subtext"],
                        font=(FONT, 12), padx=4, pady=2, cursor="hand2")
        gear.pack(side=tk.RIGHT, padx=(0, 2), pady=2)
        gear.bind("<Button-1>", lambda e: self._on_settings and self._on_settings())
        gear.bind("<Enter>", lambda e: gear.configure(fg=C["text"]))
        gear.bind("<Leave>", lambda e: gear.configure(fg=C["subtext"]))

        # 关闭按钮
        close = tk.Button(bar, text="✕", bg=C["surface"], fg=C["subtext"],
                          font=(FONT, 12), bd=0, cursor="hand2",
                          activebackground=C["hover"], activeforeground="#ffffff",
                          command=self.hide)
        close.pack(side=tk.RIGHT, padx=(2, 6), pady=2)

        # 高亮当前模式
        self._highlight_active_tab()

        # 标签栏下方分隔线
        self._add_separator(self._inner, tk.TOP)

        # 自动路由提示标签（默认隐藏）
        self._route_hint = tk.Label(
            self._inner, text="", bg=C["bg"], fg=C["accent"],
            font=(FONT, 8), anchor="w",
        )
        self._route_hint.pack(fill=tk.X, side=tk.TOP, padx=12, pady=(2, 0))

        # 拖拽：标题栏
        bar.bind("<Button-1>", self._start_drag)
        bar.bind("<B1-Motion>", self._drag)

    def _switch_mode(self, mode_key: str) -> None:
        """切换模式标签 —— 清空树，用新模式重新查询"""
        if mode_key == self.current_mode:
            return
        self.current_mode = mode_key
        self._highlight_active_tab()

        # 清空树，新建根节点
        self._tree_nodes = []
        self._next_node_id = 0
        self._add_node("query", self.original_text, "⏳ 正在处理，请稍候...",
                       self.current_mode)

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
        """构建滚动结果区域 + 可折叠侧边栏"""
        # 外层水平容器：侧边栏 | 结果区
        outer = tk.Frame(self._inner, bg=C["bg"])
        outer.pack(fill=tk.BOTH, expand=True, padx=2, pady=(2, 0))

        # ── 侧边栏（默认隐藏） ──
        self._sidebar_frame = tk.Frame(outer, bg=C["surface"], width=200)
        self._sidebar_frame.pack_propagate(False)
        # 不 pack，由 _toggle_sidebar 控制

        self._sidebar_canvas = tk.Canvas(
            self._sidebar_frame, bg=C["surface"],
            bd=0, highlightthickness=0,
        )
        self._sidebar_canvas.bind("<MouseWheel>",
            lambda e: self._sidebar_canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        self._sidebar_canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        sb_side = tk.Scrollbar(self._sidebar_frame, command=self._sidebar_canvas.yview,
                               bg=C["scroll_bg"], troughcolor=C["surface"])
        sb_side.pack(fill=tk.Y, side=tk.RIGHT)
        self._sidebar_canvas.configure(yscrollcommand=sb_side.set)

        # ── 结果区 ──
        container = tk.Frame(outer, bg=C["bg"])
        container.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        self.result_area = HtmlFrame(
            container,
            messages_enabled=False,  # 不显示内部调试信息
            vertical_scrollbar=True,
        )
        self.result_area.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # 右键菜单触发追问（HtmlFrame 选择文本后右键即可）
        self.result_area.bind("<Button-3>", self._on_result_right_click)
        # 左键点击关闭右键菜单
        self.result_area.bind("<Button-1>", self._hide_context_menu)

        # 渲染已有树（如果有）
        self._render_tree()

    # ── 操作栏 ──────────────────────────────────────────

    def _build_action_bar(self) -> None:
        """构建底部操作栏（pack_propagate(False) 防止被 expand=True 区域挤没）"""
        bottom = tk.Frame(self._inner, bg=C["bg"], height=34)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        bottom.pack_propagate(False)

        sep = tk.Frame(bottom, bg=C["border"], height=1)
        sep.pack(fill=tk.X, side=tk.TOP)

        bar = tk.Frame(bottom, bg=C["surface"])
        bar.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        btn_frame = tk.Frame(bar, bg=C["surface"])
        btn_frame.pack(side=tk.LEFT, padx=4)

        def _make_btn(text, command):
            """用 Label 模拟按钮"""
            lbl = tk.Label(btn_frame, text=text, bg=C["surface"], fg=C["text"],
                           font=(FONT, 9), padx=8, pady=4, cursor="hand2")
            lbl.pack(side=tk.LEFT, padx=2)
            lbl.bind("<Button-1>", lambda e: command())
            return lbl

        # 复制
        _make_btn("📋 复制", self._copy_result)

        # 分支树侧边栏
        self._sidebar_btn = _make_btn("📂 分支树", self._toggle_sidebar)

        # 重试
        _make_btn("🔄 重试", self._retry)

        # 快捷键提示
        hint = tk.Label(bar, text="Esc 关闭 | Enter 复制 | 右键追问",
                        bg=C["surface"], fg=C["subtext"], font=(FONT, 9))
        hint.pack(side=tk.RIGHT, padx=10)

    # ── 交互 ────────────────────────────────────────────

    def _copy_result(self) -> None:
        """复制活跃节点的结果到剪贴板"""
        if self._active_node_id is not None:
            node = self._get_node(self._active_node_id)
            if node and node.get("result", ""):
                self.root.clipboard_clear()
                self.root.clipboard_append(node["result"])
                if self._on_copy:
                    self._on_copy(node["result"])

    def _retry(self) -> None:
        """重试：清空树 → 新根节点（保留模式）"""
        self._tree_nodes = []
        self._next_node_id = 0
        self._add_node("query", self.original_text, "⏳ 正在重新处理，请稍候...",
                       self.current_mode)
        if self._on_retry:
            self._on_retry()

    # ── 对话树 ──────────────────────────────────────────

    def _add_node(self, node_type: str, text: str, result: str,
                  mode: str, parent_id: int | None = None) -> dict:
        """添加节点到树中并重渲染"""
        node_id = self._next_node_id
        self._next_node_id += 1

        depth = 0
        if parent_id is not None:
            parent = self._get_node(parent_id)
            if parent:
                depth = parent["depth"] + 1
                # 更新旧"最后子节点"标记
                for sibling in self._tree_nodes:
                    if sibling.get("parent_id") == parent_id and sibling.get("is_last"):
                        sibling["is_last"] = False

        node = {
            "id": node_id,
            "type": node_type,
            "text": text,
            "result": result,
            "mode": mode,
            "parent_id": parent_id,
            "depth": depth,
            "is_last": True,
        }
        self._tree_nodes.append(node)
        self._active_node_id = node_id  # 新节点自动成为活跃节点
        self._render_tree()
        return node

    def _render_tree(self) -> None:
        """渲染当前活跃节点到结果区（Markdown → HTML）"""
        if self.window is None or self.result_area is None:
            return
        try:
            if not self._tree_nodes or self._active_node_id is None:
                self.result_area.load_html(self._wrap_html("<p style='color:#9ca3af'>暂无内容</p>"))
                return

            node = self._get_node(self._active_node_id)
            if node is None:
                self.result_area.load_html(self._wrap_html("<p style='color:#9ca3af'>暂无内容</p>"))
                return

            is_loading = "⏳" in node.get("result", "")

            # 构建 Markdown 内容
            md_parts = []

            # 追问层级提示
            if node["depth"] > 0:
                parent = self._get_node(node["parent_id"]) if node.get("parent_id") is not None else None
                if parent:
                    parent_label = parent["text"].replace("\n", " ").strip()
                    if len(parent_label) > 50:
                        parent_label = parent_label[:50] + "…"
                    md_parts.append(f"*↳ 追问自：{parent_label}*")

            # 节点头 = 划词文本
            label = node["text"].replace("\n", " ").strip()
            if len(label) > 100:
                label = label[:100] + "…"
            md_parts.append(f"### {label}")

            # 分隔线
            md_parts.append("---")

            # AI 回答内容（直接使用 Markdown）
            if is_loading:
                md_parts.append(f"*{node['result']}*")
            else:
                md_parts.append(node["result"])

            # MD → HTML
            md_content = "\n\n".join(md_parts)
            html_body = markdown.markdown(
                md_content,
                extensions=["fenced_code", "tables", "codehilite"],
            )
            self.result_area.load_html(self._wrap_html(html_body))

            # 侧边栏可见时同步刷新（高亮当前节点）
            if self._sidebar_visible:
                self._render_sidebar()

        except tk.TclError:
            pass

    @staticmethod
    def _wrap_html(body: str) -> str:
        """将 HTML body 包裹为完整文档，注入与主题匹配的 CSS"""
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="
    font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
    font-size: 13px; color: {C['text']}; background: {C['bg']};
    margin: 0; padding: 12px 16px; line-height: 1.7;
">
<style>
    h1, h2, h3, h4 {{ color: {C['text']}; margin-top: 12px; margin-bottom: 6px; }}
    h3 {{ font-size: 14px; }}
    hr {{ border: none; border-top: 1px solid {C['border']}; margin: 12px 0; }}
    p {{ margin: 6px 0; }}
    a {{ color: {C['accent']}; }}
    blockquote {{
        border-left: 3px solid {C['accent']}; margin: 8px 0; padding: 2px 12px;
        color: {C['subtext']};
    }}
    code {{
        background: {C['surface']}; padding: 2px 6px; border-radius: 4px;
        font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 12px;
    }}
    pre {{
        background: {C['surface']}; padding: 12px; border-radius: 6px;
        overflow-x: auto; border: 1px solid {C['border']};
    }}
    pre code {{ background: none; padding: 0; }}
    table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
    th, td {{ border: 1px solid {C['border']}; padding: 6px 10px; text-align: left; }}
    th {{ background: {C['surface']}; font-weight: bold; }}
    ul, ol {{ padding-left: 20px; margin: 4px 0; }}
    li {{ margin: 2px 0; }}
    strong {{ color: {C['text']}; }}
    em {{ color: {C['subtext']}; }}
    details {{
        margin: 8px 0; padding: 10px 14px;
        background: {C['surface']}; border: 1px solid {C['border']};
        border-radius: 6px;
    }}
    details[open] {{ padding-bottom: 14px; }}
    summary {{
        cursor: pointer; font-size: 12px; color: {C['subtext']};
        font-weight: 600; user-select: none;
    }}
    summary:hover {{ color: {C['text']}; }}
</style>
{body}
</body>
</html>"""

    # ── 分支树侧边栏 ──────────────────────────────────

    def _toggle_sidebar(self) -> None:
        """切换侧边栏显示/隐藏"""
        self._sidebar_visible = not self._sidebar_visible
        if self._sidebar_visible:
            # 拿到 outer 的已有子控件（排除 sidebar_frame 自身）
            siblings = [c for c in self._sidebar_frame.master.winfo_children()
                        if c is not self._sidebar_frame]
            if siblings:
                self._sidebar_frame.pack(fill=tk.Y, side=tk.LEFT,
                                         before=siblings[0])
            else:
                self._sidebar_frame.pack(fill=tk.Y, side=tk.LEFT)
            self._render_sidebar()
        else:
            self._sidebar_frame.pack_forget()
        self._update_sidebar_btn()

    def _update_sidebar_btn(self) -> None:
        """更新侧边栏按钮文字"""
        if hasattr(self, "_sidebar_btn") and self._sidebar_btn is not None:
            try:
                self._sidebar_btn.configure(
                    text="📂 关闭分支" if self._sidebar_visible else "📂 分支树")
            except tk.TclError:
                pass

    def _walk_tree(self, parent_id=None):
        """DFS 遍历树，子节点紧跟父节点。跳过折叠节点的子树。"""
        children = [n for n in self._tree_nodes if n.get("parent_id") == parent_id]
        for child in children:
            yield child
            if child["id"] not in self._collapsed_nodes:
                yield from self._walk_tree(child["id"])

    def _render_sidebar(self) -> None:
        """渲染侧边栏树形列表到 Canvas（支持子树折叠/展开）"""
        if self._sidebar_canvas is None:
            return
        try:
            self._sidebar_canvas.delete("all")

            if not self._tree_nodes:
                return

            # 预先算好每个节点是否有子节点
            child_ids = {n.get("parent_id") for n in self._tree_nodes if n.get("parent_id") is not None}

            y = 8
            for node in self._walk_tree():
                depth = node["depth"]
                nid = node["id"]
                has_children = nid in child_ids
                is_collapsed = nid in self._collapsed_nodes

                raw = node["text"].replace("\n", " ").strip()
                text_preview = raw[:24] + "…" if len(raw) > 24 else raw
                indent = "  " * depth
                marker = "└ " if node.get("is_last") else "├ " if depth > 0 else ""

                # ── 折叠/展开标记 ──
                x_label = 8
                if has_children:
                    toggle_char = "▶" if is_collapsed else "▼"
                    toggle_tag = f"toggle_{nid}"
                    self._sidebar_canvas.create_text(
                        8, y, text=toggle_char, anchor="nw",
                        fill=C["subtext"], font=(FONT, 9),
                        tags=(toggle_tag, "side_item"),
                    )
                    self._sidebar_canvas.tag_bind(
                        toggle_tag, "<Button-1>",
                        lambda e, nid=nid: self._toggle_collapse(nid))
                    self._sidebar_canvas.tag_bind(
                        toggle_tag, "<Enter>",
                        lambda e: self._sidebar_canvas.configure(cursor="hand2"))
                    self._sidebar_canvas.tag_bind(
                        toggle_tag, "<Leave>",
                        lambda e: self._sidebar_canvas.configure(cursor=""))
                    x_label = 24  # 给 toggle 留空间
                elif depth > 0:
                    # 叶子节点：把 marker 放在 toggle 位置
                    self._sidebar_canvas.create_text(
                        8, y, text=marker.replace(" ", ""), anchor="nw",
                        fill=C["border"], font=(FONT, 9),
                        tags=("side_item",),
                    )
                    x_label = 24

                # ── 节点标签 ──
                label = f"{indent}{marker if not has_children else ''}{text_preview}"
                is_active = nid == self._active_node_id
                fill = C["accent"] if is_active else C["text"]
                font = (FONT, 9, "bold") if is_active else (FONT, 9)

                tag = f"side_{nid}"
                self._sidebar_canvas.create_text(
                    x_label, y, text=label, anchor="nw", fill=fill, font=font,
                    tags=(tag, "side_item"),
                )
                self._sidebar_canvas.tag_bind(
                    tag, "<Button-1>",
                    lambda e, nid=nid: self._jump_to_node(nid))
                self._sidebar_canvas.tag_bind(
                    tag, "<Enter>",
                    lambda e: self._sidebar_canvas.configure(cursor="hand2"))
                self._sidebar_canvas.tag_bind(
                    tag, "<Leave>",
                    lambda e: self._sidebar_canvas.configure(cursor=""))

                y += 24

            # 更新滚动区域
            bbox = self._sidebar_canvas.bbox("all")
            if bbox:
                self._sidebar_canvas.configure(
                    scrollregion=(0, 0, 200, bbox[3] + 8))

        except tk.TclError:
            pass

    def _toggle_collapse(self, node_id: int) -> None:
        """切换节点的折叠/展开状态"""
        if node_id in self._collapsed_nodes:
            self._collapsed_nodes.discard(node_id)
        else:
            self._collapsed_nodes.add(node_id)
        self._render_sidebar()

    def _jump_to_node(self, node_id: int) -> None:
        """切换到指定节点：设置活跃节点 → 重渲染结果区"""
        if self._get_node(node_id) is None:
            return
        if node_id == self._active_node_id:
            return  # 已经是活跃节点
        self._active_node_id = node_id
        self._render_tree()  # 内部会刷新 sidebar

    # ── 追问输入栏 ──────────────────────────────────────

    def _build_input_bar(self) -> None:
        """构建底部输入栏：文本输入 + 发送按钮"""
        bar = tk.Frame(self._inner, bg=C["bg"], height=38)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        # 顶部分隔线
        tk.Frame(bar, bg=C["border"], height=1).pack(fill=tk.X, side=tk.TOP)

        inner = tk.Frame(bar, bg=C["bg"])
        inner.pack(fill=tk.BOTH, expand=True, padx=8, pady=(5, 3))

        # 输入框（用 Frame 包一层模拟边框颜色）
        entry_frame = tk.Frame(inner, bg=C["border"])
        entry_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        self._input_entry = tk.Entry(
            entry_frame, bg=C["bg"], fg=C["subtext"],
            font=(FONT, 10), relief="flat", bd=0,
            insertbackground=C["text"],
            highlightthickness=0,
        )
        self._input_entry.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        self._input_entry.bind("<Return>", lambda e: self._send_input())

        # 占位符
        self._reset_input_placeholder()
        self._input_entry.bind("<FocusIn>", self._on_input_focus_in)
        self._input_entry.bind("<FocusOut>", self._on_input_focus_out)

        # 发送按钮
        send_btn = tk.Label(
            inner, text="发送", bg=C["accent"], fg="#ffffff",
            font=(FONT, 9, "bold"), padx=14, pady=5, cursor="hand2",
        )
        send_btn.pack(side=tk.RIGHT)
        send_btn.bind("<Button-1>", lambda e: self._send_input())
        send_btn.bind("<Enter>", lambda e: send_btn.configure(bg="#2563eb"))
        send_btn.bind("<Leave>", lambda e: send_btn.configure(bg=C["accent"]))

    def _reset_input_placeholder(self) -> None:
        """重置输入框为占位符状态"""
        if self._input_entry is None:
            return
        self._input_entry.delete(0, tk.END)
        self._input_entry.insert(0, self._input_placeholder)
        self._input_entry.configure(fg=C["subtext"])

    def _on_input_focus_in(self, event=None) -> None:
        """输入框获得焦点：清除占位符"""
        if self._input_entry is None:
            return
        if self._input_entry.get() == self._input_placeholder:
            self._input_entry.delete(0, tk.END)
            self._input_entry.configure(fg=C["text"])

    def _on_input_focus_out(self, event=None) -> None:
        """输入框失去焦点：恢复占位符"""
        if self._input_entry is None:
            return
        if not self._input_entry.get().strip():
            self._reset_input_placeholder()

    def _send_input(self) -> None:
        """发送用户输入的追问内容"""
        if self._input_entry is None:
            return
        text = self._input_entry.get().strip()
        if not text or text == self._input_placeholder:
            return

        # 清空输入框，保持聚焦以便继续输入（不设占位符，焦点离开时自动恢复）
        self._input_entry.delete(0, tk.END)
        self._input_entry.configure(fg=C["text"])
        self._input_entry.focus_set()

        # 复用追问逻辑
        self._do_follow_up(text)

    # ── 追问（右键菜单） ──────────────────────────────

    def _on_result_right_click(self, event=None) -> None:
        """右键菜单：如果选中了文字，显示'追问'选项"""
        try:
            selected = self.result_area.get_selection()
        except Exception:
            return
        if not selected or not selected.strip():
            return

        menu = tk.Menu(self.window, tearoff=0,
                       bg=C["surface"], fg=C["text"],
                       activebackground=C["accent"], activeforeground="#ffffff",
                       font=(FONT, 10))
        menu.add_command(label="💬 追问",
                         command=lambda s=selected.strip(): self._do_follow_up(s))
        self._context_menu = menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _hide_context_menu(self, event=None) -> None:
        """左键点击时关闭右键菜单"""
        if hasattr(self, "_context_menu") and self._context_menu is not None:
            try:
                self._context_menu.unpost()
            except tk.TclError:
                pass
            self._context_menu = None

    def _do_follow_up(self, selected: str) -> None:
        """执行追问：基于选中的文字创建子节点 → 发起请求"""
        self._hide_context_menu()

        # 活跃节点即为追问的父节点
        parent_node = self._get_node(self._active_node_id) if self._active_node_id is not None else None

        # 添加子节点
        self._add_node("follow_up", selected, "⏳ 正在追问，请稍候...",
                       self.current_mode, parent_node["id"] if parent_node else None)

        # 通知外部
        if self._on_follow_up:
            prev_result = parent_node["result"] if parent_node else ""
            self._on_follow_up(
                selected,
                self.original_text,
                prev_result,
                self.current_mode,
            )

    def _get_node(self, node_id: int) -> dict | None:
        """按 id 查找节点"""
        for n in self._tree_nodes:
            if n["id"] == node_id:
                return n
        return None

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
