"""FastAPI 请求契约。

响应的大型工作空间由 ``export.web_payload`` 统一组装；这里重点约束会改变
状态的输入，避免 Web 层把无效选择传入领域层。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


Locale = Literal["zh", "en"]


class ModelSelection(BaseModel):
    mode: Literal["live", "mock"] = "live"
    provider: str
    model: str | None = None

    @field_validator("provider")
    @classmethod
    def provider_is_explicit(cls, value: str) -> str:
        value = value.strip()
        if not value or value == "auto":
            raise ValueError("Web 模式必须显式选择提供方，不能使用 auto")
        return value


class ProfileUpdate(BaseModel):
    profile: dict[str, Any]


class LocaleRequest(BaseModel):
    locale: Locale = "zh"


class PlanCommitRequest(BaseModel):
    action_ids: list[str] = Field(min_length=1)
    rationale: str = Field(default="", max_length=2000)
    confirmed_by_user: Literal[True]

    @field_validator("action_ids")
    @classmethod
    def unique_actions(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip() for item in values if item.strip()))
        if not cleaned:
            raise ValueError("至少选择一个有效动作")
        return cleaned


class SimulateWeekRequest(BaseModel):
    adherence: float = Field(default=0.85, ge=0, le=1)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    locale: Locale = "zh"
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
