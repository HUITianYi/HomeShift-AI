"""舒适约束校验（Comfort Guardian 角色的执行体）。

产品口号是 "Cut bills, not comfort"。要让这句话不只是标语，就必须有一个
地方**真的会拒绝**某些本来很省钱的动作。这个模块就是那个地方。

每条约束都做成显式规则，输出三种判定：
  approved  —— 通过，可以推荐给用户
  adjusted  —— 参数被收紧后才通过（例如空调只能调到 25°C 而不是 26°C）
  vetoed    —— 否决，不会出现在给用户的计划里

关键设计：被否决的动作**不会被悄悄删掉**，而是带着理由保留在
plans.vetoed 里，导出给网站展示。让用户看见"系统为你放弃了多少钱"，
比只看见省了多少钱更能建立信任——这也是答辩时值得强调的一点。
"""

from __future__ import annotations

# 每个动作在什么条件下会被舒适约束干预
COMFORT_RULES: dict[str, dict] = {
    "ac_setpoint_26": {
        "constraint_key": "max_ac_setpoint",
        "kind": "thermal",
        "check": "setpoint_ceiling",
        "explain_zh": "空调目标温度不得高于用户设定的上限",
        "explain_en": "AC target must not exceed the household's locked ceiling",
    },
    "heater_timer": {
        "constraint_key": "hot_water_always_available",
        "kind": "convenience",
        "check": "boolean_block",
        "explain_zh": "若用户要求随时有热水，则不能改为定时加热",
        "explain_en": "Blocked if the household requires hot water on demand",
    },
    "cold_wash": {
        "constraint_key": "requires_warm_wash",
        "kind": "hygiene",
        "check": "boolean_block",
        "explain_zh": "若家中有婴儿衣物或医疗需求，则保留温水洗",
        "explain_en": "Blocked if warm wash is required for hygiene reasons",
    },
    "standby_cut": {
        "constraint_key": "always_on_devices",
        "kind": "availability",
        "check": "device_exception",
        "explain_zh": "医疗设备、安防、居家办公网络等必须持续供电",
        "explain_en": "Medical, security and WFH network devices must stay powered",
    },
    "shift_laundry_offpeak": {
        "constraint_key": "quiet_hours",
        "kind": "noise",
        "check": "quiet_hours_block",
        "explain_zh": "错峰时段若落在静音时段内（如组屋夜间），不建议运行洗衣机",
        "explain_en": "Blocked when the off-peak window falls inside quiet hours",
    },
}


def _verdict(status: str, reason_zh: str, reason_en: str, rule: str | None = None) -> dict:
    return {
        "status": status,          # approved | adjusted | vetoed
        "rule": rule,
        "reason": {"zh": reason_zh, "en": reason_en},
    }


def review_action(action: dict, profile: dict) -> dict:
    """对单个候选动作做舒适审查，返回判定。"""
    comfort = profile.get("comfort_preferences") or {}
    action_id = action.get("id", "")
    rule = COMFORT_RULES.get(action_id)

    if rule is None:
        return _verdict(
            "approved",
            "该动作不涉及已登记的舒适约束",
            "No registered comfort constraint applies",
        )

    check = rule["check"]
    key = rule["constraint_key"]

    # --- 空调温度上限 ---
    if check == "setpoint_ceiling":
        ceiling = comfort.get("max_ac_setpoint")
        current = profile.get("ac_setpoint")
        if ceiling is None or current is None:
            return _verdict("approved", "未设定空调温度上限，按默认放行",
                            "No AC ceiling set; approved by default", action_id)
        if ceiling <= current:
            return _verdict(
                "vetoed",
                f"用户设定空调不得高于 {ceiling}°C，而当前已是 {current}°C，"
                "再调高会突破舒适底线",
                f"Ceiling {ceiling}°C already reached at {current}°C; raising further "
                "would break the comfort floor",
                action_id,
            )
        if ceiling < 26:
            return _verdict(
                "adjusted",
                f"目标温度已从 26°C 收紧到 {ceiling}°C，以遵守用户的舒适约束"
                f"（{comfort.get('notes', '')}）",
                f"Target tightened from 26°C to {ceiling}°C to honour the locked rule",
                action_id,
            )
        return _verdict("approved", f"目标温度 {min(26, ceiling)}°C 在舒适上限内",
                        "Target within the comfort ceiling", action_id)

    # --- 布尔型阻断 ---
    if check == "boolean_block":
        if comfort.get(key) is True:
            return _verdict(
                "vetoed",
                f"用户已锁定约束「{key}」，该动作会影响这项体验",
                f"Locked constraint '{key}' blocks this action",
                action_id,
            )
        return _verdict("approved", "未触发相关约束", "No conflict", action_id)

    # --- 设备例外（待机切断） ---
    if check == "device_exception":
        exceptions = comfort.get("always_on_devices") or []
        if profile.get("observed", {}).get("wfh_likely") and "router" not in exceptions:
            exceptions = list(exceptions) + ["网络路由（居家办公需要）"]
        if exceptions:
            return _verdict(
                "adjusted",
                f"执行时需排除以下必须常供电的设备：{'、'.join(map(str, exceptions))}",
                f"Must exclude always-on devices: {', '.join(map(str, exceptions))}",
                action_id,
            )
        return _verdict("approved", "无必须常供电的设备", "No always-on exceptions", action_id)

    # --- 静音时段 ---
    if check == "quiet_hours_block":
        quiet = comfort.get("quiet_hours")
        if quiet:
            return _verdict(
                "adjusted",
                f"错峰时段需避开静音时段 {quiet}",
                f"Off-peak window must avoid quiet hours {quiet}",
                action_id,
            )
        return _verdict("approved", "未设定静音时段", "No quiet hours set", action_id)

    return _verdict("approved", "无适用规则", "No applicable rule", action_id)


