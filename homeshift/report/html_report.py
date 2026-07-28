"""HTML 可视化周报：自包含、零依赖、可直接浏览器打开或投屏演示。

内容：关键指标卡片 + 最近 28 天用电趋势（SVG 折线）+ 用电结构
（SVG 条形）+ 当前计划与追踪结果。图表遵循数据可视化规范：
细线条、单色系、文字用墨色 token、网格线弱化、明暗双模式。
"""

from __future__ import annotations

import html
from datetime import date

from ..domain.disaggregate import disaggregate
from ..domain.tariff import monthly_cost
from ..domain.tracker import track_progress

CAT_LABELS = {
    "aircon": "空调",
    "water_heater": "热水器",
    "fridge": "冰箱",
    "standby": "待机负载",
    "laundry": "洗衣",
    "other": "照明/厨房/娱乐等",
}

CSS = """
:root { color-scheme: light;
  --surface: #fcfcfb; --card: #ffffff; --border: #e6e5e1;
  --ink-1: #0b0b0b; --ink-2: #52514e; --ink-3: #8a8984;
  --series: #2a78d6; --accent: #eb6834; --grid: #ececea; }
@media (prefers-color-scheme: dark) { :root {
  color-scheme: dark;
  --surface: #1a1a19; --card: #232322; --border: #3a3a38;
  --ink-1: #ffffff; --ink-2: #c3c2b7; --ink-3: #8a8984;
  --series: #3987e5; --accent: #d95926; --grid: #32322f; } }
* { box-sizing: border-box; }
body { margin: 0; padding: 32px 16px; background: var(--surface); color: var(--ink-1);
  font-family: "Segoe UI", "Microsoft YaHei", system-ui, sans-serif; }
.wrap { max-width: 860px; margin: 0 auto; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 28px 0 10px; color: var(--ink-1); }
.sub { color: var(--ink-2); font-size: 13px; margin-bottom: 20px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.tile { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.tile .v { font-size: 26px; font-weight: 650; letter-spacing: -0.5px; }
.tile .v small { font-size: 13px; font-weight: 400; color: var(--ink-2); margin-left: 2px; }
.tile .k { font-size: 12px; color: var(--ink-2); margin-top: 2px; }
.tile .d { font-size: 11px; color: var(--ink-3); margin-top: 4px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px; overflow-x: auto; }
svg { display: block; max-width: 100%; height: auto; }
svg text { font-family: inherit; }
.bar-row:hover rect { opacity: 0.85; }
table.plan { border-collapse: collapse; width: 100%; font-size: 13px; }
table.plan th, table.plan td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
table.plan th { color: var(--ink-2); font-weight: 500; font-size: 12px; }
table.plan td.num, table.plan th.num { text-align: right; font-variant-numeric: tabular-nums; }
.footer { margin-top: 28px; color: var(--ink-3); font-size: 11px; }
.badge { display:inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px;
  border: 1px solid var(--border); color: var(--ink-2); margin-left: 6px; }
"""


