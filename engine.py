"""
LLM 引擎模块
-----------
引擎抽象 + DeepSeek 实现。
所有模式（翻译/提问/润色/总结）共用同一调用逻辑，差异只在 system prompt。
"""

import requests
from config import Config, MODES


class DeepSeekEngine:
    """DeepSeek API 引擎（OpenAI 兼容接口）"""

    def __init__(self):
        self.api_key = Config.DEEPSEEK_API_KEY
        self.base_url = Config.DEEPSEEK_BASE_URL.rstrip("/")
        self.model = Config.DEEPSEEK_MODEL

    def query(self, text: str, mode: str) -> str:
        """
        以指定模式查询 API。

        Args:
            text: 用户输入的文本
            mode: 模式 key，如 "translate" / "ask" / "polish" / "summarize"

        Returns:
            API 返回的文本结果
        """
        mode_config = MODES.get(mode, MODES["ask"])
        system_prompt = mode_config["system_prompt"]

        if not self.api_key:
            return (
                "❌ 未配置 API Key\n\n"
                "请复制 .env.example 为 .env，填入 DeepSeek API Key。\n"
                "获取：https://platform.deepseek.com/api_keys"
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
                {"role": "user", "content": text},
            ],
            "stream": False,
            "temperature": 0.3,
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout:
            return "⏱️ 请求超时，请重试。"
        except requests.exceptions.ConnectionError:
            return "🌐 网络连接失败，请检查网络或代理设置。"
        except requests.exceptions.HTTPError:
            status = resp.status_code
            if status == 401:
                return "🔑 API Key 无效，请检查 .env 中的 DEEPSEEK_API_KEY。"
            elif status == 429:
                return "🔄 请求过于频繁，请稍后重试。"
            elif status == 402:
                return "💰 API 余额不足，请充值。"
            return f"⚠️ API 错误（HTTP {status}）"
        except Exception as e:
            return f"❌ 未知错误：{e}"


# 全局单例
engine = DeepSeekEngine()
