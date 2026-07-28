"""节能动作模拟器：确定性的“如果做 X 能省多少”计算。

设计原则：所有节省数字必须由这里的规则算出，而不是让大语言模型
凭感觉编——LLM 负责决策与解释，数字必须可复算、可追溯。
每条规则的经验系数都有出处注释，全部可在答辩时讲清楚。

输入：负载分解结果（各类别 kWh/天）+ 用户画像（含舒适约束）+ 电价/碳配置
输出：候选节能动作列表，含 kWh / 当前地区货币 / CO2 三个维度的月度估算
"""

from __future__ import annotations

from .carbon import emission_factor
from .comfort import review_actions
from .tariff import currency, effective_rate

# 空调每调高 1°C 约省 7% 制冷能耗（NEA/新加坡节能宣传常用经验值，线性近似）
AC_SAVING_PER_DEGREE = 0.07
# 储水式热水器 always-on 时，保温损耗约占其总耗电的 40%（本模拟器标定值）
HEATER_STANDBY_SHARE = 0.40
# 温水洗 -> 冷水洗约省 60%（洗衣机大部分能耗用于加热水）
COLD_WASH_SAVING = 0.60
# 智能排插/物理断电可消除约 40% 待机负载
STANDBY_CUT_SHARE = 0.40
# 冰箱除霜、调温、检查门封约省 7%
FRIDGE_TUNE_SHARE = 0.07


