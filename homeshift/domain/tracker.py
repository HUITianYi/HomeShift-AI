"""效果追踪：计划执行后，实际省了多少？

关键设计：天气归一化。新加坡的空调用电与室外温度强相关，
直接对比前后两周的总电量会把“天气变凉”误当成“节能有效”。
因此对空调部分按制冷度时（CDH, Cooling Degree Hours, 基准 26°C）
缩放出“若无任何动作、在新天气下的预期用电”，再与实际用电相减，
得到真正归因于节能动作的节省。

这也是复盘（review）与周报的数据来源。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .carbon import emission_factor
from .disaggregate import CATEGORIES, disaggregate
from .tariff import effective_rate

# 动作 -> 负载类别（用于分动作归因）
ACTION_CATEGORY = {
    "ac_setpoint_26": "aircon",
    "heater_timer": "water_heater",
    "cold_wash": "laundry",
    "standby_cut": "standby",
    "fridge_tune": "fridge",
}


def cooling_degree_hours(
    weather: dict[datetime, float], start: date, end: date, base_c: float = 26.0
) -> float:
    """[start, end] 期间的日均制冷度时（CDH）。

    热带地区用 26°C 基准；温带地区应传入更低的基准（如 18°C），
    此时它同时反映夏季制冷需求。基准值由 config.disaggregation.cdh_base_c 控制。
    """
    total = 0.0
    days: set[date] = set()
    for ts, temp in weather.items():
        if start <= ts.date() <= end:
            total += max(0.0, temp - base_c) * 0.5  # 半小时粒度
            days.add(ts.date())
    return round(total / len(days), 2) if days else 0.0


def thermal_degree_hours(
    weather: dict[datetime, float], start: date, end: date,
    cool_base_c: float = 26.0, heat_base_c: float = 15.0,
) -> float:
    """冷+热度时之和：温带地区冬夏都有温控负载，只看 CDH 会低估相关性。"""
    total = 0.0
    days: set[date] = set()
    for ts, temp in weather.items():
        if start <= ts.date() <= end:
            total += (max(0.0, temp - cool_base_c) + max(0.0, heat_base_c - temp)) * 0.5
            days.add(ts.date())
    return round(total / len(days), 2) if days else 0.0


def _weather_coverage(weather: dict, start: date, end: date) -> float:
    """该时段实际拿到的气温点数 / 应有的半小时点数。"""
    days = (end - start).days + 1
    expected = max(1, days * 48)
    got = sum(1 for ts in weather if start <= ts.date() <= end)
    return min(1.0, got / expected)


def _reliability(pct, planned: float, actual: float) -> str:
    """分动作归因的可信度判定。"""
    if pct is None:
        return "not_measurable"
    if planned < 0.15:
        return "low_signal"          # 预期节省太小，淹没在分解误差里
    if pct > 250:
        return "implausible_high"    # 远超预期，几乎肯定是归类误差
    if pct < -50:
        return "implausible_low"
    return "ok"


def track_progress(ctx) -> dict:
    """对比基线期与计划执行期，输出节省与分动作达成率。"""
    plan = ctx.store.get_active_plan()
    if plan is None:
        return {"status": "no_plan", "message": "尚未制定节能计划，请先运行 plan"}

    baseline = plan["baseline"]
    base_start = date.fromisoformat(baseline["start"])
    base_end = date.fromisoformat(baseline["end"])
    after_start = base_end + timedelta(days=1)
    last = ctx.usage.last_date()
    if last is None or last < after_start + timedelta(days=2):
        return {
            "status": "insufficient_data",
            "message": "计划生效后的数据不足 3 天，无法评估。"
            "（演示环境可运行 simulate-week 快进一周）",
        }
    after_end = last
    if (after_end - after_start).days > 6:
        after_start = after_end - timedelta(days=6)  # 只看最近 7 天

    weather = ctx.usage.load_weather()
    before_rows = ctx.usage.rows_between(base_start, base_end)
    after_rows = ctx.usage.rows_between(after_start, after_end)

    before_days = max(1, (base_end - base_start).days + 1)
    after_days = max(1, (after_end - after_start).days + 1)
    before_daily = sum(kwh for _, kwh in before_rows) / before_days
    after_daily = sum(kwh for _, kwh in after_rows) / after_days

    disagg_before = disaggregate(before_rows, weather, ctx.config)
    disagg_after = disaggregate(after_rows, weather, ctx.config)

    # --- 天气归一化 ---
    disagg_cfg = ctx.config.get("disaggregation", {})
    base_c = disagg_cfg.get("cdh_base_c", 26.0)
    climate = ctx.config.get("region", {}).get("climate", "tropical")
    degree_fn = cooling_degree_hours if climate == "tropical" else thermal_degree_hours

    # 天气覆盖率：两个时期都必须有足够的气温数据，归一化才成立。
    # 否则会出现"基线期 CDH=0、执行期 CDH=275"这种把缺数据当成天气突变的荒谬结果。
    cover_before = _weather_coverage(weather, base_start, base_end)
    cover_after = _weather_coverage(weather, after_start, after_end)
    MIN_COVERAGE = 0.5
    normalization_ok = cover_before >= MIN_COVERAGE and cover_after >= MIN_COVERAGE

    cdh_before = degree_fn(weather, base_start, base_end, base_c)
    cdh_after = degree_fn(weather, after_start, after_end, base_c)
    ac_before = disagg_before["daily_avg_kwh"]["aircon"]

    if normalization_ok and cdh_before > 0:
        expected_ac_after = ac_before * (cdh_after / cdh_before)
        normalization_note = (
            f"温控类用电按度时(基准{base_c}°C)归一化，已剔除气温变化的影响")
    else:
        # 退回到"不做归一化"的朴素对比，并明确告诉用户结论的局限
        expected_ac_after = ac_before
        if not normalization_ok:
            normalization_note = (
                f"天气数据覆盖不足（基线期 {cover_before:.0%}、执行期 {cover_after:.0%}），"
                "本次未做天气归一化。下面的节省数字包含了气温变化的影响，请谨慎解读。")
        else:
            normalization_note = "基线期无制冷需求，无需归一化"

    expected_daily_no_action = before_daily - ac_before + expected_ac_after

    saving_daily = expected_daily_no_action - after_daily
    saving_pct = 100 * saving_daily / expected_daily_no_action if expected_daily_no_action else 0.0

    planned_daily = sum(a.get("est_kwh_per_day", 0.0) for a in plan.get("actions", []))
    overall_achievement = saving_daily / planned_daily if planned_daily > 0 else None

    # --- 分类别变化与分动作归因 ---
    category_delta = {}
    for c in CATEGORIES:
        b = disagg_before["daily_avg_kwh"][c]
        a = disagg_after["daily_avg_kwh"][c]
        expected = b
        if c == "aircon":
            expected = expected_ac_after  # 空调按天气归一化后的预期
        category_delta[c] = {
            "before_kwh_day": round(b, 2),
            "after_kwh_day": round(a, 2),
            "saving_kwh_day": round(expected - a, 2),
        }

    per_action = []
    for action in plan.get("actions", []):
        cat = ACTION_CATEGORY.get(action["id"])
        entry = {
            "id": action["id"],
            "title": action["title"],
            "planned_kwh_day": action.get("est_kwh_per_day", 0.0),
        }
        if cat:
            actual = category_delta[cat]["saving_kwh_day"]
            planned = action.get("est_kwh_per_day", 0.0)
            entry["actual_kwh_day"] = actual
            pct = round(100 * actual / planned, 0) if planned > 0 else None
            entry["achievement_pct"] = pct
            # 可信度：负载分解本身有误差，类别越小、偏差越离谱，越不该当成"执行得好"。
            # 达成率 300% 通常不是用户超额完成，而是分解把别的负载算进了这一类。
            entry["reliability"] = _reliability(pct, planned, actual)
            if entry["reliability"] != "ok":
                entry["reliability_note"] = (
                    "该动作的实际节省超出预期过多，更可能是负载分解的归类误差，"
                    "而不是真的省了这么多；请以总体节省为准。"
                    if entry["reliability"] == "implausible_high"
                    else "该类别的日均用电很小，分解误差相对占比大，归因不稳定。"
                )
        else:
            entry["actual_kwh_day"] = None
            entry["achievement_pct"] = None
            entry["note"] = "该动作不改变用电量（如错峰），以电费口径评估"
        per_action.append(entry)

    rate = effective_rate(ctx.config)
    factor = emission_factor(ctx.config)
    return {
        "status": "ok",
        "plan_version": plan["version"],
        "baseline_period": {"start": base_start.isoformat(), "end": base_end.isoformat()},
        "after_period": {"start": after_start.isoformat(), "end": after_end.isoformat()},
        "weather_normalization": {
            "cdh_before_per_day": cdh_before,
            "cdh_after_per_day": cdh_after,
            "applied": normalization_ok and cdh_before > 0,
            "metric": "CDH" if climate == "tropical" else "CDH+HDH",
            "base_c": base_c,
            "coverage_before_pct": round(100 * cover_before, 1),
            "coverage_after_pct": round(100 * cover_after, 1),
            "note": normalization_note,
        },
        "daily_kwh": {
            "baseline": round(before_daily, 2),
            "expected_no_action": round(expected_daily_no_action, 2),
            "actual_after": round(after_daily, 2),
        },
        "saving": {
            "kwh_per_day": round(saving_daily, 2),
            "pct": round(saving_pct, 1),
            "kwh_per_month_projection": round(saving_daily * 30, 1),
            "cost_per_month_projection": round(saving_daily * 30 * rate, 2),
            "sgd_per_month_projection": round(saving_daily * 30 * rate, 2),  # 兼容旧字段
            "co2_kg_per_month_projection": round(saving_daily * 30 * factor, 1),
        },
        "planned_saving_kwh_per_day": round(planned_daily, 2),
        "overall_achievement_pct": (
            round(100 * overall_achievement, 0) if overall_achievement is not None else None
        ),
        "category_delta": category_delta,
        "per_action": per_action,
    }
