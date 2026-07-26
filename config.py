"""
配置管理模块
-----------
从 .env 加载 API 配置，定义四种模式的 system prompt 和过滤规则。
"""

import json as _json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


class Config:
    """应用全局配置"""

    # ── DeepSeek API ────────────────────────────────────
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
    )
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # ── 剪贴板监听 ──────────────────────────────────────
    POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "0.4"))  # 轮询间隔（秒）

    # ── 窗口 ────────────────────────────────────────────
    WINDOW_WIDTH = int(os.getenv("WINDOW_WIDTH", "800"))
    WINDOW_HEIGHT = int(os.getenv("WINDOW_HEIGHT", "600"))

    # ── 通用 ────────────────────────────────────────────
    DEFAULT_MODE = os.getenv("DEFAULT_MODE", "translate")
    FONT = os.getenv("FONT", "Microsoft YaHei UI")
    AUTO_DICT = os.getenv("AUTO_DICT", "true").lower() == "true"
    AUTO_START = os.getenv("AUTO_START", "false").lower() == "true"
    AUTO_ROUTE = os.getenv("AUTO_ROUTE", "false").lower() == "true"
    SAVE_HISTORY = os.getenv("SAVE_HISTORY", "false").lower() == "true"
    HOTKEY_PAUSE = os.getenv("HOTKEY_PAUSE", "ctrl+shift+p")
    PROVIDER = os.getenv("PROVIDER", "DeepSeek")


# ═══════════════════════════════════════════════════════════
# 模式定义
# ═══════════════════════════════════════════════════════════

MODES = {
    "translate": {
        "label": "翻译",
        "system_prompt": (
            "你是一个专业的翻译助手。请将用户输入的文本翻译成中文。"
            "如果输入已经是中文，则翻译成英文。"
            "保持原文的格式、语气和风格。"
            "只返回翻译结果，不要添加任何解释。"
        ),
    },
    "ask": {
        "label": "提问",
        "system_prompt": (
            "你是一个知识渊博的 AI 助手。根据用户选中的文本提供清晰、准确的回答。\n"
            "- 如果文本是一个问题，直接回答。\n"
            "- 如果文本是一个概念或术语，给出简明解释。\n"
            "- 如果文本是一段代码，解释代码的功能、逻辑和关键实现细节，"
            "指出潜在问题或可改进之处。\n"
            "- 如果文本是一段内容，给出分析或总结。\n"
            "请用中文回答。"
        ),
    },
    "polish": {
        "label": "润色",
        "system_prompt": (
            "你是一个文字润色助手。请优化以下文字的表达，使其更加流畅、优美。\n"
            "- 纠正语法错误和错别字。\n"
            "- 保持原意不变。\n"
            "- 保持原文的语言（中文保持中文，英文保持英文）。\n"
            "只返回润色后的文本。"
        ),
    },
    "summarize": {
        "label": "总结",
        "system_prompt": (
            "你是一个内容总结助手。请用简洁的要点总结以下内容的核心信息。\n"
            "- 用无序列表（- ）列出 3-5 个关键要点。\n"
            "- 每个要点不超过一句话。\n"
            "- 保留原文中的重要数据和专有名词。\n"
            "请用中文输出。"
        ),
    },
    "dict": {
        "label": "词典",
        "system_prompt": (
            "你是一个专业的英语词典。请对用户输入的单词给出详细解释。\n\n"
            "**格式要求**（用 Markdown）：\n"
            "- 音标：英式 /ˈxxx/　美式 /ˈxxx/\n"
            "- 词性：名词 / 动词 / 形容词 等\n"
            "- 主要释义（含中文翻译），按常用度排列\n"
            "- 2-3 个英文例句（带中文翻译）\n"
            "- 如有常见搭配或同义词，简要列出\n\n"
            "保持简洁清晰，适合快速查阅。"
        ),
    },
}

# ── 保存出厂默认值（供设置面板"恢复默认"使用）─────────
# 必须在 .env 覆盖之前保存，否则恢复默认拿到的是已修改的值

# ── 自动路由分类器 Prompt ─────────────────────────────

