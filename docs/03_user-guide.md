# 操作手册（从零到完整演示）

> 面向第一次接触本项目的组员/评审：照着做即可，每一步都有预期输出说明。

## 0. 环境要求

- Python **3.10 或以上**（验证环境：Windows 11 + Python 3.12）
- 操作系统不限（Windows / macOS / Linux）
- **离线演示模式无需安装任何第三方包、无需网络、无需 API key**

检查 Python 版本：

```bash
python --version
```

在项目根目录（能看到 `homeshift/` 文件夹和 `README.md` 的目录）打开终端，后续所有命令都在这里执行。

## 1. 初始化演示环境

```bash
python -m homeshift init
```

预期输出：生成 56 天（半小时粒度）的合成电表/天气数据与默认家庭画像，显示日均用电约 18-19 kWh。

生成的文件（都在 `data/` 目录，随时可删掉重新 init）：

| 文件 | 内容 |
| --- | --- |
| `usage.csv` | 智能电表读数（timestamp, kwh） |
| `weather.csv` | 室外温度 |
| `usage_groundtruth.csv` | 分电器真值（仅用于精度评估，Agent 不可见） |
| `profile.json` | 家庭画像（可手动编辑，比如改空调设定温度） |

检查状态：

```bash
python -m homeshift status
```

`LLM 模式` 显示 `mock` 表示离线演示模式（正常）。

## 2. 核心演示流程（推荐顺序）

### 2.1 诊断

```bash
python -m homeshift diagnose
```

你会看到 Agent 的完整工作过程：逐条打印 `[工具] xxx(...)` 调用轨迹（这就是 Agentic loop 的可视化），最后输出诊断报告：日均/月度用电与电费、负载分解表（空调约 62%）、三大关键发现。

### 2.2 制定计划

```bash
python -m homeshift plan
```

Agent 读取画像与历史记忆 → 运行模拟器 → 挑选动作 → 保存计划 v1。输出 5 个动作的清单，每个附 kWh/S$/CO2 三维收益与舒适影响。计划已持久化到 `data/plans.json`。

### 2.3 快进一周（演示专用）

```bash
python -m homeshift simulate-week
```

向数据末尾追加 7 天"执行了计划"的电表数据。每个动作每天有 85% 概率被执行（可用 `--adherence 0.6` 模拟执行率更差的家庭，复盘结果会相应变化——这是很好的演示互动点）。

### 2.4 周度复盘

```bash
python -m homeshift review
```

Agent 读取计划与追踪数据，输出：天气归一化后的实际节省、总体达成率、分动作达成率表、分析与调整建议。**若某动作达成率低，Agent 会自动把结论写入长期记忆**（可在 `data/memory.json` 看到）——这是反思闭环的证据。

### 2.5 可视化周报

```bash
python -m homeshift report
```

生成 `data/report.html`，浏览器打开即可投屏：指标卡片、28 天趋势图（带"计划生效"标记线）、用电结构条形图、计划达成率表。支持深色模式。

### 2.6 附加演示点

```bash
# 负载分解精度评估（体现工程严谨性）
python -m homeshift eval-disagg

# 自由对话（mock 模式为关键词路由；真实模式为自然对话）
python -m homeshift chat

# 测试套件（14 个测试，覆盖完整闭环）
python -m unittest
```

## 3. 切换到真实 Claude 模型（可选）

```bash
pip install anthropic
```

设置 API key（从 https://platform.claude.com 获取）：

```powershell
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

```bash
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."
```

之后运行任何 Agent 命令（diagnose/plan/review/chat），系统自动切换为真实 Claude（`python -m homeshift status` 可确认）。此时 Agent 的工具调用顺序、报告措辞由模型自由决定，`chat` 支持任意自然语言提问。

**成本提示**：默认模型为 `claude-opus-5`；一次 diagnose 任务约消耗几万 token。课堂演示建议以 mock 模式为主、真实模式做一次对比展示。

## 4. 配置覆盖（config.json）

在项目根目录创建 `config.json` 可覆盖任意默认配置（深度合并），例如：

```json
{
  "llm": {"model": "claude-sonnet-5"},
  "tariff": {"plan": "tou"},
  "datagen": {"default_adherence": 0.6}
}
```

常用配置项：

| 路径 | 默认值 | 说明 |
| --- | --- | --- |
| `llm.provider` | `auto` | `auto`/`anthropic`/`mock` |
| `llm.model` | `claude-opus-5` | 真实模式的模型 |
| `tariff.plan` | `regulated` | `regulated` 固定费率 / `tou` 分时电价（会激活"错峰洗衣"的经济价值） |
| `tariff.regulated_rate_sgd_per_kwh` | `0.2988` | 电价（按 SP Group 季度公布更新） |
| `carbon.grid_emission_factor_kg_per_kwh` | `0.412` | 电网排放因子 |
| `datagen.default_adherence` | `0.85` | simulate-week 的默认执行率 |

## 5. 重置与重演

```bash
# 完全重置（删除所有数据、计划、记忆）
# Windows:  Remove-Item -Recurse -Force data
# macOS/Linux:  rm -rf data
python -m homeshift init
```

数据生成带固定随机种子，重置后数字完全可复现——演示彩排和正式演示的输出一致。

## 6. 故障排查

| 现象 | 原因与解决 |
| --- | --- |
| `没有用电数据，请先运行 init` | 未初始化或 `data/` 被删，运行 `python -m homeshift init` |
| 中文乱码（Windows） | 程序已强制 UTF-8 输出；若终端仍乱码，换用 Windows Terminal 或执行 `chcp 65001` |
| `尚无生效计划` | `simulate-week`/`review` 依赖计划，先运行 `plan` |
| 复盘提示"数据不足 3 天" | 计划刚建立，先 `simulate-week` 快进 |
| 设置了 key 仍是 mock 模式 | 未安装 SDK（`pip install anthropic`），或 key 未在当前终端会话生效（重开终端需重新 set） |
| 真实模式报 401 | API key 无效或过期 |
| 想强制离线 | `config.json` 中 `{"llm": {"provider": "mock"}}` |
