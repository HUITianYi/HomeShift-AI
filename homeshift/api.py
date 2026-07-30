"""HomeShift AI 本地 Demo 的 FastAPI 入口。

启动：
    python -m uvicorn homeshift.api:app --reload --port 8000
"""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from .agent.prompts import (
    DIAGNOSE_PROMPT,
    REVIEW_PROMPT,
    WEB_PLAN_PROMPT_EN,
    WEB_PLAN_PROMPT_ZH,
)
from .agent.tools import dispatch_tool
from .api_models import (
    ChatRequest,
    LocaleRequest,
    ModelSelection,
    PlanCommitRequest,
    ProfileUpdate,
    SimulateWeekRequest,
)
from .api_runtime import (
    ApiProblem,
    context_for,
    mark_workflow_step,
    operation_response,
    public_settings,
    require_workflow_step,
    reset_derived_state,
    run_agent,
    workspace_payload,
)
from .config import DEFAULTS, PROJECT_ROOT, load_config, save_config_patch
from .datagen.generate import append_week_with_plan, init_dataset
from .datastore.store import DEFAULT_PROFILE
from .llm.registry import describe_providers, get_preset, resolve_llm_settings, validate_settings
from .realdata.loaders import load_generic_csv
from .realdata.pipeline import build_real_dataset
from .realdata.sources import list_datasets
from .realdata.weather import fetch_weather_for_slots
from .report.html_report import build_report


