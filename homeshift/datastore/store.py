"""智能体的持久记忆（JSON 文件存储）。

- profile.json  用户画像：家庭结构、电器、作息、舒适约束、目标
- plans.json    节能计划的全部历史版本（含基线期与预期节省）
- memory.json   长期记忆：用户反馈、复盘结论（跨会话保留）
- reviews.json  周度复盘报告存档

设计意图：Agent 的“记忆”不是对话上下文，而是结构化、可解释、可审计的
文件——每次会话都能读到之前学到的东西（例如“用户觉得 26°C 太热”）。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

DEFAULT_PROFILE: dict = {
    "home_type": "HDB 4房式组屋",
    "location": "Singapore",
    "household": "两名上班族 + 两名学生，白天多数时间不在家，晚间与周末在家",
    "major_appliances": [
        {"name": "分体式空调 x3（主卧/次卧/客厅）", "note": "睡眠时段整晚开启，当前设定 24°C"},
        {"name": "储水式热水器 3kW", "note": "常年保持通电（always-on）"},
        {"name": "冰箱（双门）", "note": "24 小时运行"},
        {"name": "滚筒洗衣机", "note": "每周约 4 次，习惯温水洗"},
        {"name": "照明/电视/路由器/厨房电器", "note": "常规使用"},
    ],
    "ac_setpoint": 24,
    "heater_mode": "always_on",
    "wash_mode": "warm",
    "comfort_preferences": {
        "sleep_needs_ac": True,
        "max_ac_setpoint": 26,
        "notes": "孩子睡眠怕热，空调温度不可高于 26°C",
    },
    "goals": {
        "monthly_saving_target_sgd": 20,
        "priority": "省钱优先，不牺牲睡眠舒适度",
    },
}


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.profile_path = self.data_dir / "profile.json"
        self.plans_path = self.data_dir / "plans.json"
        self.memory_path = self.data_dir / "memory.json"
        self.reviews_path = self.data_dir / "reviews.json"

    # ---------- 通用读写 ----------

    def _read_json(self, path: Path, default):
        if not path.exists():
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, path: Path, payload) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    # ---------- 用户画像 ----------

    def get_profile(self) -> dict:
        return self._read_json(self.profile_path, {})

    def save_profile(self, profile: dict) -> None:
        self._write_json(self.profile_path, profile)

    def ensure_default_profile(self) -> dict:
        profile = self.get_profile()
        if not profile:
            profile = DEFAULT_PROFILE
            self.save_profile(profile)
        return profile

    # ---------- 节能计划（带版本） ----------

    def list_plans(self) -> list[dict]:
        return self._read_json(self.plans_path, [])

    def get_active_plan(self) -> dict | None:
        for plan in reversed(self.list_plans()):
            if plan.get("status") == "active":
                return plan
        return None

    def save_plan(self, plan: dict) -> dict:
        plans = self.list_plans()
        for old in plans:
            if old.get("status") == "active":
                old["status"] = "superseded"
        plan["version"] = len(plans) + 1
        plan["status"] = "active"
        plans.append(plan)
        self._write_json(self.plans_path, plans)
        return plan

    # ---------- 长期记忆 ----------

    def get_memories(self) -> list[dict]:
        return self._read_json(self.memory_path, [])

    def add_memory(self, note: str, kind: str = "feedback", when: date | None = None) -> dict:
        memories = self.get_memories()
        entry = {
            "id": len(memories) + 1,
            "kind": kind,
            "note": note,
            "created_at": (when or datetime.now().date()).isoformat(),
        }
        memories.append(entry)
        self._write_json(self.memory_path, memories)
        return entry

    # ---------- 复盘报告 ----------

    def get_reviews(self) -> list[dict]:
        return self._read_json(self.reviews_path, [])

    def add_review(self, review: dict) -> dict:
        reviews = self.get_reviews()
        review["id"] = len(reviews) + 1
        reviews.append(review)
        self._write_json(self.reviews_path, reviews)
        return review
