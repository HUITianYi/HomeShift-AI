import { z } from "zod";

const nonNegative = z.number().finite().nonnegative();
const positive = z.number().finite().positive();

export const householdProfileSchema = z.object({
  householdName: z.string().trim().min(1).max(80),
  homeType: z.string().trim().min(1).max(80),
  residents: z.number().int().min(1).max(20),
  workFromHome: z.boolean(),
  monthlyTargetPercent: z.number().min(1).max(30),
  comfortTemperature: z.number().min(20).max(30),
  budgetSgd: nonNegative.max(100_000),
});

export const billInputSchema = z
  .object({
    periodStart: z.iso.date(),
    periodEnd: z.iso.date(),
    totalKwh: positive.max(100_000),
    totalCostSgd: nonNegative.max(1_000_000),
  })
  .refine((value) => value.periodEnd >= value.periodStart, {
    message: "Bill end date must not be before the start date.",
    path: ["periodEnd"],
  });

export const applianceInputsSchema = z.object({
  airConditioning: z.object({
    quantity: z.number().int().min(0).max(20),
    ratedPowerKw: nonNegative.max(20),
    hoursPerDay: nonNegative.max(24),
    currentTemperature: z.number().min(16).max(30),
  }),
  refrigerator: z.object({
    annualKwh: nonNegative.max(20_000),
    replacementCostSgd: nonNegative.max(100_000),
  }),
  waterHeater: z.object({
    ratedPowerKw: nonNegative.max(50),
    minutesPerDay: nonNegative.max(1_440),
  }),
  washingMachine: z.object({
    kwhPerCycle: nonNegative.max(50),
    cyclesPerWeek: nonNegative.max(50),
  }),
  otherMonthlyKwh: nonNegative.max(100_000),
});

export const analysisParametersSchema = z.object({
  tariffSgdPerKwh: positive.max(10),
  gridEmissionKgPerKwh: positive.max(10),
});

export const loadPointSchema = z.object({
  timestamp: z.iso.datetime({ offset: true }),
  time: z.string().regex(/^\d{2}:\d{2}$/),
  kwh: nonNegative.max(10_000),
  period: z.enum(["overnight", "daytime", "evening"]),
});

export const agentRequestSchema = z
  .object({
    locale: z.enum(["en", "zh"]),
    profile: householdProfileSchema,
    bill: billInputSchema,
    appliances: applianceInputsSchema,
    parameters: analysisParametersSchema,
    loadPoints: z.array(loadPointSchema).min(1).max(1_600),
  })
  .refine(
    (value) =>
      value.profile.comfortTemperature >=
      value.appliances.airConditioning.currentTemperature,
    {
      message:
        "Highest comfortable temperature must not be below the current AC temperature.",
      path: ["profile", "comfortTemperature"],
    },
  );

export const specialistAgentNameSchema = z.enum([
  "Consumption Detective",
  "Appliance Auditor",
  "Cost Optimizer",
  "Comfort Guardian",
  "Carbon Analyst",
  "Plan and Action Coach",
]);

export const specialistFindingSchema = z.object({
  agent: specialistAgentNameSchema,
  task: z.string().trim().min(1).max(220),
  result: z.string().trim().min(1).max(500),
  evidence: z.enum(["measured", "estimated", "tool-calculated"]),
});

export const agentDecisionSchema = z.object({
  recommendedPlanId: z.enum(["money", "balanced", "carbon"]),
  rationale: z.array(z.string().trim().min(1).max(400)).min(1).max(3),
  rejectedRisks: z.array(z.string().trim().min(1).max(400)).max(3),
  nextActions: z.array(z.string().trim().min(1).max(400)).min(1).max(7),
  specialistFindings: z.array(specialistFindingSchema).length(6),
});
