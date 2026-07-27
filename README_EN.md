# Huaci Assistant

<p align="center">
  <strong>Select. Copy. Get an answer.</strong>
</p>

<p align="center">
  A system-wide translation and AI assistant for Windows. Copy text in any application to translate, explain, polish, summarize, or look it up in a floating window.
</p>

<p align="center">
  <a href="README.md">简体中文</a>
  ·
  <a href="https://github.com/ybhuang995-dev/huaci-assistant/releases">Download the latest release</a>
  ·
  <a href="https://github.com/ybhuang995-dev/huaci-assistant/issues">Report an issue</a>
</p>

<p align="center">
  <img
    src="images/悬浮窗分支树展示.png"
    alt="Huaci Assistant floating window and follow-up conversation tree"
    width="860"
  />
</p>

## Overview

Huaci Assistant is a Windows desktop productivity tool that runs in the background and watches the clipboard. Select text in a browser, Word, a PDF reader, an IDE, or another application, then press `Ctrl+C`. A floating window appears with the result, so you do not have to switch to a separate chat page.

The application is written in Python, with a tkinter-based floating window and a WebView2 settings panel. It supports OpenAI-compatible APIs. End users can download a packaged EXE from GitHub Releases, while developers can run or package the application from source.

## Features

| Feature | Description |
| --- | --- |
| Translation | Translate between Chinese and English while preserving formatting and tone where possible |
| Dictionary | Show phonetics, parts of speech, definitions, and examples for a single English word |
| Ask | Explain selected text, concepts, or code |
| Polish | Improve wording and grammar without changing the intended meaning |
| Summarize | Extract the key points from longer text |
| Streaming output | Display model responses as they are generated |
| Follow-up branches | Select part of an answer and continue with contextual, branching follow-up questions |
| History | Save, browse, and reopen previous queries |
| Custom modes | Enable or disable modes and edit their system prompts |
| Multiple providers | Use DeepSeek, OpenAI, SiliconFlow, or another OpenAI-compatible endpoint |

## Requirements

### Using the EXE

- Windows 10 or Windows 11
- WebView2 Runtime, which is already installed on most Windows 10/11 systems
- An API key for a supported model provider
- Network access to the configured model endpoint

### Running from source

- Windows 10 or Windows 11
- Python 3.10 or later
- pip

> Huaci Assistant relies on Windows clipboard APIs, the system tray, and WebView2. Linux, macOS, and WSL are not supported.

## Quick Start

### Option 1: Download the EXE