def create_app(root: Path | None = None) -> FastAPI:
    api = FastAPI(
        title="HomeShift AI API",
        version="1.0.0-demo",
        description="Python 领域层的本地 Demo HTTP 适配器",
    )
    api.state.project_root = Path(root or PROJECT_ROOT).resolve()
    api.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.get("/", include_in_schema=False)
    def api_root():
        """直接访问后端端口时，引导到交互式 API 文档。"""
        return RedirectResponse(url="/docs", status_code=307)

    @api.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    @api.exception_handler(ApiProblem)
    async def api_problem_handler(_request: Request, exc: ApiProblem):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @api.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_input",
                    "message": "请求参数无效",
                    "details": exc.errors(),
                }
            },
        )

    def ctx():
        return context_for(api.state.project_root)

    def require_data(current):
        if not current.usage.has_data():
            raise ApiProblem("data_missing", "请先导入家庭用电数据。", 409)

    @api.get("/api/v1/status")
    def get_status():
        current = ctx()
        date_range = current.usage.date_range()
        plan = current.store.get_active_plan()
        provenance = _read_json(current.data_dir / "provenance.json", {})
        tracking = _read_json(current.data_dir / "tracking_meta.json", {})
        return {
            "ready": current.usage.has_data() and bool(current.store.get_profile()),
            "data": {
                "available": current.usage.has_data(),
                "kind": provenance.get("data_kind"),
                "dataset": (provenance.get("dataset") or {}).get("id"),
                "start": date_range[0].isoformat() if date_range else None,
                "end": date_range[1].isoformat() if date_range else None,
                "tracking_kind": tracking.get("kind"),
            },
            "region": current.config.get("region", {}),
            "plan": {
                "active": bool(plan),
                "version": plan.get("version") if plan else None,
            },
            "memory_count": len(current.store.get_memories()),
            "model": public_settings(current),
        }

    @api.get("/api/v1/providers")
    def get_providers():
        current = ctx()
        selected = current.config.get("llm", {})
        providers = []
        for item in describe_providers():
            configured = item["key_ready"]
            # custom 的“密钥可选”不等于端点已经配置；没有 base_url/model 时
            # 前端不能把它列成可选成功项。
            if item["name"] == "custom":
                configured = bool(
                    selected.get("provider") == "custom"
                    and selected.get("base_url")
                    and selected.get("model")
                )
            providers.append({
                "name": item["name"],
                "label": item["label"],
                "kind": item["kind"],
                "default_model": item.get("default_model"),
                "configured": configured,
                "notes": item.get("notes", ""),
                "selected": item["name"] == selected.get("provider"),
            })
        return {"providers": providers, "current": public_settings(current)}

    @api.put("/api/v1/settings/model")
    def put_model(body: ModelSelection):
        if body.mode == "mock" and body.provider != "mock":
            raise ApiProblem("invalid_input", "离线彩排必须选择 mock 提供方。", 422)
        if body.mode == "live" and body.provider == "mock":
            raise ApiProblem("invalid_input", "实时模式不能选择 Mock。", 422)
        try:
            get_preset(body.provider)
            candidate = copy.deepcopy(load_config(api.state.project_root))
            candidate["llm"]["provider"] = body.provider
            candidate["llm"]["model"] = body.model
            validate_settings(resolve_llm_settings(candidate))
        except Exception as exc:
            raise ApiProblem("configuration_missing", str(exc), 409) from exc
        save_config_patch(
            {"llm": {"provider": body.provider, "model": body.model}},
            api.state.project_root,
        )
        return {"model": public_settings(ctx())}

    @api.get("/api/v1/datasets")
    def get_datasets():
        registered = []
        for item in list_datasets():
            registered.append({
                "id": item["id"],
                "title": item["title"],
                "short": item["short"],
                "manual": bool(item.get("manual")),
                "license": item.get("license"),
                "period": item.get("period"),
                "raw_resolution_minutes": item.get("raw_resolution_minutes"),
                "recommended_for": item.get("recommended_for"),
                "region": item.get("region"),
                "manual_hint": item.get("manual_hint"),
            })
        registered.insert(0, {
            "id": "synthetic",
            "title": "HomeShift 合成家庭",
            "short": "可重复生成的 56 天离线演示数据，含分电器真值",
            "manual": False,
            "license": "项目内生成",
            "period": "动态生成",
            "raw_resolution_minutes": 30,
            "recommended_for": "无网络彩排与完整流程演示",
            "region": DEFAULTS["region"],
        })
        return {"datasets": registered}

    @api.post("/api/v1/datasets/import")
    def import_dataset(
        dataset: Annotated[str, Form()],
        confirm_reset: Annotated[bool, Form()] = False,
        weather_source: Annotated[str, Form()] = "openmeteo",
        window_days: Annotated[int, Form(ge=7, le=365)] = 63,
        time_col: Annotated[str | None, Form()] = None,
        value_col: Annotated[str | None, Form()] = None,
        value_unit: Annotated[str, Form()] = "kwh",
        timestamp_format: Annotated[str | None, Form()] = None,
        file: UploadFile | None = File(default=None),
    ):
        current = ctx()
        if current.usage.has_data() and not confirm_reset:
            raise ApiProblem(
                "reset_confirmation_required",
                "重新导入会清空旧诊断、计划、复盘、记忆和 Trace，请先明确确认。",
                409,
            )
        if value_unit.lower() not in {"kwh", "wh", "kw", "w"}:
            raise ApiProblem("invalid_input", "单位只能是 kWh、Wh、kW 或 W。", 422)

        if dataset == "synthetic":
            reset_derived_state(current)
            # 合成器的物理模型与默认画像是新加坡场景，切回时必须同步地区口径。
            save_config_patch(
                {
                    "region": copy.deepcopy(DEFAULTS["region"]),
                    "tariff": copy.deepcopy(DEFAULTS["tariff"]),
                    "carbon": copy.deepcopy(DEFAULTS["carbon"]),
                    "disaggregation": copy.deepcopy(DEFAULTS["disaggregation"]),
                },
                api.state.project_root,
            )
            current = ctx()
            summary = init_dataset(current, days=window_days)
            profile = copy.deepcopy(DEFAULT_PROFILE)
            profile["data_source"] = "synthetic"
            profile["dataset_id"] = "synthetic"
            current.store.save_profile(profile)
            return {"import": summary, "workspace": workspace_payload(ctx())}

        local_path = None
        tmp_dir = None
        try:
            if file is not None:
                tmp_dir = tempfile.TemporaryDirectory(prefix="homeshift_import_")
                suffix = Path(file.filename or "upload.csv").suffix or ".csv"
                local_path = Path(tmp_dir.name) / f"upload{suffix}"
                with open(local_path, "wb") as output:
                    shutil.copyfileobj(file.file, output)
            if dataset in {"spgroup", "csv"} and local_path is None:
                raise ApiProblem("invalid_input", "该数据源需要上传 CSV 文件。", 422)
            loader_kwargs = {
                "time_col": time_col or None,
                "value_col": value_col or None,
                "value_unit": value_unit.lower(),
                "time_format": timestamp_format or None,
            }
            try:
                provenance = build_real_dataset(
                    current,
                    dataset=dataset,
                    window_days=window_days,
                    file_path=str(local_path) if local_path else None,
                    weather_source=weather_source,
                    loader_kwargs=loader_kwargs,
                )
            except (ValueError, KeyError, SystemExit) as exc:
                raise ApiProblem("invalid_input", str(exc), 422) from exc
        finally:
            if tmp_dir is not None:
                tmp_dir.cleanup()
        return {"import": provenance, "workspace": workspace_payload(ctx())}

    @api.get("/api/v1/profile")
    def get_profile():
        return {"profile": ctx().store.get_profile()}

    @api.put("/api/v1/profile")
    def put_profile(body: ProfileUpdate):
        current = ctx()
        require_data(current)
        profile = body.profile
        required = ("home_type", "location", "comfort_preferences", "goals")
        missing = [key for key in required if key not in profile]
        if missing:
            raise ApiProblem("invalid_input", f"家庭画像缺少字段：{', '.join(missing)}", 422)
        current.store.save_profile(profile)
        return {"profile": profile, "workspace": workspace_payload(current)}

    @api.get("/api/v1/workspace")
    def get_workspace():
        current = ctx()
        trace_payload = _read_json(current.data_dir / "last_trace.json", {})
        # 旧 CLI 直接写入的数组可能累计了多个数据集/多个任务，绝不能冒充
        # “本次运行”。只有新 Web 格式 {"operation": ..., "trace": [...]} 可展示。
        trace = [] if isinstance(trace_payload, list) else trace_payload.get("trace", [])
        return workspace_payload(current, trace=trace)

    @api.post("/api/v1/diagnose")
    def diagnose(body: LocaleRequest):
        current = ctx()
        require_data(current)
        prompt = DIAGNOSE_PROMPT if body.locale == "zh" else (
            "Diagnose the household's recent electricity use. Read the profile, usage, "
            "weather, tariff, carbon factor and NILM result. Explain the top three "
            "evidence-based findings, method limits, and the next step."
        )
        run = run_agent(current, prompt, locale=body.locale, operation="diagnose")
        mark_workflow_step(current, "diagnosis", run)
        return operation_response(current, run)

    @api.post("/api/v1/plan/propose")
    def propose_plan(body: LocaleRequest):
        current = ctx()
        require_data(current)
        require_workflow_step(
            current,
            "diagnosis",
            "请先完成本次 Agent 诊断，再请求计划建议。",
        )
        prompt = WEB_PLAN_PROMPT_ZH if body.locale == "zh" else WEB_PLAN_PROMPT_EN
        run = run_agent(
            current,
            prompt,
            locale=body.locale,
            operation="plan_proposal",
            proposal_only=True,
        )
        if not run.get("proposal"):
            raise ApiProblem(
                "agent_failed",
                "Agent 未提交结构化 action_ids，未形成可确认建议。",
                502,
            )
        mark_workflow_step(current, "plan_proposal", run)
        return operation_response(current, run)

    @api.post("/api/v1/plan/commit")
    def commit_plan(body: PlanCommitRequest):
        current = ctx()
        require_data(current)
        require_workflow_step(
            current,
            "plan_proposal",
            "请先让 Agent 生成本次行动建议，再提交正式计划。",
        )
        result = dispatch_tool(
            current,
            "save_plan",
            {"action_ids": body.action_ids, "rationale": body.rationale},
        )
        if result.get("error"):
            raise ApiProblem("invalid_input", result.get("message", "计划无法提交"), 422, result)
        mark_workflow_step(current, "plan_commit")
        return {"plan": result["plan"], "workspace": workspace_payload(current)}

    @api.post("/api/v1/tracking/simulate-week")
    def simulate_week(body: SimulateWeekRequest):
        current = ctx()
        plan = current.store.get_active_plan()
        if not plan:
            raise ApiProblem("plan_missing", "请先确认并提交正式计划。", 409)
        summary = append_week_with_plan(current, plan, body.adherence)
        marker = {
            "kind": "synthetic",
            "label": "合成实施后数据",
            "summary": summary,
        }
        _write_json(current.data_dir / "tracking_meta.json", marker)
        mark_workflow_step(current, "tracking")
        return {"tracking": marker, "workspace": workspace_payload(current)}

    @api.post("/api/v1/tracking/import")
    def import_tracking(
        file: UploadFile = File(...),
        time_col: Annotated[str | None, Form()] = None,
        value_col: Annotated[str | None, Form()] = None,
        value_unit: Annotated[str, Form()] = "kwh",
        timestamp_format: Annotated[str | None, Form()] = None,
        weather_source: Annotated[str, Form()] = "none",
    ):
        current = ctx()
        plan = current.store.get_active_plan()
        if not plan:
            raise ApiProblem("plan_missing", "请先确认并提交正式计划。", 409)
        with tempfile.TemporaryDirectory(prefix="homeshift_tracking_") as folder:
            path = Path(folder) / "tracking.csv"
            with open(path, "wb") as output:
                shutil.copyfileobj(file.file, output)
            try:
                parsed = load_generic_csv(
                    path,
                    time_col=time_col,
                    value_col=value_col,
                    value_unit=value_unit,
                    time_format=timestamp_format,
                )
            except ValueError as exc:
                raise ApiProblem("invalid_input", str(exc), 422) from exc
        rows = parsed["usage"]
        current_last = current.usage.load_usage()[-1][0]
        if rows[0][0] <= current_last:
            raise ApiProblem(
                "invalid_input",
                f"实施后数据必须全部晚于当前最后时点 {current_last.isoformat(timespec='minutes')}。",
                422,
            )
        region = current.config.get("region", {})
        try:
            weather, weather_meta = fetch_weather_for_slots(
                [ts for ts, _ in rows],
                region.get("latitude", 1.3521),
                region.get("longitude", 103.8198),
                source=weather_source,
                timeout=current.config.get("realdata", {}).get("download_timeout_seconds", 180),
            )
        except Exception as exc:
            weather, weather_meta = [], {"source": "failed", "error": str(exc)}
        current.usage.append_rows(rows, weather, [], [])
        marker = {
            "kind": "real",
            "label": "真实实施后数据",
            "rows": len(rows),
            "period": {
                "start": rows[0][0].isoformat(timespec="minutes"),
                "end": rows[-1][0].isoformat(timespec="minutes"),
            },
            "weather": weather_meta,
        }
        _write_json(current.data_dir / "tracking_meta.json", marker)
        _append_tracking_provenance(current, marker)
        mark_workflow_step(current, "tracking")
        return {"tracking": marker, "workspace": workspace_payload(current)}

    @api.post("/api/v1/review")
    def review(body: LocaleRequest):
        current = ctx()
        if not current.store.get_active_plan():
            raise ApiProblem("plan_missing", "请先确认并提交正式计划。", 409)
        if not (current.data_dir / "tracking_meta.json").exists():
            raise ApiProblem(
                "tracking_missing",
                "请先生成或上传实施后数据，再运行复盘 Agent。",
                409,
            )
        prompt = REVIEW_PROMPT if body.locale == "zh" else (
            "Review the active plan using weather-normalized tracking. Explain total "
            "savings, action-level reliability, anomalies, next-week advice, and record "
            "a durable insight only when justified."
        )
        run = run_agent(current, prompt, locale=body.locale, operation="review")
        mark_workflow_step(current, "review", run)
        return operation_response(current, run)

    @api.post("/api/v1/chat")
    def chat(body: ChatRequest):
        current = ctx()
        require_data(current)
        history_text = "\n".join(
            f"{turn.role}: {turn.text}" for turn in body.history[-8:]
        )
        if body.locale == "en":
            prompt = (
                "Answer the user's question using the current household, active plan, "
                "tracking evidence and long-term memories. Use tools for every number.\n"
                f"Recent conversation:\n{history_text}\nUser: {body.message}"
            )
        else:
            prompt = (
                "请结合当前家庭画像、正式计划、追踪证据和长期记忆回答用户。"
                "涉及任何数字必须调用工具，不要凭空计算。\n"
                f"最近对话：\n{history_text}\n用户：{body.message}"
            )
        run = run_agent(current, prompt, locale=body.locale, operation="chat")
        return {"run": run}

    @api.get("/api/v1/report")
    def report():
        current = ctx()
        require_data(current)
        try:
            path = build_report(current)
        except RuntimeError as exc:
            raise ApiProblem("report_failed", str(exc), 409) from exc
        return FileResponse(
            path,
            media_type="text/html; charset=utf-8",
            filename="homeshift-weekly-report.html",
        )

    return api


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_tracking_provenance(current, marker: dict) -> None:
    path = current.data_dir / "provenance.json"
    provenance = _read_json(path, {})
    history = provenance.get("tracking_imports", [])
    history.append(marker)
    provenance["tracking_imports"] = history
    _write_json(path, provenance)


app = create_app()
