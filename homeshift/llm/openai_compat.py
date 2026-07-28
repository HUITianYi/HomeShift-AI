"""OpenAI 兼容协议客户端（DeepSeek / OpenAI / 通义 / Kimi / GLM / Ollama ...）。

为什么要有这一层：
项目的 Agent 循环（agent/core.py）按 Anthropic Messages API 的内容块格式工作
（text / tool_use / tool_result）。而绝大多数国内外模型服务走的是 OpenAI 的
/chat/completions 格式（message.tool_calls + role="tool"）。本模块做双向翻译，
使得 **换模型不需要改 Agent 一行代码**。

翻译对照表
---------------------------------------------------------------------------
工具定义   Anthropic {name, description, input_schema}
       -> OpenAI    {type:"function", function:{name, description, parameters}}

助手回合   Anthropic content=[{type:"tool_use", id, name, input}]
       -> OpenAI    {role:"assistant", tool_calls:[{id, function:{name, arguments:JSON字符串}}]}

工具结果   Anthropic {role:"user", content=[{type:"tool_result", tool_use_id, content}]}
       -> OpenAI    多条 {role:"tool", tool_call_id, content}

停止原因   OpenAI finish_reason "tool_calls" -> Anthropic stop_reason "tool_use"
                                "stop"       -> "end_turn"
                                "length"     -> "max_tokens"
                        content_filter       -> "refusal"
---------------------------------------------------------------------------

实现说明：只用标准库 urllib，不依赖 openai SDK —— 保持项目"零必装依赖"的特点，
同时自己实现了指数退避重试与友好的错误信息。
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request

from .base import LLMClient, LLMResponse

# 这些 HTTP 状态码值得重试（限流 / 服务端临时故障）
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class LLMCallError(RuntimeError):
    """调用模型失败，且已附带可读的排错提示。"""


# ---------------------------------------------------------------------------
# 格式转换：Anthropic -> OpenAI
# ---------------------------------------------------------------------------

def tools_to_openai(tools: list[dict]) -> list[dict]:
    """Anthropic 工具定义 -> OpenAI function 定义。"""
    converted = []
    for tool in tools:
        schema = tool.get("input_schema") or {"type": "object", "properties": {}}
        converted.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": schema,
            },
        })
    return converted


def _blocks_to_text(content) -> str:
    """把内容块列表里的文本拼起来（忽略 thinking，不回传给不认识它的模型）。"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            parts.append(block["text"])
    return "\n".join(parts)


def messages_to_openai(system: str, messages: list[dict]) -> list[dict]:
    """Anthropic 消息历史 -> OpenAI 消息历史。

    注意顺序约束：OpenAI 要求每条 role="tool" 消息紧跟在包含对应
    tool_call_id 的 assistant 消息之后，本函数保持了原有的时间顺序，
    因此天然满足该约束。
    """
    out: list[dict] = [{"role": "system", "content": system}]

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        # --- 用户消息：可能是纯文本，也可能是一批 tool_result ---
        if role == "user":
            if isinstance(content, str):
                out.append({"role": "user", "content": content})
                continue
            if not isinstance(content, list):
                continue
            tool_results = [b for b in content if isinstance(b, dict)
                            and b.get("type") == "tool_result"]
            if tool_results:
                for block in tool_results:
                    raw = block.get("content")
                    if isinstance(raw, list):
                        text = "".join(b.get("text", "") for b in raw
                                       if isinstance(b, dict) and b.get("type") == "text")
                    else:
                        text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                    out.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": text or "{}",
                    })
            else:
                text = _blocks_to_text(content)
                if text:
                    out.append({"role": "user", "content": text})
            continue

        # --- 助手消息：可能带 tool_use ---
        if role == "assistant":
            if isinstance(content, str):
                out.append({"role": "assistant", "content": content})
                continue
            if not isinstance(content, list):
                continue
            text = _blocks_to_text(content)
            tool_uses = [b for b in content if isinstance(b, dict)
                         and b.get("type") == "tool_use"]
            entry: dict = {"role": "assistant", "content": text or None}
            if tool_uses:
                entry["tool_calls"] = [{
                    "id": call.get("id", f"call_{i}"),
                    "type": "function",
                    "function": {
                        "name": call.get("name", ""),
                        "arguments": json.dumps(call.get("input") or {}, ensure_ascii=False),
                    },
                } for i, call in enumerate(tool_uses)]
            # OpenAI 允许 content 为 null，但必须至少有 content 或 tool_calls
            if entry.get("content") is None and "tool_calls" not in entry:
                continue
            out.append(entry)

    return out


# ---------------------------------------------------------------------------
# 格式转换：OpenAI -> Anthropic
# ---------------------------------------------------------------------------

FINISH_REASON_MAP = {
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "stop": "end_turn",
    "length": "max_tokens",
    "content_filter": "refusal",
}


