# 08 · 网站数据对接说明

> **这份文档可以直接转发给做可视化网站的队友。**

后端每跑一次 `python -m homeshift export-web`，就会在 `data/web/` 下生成
一整套给网站用的数据。本文说明这些数据长什么样、怎么用、以及两边需要先对齐什么。

---

## 0. 先对齐三件事（重要，建议开会 10 分钟敲定）

在写任何对接代码之前，两边需要统一口径。否则答辩时教授同时看到网站和代码，
会立刻发现不一致。

### (1) 「7 个 agent」的说法

网站文案是 *"Seven specialist agents"*，后端实现是
**一个 LLM 编排循环 + 七个专职角色**。

我们已经把这七个角色**在代码里做成真的**（`homeshift/agent/roles.py`）：
每个工具都归属于一个角色，每次调用都记录"谁出手、做了什么、耗时多久"，
并且有一个自动化测试保证"不会出现没被任何角色认领的工具"。

统一话术建议：

> "系统由七个专职 agent 组成：数据管家、负载侦探、成本分析师、碳排分析师、
> 舒适守门人、规划师、追踪与记忆。它们共享一个编排器（single-controller
> multi-role 架构），由编排器决定下一个该谁出手。所有数字由各角色对应的
> 确定性工具算出，模型本身不产生任何数字。"

**不要说**"七个 agent 各自独立跑一个 LLM 会话" —— 那不是我们的实现，
而且真那样做会贵七倍且数字容易互相打架。

七个角色的完整信息在 `agents.json`，可以直接驱动网站上的 agent 展示区。

### (2) 场景一致性

后端目前默认接入的公开数据集是**法国**家庭（UCI，唯一自带分表真值的免密钥
数据集，用来验证负载分解算法）。而网站文案写的是**新加坡 Tampines HDB**。

两种解法，选一个：

- **方案 A（推荐）**：网站主线用新加坡场景，后端跑
  `python fetch_real_data.py --dataset spgroup --file <新加坡电表CSV>`，
  导出的数据里币种、电价、碳因子会自动是 SGD / 新加坡口径。
  UCI 那条线单独作为"算法精度验证"章节展示。
- **方案 B**：网站文案改成跟随数据（`meta.region.name` 里有地区名）。

数据包的 `meta.region`、`meta.currency`、`meta.data_kind` 三个字段会如实反映
当前是什么场景，网站可以直接读它们来渲染，不要写死"Tampines / S$"。

### (3) 数字口径

**所有数字以后端导出的为准，网站不要自己再算一遍。**
后端已经把货币符号、小数位都格式化好了（见下文 `display` 字段），
两边各算一次必然会出现"网站显示 146.08、报告显示 146.1"这类尴尬。

---

## 1. 拿到哪些文件

```
data/web/
├── homeshift_web.json    完整数据包（推荐用这个）
├── homeshift_web.js      同样内容，但是 window.HOMESHIFT_DATA = {...}
├── meta.json             ┐
├── household.json        │
├── baseline.json         │ 分段文件，按需单独取
├── diagnosis.json        │
├── plans.json            │
├── track.json            │
├── agents.json           ┘
└── SCHEMA.md             字段说明书（自动生成，永远和数据一致）
```

**纯静态页面**（没有后端服务器、直接开 html）用 `.js` 那个，
避免 `fetch` 本地文件的跨域问题：

```html
<script src="homeshift_web.js"></script>
<script>
  const d = window.HOMESHIFT_DATA;
  console.log(d.baseline.headline.est_bill.display);  // "S$146.08"
</script>
```

有服务器就用 `.json`：

```js
const d = await fetch('/data/homeshift_web.json').then(r => r.json());
```

---

## 2. 三条通用约定

### (1) 所有展示文本都是双语对象

```json
"label": { "zh": "空调", "en": "Cooling / AC" }
```

网站的中英切换直接取键：`label[lang]`，不需要维护翻译表。

### (2) 所有金额都已格式化好

```json
"est_bill": { "value": 146.08, "display": "S$146.08", "currency": "SGD" }
```

