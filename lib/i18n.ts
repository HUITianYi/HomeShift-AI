export type Locale = "en" | "zh";

const zh: Record<string, string> = {
  "Baseline": "基线",
  "Diagnosis": "诊断",
  "Plans": "方案",
  "Track": "跟踪",
  "Synthetic demo": "合成数据演示",
  "Reset demo": "重置演示",
  "Demo progress": "演示进度",
  "HomeShift AI home": "HomeShift AI 首页",
  "10 percent reduction goal": "10% 节能目标",
  "HOUSEHOLD ENERGY COPILOT": "家庭能源智能助手",
  "Data ready": "数据已就绪",
  "Cut bills, not comfort.": "节省电费，不牺牲舒适。",
  "Turn your energy data into a plan your household will": "把家庭能源数据变成",
  "actually follow.": "真正能执行的计划。",
  "Seven specialist agents diagnose what drives your bill, negotiate cost against comfort and carbon, then adapt a practical seven-day plan as new data arrives.":
    "七个专业智能体分析电费成因，在成本、舒适度与碳排之间协商，并根据新数据持续调整可执行的七天计划。",
  "Run 7-agent diagnosis": "运行七智能体诊断",
  "Reload synthetic case": "重新载入合成案例",
  "User-confirmed actions only": "仅执行用户确认的行动",
  "Deterministic calculations": "确定性计算",
  "MAY BASELINE": "五月用电基线",
  "Tampines household": "淡滨尼家庭",
  "3 sources": "3 项数据来源",
  "this month": "本月",
  "Est. bill": "预计电费",
  "Carbon": "碳排放",
  "Target": "目标",
  "goal": "目标",
  "4-room HDB": "四房式组屋",
  "3 residents": "3 名家庭成员",
  "1 WFH": "1 人居家办公",
  "24-HOUR SIGNATURE": "24 小时用电特征",
  "When the home uses energy": "家庭何时用电",
  "Daytime": "日间",
  "Evening opportunity": "晚间优化空间",
  "Overnight remains above target": "夜间基荷仍高于目标",
  "DATA DESK": "数据台",
  "Bring your evidence": "导入家庭用电依据",
  "Demo files are synthetic. Real uploads are stored privately when cloud storage is connected.":
    "演示文件均为合成数据；连接云存储后，真实上传文件将被私密保存。",
  "Electricity bill": "电费账单",
  "PNG, JPG or PDF": "PNG、JPG 或 PDF",
  "Half-hour data": "半小时用电数据",
  "CSV with time + kWh": "包含时间与用电量的 CSV",
  "Appliance label": "家电能效标签",
  "Energy label photo": "能效标签照片",
  "Comfort rules locked": "舒适度规则已锁定",
  "25°C sleep · WFH protected · ≤ S$300": "睡眠 25°C · 居家办公优先 · 预算 ≤ S$300",
  "Estimates are tool-calculated. No appliance is controlled automatically.":
    "所有估算均由计算工具生成；系统不会自动控制家电。",
  "Prototype · Agentic AI in Sustainability": "原型 · 可持续发展智能体 AI",
  "DIAGNOSIS": "诊断",
  "The bill is high for": "电费偏高源于",
  "three specific reasons.": "三个具体原因。",
  "HomeShift separates measured evidence from estimates, then shows how each specialist reached an actionable conclusion.":
    "HomeShift 区分实测证据与估算结果，并展示每个专业智能体如何得出可执行结论。",
  "Live agent run": "实时智能体运行",
  "Transparent demo engine": "透明演示引擎",
  "AGENT WORKLOG": "智能体工作记录",
  "Six specialists, one decision": "六个专家，一个决策",
  "Waiting for upstream evidence": "等待上游证据",
  "Orchestrator decision": "编排智能体决策",
  "Preserve sleep comfort, avoid purchases in week one, and target the evening cooling peak first.":
    "保护睡眠舒适度，第一周不新增购置，并优先处理晚间制冷峰值。",
  "DETECTIVE VIEW": "用电侦测视图",
  "Peak concentration": "峰值集中情况",
  "Peak": "峰值",
  "38% cooling share": "制冷占比 38%",
  "Most addressable after 19:00": "19:00 后最具优化空间",
  "Measured + label-informed estimates": "实测数据 + 能效标签估算",
  "APPLIANCE AUDIT": "家电审计",
  "Estimated monthly contribution": "预计月度用电贡献",
  "Diagnosis complete. All three proposed pathways satisfy the S$300 hard budget limit.":
    "诊断完成。三套方案均满足 S$300 的硬性预算限制。",
  "Compare three plans": "比较三套方案",
  "NEGOTIATED OPTIONS": "协商后的方案",
  "Choose the trade-off,": "选择你接受的权衡，",
  "not a generic tip.": "而不是通用建议。",
  "Cost, comfort and carbon agents score every measure. Hard constraints are enforced before a plan reaches you.":
    "成本、舒适度与碳排智能体分别评估每项措施；方案生成前必须满足所有硬性约束。",
  "Sleep protected": "睡眠舒适度已保护",
  "Under S$300": "低于 S$300",
  "Best fit": "最佳匹配",
  "monthly energy": "月度用电",
  "Bill saving": "电费节省",
  "CO₂ avoided": "减少 CO₂",
  "Comfort": "舒适度",
  "Upfront": "前期投入",
  "Choose ": "选择",
  "Choose": "选择",
  "% confidence": "% 置信度",
  "Tool-verified math": "工具验证计算",
  "Tariff: S$0.3478/kWh · Grid factor: 0.402 kg CO₂/kWh":
    "电价：S$0.3478/kWh · 电网系数：0.402 kg CO₂/kWh",
  "Hard constraints": "硬性约束",
  "No recommendation violates 25°C sleep comfort or WFH availability":
    "所有建议均不会违反 25°C 睡眠舒适度或居家办公可用性",
  "Adaptive": "持续调整",
  "Week-two actions change when verified performance differs from plan":
    "当实际效果与计划存在偏差时，第二周行动将自动调整",
  "ACTION LOOP": "行动闭环",
  "Seven small shifts.": "七个小改变。",
  "One measurable result.": "一个可验证结果。",
  "week complete": "本周完成",
  "WEEK ONE": "第一周",
  "Your action board": "你的行动任务板",
  "done": "已完成",
  "/7 done": "/7 已完成",
  "Setup": "设置",
  "LIVE FORECAST": "实时预测",
  "On course": "进展正常",
  "planned monthly reduction": "预计月度节电量",
  "Bill": "电费",
  "DAY-7 CHECK-IN": "第 7 天验证",
  "Close the loop": "完成数据闭环",
  "Import the preloaded after-data to compare forecast with observed performance.":
    "导入预置的执行后数据，对比预测与实际表现。",
  "Verify after-data": "验证执行后数据",
  "synthetic_week1_after.csv · clearly labelled": "synthetic_week1_after.csv · 已明确标注为合成数据",
  "VERIFIED RESULT": "已验证结果",
  "less energy observed": "实际用电下降",
  "% less energy observed": "% 实际用电下降",
  "Slightly below the 10% target, with strong comfort compliance. The coach keeps the cooling routine and strengthens the plug-load reminder next week.":
    "结果略低于 10% 目标，但舒适度保持良好。行动教练将保留制冷计划，并在下周加强插座负荷提醒。",
  "Actual use": "实际用电",
  "baseline": "基线",
  "Bill saved": "节省电费",
  "tool calculated": "工具计算",
  "grid factor applied": "已应用电网系数",
  "Vs. plan": "相比计划",
  "adjust next week": "下周调整",
  "/mo": "/月",
  "kg/mo": "kg/月",
  "Plan adjusted:": "计划已调整：",
  "keep 25°C start temperature; add an automatic 00:00 plug reminder on three nights.":
    "保持 25°C 起始温度；每周三晚增加 00:00 插座断电提醒。",
  "Maximum Savings": "最大节省",
  "Save most": "节省最多",
  "Sharper changes for the lowest monthly bill.": "采用更积极的调整，以获得最低月度电费。",
  "Balanced": "均衡方案",
  "Recommended": "推荐",
  "Meets the 10% goal while protecting sleep and work comfort.":
    "在保护睡眠与工作舒适度的同时实现 10% 目标。",
  "Low Carbon": "低碳方案",
  "Cut carbon": "减少碳排",
  "The largest energy reduction with a small equipment upgrade.":
    "通过小规模设备升级实现最大节能量。",
  "Raise overnight AC to 27°C": "夜间空调调至 27°C",
  "Use sleep mode from 23:30 and a fan for the first hour.":
    "23:30 起使用睡眠模式，首小时配合风扇。",
  "Cut the hidden baseload": "降低隐藏基荷",
  "Switch off the entertainment and office power strips overnight.":
    "夜间关闭娱乐设备与办公区插线板。",
  "Cold-wash and line-dry": "冷水洗涤并自然晾干",
  "Move three weekly cycles outside the evening peak.":
    "每周三次洗衣移出晚间高峰。",
  "Use AC smart sleep mode": "使用空调智能睡眠模式",
  "Start at 25°C, then step up by 1°C after 90 minutes.":
    "从 25°C 开始，90 分钟后升高 1°C。",
  "Create a night shutdown routine": "建立夜间断电例程",
  "Switch two plug groups off at 00:00; keep the work setup available.":
    "00:00 关闭两组插座，同时保留办公设备可用。",
  "Shift two laundry cycles": "调整两次洗衣时间",
  "Cold-wash on Tuesday and Saturday before 18:00.":
    "周二和周六 18:00 前使用冷水洗涤。",
  "Adopt the balanced routine": "采用均衡方案",
  "Keep the same comfort-preserving schedule as the recommended plan.":
    "沿用推荐方案中保护舒适度的时间安排。",
  "Replace the oldest refrigerator": "更换最旧的冰箱",
  "Move to a five-tick model at the next planned replacement.":
    "下次计划更换时选择五级能效型号。",
  "Tune cooling maintenance": "优化制冷设备维护",
  "Clean filters monthly and seal the bedroom door gap.":
    "每月清洁滤网并密封卧室门缝。",
  "Highest bill reduction while staying inside the S$300 budget, with a noticeable change to sleep temperature.":
    "在 S$300 预算内实现最大电费降幅，但睡眠温度会有明显变化。",
  "The only plan that reaches the target with no purchase and keeps every hard comfort constraint intact.":
    "唯一无需购置设备、达到目标且满足全部舒适度硬约束的方案。",
  "Greatest carbon benefit and still within budget; payback is longer than the seven-day trial.":
    "碳减排效益最高且仍在预算内，但回收期超过七天试用周期。",
  "Air conditioning": "空调",
  "Water heating": "热水器",
  "Refrigeration": "冰箱",
  "Laundry": "洗衣",
  "Lighting & plugs": "照明与插座",
  "Evening peaks + 8 h/night usage": "晚间峰值 + 每晚使用 8 小时",
  "Three residents, daily showers": "3 名成员，每日淋浴",
  "Energy label + continuous duty cycle": "能效标签 + 持续运行周期",
  "Four weekly warm-water cycles": "每周 4 次温水洗涤",
  "Overnight baseload pattern": "夜间基荷特征",
  "Cooling drives the evening peak": "制冷推高晚间峰值",
  "The steep rise after 19:00 is consistent with overlapping air-conditioning and shower demand.":
    "19:00 后的用电快速上升与空调和淋浴需求叠加一致。",
  "Overnight baseload stays elevated": "夜间基荷持续偏高",
  "Always-on plugs and an older refrigerator appear to keep demand above a comparable-home benchmark.":
    "常开插座与老旧冰箱可能使夜间用电高于同类家庭基准。",
  "Laundry compounds the 20:00 peak": "洗衣进一步加剧 20:00 峰值",
  "Moving two weekly cycles and using cold water reduces peak overlap without changing total household routines.":
    "每周调整两次洗衣并使用冷水，可在不改变整体作息的情况下减少峰值叠加。",
  "Four recurring step changes align with the declared washing schedule.":
    "四次重复的阶梯变化与申报的洗衣时间一致。",
  "Consumption Detective": "用电侦探",
  "Appliance Auditor": "家电审计师",
  "Cost Optimizer": "成本优化师",
  "Comfort Guardian": "舒适度守护者",
  "Carbon Analyst": "碳排分析师",
  "Plan & Action Coach": "计划与行动教练",
  "Checked 1,440 half-hour intervals": "检查了 1,440 个半小时区间",
  "Found evening cooling peak and high overnight baseload": "发现晚间制冷峰值和偏高夜间基荷",
  "Matched declared appliances and energy label": "匹配申报家电与能效标签",
  "Air conditioner estimated at 38% of monthly demand": "空调预计占月度用电的 38%",
  "Simulated tariff impact and payback": "模拟电价影响和回收期",
  "Validated all monetary estimates with calculation tools": "使用计算工具验证全部金额估算",
  "Applied sleep, WFH and temperature constraints": "应用睡眠、居家办公和温度约束",
  "Rejected two aggressive cooling changes": "否决两项激进制冷调整",
  "Ranked measures by avoided emissions": "按减排效益排序措施",
  "Verified emissions against the configured grid factor": "根据配置的电网系数验证碳排",
  "Negotiated three feasible pathways": "协商形成三套可行方案",
  "Recommended the no-cost balanced plan": "推荐零成本的均衡方案",
  "Set the baseline": "设定基线",
  "Confirm the three comfort rules and photograph AC settings.":
    "确认三项舒适度规则并拍摄空调设置。",
  "Program smart sleep": "设置智能睡眠",
  "Start at 25°C and step up once after 90 minutes.":
    "从 25°C 开始，90 分钟后升高一次。",
  "Tame the baseload": "降低基荷",
  "Create two labelled shutdown groups for office and TV plugs.":
    "为办公区和电视插座建立两组带标签的断电组。",
  "Shift the wash": "调整洗衣时间",
  "Run one cold-water cycle before 18:00.": "18:00 前完成一次冷水洗涤。",
  "Check comfort": "检查舒适度",
  "Rate sleep comfort; keep 25°C if the score falls below 4/5.":
    "评价睡眠舒适度；若低于 4/5，则保持 25°C。",
  "Clean for efficiency": "清洁以提升效率",
  "Clean the bedroom AC filter and check the door seal.":
    "清洁卧室空调滤网并检查门缝密封。",
  "Verify and adapt": "验证并调整",
  "Import the after-data and let HomeShift adjust next week.":
    "导入执行后数据，让 HomeShift 调整下周计划。",
};

