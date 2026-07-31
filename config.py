"""
配置管理模块
-----------
从 .env 加载 API 配置，定义四种模式的 system prompt 和过滤规则。
"""

import json as _json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def _get_data_dir() -> Path:
    """数据目录。—— 打包后 exe 同目录，开发中项目根目录"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


load_dotenv(_get_data_dir() / ".env")


class Config:
    """应用全局配置"""

    # ── DeepSeek API ────────────────────────────────────
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
    )
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

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
    HISTORY_MIN_NODES = int(os.getenv("HISTORY_MIN_NODES", "3"))

    # ── 用户方向（可选）───────────────────────────────
    USER_DIRECTION = os.getenv("USER_DIRECTION", "")


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
        "classifier_desc": "- translate: 非中文的外语文本（英文/日文/韩文等），需要翻译成中文",
    },
    "ask": {
        "label": "提问",
        "system_prompt": (
            "你是一个知识渊博的 AI 助手。根据用户选中的文本提供清晰、准确的回答。\n"
            "- 如果文本是一个问题，直接回答。\n"
            "- 如果文本是一个概念或术语，给出简明解释。\n"
            "- 如果文本是一段内容，给出分析或总结。\n"
            "请用中文回答。"
        ),
        "classifier_desc": "- ask: 中文问题、概念、术语，需要解释或回答",
    },
    "code": {
        "label": "代码",
        "system_prompt": (
            "你是一个专业的代码助手。请对用户提供的代码进行全面分析。\n\n"
            "**分析要点：**\n"
            "- 简要说明代码的整体功能和用途\n"
            "- 逐段解释核心逻辑和关键实现细节\n"
            "- 指出潜在的 bug、边界条件问题或安全隐患\n"
            "- 提出性能优化或代码结构改进建议\n"
            "- 如果用户明确要求，可以重构或改写代码\n\n"
            "**格式要求：**\n"
            "- 使用 Markdown 排版，代码块标记正确的语言类型\n"
            "- 对比代码用 diff 格式标注变更\n"
            "- 复杂度较高的逻辑可配图表或伪代码辅助说明\n\n"
            "请用中文回答，代码标识符和注释保持原文语言。"
        ),
        "classifier_desc": "- code: 代码片段（任何编程语言），需要解释、审查、调试或优化",
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
        "classifier_desc": "- summarize: 长文本（>200字）的要点提炼",
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
        "classifier_desc": "- dict: 单个英文单词的词典释义（发音+词性+例句）",
    },
}

# ── 保存出厂默认值（供设置面板"恢复默认"使用）─────────
# 必须在 .env 覆盖之前保存，否则恢复默认拿到的是已修改的值

_FACTORY_MODE_PROMPTS = {mk: MODES[mk]["system_prompt"] for mk in MODES}
_FACTORY_MODE_ENABLED = {mk: True for mk in MODES}
_FACTORY_MODE_CLASSIFIER_DESCS = {mk: MODES[mk]["classifier_desc"] for mk in MODES}
_FACTORY_CUSTOM_MODES: list = []
_FACTORY_FILTERS = {
    "too_short": True, "numbers": True, "paths": True,
    "url": True, "filename": True,
}


def build_classifier_prompt() -> str:
    """动态生成分类器 prompt，只列出 MODE_ENABLED 中启用的模式。

    这样用户取消勾选的模式不会出现在 LLM 的可选项中，
    避免 LLM 选中一个已被禁用的模式再被 fallback 截掉。
    """
    enabled = {mk for mk in MODES if MODE_ENABLED.get(mk, True)}

    def _get_desc(mk: str) -> str:
        return MODES[mk].get("classifier_desc", f"- {mk}: {MODES[mk].get('label', mk)}")

    lines: list[str] = []
    lines.append("你是一个文本分类器。分析用户文本，只返回 {\"mode\": \"<key>\"}。\n")
    lines.append("可用模式：")
    for mk in MODES:
        if mk in enabled:
            lines.append(_get_desc(mk))

    lines.append("")
    lines.append("判断规则（按顺序，命中即停）：")

    idx = 1  # 顶级规则编号

    # 1. 单词 → dict
    if "dict" in enabled:
        lines.append(f"{idx}. 单个英文单词（如 hello、algorithm、serendipity）→ dict")
        idx += 1

    # 2. 非中文 → translate
    if "translate" in enabled:
        lines.append(f"{idx}. 非中文文本（英文句子/段落/日文/韩文）→ translate")
        idx += 1

    # 3. 中文文本子规则（只包含已启用模式）
    cn_mode_order = ["ask", "summarize"]
    cn_enabled = [m for m in cn_mode_order if m in enabled]
    if cn_enabled:
        lines.append(f"{idx}. 中文文本 → 按以下子规则：")
        idx += 1
        sub_letter = ord('a')
        for m in cn_enabled:
            desc = _get_desc(m)
            desc = desc.split(": ", 1)[1] if ": " in desc else desc
            lines.append(f"   {chr(sub_letter)}. {desc} → {m}")
            sub_letter += 1
        # 兜底：以上都不符合 → 第一个启用的中文模式
        fallback_cn = cn_enabled[0]
        lines.append(f"   {chr(sub_letter)}. 以上都不符合 → {fallback_cn}")

    # 4. 代码片段 → code
    if "code" in enabled:
        lines.append(f"{idx}. 代码片段（任何编程语言）→ code")
        idx += 1

    # 5. 自定义模式：让 LLM 根据描述自行判断
    _BUILTIN_KEYS = {"translate", "ask", "code", "summarize", "dict"}
    custom_enabled = [mk for mk in enabled if mk not in _BUILTIN_KEYS]
    if custom_enabled:
        lines.append(f"{idx}. 如果以上规则都不匹配，根据「可用模式」中的描述选择最合适的模式。")
        idx += 1

    # 翻译警告（仅当 translate 启用时才有意义）
    if "translate" in enabled:
        lines.append("")
        lines.append("⚠️ 中文文本永远不要选 translate。translate 只用于外语翻译成中文。")

    lines.append("只返回 JSON，不要任何其他文字。")
    return "\n".join(lines)

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

# ── 从 .env 加载分类器描述覆盖 ──────────────────────
_CLASSIFIER_DESCS_RAW = os.getenv("MODE_CLASSIFIER_DESCS", "")
if _CLASSIFIER_DESCS_RAW:
    try:
        descs = _json.loads(_CLASSIFIER_DESCS_RAW)
        for mk, desc in descs.items():
            if mk in MODES:
                MODES[mk]["classifier_desc"] = desc
    except (_json.JSONDecodeError, TypeError):
        pass

# ── 从 .env 加载自定义模式 ──────────────────────────
_CUSTOM_MODES_RAW = os.getenv("CUSTOM_MODES", "")
if _CUSTOM_MODES_RAW:
    try:
        custom_list = _json.loads(_CUSTOM_MODES_RAW)
        for cm in custom_list:
            key = cm.get("key", "")
            if key and key not in MODES:
                MODES[key] = {
                    "label": cm.get("label", key),
                    "system_prompt": cm.get("system_prompt", ""),
                    "classifier_desc": cm.get("classifier_desc", ""),
                    "custom": True,
                }
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
    "code": "代码",
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
