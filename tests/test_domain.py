"""领域计算引擎测试：负载分解、节能模拟、电价/碳换算。"""

from __future__ import annotations

import unittest

from homeshift.domain.disaggregate import CATEGORIES, disaggregate
from homeshift.domain.simulate import candidate_actions
from homeshift.domain.tariff import monthly_cost
from homeshift.domain.carbon import co2_kg

try:
    from .helpers import TempEnv
except ImportError:  # 直接以 discover -s tests 方式运行时
    from helpers import TempEnv


class TestDisaggregate(unittest.TestCase):
    def test_categories_sum_to_total(self):
        with TempEnv() as ctx:
            rows = ctx.usage.last_n_days(28)
            result = disaggregate(rows, ctx.usage.load_weather())
            self.assertEqual(result["days"], 28)
            for day_row in result["daily_series"]:
                assigned = sum(day_row[c] for c in CATEGORIES)
                # 分类之和应等于当日总量（other 兜底），容忍舍入误差
                self.assertAlmostEqual(assigned, day_row["total_kwh"], delta=0.15)

    def test_aircon_is_largest_category(self):
        """空调整晚运行的家庭，负载分解应识别出空调为最大类别。"""
        with TempEnv() as ctx:
            rows = ctx.usage.last_n_days(28)
            result = disaggregate(rows, ctx.usage.load_weather())
            daily = result["daily_avg_kwh"]
            self.assertEqual(max(daily, key=daily.get), "aircon")
            self.assertGreater(result["share_pct"]["aircon"], 35)

    def test_heater_detected(self):
        """always-on 热水器的保温损耗应被识别出可观份额。"""
        with TempEnv() as ctx:
            rows = ctx.usage.last_n_days(28)
            result = disaggregate(rows, ctx.usage.load_weather())
            self.assertGreater(result["daily_avg_kwh"]["water_heater"], 1.0)

    def test_empty_rows(self):
        result = disaggregate([], {})
        self.assertEqual(result["error"], "no_data")


class TestSimulate(unittest.TestCase):
    def test_actions_generated_with_positive_savings(self):
        with TempEnv() as ctx:
            rows = ctx.usage.last_n_days(28)
            disagg = disaggregate(rows, ctx.usage.load_weather())
            profile = ctx.store.get_profile()
            sim = candidate_actions(disagg, profile, ctx.config)
            ids = [a["id"] for a in sim["actions"]]
            # 该画像（24°C 空调 + always-on 热水器 + 温水洗）应触发这些动作
            self.assertIn("ac_setpoint_26", ids)
            self.assertIn("heater_timer", ids)
            self.assertIn("cold_wash", ids)
            for action in sim["actions"]:
                self.assertGreaterEqual(action["est_sgd_per_month"], 0)
            self.assertGreater(sim["potential_total_per_month"]["sgd"], 5)

    def test_ac_saving_formula(self):
        """空调节省 = 空调日均 kWh x 7%/°C x 温差（可复算）。"""
        with TempEnv() as ctx:
            rows = ctx.usage.last_n_days(28)
            disagg = disaggregate(rows, ctx.usage.load_weather())
            profile = ctx.store.get_profile()  # 24°C -> 26°C，delta=2
            sim = candidate_actions(disagg, profile, ctx.config)
            ac = next(a for a in sim["actions"] if a["id"] == "ac_setpoint_26")
            expected = disagg["daily_avg_kwh"]["aircon"] * 0.07 * 2
            self.assertAlmostEqual(ac["est_kwh_per_day"], expected, delta=0.02)

    def test_comfort_constraint_respected(self):
        """用户约束空调最高 25°C 时，目标温度不能是 26°C。"""
        with TempEnv() as ctx:
            profile = ctx.store.get_profile()
            profile["comfort_preferences"]["max_ac_setpoint"] = 25
            ctx.store.save_profile(profile)
            rows = ctx.usage.last_n_days(28)
            disagg = disaggregate(rows, ctx.usage.load_weather())
            sim = candidate_actions(disagg, ctx.store.get_profile(), ctx.config)
            ac = next(a for a in sim["actions"] if a["id"] == "ac_setpoint_26")
            self.assertIn("25", ac["title"])  # 目标被约束到 25°C


class TestTariffCarbon(unittest.TestCase):
    def test_monthly_cost(self):
        cfg = {"tariff": {"plan": "regulated", "regulated_rate_sgd_per_kwh": 0.30,
                          "gst_rate": 0.09,
                          "tou": {"peak_rate_sgd_per_kwh": 0.34,
                                  "offpeak_rate_sgd_per_kwh": 0.22,
                                  "peak_start_hour": 9, "peak_end_hour": 23}}}
        cost = monthly_cost(500, cfg)
        self.assertAlmostEqual(cost["energy_sgd"], 150.0, places=2)
        self.assertAlmostEqual(cost["total_sgd"], 163.5, places=2)

    def test_co2(self):
        cfg = {"carbon": {"grid_emission_factor_kg_per_kwh": 0.412}}
        self.assertAlmostEqual(co2_kg(100, cfg), 41.2, places=1)


if __name__ == "__main__":
    unittest.main()
