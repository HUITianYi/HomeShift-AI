"""工具注册表：智能体能对世界做的所有事情。

每个工具 = Anthropic tool-use 规范的 JSON Schema 定义 + 一个本地执行函数。
LLM 决定“调用哪个工具、传什么参数”；执行结果（真实数据/确定性计算）
以 JSON 返回给 LLM。这就是 Agentic AI 的核心闭环：
LLM 负责推理与决策，工具负责事实与计算。

工具一览（感知 -> 分析 -> 行动 -> 记忆）：
- 感知: get_household_profile / get_usage_summary / get_weather_summary
        / get_tariff_info / get_carbon_info
- 分析: disaggregate_usage / simulate_savings
- 行动: save_plan / track_progress
- 记忆: get_active_plan / record_feedback / get_memories
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from ..domain import carbon as carbon_mod
from ..domain import tariff as tariff_mod
from ..domain.disaggregate import disaggregate
from ..domain.simulate import candidate_actions
from ..domain.tracker import track_progress

# ---------------------------------------------------------------------------
# 工具定义（传给 Claude API 的 tools 参数）
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "get_household_profile",
        "description": (
            "读取家庭画像：住房类型、成员与作息、主要电器、空调设定温度、"
            "热水器使用模式、舒适约束（不可violated）与省钱目标。"
            "任何诊断或计划前都应先了解画像。"
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_usage_summary",
        "description": (
            "读取最近 N 天的智能电表数据摘要：逐日用电量、日均值、最高/最低日、"
            "以及按当前电价折算的月度电费估算。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "回看天数，默认 30",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_weather_summary",
        "description": "读取最近 N 天室外温度摘要（日均/最高温、制冷度时），用于解释空调用电。",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "回看天数，默认 30"}
            },
            "required": [],
        },
    },
    {
        "name": "disaggregate_usage",
        "description": (
            "负载分解（NILM）：把最近 N 天的总电表读数拆解为空调/热水器/冰箱/"
            "待机/洗衣/其他六大类，返回各类日均 kWh 与占比。"
            "这是诊断“电费为什么高”的核心工具。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "回看天数，默认 28"}
            },
            "required": [],
        },
    },
    {
        "name": "get_tariff_info",
        "description": "读取当前电价方案（受管制固定费率/分时电价）与费率明细。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_carbon_info",
        "description": "读取电网碳排放因子（kgCO2/kWh），用于把节电换算为减排。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "simulate_savings",
        "description": (
            "确定性节能模拟器：基于负载分解结果、家庭画像（含舒适约束）和电价，"
            "计算每个候选节能动作的月度节省（kWh/当前地区货币/CO2）。"
            "所有节省数字必须来自本工具，禁止自行估算。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "负载分解回看天数，默认 28",
                }
            },
            "required": [],
        },
    },
    {
        "name": "save_plan",
        "description": (
            "保存节能计划（自动成为当前生效版本，旧版本归档）。"
            "传入选中的动作 id 列表（来自 simulate_savings 的候选），"
            "系统会自动记录基线期、预期节省与创建时间。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "选中的动作 id，如 ['ac_setpoint_26','heater_timer']",
                },
                "rationale": {
                    "type": "string",
                    "description": "选择这些动作的理由（写给用户看的一句话）",
                },
            },
            "required": ["action_ids"],
        },
    },
    {
        "name": "get_active_plan",
        "description": "读取当前生效的节能计划（动作清单、预期节省、基线期、版本号）。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "track_progress",
        "description": (
            "追踪计划执行效果：对比基线期与计划生效后的用电，"
            "含天气归一化（制冷度时）、总体节省、分动作达成率。复盘必用。"
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "record_feedback",
        "description": (
            "把用户反馈或复盘结论写入长期记忆（跨会话保留），"
            "例如“用户觉得 26°C 午后太热，空调约束调整为 25°C”。"
            "涉及舒适约束的反馈应同时更新画像。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "要记住的内容"},
                "kind": {
                    "type": "string",
                    "enum": ["feedback", "insight", "constraint"],
                    "description": "feedback=用户反馈 insight=复盘结论 constraint=约束变化",
                },
            },
            "required": ["note"],
        },
    },
    {
        "name": "get_memories",
        "description": "读取长期记忆（历史反馈与复盘结论），避免重复犯错或重复建议。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


# ---------------------------------------------------------------------------
# 工具执行（dispatch）
# ---------------------------------------------------------------------------

def _usage_summary(ctx, days: int) -> dict:
    rows = ctx.usage.last_n_days(days)
    if not rows:
        return {"error": "no_data", "message": "没有用电数据，请先运行 init"}
    daily = ctx.usage.daily_totals(rows)
    values = list(daily.values())
    avg = sum(values) / len(values)
    peak_day = max(daily, key=daily.get)
    low_day = min(daily, key=daily.get)
    monthly = tariff_mod.monthly_cost(avg * 30, ctx.config)
    return {
        "period": {"start": min(daily).isoformat(), "end": max(daily).isoformat()},
        "days": len(values),
        "avg_daily_kwh": round(avg, 2),
        "max_day": {"date": peak_day.isoformat(), "kwh": daily[peak_day]},
        "min_day": {"date": low_day.isoformat(), "kwh": daily[low_day]},
        "projected_monthly": monthly,
        "daily_kwh": {d.isoformat(): v for d, v in daily.items()},
    }


def _weather_summary(ctx, days: int) -> dict:
    weather = ctx.usage.load_weather()
    last = ctx.usage.last_date()
    if not weather or last is None:
        return {"error": "no_data", "message": "没有天气数据"}
    start = last - timedelta(days=days - 1)
    daily_temps: dict[date, list[float]] = {}
    for ts, temp in weather.items():
        if start <= ts.date() <= last:
            daily_temps.setdefault(ts.date(), []).append(temp)
    if not daily_temps:
        return {"error": "no_data", "message": "该时段没有天气数据"}
    avg_temp = sum(sum(v) / len(v) for v in daily_temps.values()) / len(daily_temps)
    max_temp = max(max(v) for v in daily_temps.values())
    cdh = sum(
        sum(max(0.0, t - 26.0) * 0.5 for t in temps) for temps in daily_temps.values()
    ) / len(daily_temps)
    return {
        "period": {"start": min(daily_temps).isoformat(), "end": max(daily_temps).isoformat()},
        "avg_temp_c": round(avg_temp, 1),
        "max_temp_c": round(max_temp, 1),
        "cooling_degree_hours_per_day": round(cdh, 1),
        "note": "制冷度时(CDH)以 26°C 为基准，反映空调制冷需求强度",
    }


def _disaggregate(ctx, days: int) -> dict:
    rows = ctx.usage.last_n_days(days)
    weather = ctx.usage.load_weather()
    # 传 config：作息锚点与气候假设会随数据集切换
    return disaggregate(rows, weather, ctx.config)


def _simulate(ctx, days: int) -> dict:
    disagg = _disaggregate(ctx, days)
    profile = ctx.store.get_profile()
    return candidate_actions(disagg, profile, ctx.config)


def _save_plan(ctx, action_ids: list[str], rationale: str) -> dict:
    sim = _simulate(ctx, 28)
    if "actions" not in sim:
        return {"error": "simulate_failed", "detail": sim}
    chosen = [a for a in sim["actions"] if a["id"] in action_ids]
    if not chosen:
        return {
            "error": "no_valid_actions",
            "message": f"动作 id 无效：{action_ids}；可选：{[a['id'] for a in sim['actions']]}",
        }
    last = ctx.usage.last_date()
    baseline_start = last - timedelta(days=27)
    currency_code = sim.get("currency") or ctx.config.get("region", {}).get("currency", "")
    expected_cost = round(
        sum(a.get("est_cost_per_month", a.get("est_sgd_per_month", 0)) for a in chosen), 2
    )
    plan = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "baseline": {"start": baseline_start.isoformat(), "end": last.isoformat()},
        "rationale": rationale,
        "actions": chosen,
        "expected_per_month": {
            "kwh": round(sum(a["est_kwh_per_month"] for a in chosen), 1),
            "cost": expected_cost,
            "currency": currency_code,
            "sgd": expected_cost,  # 旧 CLI/导出兼容；Web 不读取该字段
            "co2_kg": round(sum(a["est_co2_kg_per_month"] for a in chosen), 1),
        },
    }
    saved = ctx.store.save_plan(plan)
    return {"saved": True, "plan": saved}


def _record_feedback(ctx, note: str, kind: str) -> dict:
    entry = ctx.store.add_memory(note, kind=kind)
    return {"saved": True, "memory": entry}


def dispatch_tool(ctx, name: str, tool_input: dict) -> dict:
    """执行工具并返回 JSON 可序列化的结果。"""
    if name == "get_household_profile":
        profile = ctx.store.get_profile()
        return profile if profile else {"error": "no_profile", "message": "画像不存在，请先运行 init"}
    if name == "get_usage_summary":
        return _usage_summary(ctx, int(tool_input.get("days", 30)))
    if name == "get_weather_summary":
        return _weather_summary(ctx, int(tool_input.get("days", 30)))
    if name == "disaggregate_usage":
        return _disaggregate(ctx, int(tool_input.get("days", 28)))
    if name == "get_tariff_info":
        return tariff_mod.tariff_summary(ctx.config)
    if name == "get_carbon_info":
        return carbon_mod.carbon_summary(ctx.config)
    if name == "simulate_savings":
        return _simulate(ctx, int(tool_input.get("days", 28)))
    if name == "save_plan":
        return _save_plan(
            ctx,
            list(tool_input.get("action_ids", [])),
            str(tool_input.get("rationale", "")),
        )
    if name == "get_active_plan":
        plan = ctx.store.get_active_plan()
        return plan if plan else {"error": "no_plan", "message": "尚无生效的节能计划"}
    if name == "track_progress":
        return track_progress(ctx)
    if name == "record_feedback":
        return _record_feedback(
            ctx, str(tool_input.get("note", "")), str(tool_input.get("kind", "feedback"))
        )
    if name == "get_memories":
        return {"memories": ctx.store.get_memories()}
    return {"error": "unknown_tool", "message": f"未知工具: {name}"}


def serialize_result(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)
