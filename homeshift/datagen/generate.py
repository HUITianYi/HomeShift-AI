"""合成数据生成器：模拟一个新加坡 HDB 4 房式家庭的智能电表数据。

为什么要合成数据？
- 课程演示无法接入真实电表；真实接口预留在 connectors/meter_api.py。
- 合成数据带有“分电器真值”（ground truth），可以定量评估负载分解
  算法的精度（eval-disagg 命令）——这是真实 NILM 研究做不到的奢侈。

模拟要点（对应新加坡热带气候与典型作息）：
- 天气：日最高温 ~32°C、夜间 ~27°C，正弦曲线插值到半小时。
- 空调：夜间整晚开（主卧+次卧），功率随室外温度升高而上升；
  周末下午客厅空调概率性开启。这是账单的最大头。
- 热水器：储水式 3kW 常年通电——早晚洗澡加热 + 全天保温耗损
  （这是刻意埋下的、等待智能体“诊断”出来的低效点）。
- 洗衣机：每周 4 次温水洗（另一个可优化点）。
- 冰箱/待机/照明/厨房/电视：常规基线。

simulate-week 时可传入 plan_effects，把节能动作的效果（按每日执行概率）
注入未来 7 天数据，供追踪/复盘环节展示真实的前后对比。
"""

from __future__ import annotations

import math
import random
from datetime import date, datetime, time, timedelta

from ..domain.appliances import APPLIANCES

APPLIANCE_KEYS = list(APPLIANCES.keys())

# 节能动作 -> 对生成器参数的影响（simulate-week 使用）
# 与 domain/simulate.py 中动作定义的 id 一一对应。
ACTION_EFFECT_KEYS = {
    "ac_setpoint_26": "ac_factor",        # 空调 24->26°C：能耗 x0.86（约 7%/°C）
    "heater_timer": "heater_timer",       # 热水器改定时：去掉全天保温损耗
    "cold_wash": "cold_wash",             # 冷水洗衣：单次 0.9 -> 0.35 kWh
    "standby_cut": "standby_cut",         # 排插断待机：待机负载下降约 40%
    "fridge_tune": "fridge_factor",       # 冰箱除霜/调温：约 -7%
    "shift_laundry_offpeak": "shift_laundry",  # 错峰洗衣：仅改变用电时段
}


def _daily_temps(rng: random.Random) -> tuple[float, float]:
    tmax = min(35.5, max(29.5, rng.gauss(32.3, 1.1)))
    tmin = tmax - min(7.5, max(4.0, rng.gauss(5.6, 0.7)))
    return tmax, tmin


def _slot_temp(tmax: float, tmin: float, hour: float) -> float:
    # 最高温出现在 15:00，最低温在凌晨 03:00（余弦插值）
    phase = (hour - 15.0) / 24.0 * 2 * math.pi
    return (tmax + tmin) / 2 + (tmax - tmin) / 2 * math.cos(phase)


def _day_effects(plan_effects: dict | None, rng: random.Random) -> dict:
    """把计划动作按“每日执行概率”转成当天生效的生成器参数。"""
    eff = {
        "ac_factor": 1.0,
        "heater_timer": False,
        "cold_wash": False,
        "standby_cut": False,
        "fridge_factor": 1.0,
        "shift_laundry": False,
    }
    if not plan_effects:
        return eff
    for action_id, adherence in plan_effects.items():
        key = ACTION_EFFECT_KEYS.get(action_id)
        if key is None or rng.random() > adherence:
            continue  # 今天没执行这个动作（模拟真实生活的不完美）
        if key == "ac_factor":
            eff["ac_factor"] = 0.86
        elif key == "fridge_factor":
            eff["fridge_factor"] = 0.93
        else:
            eff[key] = True
    return eff


