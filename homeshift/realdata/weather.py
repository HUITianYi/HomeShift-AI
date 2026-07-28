"""真实气温数据获取。

两个来源，都不需要 API 密钥：

1. Open-Meteo Historical Weather API（推荐，全球通用）
   https://archive-api.open-meteo.com/v1/archive
   基于 ERA5 再分析数据，1940 年至今，全球任意坐标，小时粒度，CC BY 4.0。
   —— 这保证了无论用哪个国家的电表数据集，都能拿到"同一地点、同一时间"的
      真实气温，天气归一化才有意义。

2. data.gov.sg 实时气温 API（新加坡本地，逐分钟观测站数据）
   https://api-open.data.gov.sg/v2/real-time-api/air-temperature
   用于接入新加坡真实家庭数据的场景。

小时 -> 半小时：线性插值。气温在半小时尺度上变化平缓，线性插值引入的
误差远小于 ERA5 本身的空间分辨率误差，这一点在文档中如实说明。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .download import DownloadError, fetch_json

OPENMETEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
DATAGOVSG_TEMP = "https://api-open.data.gov.sg/v2/real-time-api/air-temperature"


# ---------------------------------------------------------------------------
# Open-Meteo
# ---------------------------------------------------------------------------

def fetch_openmeteo_hourly(
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    timeout: int = 180,
) -> list[tuple[datetime, float]]:
    """拉取 [start, end] 的逐小时气温（本地时间）。"""
    url = (
        f"{OPENMETEO_ARCHIVE}?latitude={latitude}&longitude={longitude}"
        f"&start_date={start.isoformat()}&end_date={end.isoformat()}"
        f"&hourly=temperature_2m&timezone=auto"
    )
    print(f"  请求 Open-Meteo：{start} ~ {end} @ ({latitude}, {longitude})")
    payload = fetch_json(url, timeout=timeout)

    if payload.get("error"):
        raise DownloadError(f"Open-Meteo 返回错误：{payload.get('reason')}")

    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    if not times:
        raise DownloadError("Open-Meteo 没有返回任何气温数据，请检查日期范围与坐标。")

    out: list[tuple[datetime, float]] = []
    last_valid: float | None = None
    for t, v in zip(times, temps):
        if v is None:
            v = last_valid            # ERA5 极少缺值；万一缺就沿用上一个
            if v is None:
                continue
        last_valid = v
        out.append((datetime.fromisoformat(t), float(v)))
    print(f"  取得 {len(out)} 个小时点，气温范围 "
          f"{min(v for _, v in out):.1f} ~ {max(v for _, v in out):.1f} °C")
    return out


# ---------------------------------------------------------------------------
# data.gov.sg（新加坡）
# ---------------------------------------------------------------------------

def fetch_datagovsg_daily(day: date, timeout: int = 60) -> list[tuple[datetime, float]]:
    """拉取新加坡某一天的观测站气温，返回全岛均值的时间序列。"""
    url = f"{DATAGOVSG_TEMP}?date={day.isoformat()}"
    payload = fetch_json(url, timeout=timeout)
    data = payload.get("data") or {}
    readings = data.get("readings") or []
    out: list[tuple[datetime, float]] = []
    for entry in readings:
        ts_raw = entry.get("timestamp")
        values = entry.get("data") or []
        if not ts_raw or not values:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
        temps = [v.get("value") for v in values if isinstance(v.get("value"), (int, float))]
        if temps:
            out.append((ts, sum(temps) / len(temps)))
    return out


def fetch_datagovsg_range(start: date, end: date, timeout: int = 60
                          ) -> list[tuple[datetime, float]]:
    """逐日拉取新加坡气温（该接口按天查询）。"""
    out: list[tuple[datetime, float]] = []
    day = start
    total = (end - start).days + 1
    index = 0
    while day <= end:
        index += 1
        try:
            out.extend(fetch_datagovsg_daily(day, timeout=timeout))
        except DownloadError as exc:
            print(f"  [跳过] {day}：{exc}")
        if index % 10 == 0:
            print(f"  已拉取 {index}/{total} 天 ...")
        day += timedelta(days=1)
    if not out:
        raise DownloadError("data.gov.sg 没有返回任何数据（该接口通常只保留近期数据）。")
    out.sort(key=lambda item: item[0])
    return out


# ---------------------------------------------------------------------------
# 重采样到半小时
# ---------------------------------------------------------------------------

def to_half_hourly(
    series: list[tuple[datetime, float]],
    slots: list[datetime],
) -> list[tuple[datetime, float]]:
    """把任意粒度的气温序列对齐到给定的半小时时间点（线性插值 + 边界外推）。"""
    if not series:
        return []
    series = sorted(series, key=lambda item: item[0])
    times = [t for t, _ in series]
    values = [v for _, v in series]

    out: list[tuple[datetime, float]] = []
    cursor = 0
    for slot in slots:
        while cursor < len(times) - 2 and times[cursor + 1] <= slot:
            cursor += 1
        if slot <= times[0]:
            out.append((slot, values[0]))
            continue
        if slot >= times[-1]:
            out.append((slot, values[-1]))
            continue
        t0, t1 = times[cursor], times[cursor + 1]
        v0, v1 = values[cursor], values[cursor + 1]
        span = (t1 - t0).total_seconds()
        if span <= 0:
            out.append((slot, v0))
            continue
        ratio = (slot - t0).total_seconds() / span
        out.append((slot, v0 + (v1 - v0) * max(0.0, min(1.0, ratio))))
    return [(t, round(v, 2)) for t, v in out]


def fetch_weather_for_slots(
    slots: list[datetime],
    latitude: float,
    longitude: float,
    source: str = "openmeteo",
    timeout: int = 180,
) -> tuple[list[tuple[datetime, float]], dict]:
    """为一批半小时时间点获取匹配的真实气温。

    返回 (半小时气温序列, 来源元信息)
    """
    if not slots:
        return [], {"source": "none", "reason": "没有用电数据时间点"}
    start = slots[0].date()
    end = slots[-1].date()

    if source == "none":
        return [], {"source": "none", "reason": "配置中关闭了天气获取"}

    if source == "datagovsg":
        series = fetch_datagovsg_range(start, end, timeout=timeout)
        meta = {
            "source": "data.gov.sg real-time air-temperature",
            "url": DATAGOVSG_TEMP,
            "note": "新加坡全岛观测站均值；该接口一般只覆盖近期日期",
        }
    else:
        series = fetch_openmeteo_hourly(latitude, longitude, start, end, timeout=timeout)
        meta = {
            "source": "Open-Meteo Historical Weather API (ERA5)",
            "url": OPENMETEO_ARCHIVE,
            "latitude": latitude,
            "longitude": longitude,
            "license": "CC BY 4.0",
            "note": "小时粒度 ERA5 再分析数据，按线性插值对齐到半小时",
        }

    half = to_half_hourly(series, slots)
    meta["points_raw"] = len(series)
    meta["points_half_hourly"] = len(half)
    meta["period"] = {"start": start.isoformat(), "end": end.isoformat()}
    return half, meta
