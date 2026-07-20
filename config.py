"""
配置管理模块
-----------
从 .env 加载 API 配置，定义四种模式的 system prompt 和过滤规则。
"""

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
    WINDOW_WIDTH = int(os.getenv("WINDOW_WIDTH", "500"))
    WINDOW_HEIGHT = int(os.getenv("WINDOW_HEIGHT", "380"))


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
}

# 默认模式
DEFAULT_MODE = "translate"

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
    (re.compile(r"^.{0,1}$"), "too short"),
    # 纯数字 + 常见符号
    (re.compile(r"^[\d\s.,+\-*/=%%$€£¥()[\]{}<>|&^~#@!;:'""`]+$"), "numbers/symbols only"),
    # Windows 路径（C:\...  D:/...  \\server\...）
    (re.compile(r"^[A-Za-z]:[\\/]"), "Windows path"),
    # UNC 路径
    (re.compile(r"^\\\\"), "UNC path"),
    # Unix 绝对路径
    (re.compile(r"^/"), "Unix path"),
    # 纯 URL
    (re.compile(r"^https?://\S+$"), "URL"),
    # 单文件名（含扩展名）
    (re.compile(r"^[\w\-. ]+\.[a-zA-Z]{2,6}$"), "filename"),
    # 纯数字
    (re.compile(r"^\d+$"), "pure digits"),
]
