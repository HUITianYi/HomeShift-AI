"""新增能力的测试：真实数据接入、多模型 API、舒适否决、角色体系、网站导出。

这些测试都不联网：
- 真实数据用一份仿 UCI 格式的小样本，验证解析与重采样是否正确；
- LLM 客户端只验证格式翻译（Anthropic <-> OpenAI），不发真实请求。
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta

from homeshift.agent.roles import ROLES, role_of_tool, validate_coverage
from homeshift.agent.tools import TOOL_DEFINITIONS
from homeshift.domain.comfort import locked_rules, review_actions
from homeshift.llm.openai_compat import (
    messages_to_openai,
    response_to_anthropic,
    tools_to_openai,
)
from homeshift.llm.registry import PROVIDERS, resolve_llm_settings
from homeshift.realdata.loaders import load_generic_csv, load_uci
from homeshift.realdata.pipeline import select_window
from homeshift.realdata.weather import to_half_hourly

from .helpers import TempEnv


# ===========================================================================
# 真实数据解析
# ===========================================================================

class TestRealDataLoaders(unittest.TestCase):
    def _write_uci_sample(self, path, minutes=600, missing_every=0):
        lines = ["Date;Time;Global_active_power;Global_reactive_power;Voltage;"
                 "Global_intensity;Sub_metering_1;Sub_metering_2;Sub_metering_3"]
        ts = datetime(2009, 5, 1, 0, 0, 0)
        for i in range(minutes):
            if missing_every and i % missing_every == 0:
                lines.append(f"{ts:%d/%m/%Y};{ts:%H:%M:%S};?;?;?;?;;;")
            else:
                # 每分钟 1.2 kW -> 每分钟 0.02 kWh -> 每半小时 0.6 kWh
                lines.append(f"{ts:%d/%m/%Y};{ts:%H:%M:%S};1.200;0.100;240.00;5.0;"
                             f"6.000;12.000;18.000")
            ts += timedelta(minutes=1)
        path.write_text("\n".join(lines), encoding="utf-8")

    def test_uci_resamples_to_half_hour_with_correct_units(self):
        with TempEnv() as ctx:
            raw = ctx.data_dir / "uci_sample.txt"
            ctx.data_dir.mkdir(parents=True, exist_ok=True)
            self._write_uci_sample(raw, minutes=120)
            result = load_uci(raw, progress=False)

            self.assertEqual(len(result["usage"]), 4)  # 120 分钟 = 4 个半小时
            # 1.2 kW 持续 30 分钟 = 0.6 kWh
            for _, kwh in result["usage"]:
                self.assertAlmostEqual(kwh, 0.6, places=3)
            # 分表：18 Wh/分钟 * 30 = 540 Wh = 0.54 kWh
            self.assertAlmostEqual(result["truth"][0]["sub_metering_3"], 0.54, places=3)
            self.assertEqual(result["stats"]["raw_missing_pct"], 0.0)

    def test_uci_drops_incomplete_half_hours_instead_of_faking_zero(self):
        """缺失值不能补 0，否则会凭空制造出'节省'。"""
        with TempEnv() as ctx:
            raw = ctx.data_dir / "uci_gappy.txt"
            ctx.data_dir.mkdir(parents=True, exist_ok=True)
            # 每 2 分钟缺一条 -> 每个半小时只有 15 个样本 < 20，应全部丢弃
            self._write_uci_sample(raw, minutes=120, missing_every=2)
            result = load_uci(raw, progress=False)
            self.assertEqual(len(result["usage"]), 0)
            self.assertGreater(result["stats"]["slots_dropped_incomplete"], 0)

    def test_uci_rejects_wrong_file_format(self):
        with TempEnv() as ctx:
            ctx.data_dir.mkdir(parents=True, exist_ok=True)
            raw = ctx.data_dir / "not_uci.txt"
            raw.write_text("foo,bar\n1,2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_uci(raw, progress=False)

    def test_generic_csv_autodetects_columns(self):
        with TempEnv() as ctx:
            ctx.data_dir.mkdir(parents=True, exist_ok=True)
            path = ctx.data_dir / "meter.csv"
            rows = ["Reading Date,kWh,Account"]
            ts = datetime(2026, 1, 1, 0, 0)
            for _ in range(96):
                rows.append(f"{ts:%Y-%m-%d %H:%M},0.5,ACC1")
                ts += timedelta(minutes=30)
            path.write_text("\n".join(rows), encoding="utf-8")

            result = load_generic_csv(path)
            self.assertEqual(len(result["usage"]), 96)
            self.assertAlmostEqual(result["usage"][0][1], 0.5)
            self.assertEqual(result["stats"]["inferred_step_minutes"], 30)

    def test_generic_csv_converts_power_to_energy(self):
        """输入是 kW（功率）时必须按时长换算成 kWh，否则数字会大一倍。"""
        with TempEnv() as ctx:
            ctx.data_dir.mkdir(parents=True, exist_ok=True)
            path = ctx.data_dir / "power.csv"
            rows = ["timestamp,kw"]
            ts = datetime(2026, 1, 1, 0, 0)
            for _ in range(48):
                rows.append(f"{ts:%Y-%m-%dT%H:%M},2.0")
                ts += timedelta(minutes=30)
            path.write_text("\n".join(rows), encoding="utf-8")

            result = load_generic_csv(path, value_unit="kw")
            # 2 kW 持续半小时 = 1 kWh
            self.assertAlmostEqual(result["usage"][0][1], 1.0, places=3)


class TestWindowSelection(unittest.TestCase):
    def test_picks_most_recent_complete_window(self):
        usage = []
        ts = datetime(2026, 1, 1, 0, 0)
        for _ in range(100 * 48):
            usage.append((ts, 0.4))
            ts += timedelta(minutes=30)
        window = select_window(usage, 63)
        self.assertEqual(window["days"], 63)
        self.assertEqual(window["completeness_pct"], 100.0)
        # 应该取最近的一段，而不是最早的
        self.assertEqual(window["end"], usage[-1][0].date())

    def test_handles_dataset_shorter_than_window(self):
        usage = [(datetime(2026, 1, 1) + timedelta(minutes=30 * i), 0.4)
                 for i in range(10 * 48)]
        window = select_window(usage, 63)
        self.assertEqual(window["days"], 10)


class TestWeatherResampling(unittest.TestCase):
    def test_hourly_interpolates_to_half_hourly(self):
        series = [(datetime(2026, 1, 1, 0, 0), 20.0),
                  (datetime(2026, 1, 1, 1, 0), 24.0)]
        slots = [datetime(2026, 1, 1, 0, 0), datetime(2026, 1, 1, 0, 30),
                 datetime(2026, 1, 1, 1, 0)]
        out = to_half_hourly(series, slots)
        self.assertEqual([v for _, v in out], [20.0, 22.0, 24.0])

    def test_extrapolates_at_boundaries_without_crashing(self):
        series = [(datetime(2026, 1, 1, 12, 0), 30.0)]
        slots = [datetime(2026, 1, 1, 0, 0), datetime(2026, 1, 2, 0, 0)]
        out = to_half_hourly(series, slots)
        self.assertEqual([v for _, v in out], [30.0, 30.0])


# ===========================================================================
# LLM 多模型
# ===========================================================================

class TestProviderRegistry(unittest.TestCase):
    def test_auto_falls_back_to_mock_without_keys(self):
        cfg = {"llm": {"provider": "auto"}}
        import os

        saved = {k: os.environ.pop(k) for k in list(os.environ)
                 if k.endswith("_API_KEY")}
        try:
            settings = resolve_llm_settings(cfg)
            self.assertEqual(settings["provider"], "mock")
            self.assertIn("未探测到", settings["reason"])
        finally:
            os.environ.update(saved)

    def test_deepseek_preset_uses_current_model_names(self):
        """deepseek-chat / deepseek-reasoner 已于 2026-07-24 下线，不能再用。"""
        preset = PROVIDERS["deepseek"]
        self.assertEqual(preset["base_url"], "https://api.deepseek.com")
        self.assertIn(preset["default_model"], ("deepseek-v4-pro", "deepseek-v4-flash"))
        self.assertNotIn(preset["default_model"], ("deepseek-chat", "deepseek-reasoner"))

    def test_explicit_provider_and_model_override_preset(self):
        cfg = {"llm": {"provider": "deepseek", "model": "deepseek-v4-flash"}}
        settings = resolve_llm_settings(cfg)
        self.assertEqual(settings["model"], "deepseek-v4-flash")
        self.assertEqual(settings["kind"], "openai_compat")


class TestOpenAIFormatTranslation(unittest.TestCase):
    def test_tool_schema_conversion(self):
        converted = tools_to_openai(TOOL_DEFINITIONS)
        self.assertEqual(len(converted), len(TOOL_DEFINITIONS))
        first = converted[0]
        self.assertEqual(first["type"], "function")
        self.assertIn("parameters", first["function"])
        self.assertEqual(first["function"]["name"], TOOL_DEFINITIONS[0]["name"])

    def test_tool_use_roundtrip(self):
        """Anthropic 的 tool_use/tool_result 必须能翻译成 OpenAI 的
        tool_calls/role=tool，且顺序不能乱（OpenAI 对顺序有硬性要求）。"""
        messages = [
            {"role": "user", "content": "诊断一下"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "我先看看电价"},
                {"type": "tool_use", "id": "tu_1", "name": "get_tariff_info", "input": {}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu_1",
                 "content": [{"type": "text", "text": '{"rate": 0.3}'}]},
            ]},
        ]
        out = messages_to_openai("你是助手", messages)
        self.assertEqual(out[0]["role"], "system")
        self.assertEqual(out[1]["role"], "user")
        self.assertEqual(out[2]["role"], "assistant")
        self.assertEqual(out[2]["tool_calls"][0]["id"], "tu_1")
        self.assertEqual(out[2]["tool_calls"][0]["function"]["name"], "get_tariff_info")
        self.assertEqual(out[3]["role"], "tool")
        self.assertEqual(out[3]["tool_call_id"], "tu_1")

    def test_thinking_blocks_are_not_sent_to_openai_models(self):
        """Claude 的 thinking 块其他模型不认识，必须过滤掉。"""
        messages = [{"role": "assistant", "content": [
            {"type": "thinking", "thinking": "内部推理"},
            {"type": "text", "text": "对外回答"},
        ]}]
        out = messages_to_openai("sys", messages)
        self.assertEqual(out[1]["content"], "对外回答")
        self.assertNotIn("内部推理", json.dumps(out, ensure_ascii=False))

    def test_openai_response_converts_to_anthropic_blocks(self):
        payload = {"choices": [{"finish_reason": "tool_calls", "message": {
            "content": "让我查一下",
            "tool_calls": [{"id": "call_0", "type": "function", "function": {
                "name": "disaggregate_usage", "arguments": '{"days": 28}'}}],
        }}]}
        response = response_to_anthropic(payload)
        self.assertEqual(response.stop_reason, "tool_use")
        kinds = [b["type"] for b in response.content]
        self.assertEqual(kinds, ["text", "tool_use"])
        self.assertEqual(response.content[1]["input"], {"days": 28})

    def test_malformed_tool_arguments_do_not_crash(self):
        """小模型经常吐出非法 JSON，不能让整个 Agent 循环崩掉。"""
        payload = {"choices": [{"finish_reason": "tool_calls", "message": {
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {
                "name": "get_tariff_info", "arguments": "{不是合法JSON"}}],
        }}]}
        response = response_to_anthropic(payload)
        self.assertEqual(response.content[0]["type"], "tool_use")
        self.assertIn("_malformed_arguments", response.content[0]["input"])

    def test_finish_reason_corrected_when_tool_calls_present(self):
        """有些服务返回 finish_reason='stop' 却带着 tool_calls，必须纠正。"""
        payload = {"choices": [{"finish_reason": "stop", "message": {
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "get_memories", "arguments": "{}"}}],
        }}]}
        self.assertEqual(response_to_anthropic(payload).stop_reason, "tool_use")


# ===========================================================================
# 舒适守门人与角色体系
# ===========================================================================

class TestComfortGuardian(unittest.TestCase):
    def test_vetoes_ac_action_when_ceiling_already_reached(self):
        profile = {"ac_setpoint": 26, "comfort_preferences": {"max_ac_setpoint": 26}}
        actions = [{"id": "ac_setpoint_26", "est_kwh_per_month": 30,
                    "est_cost_per_month": 9.0}]
        result = review_actions(actions, profile)
        self.assertEqual(len(result["vetoed"]), 1)
        self.assertEqual(result["summary"]["forgone_cost_per_month"], 9.0)

    def test_adjusts_instead_of_vetoing_when_ceiling_is_tighter(self):
        profile = {"ac_setpoint": 23, "comfort_preferences": {"max_ac_setpoint": 25}}
        actions = [{"id": "ac_setpoint_26", "est_kwh_per_month": 30}]
        result = review_actions(actions, profile)
        self.assertEqual(len(result["approved"]), 1)
        self.assertEqual(result["approved"][0]["comfort_verdict"]["status"], "adjusted")

    def test_vetoed_actions_keep_their_reason(self):
        """被否决的动作不能悄悄消失，必须带着理由留给用户看。"""
        profile = {"comfort_preferences": {"requires_warm_wash": True}}
        actions = [{"id": "cold_wash", "est_kwh_per_month": 20}]
        result = review_actions(actions, profile)
        verdict = result["vetoed"][0]["comfort_verdict"]
        self.assertEqual(verdict["status"], "vetoed")
        self.assertTrue(verdict["reason"]["zh"])
        self.assertTrue(verdict["reason"]["en"])

    def test_locked_rules_are_bilingual(self):
        profile = {"comfort_preferences": {"max_ac_setpoint": 25, "sleep_needs_ac": True},
                   "goals": {"monthly_saving_target_pct": 10}}
        rules = locked_rules(profile)
        self.assertTrue(rules)
        for rule in rules:
            self.assertIn("zh", rule["label"])
            self.assertIn("en", rule["label"])


class TestRoles(unittest.TestCase):
    def test_seven_roles_exactly(self):
        """对外宣称七个 agent，代码里就必须正好是七个。"""
        self.assertEqual(len(ROLES), 7)

    def test_every_tool_is_owned_by_a_role(self):
        """加了新工具却忘了归属，会让'七个 agent'的说法与实现脱节。"""
        check = validate_coverage(TOOL_DEFINITIONS)
        self.assertTrue(check["ok"],
                        f"未认领：{check['unassigned_tools']}，幽灵：{check['phantom_tools']}")

    def test_exactly_one_role_holds_veto(self):
        self.assertEqual(sum(1 for r in ROLES if r["veto"]), 1)

    def test_role_lookup(self):
        self.assertEqual(role_of_tool("disaggregate_usage"), "load_detective")
        self.assertEqual(role_of_tool("不存在的工具"), "orchestrator")


if __name__ == "__main__":
    unittest.main()
