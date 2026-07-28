"""智能体闭环测试：用 Mock LLM 走完整的 诊断 -> 计划 -> 快进 -> 复盘 流程。

这同时验证了：工具循环、工具执行、计划持久化、数据快进、
天气归一化追踪，以及“计划确实带来了可测量的节省”。
"""

from __future__ import annotations

import unittest

from homeshift.agent.core import Agent
from homeshift.agent.prompts import DIAGNOSE_PROMPT, PLAN_PROMPT, REVIEW_PROMPT
from homeshift.datagen.generate import append_week_with_plan
from homeshift.domain.tracker import track_progress
from homeshift.llm.mock_client import MockLLMClient

try:
    from .helpers import TempEnv
except ImportError:  # 直接以 discover -s tests 方式运行时
    from helpers import TempEnv


class TestAgentLoop(unittest.TestCase):
    def test_full_cycle(self):
        with TempEnv() as ctx:
            agent = Agent(ctx, MockLLMClient(), verbose=False)

            # 1) 诊断
            report = agent.run_task(DIAGNOSE_PROMPT)
            self.assertIn("诊断报告", report)
            self.assertIn("空调", report)
            self.assertIn("负载分解", report)

            # 2) 计划
            plan_text = agent.run_task(PLAN_PROMPT)
            self.assertIn("节能计划", plan_text)
            plan = ctx.store.get_active_plan()
            self.assertIsNotNone(plan)
            self.assertGreaterEqual(len(plan["actions"]), 3)
            self.assertGreater(plan["expected_per_month"]["sgd"], 0)

            # 3) 数据不足时复盘应给出友好提示
            early_review = agent.run_task(REVIEW_PROMPT)
            self.assertIn("不足", early_review)

            # 4) 快进一周（注入计划效果）
            append_week_with_plan(ctx, plan, adherence=0.9)

            # 5) 复盘：应产生可测量的节省
            review = agent.run_task(REVIEW_PROMPT)
            self.assertIn("复盘", review)
            track = track_progress(ctx)
            self.assertEqual(track["status"], "ok")
            self.assertGreater(
                track["saving"]["kwh_per_day"], 0.5,
                "执行计划后应有明显节省（>0.5 kWh/天）",
            )
            # 达成率应在合理区间（执行率 0.9，允许估算误差）
            self.assertIsNotNone(track["overall_achievement_pct"])
            self.assertGreater(track["overall_achievement_pct"], 30)

    def test_plan_respects_comfort(self):
        """计划中的动作不允许有 high 舒适影响。"""
        with TempEnv() as ctx:
            agent = Agent(ctx, MockLLMClient(), verbose=False)
            agent.run_task(PLAN_PROMPT)
            plan = ctx.store.get_active_plan()
            for action in plan["actions"]:
                self.assertNotEqual(action["comfort_impact"], "high")

    def test_help_fallback(self):
        with TempEnv() as ctx:
            agent = Agent(ctx, MockLLMClient(), verbose=False)
            reply = agent.run_task("你好呀")
            self.assertIn("HomeShift", reply)

    def test_review_writes_memory_on_low_achievement(self):
        """执行率极低时，复盘应把结论写入长期记忆（反思闭环）。"""
        with TempEnv() as ctx:
            agent = Agent(ctx, MockLLMClient(), verbose=False)
            agent.run_task(PLAN_PROMPT)
            plan = ctx.store.get_active_plan()
            append_week_with_plan(ctx, plan, adherence=0.1)  # 几乎没执行
            agent.run_task(REVIEW_PROMPT)
            track = track_progress(ctx)
            if (track.get("overall_achievement_pct") or 100) < 60:
                self.assertTrue(
                    any(m["kind"] == "insight" for m in ctx.store.get_memories()),
                    "低达成率的复盘应写入 insight 记忆",
                )


class TestReport(unittest.TestCase):
    def test_html_report(self):
        from homeshift.report.html_report import build_report

        with TempEnv() as ctx:
            path = build_report(ctx)
            from pathlib import Path

            content = Path(path).read_text(encoding="utf-8")
            self.assertIn("HomeShift AI", content)
            self.assertIn("<svg", content)


if __name__ == "__main__":
    unittest.main()
