"""电价数据接口（预留）。

真实接入方案（新加坡）：
- 受管制电价：SP Group 每季度公布（spgroup.com.sg），可写爬虫或人工更新
  config.json 的 tariff.regulated_rate_sgd_per_kwh；
- 零售方案比价：Open Electricity Market 价格比较网站
  (compare.openelectricitymarket.sg)；
- 半小时批发电价（WEP）：EMC/EMA 公布，适合评估“错峰”价值。
"""

from __future__ import annotations


def fetch_current_tariff() -> dict:
    """返回 {"regulated_rate_sgd_per_kwh": float, "effective_from": str, ...}

    TODO(接入时实现)：抓取 SP Group 公布页或订阅 OEM 数据源，
    返回后写回 config.json 或直接覆盖 config["tariff"]。
    """
    raise NotImplementedError(
        "真实电价 API 尚未接入。当前使用 config 中的费率；接入方法见本模块 docstring。"
    )
