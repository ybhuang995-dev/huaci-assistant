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

- **语言**：Python（主人正在学，可同步讲解）
- **LLM API**：DeepSeek API（OpenAI 兼容）/ 后续可扩展 OpenAI、Ollama
- **剪贴板监听**：`pyperclip` 或 `win32clipboard`（轮询剪贴板变更）
- **全局热键**（可选）：`keyboard` 或 `pynput`（强制唤起悬浮窗，作为剪贴板监听的补充）
- **UI 悬浮窗**：先 `tkinter` 跑通，后续可升级 `PyQt6`
- **流式处理**：`httpx` 或 `aiohttp`（SSE streaming）
- **打包分发**：`PyInstaller` → 单 exe，系统托盘常驻，开机自启

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

## 引擎抽象层（精简版）

只支持 DeepSeek 不需要完整抽象工厂，但留扩展口：

```python
class BaseEngine:
    """引擎基类"""
    def translate(self, text: str, mode: str, stream: bool) -> str: ...
    def _build_prompt(self, text: str, mode: str) -> str: ...
    def _stream_request(self, messages: list) -> Iterator[str]: ...

class DeepSeekEngine(BaseEngine):
    """DeepSeek API（OpenAI 兼容）"""
    # api_base, api_key, model

class OllamaEngine(BaseEngine):   # 后续扩展
    """本地 Ollama 模型"""
```

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

### Phase 1：最小可用（MVP）
- [ ] 剪贴板监听（轮询检测变更）
- [ ] 智能过滤（去重 + 简单规则）
- [ ] DeepSeek API 调用（非流式翻译）
- [ ] tkinter 悬浮窗显示结果
- [ ] 系统托盘图标 + 右键菜单（启用/禁用/退出）
- [ ] 悬浮窗内模式切换（翻译/提问）

### Phase 2：完善体验
- [ ] SSE 流式输出（结果逐字出现）
- [ ] 悬浮窗优化：毛玻璃效果、置顶、拖拽、鼠标旁弹出
- [ ] 单词检测 → 词典模式（发音+词性+例句）
- [ ] Enter 复制结果、Esc 关闭
- [ ] 全局热键补充（强制唤起悬浮窗，不依赖剪贴板）

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

## 输出风格

- 每个 phase 开始前先讲设计思路，再写代码
- 代码同步解释原理（主人在学 Python）
- 改完就跑通验证
