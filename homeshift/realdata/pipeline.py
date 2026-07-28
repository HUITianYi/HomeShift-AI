"""真实数据接入流水线：一条命令从"什么都没有"到"系统可用"。

整体流程
---------------------------------------------------------------------------
  1. 下载原始数据集（多镜像 + 断点续传 + 缓存）
  2. 解析并重采样到半小时（流式，不吃内存）
  3. 按数据质量挑选一个连续的演示窗口（默认 63 天）
  4. 拉取该窗口、该地点的真实气温（Open-Meteo / data.gov.sg）
  5. 写入 data/usage.csv、data/weather.csv、data/usage_groundtruth.csv
  6. 从真实数据反推家庭画像（用电水平、作息、是否有夜间制冷等）
  7. 写入 data/provenance.json（数据出处与质量报告，答辩可直接引用）
  8. 把地区/电价/碳因子写回 config.json，让下游计算自动对齐
---------------------------------------------------------------------------

为什么要"挑窗口"而不是用全部数据：
真实数据集动辄好几年，全量塞进 Agent 上下文既慢又贵，也不符合"最近一个月
诊断 + 一周复盘"的产品场景。这里自动挑选缺失最少、最近的一段连续数据。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from ..config import save_config_patch
from .download import download_file, extract_member
from .loaders import LOADERS
from .sources import get_dataset
from .weather import fetch_weather_for_slots

TS_FORMAT = "%Y-%m-%dT%H:%M"


# ===========================================================================
# 主入口
# ===========================================================================

def build_real_dataset(
    ctx,
    dataset: str = "uci",
    window_days: int | None = None,
    file_path: str | None = None,
    weather_source: str | None = None,
    loader_kwargs: dict | None = None,
    keep_config: bool = False,
) -> dict:
    """下载 + 处理 + 写入。返回一份摘要（同时存为 data/provenance.json）。"""
    cfg = ctx.config
    rd_cfg = cfg.get("realdata", {})
    window_days = window_days or rd_cfg.get("window_days", 63)
    weather_source = weather_source or rd_cfg.get("weather_source", "openmeteo")
    cache_dir = ctx.root / rd_cfg.get("cache_dir", "data/raw")
    timeout = rd_cfg.get("download_timeout_seconds", 600)

    meta = get_dataset(dataset)
    print(f"\n[1/8] 数据集：{meta['title']}")
    print(f"      {meta['short']}")
    print(f"      许可：{meta['license']}")

    # ---------- 1. 拿到原始文件 ----------
    if meta.get("manual") or file_path:
        if not file_path:
            raise SystemExit(
                f"\n数据集 '{dataset}' 需要你手工提供文件。\n\n{meta.get('manual_hint', '')}\n"
            )
        raw_path = Path(file_path)
        if not raw_path.is_absolute():
            raw_path = (ctx.root / raw_path).resolve()
        if not raw_path.exists():
            raise SystemExit(f"文件不存在：{raw_path}")
        print(f"\n[2/8] 使用本地文件：{raw_path}")
    else:
        print(f"\n[2/8] 下载原始数据（约 {meta.get('approx_size_mb', '?')} MB，首次较慢）")
        archive = download_file(
            meta["urls"], cache_dir / meta["archive_name"], timeout=timeout, label="下载"
        )
        raw_path = extract_member(archive, meta["member"], cache_dir)

    # ---------- 2. 解析 ----------
    print(f"\n[3/8] 解析并重采样到半小时粒度")
    loader = LOADERS[meta["loader"]]
    parsed = loader(raw_path, **(loader_kwargs or {}))
    stats = parsed["stats"]
    print(f"      原始行数 {stats['raw_rows']:,}，缺失 {stats['raw_missing_pct']}%")
    print(f"      产出半小时时段 {stats['half_hour_slots']:,} 个")
    if not parsed["usage"]:
        raise SystemExit(
            f"\n[无法使用] {stats.get('warning', '解析后没有任何可用数据')}\n"
            "请换一个数据集，或检查原始文件是否完整："
            "python fetch_real_data.py --list"
        )
    print(f"      覆盖范围 {stats['period_start']} ~ {stats['period_end']}")

    # ---------- 3. 挑窗口 ----------
    print(f"\n[4/8] 挑选连续的演示窗口（目标 {window_days} 天）")
    window = select_window(parsed["usage"], window_days)
    print(f"      选中 {window['start']} ~ {window['end']}"
          f"（{window['days']} 天，完整度 {window['completeness_pct']}%）")
    usage = window["usage"]
    slots = [ts for ts, _ in usage]
    truth = [row for row in parsed["truth"]
             if window["start"] <= row["timestamp"].date() <= window["end"]]

    # ---------- 4. 地区信息 ----------
    region = meta.get("region") or cfg.get("region", {})
    lat = region.get("latitude", 1.3521)
    lon = region.get("longitude", 103.8198)

    # ---------- 5. 天气 ----------
    print(f"\n[5/8] 获取该时段该地点的真实气温（{weather_source}）")
    try:
        weather, weather_meta = fetch_weather_for_slots(
            slots, lat, lon, source=weather_source, timeout=timeout
        )
    except Exception as exc:  # noqa: BLE001
        print(f"      [警告] 天气获取失败：{exc}")
        print("      将继续写入用电数据；天气归一化功能会降级（诊断/计划仍可用）。")
        weather, weather_meta = [], {"source": "failed", "error": str(exc)}

    # ---------- 6. 写文件 ----------
    print(f"\n[6/8] 写入项目数据目录 {ctx.data_dir}")
    ctx.data_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(ctx.data_dir / "usage.csv", ["timestamp", "kwh"],
               [[ts.strftime(TS_FORMAT), f"{v:.4f}"] for ts, v in usage])
    print(f"      usage.csv   {len(usage):,} 行")

    if weather:
        _write_csv(ctx.data_dir / "weather.csv", ["timestamp", "temp_c"],
                   [[ts.strftime(TS_FORMAT), f"{v:.2f}"] for ts, v in weather])
        print(f"      weather.csv {len(weather):,} 行")

    truth_columns = parsed.get("truth_columns") or []
    gt_path = ctx.data_dir / "usage_groundtruth.csv"
    if truth and truth_columns:
        _write_csv(gt_path, ["timestamp"] + truth_columns,
                   [[row["timestamp"].strftime(TS_FORMAT)]
                    + [f"{row.get(c, 0.0):.4f}" for c in truth_columns] for row in truth])
        print(f"      usage_groundtruth.csv {len(truth):,} 行（{len(truth_columns)} 路分表）")
    else:
        # 真实家庭没有分表真值：删掉旧的合成真值，避免拿假真值评估真数据
        if gt_path.exists():
            gt_path.unlink()
        print("      无分表真值（真实家庭只有总表，这是正常的）")

    # ---------- 7. 画像 ----------
    print(f"\n[7/8] 从真实数据反推家庭画像")
    profile = infer_profile(usage, weather, meta, window)
    ctx.store.save_profile(profile)
    print(f"      日均用电 {profile['observed']['avg_daily_kwh']} kWh，"
          f"夜间占比 {profile['observed']['night_share_pct']}%")
    print(f"      推断作息：{profile['household']}")

    # 真实数据换了家庭，旧的计划/记忆/复盘不再适用，清掉避免张冠李戴
    _reset_derived_state(ctx)

    # ---------- 8. 出处与配置 ----------
    print(f"\n[8/8] 写入数据出处 provenance.json 并同步配置")
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_kind": "real",
        "dataset": {
            "id": meta["id"], "title": meta["title"], "license": meta["license"],
            "citation": meta["citation"], "period_available": meta.get("period"),
            "source_urls": meta.get("urls", []),
            "raw_resolution_minutes": meta.get("raw_resolution_minutes"),
        },
        "window": {k: v for k, v in window.items() if k != "usage"},
        "parse_stats": stats,
        "weather": weather_meta,
        "region": region,
        "category_map": meta.get("category_map", {}),
        "truth_notes": meta.get("truth_notes", []),
        "known_limitations": _limitations(meta, window, weather_meta),
    }
    with open(ctx.data_dir / "provenance.json", "w", encoding="utf-8") as f:
        json.dump(provenance, f, ensure_ascii=False, indent=2, default=str)

    if not keep_config and meta.get("region"):
        patch = {"region": meta["region"]}
        if meta.get("tariff"):
            patch["tariff"] = meta["tariff"]
        if meta.get("carbon"):
            patch["carbon"] = meta["carbon"]
        if meta["region"].get("climate") == "temperate":
            patch["disaggregation"] = {"cdh_base_c": 18.0}
        path = save_config_patch(patch, ctx.root)
        print(f"      已把地区/电价/碳因子写入 {path.name}")
        print(f"      货币切换为 {meta['region']['currency']}，"
              f"气候模式 {meta['region']['climate']}")

    print("\n完成。下一步：")
    print("  python -m homeshift status      # 确认数据已就位")
    print("  python -m homeshift diagnose    # 让 Agent 诊断真实数据")
    return provenance


# ===========================================================================
# 窗口挑选
# ===========================================================================

def select_window(usage: list[tuple[datetime, float]], window_days: int) -> dict:
    """挑一段"最近的、完整度最高的"连续窗口。

    完整度 = 实际半小时时段数 / 应有时段数(48 * 天数)。
    做法：按天聚合，从最后一天往前滑动，找第一个完整度 >= 90% 的窗口；
    找不到就退而求其次，返回完整度最高的那个。
    """
    if not usage:
        raise ValueError("没有可用的用电数据")

    by_day: dict[date, int] = {}
    for ts, _ in usage:
        by_day[ts.date()] = by_day.get(ts.date(), 0) + 1
    all_days = sorted(by_day)

    if len(all_days) <= window_days:
        chosen_start, chosen_end = all_days[0], all_days[-1]
    else:
        best = None
        end_index = len(all_days) - 1
        while end_index - window_days + 1 >= 0:
            start_index = end_index - window_days + 1
            start_day = all_days[start_index]
            end_day = all_days[end_index]
            # 必须是日历上连续的
            calendar_days = (end_day - start_day).days + 1
            slots = sum(by_day.get(start_day + timedelta(days=i), 0)
                        for i in range(calendar_days))
            completeness = slots / (48 * calendar_days)
            if best is None or completeness > best[0]:
                best = (completeness, start_day, end_day)
            if completeness >= 0.90:
                break
            end_index -= 7  # 每次往前挪一周，避免 O(n^2)
        chosen_start, chosen_end = best[1], best[2]

    selected = [(ts, v) for ts, v in usage if chosen_start <= ts.date() <= chosen_end]
    calendar_days = (chosen_end - chosen_start).days + 1
    completeness = len(selected) / (48 * calendar_days) if calendar_days else 0

    return {
        "start": chosen_start,
        "end": chosen_end,
        "days": calendar_days,
        "slots": len(selected),
        "expected_slots": 48 * calendar_days,
        "completeness_pct": round(100 * completeness, 1),
        "usage": selected,
    }


# ===========================================================================
# 从真实数据反推画像
# ===========================================================================

def infer_profile(
    usage: list[tuple[datetime, float]],
    weather: list[tuple[datetime, float]],
    meta: dict,
    window: dict,
) -> dict:
    """真实数据集不会附带"这家人几点睡觉"，只能从用电曲线反推。

    反推的每一项都标注了依据，Agent 读到画像时能知道哪些是观测、哪些是假设。
    这比直接编一个画像诚实得多，也是答辩时值得讲的一点。
    """
    daily: dict[date, float] = {}
    slot_profile: dict[int, list[float]] = {}
    for ts, kwh in usage:
        daily[ts.date()] = daily.get(ts.date(), 0.0) + kwh
        slot = ts.hour * 2 + (1 if ts.minute >= 30 else 0)
        slot_profile.setdefault(slot, []).append(kwh)

    avg_daily = sum(daily.values()) / max(len(daily), 1)
    slot_avg = {s: sum(v) / len(v) for s, v in slot_profile.items()}

    peak_slot = max(slot_avg, key=slot_avg.get) if slot_avg else 40
    peak_time = f"{peak_slot // 2:02d}:{'30' if peak_slot % 2 else '00'}"

    night_slots = [s for s in slot_avg if s >= 44 or s < 15]     # 22:00-07:30
    day_slots = [s for s in slot_avg if 18 <= s < 32]            # 09:00-16:00
    night_kwh = sum(slot_avg[s] for s in night_slots) * 0.5 if night_slots else 0
    total_avg = sum(slot_avg.values()) if slot_avg else 1
    night_share = 100 * sum(slot_avg[s] for s in night_slots) / total_avg if total_avg else 0

    baseline_slot = min(slot_avg.values()) if slot_avg else 0
    baseline_daily = baseline_slot * 48

    # 白天是否有人：白天均值明显高于基线 -> 可能居家办公
    day_avg = sum(slot_avg[s] for s in day_slots) / len(day_slots) if day_slots else 0
    wfh_likely = day_avg > baseline_slot * 1.6

    climate = (meta.get("region") or {}).get("climate", "tropical")
    thermal_label = "空调制冷" if climate == "tropical" else "供暖/制冷"

    avg_temp = (sum(v for _, v in weather) / len(weather)) if weather else None

    household = (
        f"从用电曲线反推：用电高峰在 {peak_time}，"
        + ("白天在家（居家办公可能性高）" if wfh_likely else "白天多数时间不在家")
        + f"，夜间用电占全天 {night_share:.0f}%"
    )

    return {
        "home_type": meta.get("region", {}).get("name", "未知住宅"),
        "location": meta.get("region", {}).get("name", "-"),
        "household": household,
        "data_source": "real",
        "dataset_id": meta["id"],
        # ---- 观测到的事实（来自真实数据，不是假设）----
        "observed": {
            "period": {"start": str(window["start"]), "end": str(window["end"])},
            "days": window["days"],
            "avg_daily_kwh": round(avg_daily, 2),
            "max_daily_kwh": round(max(daily.values()), 2) if daily else 0,
            "min_daily_kwh": round(min(daily.values()), 2) if daily else 0,
            "peak_half_hour": peak_time,
            "night_share_pct": round(night_share, 1),
            "baseline_daily_kwh": round(baseline_daily, 2),
            "avg_outdoor_temp_c": round(avg_temp, 1) if avg_temp is not None else None,
            "wfh_likely": wfh_likely,
        },
        # ---- 需要用户确认的假设（Agent 会在报告里标注）----
        "assumptions": [
            "电器清单来自数据集文档，不是用户自述",
            "作息由用电曲线反推，可能与实际有出入",
            "舒适约束为默认值，真实使用时应由用户填写",
        ],
        "major_appliances": _appliances_from_meta(meta),
        "ac_setpoint": 24,
        "heater_mode": "always_on" if climate == "tropical" else "unknown",
        "wash_mode": "warm",
        "comfort_preferences": {
            "sleep_needs_ac": climate == "tropical",
            "max_ac_setpoint": 26,
            "notes": f"默认约束（真实用户应自行设定）：{thermal_label}以睡眠舒适为底线",
        },
        "goals": {
            "monthly_saving_target_pct": 10,
            "priority": "省钱优先，不牺牲睡眠舒适度",
        },
    }


def _appliances_from_meta(meta: dict) -> list[dict]:
    notes = meta.get("truth_notes") or []
    if notes:
        return [{"name": "（依据数据集分表文档）", "note": n} for n in notes]
    return [{"name": "未知（仅有总表数据）",
             "note": "真实场景下电器清单需由用户填写或由负载分解推断"}]


# ===========================================================================
# 辅助
# ===========================================================================

def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    import csv as _csv

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = _csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def _reset_derived_state(ctx) -> None:
    """换数据源后清空所有属于旧家庭的派生状态，避免跨家庭串线。"""
    for name in (
        "plans.json",
        "memory.json",
        "reviews.json",
        "last_trace.json",
        "tracking_meta.json",
        "report.html",
    ):
        path = ctx.data_dir / name
        if path.exists():
            path.unlink()


def _limitations(meta: dict, window: dict, weather_meta: dict) -> list[str]:
    out = [
        f"数据完整度 {window['completeness_pct']}%，缺失时段未做插值填补（避免虚构用电）",
    ]
    climate = (meta.get("region") or {}).get("climate")
    if climate == "temperate":
        out.append(
            "该数据集来自温带地区，本项目的负载分解启发式最初按热带（全年制冷）"
            "假设设计；在温带数据上 aircon 类别实际混合了采暖与其他负载，"
            "eval-disagg 的结果应据此解读"
        )
    if not meta.get("category_map"):
        out.append("该数据源没有分电器真值，负载分解精度无法定量验证（真实场景的常态）")
    if weather_meta.get("source") == "failed":
        out.append("天气数据获取失败，天气归一化不可用，复盘结论未剔除气温影响")
    return out
