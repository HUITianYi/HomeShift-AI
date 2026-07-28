"""负载分解（NILM-lite）：只用总电表读数 + 天气，估算分类别用电。

这是“诊断高耗能原因”的核心。真实场景中家庭只有一块总电表，
必须靠启发式/机器学习把总量拆到电器类别。这里实现一套可解释的
启发式（每一步都能讲清楚原理），并用 eval-disagg 命令对照
合成数据的分电器真值定量评估误差。

启发式思路（按新加坡家庭作息设计）：
1. 基线负载 = 工作日白天(09:00-16:00，家中无人)的负载下限
   -> 冰箱 + 待机（按典型功率比例 58:42 拆分）
2. 热水器保温损耗 = 工作日白天高于基线的小幅超额（储水式热水器
   always-on 的特征信号），推广到全天
3. 夜间(22:00-07:30) 扣除基线与保温后的剩余 -> 空调
4. 周末下午高于工作日同时段典型值的部分 -> 空调（客厅）
5. 早晚洗澡时段的短脉冲 -> 热水器加热
6. 晚间洗衣时段的尖峰 -> 洗衣机
7. 其余 -> 照明/厨房/娱乐等（other）

已知局限（诚实声明，也是答辩要点）：
- 夜间热水器补热会被部分误记为空调（约 0.2-0.4 kWh/天）
- 依赖“白天无人”假设，居家办公家庭需要改用其他锚点
"""

from __future__ import annotations

from datetime import date, datetime

CATEGORIES = ["aircon", "water_heater", "fridge", "standby", "laundry", "other"]

# 关键时段（slot = 半小时序号，0 = 00:00）
DAYTIME_SLOTS = range(18, 32)          # 09:00 - 16:00
NIGHT_AC_SLOTS = [s for s in range(48) if s >= 44 or s < 15]  # 22:00 - 07:30
WEEKEND_AC_SLOTS = range(26, 35)       # 13:00 - 17:30
SHOWER_SLOTS = (13, 14, 42, 43)        # 06:30/07:00 与 21:00/21:30
LAUNDRY_SLOTS = (39, 40, 41, 45, 46)   # 19:30-21:00 及错峰 22:30-23:30
EVENING_ALLOWANCE = 0.12               # 晚间照明+电视的每槽典型 kWh（用于扣减）


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(pct / 100 * (len(ordered) - 1)))))
    return ordered[idx]


def _slot_of(ts: datetime) -> int:
    return ts.hour * 2 + (1 if ts.minute >= 30 else 0)


def _slots_from_hours(start_hour: float, end_hour: float) -> list[int]:
    """把 [start, end) 小时区间转成半小时槽位序号，支持跨零点。"""
    start = int(start_hour * 2)
    end = int(end_hour * 2)
    if start <= end:
        return list(range(start, end))
    return [s for s in range(48) if s >= start or s < end]


