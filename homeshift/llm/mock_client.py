"""离线 Mock LLM 客户端。

作用：在没有 ANTHROPIC_API_KEY 的环境（课堂演示、评审电脑）也能
完整展示 Agentic 闭环。它不是“假数据”——工具调用循环、工具执行、
数据计算全部真实，只是“下一步调用哪个工具”的决策由预定义剧本
（playbook）驱动，最终报告由模板 + 真实数字渲染。

这同时是教学素材：剧本明确展示了一个 Agent 完成任务的典型
工具调用序列（感知 -> 分析 -> 决策 -> 行动 -> 记忆）。

局限（诚实声明）：Mock 模式没有自由推理能力，chat 只做关键词路由；
接入真实 Claude 后即可自然对话、处理任意问题。
"""

from __future__ import annotations

import json

from .base import LLMClient, LLMResponse

# ---------------------------------------------------------------------------
# 对话历史解析
# ---------------------------------------------------------------------------


def _last_user_text(messages: list[dict]) -> str:
    """最后一条“真正的用户话语”（排除 tool_result 消息）。"""
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [b.get("text", "") for b in content if b.get("type") == "text"]
            if texts:
                return "\n".join(texts)
    return ""


def _turn_start_index(messages: list[dict]) -> int:
    """当前任务回合的起点：最后一条用户文本消息的下标。"""
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return idx
        if isinstance(content, list) and any(b.get("type") == "text" for b in content):
            return idx
    return 0


def _collect_tool_results(messages: list[dict]) -> dict[str, dict]:
    """收集当前回合内已完成的工具调用 {工具名: 结果}。"""
    start = _turn_start_index(messages)
    id_to_name: dict[str, str] = {}
    results: dict[str, dict] = {}
    for msg in messages[start:]:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use":
                id_to_name[block["id"]] = block["name"]
            elif block.get("type") == "tool_result":
                name = id_to_name.get(block.get("tool_use_id", ""))
                if not name:
                    continue
                raw = block.get("content")
                text = ""
                if isinstance(raw, list):
                    text = "".join(b.get("text", "") for b in raw if b.get("type") == "text")
                elif isinstance(raw, str):
                    text = raw
                try:
                    results[name] = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    results[name] = {"raw": text}
    return results


# ---------------------------------------------------------------------------
# 场景识别与剧本
# ---------------------------------------------------------------------------

def _detect_scenario(user_text: str) -> str:
    text = user_text.lower()
    if any(k in text for k in ("复盘", "review", "效果", "进展", "达成")):
        return "review"
    if any(k in text for k in ("计划", "方案", "怎么省", "如何省", "省钱", "plan")):
        return "plan"
    if any(k in text for k in ("诊断", "为什么", "耗电", "电费", "结构", "diagnose", "分析")):
        return "diagnose"
    return "help"


def _plan_action_selection(results: dict) -> dict:
    """从模拟器候选中选动作（模拟 LLM 的决策规则，透明可解释）。"""
    sim = results.get("simulate_savings", {})
    actions = sim.get("actions", [])
    chosen = [
        a["id"]
        for a in actions
        if a.get("est_sgd_per_month", 0) > 0 and a.get("comfort_impact") != "high"
    ][:5]
    return {
        "action_ids": chosen,
        "rationale": "优先选择零成本/低成本、不影响舒适度、且月节省金额最高的动作组合",
    }


def _review_needs_feedback(results: dict) -> bool:
    track = results.get("track_progress", {})
    if track.get("status") != "ok":
        return False
    overall = track.get("overall_achievement_pct")
    if overall is not None and overall < 60:
        return True
    for item in track.get("per_action", []):
        pct = item.get("achievement_pct")
        if pct is not None and pct < 40:
            return True
    return False


def _review_feedback_note(results: dict) -> str:
    track = results.get("track_progress", {})
    weak = [
        item["title"]
        for item in track.get("per_action", [])
        if item.get("achievement_pct") is not None and item["achievement_pct"] < 40
    ]
    overall = track.get("overall_achievement_pct")
    return (
        f"复盘结论：总体达成率 {overall}%；执行偏弱的动作：{'、'.join(weak) if weak else '无'}。"
        "下周复盘时重点关注这些动作的执行难点，必要时替换为更容易坚持的动作。"
    )


