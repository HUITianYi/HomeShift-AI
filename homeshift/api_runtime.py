"""Web API 的请求级运行时。

领域数字仍全部来自既有 Python 工具。本模块只负责：
- 禁止隐式 Mock 降级；
- 注入地区化提示词；
- 为“规划建议”提供不写盘的 Store；
- 把一次 Agent 运行和最新工作空间封装为稳定响应。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agent.core import Agent
from .agent.prompts import build_system_prompt
from .config import load_config
from .context import AppContext
from .export.web_payload import build_payload
from .llm.registry import resolve_llm_settings, validate_settings


class ApiProblem(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class ProposalStore:
    """读操作委托给真实 Store，所有写操作只保留在请求内存。"""

    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.proposal: dict | None = None
        self.pending_memories: list[dict] = []
        self.pending_reviews: list[dict] = []

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    def save_plan(self, plan: dict) -> dict:
        draft = {**plan, "version": None, "status": "proposed", "persisted": False}
        self.proposal = draft
        return draft

    def add_memory(self, note: str, kind: str = "feedback", when=None) -> dict:
        item = {"id": None, "kind": kind, "note": note, "persisted": False}
        self.pending_memories.append(item)
        return item

    def add_review(self, review: dict) -> dict:
        draft = {**review, "id": None, "persisted": False}
        self.pending_reviews.append(draft)
        return draft


def context_for(root: Path) -> AppContext:
    return AppContext(root=root, config=load_config(root))


def public_settings(ctx: AppContext) -> dict:
    settings = resolve_llm_settings(ctx.config)
    requested = ctx.config.get("llm", {}).get("provider", "auto")
    return {
        "provider": settings["provider"],
        "kind": settings["kind"],
        "label": settings["label"],
        "model": settings.get("model"),
        "configured": bool(settings.get("api_key")) or settings["kind"] == "mock",
        "explicit": requested != "auto",
        "reason": settings.get("reason"),
    }


def build_web_llm(ctx: AppContext):
    """构建 Web LLM；auto 解析为 Mock 时必须阻断，不得伪装成实时成功。"""
    from .agent.core import build_llm

    settings = resolve_llm_settings(ctx.config)
    requested = ctx.config.get("llm", {}).get("provider", "auto")
    if requested == "auto":
        raise ApiProblem(
            "configuration_missing",
            "Web 模式尚未显式选择模型。请在模型面板选择已配置提供方，或主动选择离线彩排。",
            409,
        )
    if settings["kind"] == "mock" and requested != "mock":
        raise ApiProblem(
            "configuration_missing",
            "实时模型未配置；系统不会自动降级为 Mock。",
            409,
        )
    try:
        validate_settings(settings)
        return build_llm(ctx), settings
    except Exception as exc:  # provider errors use several concrete exception types
        raise ApiProblem("configuration_missing", str(exc), 409) from exc


def save_trace(ctx: AppContext, operation: str, trace: list[dict]) -> None:
    """覆盖保存最近一次审计轨迹；响应始终使用当前请求的内存轨迹。"""
    ctx.data_dir.mkdir(parents=True, exist_ok=True)
    payload = {"operation": operation, "trace": trace}
    (ctx.data_dir / "last_trace.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_agent(
    ctx: AppContext,
    prompt: str,
    *,
    locale: str,
    operation: str,
    proposal_only: bool = False,
) -> dict:
    llm, settings = build_web_llm(ctx)
    proposal_store = None
    if proposal_only:
        proposal_store = ProposalStore(ctx.store)
        ctx.store = proposal_store
    try:
        agent = Agent(
            ctx,
            llm,
            verbose=False,
            system_prompt=build_system_prompt(ctx.config, locale),
        )
        final_text = agent.run_task(prompt)
    except ApiProblem:
        raise
    except Exception as exc:
        raise ApiProblem("agent_failed", f"Agent 调用失败：{exc}", 502) from exc

    trace = list(agent.trace)
    # 在 Web 语义中 save_plan 是建议提交工具，不是已经正式保存。
    if proposal_only:
        for entry in trace:
            if entry.get("tool") == "save_plan":
                entry["tool"] = "propose_plan"
    save_trace(ctx, operation, trace)
    result = {
        "mode": "mock" if settings["kind"] == "mock" else "live",
        "provider": settings["provider"],
        "model": settings.get("model") or "mock-playbook",
        "final_text": final_text,
        "trace": trace,
    }
    if proposal_only:
        result["proposal"] = proposal_store.proposal if proposal_store else None
    return result


def operation_response(ctx: AppContext, run: dict) -> dict:
    return {
        "run": run,
        "workspace": workspace_payload(ctx, trace=run.get("trace", [])),
    }


def workspace_payload(ctx: AppContext, trace: list[dict] | None = None) -> dict:
    """在既有 Web 导出适配层之上补充仅运行时需要的状态。"""
    payload = build_payload(ctx, trace=trace)
    tracking_path = ctx.data_dir / "tracking_meta.json"
    tracking_meta = {}
    if tracking_path.exists():
        tracking_meta = json.loads(tracking_path.read_text(encoding="utf-8"))
    payload["memory"] = {
        "items": ctx.store.get_memories(),
        "count": len(ctx.store.get_memories()),
    }
    payload["runtime"] = {
        "model": public_settings(ctx),
        "tracking": tracking_meta,
    }
    return payload


def reset_derived_state(ctx: AppContext) -> None:
    """合成数据导入也必须执行与真实导入一致的完整重置。"""
    for name in (
        "plans.json",
        "memory.json",
        "reviews.json",
        "last_trace.json",
        "tracking_meta.json",
        "report.html",
    ):
        path = ctx.data_dir / name
        if path.exists():
            path.unlink()
