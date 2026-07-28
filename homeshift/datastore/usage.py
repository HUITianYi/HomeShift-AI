"""用电与天气数据访问层。

数据文件（均为 CSV，半小时粒度，时间戳为该时段起点）：
- usage.csv             timestamp,kwh            —— 智能电表读数（智能体可见）
- weather.csv           timestamp,temp_c         —— 室外温度
- usage_groundtruth.csv timestamp,<各电器kwh...> —— 分电器真值（仅用于评估
  负载分解精度，智能体不可见，模拟真实场景中 NILM 没有真值的情况）

接真实电表 API 的预留接口见 connectors/meter_api.py。
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

TS_FORMAT = "%Y-%m-%dT%H:%M"


class UsageStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.usage_path = self.data_dir / "usage.csv"
        self.weather_path = self.data_dir / "weather.csv"
        self.groundtruth_path = self.data_dir / "usage_groundtruth.csv"

    # ---------- 基础读取 ----------

    def has_data(self) -> bool:
        return self.usage_path.exists()

    def load_usage(self) -> list[tuple[datetime, float]]:
        """全部电表读数，按时间升序返回 [(时段起点, kWh), ...]。"""
        if not self.usage_path.exists():
            return []
        rows: list[tuple[datetime, float]] = []
        with open(self.usage_path, "r", encoding="utf-8", newline="") as f:
            for record in csv.DictReader(f):
                ts = datetime.strptime(record["timestamp"], TS_FORMAT)
                rows.append((ts, float(record["kwh"])))
        rows.sort(key=lambda item: item[0])
        return rows

    def load_weather(self) -> dict[datetime, float]:
        """{时段起点: 室外温度°C}。"""
        if not self.weather_path.exists():
            return {}
        temps: dict[datetime, float] = {}
        with open(self.weather_path, "r", encoding="utf-8", newline="") as f:
            for record in csv.DictReader(f):
                ts = datetime.strptime(record["timestamp"], TS_FORMAT)
                temps[ts] = float(record["temp_c"])
        return temps

    def load_groundtruth(self) -> list[dict]:
        """分电器真值（仅供 eval-disagg 评估用）。"""
        if not self.groundtruth_path.exists():
            return []
        rows: list[dict] = []
        with open(self.groundtruth_path, "r", encoding="utf-8", newline="") as f:
            for record in csv.DictReader(f):
                if not record.get("timestamp"):
                    continue
                row: dict = {"timestamp": datetime.strptime(record["timestamp"], TS_FORMAT)}
                for key, value in record.items():
                    if key == "timestamp" or key is None:
                        continue
                    # 表头与数据列数不一致时 DictReader 会给出 list，
                    # 这种行是脏数据，跳过而不是让整个流程崩掉
                    if isinstance(value, (list, tuple)) or value in (None, ""):
                        continue
                    try:
                        row[key] = float(value)
                    except (TypeError, ValueError):
                        continue
                rows.append(row)
        rows.sort(key=lambda item: item["timestamp"])
        return rows

    # ---------- 常用切片 ----------

    def date_range(self) -> tuple[date, date] | None:
        rows = self.load_usage()
        if not rows:
            return None
        return rows[0][0].date(), rows[-1][0].date()

    def last_date(self) -> date | None:
        rng = self.date_range()
        return rng[1] if rng else None

    def rows_between(self, start: date, end: date) -> list[tuple[datetime, float]]:
        """[start, end] 闭区间内的读数。"""
        return [(ts, kwh) for ts, kwh in self.load_usage() if start <= ts.date() <= end]

    def last_n_days(self, days: int) -> list[tuple[datetime, float]]:
        last = self.last_date()
        if last is None:
            return []
        start = last - timedelta(days=days - 1)
        return self.rows_between(start, last)

    @staticmethod
    def daily_totals(rows: list[tuple[datetime, float]]) -> dict[date, float]:
        totals: dict[date, float] = {}
        for ts, kwh in rows:
            totals[ts.date()] = totals.get(ts.date(), 0.0) + kwh
        return {d: round(v, 3) for d, v in sorted(totals.items())}

    # ---------- 写入（供数据生成器使用） ----------

    def append_rows(
        self,
        usage_rows: list[tuple[datetime, float]],
        weather_rows: list[tuple[datetime, float]],
        truth_rows: list[dict],
        appliance_keys: list[str],
    ) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._append_csv(
            self.usage_path,
            ["timestamp", "kwh"],
            [[ts.strftime(TS_FORMAT), f"{kwh:.4f}"] for ts, kwh in usage_rows],
        )
        self._append_csv(
            self.weather_path,
            ["timestamp", "temp_c"],
            [[ts.strftime(TS_FORMAT), f"{t:.2f}"] for ts, t in weather_rows],
        )
        # 分电器真值：只有当既有文件的表头与本次写入一致时才追加。
        # 真实数据集的分表口径（如 UCI 的 sub_metering_*）与合成数据的电器名
        # 完全不同，混写会产出一个谁也读不了的文件。
        truth_header = ["timestamp"] + appliance_keys
        if self._header_conflicts(self.groundtruth_path, truth_header):
            print("  [提示] 现有分电器真值来自其他数据源，表头不一致，"
                  "本次不写入合成真值（eval-disagg 仍使用原有真值）。")
            return
        truth_records = []
        for row in truth_rows:
            record = [row["timestamp"].strftime(TS_FORMAT)]
            record += [f"{row.get(key, 0.0):.4f}" for key in appliance_keys]
            truth_records.append(record)
        self._append_csv(self.groundtruth_path, truth_header, truth_records)

    @staticmethod
    def _header_conflicts(path: Path, header: list[str]) -> bool:
        if not path.exists():
            return False
        with open(path, "r", encoding="utf-8", newline="") as f:
            existing = next(csv.reader(f), [])
        return [h.strip() for h in existing] != header

    @staticmethod
    def _append_csv(path: Path, header: list[str], records: list[list[str]]) -> None:
        exists = path.exists()
        with open(path, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(header)
            writer.writerows(records)
