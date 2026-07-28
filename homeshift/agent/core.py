"""Agent 核心：标准的 tool-use 循环（agentic loop）。

流程（与 Anthropic Messages API 的原生 tool-use 协议一致）：

  用户请求 -> LLM 推理
     -> stop_reason == "tool_use"？
          是：本地执行工具 -> 结果作为 tool_result 追加到对话 -> 回到 LLM
          否：输出最终回答，回合结束

护栏：
- max_tool_rounds 限制单回合最大工具轮数（防失控）；
- 工具执行异常会以 is_error 返回给 LLM，让其自行调整而不是崩溃；
- stop_reason == "refusal"（安全分类器拒绝）时给出友好提示。

同一套循环同时驱动 AnthropicClient（自由推理）与 MockLLMClient
（剧本决策），这正是抽象 LLM 接口的意义。
"""

from __future__ import annotations

import json
import time

from ..context import AppContext
from ..llm.base import LLMClient, LLMResponse
from .prompts import SYSTEM_PROMPT
from .roles import role_name, role_of_tool
from .tools import TOOL_DEFINITIONS, dispatch_tool, serialize_result


def _shorten(text: str, limit: int = 120) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


class Agent:
    def __init__(
        self,
        ctx: AppContext,
        llm: LLMClient,
        verbose: bool = True,
        system_prompt: str | None = None,
    ):
        self.ctx = ctx
        self.llm = llm
        self.verbose = verbose
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.max_rounds = ctx.config["llm"].get("max_tool_rounds", 16)
        # 协作轨迹：记录"哪个角色、用哪个工具、耗时多久、产出什么"
        # 这是把"7 个专家 agent"的说法落到实处的地方，也是导出给网站的 trace。
        self.trace: list[dict] = []

    # ------------------------------------------------------------------
    def run_task(self, user_prompt: str, history: list[dict] | None = None) -> str:
        """执行一个任务回合，返回最终文本回答。

        history 传入则续接多轮对话（chat 模式），并被原地更新。
        """
        messages = history if history is not None else []
        messages.append({"role": "user", "content": user_prompt})

        final_text_parts: list[str] = []
        for _round in range(self.max_rounds):
            response = self.llm.create(self.system_prompt, messages, TOOL_DEFINITIONS)

            if response.stop_reason == "refusal":
                text = "（请求被安全策略拒绝，请换一种问法。）"
                messages.append({"role": "assistant", "content": text})
                return text

            # 展示模型的文字输出（中间narration + 最终回答）
            for block in response.content:
                if block.get("type") == "text" and block.get("text"):
                    final_text_parts.append(block["text"])
                    if self.verbose:
                        print(block["text"])
                        print()

            # 助手消息原样入历史（含 thinking / tool_use 块，符合 API 回传要求）
            messages.append({"role": "assistant", "content": response.content})

            tool_calls = [b for b in response.content if b.get("type") == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_calls:
                break  # 回合结束

            # 执行全部工具调用，结果打包为一条 user 消息回传
            tool_results: list[dict] = []
            for call in tool_calls:
                name, tool_input = call["name"], call.get("input") or {}
                role_id = role_of_tool(name)
                if self.verbose:
                    args = json.dumps(tool_input, ensure_ascii=False)
                    print(f"  [{role_name(role_id)}] {name}({args})")
                started = time.perf_counter()
                try:
                    result = dispatch_tool(self.ctx, name, tool_input)
                    payload = serialize_result(result)
                    is_error = False
                except Exception as exc:  # 工具异常交还给模型处理
                    payload = json.dumps(
                        {"error": "tool_exception", "message": str(exc)},
                        ensure_ascii=False,
                    )
                    is_error = True
                elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
                if self.verbose:
                    status = "错误" if is_error else "完成"
                    print(f"         -> {status}，返回 {_shorten(payload, 80)}")
                self.trace.append({
                    "step": len(self.trace) + 1,
                    "round": _round + 1,
                    "role": role_id,
                    "role_name": role_name(role_id),
                    "tool": name,
                    "input": tool_input,
                    "ok": not is_error,
                    "elapsed_ms": elapsed_ms,
                    "output_preview": _shorten(payload, 220),
                })
                entry = {
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": [{"type": "text", "text": payload}],
                }
                if is_error:
                    entry["is_error"] = True
                tool_results.append(entry)
            if self.verbose:
                print()
            messages.append({"role": "user", "content": tool_results})
        else:
            note = f"（已达到单回合最大工具轮数 {self.max_rounds}，输出当前结果。）"
            final_text_parts.append(note)
            if self.verbose:
                print(note)

        # 只把“最后一段”当作最终回答（前面的是过程narration）
        return final_text_parts[-1] if final_text_parts else "（模型没有返回文本。）"


def build_llm(ctx: AppContext):
    """根据配置/环境自动装配 LLM 客户端。

    provider 决定走哪套协议：
      mock          -> MockLLMClient（离线剧本）
      anthropic     -> AnthropicClient（Claude 原生 Messages API）
      openai_compat -> OpenAICompatClient（DeepSeek / OpenAI / 通义 / Ollama ...）
    """
    from ..llm.registry import resolve_llm_settings, validate_settings

    settings = resolve_llm_settings(ctx.config)
    kind = settings["kind"]

    if kind == "mock":
        from ..llm.mock_client import MockLLMClient

        return MockLLMClient()

    validate_settings(settings)

    if kind == "anthropic":
        from ..llm.anthropic_client import AnthropicClient

        return AnthropicClient(settings)

    from ..llm.openai_compat import OpenAICompatClient

    return OpenAICompatClient(settings)
