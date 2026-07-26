export type AppStage = "baseline" | "diagnosis" | "plans" | "track";

export type SourceKind = "bill" | "interval" | "label";

export interface HouseholdProfile {
  homeType: string;
  residents: number;
  workFromHome: boolean;
  monthlyKwh: number;
  monthlyTargetPercent: number;
  comfortTemperature: number;
  budgetSgd: number;
}

export interface LoadPoint {
  time: string;
  kwh: number;
  period: "overnight" | "daytime" | "evening";
}

export interface ApplianceEstimate {
  name: string;
  monthlyKwh: number;
  sharePercent: number;
  basis: string;
}

export interface EnergyInsight {
  id: string;
  title: string;
  detail: string;
  evidence: string;
  confidence: number;
  severity: "high" | "medium" | "low";
}

export interface PlanAction {
  title: string;
  detail: string;
  monthlySavingKwh: number;
  effort: "Low" | "Medium" | "High";
}

export interface EnergyPlan {
  id: "money" | "balanced" | "carbon";
  name: string;
  shortName: string;
  description: string;
  accent: string;
  monthlySavingKwh: number;
  monthlySavingSgd: number;
  annualSavingSgd: number;
  carbonSavingKg: number;
  upfrontCostSgd: number;
  paybackMonths: number | null;
  comfortScore: number;
  difficulty: "Easy" | "Moderate";
  actions: PlanAction[];
  rationale: string;
}

export interface AgentTraceEntry {
  agent: string;
  task: string;
  result: string;
  status: "complete" | "checking";
}

export interface DailyTask {
  day: number;
  title: string;
  detail: string;
  impactKwh: number;
}

export interface ComparisonResult {
  actualMonthlyKwh: number;
  actualSavingKwh: number;
  actualSavingPercent: number;
  plannedSavingKwh: number;
  varianceKwh: number;
  actualSavingSgd: number;
  actualCarbonSavingKg: number;
}
