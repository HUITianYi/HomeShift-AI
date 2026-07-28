"""LLM 抽象层。

Agent 核心循环只依赖这个接口，因此：
- 有 ANTHROPIC_API_KEY -> AnthropicClient（真实 Claude，自由推理）
- 无密钥/离线演示     -> MockLLMClient（脚本化决策，但走完全相同的
  工具调用循环，数字同样来自真实工具计算）

消息与内容块沿用 Anthropic Messages API 的字典格式
（{"type": "text"|"tool_use"|"tool_result", ...}），两种客户端零转换互通。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    stop_reason: str            # "end_turn" | "tool_use" | "refusal" | ...
    content: list[dict] = field(default_factory=list)  # Anthropic 格式的内容块


class LLMClient(ABC):
    provider_name: str = "base"

    @abstractmethod
    def create(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        """发起一轮对话。messages 为 Anthropic 格式的完整历史。"""
        raise NotImplementedError