CLASSIFIER_PROMPT = (
    "你是一个文本分类器。分析用户文本，只返回 {\"mode\": \"<key>\"}。\n\n"
    "可用模式：\n"
    "- translate: 非中文的外语文本（英文/日文/韩文等），需要翻译成中文\n"
    "- ask: 中文问题、概念、术语、代码，需要解释或回答\n"
    "- polish: 中文文本的语法和表达优化\n"
    "- summarize: 长文本（>200字）的要点提炼\n"
    "- dict: 单个英文单词的词典释义（发音+词性+例句）\n\n"
    "判断规则（按顺序，命中即停）：\n"
    "1. 单个英文单词（如 hello、algorithm、serendipity）→ dict\n"
    "2. 非中文文本（英文句子/段落/日文/韩文）→ translate\n"
    "3. 中文文本 → 按以下子规则：\n"
    "   a. 包含疑问（什么/怎么/为什么/如何/能不能/解释/这段代码）→ ask\n"
    "   b. 超过 200 字的长篇信息 → summarize\n"
    "   c. 有明显语法错误、不通顺、需要改写 → polish\n"
    "   d. 以上都不符合 → ask\n"
    "4. 代码片段（任何编程语言）→ ask\n\n"
    "⚠️ 中文文本永远不要选 translate。translate 只用于外语翻译成中文。\n"
    "只返回 JSON，不要任何其他文字。"
)

_FACTORY_MODE_PROMPTS = {mk: MODES[mk]["system_prompt"] for mk in MODES}
_FACTORY_MODE_ENABLED = {mk: True for mk in MODES}
_FACTORY_FILTERS = {
    "too_short": True, "numbers": True, "paths": True,
    "url": True, "filename": True,
}

# ── 从 .env 加载模式 Prompt 覆盖 ─────────────────────
_MODE_PROMPTS_RAW = os.getenv("MODE_PROMPTS", "")
if _MODE_PROMPTS_RAW:
    try:
        _overrides = _json.loads(_MODE_PROMPTS_RAW)
        for mk, prompt in _overrides.items():
            if mk in MODES:
                MODES[mk]["system_prompt"] = prompt
    except (_json.JSONDecodeError, TypeError):
        pass

# ── 从 .env 加载模式启用状态 ─────────────────────────
_MODE_ENABLED_RAW = os.getenv("MODE_ENABLED", "")
MODE_ENABLED = {}
if _MODE_ENABLED_RAW:
    try:
        MODE_ENABLED = _json.loads(_MODE_ENABLED_RAW)
    except (_json.JSONDecodeError, TypeError):
        pass
if not MODE_ENABLED:
    MODE_ENABLED = {mk: True for mk in MODES}

# ── 从 .env 加载过滤器开关 ───────────────────────────
_FILTERS_RAW = os.getenv("FILTERS", "")
FILTERS_ENABLED = {
    "too_short": True, "numbers": True, "paths": True,
    "url": True, "filename": True,
}
if _FILTERS_RAW:
    try:
        FILTERS_ENABLED.update(_json.loads(_FILTERS_RAW))
    except (_json.JSONDecodeError, TypeError):
        pass

# ── 单词检测 ──────────────────────────────────────────

import re as _re  # noqa: E402

def is_single_english_word(text: str) -> bool:
    """检测是否为单个英语单词（2-30 个字母）"""
    return bool(_re.match(r"^[a-zA-Z]{2,30}$", text.strip()))

# 默认模式
DEFAULT_MODE = os.getenv("DEFAULT_MODE", "translate")

# 各模式的窗口标题
MODE_TITLES = {
    "translate": "翻译",
    "ask": "AI 问答",
    "polish": "润色",
    "summarize": "总结",
}

# ═══════════════════════════════════════════════════════════
# 智能过滤规则（用于剪贴板内容判断是否触发弹窗）
# ═══════════════════════════════════════════════════════════

import re  # noqa: E402

FILTER_RULES = [
    # 过短（< 2 个有效字符）
    (re.compile(r"^.{0,1}$"), "too_short"),
    # 纯数字 + 常见符号
    (re.compile(r"^[\d\s.,+\-*/=%%$€£¥()[\]{}<>|&^~#@!;:'""`]+$"), "numbers"),
    # Windows 路径（C:\...  D:/...  \\server\...）
    (re.compile(r"^[A-Za-z]:[\\/]"), "paths"),
    # UNC 路径
    (re.compile(r"^\\\\"), "paths"),
    # Unix 绝对路径
    (re.compile(r"^/"), "paths"),
    # 纯 URL
    (re.compile(r"^https?://\S+$"), "url"),
    # 单文件名（含扩展名）
    (re.compile(r"^[\w\-. ]+\.[a-zA-Z]{2,6}$"), "filename"),
    # 纯数字
    (re.compile(r"^\d+$"), "numbers"),
]
