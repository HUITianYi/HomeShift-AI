import type {
  AgentTraceEntry,
  DailyTask,
  HouseholdProfile,
} from "./types";

export const demoProfile: HouseholdProfile = {
  homeType: "4-room HDB",
  residents: 3,
  workFromHome: true,
  monthlyKwh: 420,
  monthlyTargetPercent: 10,
  comfortTemperature: 25,
  budgetSgd: 300,
};

export const agentTrace: AgentTraceEntry[] = [
  {
    agent: "Consumption Detective",
    task: "Checked 1,440 half-hour intervals",
    result: "Found evening cooling peak and high overnight baseload",
    status: "complete",
  },
  {
    agent: "Appliance Auditor",
    task: "Matched declared appliances and energy label",
    result: "Air conditioner estimated at 38% of monthly demand",
    status: "complete",
  },
  {
    agent: "Cost Optimizer",
    task: "Simulated tariff impact and payback",
    result: "Validated all monetary estimates with calculation tools",
    status: "complete",
  },
  {
    agent: "Comfort Guardian",
    task: "Applied sleep, WFH and temperature constraints",
    result: "Rejected two aggressive cooling changes",
    status: "complete",
  },
  {
    agent: "Carbon Analyst",
    task: "Ranked measures by avoided emissions",
    result: "Verified emissions against the configured grid factor",
    status: "complete",
  },
  {
    agent: "Plan & Action Coach",
    task: "Negotiated three feasible pathways",
    result: "Recommended the no-cost balanced plan",
    status: "complete",
  },
];

export const dailyTasks: DailyTask[] = [
  {
    day: 1,
    title: "Set the baseline",
    detail: "Confirm the three comfort rules and photograph AC settings.",
    impactKwh: 0,
  },
  {
    day: 2,
    title: "Program smart sleep",
    detail: "Start at 25°C and step up once after 90 minutes.",
    impactKwh: 0.8,
  },
  {
    day: 3,
    title: "Tame the baseload",
    detail: "Create two labelled shutdown groups for office and TV plugs.",
    impactKwh: 0.4,
  },
  {
    day: 4,
    title: "Shift the wash",
    detail: "Run one cold-water cycle before 18:00.",
    impactKwh: 0.2,
  },
  {
    day: 5,
    title: "Check comfort",
    detail: "Rate sleep comfort; keep 25°C if the score falls below 4/5.",
    impactKwh: 0.8,
  },
  {
    day: 6,
    title: "Clean for efficiency",
    detail: "Clean the bedroom AC filter and check the door seal.",
    impactKwh: 0.3,
  },
  {
    day: 7,
    title: "Verify and adapt",
    detail: "Import the after-data and let HomeShift adjust next week.",
    impactKwh: 0.9,
  },
];
