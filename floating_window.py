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

        # 对话树
        self._tree_nodes: list[dict] = []  # [{id, type, text, result, mode, parent_id, depth, is_last}]
        self._next_node_id = 0
        self._active_node_id: int | None = None  # 当前结果区显示的节点

        # 回调（由 main.py 设置）
        self._on_mode_switch: callable | None = None
        self._on_retry: callable | None = None
        self._on_copy: callable | None = None
        self._on_follow_up: callable | None = None

        # 追问气泡
        self._bubble: tk.Toplevel | None = None

        # 分支树侧边栏
        self._sidebar_visible = False
        self._sidebar_canvas: tk.Canvas | None = None

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
        self._build_action_bar()      # BOTTOM 先 pack，抢在 expand 之前占位
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
            self._sidebar_canvas = None
            self._sidebar_btn = None
            self._sidebar_visible = False
            self._active_node_id = None

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
        hint = tk.Label(bar, text="Esc 关闭  |  Enter 复制",
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
        """渲染当前活跃节点到结果区（单节点显示，非内联树）"""
        if self.window is None or self.result_area is None:
            return
        try:
            self.result_area.configure(state=tk.NORMAL)
            self.result_area.delete("1.0", tk.END)

            # 配置标签样式
            self.result_area.tag_configure("header", font=(FONT, 10, "bold"),
                                           foreground=C["text"], spacing3=6)
            self.result_area.tag_configure("sep", font=(FONT, 7),
                                           foreground=C["border"])
            self.result_area.tag_configure("content", font=(FONT, 11),
                                           foreground=C["text"],
                                           lmargin1=0, lmargin2=0)
            self.result_area.tag_configure("loading", font=(FONT, 10, "italic"),
                                           foreground=C["subtext"])
            self.result_area.tag_configure("depth_hint", font=(FONT, 9),
                                           foreground=C["subtext"])

            if not self._tree_nodes or self._active_node_id is None:
                self.result_area.configure(state=tk.DISABLED)
                return

            node = self._get_node(self._active_node_id)
            if node is None:
                self.result_area.configure(state=tk.DISABLED)
                return

            is_loading = "⏳" in node.get("result", "")

            # 追问层级提示
            if node["depth"] > 0:
                parent = self._get_node(node["parent_id"]) if node.get("parent_id") is not None else None
                if parent:
                    parent_label = parent["text"].replace("\n", " ").strip()
                    if len(parent_label) > 50:
                        parent_label = parent_label[:50] + "…"
                    self.result_area.insert(tk.END, f"↳ 追问自：{parent_label}\n", "depth_hint")

            # 节点头 = 划词文本
            label = node["text"].replace("\n", " ").strip()
            if len(label) > 100:
                label = label[:100] + "…"
            self.result_area.insert(tk.END, f"{label}\n",
                                   "loading" if is_loading else "header")

            # 分隔线
            self.result_area.insert(tk.END, f"{'─' * 40}\n", "sep")

            # AI 回答内容
            tag = "loading" if is_loading else "content"
            self.result_area.insert(tk.END, f"{node['result']}\n", tag)

            # 标记节点范围（用于追问时 tag 定位父节点）
            self.result_area.tag_add(f"node_{node['id']}", "1.0", tk.END + "-1c")

            self.result_area.configure(state=tk.DISABLED)

            # 侧边栏可见时同步刷新（高亮当前节点）
            if self._sidebar_visible:
                self._render_sidebar()

        except tk.TclError:
            pass

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
        """DFS 遍历树，子节点紧跟父节点（保证渲染顺序符合树结构）"""
        children = [n for n in self._tree_nodes if n.get("parent_id") == parent_id]
        for child in children:
            yield child
            yield from self._walk_tree(child["id"])

    def _render_sidebar(self) -> None:
        """渲染侧边栏树形列表到 Canvas（DFS 遍历 + tag_bind 可靠点击）"""
        if self._sidebar_canvas is None:
            return
        try:
            self._sidebar_canvas.delete("all")

            if not self._tree_nodes:
                return

            y = 8
            for node in self._walk_tree():
                depth = node["depth"]
                raw = node["text"].replace("\n", " ").strip()
                text_preview = raw[:24] + "…" if len(raw) > 24 else raw
                indent = "  " * depth
                marker = "└ " if node.get("is_last") else "├ " if depth > 0 else ""

                label = f"{indent}{marker}{text_preview}"

                is_active = node["id"] == self._active_node_id
                fill = C["accent"] if is_active else C["text"]
                font = (FONT, 9, "bold") if is_active else (FONT, 9)

                tag = f"side_{node['id']}"
                self._sidebar_canvas.create_text(
                    8, y, text=label, anchor="nw", fill=fill, font=font,
                    tags=(tag, "side_item"),
                )

                # Canvas tag_bind — 原生支持，不会像 Text 那样被状态影响
                self._sidebar_canvas.tag_bind(
                    tag, "<Button-1>",
                    lambda e, nid=node["id"]: self._jump_to_node(nid))
                # 悬停指针
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

    def _jump_to_node(self, node_id: int) -> None:
        """切换到指定节点：设置活跃节点 → 重渲染结果区"""
        if self._get_node(node_id) is None:
            return
        if node_id == self._active_node_id:
            return  # 已经是活跃节点
        self._active_node_id = node_id
        self._render_tree()  # 内部会刷新 sidebar

    # ── 分支树侧边栏 ──────────────────────────────────

    def _toggle_sidebar(self) -> None:
        """切换侧边栏显示/隐藏"""
        self._sidebar_visible = not self._sidebar_visible
        if self._sidebar_visible:
            # 找到兄弟 container（排除 sidebar 自身），放在它左边
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

        # 更新按钮文字
        self._update_sidebar_btn()

    def _update_sidebar_btn(self) -> None:
        """更新侧边栏按钮文字"""
        if hasattr(self, "_sidebar_btn") and self._sidebar_btn is not None:
            try:
                self._sidebar_btn.configure(
                    text="📂 关闭分支" if self._sidebar_visible else "📂 分支树")
            except tk.TclError:
                pass

    def _render_sidebar(self) -> None:
        """渲染侧边栏树形列表"""
        if self._sidebar_text is None:
            return
        try:
            self._sidebar_text.configure(state=tk.NORMAL)
            self._sidebar_text.delete("1.0", tk.END)

            self._sidebar_text.tag_configure("node_label",
                                             font=(FONT, 9), foreground=C["text"])
            self._sidebar_text.tag_configure("node_label_active",
                                             font=(FONT, 9, "bold"),
                                             foreground=C["accent"],
                                             background=C["bg"])
            self._sidebar_text.tag_configure("node_label_root",
                                             font=(FONT, 9, "bold"),
                                             foreground=C["text"])

            if not self._tree_nodes:
                self._sidebar_text.configure(state=tk.DISABLED)
                return

            for node in self._tree_nodes:
                depth = node["depth"]
                mode_label = MODES.get(node["mode"], {}).get("label", "")
                text_preview = node["text"][:28] + "…" if len(node["text"]) > 28 else node["text"]
                indent = "  " * depth
                marker = "└ " if node.get("is_last") else "├ " if depth > 0 else ""

                if node["type"] == "query":
                    label = f"{indent}{marker}📝 {mode_label}: {text_preview}\n"
                else:
                    label = f"{indent}{marker}💬 追问: {text_preview}\n"

                tag = "node_label_root" if depth == 0 else "node_label"

                # 记录插入前位置，用于标记整行
                line_start = self._sidebar_text.index(tk.END)
                self._sidebar_text.insert(tk.END, label, tag)
                self._sidebar_text.tag_add(f"side_{node['id']}",
                                           line_start, f"{line_start} lineend")
                self._sidebar_text.tag_bind(
                    f"side_{node['id']}", "<Button-1>",
                    lambda e, nid=node["id"]: self._jump_to_node(nid))
                self._sidebar_text.tag_bind(
                    f"side_{node['id']}", "<Enter>",
                    lambda e, t=f"side_{node['id']}":
                        self._sidebar_text.tag_configure(t, background=C["border"]))
                self._sidebar_text.tag_bind(
                    f"side_{node['id']}", "<Leave>",
                    lambda e, t=f"side_{node['id']}":
                        self._sidebar_text.tag_configure(t, background=""))

            self._sidebar_text.configure(state=tk.DISABLED)
        except tk.TclError:
            pass

    def _jump_to_node(self, node_id: int) -> None:
        """跳转到结果区中的指定节点"""
        mark = f"n{node_id}"
        try:
            self.result_area.see(mark)
        except tk.TclError:
            pass

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
        """执行追问：从选中位置找父节点 → 添加子节点 → 发起请求"""
        try:
            selected = self.result_area.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return
        if not selected or not selected.strip():
            return

        self._hide_follow_up_bubble()

        # 活跃节点即为追问的父节点
        parent_node = self._get_node(self._active_node_id) if self._active_node_id is not None else None

        # 添加子节点
        self._add_node("follow_up", selected.strip(), "⏳ 正在追问，请稍候...",
                       self.current_mode, parent_node["id"] if parent_node else None)

        # 通知外部
        if self._on_follow_up:
            prev_result = parent_node["result"] if parent_node else ""
            self._on_follow_up(
                selected.strip(),
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