PLAYBOOKS: dict[str, list] = {
    # (工具名, 输入构造函数或固定 dict)
    "diagnose": [
        ("get_household_profile", {}),
        ("get_usage_summary", {"days": 30}),
        ("get_weather_summary", {"days": 30}),
        ("disaggregate_usage", {"days": 28}),
        ("get_tariff_info", {}),
        ("get_carbon_info", {}),
    ],
    "plan": [
        ("get_household_profile", {}),
        ("get_memories", {}),
        ("get_tariff_info", {}),
        ("simulate_savings", {"days": 28}),
        ("save_plan", _plan_action_selection),
    ],
    "review": [
        ("get_active_plan", {}),
        ("get_tariff_info", {}),
        ("track_progress", {}),
    ],
}


# ---------------------------------------------------------------------------
# 最终报告渲染（模板 + 真实数字）
# ---------------------------------------------------------------------------

CAT_LABELS = {
    "aircon": "空调",
    "water_heater": "热水器",
    "fridge": "冰箱",
    "standby": "待机负载",
    "laundry": "洗衣",
    "other": "照明/厨房/娱乐等",
}


def _fmt(x, nd=1):
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) else str(x)


def _money(tariff: dict, value, nd=2) -> str:
    """按当前地区的币种格式化金额（不再写死 S$）。"""
    symbol = tariff.get("currency_symbol") or "S$"
    return f"{symbol}{_fmt(value, nd)}"


def _finding_for(cat: str, kwh: float, share: float, profile: dict, climate: str) -> str:
    """按类别生成结论。措辞只依据数据本身，不假设用户家里有什么设备。"""
    label = CAT_LABELS.get(cat, cat)
    if cat == "aircon":
        if climate == "tropical":
            body = ("夜间时段扣除基线负载后的剩余电量较高，符合整晚制冷的特征；"
                    "该部分与室外气温强相关，是最容易通过设定温度优化的负载。")
        else:
            body = ("这部分是夜间/早晚时段扣除基线后的剩余电量。注意：本数据来自温带地区，"
                    "该类别实际混合了取暖、热水与其他夜间负载，不应简单理解为'空调'。")
    elif cat == "water_heater":
        body = ("白天无人时段仍持续高于基线，是储水式热水器保温散热的典型信号——"
                "也就是说这部分电费并没有变成热水，而是散掉了。")
    elif cat == "standby":
        body = ("路由器、机顶盒、充电器等设备 24 小时不间断，单个功率很小但全年累积可观，"
                "属于'看不见的电费'。")
    elif cat == "fridge":
        body = "冰箱是全天候运行的刚性负载，优化空间主要在温度设定、除霜与门封状态。"
    elif cat == "laundry":
        body = "洗衣负载集中在固定时段，大部分电耗用于加热水，改冷水洗即可显著下降。"
    else:
        body = "包含照明、厨房电器与娱乐设备，构成较杂，需要更细的分表才能进一步拆解。"
    return f"**{label}（{_fmt(kwh, 2)} kWh/天，占 {_fmt(share)}%）**：{body}"


