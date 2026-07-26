import { Agent, run, tool } from "@openai/agents";
import { z } from "zod";
import {
  calculateCarbon,
  calculateCost,
  generatePlans,
} from "@/lib/energy";
import type { HouseholdProfile } from "@/lib/types";

export async function POST(request: Request) {
  if (!process.env.OPENAI_API_KEY) {
    return Response.json(
      {
        mode: "demo",
        message:
          "OPENAI_API_KEY is not configured. Deterministic demo results are active.",
      },
      { status: 503 },
    );
  }

  const body = (await request.json()) as Record<string, unknown>;
  const profile = body.profile as HouseholdProfile;
  const plans = generatePlans(profile);
  const model = process.env.OPENAI_MODEL || "gpt-5.6-terra";

  const costCalculator = tool({
    name: "calculate_energy_cost",
    description:
      "Calculate Singapore-dollar energy cost from an exact kWh value using the configured tariff.",
    parameters: z.object({ kwh: z.number().nonnegative() }),
    execute: async ({ kwh }) => ({
      kwh,
      costSgd: calculateCost(kwh),
      tariffSgdPerKwh: 0.3478,
    }),
  });

  const carbonCalculator = tool({
    name: "calculate_carbon_impact",
    description:
      "Calculate avoided carbon emissions from an exact kWh value using the configured grid factor.",
    parameters: z.object({ kwh: z.number().nonnegative() }),
    execute: async ({ kwh }) => ({
      kwh,
      carbonKg: calculateCarbon(kwh),
      gridFactorKgPerKwh: 0.402,
    }),
  });

  const consumptionDetective = new Agent({
    name: "Consumption Detective",
    model,
    instructions:
      "Review only the supplied load-pattern evidence. Identify the two most actionable patterns and explicitly distinguish measured evidence from inference. Be concise.",
  });
  const applianceAuditor = new Agent({
    name: "Appliance Auditor",
    model,
    instructions:
      "Review the supplied household and appliance estimates. Challenge implausible attribution and state uncertainty. Never invent label values.",
  });
  const costOptimizer = new Agent({
    name: "Cost Optimizer",
    model,
    instructions:
      "Evaluate the supplied, pre-calculated plans for bill impact and payback. Use the calculator for any additional arithmetic. Never calculate money mentally.",
    tools: [costCalculator],
  });
  const comfortGuardian = new Agent({
    name: "Comfort Guardian",
    model,
    instructions:
      "Enforce 25°C sleep comfort, work-from-home availability and a S$300 hard budget. Reject any option that violates a hard constraint.",
  });
  const carbonAnalyst = new Agent({
    name: "Carbon Analyst",
    model,
    instructions:
      "Evaluate the supplied, pre-calculated plans for carbon impact. Use the calculator for any additional arithmetic. Never calculate emissions mentally.",
    tools: [carbonCalculator],
  });
  const actionCoach = new Agent({
    name: "Plan and Action Coach",
    model,
    instructions:
      "Turn the selected trade-off into no more than seven concrete household actions. Each action must be observable and user-confirmed.",
  });

  const orchestrator = new Agent({
    name: "HomeShift Orchestrator",
    model,
    instructions: `You coordinate a household-energy decision. Call every specialist once.
The supplied numeric plan metrics were produced by deterministic tools and must not be changed.
Return a compact decision memo with: recommendedPlanId, rationale, rejectedRisks, and nextAction.
Do not reveal hidden reasoning or chain-of-thought; provide only conclusions and evidence.`,
    tools: [
      consumptionDetective.asTool({
        toolName: "consumption_detective",
        toolDescription: "Diagnose load patterns from supplied evidence.",
      }),
      applianceAuditor.asTool({
        toolName: "appliance_auditor",
        toolDescription: "Audit appliance attribution and uncertainty.",
      }),
      costOptimizer.asTool({
        toolName: "cost_optimizer",
        toolDescription: "Evaluate cost and payback using deterministic tools.",
      }),
      comfortGuardian.asTool({
        toolName: "comfort_guardian",
        toolDescription: "Enforce household comfort and budget constraints.",
      }),
      carbonAnalyst.asTool({
        toolName: "carbon_analyst",
        toolDescription: "Evaluate carbon outcomes using deterministic tools.",
      }),
      actionCoach.asTool({
        toolName: "action_coach",
        toolDescription: "Convert the decision into an actionable plan.",
      }),
    ],
  });

  try {
    const result = await run(
      orchestrator,
      JSON.stringify({
        householdProfile: profile,
        detectedPatterns: body.patterns,
        toolCalculatedPlans: plans,
      }),
      { maxTurns: 12 },
    );

    return Response.json({
      mode: "live",
      model,
      finalOutput: result.finalOutput,
      trace: [
        "Consumption patterns reviewed",
        "Appliance attribution audited",
        "Cost, comfort and carbon constraints negotiated",
        "Action pathway produced",
      ],
    });
  } catch (error) {
    return Response.json(
      {
        mode: "demo",
        message:
          error instanceof Error ? error.message : "Agent run did not complete.",
      },
      { status: 502 },
    );
  }
}
