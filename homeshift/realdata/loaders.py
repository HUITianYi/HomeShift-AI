"""数据集解析器：把各种原始格式统一成本项目的半小时粒度结构。

统一输出（所有 loader 都返回这个结构）：
{
  "usage":  [(datetime, kwh), ...],          # 半小时总表
  "truth":  [{"timestamp": dt, "<分表名>": kwh, ...}, ...],   # 分表真值，可为空
  "truth_columns": ["sub_metering_1", ...],
  "stats":  {...},                            # 数据质量统计（缺失率等）
}

实现原则：
- 流式解析，不把 127MB 原始文件整个读进内存，也不依赖 pandas；
- 缺失值如实统计并报告，不悄悄填 0（那会让"节省"算错）；
- 半小时聚合时记录每个时段实际有几个样本，样本太少的时段标记为不可信。
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

HALF_HOUR = timedelta(minutes=30)


def _floor_half_hour(ts: datetime) -> datetime:
    return ts.replace(minute=0 if ts.minute < 30 else 30, second=0, microsecond=0)


# ===========================================================================
# UCI Individual Household Electric Power Consumption
# ===========================================================================

UCI_EXPECTED_HEADER = [
    "Date", "Time", "Global_active_power", "Global_reactive_power",
    "Voltage", "Global_intensity", "Sub_metering_1", "Sub_metering_2", "Sub_metering_3",
]


def load_uci(path: Path, progress: bool = True, **_ignored) -> dict:
    """解析 UCI 家庭用电数据（1 分钟粒度，分号分隔，缺失值为 '?'）。

    单位换算：
    - Global_active_power 是"分钟平均有功功率(kW)" -> 该分钟能量 = kW / 60 (kWh)
    - Sub_metering_* 单位是 Wh/分钟 -> /1000 得 kWh
    - 未计量部分 = 总量 - 三路分表（UCI 官方文档给出的口径）
    """
    path = Path(path)
    buckets: dict[datetime, dict] = {}

    total_rows = 0
    missing_rows = 0

    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)
        header = [h.strip() for h in header]
        if header[:2] != ["Date", "Time"]:
            raise ValueError(
                f"这个文件的表头不像 UCI 数据集：{header[:4]}。"
                "如果你用的是别的数据集，请改用 --dataset csv"
            )

        for row in reader:
            total_rows += 1
            if progress and total_rows % 400_000 == 0:
                print(f"  已解析 {total_rows:,} 行 ...")
            if len(row) < 9:
                missing_rows += 1
                continue
            gap = row[2].strip()
            if gap == "?" or gap == "":
                missing_rows += 1
                continue
            try:
                ts = datetime.strptime(f"{row[0].strip()} {row[1].strip()}", "%d/%m/%Y %H:%M:%S")
                kw = float(gap)
            except ValueError:
                missing_rows += 1
                continue

            kwh = kw / 60.0
            s1 = _safe_float(row[6]) / 1000.0
            s2 = _safe_float(row[7]) / 1000.0
            s3 = _safe_float(row[8]) / 1000.0
            # UCI 官方说明：未计量能耗 = 总有功(Wh) - 三路分表(Wh)
            unmetered = max(0.0, kwh - (s1 + s2 + s3))

            slot = _floor_half_hour(ts)
            b = buckets.get(slot)
            if b is None:
                b = buckets[slot] = {
                    "kwh": 0.0, "sub_metering_1": 0.0, "sub_metering_2": 0.0,
                    "sub_metering_3": 0.0, "unmetered": 0.0, "n": 0,
                }
            b["kwh"] += kwh
            b["sub_metering_1"] += s1
            b["sub_metering_2"] += s2
            b["sub_metering_3"] += s3
            b["unmetered"] += unmetered
            b["n"] += 1

    if not buckets:
        raise ValueError("没有解析出任何有效数据，请检查文件是否完整。")

    # 一个完整的半小时应有 30 个 1 分钟样本；少于 20 个视为不可信，丢弃
    MIN_SAMPLES = 20
    usable = {ts: b for ts, b in buckets.items() if b["n"] >= MIN_SAMPLES}
    dropped = len(buckets) - len(usable)

    slots = sorted(usable)
    usage = [(ts, round(usable[ts]["kwh"], 4)) for ts in slots]
    truth_columns = ["sub_metering_1", "sub_metering_2", "sub_metering_3", "unmetered"]
    truth = [
        {"timestamp": ts, **{c: round(usable[ts][c], 4) for c in truth_columns}}
        for ts in slots
    ]

    stats = {
        "raw_rows": total_rows,
        "raw_missing_rows": missing_rows,
        "raw_missing_pct": round(100 * missing_rows / max(total_rows, 1), 2),
        "half_hour_slots": len(usable),
        "slots_dropped_incomplete": dropped,
        # 全部时段都因样本不足被丢弃时（缺失率极高的数据），这里会是 None，
        # 由上层给出"这份数据不可用"的提示，而不是抛 IndexError。
        "period_start": slots[0].isoformat() if slots else None,
        "period_end": slots[-1].isoformat() if slots else None,
    }
    if not slots:
        stats["warning"] = (
            f"所有半小时时段的样本都少于 {MIN_SAMPLES} 个，数据缺失过于严重，无法使用。"
        )
    return {"usage": usage, "truth": truth, "truth_columns": truth_columns, "stats": stats}


def _safe_float(value: str) -> float:
    value = (value or "").strip()
    if not value or value == "?":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


# ===========================================================================
# 通用 CSV（SP Group 导出 / Ausgrid / 学校给的任意数据）
# ===========================================================================

# 常见列名（大小写不敏感），用于自动识别
TIME_HINTS = ["timestamp", "datetime", "date_time", "time", "date", "reading_date",
              "interval_start", "period_start", "起始时间", "时间", "日期"]
VALUE_HINTS = ["kwh", "consumption", "usage", "energy", "value", "reading",
               "general_supply_kwh", "electricity", "用电量", "电量", "kw", "power"]


def load_generic_csv(
    path: Path,
    time_col: str | None = None,
    value_col: str | None = None,
    value_unit: str = "kwh",
    time_format: str | None = None,
    resample: bool = True,
    **_ignored,
) -> dict:
    """导入任意"时间 + 用电量"两列的 CSV，自动识别列名与时间格式。

    value_unit:
      kwh -> 该时段的能量（直接累加）
      wh  -> 瓦时（/1000）
      kw  -> 该时刻的平均功率（按时段长度换算成能量）
      w   -> 瓦（/1000 后按时长换算）
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        fieldnames = [(h or "").strip() for h in (reader.fieldnames or [])]
        if not fieldnames:
            raise ValueError(f"{path.name} 没有表头，无法导入。")

        tcol = time_col or _guess_column(fieldnames, TIME_HINTS)
        vcol = value_col or _guess_column(fieldnames, VALUE_HINTS, exclude=[tcol])
        if tcol is None or vcol is None:
            raise ValueError(
                f"无法自动识别时间列/用电列。该文件的列名是：{fieldnames}\n"
                "请用 --time-col 和 --value-col 手工指定。"
            )
        print(f"  识别到：时间列='{tcol}'  用电列='{vcol}'  单位={value_unit}")

        records: list[tuple[datetime, float]] = []
        bad = 0
        for row in reader:
            raw_ts = (row.get(tcol) or "").strip()
            raw_val = (row.get(vcol) or "").strip()
            if not raw_ts or not raw_val:
                bad += 1
                continue
            ts = _parse_timestamp(raw_ts, time_format)
            if ts is None:
                bad += 1
                continue
            try:
                val = float(raw_val.replace(",", ""))
            except ValueError:
                bad += 1
                continue
            records.append((ts, val))

    if not records:
        raise ValueError(f"{path.name} 里没有解析出有效数据行（跳过了 {bad} 行）。")

    records.sort(key=lambda item: item[0])

    # 推断原始采样间隔
    step_minutes = _infer_step_minutes(records)
    unit = value_unit.lower()
    if unit == "wh":
        records = [(ts, v / 1000.0) for ts, v in records]
    elif unit == "kw":
        records = [(ts, v * step_minutes / 60.0) for ts, v in records]
    elif unit == "w":
        records = [(ts, v / 1000.0 * step_minutes / 60.0) for ts, v in records]

    if resample:
        buckets: dict[datetime, float] = {}
        counts: dict[datetime, int] = {}
        for ts, kwh in records:
            slot = _floor_half_hour(ts)
            buckets[slot] = buckets.get(slot, 0.0) + kwh
            counts[slot] = counts.get(slot, 0) + 1
        slots = sorted(buckets)
        usage = [(ts, round(buckets[ts], 4)) for ts in slots]
    else:
        usage = [(ts, round(v, 4)) for ts, v in records]
        slots = [ts for ts, _ in usage]

    stats = {
        "raw_rows": len(records) + bad,
        "raw_missing_rows": bad,
        "raw_missing_pct": round(100 * bad / max(len(records) + bad, 1), 2),
        "inferred_step_minutes": step_minutes,
        "half_hour_slots": len(usage),
        "slots_dropped_incomplete": 0,
        "period_start": slots[0].isoformat(),
        "period_end": slots[-1].isoformat(),
    }
    return {"usage": usage, "truth": [], "truth_columns": [], "stats": stats}


