"""
配置管理模块
-----------
从 .env 文件加载配置，提供统一的 Config 类。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
load_dotenv(Path(__file__).parent / ".env")


class Config:
    """应用全局配置"""

    # ── DeepSeek API ────────────────────────────────────
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
    )
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # ── 快捷键 ──────────────────────────────────────────
    TRANSLATE_HOTKEY = os.getenv("TRANSLATE_HOTKEY", "ctrl+alt+t")
    ASK_HOTKEY = os.getenv("ASK_HOTKEY", "ctrl+alt+q")

    # ── System Prompts ──────────────────────────────────

    TRANSLATE_SYSTEM_PROMPT = (
        "你是一个专业的翻译助手。请将用户输入的文本翻译成中文。"
        "如果输入已经是中文，则翻译成英文。"
        "保持原文的格式、语气和风格。"
        "只返回翻译结果，不要添加任何解释、注释或额外内容。"
    )

    ASK_SYSTEM_PROMPT = (
        "你是一个知识渊博的 AI 助手。请根据用户选中的文本，提供清晰、准确的回答。\n"
        "- 如果文本是一个问题，直接回答。\n"
        "- 如果文本是一个概念或术语，给出简明解释。\n"
        "- 如果文本是一段内容，给出分析或总结。\n"
        "请用中文回答，除非输入是纯英文且明显需要英文回答。"
    )
