"""碳排放换算。

排放因子与其出处说明都来自 config（可被 config.json 覆盖）——
接入不同国家的真实数据时会自动切换（例如法国电网以核电为主，
排放因子约 0.056 kgCO2/kWh，只有新加坡的 1/7）。
实时碳强度 API 的预留接口见 connectors/carbon_api.py。
"""

from __future__ import annotations


def emission_factor(config: dict) -> float:
    return config["carbon"]["grid_emission_factor_kg_per_kwh"]


def co2_kg(kwh: float, config: dict) -> float:
    return round(kwh * emission_factor(config), 2)


def carbon_summary(config: dict) -> dict:
    factor = emission_factor(config)
    carbon_cfg = config.get("carbon", {})
    region = config.get("region", {})
    return {
        "grid_emission_factor_kg_per_kwh": factor,
        "region": region.get("name", "-"),
        # 出处随配置走，不再写死"新加坡"
        "source": carbon_cfg.get("source_note", "配置中的电网平均排放因子"),
        "equivalents": {
            "note": "参考换算：一棵成年树每年约吸收 20 kg CO2",
            "tree_year_kg": 20,
        },
    }
