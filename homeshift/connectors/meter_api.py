"""智能电表数据接口（预留）。

真实接入方案（新加坡）：
- SP Group 的 SP Utilities App 提供半小时粒度用电数据（可导出 CSV）；
- 开放电力市场（OEM）零售商（如 Geneco、Keppel Electric）的 API/门户；
- 自装智能插座/电表（如 Shelly EM、Tuya）通过其云 API 拉取。

接入步骤：
1. 实现 fetch_meter_readings()，返回 [(半小时时段起点 datetime, kWh), ...]
2. 将返回值写入 data/usage.csv（沿用 datastore/usage.py 的格式），或
   直接替换 UsageStore.load_usage() 的数据源。
上层的负载分解、模拟、追踪代码无需任何改动。
"""

from __future__ import annotations

from datetime import date, datetime


def fetch_meter_readings(
    start: date,
    end: date,
    api_key: str | None = None,
) -> list[tuple[datetime, float]]:
    """从真实电表 API 拉取 [start, end] 的半小时用电数据。

    TODO(接入时实现)：
        resp = requests.get(
            "https://<你的电表数据服务>/v1/readings",
            params={"start": start.isoformat(), "end": end.isoformat()},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        return [(datetime.fromisoformat(r["ts"]), r["kwh"]) for r in resp.json()]
    """
    raise NotImplementedError(
        "真实电表 API 尚未接入。演示环境请使用 `python -m homeshift init` 生成合成数据；"
        "接入方法见本模块 docstring。"
    )