def _simulate_day(
    day: date, rng: random.Random, plan_effects: dict | None
) -> tuple[list[dict], list[tuple[datetime, float]]]:
    """返回 (48 个半小时槽的分电器 kWh, 天气行)。"""
    tmax, tmin = _daily_temps(rng)
    is_weekend = day.weekday() >= 5
    eff = _day_effects(plan_effects, rng)
    use_living_ac = is_weekend and rng.random() < 0.65
    laundry_day = day.weekday() in (0, 2, 4, 6)  # 周一/三/五/日
    laundry_start_slot = 45 if eff["shift_laundry"] else 40  # 22:30 错峰 vs 20:00

    slots: list[dict] = []
    weather_rows: list[tuple[datetime, float]] = []
    for slot in range(48):
        hour = slot * 0.5
        ts = datetime.combine(day, time(int(hour), 30 if slot % 2 else 0))
        temp = _slot_temp(tmax, tmin, hour)
        weather_rows.append((ts, temp))

        r = {key: 0.0 for key in APPLIANCE_KEYS}

        # 冰箱：小基线 + 轻微温度相关
        r["fridge"] = max(
            0.015,
            (0.026 + 0.0015 * max(0.0, temp - 27) + rng.uniform(-0.003, 0.003))
            * eff["fridge_factor"],
        )

        # 待机负载：路由器、机顶盒、充电器等
        standby_base = 0.010 if eff["standby_cut"] else 0.017
        r["standby"] = max(0.004, standby_base + rng.uniform(-0.002, 0.002))

        # 空调（夜间睡眠时段），功率随室外温度上升
        if hour >= 22.5 or hour < 7.0:
            kw = max(0.0, 0.55 + 0.06 * max(0.0, temp - 26.0) + rng.gauss(0, 0.05))
            r["aircon_master"] = kw * 0.5 * eff["ac_factor"]
        if hour >= 22.0 or hour < 6.5:
            kw = max(0.0, 0.45 + 0.05 * max(0.0, temp - 26.0) + rng.gauss(0, 0.04))
            r["aircon_kids"] = kw * 0.5 * eff["ac_factor"]
        if use_living_ac and 13.5 <= hour < 17.0:
            kw = max(0.0, 0.95 + 0.08 * max(0.0, temp - 26.0) + rng.gauss(0, 0.07))
            r["aircon_living"] = kw * 0.5 * eff["ac_factor"]

        # 热水器：早晚洗澡加热脉冲
        if slot in (13, 14):  # 06:30 / 07:00
            r["water_heater"] += rng.uniform(0.30, 0.40)
        if slot in (42, 43):  # 21:00 / 21:30
            r["water_heater"] += rng.uniform(0.30, 0.40)
        # 保温损耗：always_on 时全天随机补热；改定时后仅使用时段附近少量补热
        reheat_slots_ok = True if not eff["heater_timer"] else slot in (12, 13, 14, 15, 41, 42, 43, 44)
        if reheat_slots_ok and rng.random() < 0.196:
            r["water_heater"] += rng.uniform(0.07, 0.11)

        # 洗衣机
        if laundry_day and slot == laundry_start_slot:
            cycle = rng.uniform(0.30, 0.40) if eff["cold_wash"] else rng.uniform(0.80, 1.00)
            r["washing_machine"] += cycle * 0.65
        if laundry_day and slot == laundry_start_slot + 1:
            cycle = rng.uniform(0.30, 0.40) if eff["cold_wash"] else rng.uniform(0.80, 1.00)
            r["washing_machine"] += cycle * 0.35

        # 照明
        if 18.5 <= hour < 23.5:
            r["lighting"] = (0.11 + rng.uniform(-0.02, 0.02)) * 0.5
        elif 6.5 <= hour < 7.5:
            r["lighting"] = 0.05 * 0.5

        # 电视/娱乐
        if 19.0 <= hour < 23.0:
            r["tv_media"] = (0.11 + rng.uniform(-0.02, 0.02)) * 0.5
        if is_weekend and 14.0 <= hour < 17.0:
            r["tv_media"] += 0.08 * 0.5

        # 厨房（做饭/烧水脉冲）
        if slot == 14:  # 07:00 早餐
            r["kitchen"] += rng.uniform(0.20, 0.30)
        if slot in (36, 37):  # 18:00-19:00 晚餐
            r["kitchen"] += rng.uniform(0.28, 0.40)
        if is_weekend and slot == 24:  # 周末午餐
            r["kitchen"] += rng.uniform(0.25, 0.35)

        # 风扇（晚间未开空调的公共区域）
        if 19.0 <= hour < 22.5:
            r["fans"] = 0.045 * 0.5

        slots.append({"timestamp": ts, **{key: round(value, 4) for key, value in r.items()}})
    return slots, weather_rows


