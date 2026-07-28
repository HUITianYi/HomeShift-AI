export type Locale = "zh" | "en";

const dictionary = {
  zh: {
    data: "数据接入",
    baseline: "基线",
    diagnosis: "诊断",
    plan: "计划",
    track: "追踪与记忆",
    configureModel: "模型",
    trace: "Agent 轨迹",
    chat: "问 HomeShift",
    report: "HTML 周报",
    noData: "还没有当前家庭数据",
    live: "实时模型",
    mock: "离线彩排",
    synthetic: "合成数据",
    real: "真实数据",
  },
  en: {
    data: "Data",
    baseline: "Baseline",
    diagnosis: "Diagnosis",
    plan: "Plan",
    track: "Track & memory",
    configureModel: "Model",
    trace: "Agent trace",
    chat: "Ask HomeShift",
    report: "HTML report",
    noData: "No household data yet",
    live: "Live model",
    mock: "Offline rehearsal",
    synthetic: "Synthetic data",
    real: "Real data",
  },
} as const;

export function useCopy(locale: Locale) {
  return dictionary[locale];
}
