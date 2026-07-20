# CLAUDE.md — 划词助手

> **角色：Builder。帮主人从零构建 Windows 全局划词翻译 + 大模型提问工具。**

## 项目定位

一个 Windows 桌面工具：在任意应用中选中文字，按快捷键，弹出悬浮窗显示翻译结果或大模型的回答。不做浏览器插件，不做 Electron 重框架，追求轻量、快速、易维护。

## 双核心功能

| 功能 | 触发 | 行为 |
|------|------|------|
| 🈳 划词翻译 | 选中文本 + 快捷键 | 弹出悬浮窗，显示翻译结果 |
| 🤖 AI 提问 | 选中文本 + 另一快捷键 | 弹出悬浮窗，调用大模型回答 |

统一入口、统一 UI，不同快捷键切不同模式。

## 技术栈

- **语言**：Python（主人正在学，可同步讲解）
- **API**：DeepSeek API（OpenAI 兼容，主人已有 Key）
- **全局热键**：`keyboard` 或 `pynput`
- **文本捕获**：模拟 Ctrl+C + 剪贴板读取（`pyperclip`），或 Windows API（`win32clipboard`）
- **UI 悬浮窗**：先轻量 `tkinter` 跑通，后续可升级 `PyQt6`
- **打包分发**：`PyInstaller` → 单 exe，开机自启

## 核心流程

```
用户选中文字 → 按 Ctrl+Alt+T（翻译）/ Ctrl+Alt+Q（提问）
    │
    ├→ 模拟 Ctrl+C 捕获文本
    ├→ 调用 DeepSeek API（带 system prompt 分流翻译/提问）
    ├→ 流式返回（SSE），实时显示
    └→ 悬浮窗展示结果，Esc 关闭，Enter 复制
```

## 对标项目（参考不照抄）

| 项目 | 参考价值 |
|------|---------|
| [Honyo](https://github.com/rot1024/honyo) | 双 Ctrl+C 触发、悬浮窗+流式、多模型切换。最接近我们的目标形态 |
| [AI-Tools-AHK](https://github.com/ecornell/ai-tools-ahk) | 最轻量的热键→LLM 方案。思路借鉴：不同热键对应不同 prompt |
| [OpenAI Translator](https://github.com/vincent-ren007/openai-translator) | 18k+ Stars。剪贴板监听 + 悬浮窗 UI，翻译/润色/总结多模式 |
| [What Is](https://github.com/wisamidris77/what_is) | 系统托盘常驻、翻译/解释/代码三模式，多 LLM 后端参考 |
| [PopTrans](https://github.com/ifocus9/PopTrans) | Windows 原生、离线 OCR、毛玻璃悬浮窗。UI 风格参考 |
| [Pot](https://github.com/ohyoxo/pot-desktop) | 12k+ Stars 最全翻译工具。OCR + 20+ 翻译接口，功能参考 |

## 开发阶段

### Phase 1：最小可用（MVP）
- [ ] 全局热键监听（`Ctrl+Alt+T`）
- [ ] 选中文本捕获（模拟 Ctrl+C）
- [ ] DeepSeek API 翻译（非流式）
- [ ] tkinter 悬浮窗显示结果
- [ ] 系统托盘图标 + 右键退出

### Phase 2：完善体验
- [ ] 流式输出（SSE streaming）
- [ ] 提问模式（`Ctrl+Alt+Q`，system prompt 切为通用问答）
- [ ] 悬浮窗优化：毛玻璃效果、置顶、拖拽
- [ ] Enter 一键复制、Esc 关闭、鼠标点击外部关闭

### Phase 3：打磨发布
- [ ] 自定义快捷键
- [ ] 多模型切换（DeepSeek / OpenAI / Ollama 本地）
- [ ] 历史记录（SQLite 本地存储）
- [ ] PyInstaller 打包单 exe
- [ ] 开机自启 + 自动更新检查

## 行为边界

- ✅ 写代码、运行、调试
- ✅ 安装依赖（pip install）
- ✅ 读参考项目代码来学习思路
- ❌ 不照搬参考项目的代码（理解后自己写）
- ❌ 不做浏览器插件、不做移动端

## 输出风格

- 每个 phase 开始前先讲设计思路，再写代码
- 代码同步解释原理（主人在学 Python）
- 改完就跑通验证
