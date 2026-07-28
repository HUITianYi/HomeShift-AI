"""电价计算。

费率数值来自 config（可被 config.json 覆盖），币种由 config["region"] 决定，
因此接入英国/法国/澳洲的真实数据集时无需改代码，只改配置。
真实电价接口见 connectors/tariff_api.py。

向后兼容：旧配置里的 regulated_rate_sgd_per_kwh / peak_rate_sgd_per_kwh
仍然可用，会被自动识别。
"""

from __future__ import annotations


def _pick(d: dict, *keys, default=0.0):
    """依次尝试多个键名（用于兼容新旧配置字段名）。"""
    for key in keys:
        if key in d:
            return d[key]
    return default


def currency(config: dict) -> dict:
    region = config.get("region", {})
    return {
        "code": region.get("currency", "SGD"),
        "symbol": region.get("currency_symbol", "S$"),
    }


def regulated_rate(config: dict) -> float:
    t = config["tariff"]
    return float(_pick(t, "regulated_rate_per_kwh", "regulated_rate_sgd_per_kwh", default=0.0))


def tou_rates(config: dict) -> tuple[float, float]:
    tou = config["tariff"].get("tou", {})
    peak = float(_pick(tou, "peak_rate_per_kwh", "peak_rate_sgd_per_kwh", default=0.0))
    off = float(_pick(tou, "offpeak_rate_per_kwh", "offpeak_rate_sgd_per_kwh", default=0.0))
    return peak, off


def effective_rate(config: dict) -> float:
    """当前计费方案下的边际电价（每 kWh，不含消费税）。

    TOU 方案返回峰谷简单均值，仅用于粗略估算；逐时段精确计费见 cost_of_usage()。
    """
    if config["tariff"].get("plan") == "tou":
        peak, off = tou_rates(config)
        return (peak + off) / 2
    return regulated_rate(config)


def cost_of_usage(rows: list[tuple], config: dict) -> float:
    """按逐半小时读数精确计费（TOU 下峰谷分别计价）。

    rows: [(datetime, kwh), ...]
    """
    tariff = config["tariff"]
    if tariff.get("plan") != "tou":
        return sum(kwh for _, kwh in rows) * regulated_rate(config)
    peak_rate, off_rate = tou_rates(config)
    tou = tariff.get("tou", {})
    start = tou.get("peak_start_hour", 9)
    end = tou.get("peak_end_hour", 23)
    total = 0.0
    for ts, kwh in rows:
        in_peak = start <= ts.hour < end
        total += kwh * (peak_rate if in_peak else off_rate)
    return total


def monthly_cost(kwh_month: float, config: dict, include_gst: bool = True) -> dict:
    tariff = config["tariff"]
    cur = currency(config)
    energy = kwh_month * effective_rate(config)
    gst = energy * tariff.get("gst_rate", 0.0) if include_gst else 0.0
    return {
        "kwh": round(kwh_month, 1),
        "energy_cost": round(energy, 2),
        "gst": round(gst, 2),
        "total_cost": round(energy + gst, 2),
        # 兼容旧字段名（报表/测试中仍在使用）
        "energy_sgd": round(energy, 2),
        "gst_sgd": round(gst, 2),
        "total_sgd": round(energy + gst, 2),
        "currency": cur["code"],
        "currency_symbol": cur["symbol"],
        "plan": tariff.get("plan"),
        "rate_per_kwh": effective_rate(config),
        "rate_sgd_per_kwh": effective_rate(config),
    }


def tariff_summary(config: dict) -> dict:
    """给智能体看的电价信息（get_tariff_info 工具的返回值）。"""
    tariff = config["tariff"]
    peak, off = tou_rates(config)
    tou = tariff.get("tou", {})
    cur = currency(config)
    return {
        "current_plan": tariff.get("plan"),
        "currency": cur["code"],
        "currency_symbol": cur["symbol"],
        "regulated_rate_per_kwh": regulated_rate(config),
        "regulated_rate_sgd_per_kwh": regulated_rate(config),  # 兼容旧字段
        "tou_option": {
            "peak_rate_per_kwh": peak,
            "offpeak_rate_per_kwh": off,
            "peak_hours": f"{tou.get('peak_start_hour', 9)}:00-{tou.get('peak_end_hour', 23)}:00",
        },
        "gst_rate": tariff.get("gst_rate", 0.0),
        "note": tariff.get("source_note", "费率为配置值，实际以供电商公布为准"),
    }