def simulate_days(
    start: date,
    days: int,
    seed: int,
    plan_effects: dict | None = None,
) -> tuple[list[tuple[datetime, float]], list[tuple[datetime, float]], list[dict]]:
    """模拟 [start, start+days) 的数据。

    plan_effects: {action_id: 每日执行概率} —— simulate-week 时传入。
    返回 (电表行, 天气行, 分电器真值行)。
    """
    rng = random.Random(seed)
    usage_rows: list[tuple[datetime, float]] = []
    weather_rows: list[tuple[datetime, float]] = []
    truth_rows: list[dict] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        slots, day_weather = _simulate_day(day, rng, plan_effects)
        weather_rows.extend(day_weather)
        for row in slots:
            total = sum(value for key, value in row.items() if key != "timestamp")
            usage_rows.append((row["timestamp"], round(total, 4)))
            truth_rows.append(row)
    return usage_rows, weather_rows, truth_rows


def _write_synthetic_provenance(ctx, summary: dict) -> None:
    """合成数据也要记出处，否则切回合成后 status 仍显示上一次的真实数据集。"""
    import json
    from datetime import datetime

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_kind": "synthetic",
        "dataset": {
            "id": "synthetic",
            "title": "HomeShift 合成数据生成器",
            "license": "本项目自有",
            "citation": "由 homeshift/datagen/generate.py 按新加坡气候与 HDB 家庭作息生成",
        },
        "window": {
            "start": summary.get("start"), "end": summary.get("end"),
            "days": summary.get("days"), "completeness_pct": 100.0,
        },
        "weather": {"source": "synthetic", "note": "与用电数据一同生成，物理上自洽"},
        "known_limitations": [
            "这是合成数据，用于无网络时的演示；结论不代表任何真实家庭",
            "自带分电器真值，因此可以定量检验负载分解算法（真实家庭没有这个条件）",
        ],
    }
    ctx.data_dir.mkdir(parents=True, exist_ok=True)
    with open(ctx.data_dir / "provenance.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


def init_dataset(ctx, days: int | None = None, seed: int | None = None, end: date | None = None) -> dict:
    """生成基线数据集（覆盖写入）。返回摘要信息。"""
    cfg = ctx.config["datagen"]
    days = days or cfg["days"]
    seed = seed if seed is not None else cfg["seed"]
    end = end or (date.today() - timedelta(days=1))
    start = end - timedelta(days=days - 1)

    # 覆盖旧数据
    for path in (ctx.usage.usage_path, ctx.usage.weather_path, ctx.usage.groundtruth_path):
        if path.exists():
            path.unlink()

    usage_rows, weather_rows, truth_rows = simulate_days(start, days, seed)
    ctx.usage.append_rows(usage_rows, weather_rows, truth_rows, APPLIANCE_KEYS)

    total = sum(kwh for _, kwh in usage_rows)
    summary = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "total_kwh": round(total, 1),
        "avg_daily_kwh": round(total / days, 2),
    }
    # 覆盖出处文件：否则从真实数据切回合成后，status 仍会显示上一次的数据集
    _write_synthetic_provenance(ctx, summary)
    return summary


def append_week_with_plan(ctx, plan: dict, adherence: float, seed_offset: int = 0) -> dict:
    """在现有数据末尾追加 7 天、注入当前计划动作效果（simulate-week）。"""
    last = ctx.usage.last_date()
    if last is None:
        raise RuntimeError("尚无基线数据，请先运行 init")
    start = last + timedelta(days=1)
    action_ids = [action["id"] for action in plan.get("actions", [])]
    plan_effects = {action_id: adherence for action_id in action_ids}
    seed = ctx.config["datagen"]["seed"] + 1000 + plan.get("version", 1) + seed_offset
    usage_rows, weather_rows, truth_rows = simulate_days(start, 7, seed, plan_effects)
    ctx.usage.append_rows(usage_rows, weather_rows, truth_rows, APPLIANCE_KEYS)
    total = sum(kwh for _, kwh in usage_rows)
    return {
        "start": start.isoformat(),
        "end": (start + timedelta(days=6)).isoformat(),
        "days": 7,
        "avg_daily_kwh": round(total / 7, 2),
        "actions_applied": action_ids,
        "adherence": adherence,
    }
