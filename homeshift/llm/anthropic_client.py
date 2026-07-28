"""Anthropic Claude 客户端（原生 Messages API）。

两种工作方式，自动选择：
1. 装了 `anthropic` SDK  -> 用官方 SDK（自带重试、超时、类型）
2. 没装 SDK              -> 用标准库 urllib 直接调 HTTP 接口（保持零依赖可用）

两者对上层完全等价，返回同样的 LLMResponse。

相比原版修复的问题：
- 原版 `anthropic.Anthropic()` 不传任何参数，无法使用自定义 base_url（中转/代理）
  也无法从 settings 拿密钥，只能依赖进程环境变量；
- 原版没有任何异常处理，密钥错误时抛 SDK 原始异常，用户看不懂；
- 原版未安装 SDK 时直接不可用，与"零依赖"的宣传不符。
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request

from .base import LLMClient, LLMResponse

ANTHROPIC_VERSION = "2023-06-01"
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class LLMCallError(RuntimeError):
    pass


class AnthropicClient(LLMClient):
    provider_name = "anthropic"

    def __init__(self, settings: dict):
        self.settings = settings
        self.model = settings["model"]
        self.max_tokens = settings.get("max_tokens", 8000)
        self.api_key = settings.get("api_key")
        self.base_url = (settings.get("base_url") or "https://api.anthropic.com").rstrip("/")
        self.timeout = settings.get("timeout", 180)
        self.max_retries = settings.get("max_retries", 3)
        self.extra_body = settings.get("extra_body") or {}
        self.last_usage: dict | None = None

        try:
            import anthropic  # 可选依赖

            self._sdk = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                max_retries=self.max_retries,
                timeout=self.timeout,
            )
        except ImportError:
            self._sdk = None  # 走内置 HTTP 实现

    # ------------------------------------------------------------------
    def create(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        body: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
        body.update(self.extra_body)

        if self._sdk is not None:
            return self._create_via_sdk(body)
        return self._create_via_http(body)

    # ------------------------------------------------------------------
    def _create_via_sdk(self, body: dict) -> LLMResponse:
        try:
            response = self._sdk.messages.create(**body)
        except Exception as exc:  # SDK 异常层级较多，统一转成可读错误
            raise LLMCallError(f"[anthropic] 调用失败：{exc}") from exc
        usage = getattr(response, "usage", None)
        self.last_usage = usage.model_dump() if usage is not None else None
        content = [block.model_dump() for block in response.content]
        return LLMResponse(stop_reason=response.stop_reason, content=content)

    # ------------------------------------------------------------------
    def _create_via_http(self, body: dict) -> LLMResponse:
        if not self.api_key:
            raise LLMCallError("缺少 ANTHROPIC_API_KEY。")
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                f"{self.base_url}/v1/messages", data=data, headers=headers, method="POST"
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                self.last_usage = payload.get("usage")
                return LLMResponse(
                    stop_reason=payload.get("stop_reason", "end_turn"),
                    content=payload.get("content", []),
                )
            except urllib.error.HTTPError as exc:
                detail = _read_body(exc)
                if exc.code in RETRYABLE_STATUS and attempt < self.max_retries:
                    time.sleep(min(2 ** attempt + random.random(), 20))
                    continue
                raise LLMCallError(f"[anthropic] HTTP {exc.code}：{detail}") from exc
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt + random.random(), 20))
                    continue
                raise LLMCallError(f"[anthropic] 无法连接 {self.base_url}：{exc.reason}") from exc
        raise LLMCallError("[anthropic] 重试后仍失败")


def _read_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")[:800]
    except Exception:
        return ""
