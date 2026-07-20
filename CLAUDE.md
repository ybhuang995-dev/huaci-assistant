# CLAUDE.md — 划词助手

> **角色：Builder。帮主人从零构建 Windows 全局划词翻译 + 大模型提问工具。**

## 项目定位

一个 Windows 桌面工具：在任意应用中选中文字，Ctrl+C 复制，自动弹出悬浮窗显示翻译或大模型回答。不做浏览器插件、不做 Electron 重框架，追求轻量、快速、易维护。

## 核心交互（借鉴 OpenAI Translator 后修正）

```
用户选中文字 → Ctrl+C（正常复制操作）
    │
    ▼
后台监听剪贴板变更
    │
    ├→ 智能过滤（去重 / 路径 / 太短 / 无意义）
    │
    ├→ 通过 → 弹出悬浮窗
    │        ┌─────────────────────────────┐
    │        │ [翻译] [提问] [润色] [总结]  │  ← 模式切换标签
    │        ├─────────────────────────────┤
    │        │  原文: Hello world          │
    │        │                             │
    │        │  ── 结果（流式输出）──       │
    │        │  你好，世界                  │
    │        ├─────────────────────────────┤
    │        │ [📋 复制] [🔄 重试] [✕]   │
    │        └─────────────────────────────┘
    │
    └→ 不通过 → 不弹窗，静默忽略
```

**为什么剪贴板而非选中文本**：OpenAI Translator 的核心设计——"复制即翻译"。用户本就要 Ctrl+C，不增加任何额外操作。且绕过了 Windows 选中文本捕获的技术难点（不同应用获取选中文本的方式不一致）。

## 技术栈

- **语言**：Python 3.10+
- **LLM API**：DeepSeek API（OpenAI 兼容）/ 后续可扩展 OpenAI、Ollama
- **剪贴板监听**：`ctypes` 直接调用 Windows API（`OpenClipboard`/`GetClipboardData`/`GlobalLock`），轮询间隔 400ms
- **UI 悬浮窗**：`tkinter`（无边框 Toplevel，置顶，可拖拽），浅色主题
- **HTTP 请求**：`requests`（当前非流式，后续换 `httpx` 做 SSE streaming）
- **系统托盘**：`pystray` + `Pillow`（生成托盘图标）
- **配置管理**：`python-dotenv`（`.env` 文件）
- **打包分发**：`PyInstaller` → 单 exe，系统托盘常驻，开机自启

> **已废弃的尝试**：`keyboard` 库 + `keybd_event`/`SendInput` 模拟 Ctrl+C。原因：键盘钩子线程重入导致死锁。剪贴板监听方案更简单可靠。

## 智能过滤（防误触）

OpenAI Translator 的经验：如果没有过滤，复制文件路径、单个字母、数字等也会弹窗，极其烦人。

```
剪贴板变更
  ├→ 与上次内容完全相同 → 跳过（去重）
  ├→ 纯文件路径（匹配盘符 / 路径分隔符）→ 跳过
  ├→ 纯数字 / 纯符号 → 跳过
  ├→ 字符数 < 2 → 跳过
  ├→ 纯 URL → 跳过
  └→ 以上都不匹配 → 触发弹出
```

## 模式设计（Prompt 驱动）

借鉴 OpenAI Translator——翻译、润色、总结、提问共用同一调用逻辑，差异只在 system prompt：

| 模式 | 默认快捷键 | System Prompt |
|------|-----------|---------------|
| 翻译 | 弹出窗默认 | "你是专业翻译，保留技术术语……" |
| 提问 | 弹出窗内切换 | "你是通用 AI 助手，回答用户问题……" |
| 润色 | 弹出窗内切换 | "优化以下文字的表达，不改原意……" |
| 总结 | 弹出窗内切换 | "用简洁的要点总结以下内容……" |

## 引擎层（当前实现）

只有一个 `DeepSeekEngine`，调用 OpenAI 兼容 API。后续扩展再加抽象。

```python
class DeepSeekEngine:
    """DeepSeek API（OpenAI 兼容）"""
    def query(self, text: str, mode: str) -> str:
        """根据 mode 查 MODES 配置的 system_prompt，调用 /chat/completions"""

# 全局单例
engine = DeepSeekEngine()
```

## 架构（当前实现）

```
┌─────────────────┐     _clip_queue      ┌──────────┐
│ ClipboardMonitor │ ─────────────────→  │ 主线程    │
│ (daemon thread)  │                     │ (tkinter) │
│ 轮询 400ms       │                     │ _tick()   │
│ 智能过滤         │                     │ 100ms     │
└─────────────────┘                     └──────────┘
                                               │
                                         显示/刷新悬浮窗
                                         放入 _work_queue
                                               │
                                               ▼
                                        ┌──────────┐
                                        │ Worker   │
                                        │ (daemon) │
                                        │ 调 API   │
                                        └──────────┘
                                               │
                                         root.after()
                                         更新结果区域
```

