"""天气数据接口（预留）。

真实接入方案（新加坡）：
- data.gov.sg 实时 API（免费、无需密钥）：
  GET https://api-open.data.gov.sg/v2/real-time-api/air-temperature
- 历史数据：Meteorological Service Singapore (weather.gov.sg) 的
  Historical Daily Records。

接入后将数据写入 data/weather.csv（timestamp,temp_c），
负载分解与天气归一化即自动使用真实温度。
"""

from __future__ import annotations

from datetime import date, datetime


def fetch_temperature(
    start: date,
    end: date,
    station: str = "S24",  # 樟宜观测站
) -> list[tuple[datetime, float]]:
    """拉取 [start, end] 的半小时室外温度。

    TODO(接入时实现)：
        resp = requests.get(
            "https://api-open.data.gov.sg/v2/real-time-api/air-temperature",
            params={"date": start.isoformat()},
            timeout=30,
        )
        # 解析 resp.json()["data"]["readings"]，过滤 station，重采样到半小时
    """
    raise NotImplementedError(
        "真实天气 API 尚未接入。演示环境使用合成天气数据；接入方法见本模块 docstring。"
    )