**直接用 `display`**。`value` 留给需要计算或画图的场景。
币种会随数据集自动切换（新加坡 SGD / 法国 EUR），网站不要硬编码 `S$`。

### (3) 所有物理量同理

```json
"kwh_this_month": { "value": 420, "unit": "kWh", "display": "420 kWh" }
```

### (4) 每段都有 `available`

```js
if (!d.track.available) {
  // 别渲染 04 Track 那一段，d.track.message.zh 里有原因
  // 例如"计划生效后的数据不足 3 天，无法评估"
}
```

这不是错误处理，是**正常状态**：计划刚制定时本来就还没有追踪数据。

---

## 3. 四个分段对应关系

### 01 Baseline

```js
d.baseline.headline.kwh_this_month.display   // "543 kWh"      ← 大数字
d.baseline.headline.est_bill.display         // "S$146.08"     ← Est. bill
d.baseline.headline.carbon_kg.display        // "168.8 kg"     ← Carbon
d.baseline.headline.sources_count            // 4              ← "N sources"
d.household.goal.display                     // "−10%"         ← Target
d.household.tags                             // ["4-room HDB", "WFH", ...]
d.baseline.period.label.zh                   // 期间标签

// 24-HOUR SIGNATURE
d.baseline.signature_24h.slots               // 48 个点 {slot, time, kwh}
d.baseline.signature_24h.peak                // {time:"20:30", kwh:0.93}
d.baseline.signature_24h.bands               // 三个时段带 + 观察结论文案

// 趋势图
d.baseline.daily_series                      // [{date, kwh, temp_c, is_weekend}]

// DATA DESK（证据卡片）
d.baseline.evidence                          // [{kind, file, label, available, rows}]

// 已锁定的舒适规则
d.household.comfort_rules                    // [{id, label:{zh,en}, kind, locked}]
```

`comfort_rules` 直接对应网站上 "Comfort rules locked · 25°C sleep · WFH
protected" 那一行，`locked: true` 的可以加个锁图标。

### 02 Diagnosis

```js
d.diagnosis.categories       // 六大类，已按用电量排序，含 rank
// 每项：{ id, rank, label:{zh,en}, kwh_per_day, share_pct,
//         cost_per_month:{display}, co2_kg_per_month }

d.diagnosis.findings         // 前三条关键发现（按实际占比生成，不是写死的）
d.diagnosis.method.notes     // 方法说明与局限（建议放折叠区）
d.diagnosis.accuracy         // 分解精度
d.diagnosis.daily_series     // 每日分类别用电，可画堆叠面积图
```

`accuracy.available` 为 `true` 时才有 `per_category`（各类别的真值/估算/MAE）。
为 `false` 时 `note.zh` 会说明原因（真实家庭没有分表真值是常态）。
**建议照实展示** —— "我们知道自己的误差有多大"比"我们很准"更有说服力。

### 03 Plans

```js
d.plans.candidates              // 候选动作列表
// 每项：{ id, title:{zh,en}, description:{zh,en}, category,
//         selected,               ← 是否已被采纳进正式计划
//         confirmed_by_user,      ← 始终 false，等网站上用户点确认
//         savings: { kwh_per_month, cost_per_month:{display}, co2_kg_per_month },
//         comfort_impact: { level, label:{zh,en} },
//         effort: { level, label:{zh,en} },
//         comfort_verdict: { status, reason:{zh,en} } }

d.plans.vetoed_by_comfort       // ★ 被舒适守门人否决的动作 + 理由
d.plans.comfort_summary         // { vetoed_count, forgone_cost_per_month, ... }
d.plans.seven_day_schedule      // 七天可勾选清单 [{day, date, items:[...]}]
d.plans.expected_per_month      // 已采纳动作的预期月度收益
d.plans.potential_per_month     // 全部候选的理论上限
```

**`vetoed_by_comfort` 强烈建议做一个展示区**，这是这个产品最有说服力的地方：

> "系统为保护你的舒适度，主动放弃了 S$9.00/月的可省金额。
> 原因：你设定了空调不得高于 26°C，而当前已是 26°C。"

