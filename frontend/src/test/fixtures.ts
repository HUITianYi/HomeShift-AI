export const statusFixture = {
  ready: true,
  data: {
    available: true,
    kind: "real",
    dataset: "uci",
    start: "2009-01-01",
    end: "2009-02-28",
    tracking_kind: null,
  },
  region: { code: "fr", name: "Sceaux, France", currency: "EUR" },
  plan: { active: false, version: null },
  memory_count: 0,
  model: {
    provider: "mock",
    kind: "mock",
    label: "离线 Mock",
    model: "-",
    configured: true,
    explicit: true,
    reason: "explicit",
  },
};

const bilingual = (zh: string, en: string) => ({ zh, en });
const money = (value: number) => ({ value, display: `€${value.toFixed(2)}`, currency: "EUR" });
const quantity = (value: number, unit: string) => ({ value, display: `${value} ${unit}`, unit });

export const workspaceFixture = {
  meta: {
    schema_version: "1.0",
    data_kind: "real",
    data_badge: bilingual("真实数据", "Real dataset"),
    region: { code: "fr", name: "Sceaux, France", timezone: "Europe/Paris", climate: "temperate" },
    currency: { code: "EUR", symbol: "€" },
    tariff: { plan: "regulated", rate_per_kwh: 0.2516, gst_rate: 0.2, note: "EDF" },
    carbon: { grid_emission_factor_kg_per_kwh: 0.056, note: "France grid" },
    provenance: {
      dataset: { id: "uci", title: "UCI France household" },
      window: { completeness_pct: 98.7 },
      weather: { source: "Open-Meteo" },
      known_limitations: ["NILM is estimated"],
    },
  },
  household: {
    name: bilingual("法国真实家庭", "French real household"),
    location: "Sceaux, France",
    summary: bilingual("画像由真实曲线反推", "Inferred from real load"),
    tags: ["Peak 20:30"],
    profile_origin: bilingual("画像由真实用电曲线反推", "Profile inferred from a real load curve"),
    assumptions: [],
    comfort_rules: [],
    goal: { display: "−10%", priority: "comfort first" },
  },
  baseline: {
    available: true,
    period: { start: "2009-02-01", end: "2009-02-28", days: 28 },
    headline: {
      kwh_this_month: quantity(390, "kWh"),
      avg_daily_kwh: quantity(13, "kWh"),
      est_bill: money(117.45),
      carbon_kg: quantity(21.8, "kg"),
      sources_count: 4,
    },
    extremes: {},
    signature_24h: {
      slots: Array.from({ length: 48 }, (_, slot) => ({ slot, time: `${String(Math.floor(slot / 2)).padStart(2, "0")}:${slot % 2 ? "30" : "00"}`, kwh: 0.2 + slot / 100 })),
      peak: { time: "20:30", kwh: 0.8 },
      bands: [],
    },
    daily_series: [
      { date: "2009-02-27", kwh: 12, temp_c: 8 },
      { date: "2009-02-28", kwh: 14, temp_c: 9 },
    ],
    evidence: [
      { kind: "half_hour_data", file: "usage.csv", label: bilingual("半小时电表数据", "Half-hour data"), available: true, rows: 1344 },
    ],
  },
  diagnosis: {
    available: true,
    days: 28,
    avg_daily_total_kwh: 13,
    categories: [
      { id: "water_heater", rank: 1, label: bilingual("热水器", "Water heater"), kwh_per_day: 4, kwh_per_month: 120, share_pct: 31, cost_per_month: money(36), co2_kg_per_month: 6.7 },
    ],
    findings: [],
    method: { name: bilingual("NILM 启发式负载分解", "Heuristic NILM"), notes: [] },
    accuracy: { available: false, note: bilingual("无真值", "No ground truth") },
    daily_series: [],
  },
  plans: {
    available: true,
    has_committed_plan: false,
    version: null,
    rationale: "",
    expected_per_month: { kwh: null, cost: money(0), co2_kg: null },
    potential_per_month: { kwh: 26, cost: money(7.8), co2_kg: 1.5 },
    candidates: [],
    vetoed_by_comfort: [],
    comfort_summary: {},
    seven_day_schedule: [],
  },
  track: {
    available: false,
    status: "no_plan",
    message: bilingual("尚无计划", "No plan"),
  },
  agents: {
    count: 7,
    orchestration: bilingual("单编排器 + 七个角色", "One orchestrator + seven roles"),
    agents: Array.from({ length: 7 }, (_, index) => ({
      id: `role-${index}`,
      order: index + 1,
      name: bilingual(`角色 ${index + 1}`, `Role ${index + 1}`),
      mission: bilingual("专业职责", "Specialist mission"),
      tools: [],
      has_veto: index === 5,
      calls_in_last_run: 0,
    })),
    trace: [],
  },
  memory: { count: 0, items: [] },
  runtime: { model: statusFixture.model, tracking: {} },
  disclaimers: {},
};

export const providersFixture = {
  providers: [
    { name: "mock", label: "离线 Mock", kind: "mock", default_model: "-", configured: true, notes: "rehearsal", selected: true },
  ],
  current: statusFixture.model,
};

export const datasetsFixture = {
  datasets: [
    { id: "synthetic", title: "HomeShift 合成家庭", short: "离线演示", manual: false, license: "项目内生成", period: "动态", raw_resolution_minutes: 30, recommended_for: "彩排", region: {} },
    { id: "uci", title: "UCI France", short: "法国真实家庭", manual: false, license: "CC BY 4.0", period: "2006-2010", raw_resolution_minutes: 1, recommended_for: "NILM", region: {} },
  ],
};

export const profileFixture = {
  profile: {
    home_type: "Maison",
    location: "Sceaux, France",
    household: "Test household",
    ac_setpoint: 24,
    heater_mode: "timed",
    wash_mode: "warm",
    comfort_preferences: { max_ac_setpoint: 26, notes: "comfort" },
    goals: { monthly_saving_target_pct: 10, priority: "comfort first" },
  },
};
