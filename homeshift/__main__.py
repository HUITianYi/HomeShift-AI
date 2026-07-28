"""HomeShift AI 命令行入口。

用法：python -m homeshift <命令>

命令一览（推荐演示顺序）：
  init           生成演示数据集与默认家庭画像
  status         查看系统状态（LLM 模式、数据范围、当前计划）
  diagnose       [Agent] 诊断电费为什么高（负载分解 + 解读）
  plan           [Agent] 制定个性化节能计划
  simulate-week  快进一周“执行计划后”的电表数据（演示用）
  review         [Agent] 周度复盘：实际省了多少、达成率、调整建议
  chat           与智能体自由对话（mock 模式为关键词路由）
  report         生成 HTML 可视化周报（data/report.html）
  eval-disagg    用分电器真值评估负载分解精度（演示环境专属）
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import resolve_provider
from .context import AppContext


def _print_header(title: str) -> None:
    print()
    print("=" * 56)
    print(f"  {title}")
    print("=" * 56)
    print()


def _provider_banner(ctx: AppContext) -> None:
    from .llm.registry import resolve_llm_settings

    s = resolve_llm_settings(ctx.config)
    if s["kind"] == "mock":
        print("[LLM] 离线演示模式 Mock —— 设置任一模型的 API 密钥即可切换到真实模型")
        print("      查看可用模型：python -m homeshift providers")
    else:
        print(f"[LLM] {s['label']}　模型：{s['model']}")
    print()


def cmd_init(ctx: AppContext, args) -> None:
    from .datagen.generate import init_dataset

    _print_header("初始化：生成演示数据集与家庭画像")
    summary = init_dataset(ctx, days=args.days)
    profile = ctx.store.ensure_default_profile()
    print(f"数据期间   {summary['start']} ~ {summary['end']}（{summary['days']} 天，半小时粒度）")
    print(f"总用电量   {summary['total_kwh']} kWh")
    print(f"日均用电   {summary['avg_daily_kwh']} kWh")
    print(f"家庭画像   {profile['home_type']}，{profile['household']}")
    print()
    print("下一步：python -m homeshift diagnose")


def cmd_status(ctx: AppContext, args) -> None:
    _print_header("系统状态")
    from .llm.registry import resolve_llm_settings

    llm = resolve_llm_settings(ctx.config)
    print(f"LLM 模式    {llm['provider']}    模型: {llm['model'] or '-（离线剧本）'}")
    print(f"            {llm['reason']}")
    region = ctx.config.get("region", {})
    print(f"地区/币种   {region.get('name', '-')}　{region.get('currency', '-')}"
          f"　气候 {region.get('climate', '-')}")
    rng = ctx.usage.date_range()
    if rng:
        print(f"用电数据    {rng[0]} ~ {rng[1]}")
    else:
        print("用电数据    （无，请先运行 init）")
    plan = ctx.store.get_active_plan()
    if plan:
        exp = plan.get("expected_per_month", {})
        print(
            f"当前计划    v{plan['version']}（{len(plan.get('actions', []))} 个动作，"
            f"预期省 S${exp.get('sgd')}/月）"
        )
    else:
        print("当前计划    （无）")
    memories = ctx.store.get_memories()
    print(f"长期记忆    {len(memories)} 条")

    provenance = ctx.data_dir / "provenance.json"
    if provenance.exists():
        import json as _json

        with open(provenance, "r", encoding="utf-8") as f:
            prov = _json.load(f)
        ds = prov.get("dataset", {})
        win = prov.get("window", {})
        kind = "真实数据集" if prov.get("data_kind") == "real" else "合成演示数据"
        print(f"数据来源    {kind} {ds.get('id')} —— {ds.get('title', '')}")
        print(f"            许可 {ds.get('license')}　完整度 {win.get('completeness_pct')}%")
        print(f"            天气 {prov.get('weather', {}).get('source', '-')}")
        if prov.get("data_kind") != "real":
            print("            运行 python fetch_real_data.py 可换成真实数据")
    else:
        print("数据来源    合成演示数据（运行 python fetch_real_data.py 换成真实数据）")
    print(f"数据目录    {ctx.data_dir}")


def _run_agent_task(ctx: AppContext, prompt: str, title: str) -> None:
    from .agent.core import Agent, build_llm
    from .llm.registry import ProviderError

    _print_header(title)
    _provider_banner(ctx)
    try:
        agent = Agent(ctx, build_llm(ctx))
    except ProviderError as exc:
        print(f"[配置错误] {exc}")
        sys.exit(2)
    try:
        agent.run_task(prompt)
    except Exception as exc:  # 模型调用失败时给出可读提示而不是堆栈
        print(f"\n[模型调用失败] {exc}")
        print("\n可以先用离线模式验证系统：在 config.json 里设 "
              '{"llm": {"provider": "mock"}}')
        sys.exit(3)
    _save_trace(ctx, agent.trace, task=title)


MAX_TRACE_STEPS = 120


def _save_trace(ctx: AppContext, trace: list, task: str = "") -> None:
    """累积保存角色协作轨迹（跨命令），export-web 会读它。

    之所以累积而不是覆盖：一次 diagnose 只会用到 3 个角色，
    但网站要展示的是"七个 agent 如何协作完成整条流程"，
    所以需要把 diagnose -> plan -> review 的轨迹串起来。
    """
    import json as _json

    if not trace:
        return
    path = ctx.data_dir / "last_trace.json"
    existing = []
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = _json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = []

    for entry in trace:
        entry["task"] = task
    merged = (existing + trace)[-MAX_TRACE_STEPS:]
    for index, entry in enumerate(merged, start=1):
        entry["step"] = index

    ctx.data_dir.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(merged, f, ensure_ascii=False, indent=2, default=str)


def cmd_diagnose(ctx: AppContext, args) -> None:
    from .agent.prompts import DIAGNOSE_PROMPT

    _run_agent_task(ctx, DIAGNOSE_PROMPT, "Agent 任务：用电诊断")


def cmd_plan(ctx: AppContext, args) -> None:
    from .agent.prompts import PLAN_PROMPT

    _run_agent_task(ctx, PLAN_PROMPT, "Agent 任务：制定节能计划")


def cmd_review(ctx: AppContext, args) -> None:
    from .agent.prompts import REVIEW_PROMPT

    _run_agent_task(ctx, REVIEW_PROMPT, "Agent 任务：周度复盘")


def cmd_chat(ctx: AppContext, args) -> None:
    from .agent.core import Agent, build_llm

    _print_header("与 HomeShift AI 对话（输入 exit 退出）")
    _provider_banner(ctx)
    agent = Agent(ctx, build_llm(ctx))
    history: list[dict] = []
    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input or user_input.lower() in ("exit", "quit", "q", "退出"):
            break
        print()
        agent.run_task(user_input, history=history)
        print()


def cmd_simulate_week(ctx: AppContext, args) -> None:
    from .datagen.generate import append_week_with_plan

    _print_header("演示快进：模拟执行计划后的一周")
    plan = ctx.store.get_active_plan()
    if plan is None:
        print("尚无生效计划。请先运行 python -m homeshift plan")
        sys.exit(1)
    adherence = args.adherence
    summary = append_week_with_plan(ctx, plan, adherence)
    print(f"已追加     {summary['start']} ~ {summary['end']} 的电表/天气数据")
    print(f"注入动作   {', '.join(summary['actions_applied'])}")
    print(f"执行率     每个动作每天 {adherence:.0%} 概率被执行（模拟真实生活的不完美）")
    print(f"本周日均   {summary['avg_daily_kwh']} kWh")
    print()
    print("下一步：python -m homeshift review")


def cmd_report(ctx: AppContext, args) -> None:
    from .report.html_report import build_report

    _print_header("生成 HTML 可视化周报")
    path = build_report(ctx)
    print(f"已生成：{path}")
    print("用浏览器打开即可查看/投屏。")


def cmd_eval_disagg(ctx: AppContext, args) -> None:
    from .domain.disaggregate import disaggregate, evaluate_against_truth

    _print_header("负载分解精度评估（对照分电器真值）")
    rows = ctx.usage.last_n_days(28)
    if not rows:
        print("没有数据，请先运行 init")
        sys.exit(1)
    disagg = disaggregate(rows, ctx.usage.load_weather(), ctx.config)
    start = rows[0][0].date()
    truth = [r for r in ctx.usage.load_groundtruth() if r["timestamp"].date() >= start]

    # 真实数据集的分表口径与本项目类别不同，映射关系记录在 provenance.json，
    # 不传这个映射会让所有真值都落到 other，得出完全错误的评估结果。
    category_map = None
    provenance = ctx.data_dir / "provenance.json"
    if provenance.exists():
        import json as _json

        with open(provenance, "r", encoding="utf-8") as f:
            category_map = _json.load(f).get("category_map") or None

    result = evaluate_against_truth(disagg, truth, category_map)
    if "error" in result:
        print(f"无法评估：{result['error']}")
        return
    print(f"评估天数：{result['days']}")
    print()
    print(f"{'类别':<14}{'真值 kWh/天':>12}{'估算 kWh/天':>12}{'MAE kWh/天':>12}")
    print("-" * 52)
    from .domain.appliances import CATEGORY_LABELS

    for cat, metrics in result["per_category"].items():
        label = CATEGORY_LABELS.get(cat, cat)
        print(
            f"{label:<14}{metrics['truth_avg_kwh_day']:>12.2f}"
            f"{metrics['est_avg_kwh_day']:>12.2f}{metrics['mae_kwh_day']:>12.2f}"
        )
    print()
    if category_map:
        print("说明：真值来自数据集自带的分表，映射关系见 data/provenance.json 的 category_map。")
        print("      口径不完全对应之处（如某路分表混合了多种电器）已在该文件中显式记录。")
    else:
        print("说明：真实场景没有分电器真值；合成数据让我们得以定量检验启发式的可信度。")


def cmd_providers(ctx: AppContext, args) -> None:
    from .llm.registry import describe_providers, resolve_llm_settings

    _print_header("可用的大模型提供方")
    current = resolve_llm_settings(ctx.config)
    print(f"当前生效：{current['provider']}（{current['reason']}）\n")
    print(f"{'名称':<14}{'密钥':<6}{'默认模型':<26}说明")
    print("-" * 100)
    for p in describe_providers():
        ready = "就绪" if p["key_ready"] else "未配"
        print(f"{p['name']:<14}{ready:<6}{str(p['default_model'] or '-'):<26}{p['label']}")
        if p["key_env"]:
            print(f"{'':<20}环境变量：{' 或 '.join(p['key_env'])}")
        if p["notes"]:
            print(f"{'':<20}{p['notes']}")
        print()
    print("切换方法：在项目根目录的 config.json 写入")
    print('  {"llm": {"provider": "deepseek"}}')
    print("并设置对应的环境变量后重新运行任意 Agent 命令。")


def cmd_llm_test(ctx: AppContext, args) -> None:
    """最小连通性测试：发一轮带工具的请求，验证密钥、网络与工具调用协议。"""
    from .agent.core import build_llm
    from .agent.tools import TOOL_DEFINITIONS
    from .llm.registry import ProviderError, resolve_llm_settings

    _print_header("大模型连通性测试")
    settings = resolve_llm_settings(ctx.config)
    print(f"提供方  {settings['provider']}（{settings['label']}）")
    print(f"模型    {settings['model']}")
    print(f"地址    {settings['base_url'] or '-'}")
    print(f"密钥    {'已设置' if settings['api_key'] else '未设置'}")
    print()

    if settings["kind"] == "mock":
        print("当前是离线 Mock 模式，无需联网。要测试真实模型请先配置 provider。")
        return
    try:
        client = build_llm(ctx)
    except ProviderError as exc:
        print(f"[配置错误] {exc}")
        sys.exit(2)

    print("正在发送一条测试请求（要求模型调用 get_tariff_info 工具）...")
    try:
        response = client.create(
            "你是一个测试助手。请调用 get_tariff_info 工具来回答问题。",
            [{"role": "user", "content": "现在的电价是多少？请使用工具查询。"}],
            TOOL_DEFINITIONS,
        )
    except Exception as exc:
        print(f"\n[失败] {exc}")
        sys.exit(3)

    tool_calls = [b for b in response.content if b.get("type") == "tool_use"]
    texts = [b.get("text", "") for b in response.content if b.get("type") == "text"]
    print(f"\n返回状态  stop_reason = {response.stop_reason}")
    print(f"文本输出  {(texts[0][:120] + '...') if texts else '（无）'}")
    if tool_calls:
        print(f"工具调用  {tool_calls[0]['name']}({tool_calls[0].get('input')})")
        print("\n通过：该模型支持工具调用，可以驱动完整的 Agent 循环。")
    else:
        print("\n[警告] 模型没有发起工具调用。")
        print("可能原因：该模型不支持 function calling，或提示词被忽略。")
        print("这类模型无法驱动本项目的 Agent 循环，建议换一个支持工具调用的模型。")
    usage = getattr(client, "last_usage", None)
    if usage:
        print(f"\nToken 用量：{usage}")


def cmd_agents(ctx: AppContext, args) -> None:
    from .agent.roles import roster, validate_coverage
    from .agent.tools import TOOL_DEFINITIONS

    _print_header("七个专家角色（specialist agents）")
    for role in roster():
        veto = "  [持否决权]" if role["veto"] else ""
        print(f"{role['order']}. {role['name']}　{role['name_en']}{veto}")
        print(f"   职责：{role['mission']}")
        print(f"   工具：{'、'.join(role['tools']) if role['tools'] else '（作用于其他角色的产物）'}")
        print()
    check = validate_coverage(TOOL_DEFINITIONS)
    if check["ok"]:
        print(f"自检通过：{len(TOOL_DEFINITIONS)} 个工具全部有角色认领，无孤儿工具。")
    else:
        print(f"[自检失败] 未认领的工具：{check['unassigned_tools']}　"
              f"不存在的工具：{check['phantom_tools']}")


def cmd_export_web(ctx: AppContext, args) -> None:
    import json as _json

    from .export.web_payload import export_web

    _print_header("导出可视化网站数据包")
    trace = []
    trace_path = ctx.data_dir / "last_trace.json"
    if trace_path.exists():
        with open(trace_path, "r", encoding="utf-8") as f:
            trace = _json.load(f)

    result = export_web(ctx, trace)
    print(f"输出目录：{result['out_dir']}\n")
    for path in result["files"]:
        print(f"  {path}")
    print("\n各分段可用性：")
    for section, ok in result["sections_available"].items():
        print(f"  {section:<12}{'可用' if ok else '不可用（数据不足）'}")
    print("\n交给前端队友的三件东西：")
    print("  1. homeshift_web.json —— 完整数据包")
    print("  2. homeshift_web.js   —— 静态页面可直接 <script src> 引入")
    print("  3. SCHEMA.md          —— 字段说明书（自动生成，与数据永远一致）")


def cmd_init_real(ctx: AppContext, args) -> None:
    from .realdata.pipeline import build_real_dataset

    _print_header("接入真实数据")
    build_real_dataset(
        ctx, dataset=args.dataset, window_days=args.days,
        file_path=args.file, weather_source=args.weather,
    )


def main(argv: list[str] | None = None) -> None:
    # Windows 中文控制台兼容：强制 UTF-8 输出
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="python -m homeshift",
        description="HomeShift AI — 家庭能源管理智能体（Cut bills, not comfort）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="生成演示数据集与默认家庭画像")
    p_init.add_argument("--days", type=int, default=None, help="基线数据天数（默认 56）")
    p_init.set_defaults(func=cmd_init)

    sub.add_parser("status", help="查看系统状态").set_defaults(func=cmd_status)
    sub.add_parser("diagnose", help="[Agent] 诊断电费为什么高").set_defaults(func=cmd_diagnose)
    sub.add_parser("plan", help="[Agent] 制定个性化节能计划").set_defaults(func=cmd_plan)
    sub.add_parser("review", help="[Agent] 周度复盘").set_defaults(func=cmd_review)
    sub.add_parser("chat", help="与智能体自由对话").set_defaults(func=cmd_chat)

    p_sim = sub.add_parser("simulate-week", help="快进一周执行数据（演示用）")
    p_sim.add_argument(
        "--adherence", type=float, default=None,
        help="每个动作每天被执行的概率（默认 0.85）",
    )
    p_sim.set_defaults(func=cmd_simulate_week)

    sub.add_parser("report", help="生成 HTML 可视化周报").set_defaults(func=cmd_report)
    sub.add_parser("eval-disagg", help="评估负载分解精度").set_defaults(func=cmd_eval_disagg)

    sub.add_parser("providers", help="列出可用的大模型提供方与密钥状态").set_defaults(
        func=cmd_providers)
    sub.add_parser("llm-test", help="测试当前模型的连通性与工具调用能力").set_defaults(
        func=cmd_llm_test)
    sub.add_parser("agents", help="查看七个专家角色及其工具归属").set_defaults(func=cmd_agents)
    sub.add_parser("export-web", help="导出给可视化网站的数据包").set_defaults(
        func=cmd_export_web)

    p_real = sub.add_parser("init-real", help="接入真实数据（等价于 fetch_real_data.py）")
    p_real.add_argument("--dataset", default="uci")
    p_real.add_argument("--days", type=int, default=None)
    p_real.add_argument("--file", default=None)
    p_real.add_argument("--weather", default=None,
                        choices=["openmeteo", "datagovsg", "none"])
    p_real.set_defaults(func=cmd_init_real)

    args = parser.parse_args(argv)
    ctx = AppContext()
    if getattr(args, "adherence", None) is None and args.command == "simulate-week":
        args.adherence = ctx.config["datagen"]["default_adherence"]
    args.func(ctx, args)


if __name__ == "__main__":
    main()
