"""
LLM 引擎模块
-----------
引擎抽象 + DeepSeek 实现。
所有模式（翻译/提问/代码/总结）共用同一调用逻辑，差异只在 system prompt。
支持 SSE 流式调用。

v2：用标准库 urllib 替代 httpx，避免 httpcore + OpenSSL 1.1.1n 的 TLS 兼容问题。
"""

import json
import ssl
import socket
import urllib.request
from config import Config, MODES, build_classifier_prompt, DEFAULT_MODE, MODE_ENABLED

# 创建 SSL context（PyInstaller 打包后 certifi 路径变化，显式加载）
try:
    import certifi as _certifi
    _SSL_CONTEXT = ssl.create_default_context(
        cafile=_certifi.where(),
        purpose=ssl.Purpose.SERVER_AUTH,
    )
except Exception:
    _SSL_CONTEXT = ssl.create_default_context()


def _http_request(method: str, url: str, headers: dict, body: bytes = None,
                  timeout: float = 60.0) -> urllib.request.http.client.HTTPResponse:
    """发送 HTTP 请求，返回 response 对象（需调用方管理生命周期）。"""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT)


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

        # 注入用户当前关注方向（如有）
        if Config.USER_DIRECTION.strip():
            system_prompt = (
                f"{system_prompt}\n\n"
                f"[用户当前关注方向]\n{Config.USER_DIRECTION.strip()}\n\n"
                f"请在回答时优先考虑上述方向，用更贴合用户当前需求的方式组织回答。"
            )

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

        # 注入用户当前关注方向（如有）
        if Config.USER_DIRECTION.strip():
            system_prompt = (
                f"{system_prompt}\n\n"
                f"[用户当前关注方向]\n{Config.USER_DIRECTION.strip()}\n\n"
                f"请在回答时优先考虑上述方向，用更贴合用户当前需求的方式组织回答。"
            )

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
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            resp = _http_request("POST", url, headers, body, timeout=60.0)

            # 检查 HTTP 状态码
            status = resp.status
            if status == 401:
                yield "🔑 API Key 无效，请检查 .env 中的 DEEPSEEK_API_KEY。"
                return
            elif status == 429:
                yield "🔄 请求过于频繁，请稍后重试。"
                return
            elif status == 402:
                yield "💰 API 余额不足，请充值。"
                return
            elif status >= 400:
                yield f"⚠️ API 错误（HTTP {status}）"
                return

            # 逐行读取 SSE 流
            for line_bytes in resp:
                line = line_bytes.decode("utf-8", errors="replace").strip()
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

            if in_reasoning:
                yield '\n</details>\n'

        except urllib.error.URLError as e:
            if in_reasoning:
                yield '\n</details>\n'
            reason = str(e.reason) if e.reason else str(e)
            yield f"🌐 网络连接失败：{reason}"
            yield self._diagnose_ssl()
        except socket.timeout:
            if in_reasoning:
                yield '\n</details>\n'
            yield "⏱️ 请求超时，请重试。"
        except Exception as e:
            if in_reasoning:
                yield '\n</details>\n'
            yield f"❌ 未知错误：{e}"

    def classify(self, text: str) -> str:
        """轻量级文本分类，返回模式 key。"""
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
            "max_tokens": 200,
            "temperature": 0,
            "stream": False,
        }

        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            resp = _http_request("POST", url, headers, body, timeout=5.0)
            data = json.loads(resp.read().decode("utf-8"))
            msg = data.get("choices", [{}])[0].get("message", {})
            content = msg.get("content", "").strip()
            if not content:
                reasoning = msg.get("reasoning_content", "").strip()
                if reasoning:
                    import re as _re
                    m = _re.search(r'\{[^}]+\}', reasoning)
                    if m:
                        content = m.group()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("\n```", 1)[0].strip()
            result = json.loads(content)
            mode = result.get("mode", DEFAULT_MODE)
            if mode in MODES:
                return mode
        except Exception:
            pass

        return DEFAULT_MODE

    def _diagnose_ssl(self) -> str:
        """诊断 SSL/TLS 连接问题，返回调试信息。"""
        lines = ["\n\n--- 🔍 SSL 诊断 ---"]
        try:
            import certifi
            lines.append(f"certifi 路径：{certifi.__file__}")
            lines.append(f"CA bundle：{certifi.where()}")
            import os as _os
            lines.append(f"CA 文件存在：{_os.path.exists(certifi.where())}")
        except Exception as ex:
            lines.append(f"certifi 加载失败：{ex}")

        try:
            lines.append(f"OpenSSL 版本：{ssl.OPENSSL_VERSION}")
        except Exception as ex:
            lines.append(f"ssl 模块状态：{ex}")

        try:
            # socket 级 TLS 直连（绕过所有 HTTP 库）
            sock = socket.create_connection(("api.deepseek.com", 443), timeout=10)
            ssock = _SSL_CONTEXT.wrap_socket(sock, server_hostname="api.deepseek.com")
            lines.append(f"socket TLS 直连：ok, cipher={ssock.cipher()[0]}, tls={ssock.version()}")
            ssock.send(b"GET / HTTP/1.1\r\nHost: api.deepseek.com\r\n\r\n")
            data = ssock.recv(1024)
            lines.append(f"HTTP 响应：{data.decode().split(chr(13)+chr(10))[0]}")
            ssock.close()
        except Exception as ex:
            lines.append(f"socket TLS 直连失败：{ex}")

        try:
            addrs = socket.getaddrinfo("api.deepseek.com", 443)
            lines.append(f"DNS 解析：ok ({addrs[0][4][0] if addrs else '?'})")
        except Exception as ex:
            lines.append(f"DNS 解析失败：{ex}")

        try:
            lines.append(f"HTTP_PROXY={(__import__('os').getenv('HTTP_PROXY') or '无')}")
            lines.append(f"HTTPS_PROXY={(__import__('os').getenv('HTTPS_PROXY') or '无')}")
        except Exception:
            pass

        try:
            # urllib GET 测试
            req = urllib.request.Request("https://api.deepseek.com/v1/models")
            resp = urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT)
            lines.append(f"urllib GET：HTTP {resp.status}")
        except Exception as ex:
            lines.append(f"urllib GET：{ex}")

        return "\n".join(lines)

    def test_connection(self, api_key: str = None, base_url: str = None,
                        model: str = None) -> bool:
        """测试 API 连接。成功返回 True，失败抛异常。"""
        key = api_key or self.api_key
        url = (base_url or self.base_url).rstrip("/")
        mdl = model or self.model

        if not key:
            raise ValueError("API Key 未配置")

        body = json.dumps({
            "model": mdl,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1,
        }, ensure_ascii=False).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        resp = _http_request("POST", f"{url}/chat/completions", headers, body,
                             timeout=15.0)
        resp.read()  # consume response
        return True


# 全局单例
engine = DeepSeekEngine()