def candidate_actions(disagg: dict, profile: dict, config: dict) -> dict:
    """生成候选节能动作。disagg 为 disaggregate() 的返回值。"""
    if "daily_avg_kwh" not in disagg:
        return {"error": "no_disaggregation", "message": "请先完成负载分解"}

    daily = disagg["daily_avg_kwh"]
    rate = effective_rate(config)
    factor = emission_factor(config)
    comfort = profile.get("comfort_preferences", {})
    actions: list[dict] = []

    def add(action_id, title, description, category, kwh_day, comfort_impact, effort, notes=""):
        kwh_month = kwh_day * 30
        actions.append(
            {
                "id": action_id,
                "title": title,
                "description": description,
                "category": category,
                "est_kwh_per_day": round(kwh_day, 2),
                "est_kwh_per_month": round(kwh_month, 1),
                "est_cost_per_month": round(kwh_month * rate, 2),
                "est_sgd_per_month": round(kwh_month * rate, 2),  # 兼容旧字段
                "est_co2_kg_per_month": round(kwh_month * factor, 1),
                "comfort_impact": comfort_impact,
                "effort": effort,
                "notes": notes,
            }
        )

    # 1) 空调：提高设定温度（受舒适约束限制）
    ac_daily = daily.get("aircon", 0.0)
    current_setpoint = profile.get("ac_setpoint", 24)
    max_setpoint = comfort.get("max_ac_setpoint", 26)
    target = min(26, max_setpoint)
    delta = max(0, target - current_setpoint)
    if ac_daily >= 1.0 and delta > 0:
        saving = ac_daily * min(AC_SAVING_PER_DEGREE * delta, 0.30)
        add(
            "ac_setpoint_26",
            f"空调设定 {current_setpoint}°C -> {target}°C，配合风扇助眠",
            f"每调高 1°C 约省 7% 制冷电耗；调至 {target}°C 并开风扇增强体感对流，"
            "不影响入睡舒适度（遵守画像中的舒适约束）。",
            "aircon",
            saving,
            "low",
            "zero_cost",
            f"依据舒适约束：空调不高于 {max_setpoint}°C",
        )

    # 2) 热水器：always-on 改为定时/即用即开
    heater_daily = daily.get("water_heater", 0.0)
    if profile.get("heater_mode") == "always_on" and heater_daily >= 1.0:
        add(
            "heater_timer",
            "储水式热水器改定时加热（早晚各一次）",
            "热水器 24 小时保温的散热损耗约占其耗电 40%；改为洗澡前 30 分钟"
            "定时通电（或加装定时器），热水体验不变。",
            "water_heater",
            heater_daily * HEATER_STANDBY_SHARE,
            "none",
            "low_cost",
            "可用机械定时器（约合 10-20 元）或手动开关",
        )

    # 3) 洗衣：温水改冷水
    laundry_daily = daily.get("laundry", 0.0)
    if profile.get("wash_mode") == "warm" and laundry_daily >= 0.2:
        add(
            "cold_wash",
            "洗衣机改用冷水洗涤程序",
            "洗衣机 80% 以上的电耗用于加热水；日常衣物用冷水程序"
            "配合常规洗衣液即可，衣物清洁度基本不受影响。",
            "laundry",
            laundry_daily * COLD_WASH_SAVING,
            "none",
            "zero_cost",
        )

    # 4) 待机负载：智能排插/物理断电
    standby_daily = daily.get("standby", 0.0)
    if standby_daily >= 0.5:
        add(
            "standby_cut",
            "用排插切断夜间/外出时段的待机负载",
            "机顶盒、电视、充电器等待机功耗 24 小时累积可观；"
            "睡前/出门顺手关排插，或使用带定时的智能排插。",
            "standby",
            standby_daily * STANDBY_CUT_SHARE,
            "none",
            "low_cost",
        )

    # 5) 冰箱：除霜、调温、检查门封
    fridge_daily = daily.get("fridge", 0.0)
    if fridge_daily >= 1.0:
        add(
            "fridge_tune",
            "冰箱保养：除霜、温度调至 4°C/-18°C、检查门封",
            "结霜与过低设定都会增加压缩机负担；一次保养即可持续受益。",
            "fridge",
            fridge_daily * FRIDGE_TUNE_SHARE,
            "none",
            "zero_cost",
        )

    # 6) 错峰洗衣（仅在分时电价下省钱，用于展示电价方案的影响）
    tariff = config["tariff"]
    if laundry_daily >= 0.2:
        if tariff["plan"] == "tou":
            tou = tariff["tou"]
            from .tariff import tou_rates

            peak, off = tou_rates(config)
            shift_day = laundry_daily * (peak - off)
            actions.append(
                {
                    "id": "shift_laundry_offpeak",
                    "title": "洗衣移到 23:00 后的低谷时段",
                    "description": "分时电价下峰谷价差明显，错峰运行洗衣机直接降低电费。",
                    "category": "laundry",
                    "est_kwh_per_day": 0.0,
                    "est_kwh_per_month": 0.0,
                    "est_cost_per_month": round(shift_day * 30, 2),
                    "est_sgd_per_month": round(shift_day * 30, 2),
                    "est_co2_kg_per_month": 0.0,
                    "comfort_impact": "low",
                    "effort": "zero_cost",
                    "notes": "省钱不省电：转移用电时段，同时缓解电网高峰压力",
                }
            )
        else:
            actions.append(
                {
                    "id": "shift_laundry_offpeak",
                    "title": "洗衣移到低谷时段（当前固定费率下不省钱）",
                    "description": "当前为受管制固定电价，错峰不改变电费；"
                    "若改签零售商分时方案，此动作可直接省钱。",
                    "category": "laundry",
                    "est_kwh_per_day": 0.0,
                    "est_kwh_per_month": 0.0,
                    "est_cost_per_month": 0.0,
                    "est_sgd_per_month": 0.0,
                    "est_co2_kg_per_month": 0.0,
                    "comfort_impact": "low",
                    "effort": "zero_cost",
                    "notes": "对电网友好，但当前电价方案下无经济收益",
                }
            )

    actions.sort(key=lambda a: a["est_sgd_per_month"], reverse=True)

    # --- 舒适守门人：有否决权的一道关 ---
    # 被否决的动作不会进入候选列表，但会带着理由保留在 vetoed 里，
    # 让用户看见"系统为保护舒适度放弃了多少钱"。
    review = review_actions(actions, profile)
    actions = review["approved"]
    total_kwh = sum(a["est_kwh_per_month"] for a in actions)
    total_cost = sum(a["est_sgd_per_month"] for a in actions)
    total_co2 = sum(a["est_co2_kg_per_month"] for a in actions)
    return {
        "based_on_period": disagg.get("period"),
        "rate_sgd_per_kwh": rate,
        "emission_factor_kg_per_kwh": factor,
        "actions": actions,
        "comfort_review": {
            "vetoed": review["vetoed"],
            "summary": review["summary"],
        },
        "currency": currency(config)["code"],
        "currency_symbol": currency(config)["symbol"],
        "potential_total_per_month": {
            "kwh": round(total_kwh, 1),
            "cost": round(total_cost, 2),
            "sgd": round(total_cost, 2),  # 兼容旧字段
            "co2_kg": round(total_co2, 1),
        },
    }
