"""
LLM 引擎模块
-----------
引擎抽象 + DeepSeek 实现。
所有模式（翻译/提问/润色/总结）共用同一调用逻辑，差异只在 system prompt。
支持非流式（query）和 SSE 流式（query_stream）两种调用。
"""

import json
import httpx
from config import Config, MODES, build_classifier_prompt, DEFAULT_MODE, MODE_ENABLED


class DeepSeekEngine:
    """DeepSeek API 引擎（OpenAI 兼容接口）"""

    def __init__(self):
        self.api_key = Config.DEEPSEEK_API_KEY
        self.base_url = Config.DEEPSEEK_BASE_URL.rstrip("/")
        self.model = Config.DEEPSEEK_MODEL

    def query(self, text: str, mode: str) -> str:
        """非流式查询（保持兼容）"""
        parts = list(self.query_stream(text, mode))
        return "".join(parts) if parts else "⚠️ 空响应"

    def follow_up(self, original_text: str, previous_result: str,
                  selected_text: str, mode: str) -> str:
        """非流式追问（保持兼容）"""
        parts = list(self.follow_up_stream(
            original_text, previous_result, selected_text, mode))
        return "".join(parts) if parts else "⚠️ 空响应"

    # ── 流式（SSE） ──────────────────────────────────────

    def query_stream(self, text: str, mode: str):
        """流式查询，逐 chunk yield delta 文本"""
        mode_config = MODES.get(mode, MODES["ask"])
        system_prompt = mode_config["system_prompt"]

        if not self.api_key:
            yield (
                "❌ 未配置 API Key\n\n"
                "请复制 .env.example 为 .env，填入 DeepSeek API Key。\n"
                "获取：https://platform.deepseek.com/api_keys"
            )
            return

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
            "stream": True,
            "temperature": 0.3,
        }

        yield from self._stream_request(url, headers, payload)

    def follow_up_stream(self, original_text: str, previous_result: str,
                         selected_text: str, mode: str):
        """流式追问"""
        mode_config = MODES.get(mode, MODES["ask"])
        mode_label = mode_config["label"]
        system_prompt = mode_config["system_prompt"]

        if not self.api_key:
            yield "❌ 未配置 API Key"
            return

        prompt = (
            f"用户之前选中了以下原文，你以「{mode_label}」模式给出了回答。\n\n"
            f"【原文】\n{original_text}\n\n"
            f"【你的上次回答】\n{previous_result}\n\n"
            f"【用户在回答中选中的内容】\n{selected_text}\n\n"
            f"请针对用户选中的这部分，在上次回答的上下文基础上，"
            f"提供更详细的解释或补充。保持「{mode_label}」角色定位。"
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
                {"role": "user", "content": prompt},
            ],
            "stream": True,
            "temperature": 0.3,
        }

        yield from self._stream_request(url, headers, payload)

    def _stream_request(self, url: str, headers: dict, payload: dict):
        """发送 SSE 流式请求，逐 chunk yield delta 文本。

        兼容推理模型（reasoning_content）和普通模型（content）。
        推理模型的思考链用 <details> 包裹，可在 UI 中折叠。
        """
        in_reasoning = False
        try:
            with httpx.stream("POST", url, json=payload, headers=headers,
                              timeout=60.0) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                        )
                        reasoning = delta.get("reasoning_content", "")
                        content = delta.get("content", "")
                        if reasoning:
                            if not in_reasoning:
                                yield ('\n<details>\n'
                                       '<summary>💭 思考过程</summary>\n\n')
                                in_reasoning = True
                            yield reasoning
                        if content:
                            if in_reasoning:
                                yield '\n</details>\n\n'
                                in_reasoning = False
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                # 流正常结束 — 关闭未闭合的 details
                if in_reasoning:
                    yield '\n</details>\n'
                    in_reasoning = False

        except httpx.TimeoutException:
            if in_reasoning:
                yield '\n</details>\n'
            yield "⏱️ 请求超时，请重试。"
        except httpx.ConnectError:
            if in_reasoning:
                yield '\n</details>\n'
            yield "🌐 网络连接失败，请检查网络或代理设置。"
        except httpx.HTTPStatusError as e:
            if in_reasoning:
                yield '\n</details>\n'
            status = e.response.status_code
            if status == 401:
                yield "🔑 API Key 无效，请检查 .env 中的 DEEPSEEK_API_KEY。"
            elif status == 429:
                yield "🔄 请求过于频繁，请稍后重试。"
            elif status == 402:
                yield "💰 API 余额不足，请充值。"
            else:
                yield f"⚠️ API 错误（HTTP {status}）"
        except Exception as e:
            if in_reasoning:
                yield '\n</details>\n'
            yield f"❌ 未知错误：{e}"

    def classify(self, text: str) -> str:
        """轻量级文本分类，返回模式 key。

        用极简 prompt + temperature=0 让 LLM 快速判断文本模式。
        兼容推理模型（reasoning_content）和普通模型（content）。
        失败时 fallback 到 DEFAULT_MODE。
        """
        if not self.api_key or len(text) < 2:
            return DEFAULT_MODE

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": build_classifier_prompt()},
                {"role": "user", "content": text},
            ],
            "max_tokens": 200,   # 推理模型需要 extra token 给 reasoning
            "temperature": 0,
            "stream": False,
        }

        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            msg = data.get("choices", [{}])[0].get("message", {})
            content = msg.get("content", "").strip()
            # 兼容推理模型：content 可能为空，输出在 reasoning_content 中
            if not content:
                reasoning = msg.get("reasoning_content", "").strip()
                if reasoning:
                    # 从推理内容末尾提取 JSON（推理模型可能在推理后输出）
                    # 尝试找 JSON 片段
                    import re as _re
                    m = _re.search(r'\{[^}]+\}', reasoning)
                    if m:
                        content = m.group()
            # 解析 JSON（兼容 markdown 代码块包裹）
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("\n```", 1)[0].strip()
            result = json.loads(content)
            mode = result.get("mode", DEFAULT_MODE)
            # 验证 mode 有效性
            if mode in MODES:
                return mode
        except Exception:
            pass

        return DEFAULT_MODE

    def test_connection(self, api_key: str = None, base_url: str = None,
                        model: str = None) -> bool:
        """测试 API 连接。成功返回 True，失败抛异常。"""
        key = api_key or self.api_key
        url = (base_url or self.base_url).rstrip("/")
        mdl = model or self.model

        if not key:
            raise ValueError("API Key 未配置")

        resp = httpx.post(
            f"{url}/chat/completions",
            json={
                "model": mdl,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 1,
            },
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        return True


# 全局单例
engine = DeepSeekEngine()