def _compose_diagnose(r: dict) -> str:
    usage = r.get("get_usage_summary", {})
    weather = r.get("get_weather_summary", {})
    disagg = r.get("disaggregate_usage", {})
    tariff = r.get("get_tariff_info", {})
    carbon = r.get("get_carbon_info", {})
    profile = r.get("get_household_profile", {})
    if "error" in usage:
        return ("没有用电数据。请先运行 `python fetch_real_data.py`（真实数据）"
                "或 `python -m homeshift init`（合成演示数据）。")

    monthly = usage.get("projected_monthly", {})
    daily_avg = disagg.get("daily_avg_kwh", {})
    share = disagg.get("share_pct", {})
    ranked = sorted(daily_avg.items(), key=lambda kv: kv[1], reverse=True)
    factor = carbon.get("grid_emission_factor_kg_per_kwh", 0)
    is_real = profile.get("data_source") == "real"
    climate = "tropical"
    if isinstance(profile.get("comfort_preferences"), dict):
        climate = "tropical" if profile["comfort_preferences"].get("sleep_needs_ac") else "temperate"

    lines = [
        "# 家庭用电诊断报告",
        "",
        "## 1. 总体情况",
        f"- 统计期：{usage['period']['start']} ~ {usage['period']['end']}（{usage['days']} 天）",
        f"- 日均用电 **{_fmt(usage['avg_daily_kwh'], 2)} kWh**，折算月用电约 "
        f"**{_fmt(monthly.get('kwh'))} kWh**，电费约 "
        f"**{_money(tariff, monthly.get('total_cost', monthly.get('total_sgd')))}/月**"
        f"（{_fmt(tariff.get('regulated_rate_per_kwh'), 4)} "
        f"{tariff.get('currency', '')}/kWh + 税）",
    ]
    # 天气：拿不到就如实说明，不能凭空断言"空调需求较高"
    if weather and "error" not in weather and weather.get("avg_temp_c") is not None:
        lines.append(
            f"- 期间日均气温 {_fmt(weather.get('avg_temp_c'))}°C，"
            f"日均制冷度时 {_fmt(weather.get('cooling_degree_hours_per_day'))}"
        )
    else:
        lines.append("- 天气数据不可用，本次诊断未做气温归因（复盘时的天气归一化也会受影响）")
    lines.append(
        f"- 折算碳排放约 {_fmt(monthly.get('kwh', 0) * factor, 0)} kg CO2/月"
        f"（排放因子 {factor} kg/kWh，{carbon.get('region', '-')}）"
    )
    if is_real:
        obs = profile.get("observed", {})
        lines.append(
            f"- 数据来源：**真实数据集**（{profile.get('dataset_id')}），"
            f"用电高峰出现在 {obs.get('peak_half_hour', '-')}，"
            f"夜间用电占比 {obs.get('night_share_pct', '-')}%"
        )

    lines += ["", "## 2. 用电结构（负载分解估算）",
              "| 类别 | 日均 kWh | 占比 |", "| --- | ---: | ---: |"]
    for cat, kwh in ranked:
        lines.append(f"| {CAT_LABELS.get(cat, cat)} | {_fmt(kwh, 2)} | {_fmt(share.get(cat, 0))}% |")

    # 关键发现：取实际占比最高的前三类，措辞随数据变化
    findings = ["", "## 3. 关键发现（按实际占比排序）"]
    for i, (cat, kwh) in enumerate(ranked[:3], 1):
        findings.append(f"{i}. " + _finding_for(cat, kwh, share.get(cat, 0), profile, climate))

    notes = disagg.get("method_notes", [])
    next_steps = [
        "",
        "## 4. 方法与局限",
    ]
    for note in notes:
        next_steps.append(f"- {note}")
    if is_real:
        next_steps.append(
            "- 家庭画像中的作息由用电曲线反推、电器清单来自数据集文档，"
            "并非用户自述，相关结论应作为假设看待"
        )
    next_steps += [
        "",
        "## 5. 下一步",
        "运行 `python -m homeshift plan`，我会结合以上结构与你的舒适约束生成量化的节能计划。",
    ]
    return "\n".join(lines + findings + next_steps)


def _compose_plan(r: dict) -> str:
    saved = r.get("save_plan", {})
    plan = saved.get("plan", {})
    if not plan:
        return f"计划保存失败：{json.dumps(saved, ensure_ascii=False)}"
    exp = plan.get("expected_per_month", {})
    comfort = r.get("get_household_profile", {}).get("comfort_preferences", {})
    tariff = r.get("get_tariff_info", {}) or {"currency_symbol": plan.get("currency_symbol", "S$")}

    impact_label = {"none": "无", "low": "很小", "medium": "中等", "high": "较大"}
    effort_label = {"zero_cost": "零成本", "low_cost": "低成本", "invest": "需投入"}

    lines = [
        f"# 个性化节能计划（v{plan.get('version')}）",
        "",
        f"依据最近 28 天的负载分解结果与你的舒适约束"
        f"（{comfort.get('notes', '空调不高于 26°C')}）制定。",
        "",
        f"**预期每月节省：{_fmt(exp.get('kwh'))} kWh ≈ "
        f"{_money(tariff, exp.get('cost', exp.get('sgd')))}，"
        f"减排 {_fmt(exp.get('co2_kg'))} kg CO2**",
        "",
        "## 动作清单",
    ]
    for idx, action in enumerate(plan.get("actions", []), 1):
        lines += [
            f"### {idx}. {action['title']}",
            f"{action['description']}",
            f"- 预计节省：{_fmt(action['est_kwh_per_month'])} kWh/月 ≈ "
            f"{_money(tariff, action.get('est_cost_per_month', action.get('est_sgd_per_month')))}/月，"
            f"减排 {_fmt(action['est_co2_kg_per_month'])} kg CO2",
            f"- 舒适影响：{impact_label.get(action['comfort_impact'], action['comfort_impact'])}"
            f"　执行成本：{effort_label.get(action['effort'], action['effort'])}",
        ]
        if action.get("notes"):
            lines.append(f"- 备注：{action['notes']}")
        lines.append("")

    lines += [
        "## 如何落实与追踪",
        "1. 今晚开始执行以上动作（都不需要牺牲舒适度）；",
        "2. 一周后运行 `python -m homeshift review`，我会用实际电表数据做天气归一化对比，"
        "告诉你每个动作真实省了多少、哪些没执行到位；",
        "3. 觉得某个动作不舒服？告诉我（chat 或复盘时反馈），我会记住并调整计划。",
        "",
        "> 演示环境提示：可运行 `python -m homeshift simulate-week` 快进一周“真实执行”数据。",
    ]
    return "\n".join(lines)