def response_to_anthropic(payload: dict) -> LLMResponse:
    """OpenAI /chat/completions 响应 -> 项目内部的 LLMResponse。"""
    choices = payload.get("choices") or []
    if not choices:
        raise LLMCallError(
            "模型返回了空的 choices。原始响应：" + json.dumps(payload, ensure_ascii=False)[:500]
        )
    choice = choices[0]
    message = choice.get("message") or {}
    finish = choice.get("finish_reason") or "stop"

    content: list[dict] = []

    # 有些模型（如 DeepSeek 思考模式）会返回 reasoning_content，
    # 它不参与后续回传，仅在需要时供调试查看，这里不放进 content。
    text = message.get("content")
    if text:
        content.append({"type": "text", "text": text})

    tool_calls = message.get("tool_calls") or []
    for i, call in enumerate(tool_calls):
        fn = call.get("function") or {}
        raw_args = fn.get("arguments") or "{}"
        # 小模型偶尔会把 arguments 写成非法 JSON，这里兜底而不是崩溃
        try:
            parsed = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            if not isinstance(parsed, dict):
                parsed = {"value": parsed}
        except json.JSONDecodeError:
            parsed = {"_malformed_arguments": str(raw_args)[:400]}
        content.append({
            "type": "tool_use",
            "id": call.get("id") or f"call_{i}",
            "name": fn.get("name", ""),
            "input": parsed,
        })

    stop_reason = FINISH_REASON_MAP.get(finish, "end_turn")
    # 少数服务在有 tool_calls 时仍返回 finish_reason="stop"，这里纠正
    if tool_calls and stop_reason != "tool_use":
        stop_reason = "tool_use"

    return LLMResponse(stop_reason=stop_reason, content=content)


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------

class OpenAICompatClient(LLMClient):
    """任何暴露 POST {base_url}/chat/completions 的服务都能用这个客户端。"""

    provider_name = "openai_compat"

    def __init__(self, settings: dict):
        self.settings = settings
        self.provider_name = settings.get("provider", "openai_compat")
        self.model = settings["model"]
        self.base_url = (settings["base_url"] or "").rstrip("/")
        self.api_key = settings.get("api_key")
        self.max_tokens = settings.get("max_tokens", 8000)
        self.temperature = settings.get("temperature")
        self.timeout = settings.get("timeout", 180)
        self.max_retries = settings.get("max_retries", 3)
        self.extra_body = settings.get("extra_body") or {}
        self.last_usage: dict | None = None

    # -- 内部：拼 URL --------------------------------------------------------
    def _endpoint(self) -> str:
        # 允许用户填 ".../v1" 或不带 "/v1"；两种都能正确拼出 /chat/completions
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    # -- 内部：单次 HTTP -----------------------------------------------------
    def _post(self, body: dict) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self._endpoint(), data=data, headers=headers, method="POST"
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # -- 对外：一轮对话 ------------------------------------------------------
    def create(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        body: dict = {
            "model": self.model,
            "messages": messages_to_openai(system, messages),
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if tools:
            body["tools"] = tools_to_openai(tools)
            body["tool_choice"] = "auto"
        if self.temperature is not None:
            body["temperature"] = self.temperature
        body.update(self.extra_body)

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                payload = self._post(body)
                self.last_usage = payload.get("usage")
                # 有的网关把错误塞在 200 响应体里
                if "error" in payload and "choices" not in payload:
                    raise LLMCallError(_format_api_error(payload, self.provider_name))
                return response_to_anthropic(payload)

            except urllib.error.HTTPError as exc:
                detail = _read_error_body(exc)
                if exc.code in RETRYABLE_STATUS and attempt < self.max_retries:
                    _sleep_backoff(attempt)
                    last_error = exc
                    continue
                raise LLMCallError(
                    _http_error_hint(exc.code, detail, self.provider_name, self.model)
                ) from exc

            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    _sleep_backoff(attempt)
                    last_error = exc
                    continue
                raise LLMCallError(
                    f"无法连接 {self._endpoint()}：{exc.reason}\n"
                    "排查：1) 网络/代理是否正常；2) base_url 是否写对；"
                    "3) 若用 Ollama，确认 `ollama serve` 已启动。"
                ) from exc

            except json.JSONDecodeError as exc:
                raise LLMCallError(
                    f"{self.provider_name} 返回的不是合法 JSON，通常说明 base_url 指向了网页而非 API。"
                ) from exc

        raise LLMCallError(f"重试 {self.max_retries} 次后仍失败：{last_error}")


# ---------------------------------------------------------------------------
# 错误信息辅助（让报错能直接告诉用户怎么修）
# ---------------------------------------------------------------------------

def _sleep_backoff(attempt: int) -> None:
    time.sleep(min(2 ** attempt + random.random(), 20))


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")[:800]
    except Exception:
        return ""


def _format_api_error(payload: dict, provider: str) -> str:
    err = payload.get("error")
    if isinstance(err, dict):
        return f"[{provider}] {err.get('type', 'error')}: {err.get('message', '')}"
    return f"[{provider}] {err}"


def _http_error_hint(code: int, detail: str, provider: str, model: str) -> str:
    hints = {
        401: "API 密钥无效或未生效。检查环境变量是否设置成功（注意重开终端）。",
        402: "账户余额不足，请先充值。",
        403: "无权访问该模型，可能需要实名或开通权限。",
        404: (f"接口或模型不存在。常见原因：模型名 '{model}' 写错或已下线；"
              "base_url 多写/少写了 /v1。"),
        422: "请求参数不被该服务接受，可能是它不支持 tools（function calling）。",
        429: "触发限流，稍后重试或降低并发。",
    }
    tail = hints.get(code, "")
    return (f"[{provider}] HTTP {code}。{tail}\n服务端返回：{detail}").strip()
