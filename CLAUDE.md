# CLAUDE.md — 划词助手

> **角色：Builder。帮主人从零构建 Windows 全局划词翻译 + 大模型提问工具。**

## 运行命令

```
pip install -r requirements.txt   # 安装依赖（首次）
python main.py                    # 启动（托盘常驻，Ctrl+C 复制触发）
run.bat                           # Windows 一键启动
python test_ui.py                 # 诊断用：独立测试悬浮窗组件渲染
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
    │        ┌──────────────────────────────────────────┐
    │        │ [翻译] [提问] [润色] [总结] [词典] [⚙][✕]│
    │        ├──────────────────────────────────────────┤
    │        │ ← 侧边栏  │  对话树结果区（HtmlFrame）   │
    │        │ (📂 切换) │                              │
    │        │           │ 复制的文字 ← 节点名           │
    │        │  划词文本  │ ────────────                 │
    │        │   ├ 追问1  │ AI 回答（Markdown 渲染）     │
    │        │   └ 追问2  │      └─ 追问的追问           │
    │        ├──────────────────────────────────────────┤
    │        │ [✏️ 追问输入栏                    ] [发送]│
    │        ├──────────────────────────────────────────┤
    │        │ [📋 复制] [📂 分支树] [🔄 重试]         │
    │        └──────────────────────────────────────────┘
    │
    └→ 不通过 → 静默忽略，不弹窗
```

**为什么剪贴板而非选中文本**：OpenAI Translator 的核心设计——"复制即翻译"。用户本就要 Ctrl+C，不增加额外操作。

## 技术栈

- **语言**：Python 3.10+
- **浮窗 UI**：`tkinter`（无边框 `overrideredirect` Toplevel，置顶，可拖拽）
- **设置面板 UI**：`pywebview` + Windows WebView2，直接渲染 HTML/CSS/JS 原型（100% 还原 CSS 视觉效果，替代已废弃的 CustomTkinter）
- **结果渲染**：`markdown` + `tkinterweb.HtmlFrame`（替代 tkinter Text 控件）
- **剪贴板**：`ctypes` 直接调用 Windows API（`OpenClipboard`/`GetClipboardData`/`GlobalLock`），轮询 400ms
- **LLM**：DeepSeek API（OpenAI 兼容），`httpx` SSE 流式调用
- **托盘**：`pystray` + `Pillow`
- **配置**：`python-dotenv` 加载 `.env`，14 个字段支持运行时热更新

> **已废弃**：`keyboard` 库 + `SendInput` 模拟 Ctrl+C（键盘钩子线程重入导致死锁）；CustomTkinter 设置面板（CSS 效果无法还原）。

## 架构（四线程 + 双队列）

```
┌─────────────────┐     _clip_queue      ┌──────────┐
│ ClipboardMonitor │ ─────────────────→  │ 主线程    │
│ (daemon thread)  │                     │ (tkinter) │
│ 轮询 400ms       │                     │ _tick()   │
│ 8条正则过滤      │                     │ 100ms     │
└─────────────────┘                     └──────────┘
                                               │
                                    ┌──────────┤
                                    │          │
                              show() 悬浮窗    SettingsWindow
                              put _work_queue  (pywebview WebView2)
                                    │          在主线程 webview.start()
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

┌──────────┐
│ 托盘线程  │  pystray — 右键菜单：暂停/恢复、设置、退出
│ (daemon) │  注意：托盘回调不在主线程，SettingsWindow.show()
└──────────┘  内部用 root.after(0, ...) 委托到主线程
```

**关键决策**：
- **双队列**：`_clip_queue`（剪贴板事件 → 主线程）+ `_work_queue`（API 调用 → Worker），分离避免互相干扰
- **查询计数器**：`_query_counter` 全局递增。Worker 完成后检查 `query_id`，丢弃过期结果（切换模式/新查询导致的旧请求）
- **两层去重**：① `_read_clipboard()` 标准化文本 + `_last_text`/`_last_triggered` 比较 ② `mark_as_seen()` 标记自己写入剪贴板的内容
- **工作队列任务格式**：`(text, mode, query_id, follow_up_data_or_None)`
- **pywebview 线程约束**：`webview.start()` 必须在主线程调用。`SettingsWindow.show()` 检测当前线程，非主线程时通过 `root.after(0, self._do_show)` 委托，避免 `WebViewException`

## 文件结构

```
划词助手/
├── main.py                  # 入口：线程管理、队列调度、回调注册
├── floating_window.py       # 悬浮窗 UI（tkinter Toplevel + HtmlFrame）
├── settings_window.py       # 设置面板（pywebview WebView2 + SettingsApi bridge）
├── clipboard_monitor.py     # 剪贴板监听（Windows API + 8 条正则过滤）
├── engine.py                # LLM 引擎（httpx SSE 流式 + follow_up + classify）
├── config.py                # 配置类 + 模式定义 + 过滤规则 + 出厂预设
├── autostart.py             # 开机自启（注册表 HKCU\...\Run）
├── history.py               # SQLite 历史记录（自动保存 + 浏览 + 回放）
├── prototypes/
│   └── settings-panel.html  # 设置面板 HTML/CSS/JS 原型（890+ 行）
├── requirements.txt
├── run.bat
├── .env                     # 用户配置（14 字段，不提交 Git）
└── .env.example             # 配置模板
```