export function translate(locale: Locale, value: string): string {
  if (locale === "en" || !value.trim()) return value;

  const normalized = value.trim().replace(/\s+/g, " ");
  const exact = zh[normalized];
  if (exact) return exact;

  const peak = normalized.match(/^Peak (.+)$/);
  if (peak) return `峰值 ${peak[1]}`;

  const complete = normalized.match(/^(\d+)\/7 done$/);
  if (complete) return `${complete[1]}/7 已完成`;

  const perDay = normalized.match(/^−(.+) kWh\/day$/);
  if (perDay) return `−${perDay[1]} kWh/天`;

  const observed = normalized.match(/^(.+)% less energy observed$/);
  if (observed) return `实际用电下降 ${observed[1]}%`;

  const pathway = normalized.match(
    /^The (.+) pathway turns recommendations into household-sized tasks, then checks the observed data before adapting\.$/,
  );
  if (pathway) {
    return `${translate(locale, pathway[1])}会把建议拆分为家庭可执行的小任务，并根据实测数据持续调整。`;
  }

  const dailyShare = normalized.match(
    /^(.+)% of daily use occurs after 18:00; highest interval is (.+)\.$/,
  );
  if (dailyShare) {
    return `全天 ${dailyShare[1]}% 的用电发生在 18:00 后；最高区间为 ${dailyShare[2]}。`;
  }

  const overnight = normalized.match(
    /^(.+) kWh per half-hour versus a (.+) kWh target\.$/,
  );
  if (overnight) {
    return `每半小时 ${overnight[1]} kWh，高于 ${overnight[2]} kWh 的目标值。`;
  }

  const selected = normalized.match(/^(.+) plan selected$/);
  if (selected) return `已选择${translate(locale, selected[1])}`;

  const loaded = normalized.match(/^Loaded (\d+) interval records$/);
  if (loaded) return `已载入 ${loaded[1]} 条用电记录`;

  const ready = normalized.match(/^(.+) is ready for analysis$/);
  if (ready) return `${ready[1]} 已可用于分析`;

  return value;
}
