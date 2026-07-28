"""电网碳强度接口（预留）。

真实接入方案（新加坡）：
- EMA 每年公布电网排放因子（Grid Emission Factor），人工更新
  config.json 的 carbon.grid_emission_factor_kg_per_kwh 即可；
- 若需要小时级碳强度（新加坡以天然气为主、波动较小），可接
  Electricity Maps API (api.electricitymaps.com) 的 SG 区域数据。
"""

from __future__ import annotations


def fetch_grid_carbon_intensity() -> dict:
    """返回 {"kg_co2_per_kwh": float, "as_of": str}

    TODO(接入时实现)：
        resp = requests.get(
            "https://api.electricitymaps.com/v3/carbon-intensity/latest",
            params={"zone": "SG"},
            headers={"auth-token": os.environ["ELECTRICITYMAPS_TOKEN"]},
            timeout=30,
        )
    """
    raise NotImplementedError(
        "真实碳强度 API 尚未接入。当前使用 config 中的年均排放因子；"
        "接入方法见本模块 docstring。"
    )