1. Open the [Releases page](https://github.com/ybhuang995-dev/huaci-assistant/releases).
2. Open the latest release and download the Windows EXE.
3. Run the downloaded file.
4. Right-click the Huaci Assistant icon in the system tray and open **Settings**.
5. Enter your API key, endpoint, and model name, then test the connection.
6. Select text in any application and press `Ctrl+C`.

An unsigned executable from an independent developer may trigger a Windows SmartScreen warning. Verify that the file came from this repository's Releases page and follow your own security policy before running it.

### Option 2: Run from source

```bash
git clone https://github.com/ybhuang995-dev/huaci-assistant.git
cd huaci-assistant

python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
python main.py
```

To activate the virtual environment in Windows Command Prompt:

```bat
.venv\Scripts\activate.bat
```

To activate it in Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

You can also start the application with:

```bat
run.bat
```

## Configuration

The recommended way to change settings is through **System tray → Settings**. Most changes take effect immediately without restarting the application.

You can also configure the application through a local `.env` file:

```bash
cp .env.example .env
```

Common options include:

| Variable | Purpose |
| --- | --- |
| `DEEPSEEK_API_KEY` | API key |
| `DEEPSEEK_BASE_URL` | OpenAI-compatible API endpoint |
| `DEEPSEEK_MODEL` | Model name |
| `PROVIDER` | Model provider |
| `DEFAULT_MODE` | Default processing mode |
| `AUTO_ROUTE` | Automatically select a processing mode |
| `HOTKEY_PAUSE` | Global shortcut for pausing or resuming clipboard monitoring |
| `SAVE_HISTORY` | Enable or disable local query history |
| `WINDOW_WIDTH` / `WINDOW_HEIGHT` | Floating-window dimensions |
| `POLL_INTERVAL` | Clipboard polling interval |

See [`.env.example`](.env.example) for all available variables and example values.

> Never commit `.env`. Keep API keys on your own device, and remove secrets from issues, logs, and screenshots.

## Usage

| Action | Default control |
| --- | --- |
| Trigger a query | Select text and press `Ctrl+C` |
| Close the floating window | `Esc` |
| Copy the result | `Enter` or the **Copy** button |
| Pause or resume monitoring | `Ctrl+Shift+P`, configurable in Settings |
| Change mode | Select a mode tab at the top of the floating window |
| Ask a follow-up | Select text in an answer and choose **Ask** from the context menu |
| View branches | Select **Conversation tree** |
| Open Settings | Right-click the system tray icon and select **Settings** |
| Exit | Right-click the system tray icon and select **Exit** |

The application filters common unwanted clipboard content, including duplicate values, file paths, URLs, very short text, and numeric-only values. If copying text does not open the window, check whether monitoring is paused and whether a relevant filter is enabled.

## Screenshots

### General and API settings

<p align="center">
  <img src="images/设置面板通用.png" alt="Huaci Assistant general settings" width="48%" />
  <img src="images/设置面板api配置.png" alt="Huaci Assistant API settings" width="48%" />
</p>

### Modes and prompts

<p align="center">
  <img src="images/设置面板模式prompt.png" alt="Huaci Assistant mode and prompt settings" width="55%" />
</p>

## Model Providers

An endpoint should generally work if it implements a compatible streaming OpenAI Chat Completions API.

| Provider | Example base URL |
| --- | --- |
| DeepSeek | `https://api.deepseek.com/v1` |
| OpenAI | `https://api.openai.com/v1` |
| SiliconFlow | `https://api.siliconflow.cn/v1` |
| Other compatible services | Use the endpoint documented by the provider |

Model names, pricing, rate limits, and data-handling policies vary between providers. Refer to your provider's documentation for authoritative details.

## Packaging from Source

The project uses the local PyInstaller specification file `划词助手.spec`. Install the application dependencies and PyInstaller:

```bash
pip install -r requirements.txt
pip install pyinstaller
```

Build the executable:

```bash
pyinstaller --clean --noconfirm 划词助手.spec
```

The generated executable is placed in `dist/`. Before publishing a release, test it on at least one Windows machine that does not have Python installed:

- The application starts and exits correctly.
- Clipboard monitoring, the system tray, and the floating window work.
- The WebView2 settings panel opens correctly.
- API settings can be saved and tested.
- All five modes and streaming responses work.
- The package does not contain a personal `.env`, API key, or history database.

Build artifacts should not be committed directly to Git. Attach the release EXE to the corresponding GitHub Release instead.

## Project Structure

```text
huaci-assistant/
├── main.py                  # Entry point, threads, and queue orchestration
├── floating_window.py       # Floating window, result rendering, and conversation tree
├── settings_window.py       # WebView2 settings panel and JavaScript bridge
├── clipboard_monitor.py     # Windows clipboard monitoring and filtering
├── engine.py                # Model requests, SSE streaming, and follow-ups
├── config.py                # Configuration, modes, prompts, and filters
├── autostart.py             # Windows startup integration
├── history.py               # SQLite query history
├── prototypes/
│   └── settings-panel.html  # Settings panel HTML, CSS, and JavaScript
├── images/                  # README screenshots
├── .env.example             # Safe configuration template
├── requirements.txt         # Python runtime dependencies
├── run.bat                  # Windows launcher
└── 划词助手.spec             # PyInstaller build configuration
```

## Development and Contributing

Bug reports and suggestions are welcome through [GitHub Issues](https://github.com/ybhuang995-dev/huaci-assistant/issues).

When reporting a problem, please include:

- Your Windows version
- Whether you are using the EXE or running from source
- The application version or Git commit
- Steps to reproduce the issue
- Expected and actual behavior
- Logs or screenshots with API keys and other sensitive information removed

Before submitting code:

1. Make changes on a dedicated branch.
2. Keep the change focused.
3. Do not commit `.env`, logs, history databases, or build artifacts.
4. Run at least the basic syntax check:

```bash
python -m py_compile main.py floating_window.py settings_window.py clipboard_monitor.py engine.py config.py autostart.py history.py
```

5. Manually test changes involving the GUI, clipboard, system tray, or model requests.

## Releases

The project uses Git tags and GitHub Releases:

- Python source code stays in this repository.
- Each release receives a tag such as `v1.0.0`.
- The packaged EXE is attached to the matching GitHub Release.
- Further development continues in the same repository.

Version numbers should follow [Semantic Versioning](https://semver.org/).

## Privacy and Security

- Selected clipboard text is sent to the model provider configured by the user.
- Storage and processing practices depend on that provider; review its privacy policy.
- Query history is stored locally in a SQLite database and can be controlled through Settings.
- Do not process confidential, personal, or regulated data that must not be sent to a third-party service.
- This project does not require API keys to be committed to GitHub.

## Known Limitations

- Windows is the only supported operating system.
- A compatible model service and API key are required.
- Some applications or protected interfaces may restrict clipboard access.
- An unsigned EXE may trigger Windows SmartScreen.
- Streaming behavior may vary between OpenAI-compatible providers.

## License

This repository does not currently contain a standalone license file. Until an explicit open-source license is added, the source code remains under the project author's default copyright.