def disaggregate(
    rows: list[tuple[datetime, float]],
    weather: dict[datetime, float] | None = None,
    config: dict | None = None,
) -> dict:
    """对一段半小时粒度电表数据做负载分解。

    config 可选，用于覆盖作息锚点（不同家庭/地区的"白天无人"时段不同）。
    不传则使用面向新加坡 HDB 双职工家庭的默认值。

    返回 {period, days, daily_avg: {类别: kWh/天}, share_pct, daily_series, notes}
    """
    cfg = (config or {}).get("disaggregation", {})
    daytime_slots = _slots_from_hours(
        cfg.get("away_start_hour", 9), cfg.get("away_end_hour", 16))
    night_slots = _slots_from_hours(
        cfg.get("night_start_hour", 22), cfg.get("night_end_hour", 7.5))
    fridge_share = cfg.get("fridge_share_of_baseline", 0.58)
    if not rows:
        return {"error": "no_data", "message": "该时段没有用电数据"}

    # 组织为 {日期: {slot: kwh}}
    by_day: dict[date, dict[int, float]] = {}
    for ts, kwh in rows:
        by_day.setdefault(ts.date(), {})[_slot_of(ts)] = kwh
    days = sorted(by_day.keys())

    weekdays = [d for d in days if d.weekday() < 5]
    anchor_days = weekdays if len(weekdays) >= 3 else days

    # --- 1. 基线负载（冰箱 + 待机） ---
    daytime_values = [
        by_day[d][s] for d in anchor_days for s in daytime_slots if s in by_day[d]
    ]
    baseline_slot = _percentile(daytime_values, 10)  # kWh / 半小时

    # --- 2. 热水器保温损耗率（工作日白天超额的均值，限幅防止误吸收异常） ---
    excesses = [
        min(0.25, max(0.0, by_day[d][s] - baseline_slot))
        for d in anchor_days
        for s in daytime_slots
        if s in by_day[d]
    ]
    heater_standby_slot = sum(excesses) / len(excesses) if excesses else 0.0

    # 工作日各 slot 的“干净典型值”（25 分位，避开洗衣/加班日污染），
    # 用于周末下午的空调识别
    weekday_typical: dict[int, float] = {}
    for s in range(48):
        vals = [by_day[d][s] for d in anchor_days if s in by_day[d]]
        weekday_typical[s] = _percentile(vals, 25) if vals else baseline_slot

    daily_series: list[dict] = []
    for d in days:
        slots = by_day[d]
        cats = {c: 0.0 for c in CATEGORIES}
        day_total = sum(slots.values())

        for s, kwh in slots.items():
            base_take = min(kwh, baseline_slot)
            remaining = kwh - base_take
            heater_take = min(remaining, heater_standby_slot)
            remaining -= heater_take
            cats["fridge"] += base_take * fridge_share
            cats["standby"] += base_take * (1 - fridge_share)
            cats["water_heater"] += heater_take

            # 洗澡加热脉冲（优先于夜间空调归因，减少互相污染）
            if s in SHOWER_SLOTS and remaining > 0:
                allowance = EVENING_ALLOWANCE if s in (42, 43) else 0.0
                shower_take = min(max(0.0, remaining - allowance), 0.45)
                cats["water_heater"] += shower_take
                remaining -= shower_take

            # 夜间剩余 -> 空调
            if s in night_slots and remaining > 0:
                cats["aircon"] += remaining
                remaining = 0.0

            # 周末下午高于工作日典型值 -> 空调（客厅）
            if d.weekday() >= 5 and s in WEEKEND_AC_SLOTS and remaining > 0:
                extra = min(remaining, max(0.0, kwh - weekday_typical.get(s, baseline_slot)))
                if extra > 0.08:
                    cats["aircon"] += extra
                    remaining -= extra

            # 晚间洗衣尖峰 -> 洗衣机
            if s in LAUNDRY_SLOTS and remaining > 0:
                spike = max(0.0, remaining - EVENING_ALLOWANCE)
                if spike > 0.20:
                    take = min(spike, 0.80)
                    cats["laundry"] += take
                    remaining -= take

        assigned = sum(cats.values())
        cats["other"] = max(0.0, day_total - assigned)
        daily_series.append(
            {"date": d.isoformat(), "total_kwh": round(day_total, 2)}
            | {c: round(v, 2) for c, v in cats.items()}
        )

    n = len(days)
    daily_avg = {
        c: round(sum(row[c] for row in daily_series) / n, 2) for c in CATEGORIES
    }
    total_avg = round(sum(row["total_kwh"] for row in daily_series) / n, 2)
    share = {
        c: round(100 * daily_avg[c] / total_avg, 1) if total_avg else 0.0
        for c in CATEGORIES
    }

    return {
        "period": {"start": days[0].isoformat(), "end": days[-1].isoformat()},
        "days": n,
        "avg_daily_total_kwh": total_avg,
        "daily_avg_kwh": daily_avg,
        "share_pct": share,
        "daily_series": daily_series,
        "anchors": {
            "away_hours": f"{cfg.get('away_start_hour', 9)}:00-{cfg.get('away_end_hour', 16)}:00",
            "night_hours": f"{cfg.get('night_start_hour', 22)}:00-{cfg.get('night_end_hour', 7.5)}:00",
            "fridge_share_of_baseline": fridge_share,
        },
        "method_notes": [
            f"基线负载取工作日白天({cfg.get('away_start_hour', 9)}:00-"
            f"{cfg.get('away_end_hour', 16)}:00)负载 10 分位数，"
            f"按 {fridge_share:.0%}:{1 - fridge_share:.0%} 拆为冰箱/待机",
            "热水器保温损耗由工作日白天超额均值估计并推广到全天",
            f"夜间({cfg.get('night_start_hour', 22)}:00 起)扣除基线与保温后的剩余归为温控负载",
            "已知局限：夜间热水器补热可能被误记为温控负载（约 0.2-0.4 kWh/天）",
            "已知局限：依赖'白天无人在家'假设；居家办公家庭需调整 config.disaggregation 的锚点",
        ],
    }


def evaluate_against_truth(
    disagg: dict,
    truth_rows: list[dict],
    category_map: dict | None = None,
) -> dict:
    """用分电器真值评估分解精度。

    category_map 用于真实数据集：不同数据集的分表口径不同
    （例如 UCI 的 sub_metering_2 把冰箱和洗衣机混在一起），
    映射关系由 data/provenance.json 提供，而不是写死在代码里。
    """
    from .appliances import category_of

    if not truth_rows or "daily_series" not in disagg:
        return {"error": "no_truth"}

    def to_category(key: str) -> str:
        if category_map and key in category_map:
            return category_map[key]
        return category_of(key)

    # 真值按天聚合到类别
    truth_daily: dict[str, dict[str, float]] = {}
    for row in truth_rows:
        d = row["timestamp"].date().isoformat()
        day = truth_daily.setdefault(d, {c: 0.0 for c in CATEGORIES})
        for key, value in row.items():
            if key == "timestamp":
                continue
            cat = to_category(key)
            day[cat] = day.get(cat, 0.0) + value

    est_days = {row["date"]: row for row in disagg["daily_series"]}
    common = sorted(set(est_days) & set(truth_daily))
    if not common:
        return {"error": "no_overlap"}

    result = {"days": len(common), "per_category": {}}
    for c in CATEGORIES:
        errors = [abs(est_days[d][c] - truth_daily[d][c]) for d in common]
        truth_avg = sum(truth_daily[d][c] for d in common) / len(common)
        est_avg = sum(est_days[d][c] for d in common) / len(common)
        result["per_category"][c] = {
            "truth_avg_kwh_day": round(truth_avg, 2),
            "est_avg_kwh_day": round(est_avg, 2),
            "mae_kwh_day": round(sum(errors) / len(errors), 2),
        }
    return result
