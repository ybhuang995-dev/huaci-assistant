# CLAUDE.md — 划词助手

> **角色：Builder。帮主人从零构建 Windows 全局划词翻译 + 大模型提问工具。**

## 运行命令

```
pip install -r requirements.txt   # 安装依赖（首次）
python main.py                    # 启动（托盘常驻，Ctrl+C 复制触发）
run.bat                           # Windows 一键启动
```

## 项目定位

Windows 桌面工具：在任意应用中选中文字，Ctrl+C 复制，自动弹出悬浮窗显示翻译或大模型回答。不做浏览器插件、不做 Electron 重框架。

## 核心交互

```
用户选中文字 → Ctrl+C（正常复制操作）
    │
    ▼
后台监听剪贴板变更 → 智能过滤（去重/路径/URL/太短/纯数字）
    │
    ├→ 通过 → 弹出悬浮窗
    │        ┌──────────────────────────────────────┐
    │        │ [翻译] [提问] [润色] [总结]      [✕] │
    │        ├──────────────────────────────────────┤
    │        │ ← 侧边栏  │  结果区（单节点，可滚动）│
    │        │ (📂 切换) │                          │
    │        │           │ ↳ 追问自：...            │
    │        │  划词文本  │ 复制的文字               │
    │        │   ├ 追问1  │ ────────────             │
    │        │   │ └ 追问 │ AI 回答内容              │
    │        │   └ 追问2  │                          │
    │        ├──────────────────────────────────────┤
    │        │ [📋 复制] [📂 分支树] [🔄 重试]      │
    │        └──────────────────────────────────────┘
    │
    └→ 不通过 → 静默忽略，不弹窗
```

**为什么剪贴板而非选中文本**：OpenAI Translator 的核心设计——"复制即翻译"。用户本就要 Ctrl+C，不增加额外操作。

## 技术栈

- **语言**：Python 3.10+
- **UI**：`tkinter`（无边框 `overrideredirect` Toplevel，置顶，可拖拽）
- **剪贴板**：`ctypes` 直接调用 Windows API（`OpenClipboard`/`GetClipboardData`/`GlobalLock`），轮询 400ms
- **LLM**：DeepSeek API（OpenAI 兼容），`requests` 非流式调用
- **托盘**：`pystray` + `Pillow`
- **配置**：`python-dotenv` 加载 `.env`

> **已废弃**：`keyboard` 库 + `SendInput` 模拟 Ctrl+C（键盘钩子线程重入导致死锁）。

## 架构（三线程 + 双队列）

```
┌─────────────────┐     _clip_queue      ┌──────────┐
│ ClipboardMonitor │ ─────────────────→  │ 主线程    │
│ (daemon thread)  │                     │ (tkinter) │
│ 轮询 400ms       │                     │ _tick()   │
│ 8条正则过滤      │                     │ 100ms     │
└─────────────────┘                     └──────────┘
                                               │
                                         show() 显示悬浮窗
                                         put _work_queue
                                               │
                                               ▼
                                        ┌──────────┐
                                        │ Worker   │
                                        │ (daemon) │
                                        │ query()  │
                                        │ follow_up│
                                        └──────────┘
                                               │
                                         root.after()
                                         window.update_result()
```

**关键决策**：
- **双队列**：`_clip_queue`（剪贴板事件 → 主线程）+ `_work_queue`（API 调用 → Worker），分离避免互相干扰
- **查询计数器**：`_query_counter` 全局递增。Worker 完成后检查 `query_id`，丢弃过期结果（切换模式/新查询导致的旧请求）
- **两层去重**：① `_read_clipboard()` 标准化文本 + `_last_text`/`_last_triggered` 比较 ② `mark_as_seen()` 标记自己写入剪贴板的内容
- **工作队列任务格式**：`(text, mode, query_id, follow_up_data_or_None)`

## 对话树与追问

当前最核心的交互设计——用户可以在 AI 回答中划选文字，弹出「💬 追问」气泡，基于上下文深入提问。

**数据模型**（`FloatingWindow._tree_nodes`）：
```python
node = {
    "id": int,           # 自增唯一
    "type": str,         # "query" | "follow_up"（数据保留，渲染不区分）
    "text": str,         # 触发本节点的文本（复制的原文 or 选中的追问文字）
    "result": str,       # AI 返回的回答（缓存，切换即时显示）
    "mode": str,         # "translate" | "ask" | "polish" | "summarize"
    "parent_id": int|None,  # 父节点，None = 根
    "depth": int,        # 树深度
    "is_last": bool,     # 是否父节点的最后一个子节点（用于 ├ └ 前缀）
}
```

**单节点结果区**（`_render_tree` + `_active_node_id`）：
- 结果区一次只显示一个节点的内容（而非所有节点内联展开）
- `_active_node_id` 追踪当前显示的节点
- 追问时显示 `↳ 追问自：父节点文本` 层级提示
- 每个节点的 LLM 回复缓存在 `node["result"]`，切换即时显示

