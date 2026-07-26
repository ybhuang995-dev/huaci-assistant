# 划词助手

> **选中，复制，答案即来。**

在任何应用中选中文字、按 `Ctrl+C`，悬浮窗自动弹出——翻译、解释、润色、总结，AI 已经把答案准备好了。不用切换窗口，不用记快捷键，不打断你的心流。

<p align="center">🚀 <a href="https://github.com/ybhuang995-dev/huaci-assistant/releases"><b>立即下载 EXE</b></a>（Windows 10+，无需 Python）</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/ybhuang995-dev/huaci-assistant/main/images/%E6%82%AC%E6%B5%AE%E7%AA%97%E5%88%86%E6%94%AF%E6%A0%91%E5%B1%95%E7%A4%BA.png" alt="悬浮窗翻译与追问分支树" width="85%" />
</p>

## 能做什么

| 模式 | 说明 |
|------|------|
| 🌐 **翻译** | 中英互译，保留原文格式和语气 |
| 📖 **词典** | 选中单词自动查词，音标、词性、释义、例句一次呈现 |
| 💡 **提问** | 向 AI 提问选中的文字，代码解释也不在话下 |
| ✨ **润色** | 优化表达，修正语法，不改变原意 |
| 📝 **总结** | 3–5 个要点提炼长文本，快速抓住核心 |

**智能之处：**

- **自动路由** — LLM 判断你选中的是什么（单词？句子？代码？），自动选对模式
- **追问对话树** — 在 AI 回答中划选文字继续追问，支持多轮分支对话
- **历史记录** — 每次查询自动保存，可随时回溯
- **多 API 支持** — DeepSeek、OpenAI、SiliconFlow 及所有 OpenAI 兼容接口

## 快速开始

**前提：** Windows 10+ · 一个 API Key（无需安装 Python）

### 方式一：下载 EXE（推荐）

从 [Releases](https://github.com/ybhuang995-dev/huaci-assistant/releases) 下载 `划词助手.exe`，双击即用。首次使用在托盘右键 → **设置** → **API 配置** 中填写 Key。

### 方式二：从源码运行

需要 Python 3.10+

```bash
git clone https://github.com/ybhuang995-dev/huaci-assistant.git
cd 划词助手
pip install -r requirements.txt
python main.py
```

首次运行在托盘右键 → 设置 → API 配置中填写 Key 即可，或手动 `cp .env.example .env` 编辑。

> DeepSeek 免费注册获取 Key：https://platform.deepseek.com/api_keys

启动后任务栏右下角出现托盘图标 🅐，右键可暂停监听、打开设置、退出。

## 怎么用

在任意应用（浏览器、Word、记事本、IDE…）中**选中文字 → Ctrl+C**，悬浮窗就会出现。

| 操作 | 快捷键 |
|------|--------|
| 触发 | 选中文字 + `Ctrl+C` |
| 关闭悬浮窗 | `Esc` |
| 复制结果 | `Enter` |
| 暂停/恢复 | `Ctrl+P`（可自定义） |
| 切换模式 | 点击悬浮窗顶部标签 |
| 追问 | 在回答中划选文字 → 右键「💬 追问」 |
| 设置 | 托盘右键 → 设置 |

## 设置

托盘右键 → **设置**，所有配置都在一个面板里：

<p align="center">
  <img src="https://raw.githubusercontent.com/ybhuang995-dev/huaci-assistant/main/images/%E8%AE%BE%E7%BD%AE%E9%9D%A2%E6%9D%BF%E9%80%9A%E7%94%A8.png" alt="通用设置" width="45%" />
  &nbsp;
  <img src="https://raw.githubusercontent.com/ybhuang995-dev/huaci-assistant/main/images/%E8%AE%BE%E7%BD%AE%E9%9D%A2%E6%9D%BFapi%E9%85%8D%E7%BD%AE.png" alt="API 配置" width="45%" />
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/ybhuang995-dev/huaci-assistant/main/images/%E8%AE%BE%E7%BD%AE%E9%9D%A2%E6%9D%BF%E6%A8%A1%E5%BC%8Fprompt.png" alt="模式 Prompt 自定义" width="45%" />
</p>

- **通用** — 窗口尺寸、字体、开机自启、自动路由等功能开关
- **API** — 切换 Provider、修改接口地址和模型、测试连接
- **Prompt** — 启用/禁用某个模式、自定义每种模式的 System Prompt

## 切换 API 提供商

支持所有 OpenAI 兼容接口：

| Provider | Base URL |
|----------|----------|
| DeepSeek | `https://api.deepseek.com/v1` |
| OpenAI | `https://api.openai.com/v1` |
| SiliconFlow | `https://api.siliconflow.cn/v1` |
| 其他兼容服务 | 填你的接口地址即可 |

## 项目结构

```
划词助手/
├── main.py                  # 入口，多线程调度
├── floating_window.py       # 悬浮窗 UI
├── settings_window.py       # 设置面板
├── clipboard_monitor.py     # 剪贴板监听
├── engine.py                # LLM 引擎
├── config.py                # 配置管理 + 模式定义
├── autostart.py             # 开机自启
├── history.py               # 历史记录
├── prototypes/
│   └── settings-panel.html  # 设置面板前端
├── images/                   # 截图
├── requirements.txt
├── run.bat
└── .env.example             # 配置模板（复制为 .env 填入密钥即可）
```

## 开源协议

MIT

> [English](README_EN.md)

> [English version](README_EN.md)

> [English version](README_EN.md)
