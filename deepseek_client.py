"""
DeepSeek API 客户端
------------------
封装 DeepSeek Chat API（OpenAI 兼容接口），提供两个核心方法：
- translate(text): 翻译
- ask(text): 通用 AI 问答
"""

import requests
from config import Config


class DeepSeekClient:
    """DeepSeek API 客户端"""

    def __init__(self):
        self.api_key = Config.DEEPSEEK_API_KEY
        self.base_url = Config.DEEPSEEK_BASE_URL.rstrip("/")
        self.model = Config.DEEPSEEK_MODEL

    def _call_api(self, system_prompt: str, user_text: str) -> str:
        """
        调用 DeepSeek Chat Completion API（非流式）。

        Args:
            system_prompt: 系统角色提示词（定义 AI 行为）
            user_text: 用户输入的文本

        Returns:
            AI 返回的文本内容
        """
        # 检查 API Key 是否配置
        if not self.api_key:
            return (
                "❌ 未配置 API Key\n\n"
                "请复制 .env.example 为 .env，并填入你的 DeepSeek API Key。\n"
                "获取地址：https://platform.deepseek.com/api_keys"
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "stream": False,       # MVP 阶段不使用流式
            "temperature": 0.3,    # 翻译/问答场景低温度更稳定
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()  # 非 2xx 响应抛出异常
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout:
            return "⏱️ 请求超时，请检查网络连接后重试。"
        except requests.exceptions.ConnectionError:
            return "🌐 网络连接失败，请检查网络设置或代理。"
        except requests.exceptions.HTTPError:
            status = resp.status_code
            if status == 401:
                return (
                    "🔑 API Key 无效，请检查 .env 中的 DEEPSEEK_API_KEY。\n"
                    "获取新 Key：https://platform.deepseek.com/api_keys"
                )
            elif status == 429:
                return "🔄 API 调用频率过高，请稍后重试。"
            elif status == 402:
                return "💰 API 余额不足，请前往 platform.deepseek.com 充值。"
            return f"⚠️ API 错误（HTTP {status}）"
        except Exception as e:
            return f"❌ 未知错误：{e}"

    def translate(self, text: str) -> str:
        """翻译文本（中→英 / 英→中）"""
        return self._call_api(Config.TRANSLATE_SYSTEM_PROMPT, text)

    def ask(self, text: str) -> str:
        """通用 AI 问答（解释概念、回答问题、分析总结）"""
        return self._call_api(Config.ASK_SYSTEM_PROMPT, text)


# 全局单例 — 整个应用共享一个客户端实例
client = DeepSeekClient()
