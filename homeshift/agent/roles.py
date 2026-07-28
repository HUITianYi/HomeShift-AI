"""七个专家角色（specialist roles）。

为什么需要这一层
---------------------------------------------------------------------------
可视化网站对外的叙事是「7 个专家 agent 协作」，而本项目的实现是
「1 个 LLM 循环 + 12 个工具」。如果只在导出的 JSON 里贴 7 个标签，
那是包装；答辩时被追问"到底几个 agent"会很被动。

这里的做法是把它做成真的：每个工具**归属**于一个角色，Agent 每次调用工具
都会记录"哪个角色出手了、看到了什么、产出了什么"，形成可审计的协作轨迹
（trace）。角色之间有明确的职责边界与依赖顺序，其中舒适守门人拥有
**否决权**（veto）——这是唯一一个能推翻其他角色结论的角色。

这样两边的口径就统一了，并且经得起追问：
  - 网站说的 7 个 agent = 这里的 7 个 role
  - 代码里的 1 个 LLM 循环 = 编排器（orchestrator），负责决定下一个该谁出手
这在多智能体文献里是标准的 "single-controller multi-role" 模式，
比 7 个各自持有独立 LLM 会话的实现更省 token、也更容易保证数字一致。
---------------------------------------------------------------------------
"""

from __future__ import annotations

ROLES: list[dict] = [
    {
        "id": "data_steward",
        "order": 1,
        "name": {"en": "Data Steward", "zh": "数据管家"},
        "mission": {
            "en": "Collect and validate the household's evidence before anyone reasons on it.",
            "zh": "在任何人开始推理之前，先把证据收齐并检查质量。",
        },
        "tools": ["get_household_profile", "get_usage_summary", "get_weather_summary"],
        "outputs": ["baseline", "signature_24h", "evidence"],
        "veto": False,
    },
    {
        "id": "load_detective",
        "order": 2,
        "name": {"en": "Load Detective", "zh": "负载侦探"},
        "mission": {
            "en": "Split one whole-home meter into appliance categories (NILM) and state its own error bars.",
            "zh": "把一块总电表拆成分类别用电（NILM），并如实说明自己的误差。",
        },
        "tools": ["disaggregate_usage"],
        "outputs": ["diagnosis.categories", "diagnosis.method"],
        "veto": False,
    },
    {
        "id": "cost_analyst",
        "order": 3,
        "name": {"en": "Cost Analyst", "zh": "成本分析师"},
        "mission": {
            "en": "Turn kWh into money under the household's actual tariff plan.",
            "zh": "按这户人家实际的电价方案，把 kWh 换算成钱。",
        },
        "tools": ["get_tariff_info"],
        "outputs": ["baseline.est_bill", "plans.actions[].est_cost_per_month"],
        "veto": False,
    },
    {
        "id": "carbon_analyst",
        "order": 4,
        "name": {"en": "Carbon Analyst", "zh": "碳排分析师"},
        "mission": {
            "en": "Turn kWh into CO2 using the local grid emission factor.",
            "zh": "用当地电网排放因子把 kWh 换算成碳排。",
        },
        "tools": ["get_carbon_info"],
        "outputs": ["baseline.carbon_kg", "plans.actions[].est_co2_kg_per_month"],
        "veto": False,
    },
    {
        "id": "comfort_guardian",
        "order": 5,
        "name": {"en": "Comfort Guardian", "zh": "舒适守门人"},
        "mission": {
            "en": "Hold the veto. Any action that breaks a locked comfort rule never reaches the user.",
            "zh": "持有否决权。任何违反已锁定舒适约束的动作，都不会被送到用户面前。",
        },
        "tools": [],  # 不调用外部工具，作用于其他角色的产物
        "operates_on": ["profile.comfort_preferences", "simulate_savings.actions"],
        "outputs": ["plans.actions[].comfort_verdict", "plans.vetoed"],
        "veto": True,
    },
    {
        "id": "planner",
        "order": 6,
        "name": {"en": "Planner", "zh": "规划师"},
        "mission": {
            "en": "Quantify every candidate action, pick a set the household will actually follow, commit it.",
            "zh": "量化每个候选动作，挑出这户人家真能坚持的组合，并落成正式计划。",
        },
        # get_active_plan 归规划师：计划这个产物由它创建，也由它对外提供
        "tools": ["simulate_savings", "save_plan", "get_active_plan"],
        "outputs": ["plans"],
        "veto": False,
    },
    {
        "id": "tracker_memory",
        "order": 7,
        "name": {"en": "Tracker & Memory", "zh": "追踪与记忆"},
        "mission": {
            "en": "Measure what actually happened after weather normalization, and remember it for next round.",
            "zh": "在剔除天气影响后测量真实发生了什么，并记住它用于下一轮调整。",
        },
        "tools": ["track_progress", "record_feedback", "get_memories"],
        "outputs": ["track", "memories"],
        "veto": False,
    },
]

# 工具 -> 角色 的反向索引
TOOL_TO_ROLE: dict[str, str] = {}
for _role in ROLES:
    for _tool in _role["tools"]:
        TOOL_TO_ROLE[_tool] = _role["id"]

ROLE_BY_ID = {role["id"]: role for role in ROLES}


def role_of_tool(tool_name: str) -> str:
    """某个工具由哪个角色负责。未登记的工具归为编排器自身。"""
    return TOOL_TO_ROLE.get(tool_name, "orchestrator")


def role_name(role_id: str, lang: str = "zh") -> str:
    role = ROLE_BY_ID.get(role_id)
    if not role:
        return "编排器" if lang == "zh" else "Orchestrator"
    return role["name"].get(lang, role["id"])


def roster(lang: str = "zh") -> list[dict]:
    """给 CLI / 导出用的角色花名册。"""
    return [
        {
            "id": r["id"],
            "order": r["order"],
            "name": r["name"].get(lang, r["id"]),
            "name_en": r["name"]["en"],
            "mission": r["mission"].get(lang, ""),
            "tools": r["tools"],
            "veto": r["veto"],
        }
        for r in sorted(ROLES, key=lambda x: x["order"])
    ]


def validate_coverage(tool_definitions: list[dict]) -> dict:
    """自检：确保每个工具都被某个角色认领，没有孤儿工具。

    在测试里调用，防止以后加了新工具却忘记归属，导致对外的
    "7 个 agent" 说法与实际实现脱节。
    """
    declared = set(TOOL_TO_ROLE)
    actual = {t["name"] for t in tool_definitions}
    return {
        "unassigned_tools": sorted(actual - declared),   # 有工具没角色认领
        "phantom_tools": sorted(declared - actual),      # 角色认领了不存在的工具
        "ok": not (actual - declared) and not (declared - actual),
    }