## 设置面板（pywebview + WebView2）

### JS Bridge（SettingsApi）

Python 类通过 `js_api` 暴露给 HTML，JS 侧通过 `window.pywebview.api` 调用（必须在 `pywebviewready` 事件后才能使用）：

| 方法 | 方向 | 说明 |
|------|------|------|
| `getConfig()` | JS → Py | 初始化时读取当前所有配置 |
| `save(data)` | JS → Py | 保存 → 写入 `.env` → 触发 `_on_settings_saved` 回调 |
| `testConnection(apiKey, baseUrl, model)` | JS → Py | 测试 API 连接 |
| `resetAll()` | JS → Py | 返回出厂预设值（保留 API 配置不清除） |
| `resetPrompts()` | JS → Py | 返回出厂 Prompt 预设 |
| `close()` | JS → Py | 关闭设置窗口 |

### bridge 初始化时序

```
HTML 加载 → script 执行（此时 window.pywebview 可能为 null）
  → 尝试立即初始化（兼容 pywebview 已注入的场景）
  → 否则注册 window.addEventListener('pywebviewready', _initBridge)
  → pywebview 完成注入后触发 pywebviewready 事件
  → _initBridge() 获取 api = window.pywebview.api  → 调用 api.getConfig()
```

**注意**：不能用 `var api = window.pywebview ? window.pywebview.api : null` 在脚本顶层求值——此时 pywebview 可能还没注入。

### 字段映射（14 个字段全覆盖）

```
JS camelCase          →  .env UPPER_CASE    类型
─────────────────────────────────────────────────
windowWidth           →  WINDOW_WIDTH        int → str
windowHeight          →  WINDOW_HEIGHT       int → str
defaultMode           →  DEFAULT_MODE        str
font                  →  FONT                str
autoStart             →  AUTO_START           bool → "true"/"false"
autoDict              →  AUTO_DICT            bool → "true"/"false"
provider              →  PROVIDER            str
apiKey                →  DEEPSEEK_API_KEY    str
baseUrl               →  DEEPSEEK_BASE_URL   str
model                 →  DEEPSEEK_MODEL      str
pollInterval          →  POLL_INTERVAL        ms → s（int ÷ 1000）
modeEnabled           →  MODE_ENABLED        dict → JSON string
modePrompts           →  MODE_PROMPTS        dict → JSON string
filters               →  FILTERS             dict → JSON string
```

### 热更新机制

`_on_settings_saved(values)` 在保存后立即生效，无需重启：

- `windowWidth/Height` → `Config.WINDOW_*` + `_window_ref.resize()` + `refresh_tabs()`
- `apiKey/baseUrl/model` → `engine.*` 属性直接更新
- `defaultMode` → `Config.DEFAULT_MODE` + 模块级 `DEFAULT_MODE`
- `modePrompts` → `MODES[mk]["system_prompt"]` 热替换
- `modeEnabled` → `MODE_ENABLED` 热替换 + `_window_ref.refresh_tabs()` 实时显示/隐藏标签
- `filters` → `FILTERS_ENABLED` 热替换
- `pollInterval/font/autoDict/autoStart/provider` → `Config.*` 属性更新

### 出厂预设（恢复默认）

`config.py` 在 `.env` 覆盖**之前**保存了三组出厂值：

- `_FACTORY_MODE_PROMPTS` — 所有模式的原始 system_prompt
- `_FACTORY_MODE_ENABLED` — 全部启用
- `_FACTORY_FILTERS` — 全部启用

`resetAll()` 返回出厂预设 + **当前 API 配置**（apiKey/baseUrl/model/provider 不清除），窗口默认 800×600。

## 对话树与追问

用户可以在 AI 回答中划选文字，右键弹出「💬 追问」，基于上下文深入提问。也可通过底部输入栏直接输入追问。

**数据模型**（`FloatingWindow._tree_nodes`）：
```python
node = {
    "id": int,           # 自增唯一
    "type": str,         # "query" | "follow_up"（数据保留，渲染不区分）
    "text": str,         # 触发本节点的文本（复制的原文 or 选中的追问文字）
    "result": str,       # AI 返回的回答
    "mode": str,         # "translate" | "ask" | "polish" | "summarize" | "dict"
    "parent_id": int|None,  # 父节点，None = 根
    "depth": int,        # 树深度
    "is_last": bool,     # 是否父节点的最后一个子节点（用于 ├ └ 前缀）
}
```

**结果区渲染**（`_render_tree`）：通过 `markdown.markdown()` 将活跃节点的 result 转为 HTML，注入主题 CSS，`HtmlFrame.load_html()` 显示。单节点渲染模式——侧边栏点击切换活跃节点，结果区跟随切换。