def _compose_review(r: dict) -> str:
    track = r.get("track_progress", {})
    plan = r.get("get_active_plan", {})
    if track.get("status") == "no_plan" or "error" in plan:
        return "还没有生效的节能计划。请先运行 `python -m homeshift plan`。"
    if track.get("status") == "insufficient_data":
        return (
            "计划刚制定，执行期数据还不足 3 天，暂时无法评估效果。\n"
            "演示环境可运行 `python -m homeshift simulate-week` 快进一周，再来复盘。"
        )

    daily = track.get("daily_kwh", {})
    saving = track.get("saving", {})
    wn = track.get("weather_normalization", {})
    lines = [
        f"# 周度复盘报告（计划 v{track.get('plan_version')}）",
        "",
        f"- 评估期：{track['after_period']['start']} ~ {track['after_period']['end']}"
        f"（基线：{track['baseline_period']['start']} ~ {track['baseline_period']['end']}）",
        f"- 基线日均 {_fmt(daily.get('baseline'), 2)} kWh；按本周天气归一化后，"
        f"**若不做任何动作预期 {_fmt(daily.get('expected_no_action'), 2)} kWh/天**，"
        f"实际 **{_fmt(daily.get('actual_after'), 2)} kWh/天**",
        f"- **实际节省 {_fmt(saving.get('kwh_per_day'), 2)} kWh/天（{_fmt(saving.get('pct'))}%），"
        f"折合每月约 {_fmt(saving.get('kwh_per_month_projection'))} kWh / "
        f"{_money(r.get('get_tariff_info', {}), saving.get('cost_per_month_projection', saving.get('sgd_per_month_projection')))} / "
        f"{_fmt(saving.get('co2_kg_per_month_projection'))} kg CO2**",
        f"- 对照计划预期（{_fmt(track.get('planned_saving_kwh_per_day'), 2)} kWh/天），"
        f"总体达成率 **{_fmt(track.get('overall_achievement_pct'), 0)}%**",
        (f"- 天气归一化：基线期 {wn.get('metric', 'CDH')} "
         f"{_fmt(wn.get('cdh_before_per_day'))} -> 本周 "
         f"{_fmt(wn.get('cdh_after_per_day'))}（已剔除天气影响）"
         if wn.get("applied")
         else f"- 天气归一化：**未生效** —— {wn.get('note', '')}"),
        "",
        "## 分动作达成情况",
        "| 动作 | 预期 kWh/天 | 实际 kWh/天 | 达成率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for item in track.get("per_action", []):
        pct = item.get("achievement_pct")
        pct_str = f"{_fmt(pct, 0)}%" if pct is not None else "—"
        actual = item.get("actual_kwh_day")
        actual_str = _fmt(actual, 2) if actual is not None else "—"
        lines.append(
            f"| {item['title']} | {_fmt(item.get('planned_kwh_day'), 2)} | {actual_str} | {pct_str} |"
        )

    # 规则化的分析与建议
    lines += ["", "## 分析与调整建议"]
    reliable = [i for i in track.get("per_action", [])
                if i.get("reliability") in (None, "ok")]
    unreliable = [i for i in track.get("per_action", [])
                  if i.get("reliability") not in (None, "ok", "not_measurable")]
    strong = [
        i for i in reliable
        if i.get("achievement_pct") is not None and 70 <= i["achievement_pct"] <= 250
    ]
    weak = [
        i for i in reliable
        if i.get("achievement_pct") is not None and i["achievement_pct"] < 40
    ]
    if strong:
        lines.append(
            f"- 执行到位：{'、'.join(i['title'] for i in strong)}——继续保持，"
            "这些动作已经形成习惯就是纯收益。"
        )
    if weak:
        lines.append(
            f"- 达成偏低：{'、'.join(i['title'] for i in weak)}——"
            "常见原因是忘记执行或体验不适。我已把这一点写入长期记忆，"
            "如果是舒适问题请直接告诉我，我会调整动作（例如空调 26°C 改 25°C + 风扇）。"
        )
    if unreliable:
        lines.append(
            "- 归因不可信：" + "、".join(i["title"] for i in unreliable)
            + "——这些动作的实际数字超出预期过多或信号太弱，更可能是负载分解的"
            "归类误差而非真实节省。**请以总体节省为准**，不要据此下结论。"
        )
    if not weak and not unreliable:
        lines.append("- 各动作执行良好，暂不调整计划；下周继续观察，波动大再做修正。")
    note = r.get("record_feedback")
    if note and note.get("saved"):
        lines.append("- 已写入长期记忆：本次复盘结论将用于下次计划调整。")
    lines += [
        "",
        "下周同一时间再运行 `review`，持续跟踪；数据积累越多，归因越准确。",
    ]
    return "\n".join(lines)


HELP_TEXT = """我是 HomeShift AI（离线演示模式）。我可以帮你：

1. **诊断**电费为什么高 —— 试试问“帮我诊断一下家里为什么耗电”
2. **制定**个性化节能**计划** —— “帮我制定一个省钱的节能方案”
3. **复盘**计划执行效果 —— “复盘一下这周的节能效果”

也可以直接使用命令：`diagnose` / `plan` / `review`。
设置任一模型的 API 密钥（ANTHROPIC_API_KEY / DEEPSEEK_API_KEY 等）后
将切换到真实大模型，支持自由对话。可用 `python -m homeshift providers` 查看。"""


COMPOSERS = {
    "diagnose": _compose_diagnose,
    "plan": _compose_plan,
    "review": _compose_review,
}

OPENING_NARRATION = {
    "diagnose": "好的，我来诊断你家的用电情况：先读取家庭画像和电表数据，再做负载分解。",
    "plan": "好的，我来制定节能计划：先确认画像与历史反馈，再用模拟器量化每个动作的收益。",
    "review": "好的，我来复盘计划执行效果：读取当前计划，并做天气归一化的前后对比。",
}


class MockLLMClient(LLMClient):
    provider_name = "mock"

    def create(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        user_text = _last_user_text(messages)
        scenario = _detect_scenario(user_text)
        if scenario == "help":
            return LLMResponse("end_turn", [{"type": "text", "text": HELP_TEXT}])

        results = _collect_tool_results(messages)
        playbook = list(PLAYBOOKS[scenario])

        # review 场景的条件步骤：达成率低时写入长期记忆
        if scenario == "review" and "track_progress" in results and _review_needs_feedback(results):
            playbook.append(
                ("record_feedback", lambda r: {"note": _review_feedback_note(r), "kind": "insight"})
            )

        for step_idx, (tool_name, tool_input) in enumerate(playbook):
            if tool_name in results:
                continue
            if callable(tool_input):
                tool_input = tool_input(results)
            content: list[dict] = []
            if step_idx == 0:
                content.append({"type": "text", "text": OPENING_NARRATION[scenario]})
            content.append(
                {
                    "type": "tool_use",
                    "id": f"toolu_mock_{scenario}_{step_idx}",
                    "name": tool_name,
                    "input": tool_input,
                }
            )
            return LLMResponse("tool_use", content)

        # 剧本执行完毕 -> 渲染最终报告
        text = COMPOSERS[scenario](results)
        return LLMResponse("end_turn", [{"type": "text", "text": text}])