def _line_chart(daily: dict[date, float], plan_start: date | None) -> str:
    """最近 28 天日用电折线图（单系列，无图例）。"""
    days = sorted(daily.keys())[-28:]
    values = [daily[d] for d in days]
    if len(days) < 2:
        return "<p>数据不足</p>"
    w, h = 780, 240
    pad_l, pad_r, pad_t, pad_b = 44, 14, 14, 30
    vmax = max(values) * 1.15
    vmin = 0.0

    def x(i: int) -> float:
        return pad_l + i * (w - pad_l - pad_r) / (len(days) - 1)

    def y(v: float) -> float:
        return pad_t + (h - pad_t - pad_b) * (1 - (v - vmin) / (vmax - vmin))

    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="每日用电量趋势">']
    # 网格与 Y 轴刻度
    steps = 4
    for s in range(steps + 1):
        gv = vmin + (vmax - vmin) * s / steps
        gy = y(gv)
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w - pad_r}" y2="{gy:.1f}" '
            f'stroke="var(--grid)" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pad_l - 6}" y="{gy + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="var(--ink-3)">{gv:.0f}</text>'
        )
    # X 轴日期（稀疏标注）
    label_every = max(1, len(days) // 6)
    for i, d in enumerate(days):
        if i % label_every == 0 or i == len(days) - 1:
            parts.append(
                f'<text x="{x(i):.1f}" y="{h - 8}" text-anchor="middle" '
                f'font-size="11" fill="var(--ink-3)">{d.strftime("%m-%d")}</text>'
            )
    # 计划生效标记线
    if plan_start and days[0] <= plan_start <= days[-1]:
        idx = next(i for i, d in enumerate(days) if d >= plan_start)
        px = x(idx)
        parts.append(
            f'<line x1="{px:.1f}" y1="{pad_t}" x2="{px:.1f}" y2="{h - pad_b}" '
            f'stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="4 3"/>'
        )
        parts.append(
            f'<text x="{px + 5:.1f}" y="{pad_t + 12}" font-size="11" '
            f'fill="var(--accent)">计划生效</text>'
        )
    # 折线 + 数据点（带原生 tooltip）
    points = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(values))
    parts.append(
        f'<polyline points="{points}" fill="none" stroke="var(--series)" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
    )
    for i, (d, v) in enumerate(zip(days, values)):
        parts.append(
            f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3" fill="var(--series)">'
            f"<title>{d.isoformat()}：{v:.1f} kWh</title></circle>"
        )
    parts.append(
        f'<text x="{pad_l}" y="{pad_t - 2}" font-size="11" fill="var(--ink-2)">kWh/天</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _bar_chart(daily_avg: dict[str, float], share: dict[str, float]) -> str:
    """用电结构水平条形图（单色系 + 直接标注）。"""
    ranked = sorted(daily_avg.items(), key=lambda kv: kv[1], reverse=True)
    w = 780
    row_h, gap = 34, 8
    label_w, val_w = 150, 150
    h = len(ranked) * (row_h + gap) + 10
    vmax = max(v for _, v in ranked) or 1.0
    bar_max = w - label_w - val_w - 20
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="用电结构">']
    for i, (cat, val) in enumerate(ranked):
        cy = i * (row_h + gap)
        bw = max(2.0, bar_max * val / vmax)
        label = CAT_LABELS.get(cat, cat)
        parts.append('<g class="bar-row">')
        parts.append(
            f'<text x="{label_w - 10}" y="{cy + row_h / 2 + 4}" text-anchor="end" '
            f'font-size="13" fill="var(--ink-1)">{label}</text>'
        )
        parts.append(
            f'<rect x="{label_w}" y="{cy + 4}" width="{bw:.1f}" height="{row_h - 8}" '
            f'rx="4" fill="var(--series)"><title>{label}：{val:.2f} kWh/天'
            f'（{share.get(cat, 0):.1f}%）</title></rect>'
        )
        parts.append(
            f'<text x="{label_w + bw + 10:.1f}" y="{cy + row_h / 2 + 4}" '
            f'font-size="12" fill="var(--ink-2)">{val:.2f} kWh/天　{share.get(cat, 0):.0f}%</text>'
        )
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def _tile(value: str, unit: str, label: str, detail: str = "") -> str:
    d = f'<div class="d">{html.escape(detail)}</div>' if detail else ""
    return (
        f'<div class="tile"><div class="v">{html.escape(value)}'
        f"<small>{html.escape(unit)}</small></div>"
        f'<div class="k">{html.escape(label)}</div>{d}</div>'
    )


def build_report(ctx) -> str:
    """生成报告并返回文件路径。"""
    rows = ctx.usage.last_n_days(28)
    if not rows:
        raise RuntimeError("没有用电数据，请先运行 init")
    weather = ctx.usage.load_weather()
    daily = ctx.usage.daily_totals(rows)
    avg_daily = sum(daily.values()) / len(daily)
    cost = monthly_cost(avg_daily * 30, ctx.config)
    disagg = disaggregate(rows, weather, ctx.config)
    plan = ctx.store.get_active_plan()
    track = track_progress(ctx) if plan else None

    plan_start = None
    if plan:
        plan_start = date.fromisoformat(plan["baseline"]["end"])

    from ..domain.tariff import currency
    cur = currency(ctx.config)
    monthly_total = cost.get("total_cost", cost.get("total_sgd", 0))
    rate = cost.get("rate_per_kwh", cost.get("rate_sgd_per_kwh", 0))
    tiles = [
        _tile(f"{avg_daily:.1f}", "kWh", "日均用电（近28天）"),
        _tile(
            f"{monthly_total:.0f}",
            cur["symbol"],
            "预计月度电费",
            f"含税，费率 {rate} {cur['code']}/kWh",
        ),
    ]
    if track and track.get("status") == "ok":
        s = track["saving"]
        tiles.append(
            _tile(
                f"{s.get('cost_per_month_projection', s.get('sgd_per_month_projection', 0)):.0f}",
                f"{cur['symbol']}/月", "实际节省（天气归一化）",
                f"节省 {s['kwh_per_day']} kWh/天（{s['pct']}%）",
            )
        )
        tiles.append(
            _tile(
                f"{s['co2_kg_per_month_projection']:.0f}", "kg", "月度减排 CO2",
                f"总体达成率 {track.get('overall_achievement_pct') or '—'}%",
            )
        )
    elif plan:
        exp = plan.get("expected_per_month", {})
        tiles.append(_tile(
            f"{exp.get('cost', exp.get('sgd', 0)):.0f}",
            f"{cur['symbol']}/月",
            "计划预期节省",
            "执行一周后可复盘实际效果",
        ))
        tiles.append(_tile(f"{exp.get('co2_kg', 0):.0f}", "kg/月", "预期减排 CO2"))

    plan_html = ""
    if plan:
        rows_html = ""
        track_map = {}
        if track and track.get("status") == "ok":
            track_map = {item["id"]: item for item in track.get("per_action", [])}
        for action in plan.get("actions", []):
            tr = track_map.get(action["id"], {})
            pct = tr.get("achievement_pct")
            pct_str = f"{pct:.0f}%" if isinstance(pct, (int, float)) else "—"
            rows_html += (
                "<tr>"
                f"<td>{html.escape(action['title'])}</td>"
                f'<td class="num">{action["est_kwh_per_month"]}</td>'
                f'<td class="num">{cur["symbol"]}'
                f'{action.get("est_cost_per_month", action.get("est_sgd_per_month", 0))}</td>'
                f'<td class="num">{pct_str}</td>'
                "</tr>"
            )
        plan_html = f"""
<h2>当前节能计划 v{plan.get("version")}<span class="badge">基线 {plan["baseline"]["start"]} ~ {plan["baseline"]["end"]}</span></h2>
<div class="card"><table class="plan">
<tr><th>动作</th><th class="num">预期 kWh/月</th><th class="num">预期节省/月</th><th class="num">达成率</th></tr>
{rows_html}
</table></div>"""

    generated = ctx.usage.last_date()
    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HomeShift AI 用电周报</title>
<style>{CSS}</style>
</head>
<body><div class="wrap">
<h1>HomeShift AI 用电周报</h1>
<div class="sub">Cut bills, not comfort · 数据截至 {generated} · 金额均按当前电价折算</div>
<div class="tiles">{"".join(tiles)}</div>
<h2>每日用电趋势（近 28 天）</h2>
<div class="card">{_line_chart(daily, plan_start)}</div>
<h2>用电结构（负载分解估算）</h2>
<div class="card">{_bar_chart(disagg["daily_avg_kwh"], disagg["share_pct"])}</div>
{plan_html}
<div class="footer">负载分解为基于总电表的启发式估算（方法与局限见诊断报告）。
HomeShift AI · Agentic AI in Sustainability 课程项目</div>
</div></body></html>"""

    out_path = ctx.data_dir / "report.html"
    ctx.data_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")
    return str(out_path)