**追问回调链**：
```
用户划选文字 → 右键 "💬 追问" → _do_follow_up()
  → _add_node("follow_up", selected_text, ...)
  → _on_follow_up(selected, original_text, previous_result, mode)
  → main.py 将 (selected, mode, qid, (original, previous)) 放入 _work_queue
  → Worker 调用 engine.follow_up() → SSE 流式
```

**`engine.follow_up()`**：传入原文 + 上次回答 + 选中文字，构造带上下文的 prompt 再调用 API。

**侧边栏**（`_toggle_sidebar` / `_render_sidebar` / `_jump_to_node`）：
- 「📂 分支树」按钮切换 200px 左侧面板（Canvas 渲染）
- 节点名 = 划词文本（与主结果区一致），缩进 + `├ └` 显示层级
- 有子节点的节点显示 `▶` / `▼` 折叠/展开按钮
- 点击节点 → 设置 `_active_node_id` → `_render_tree()` 切换结果区内容

## 模式设计（Prompt 驱动）

| 模式 | key | System Prompt 要点 |
|------|-----|-------------------|
| 翻译 | `translate` | 中→英 / 英→中，保留格式 |
| 提问 | `ask` | 通用 AI 助手，支持代码解释，中文回答 |
| 润色 | `polish` | 优化表达，改语法，不改原意 |
| 总结 | `summarize` | 3-5 要点，无序列表 |
| 词典 | `dict` | 音标（英式/美式）+ 词性 + 释义 + 例句 |

所有模式共用 `DeepSeekEngine.query_stream()` / `follow_up_stream()`，差异只在 `config.py` 的 `MODES[key]["system_prompt"]`。Prompt 可在设置面板中自定义。

**模式启用/禁用**：设置面板中可切换每个模式的开关（`MODE_ENABLED`），浮窗标签栏即时反映——只显示已启用的模式标签。

**单词检测**：`is_single_english_word(text)` 检测单个英文单词（2-30 字母），自动切换到词典模式。

## tkinter 注意事项

- **`tk.Button` 不可见**：部分 Windows 11 系统上 `tk.Button(bd=0)` 不渲染。操作栏统一用 `tk.Label` + `<Button-1>` 绑定代替（关闭按钮例外，仍用了 Button——如果看不到可改为 Label）
- **BOTTOM pack 几何 bug**：当 `_inner` 内同时有 `expand=True` 的 TOP 控件 + BOTTOM 控件时，BOTTOM 可能被挤没（Windows 11 部分 tkinter 版本）。两个措施缺一不可：
  1. 容器 Frame 作为唯一的 BOTTOM 子控件 + `pack_propagate(False)` 锁死高度
  2. **调用顺序**：BOTTOM 控件（`_build_action_bar` → `_build_input_bar`）必须先于 `expand=True` 的 TOP 控件（`_build_result_area`）pack
- **`overrideredirect(True)`** 窗口无标题栏，需自行实现拖拽（`<B1-Motion>`）和关闭（`<Escape>` 绑定）
- **HtmlFrame**：`tkinterweb.HtmlFrame` 用于 Markdown 渲染。注意 `messages_enabled=False` 关闭内部调试信息

## 开发进度

### ✅ Phase 1（MVP + 交互增强）
- 剪贴板监听 + 8 条正则智能过滤
- DeepSeek API 4 种模式 + `follow_up()` 上下文追问
- 悬浮窗：标签栏 + 原文预览 + 结果滚动区 + 操作栏
- 对话树内联渲染 + 侧边栏树导航
- 追问气泡（选文字 → 💬 追问）+ 追问输入栏
- 系统托盘 + 右键退出
- 双队列 + 查询计数器
- Enter 复制、Esc 关闭、拖拽移动

### ✅ Phase 2
- SSE 流式输出（`requests` → `httpx`）
- 单词检测 → 词典模式（发音+词性+例句）
- 托盘菜单暂停/恢复监听（`monitor.pause()` / `resume()`）
- 侧边栏子树折叠/展开（`▶` / `▼` 点击切换）
- 结果区 Markdown → HtmlFrame 渲染
- 设置面板 CustomTkinter → pywebview WebView2（14 字段全覆盖 + JS Bridge + 热更新 + 出厂预设 + 测试连接）
- 多模型切换（`PROVIDER` 联动 `base_url` + `model` 自动填充）
- SQLite 历史记录 — 自动保存、侧边栏浏览、追问链回放、单条/全部删除

### 📋 Phase 3
- PyInstaller 打包单 exe（开机自启 `AUTO_START` 已实现 ✅）
- 自定义 Prompt（设置面板已支持编辑，热生效 ✅）

## 行为边界

- ✅ 写代码、运行、调试、改完就跑通验证
- ✅ pip install 依赖
- ❌ 不做浏览器插件、不做移动端
- ❌ 不提交 `.env`、API Key 到 Git
