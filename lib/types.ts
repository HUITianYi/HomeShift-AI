export type AppStage = "baseline" | "diagnosis" | "plans";

export type SourceKind = "bill" | "interval" | "label";

export type LocaleCode = "en" | "zh";

export interface HouseholdProfile {
  householdName: string;
  homeType: string;
  residents: number;
  workFromHome: boolean;
  monthlyTargetPercent: number;
  comfortTemperature: number;
  budgetSgd: number;
}

export interface BillInput {
  periodStart: string;
  periodEnd: string;
  totalKwh: number;
  totalCostSgd: number;
}

export interface ApplianceInputs {
  airConditioning: {
    quantity: number;
    ratedPowerKw: number;
    hoursPerDay: number;
    currentTemperature: number;
  };
  refrigerator: {
    annualKwh: number;
    replacementCostSgd: number;
  };
  waterHeater: {
    ratedPowerKw: number;
    minutesPerDay: number;
  };
  washingMachine: {
    kwhPerCycle: number;
    cyclesPerWeek: number;
  };
  otherMonthlyKwh: number;
}

export interface AnalysisParameters {
  tariffSgdPerKwh: number;
  gridEmissionKgPerKwh: number;
}

export interface LoadPoint {
  timestamp: string;
  time: string;
  kwh: number;
  period: "overnight" | "daytime" | "evening";
}

export interface LoadDataQuality {
  startDate: string;
  endDate: string;
  dayCount: number;
  recordCount: number;
  expectedIntervals: number;
  missingIntervals: number;
  duplicateIntervals: number;
  coveragePercent: number;
  warnings: string[];
}

export interface ParsedLoadData {
  points: LoadPoint[];
  quality: LoadDataQuality;
}

export interface LoadPatterns {
  peakTime: string;
  peakKwh: number;
  overnightAverageKwh: number;
  overnightTargetKwh: number;
  overnightSavingPotentialKwh: number;
  eveningSharePercent: number;
  dailyAverageKwh: number;
  recordCount: number;
  dayCount: number;
}

export type ApplianceKey =
  | "air-conditioning"
  | "refrigeration"
  | "water-heating"
  | "laundry"
  | "other";

export interface ApplianceEstimate {
  key: ApplianceKey;
  name: string;
  monthlyKwh: number;
  sharePercent: number;
  basis: string;
  normalized: boolean;
}

export interface EnergyInsight {
  id: "peak" | "baseload" | "top-appliance";
  title: string;
  detail: string;
  evidence: string;
  evidenceKind: "measured" | "estimated";
  confidence: number;
  severity: "high" | "medium" | "low";
}

export type PlanActionCode =
  | "ac-maximum"
  | "ac-balanced"
  | "baseload-maximum"
  | "baseload-balanced"
  | "laundry-maximum"
  | "laundry-balanced"
  | "balanced-routine"
  | "refrigerator-upgrade"
  | "cooling-maintenance";

export interface PlanAction {
  code: PlanActionCode;
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
  feasible: boolean;
  meetsTarget: boolean;
  constraintNotes: string[];
}

export type SpecialistAgentName =
  | "Consumption Detective"
  | "Appliance Auditor"
  | "Cost Optimizer"
  | "Comfort Guardian"
  | "Carbon Analyst"
  | "Plan and Action Coach";

export interface SpecialistFinding {
  agent: SpecialistAgentName;
  task: string;
  result: string;
  evidence: "measured" | "estimated" | "tool-calculated";
}

export interface AgentDecision {
  recommendedPlanId: EnergyPlan["id"];
  rationale: string[];
  rejectedRisks: string[];
  nextActions: string[];
  specialistFindings: SpecialistFinding[];
}

export interface AgentTraceEntry {
  agent: SpecialistAgentName;
  task: string;
  result: string;
  evidence: SpecialistFinding["evidence"];
  status: "complete";
}

export interface HouseholdAnalysis {
  quality: LoadDataQuality;
  patterns: LoadPatterns;
  applianceEstimates: ApplianceEstimate[];
  insights: EnergyInsight[];
  plans: EnergyPlan[];
}

export interface AgentRequest {
  locale: LocaleCode;
  profile: HouseholdProfile;
  bill: BillInput;
  appliances: ApplianceInputs;
  parameters: AnalysisParameters;
  loadPoints: LoadPoint[];
}

export interface AgentSuccessResponse extends HouseholdAnalysis {
  mode: "live";
  model: string;
  decision: AgentDecision;
  trace: AgentTraceEntry[];
}

export interface AgentErrorResponse {
  mode: "error";
  code: "invalid_input" | "configuration_missing" | "agent_failed";
  message: string;
  details?: unknown;
}
