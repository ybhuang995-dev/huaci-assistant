# Huaci Assistant

> **Select. Copy. Done.**

Select text, press `Ctrl+C` — a floating window pops up with translation, explanation, polish, or summary. No window switching, no extra hotkeys, no flow interruption.

<p align="center">🚀 <a href="https://github.com/ybhuang995-dev/huaci-assistant/releases"><b>Download EXE</b></a> &nbsp;(Windows 10+, no Python required)</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/ybhuang995-dev/huaci-assistant/main/images/%E6%82%AC%E6%B5%AE%E7%AA%97%E5%88%86%E6%94%AF%E6%A0%91%E5%B1%95%E7%A4%BA.png" alt="Floating window with translation and follow-up question tree" width="85%" />
</p>

## What It Does

| Mode | |
|------|---|
| 🌐 **Translate** | Bidirectional Chinese ↔ English, preserves formatting and tone |
| 📖 **Dictionary** | Auto-detects single words — phonetics, POS, definitions, examples in one view |
| 💡 **Ask** | Ask AI about the selected text — code explanation included |
| ✨ **Polish** | Refine phrasing, fix grammar, keep the original meaning |
| 📝 **Summarize** | 3–5 bullet points to quickly digest long passages |

**Smart features:**

- **Auto Router** — The LLM figures out what you selected (word? sentence? code?) and picks the right mode
- **Follow-up Tree** — Select text in the AI's answer to ask deeper, with a branching conversation tree
- **History** — Every query saved automatically, browse and recall anytime
- **Multi-API** — Works with DeepSeek, OpenAI, SiliconFlow, and any OpenAI-compatible endpoint

## Quick Start

**Prerequisites:** Windows 10+ · An API key (no Python installation needed)

### Option 1: Download EXE (Recommended)

Grab `划词助手.exe` from [Releases](https://github.com/ybhuang995-dev/huaci-assistant/releases), double-click to run. Then tray icon → right-click → **Settings** → **API Config**, enter your key, done.

### Option 2: Run from Source

Requires Python 3.10+

```bash
git clone https://github.com/ybhuang995-dev/huaci-assistant.git
cd 划词助手
pip install -r requirements.txt
python main.py
```

On first run, configure your API key via tray icon → Settings → API Config. Or manually run `cp .env.example .env` and edit the file.

> Get a free DeepSeek key: https://platform.deepseek.com/api_keys

Look for the 🅐 tray icon after launch. Right-click to pause/resume, open settings, or exit.

## How to Use

Select text in any app (browser, Word, Notepad, IDE…) → **Ctrl+C**, and the floating window appears.

| Action | Shortcut |
|--------|----------|
| Trigger | Select text + `Ctrl+C` |
| Dismiss window | `Esc` |
| Copy result | `Enter` |
| Pause / Resume | `Ctrl+P` (customizable) |
| Switch mode | Click the top tab bar |
| Follow-up | Select text in answer → right-click "💬 Ask" |
| Settings | Tray icon → right-click → Settings |

## Settings

Tray icon → right-click → **Settings** — everything in one panel:

<p align="center">
  <img src="https://raw.githubusercontent.com/ybhuang995-dev/huaci-assistant/main/images/%E8%AE%BE%E7%BD%AE%E9%9D%A2%E6%9D%BF%E9%80%9A%E7%94%A8.png" alt="General settings" width="45%" />
  &nbsp;
  <img src="https://raw.githubusercontent.com/ybhuang995-dev/huaci-assistant/main/images/%E8%AE%BE%E7%BD%AE%E9%9D%A2%E6%9D%BFapi%E9%85%8D%E7%BD%AE.png" alt="API configuration" width="45%" />
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/ybhuang995-dev/huaci-assistant/main/images/%E8%AE%BE%E7%BD%AE%E9%9D%A2%E6%9D%BF%E6%A8%A1%E5%BC%8Fprompt.png" alt="Mode prompt customization" width="45%" />
</p>

- **General** — Window size, font, auto-start, auto route, and other toggles
- **API** — Switch provider, change endpoint and model, test connection
- **Prompt** — Enable/disable modes, customize the system prompt for each mode

## API Providers

Works with any OpenAI-compatible API:

| Provider | Base URL |
|----------|----------|
| DeepSeek | `https://api.deepseek.com/v1` |
| OpenAI | `https://api.openai.com/v1` |
| SiliconFlow | `https://api.siliconflow.cn/v1` |
| Custom | Your own endpoint |

## Project Structure

```
划词助手/
├── main.py                  # Entry point, multi-threaded pipeline
├── floating_window.py       # Floating window UI
├── settings_window.py       # Settings panel
├── clipboard_monitor.py     # Clipboard watcher
├── engine.py                # LLM engine (SSE streaming)
├── config.py                # Configuration & mode definitions
├── autostart.py             # Windows startup registry
├── history.py               # Query history (SQLite)
├── prototypes/
│   └── settings-panel.html  # Settings panel frontend
├── images/                  # Screenshots
├── requirements.txt
├── run.bat
└── .env.example             # Config template (copy to .env with your key)
```

## License

MIT

> [中文版](README.md)