def review_actions(actions: list[dict], profile: dict) -> dict:
    """批量审查。返回 {approved, vetoed, summary}。

    approved 里的每个动作都会被写入 comfort_verdict 字段；
    vetoed 单独成表，带上"因此放弃了多少钱"，供网站展示。
    """
    approved: list[dict] = []
    vetoed: list[dict] = []

    for action in actions:
        verdict = review_action(action, profile)
        enriched = dict(action)
        enriched["comfort_verdict"] = verdict
        if verdict["status"] == "vetoed":
            vetoed.append(enriched)
        else:
            approved.append(enriched)

    forgone = sum(a.get("est_cost_per_month", a.get("est_sgd_per_month", 0)) for a in vetoed)
    forgone_kwh = sum(a.get("est_kwh_per_month", 0) for a in vetoed)

    return {
        "approved": approved,
        "vetoed": vetoed,
        "summary": {
            "approved_count": len(approved),
            "vetoed_count": len(vetoed),
            "adjusted_count": sum(
                1 for a in approved if a["comfort_verdict"]["status"] == "adjusted"
            ),
            "forgone_cost_per_month": round(forgone, 2),
            "forgone_kwh_per_month": round(forgone_kwh, 1),
            "note": {
                "zh": "被否决的动作是系统为保护舒适度主动放弃的收益，不是遗漏",
                "en": "Vetoed actions are savings deliberately given up to protect comfort",
            },
        },
    }


def locked_rules(profile: dict) -> list[dict]:
    """把画像里的舒适约束整理成网站可直接展示的"已锁定规则"卡片。"""
    comfort = profile.get("comfort_preferences") or {}
    rules: list[dict] = []

    if comfort.get("max_ac_setpoint") is not None:
        value = comfort["max_ac_setpoint"]
        rules.append({
            "id": "ac_ceiling",
            "label": {"zh": f"空调不高于 {value}°C", "en": f"AC ≤ {value}°C"},
            "kind": "thermal",
            "locked": True,
        })
    if comfort.get("sleep_needs_ac"):
        rules.append({
            "id": "sleep_cooling",
            "label": {"zh": "睡眠时段必须制冷", "en": "Cooling protected during sleep"},
            "kind": "thermal",
            "locked": True,
        })
    if profile.get("observed", {}).get("wfh_likely"):
        rules.append({
            "id": "wfh_protected",
            "label": {"zh": "居家办公时段不降级", "en": "WFH hours protected"},
            "kind": "availability",
            "locked": True,
        })
    goals = profile.get("goals") or {}
    if goals.get("monthly_saving_target_pct"):
        rules.append({
            "id": "target",
            "label": {
                "zh": f"月度目标降幅 {goals['monthly_saving_target_pct']}%",
                "en": f"Target −{goals['monthly_saving_target_pct']}%",
            },
            "kind": "goal",
            "locked": False,
        })
    if comfort.get("notes"):
        rules.append({
            "id": "note",
            "label": {"zh": comfort["notes"], "en": comfort.get("notes_en", comfort["notes"])},
            "kind": "note",
            "locked": True,
        })
    return rules
