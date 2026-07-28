#!/usr/bin/env python3
"""HomeShift AI —— 真实数据一键接入脚本

这个脚本做的事（全自动，不需要你懂数据处理）：
  下载真实公开数据集 -> 解析成半小时用电 -> 拉取同地点同时段的真实气温
  -> 挑一段干净的演示窗口 -> 反推家庭画像 -> 写入 data/ -> 同步配置

最简单的用法（什么都不用想，直接跑）：
    python fetch_real_data.py

跑完之后：
    python -m homeshift status
    python -m homeshift diagnose
    python -m homeshift plan
    python -m homeshift export-web

------------------------------------------------------------------------
其他用法
------------------------------------------------------------------------
看看有哪些数据集可选：
    python fetch_real_data.py --list

只跑一遍完整流程但不改 config.json（保留你自己的电价设置）：
    python fetch_real_data.py --keep-config

用你自己家的电表 CSV（SP Group 导出的那种）：
    python fetch_real_data.py --dataset spgroup --file data/raw/my_meter.csv

用任意 CSV（自动认列名，认不出就手工指定）：
    python fetch_real_data.py --dataset csv --file 路径.csv \
        --time-col "Reading Date" --value-col "kWh" --value-unit kwh

改窗口长度 / 换天气源 / 只用新加坡气温：
    python fetch_real_data.py --days 90
    python fetch_real_data.py --weather datagovsg
    python fetch_real_data.py --weather none

网络不通时（比如需要代理）：
    macOS/Linux:  export HTTPS_PROXY=http://127.0.0.1:7890
    Windows PS :  $env:HTTPS_PROXY="http://127.0.0.1:7890"
    然后重新运行本脚本即可（已下载的部分会自动续传）。
------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from homeshift.context import AppContext                    # noqa: E402
from homeshift.realdata.pipeline import build_real_dataset  # noqa: E402
from homeshift.realdata.sources import DATASETS             # noqa: E402


BANNER = r"""
==========================================================
  HomeShift AI  ·  真实数据接入
  Cut bills, not comfort
==========================================================
"""


def print_datasets() -> None:
    print("\n可用的数据集：\n")
    for name, meta in DATASETS.items():
        flag = "需手工提供文件" if meta.get("manual") else "自动下载"
        print(f"  {name:<10} {meta['short']}")
        print(f"  {'':<10} [{flag}] 许可：{meta['license']}")
        print(f"  {'':<10} 适合：{meta['recommended_for']}")
        if meta.get("period"):
            print(f"  {'':<10} 数据期间：{meta['period']}")
        print()
    print("默认使用 uci —— 它是唯一免密钥、自带分电器真值的公开数据集，")
    print("可以定量验证我们的负载分解算法到底准不准。\n")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="python fetch_real_data.py",
        description="下载并自动处理真实用电数据，写入 HomeShift AI 项目",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="不带任何参数直接运行即可完成全流程。",
    )
    parser.add_argument("--list", action="store_true", help="列出可用数据集后退出")
    parser.add_argument("--dataset", default=None,
                        help=f"数据集名称，可选：{'、'.join(DATASETS)}（默认 uci）")
    parser.add_argument("--file", default=None, help="本地原始文件路径（csv/spgroup 用）")
    parser.add_argument("--days", type=int, default=None, help="演示窗口天数（默认 63）")
    parser.add_argument("--weather", default=None,
                        choices=["openmeteo", "datagovsg", "none"],
                        help="气温来源（默认 openmeteo，全球通用免密钥）")
    parser.add_argument("--keep-config", action="store_true",
                        help="不要自动改写 config.json 的地区/电价/碳因子")
    # 通用 CSV 的列指定
    parser.add_argument("--time-col", default=None, help="时间列名（认不出来时手工指定）")
    parser.add_argument("--value-col", default=None, help="用电量列名")
    parser.add_argument("--value-unit", default="kwh", choices=["kwh", "wh", "kw", "w"],
                        help="用电列的单位（默认 kwh）")
    parser.add_argument("--time-format", default=None,
                        help="时间格式，如 %%d/%%m/%%Y %%H:%%M（一般不用填）")

    args = parser.parse_args()

    if args.list:
        print_datasets()
        return

    print(BANNER)
    ctx = AppContext()
    dataset = args.dataset or ctx.config.get("realdata", {}).get("dataset", "uci")

    loader_kwargs = {}
    if args.time_col:
        loader_kwargs["time_col"] = args.time_col
    if args.value_col:
        loader_kwargs["value_col"] = args.value_col
    if args.value_unit:
        loader_kwargs["value_unit"] = args.value_unit
    if args.time_format:
        loader_kwargs["time_format"] = args.time_format

    try:
        build_real_dataset(
            ctx,
            dataset=dataset,
            window_days=args.days,
            file_path=args.file,
            weather_source=args.weather,
            loader_kwargs=loader_kwargs,
            keep_config=args.keep_config,
        )
    except KeyboardInterrupt:
        print("\n\n已中断。已下载的部分保留在 data/raw/，下次运行会自动续传。")
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"\n[失败] {exc}\n")
        print("常见排查：")
        print("  1. 网络问题 -> 设置 HTTPS_PROXY 后重试")
        print("  2. 想换数据集 -> python fetch_real_data.py --list")
        print("  3. 只想先看系统能不能跑 -> python -m homeshift init（生成合成数据）")
        sys.exit(1)


if __name__ == "__main__":
    main()