**侧边栏**（Canvas + DFS 遍历 + tag_bind）：
- 「📂 分支树」按钮切换 200px 左侧面板
- **Canvas 控件**（非 Text）：`create_text()` 绘制节点，`tag_bind("<Button-1>")` 处理点击——Canvas 的 tag_bind 天然可靠，不会像 Text 控件那样被 DISABLED 状态吞掉事件
- **DFS 遍历**（`_walk_tree`）：`_tree_nodes` 列表按添加时间排序，但渲染必须按树结构（父→子→兄弟）。`_walk_tree()` 生成器做 DFS，保证子节点紧跟父节点显示
- 节点名 = 划词文本（24 字截断），缩进 + `├ └` 显示层级
- 活跃节点蓝色加粗高亮（`"node_active"` tag）
- 点击节点 → `_jump_to_node(nid)` → 更新 `_active_node_id` → `_render_tree()` 重渲染结果区 + `_render_sidebar()` 刷新高亮

**追问回调链**：
```
用户划选文字 → "💬 追问"气泡 → _do_follow_up()
  → 以 _active_node_id 为父节点（不再靠 tag 查找）
  → _add_node("follow_up", selected_text, ..., parent_id)
  → _on_follow_up(selected, original_text, previous_result, mode)
  → main.py 将 (selected, mode, qid, (original, previous)) 放入 _work_queue
  → Worker 调用 engine.follow_up()
```

**`engine.follow_up()`**：传入原文 + 上次回答 + 选中文字，构造带上下文的 prompt 再调用 API。

## tkinter 注意事项

- **`tk.Button` 不可见**：部分 Windows 11 系统上 `tk.Button(bd=0)` 不渲染。操作栏统一用 `tk.Label` + `<Button-1>` 绑定代替，与标签栏一致
- **Text 控件点击不可靠**：`tk.Text` 的 `tag_bind` 和 widget 级 `<Button-1>` 在 DISABLED/NORMAL 状态下都可能不触发。可点击列表用 `tk.Canvas` + `create_text()` + `tag_bind` 替代
- **BOTTOM pack 几何 bug**：当 `_inner` 内同时有 `expand=True` 的 TOP 控件 + BOTTOM 控件时，BOTTOM 可能被挤没（Windows 11 部分 tkinter 版本）。两个措施缺一不可：
  1. 容器 Frame 作为唯一的 BOTTOM 子控件 + `pack_propagate(False)` 锁死高度
  2. **调用顺序**：BOTTOM 控件必须先于 `expand=True` 的 TOP 控件 pack（在 `show()` 里 `_build_action_bar()` 在 `_build_result_area()` 之前调用）
- **`overrideredirect(True)`** 窗口无标题栏，需自行实现拖拽（`<B1-Motion>`）和关闭（`<Escape>` 绑定）

## 模式设计（Prompt 驱动）

| 模式 | key | System Prompt 要点 |
|------|-----|-------------------|
| 翻译 | `translate` | 中→英 / 英→中，保留格式 |
| 提问 | `ask` | 通用 AI 助手，中文回答 |
| 润色 | `polish` | 优化表达，改语法，不改原意 |
| 总结 | `summarize` | 3-5 要点，无序列表 |

所有模式共用 `DeepSeekEngine.query()` / `follow_up()`，差异只在 `config.py` 的 `MODES[key]["system_prompt"]`。

## 开发进度

### ✅ Phase 1（MVP + 交互增强）
- 剪贴板监听 + 8 条正则智能过滤
- DeepSeek API 4 种模式 + `follow_up()` 上下文追问
- 悬浮窗：标签栏 + 原文预览 + 结果滚动区 + 操作栏
- 对话树：单节点结果区 + `_active_node_id` 切换 + 节点结果缓存
- 侧边栏：Canvas DFS 树渲染 + tag_bind 点击导航 + 活跃节点高亮
- 追问气泡（选文字 → 💬 追问）+ 以活跃节点为父节点
- 系统托盘 + 右键退出
- 双队列 + 查询计数器
- Enter 复制、Esc 关闭、拖拽移动
- `_walk_tree()` DFS 生成器：保证侧边栏渲染顺序符合树结构（子节点紧跟父节点）

### 🔜 Phase 2
- SSE 流式输出（`requests` → `httpx`）
- 单词检测 → 词典模式（发音+词性+例句）
- 全局热键补充
- 侧边栏键盘导航（↑↓←→ 切换节点）
- 子树折叠/展开

### 📋 Phase 3
- 多模型切换 / 自定义 Prompt / SQLite 历史
- PyInstaller 打包单 exe + 开机自启

## 行为边界

- ✅ 写代码、运行、调试、改完就跑通验证
- ✅ pip install 依赖
- ❌ 不做浏览器插件、不做移动端
- ❌ 不提交 `.env`、API Key 到 Git