def _guess_column(fieldnames: list[str], hints: list[str],
                  exclude: list | None = None) -> str | None:
    exclude = [e for e in (exclude or []) if e]
    candidates = [f for f in fieldnames if f not in exclude]
    lowered = {f: f.lower() for f in candidates}
    # 先找完全相等，再找包含
    for hint in hints:
        for field, low in lowered.items():
            if low == hint:
                return field
    for hint in hints:
        for field, low in lowered.items():
            if hint in low:
                return field
    return None


TIME_FORMATS = [
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y%m%d%H%M",
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
]


def _parse_timestamp(raw: str, explicit_format: str | None = None) -> datetime | None:
    raw = raw.strip().replace("Z", "").split("+")[0].strip()
    if explicit_format:
        try:
            return datetime.strptime(raw, explicit_format)
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    # Unix 时间戳
    try:
        num = float(raw)
        if num > 1e11:
            num /= 1000.0
        if 9e8 < num < 4e9:
            return datetime.fromtimestamp(num)
    except ValueError:
        pass
    return None


def _infer_step_minutes(records: list[tuple[datetime, float]]) -> int:
    """用相邻时间差的众数推断采样间隔。"""
    if len(records) < 3:
        return 30
    deltas: dict[int, int] = {}
    for i in range(1, min(len(records), 500)):
        d = int((records[i][0] - records[i - 1][0]).total_seconds() // 60)
        if 0 < d <= 1440:
            deltas[d] = deltas.get(d, 0) + 1
    if not deltas:
        return 30
    return max(deltas.items(), key=lambda kv: kv[1])[0]


LOADERS = {
    "load_uci": load_uci,
    "load_generic_csv": load_generic_csv,
}
