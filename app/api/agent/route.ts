import { Agent, run, tool } from "@openai/agents";
import { z } from "zod";
import {
  agentDecisionSchema,
  agentRequestSchema,
  specialistAgentNameSchema,
} from "@/lib/analysis-schema";
import {
  analyzeHousehold,
  calculateCarbon,
  calculateCost,
} from "@/lib/energy";
import type {
  AgentErrorResponse,
  AgentSuccessResponse,
  SpecialistAgentName,
} from "@/lib/types";

export async function POST(request: Request) {
  if (!process.env.OPENAI_API_KEY) {
    return errorResponse(
      "configuration_missing",
      "OPENAI_API_KEY is required for the live multi-agent demo.",
      503,
    );
  }

  let rawBody: unknown;
  try {
    rawBody = await request.json();
  } catch {
    return errorResponse(
      "invalid_input",
      "The request body must be valid JSON.",
      400,
    );
  }

  const parsed = agentRequestSchema.safeParse(rawBody);
  if (!parsed.success) {
    return errorResponse(
      "invalid_input",
      "Household analysis input is invalid.",
      400,
      z.flattenError(parsed.error),
    );
  }

  const { locale, profile, bill, appliances, parameters, loadPoints } =
    parsed.data;

  let analysis: ReturnType<typeof analyzeHousehold>;
  try {
    analysis = analyzeHousehold(
      profile,
      bill,
      appliances,
      parameters,
      loadPoints,
    );
  } catch (error) {
    return errorResponse(
      "invalid_input",
      error instanceof Error ? error.message : "Analysis input is invalid.",
      400,
    );
  }

  const model = process.env.OPENAI_MODEL || "gpt-5.6-terra";
  const responseLanguage =
    locale === "zh"
      ? "Write every user-facing task, result, rationale, risk and action in Simplified Chinese. Keep the required agent field names in English."
      : "Write every user-facing task, result, rationale, risk and action in English.";

  const costCalculator = tool({
    name: "calculate_energy_cost",
    description:
      "Calculate Singapore-dollar energy cost from an exact kWh value using the household's configured tariff.",
    parameters: z.object({ kwh: z.number().nonnegative() }),
    execute: async ({ kwh }) => ({
      kwh,
      costSgd: calculateCost(kwh, parameters.tariffSgdPerKwh),
      tariffSgdPerKwh: parameters.tariffSgdPerKwh,
    }),
  });

  const carbonCalculator = tool({
    name: "calculate_carbon_impact",
    description:
      "Calculate carbon impact from an exact kWh value using the household's configured grid factor.",
    parameters: z.object({ kwh: z.number().nonnegative() }),
    execute: async ({ kwh }) => ({
      kwh,
      carbonKg: calculateCarbon(kwh, parameters.gridEmissionKgPerKwh),
      gridFactorKgPerKwh: parameters.gridEmissionKgPerKwh,
    }),
  });

  const consumptionDetective = new Agent({
    name: "Consumption Detective",
    model,
    instructions: `${responseLanguage}
Review only the supplied measured load patterns and data-quality summary.
Identify the most actionable repeated pattern. Distinguish measured evidence from inference and never invent raw intervals.`,
  });

  const applianceAuditor = new Agent({
    name: "Appliance Auditor",
    model,
    instructions: `${responseLanguage}
Review the supplied appliance estimates, their formulas and any normalization.
State uncertainty and never invent an appliance label value.`,
  });

  const costOptimizer = new Agent({
    name: "Cost Optimizer",
    model,
    instructions: `${responseLanguage}
Evaluate only the supplied deterministic plans for bill impact, target attainment and payback.
Use calculate_energy_cost for any additional arithmetic and never alter supplied plan metrics.`,
    tools: [costCalculator],
  });

  const comfortGuardian = new Agent({
    name: "Comfort Guardian",
    model,
    instructions: `${responseLanguage}
Enforce the supplied maximum comfortable temperature, work-from-home availability and hard budget.
Reject infeasible plans and do not introduce a new constraint.`,
  });

  const carbonAnalyst = new Agent({
    name: "Carbon Analyst",
    model,
    instructions: `${responseLanguage}
Evaluate the supplied deterministic plans for carbon impact.
Use calculate_carbon_impact for any additional arithmetic and never alter supplied plan metrics.`,
    tools: [carbonCalculator],
  });

  const actionCoach = new Agent({
    name: "Plan and Action Coach",
    model,
    instructions: `${responseLanguage}
Turn a feasible trade-off into no more than seven observable, household-sized actions.
Every action must require user confirmation and must respect supplied constraints.`,
  });

  const orchestrator = new Agent({
    name: "HomeShift Orchestrator",
    model,
    outputType: agentDecisionSchema,
    instructions: `${responseLanguage}
Coordinate one household-energy decision.
Call every specialist tool exactly once before producing the final output.
The supplied numeric metrics come from deterministic formulas and must not be changed.
Recommend only a plan where feasible is true.
Return exactly six specialistFindings, one for each required agent name, without duplicates.
Use measured, estimated or tool-calculated evidence labels accurately.
Do not reveal hidden reasoning or chain-of-thought; provide only concise conclusions and evidence.`,
    tools: [
      consumptionDetective.asTool({
        toolName: "consumption_detective",
        toolDescription: "Diagnose measured load patterns.",
      }),
      applianceAuditor.asTool({
        toolName: "appliance_auditor",
        toolDescription: "Audit appliance attribution and uncertainty.",
      }),
      costOptimizer.asTool({
        toolName: "cost_optimizer",
        toolDescription: "Evaluate cost, target attainment and payback.",
      }),
      comfortGuardian.asTool({
        toolName: "comfort_guardian",
        toolDescription: "Enforce comfort, availability and budget constraints.",
      }),
      carbonAnalyst.asTool({
        toolName: "carbon_analyst",
        toolDescription: "Evaluate carbon outcomes.",
      }),
      actionCoach.asTool({
        toolName: "action_coach",
        toolDescription: "Produce observable household actions.",
      }),
    ],
  });

  try {
    const result = await run(
      orchestrator,
      JSON.stringify({
        householdProfile: profile,
        bill,
        analysisParameters: parameters,
        dataQuality: analysis.quality,
        measuredPatterns: analysis.patterns,
        applianceEstimates: analysis.applianceEstimates,
        deterministicInsights: analysis.insights,
        deterministicPlans: analysis.plans,
        calculationAssumptions: {
          airConditionerDutyFactor: 0.65,
          savingPerDegree: "6% of estimated AC energy",
          baseloadTarget: "household overnight 20th percentile",
          planSavingCap: "30% of bill baseline",
        },
      }),
      { maxTurns: 18 },
    );

    const decision = agentDecisionSchema.parse(result.finalOutput);
    validateSpecialistCoverage(
      decision.specialistFindings.map((finding) => finding.agent),
    );

    const recommendedPlan = analysis.plans.find(
      (plan) => plan.id === decision.recommendedPlanId,
    );
    if (!recommendedPlan?.feasible) {
      throw new Error("The orchestrator recommended an infeasible plan.");
    }

    const response: AgentSuccessResponse = {
      mode: "live",
      model,
      ...analysis,
      decision,
      trace: decision.specialistFindings.map((finding) => ({
        ...finding,
        status: "complete",
      })),
    };
    return Response.json(response);
  } catch (error) {
    return errorResponse(
      "agent_failed",
      error instanceof Error
        ? error.message
        : "The live multi-agent run did not complete.",
      502,
    );
  }
}

function validateSpecialistCoverage(names: SpecialistAgentName[]) {
  const expected = specialistAgentNameSchema.options;
  const unique = new Set(names);
  if (
    unique.size !== expected.length ||
    expected.some((name) => !unique.has(name))
  ) {
    throw new Error(
      "The orchestrator did not return one finding for every specialist.",
    );
  }
}

function errorResponse(
  code: AgentErrorResponse["code"],
  message: string,
  status: number,
  details?: unknown,
) {
  const body: AgentErrorResponse = {
    mode: "error",
    code,
    message,
    ...(details === undefined ? {} : { details }),
  };
  return Response.json(body, { status });
}