**关键设计决策**：
- **双队列**：`_clip_queue`（剪贴板事件 → 主线程处理）和 `_work_queue`（API 查询 → 工作线程处理）分离，避免早期单队列导致的互相干扰 bug
- **查询计数器**：`_query_counter` 全局递增，每次新查询 +1。Worker 返回结果时检查 `query_id`，如果已有更新查询则丢弃旧结果，防止过期结果覆盖新内容
- **三层去重**：① 监听器层（标准化文本 `==` 比较）② 回调层（`_last_callback_text`）③ `mark_as_seen()`（主动复制结果时标记，避免自己写入剪贴板触发弹窗）

## 对标项目

| 项目 | Stars | 参考价值 |
|------|-------|---------|
| [Honyo](https://github.com/rot1024/honyo) | ~1k | 双 Ctrl+C 触发、悬浮窗+流式、多模型切换。形态最接近我们的目标 |
| [AI-Tools-AHK](https://github.com/ecornell/ai-tools-ahk) | ~500 | 最轻量的热键→LLM 方案。不同热键对应不同 prompt |
| [OpenAI Translator](https://github.com/yetone/openai-translator) | 18k+ | **最大参考源**。剪贴板监听+悬浮窗、6 种模式 prompt 驱动、智能过滤、Tauri+Rust 桌面端 |
| [What Is](https://github.com/wisamidris77/what_is) | ~200 | 系统托盘 + 翻译/解释/代码三模式，多 LLM 后端 |
| [PopTrans](https://github.com/ifocus9/PopTrans) | ~300 | Windows 原生、离线 OCR、毛玻璃悬浮窗 |
| [Pot](https://github.com/ohyoxo/pot-desktop) | 12k+ | 最全翻译工具，OCR + 20+ 接口，功能方向的终极参考 |

## OpenAI Translator 关键借鉴

深入分析后，以下设计直接采纳：

| 借鉴 | 说明 |
|------|------|
| 剪贴板监听触发 | 非热键捕获选中文本。Copy = Translate，零额外学习成本 |
| 富过滤 | 去重、路径检测、长度判断——避免误触发是体验核心 |
| Prompt 驱动模式 | 翻译/提问/润色/总结共用一套代码，差异只在 system prompt |
| 单词检测→词典模式 | 输入为单个单词时自动切词典（发音+词性+例句） |
| 悬浮窗内模式切换 | 一个窗口，标签切换模式，而非多个快捷键 |
| 留引擎扩展口 | 先实现 DeepSeek，接口设计兼容后续 Ollama/OpenAI |

## 开发阶段

### Phase 1：最小可用（MVP）✅ 已完成
- [x] 剪贴板监听（ctypes 轮询，400ms 间隔）
- [x] 智能过滤（8 条正则规则：去重/路径/URL/文件名/纯数字/太短）
- [x] DeepSeek API 调用（非流式，4 种模式）
- [x] tkinter 悬浮窗（浅色主题，500×400，鼠标旁弹出）
- [x] 系统托盘图标 + 右键菜单（退出）
- [x] 悬浮窗内模式切换（翻译/提问/润色/总结）
- [x] 双队列架构 + 查询计数器（防过期结果覆盖）
- [x] Enter 复制结果、Esc 关闭
- [x] 拖拽移动窗口

### Phase 2：完善体验
- [ ] SSE 流式输出（结果逐字出现）
- [ ] 悬浮窗优化：毛玻璃效果、窗口大小可调
- [ ] 单词检测 → 词典模式（发音+词性+例句）
- [ ] 全局热键补充（强制唤起悬浮窗，不依赖剪贴板）
- [ ] 复制按钮视觉反馈（已复制提示）
- [ ] 加载动画（⏳ 替换为骨架屏/spinner）

### Phase 3：打磨发布
- [ ] 自定义快捷键、自定义 Prompt
- [ ] 多模型切换（DeepSeek / OpenAI 兼容 / Ollama 本地）
- [ ] 历史记录（SQLite）
- [ ] PyInstaller 打包单 exe
- [ ] 开机自启
- [ ] 自动更新检查（可选）

## 行为边界

- ✅ 写代码、运行、调试
- ✅ 安装依赖（pip install）
- ✅ 读参考项目源码学习思路
- ❌ 不照搬参考项目的代码（理解后自己实现）
- ❌ 不做浏览器插件、不做移动端

## 项目结构

```
划词助手/
├── main.py              ← 主入口：三线程 + 双队列 + 托盘
├── clipboard_monitor.py ← ctypes 剪贴板轮询 + 8 条正则过滤
├── floating_window.py   ← 悬浮窗：标签栏 + 原文 + 结果 + 操作栏
├── engine.py            ← DeepSeek API（OpenAI 兼容）
├── config.py            ← 配置管理：模式定义、过滤规则、API Key
├── requirements.txt     ← 依赖（requests pystray Pillow python-dotenv）
├── run.bat              ← Windows 一键启动
├── .env.example         ← 配置模板
├── .env                 ← 实际配置（已 gitignore）
├── .gitignore
├── CLAUDE.md            ← 本文件
├── text_capture.py      ← 废弃：Ctrl+C 模拟方案
└── deepseek_client.py   ← 废弃：旧 API 客户端
```

## 输出风格

- 每个 phase 开始前先讲设计思路，再写代码
- 代码同步解释原理（主人在学 Python）
- 改完就跑通验证
