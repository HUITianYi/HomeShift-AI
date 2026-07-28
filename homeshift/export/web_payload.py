"""导出给可视化网站的数据包。

对齐目标：队友的前端站点 homeshift-ai（四段式 Baseline / Diagnosis /
Plans / Track + 七个专家 agent）。

设计取舍
---------------------------------------------------------------------------
我们拿不到前端内部的变量名，因此这里的原则是：
**结构对齐 + 字段自解释 + 全部双语**，让前端改动量降到最小。

1) 分段与站点一一对应：baseline / diagnosis / plans / track / agents。
2) 每个展示用的文本都是 {"zh": ..., "en": ...}，前端的中英切换直接取键。
3) 每个数字都同时给"原始值"和"格式化字符串"（value + display），
   前端不需要自己处理货币符号和小数位，避免两边格式不一致。
4) 一次导出多份文件：整包 + 分段 + 一个 .js 版本，
   静态页面可以直接 <script src> 引入，不需要跑服务器解决跨域。
5) 顶层带 schema_version，后续字段变更可以让前端做兼容判断。

如果前端已经定好了字段名，只需要改本文件末尾的 adapt_* 函数，
其余计算逻辑不用动 —— 这是刻意留出的适配层。
---------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from ..agent.roles import ROLES, roster
from ..agent.tools import TOOL_DEFINITIONS
from ..domain.appliances import CATEGORY_LABELS
from ..domain.carbon import emission_factor
from ..domain.comfort import locked_rules
from ..domain.disaggregate import CATEGORIES, disaggregate, evaluate_against_truth
from ..domain.simulate import candidate_actions
from ..domain.tariff import currency, effective_rate, monthly_cost
from ..domain.tracker import track_progress

SCHEMA_VERSION = "1.0"

CATEGORY_LABELS_EN = {
    "aircon": "Cooling / AC",
    "water_heater": "Water heater",
    "fridge": "Refrigeration",
    "standby": "Standby load",
    "laundry": "Laundry",
    "other": "Lighting / kitchen / media",
}

COMFORT_IMPACT_LABEL = {
    "none": {"zh": "无影响", "en": "No impact"},
    "low": {"zh": "影响很小", "en": "Minimal"},
    "medium": {"zh": "中等影响", "en": "Moderate"},
    "high": {"zh": "影响较大", "en": "Significant"},
}

EFFORT_LABEL = {
    "zero_cost": {"zh": "零成本", "en": "Free"},
    "low_cost": {"zh": "低成本", "en": "Low cost"},
    "invest": {"zh": "需投入", "en": "Requires investment"},
}


# ===========================================================================
# 小工具
# ===========================================================================

def money(value: float | None, cur: dict, nd: int = 2) -> dict:
    """金额统一带上原始值与格式化文本，前端不用自己拼货币符号。"""
    if value is None:
        return {"value": None, "display": "—", "currency": cur["code"]}
    return {
        "value": round(float(value), nd),
        "display": f"{cur['symbol']}{float(value):,.{nd}f}",
        "currency": cur["code"],
    }


def quantity(value: float | None, unit: str, nd: int = 1) -> dict:
    if value is None:
        return {"value": None, "unit": unit, "display": "—"}
    return {
        "value": round(float(value), nd),
        "unit": unit,
        "display": f"{float(value):,.{nd}f} {unit}",
    }


def bilingual(zh: str, en: str) -> dict:
    return {"zh": zh, "en": en}


def _slot_label(slot: int) -> str:
    return f"{slot // 2:02d}:{'30' if slot % 2 else '00'}"


# ===========================================================================
# 各分段
# ===========================================================================

def build_meta(ctx) -> dict:
    provenance_path = ctx.data_dir / "provenance.json"
    provenance = None
    if provenance_path.exists():
        with open(provenance_path, "r", encoding="utf-8") as f:
            provenance = json.load(f)

    region = ctx.config.get("region", {})
    cur = currency(ctx.config)
    profile = ctx.store.get_profile()

    data_kind = "real" if profile.get("data_source") == "real" else "synthetic"

    meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "product": {
            "name": "HomeShift AI",
            "tagline": bilingual("省钱不省舒适", "Cut bills, not comfort."),
        },
        "data_kind": data_kind,
        "data_badge": bilingual(
            "真实数据" if data_kind == "real" else "合成演示数据",
            "Real dataset" if data_kind == "real" else "Synthetic demo",
        ),
        "region": {
            "code": region.get("code"),
            "name": region.get("name"),
            "timezone": region.get("timezone"),
            "climate": region.get("climate"),
        },
        "currency": cur,
        "tariff": {
            "plan": ctx.config["tariff"].get("plan"),
            "rate_per_kwh": round(effective_rate(ctx.config), 4),
            "gst_rate": ctx.config["tariff"].get("gst_rate"),
            "note": ctx.config["tariff"].get("source_note", ""),
        },
        "carbon": {
            "grid_emission_factor_kg_per_kwh": emission_factor(ctx.config),
            "note": ctx.config.get("carbon", {}).get("source_note", ""),
        },
    }
    if provenance:
        meta["provenance"] = {
            "dataset": provenance.get("dataset"),
            "window": provenance.get("window"),
            "weather": provenance.get("weather"),
            "known_limitations": provenance.get("known_limitations", []),
        }
    return meta


def build_household(ctx) -> dict:
    profile = ctx.store.get_profile()
    observed = profile.get("observed", {})
    goals = profile.get("goals", {})

    tags = []
    if profile.get("home_type"):
        tags.append(profile["home_type"])
    if observed.get("wfh_likely"):
        tags.append("WFH")
    if observed.get("peak_half_hour"):
        tags.append(f"Peak {observed['peak_half_hour']}")

    return {
        "name": bilingual(
            profile.get("home_type", "家庭"),
            profile.get("home_type", "Household"),
        ),
        "location": profile.get("location", "-"),
        "summary": bilingual(
            profile.get("household", ""),
            profile.get("household", ""),
        ),
        "tags": tags,
        "profile_origin": bilingual(
            "画像由真实用电曲线反推" if profile.get("data_source") == "real"
            else "画像为演示设定",
            "Profile inferred from real load curve" if profile.get("data_source") == "real"
            else "Profile is a demo persona",
        ),
        "assumptions": profile.get("assumptions", []),
        "comfort_rules": locked_rules(profile),
        "goal": {
            "type": "reduction_pct",
            "value": goals.get("monthly_saving_target_pct")
                     or goals.get("monthly_saving_target_sgd"),
            "display": (f"−{goals.get('monthly_saving_target_pct')}%"
                        if goals.get("monthly_saving_target_pct") else "—"),
            "priority": goals.get("priority", ""),
        },
    }


def build_baseline(ctx, days: int = 30) -> dict:
    rows = ctx.usage.last_n_days(days)
    if not rows:
        return {"available": False, "reason": "no_usage_data"}

    cur = currency(ctx.config)
    weather = ctx.usage.load_weather()
    daily = ctx.usage.daily_totals(rows)
    avg_daily = sum(daily.values()) / len(daily)
    month_kwh = avg_daily * 30
    bill = monthly_cost(month_kwh, ctx.config)
    co2 = month_kwh * emission_factor(ctx.config)

    # 24 小时曲线（48 个半小时点），网站的 "24-HOUR SIGNATURE" 用
    slot_sum: dict[int, float] = {}
    slot_count: dict[int, int] = {}
    for ts, kwh in rows:
        slot = ts.hour * 2 + (1 if ts.minute >= 30 else 0)
        slot_sum[slot] = slot_sum.get(slot, 0.0) + kwh
        slot_count[slot] = slot_count.get(slot, 0) + 1
    signature = [
        {
            "slot": s,
            "time": _slot_label(s),
            "kwh": round(slot_sum.get(s, 0.0) / max(slot_count.get(s, 1), 1), 4),
        }
        for s in range(48)
    ]
    peak = max(signature, key=lambda item: item["kwh"]) if signature else None

    # 逐日序列（含气温），网站趋势图用
    daily_temp: dict[date, list[float]] = {}
    for ts, temp in weather.items():
        if ts.date() in daily:
            daily_temp.setdefault(ts.date(), []).append(temp)
    daily_series = [
        {
            "date": d.isoformat(),
            "kwh": round(v, 3),
            "temp_c": (round(sum(daily_temp[d]) / len(daily_temp[d]), 1)
                       if d in daily_temp else None),
            "weekday": d.weekday(),
            "is_weekend": d.weekday() >= 5,
        }
        for d, v in daily.items()
    ]

    # 证据清单（网站 DATA DESK 那一块）
    evidence = []
    for name, kind, label_zh, label_en in [
        ("usage.csv", "half_hour_data", "半小时电表数据", "Half-hour meter data"),
        ("weather.csv", "weather", "室外气温", "Outdoor temperature"),
        ("usage_groundtruth.csv", "submeter_truth", "分电器真值", "Sub-meter ground truth"),
        ("provenance.json", "provenance", "数据出处与质量报告", "Provenance & quality report"),
    ]:
        path = ctx.data_dir / name
        evidence.append({
            "kind": kind,
            "file": name,
            "label": bilingual(label_zh, label_en),
            "available": path.exists(),
            "rows": _count_rows(path) if path.exists() and name.endswith(".csv") else None,
        })

    period_start, period_end = min(daily), max(daily)
    return {
        "available": True,
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "days": len(daily),
            "label": bilingual(
                f"{period_start.strftime('%m月%d日')} ~ {period_end.strftime('%m月%d日')} 基线期",
                f"{period_start.strftime('%b %d')} – {period_end.strftime('%b %d')} baseline",
            ),
        },
        "headline": {
            "kwh_this_month": quantity(month_kwh, "kWh", 0),
            "avg_daily_kwh": quantity(avg_daily, "kWh", 2),
            "est_bill": money(bill["total_cost"], cur),
            "carbon_kg": quantity(co2, "kg", 1),
            "sources_count": sum(1 for e in evidence if e["available"]),
        },
        "extremes": {
            "max_day": {"date": max(daily, key=daily.get).isoformat(),
                        "kwh": max(daily.values())},
            "min_day": {"date": min(daily, key=daily.get).isoformat(),
                        "kwh": min(daily.values())},
        },
        "signature_24h": {
            "slots": signature,
            "peak": {"time": peak["time"], "kwh": peak["kwh"]} if peak else None,
            "bands": _signature_bands(signature),
        },
        "daily_series": daily_series,
        "evidence": evidence,
    }


def _signature_bands(signature: list[dict]) -> list[dict]:
    """把 24 小时切成几段并给出观察结论（网站曲线下方的注释条）。"""
    def avg(lo, hi):
        vals = [s["kwh"] for s in signature if lo <= s["slot"] < hi]
        return sum(vals) / len(vals) if vals else 0.0

    overnight, daytime, evening = avg(0, 14), avg(18, 32), avg(36, 46)
    baseline = min(s["kwh"] for s in signature) if signature else 0
    bands = [
        {"id": "overnight", "start": "00:00", "end": "07:00",
         "avg_kwh": round(overnight, 3),
         "label": bilingual("夜间", "Overnight"),
         "note": bilingual(
             f"夜间均值 {overnight:.2f} kWh/半小时，是基线负载的 {overnight / baseline:.1f} 倍"
             if baseline else "夜间时段",
             f"Overnight averages {overnight:.2f} kWh per half-hour"
             + (f", {overnight / baseline:.1f}× the floor" if baseline else ""))},
        {"id": "daytime", "start": "09:00", "end": "16:00",
         "avg_kwh": round(daytime, 3),
         "label": bilingual("白天", "Daytime"),
         "note": bilingual(
             f"白天均值 {daytime:.2f} kWh/半小时",
             f"Daytime averages {daytime:.2f} kWh per half-hour")},
        {"id": "evening", "start": "18:00", "end": "23:00",
         "avg_kwh": round(evening, 3),
         "label": bilingual("晚间", "Evening"),
         "note": bilingual(
             f"晚间是全天高峰，均值 {evening:.2f} kWh/半小时",
             f"Evening is the daily peak at {evening:.2f} kWh per half-hour")},
    ]
    return bands


def build_diagnosis(ctx, days: int = 28) -> dict:
    rows = ctx.usage.last_n_days(days)
    if not rows:
        return {"available": False, "reason": "no_usage_data"}

    cur = currency(ctx.config)
    weather = ctx.usage.load_weather()
    disagg = disaggregate(rows, weather, ctx.config)
    if "daily_avg_kwh" not in disagg:
        return {"available": False, "reason": disagg.get("error", "disaggregation_failed")}

    rate = effective_rate(ctx.config)
    factor = emission_factor(ctx.config)
    daily_avg = disagg["daily_avg_kwh"]
    share = disagg["share_pct"]

    ranked = sorted(CATEGORIES, key=lambda c: daily_avg.get(c, 0), reverse=True)
    categories = []
    for rank, cat in enumerate(ranked, start=1):
        kwh_day = daily_avg.get(cat, 0.0)
        categories.append({
            "id": cat,
            "rank": rank,
            "label": bilingual(CATEGORY_LABELS.get(cat, cat), CATEGORY_LABELS_EN.get(cat, cat)),
            "kwh_per_day": round(kwh_day, 2),
            "kwh_per_month": round(kwh_day * 30, 1),
            "share_pct": share.get(cat, 0.0),
            "cost_per_month": money(kwh_day * 30 * rate, cur),
            "co2_kg_per_month": round(kwh_day * 30 * factor, 1),
        })

    findings = []
    for cat_entry in categories[:3]:
        findings.append({
            "id": f"finding_{cat_entry['id']}",
            "category": cat_entry["id"],
            "severity": "high" if cat_entry["share_pct"] >= 25 else "medium",
            "title": bilingual(
                f"{cat_entry['label']['zh']}占 {cat_entry['share_pct']}%",
                f"{cat_entry['label']['en']} is {cat_entry['share_pct']}% of the bill",
            ),
            "metric": {
                "kwh_per_day": cat_entry["kwh_per_day"],
                "cost_per_month": cat_entry["cost_per_month"],
            },
        })

    # 分解精度：只有在真的有分表真值时才输出，没有就明说没有
    accuracy = {"available": False,
                "note": bilingual(
                    "该数据源没有分电器真值，负载分解精度无法定量验证（真实家庭的常态）",
                    "No sub-meter ground truth in this source; accuracy cannot be quantified")}
    truth_rows = ctx.usage.load_groundtruth()
    if truth_rows:
        start = rows[0][0].date()
        truth = [r for r in truth_rows if r["timestamp"].date() >= start]
        result = evaluate_against_truth(disagg, truth, _category_map(ctx))
        if "error" not in result:
            accuracy = {
                "available": True,
                "days": result["days"],
                "per_category": result["per_category"],
                "note": bilingual(
                    "对照数据集自带的分电器真值计算的平均绝对误差（MAE）",
                    "Mean absolute error against the dataset's sub-meter ground truth"),
            }

    return {
        "available": True,
        "period": disagg["period"],
        "days": disagg["days"],
        "avg_daily_total_kwh": disagg["avg_daily_total_kwh"],
        "categories": categories,
        "findings": findings,
        "method": {
            "name": bilingual("NILM 启发式负载分解", "Heuristic NILM disaggregation"),
            "notes": disagg.get("method_notes", []),
        },
        "accuracy": accuracy,
        "daily_series": disagg.get("daily_series", []),
    }


def _category_map(ctx) -> dict | None:
    path = ctx.data_dir / "provenance.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return (json.load(f).get("category_map")) or None


def build_plans(ctx, days: int = 28) -> dict:
    cur = currency(ctx.config)
    profile = ctx.store.get_profile()
    rows = ctx.usage.last_n_days(days)
    if not rows:
        return {"available": False, "reason": "no_usage_data"}

    disagg = disaggregate(rows, ctx.usage.load_weather(), ctx.config)
    sim = candidate_actions(disagg, profile, ctx.config)
    if "actions" not in sim:
        return {"available": False, "reason": sim.get("error", "simulate_failed")}

    active = ctx.store.get_active_plan()
    chosen_ids = {a["id"] for a in (active or {}).get("actions", [])}

    def to_action(action: dict, selected: bool) -> dict:
        verdict = action.get("comfort_verdict", {})
        return {
            "id": action["id"],
            "title": bilingual(action["title"], action["title"]),
            "description": bilingual(action["description"], action["description"]),
            "category": action["category"],
            "selected": selected,
            "confirmed_by_user": False,  # 站点强调 "user-confirmed actions only"
            "savings": {
                "kwh_per_month": action["est_kwh_per_month"],
                "cost_per_month": money(
                    action.get("est_cost_per_month", action.get("est_sgd_per_month")), cur),
                "co2_kg_per_month": action["est_co2_kg_per_month"],
            },
            "comfort_impact": {
                "level": action["comfort_impact"],
                "label": COMFORT_IMPACT_LABEL.get(
                    action["comfort_impact"],
                    bilingual(action["comfort_impact"], action["comfort_impact"])),
            },
            "effort": {
                "level": action["effort"],
                "label": EFFORT_LABEL.get(
                    action["effort"], bilingual(action["effort"], action["effort"])),
            },
            "comfort_verdict": verdict,
            "notes": action.get("notes", ""),
        }

    candidates = [to_action(a, a["id"] in chosen_ids) for a in sim["actions"]]
    vetoed = [to_action(a, False) for a in sim.get("comfort_review", {}).get("vetoed", [])]

    expected = (active or {}).get("expected_per_month", {})
    plan_block = {
        "available": True,
        "has_committed_plan": active is not None,
        "version": (active or {}).get("version"),
        "created_at": (active or {}).get("created_at"),
        "rationale": (active or {}).get("rationale", ""),
        "baseline": (active or {}).get("baseline"),
        "expected_per_month": {
            "kwh": expected.get("kwh"),
            "cost": money(expected.get("cost", expected.get("sgd")), cur),
            "co2_kg": expected.get("co2_kg"),
        },
        "potential_per_month": {
            "kwh": sim["potential_total_per_month"]["kwh"],
            "cost": money(sim["potential_total_per_month"].get("cost"), cur),
            "co2_kg": sim["potential_total_per_month"]["co2_kg"],
        },
        "candidates": candidates,
        "vetoed_by_comfort": vetoed,
        "comfort_summary": sim.get("comfort_review", {}).get("summary", {}),
        "seven_day_schedule": build_seven_day_schedule(ctx, active or {"actions": sim["actions"]}),
    }
    return plan_block


DAILY_ACTIONS = {"ac_setpoint_26", "heater_timer", "standby_cut"}
WEEKLY_ACTIONS = {"cold_wash", "shift_laundry_offpeak"}
ONE_OFF_ACTIONS = {"fridge_tune"}


def build_seven_day_schedule(ctx, plan: dict) -> list[dict]:
    """把计划展开成七天的可执行清单（站点强调 "seven-day plan"）。

    规则是确定性的：每日型动作天天出现，每周型动作放在固定日，
    一次性动作放在第一天。这样前端拿到的就是一张可勾选的日历。
    """
    last = ctx.usage.last_date()
    start = (last + timedelta(days=1)) if last else date.today()
    actions = plan.get("actions", [])

    schedule = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        items = []
        for action in actions:
            aid = action["id"]
            if aid in DAILY_ACTIONS:
                items.append({"action_id": aid, "title": action["title"],
                              "cadence": "daily", "done": False})
            elif aid in WEEKLY_ACTIONS and day.weekday() in (2, 5):
                items.append({"action_id": aid, "title": action["title"],
                              "cadence": "twice_weekly", "done": False})
            elif aid in ONE_OFF_ACTIONS and offset == 0:
                items.append({"action_id": aid, "title": action["title"],
                              "cadence": "one_off", "done": False})
        schedule.append({
            "day": offset + 1,
            "date": day.isoformat(),
            "weekday": day.weekday(),
            "items": items,
        })
    return schedule


def build_track(ctx) -> dict:
    cur = currency(ctx.config)
    result = track_progress(ctx)
    status = result.get("status")

    if status != "ok":
        return {
            "available": False,
            "status": status,
            "message": bilingual(
                result.get("message", ""),
                "Not enough post-plan data to evaluate yet."),
        }

    saving = result["saving"]
    daily = result["daily_kwh"]

    per_action = []
    for item in result.get("per_action", []):
        per_action.append({
            "action_id": item["id"],
            "title": bilingual(item["title"], item["title"]),
            "planned_kwh_day": item.get("planned_kwh_day"),
            "actual_kwh_day": item.get("actual_kwh_day"),
            "achievement_pct": item.get("achievement_pct"),
            "status": _achievement_status(item.get("achievement_pct")),
            "note": item.get("note", ""),
        })

    return {
        "available": True,
        "status": "ok",
        "plan_version": result["plan_version"],
        "baseline_period": result["baseline_period"],
        "after_period": result["after_period"],
        "weather_normalization": result["weather_normalization"],
        "daily_kwh": daily,
        "comparison_bars": [
            {"id": "baseline", "label": bilingual("基线日均", "Baseline"),
             "kwh": daily["baseline"]},
            {"id": "expected", "label": bilingual("若不行动（天气归一化）",
                                                  "Expected without action"),
             "kwh": daily["expected_no_action"]},
            {"id": "actual", "label": bilingual("实际", "Actual"),
             "kwh": daily["actual_after"]},
        ],
        "saving": {
            "kwh_per_day": saving["kwh_per_day"],
            "pct": saving["pct"],
            "kwh_per_month": saving["kwh_per_month_projection"],
            "cost_per_month": money(
                saving.get("cost_per_month_projection",
                           saving.get("sgd_per_month_projection")), cur),
            "co2_kg_per_month": saving["co2_kg_per_month_projection"],
        },
        "overall_achievement_pct": result.get("overall_achievement_pct"),
        "per_action": per_action,
        "category_delta": result.get("category_delta", {}),
    }


def _achievement_status(pct) -> str:
    if pct is None:
        return "not_measurable"
    if pct >= 80:
        return "on_track"
    if pct >= 40:
        return "partial"
    return "off_track"


def build_agents(ctx, trace: list[dict] | None = None,
                 comfort_summary: dict | None = None) -> dict:
    """七个专家角色的花名册 + 协作轨迹。"""
    trace = trace or []
    calls_by_role: dict[str, int] = {}
    for entry in trace:
        calls_by_role[entry["role"]] = calls_by_role.get(entry["role"], 0) + 1

    # 舒适守门人不调用外部工具，它作用于规划师的产物；
    # 它的"工作量"= 审查过的动作条数，从舒适审查汇总里取。
    if comfort_summary:
        reviewed = (comfort_summary.get("approved_count", 0)
                    + comfort_summary.get("vetoed_count", 0))
        if reviewed:
            calls_by_role["comfort_guardian"] = reviewed

    agents = []
    for role in sorted(ROLES, key=lambda r: r["order"]):
        agents.append({
            "id": role["id"],
            "order": role["order"],
            "name": role["name"],
            "mission": role["mission"],
            "tools": role["tools"],
            "has_veto": role["veto"],
            "calls_in_last_run": calls_by_role.get(role["id"], 0),
            "status": "active" if calls_by_role.get(role["id"]) else "idle",
            "activity_note": bilingual(
                f"审查了 {calls_by_role['comfort_guardian']} 条候选动作"
                if role["id"] == "comfort_guardian" and calls_by_role.get("comfort_guardian")
                else f"调用工具 {calls_by_role.get(role['id'], 0)} 次",
                f"Reviewed {calls_by_role['comfort_guardian']} candidate actions"
                if role["id"] == "comfort_guardian" and calls_by_role.get("comfort_guardian")
                else f"{calls_by_role.get(role['id'], 0)} tool call(s)"),
        })

    return {
        "count": len(agents),
        "orchestration": bilingual(
            "单编排器 + 七个专职角色：由一个 LLM 循环决定下一个该谁出手，"
            "所有数字由角色对应的确定性工具算出，模型不产生数字。",
            "Single orchestrator, seven specialist roles: one LLM loop decides who acts next; "
            "every number comes from that role's deterministic tool, never from the model.",
        ),
        "agents": agents,
        "trace": trace,
    }


# ===========================================================================
# 组装与写盘
# ===========================================================================

def build_payload(ctx, trace: list[dict] | None = None) -> dict:
    plans = build_plans(ctx)
    return {
        "meta": build_meta(ctx),
        "household": build_household(ctx),
        "baseline": build_baseline(ctx),
        "diagnosis": build_diagnosis(ctx),
        "plans": plans,
        "track": build_track(ctx),
        "agents": build_agents(ctx, trace, plans.get("comfort_summary")),
        "disclaimers": {
            "estimates": bilingual(
                "所有 kWh / 金额 / 碳排数字均由确定性工具计算，可复算可审计；"
                "负载分解为估算，误差见 diagnosis.accuracy。",
                "All kWh / cost / CO2 figures come from deterministic tools and are auditable; "
                "disaggregation is an estimate — see diagnosis.accuracy."),
            "control": bilingual(
                "系统只给建议，不自动控制任何电器；所有动作需用户确认。",
                "Advisory only. No appliance is controlled automatically; "
                "every action requires user confirmation."),
        },
    }


def export_web(ctx, trace: list[dict] | None = None) -> dict:
    """生成整包 + 分段文件 + .js 版本，返回写出的路径清单。"""
    export_cfg = ctx.config.get("export", {})
    out_dir = ctx.root / export_cfg.get("out_dir", "data/web")
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = build_payload(ctx, trace)
    written: list[Path] = []

    full = out_dir / "homeshift_web.json"
    _dump(full, payload)
    written.append(full)

    for section in ("meta", "household", "baseline", "diagnosis", "plans", "track", "agents"):
        path = out_dir / f"{section}.json"
        _dump(path, payload[section])
        written.append(path)

    if export_cfg.get("emit_js", True):
        js_path = out_dir / "homeshift_web.js"
        js_path.write_text(
            "// HomeShift AI —— 由 `python -m homeshift export-web` 自动生成，请勿手工编辑\n"
            "// 静态页面用法： <script src=\"homeshift_web.js\"></script>\n"
            "//               然后读取 window.HOMESHIFT_DATA\n"
            "window.HOMESHIFT_DATA = "
            + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            + ";\n",
            encoding="utf-8",
        )
        written.append(js_path)

    # 字段说明书：给前端队友看的合同
    schema_path = out_dir / "SCHEMA.md"
    schema_path.write_text(_schema_doc(payload), encoding="utf-8")
    written.append(schema_path)

    return {
        "out_dir": str(out_dir),
        "files": [str(p) for p in written],
        "sections_available": {
            k: payload[k].get("available", True)
            for k in ("baseline", "diagnosis", "plans", "track")
        },
    }


def _dump(path: Path, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def _count_rows(path: Path) -> int:
    with open(path, "r", encoding="utf-8") as f:
        return max(0, sum(1 for _ in f) - 1)


def _schema_doc(payload: dict) -> str:
    """自动生成字段说明，保证文档和实际输出永远一致。"""
    lines = [
        "# HomeShift AI 网站数据契约",
        "",
        f"- schema_version: `{payload['meta']['schema_version']}`",
        f"- 生成时间: {payload['meta']['generated_at']}",
        "- 由 `python -m homeshift export-web` 自动生成，**不要手工编辑**",
        "",
        "## 约定",
        "",
        "1. 所有展示文本都是 `{\"zh\": ..., \"en\": ...}`，前端按当前语言取键。",
        "2. 所有金额都是 `{\"value\": 数字, \"display\": \"S$146.08\", \"currency\": \"SGD\"}`，",
        "   前端直接用 `display` 即可，不需要自己拼货币符号。",
        "3. 所有物理量都是 `{\"value\": 数字, \"unit\": \"kWh\", \"display\": \"420 kWh\"}`。",
        "4. 每个分段都有 `available` 布尔字段；为 `false` 时不要渲染该段，",
        "   `reason` 会说明原因（例如计划还没执行满 3 天）。",
        "",
        "## 顶层结构",
        "",
        "| 键 | 对应网站分段 | 说明 |",
        "| --- | --- | --- |",
        "| `meta` | 全局 | 数据来源、地区、币种、电价、碳因子、出处 |",
        "| `household` | 01 Baseline 头部 | 家庭画像、标签、已锁定的舒适规则、目标 |",
        "| `baseline` | 01 Baseline | 月用电、账单、碳排、24 小时曲线、逐日序列、证据清单 |",
        "| `diagnosis` | 02 Diagnosis | 负载分解六大类、关键发现、方法与局限、精度评估 |",
        "| `plans` | 03 Plans | 候选动作、被舒适否决的动作、七天执行清单 |",
        "| `track` | 04 Track | 天气归一化后的实际节省、分动作达成率 |",
        "| `agents` | 七个 agent 展示 | 角色花名册 + 本次运行的协作轨迹 |",
        "",
        "## 分段可用性（本次导出）",
        "",
    ]
    for key in ("baseline", "diagnosis", "plans", "track"):
        avail = payload[key].get("available", True)
        mark = "可用" if avail else f"不可用（{payload[key].get('reason', payload[key].get('status', '-'))}）"
        lines.append(f"- `{key}`: {mark}")

    lines += [
        "",
        "## 前端最少需要读的字段",
        "",
        "```js",
        "const d = window.HOMESHIFT_DATA;",
        "",
        "// 01 Baseline",
        "d.baseline.headline.kwh_this_month.display   // \"420 kWh\"",
        "d.baseline.headline.est_bill.display         // \"S$146.08\"",
        "d.baseline.headline.carbon_kg.display        // \"168.8 kg\"",
        "d.baseline.signature_24h.slots               // 48 个点，画曲线",
        "d.baseline.signature_24h.peak.time           // \"20:30\"",
        "d.household.comfort_rules                    // 已锁定的舒适规则卡片",
        "",
        "// 02 Diagnosis",
        "d.diagnosis.categories                       // 六大类，含占比与月成本",
        "d.diagnosis.findings                         // 前三条关键发现",
        "d.diagnosis.accuracy                         // 分解精度（有真值时才有）",
        "",
        "// 03 Plans",
        "d.plans.candidates                           // 候选动作（selected 标记已选中）",
        "d.plans.vetoed_by_comfort                    // 被舒适约束否决的动作 + 理由",
        "d.plans.seven_day_schedule                   // 七天可勾选清单",
        "",
        "// 04 Track",
        "d.track.comparison_bars                      // 基线 / 若不行动 / 实际 三根柱子",
        "d.track.saving.cost_per_month.display        // 实际月度节省",
        "d.track.per_action                           // 分动作达成率",
        "",
        "// 七个 agent",
        "d.agents.agents                              // 花名册",
        "d.agents.trace                               // 本次运行谁在什么时候做了什么",
        "```",
        "",
        "## 字段变更约定",
        "",
        "后端改字段时会提升 `meta.schema_version`。前端建议加一行判断：",
        "",
        "```js",
        "if (!d.meta.schema_version.startsWith('1.')) console.warn('数据结构有大改动');",
        "```",
    ]
    return "\n".join(lines)
