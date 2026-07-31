# AGENTS.md — 划词助手

## 角色与目标

- 角色：Builder。
- 目标：协助开发和维护 Windows 全局划词翻译与大模型提问工具。
- 产品形态是 Windows 桌面程序；不改造成浏览器插件、Electron 应用或移动端应用。
- 修改代码后，应执行与改动范围相称的本地验证，不只给出未经验证的实现。

## 开发环境

- Windows 11 + MSYS2/MINGW64（Git Bash），不是 WSL。
- 文档和命令中的项目路径优先使用正斜杠，例如 `/e/hyb/划词助手`。
- Python 版本：3.10+。

常用命令：

```bash
pip install -r requirements.txt
python main.py
./run.bat
```

## 项目定位

用户在任意应用中选中文字并按 `Ctrl+C` 后，程序监听剪贴板变化，过滤无效内容，并弹出悬浮窗显示翻译、提问、代码、总结或词典结果。

核心链路：

```text
选中文字并复制
  → ClipboardMonitor 轮询剪贴板
  → 过滤、标准化与去重
  → 主线程显示 FloatingWindow
  → Worker 调用 DeepSeekEngine
  → 主线程流式更新结果
```

采用“复制即触发”的交互，不新增全局键盘钩子或模拟 `Ctrl+C`。

## 技术栈

- 悬浮窗：`tkinter`
- 设置面板：`pywebview` + Windows WebView2
- Markdown 渲染：`markdown` + `tkinterweb.HtmlFrame`
- 剪贴板：`ctypes` 调用 Windows API
- LLM：DeepSeek 的 OpenAI 兼容接口，使用标准库 `urllib` 处理 SSE 流式请求
- 系统托盘：`pystray` + `Pillow`
- 配置：`python-dotenv` + `.env`
- 历史记录：SQLite

不要重新引入已经废弃的方案：

- `keyboard` + `SendInput` 模拟复制
- CustomTkinter 设置面板

## 主要文件

- `main.py`：入口、线程管理、双队列调度与回调注册
- `floating_window.py`：悬浮窗、Markdown 结果区、追问和对话树
- `settings_window.py`：pywebview 设置面板及 `SettingsApi` bridge
- `clipboard_monitor.py`：Windows 剪贴板监听、过滤和去重
- `engine.py`：LLM 查询、SSE 流式响应和上下文追问
- `config.py`：配置、模式、Prompt、过滤规则和出厂预设
- `autostart.py`：Windows 注册表开机自启
- `history.py`：SQLite 历史记录、浏览和回放
- `prototypes/settings-panel.html`：设置面板 HTML/CSS/JS 原型
- `划词助手.spec`：PyInstaller 打包配置

## 并发与线程约束

- `_clip_queue`：剪贴板线程向 tkinter 主线程传递事件。
- `_work_queue`：主线程向 Worker 线程传递查询任务。
- tkinter 控件只能在主线程操作；后台线程通过 `root.after(...)` 回到主线程更新 UI。
- `webview.start()` 必须在主线程调用。
- `SettingsWindow.show()` 若由托盘线程触发，必须通过 `root.after(0, ...)` 委托到主线程。
- 保留 `_query_counter` 的过期查询保护，避免旧请求覆盖新查询结果。
- 保留剪贴板标准化、`_last_text` / `_last_triggered` 与 `mark_as_seen()` 两层去重机制。
- 工作队列任务格式为：

```python
(text, mode, query_id, follow_up_data_or_none)
```

## 设置面板约束

- JavaScript 只能在 `pywebviewready` 后可靠访问 `window.pywebview.api`。
- 不要在脚本顶层永久缓存尚未注入的 `window.pywebview.api`。
- 修改配置字段时，必须同步检查以下位置：
  - HTML 表单和 JavaScript 数据
  - `SettingsApi.getConfig()` / `save()`
  - `.env` 字段映射
  - `Config` 或模块级运行时变量
  - `_on_settings_saved()` 热更新逻辑
  - `.env.example`
- JSON 类型字段写入 `.env` 前应序列化，读取时应兼容缺失或无效配置。
- 恢复默认设置时保留用户当前的 API 配置，除非需求明确要求清除。

## 对话树与模式

- 对话树节点保留 `id`、`type`、`text`、`result`、`mode`、`parent_id`、`depth` 和 `is_last` 字段。
- 追问必须携带原文、上次回答和本次追问文本，不能退化为无上下文的新查询。
- 侧边栏切换节点后，结果区应渲染对应活跃节点。
- 翻译、提问、代码、总结和词典模式共用查询引擎，差异由 `config.py` 中的 Prompt 驱动。
- 单个英文单词应继续支持自动切换到词典模式。
- 模式启用状态变化后，悬浮窗标签应即时刷新。

## tkinter 已知问题

- Windows 11 上 `tk.Button(bd=0)` 可能不可见；操作栏优先使用绑定点击事件的 `tk.Label`。
- 同一容器中存在 `expand=True` 的 TOP 控件和 BOTTOM 控件时：
  - BOTTOM 区域使用唯一容器并设置 `pack_propagate(False)`；
  - 先 pack BOTTOM 操作栏和输入栏，再 pack 可扩展的 TOP 结果区。
- `overrideredirect(True)` 会移除系统标题栏，必须保留拖拽、关闭和 `Escape` 行为。
- `HtmlFrame` 默认关闭内部调试消息：`messages_enabled=False`。

## 安全与仓库规则

- 不提交 `.env`、API Key、token、密码、个人配置或其他凭证。
- `.env.example` 只能包含占位值和安全示例。
- `history.db`、日志、构建目录和本地运行产物不应作为源码提交；修改忽略规则前先检查现有仓库状态。
- 不在日志、测试输出、提交信息或错误报告中暴露密钥。
- 删除或覆盖文件前先确认；优先采用可恢复方式。
- 调用外部 API、部署、发布或执行可能付费的操作前，必须获得用户确认。
- 不擅自执行 Git 提交、推送、打标签或发布 Release；用户明确要求后再执行。

## 修改与验证

- 修改前先阅读相关模块及其调用方，避免只修局部而破坏线程、配置或 UI 链路。
- 保持改动聚焦，不顺手重写无关模块。
- 优先运行最小且相关的验证；涉及跨模块改动时再扩大验证范围。
- 基础静态检查可使用：

```bash
python -m py_compile main.py floating_window.py settings_window.py clipboard_monitor.py engine.py config.py autostart.py history.py
```

- 涉及 GUI、剪贴板、托盘、WebView2 或 SSE 的改动，除静态检查外还应说明需要人工验证的交互路径。
- 修改依赖时同步更新 `requirements.txt`；修改配置时同步更新 `.env.example`。
- 若没有自动化测试覆盖，不要声称“全部测试通过”，应明确列出实际执行的检查。

## 发布约定

- 在同一仓库中持续开发，不为每个版本新建项目。
- 发布版本使用语义化版本标签，例如 `v1.0.0`、`v1.1.0`、`v1.1.1`。
- `main` 应保持可发布；较大的功能使用 `feature/*` 分支，紧急修复使用 `hotfix/*` 分支。
- 发布前至少检查：
  - 程序可启动；
  - 剪贴板过滤与弹窗链路正常；
  - 五种模式和流式输出正常；
  - 设置保存与热更新正常；
  - `.env` 和密钥未进入 Git；
  - PyInstaller 构建在需要发布可执行文件时成功。