`comfort_verdict.status` 有三个值：
- `approved` —— 通过
- `adjusted` —— 参数被收紧后才通过（可以加个"已为你调整"的角标）
- `vetoed` —— 否决（只出现在 `vetoed_by_comfort` 里）

网站文案 "User-confirmed actions only" 对应 `confirmed_by_user` 字段 ——
后端永远输出 `false`，由网站上的用户勾选来翻转。

### 04 Track

```js
d.track.comparison_bars      // 三根柱子：基线 / 若不行动（天气归一化）/ 实际
d.track.saving.cost_per_month.display   // 实际月度节省
d.track.saving.pct                      // 节省百分比
d.track.overall_achievement_pct         // 总体达成率
d.track.per_action                      // 分动作达成率
d.track.weather_normalization           // 天气归一化的元信息
```

**`per_action[].status` 有四个值，请按不同颜色渲染**：

| status | 含义 | 建议 |
| --- | --- | --- |
| `on_track` | 达成率 ≥ 80% | 绿 |
| `partial` | 40–80% | 黄 |
| `off_track` | < 40% | 红 |
| `not_measurable` | 该动作不改变用电量（如错峰） | 灰 |

另外注意 `per_action[].reliability` 字段。当它不是 `"ok"` 时，
说明**这条归因不可信**（比如达成率显示 1100%，实际是负载分解的归类误差）。
这时应该显示 `reliability_note`，而不是让用户以为自己超额完成了 11 倍。

`weather_normalization.applied` 为 `false` 时，
`note` 里会说明为什么没做归一化，建议在图表旁加一行提示。

---

## 4. agents 区

```js
d.agents.count           // 7
d.agents.orchestration   // 架构一句话说明（双语），可放在展示区标题下
d.agents.agents          // 七个角色
// 每项：{ id, order, name:{zh,en}, mission:{zh,en}, tools:[],
//         has_veto, status: "active"|"idle",
//         calls_in_last_run, activity_note:{zh,en} }

d.agents.trace           // 协作轨迹（按时间顺序）
// 每项：{ step, task, role, role_name, tool, input, ok,
//         elapsed_ms, output_preview }
```

`trace` 是**真实运行记录**，不是编的。可以做成一条时间线，
配合 "Run 7-agent diagnosis" 那个按钮做逐步播放动画 ——
这是全站最能体现 "agentic" 的一块。

`has_veto: true` 的只有舒适守门人，可以给它一个特殊标记。

---

## 5. 数据更新流程

```bash
# 后端每次改完数据或跑完新一轮，执行：
python -m homeshift diagnose
python -m homeshift plan
python -m homeshift simulate-week
python -m homeshift review
python -m homeshift export-web       # ← 生成最新数据包
```

然后把 `data/web/` 整个目录交给前端。

`meta.generated_at` 是生成时间，`meta.schema_version` 是结构版本。
建议前端加一行防御：

```js
if (!d.meta.schema_version.startsWith('1.')) {
  console.warn('后端数据结构有大改动，请同步更新对接代码');
}
```

---

## 6. 如果字段名和网站现有代码对不上

完全可能 —— 我们是照着网站可见的信息结构设计的，拿不到你的内部变量名。

两种改法：

- **前端改**：写个 5 行的 adapter 把字段映射过去（推荐，改动最小）
- **后端改**：把你的字段名清单发过来，改 `homeshift/export/web_payload.py`
  末尾的组装函数即可，计算逻辑完全不用动 —— 那一层就是为适配留的

**更省事的办法**：直接把你现在网站里用的那份示例 JSON 发给后端，
我们照着它的字段名重新导出一版，你一行代码都不用改。

---

## 7. 一句话总结

网站只需要读一个 `homeshift_web.js`，里面所有文本双语、所有金额已格式化、
所有分段带可用性标记、所有数字都是确定性计算出来的（不是模型编的）。
字段说明书 `SCHEMA.md` 每次导出自动重新生成，永远和实际数据一致。
