import assert from "node:assert/strict";
import test from "node:test";
import { agentDecisionSchema, agentRequestSchema } from "../lib/analysis-schema";
import {
  aggregateDailyProfile,
  analyzeHousehold,
  demoCsvTemplate,
  generateDemoLoad,
  parseIntervalCsv,
} from "../lib/energy";
import {
  demoAppliances,
  demoBill,
  demoParameters,
  demoProfile,
} from "../lib/demo-data";

test("parses a complete seven-day CSV and creates 48 average slots", () => {
  const parsed = parseIntervalCsv(demoCsvTemplate());
  assert.equal(parsed.quality.dayCount, 7);
  assert.equal(parsed.quality.recordCount, 336);
  assert.equal(parsed.quality.coveragePercent, 100);
  assert.equal(aggregateDailyProfile(parsed.points).length, 48);
});

test("accepts common header aliases and semicolon delimiters", () => {
  const source = demoCsvTemplate()
    .replace("timestamp,kwh", "date_time;consumption")
    .split("\n")
    .map((line, index) => (index === 0 ? line : line.replace(",", ";")))
    .join("\n");
  const parsed = parseIntervalCsv(source);
  assert.equal(parsed.quality.recordCount, 336);
});

test("sorts intervals and replaces duplicate timestamps with the latest row", () => {
  const rows = demoCsvTemplate().split("\n");
  const duplicate = `${rows[1].split(",")[0]},0.999`;
  const parsed = parseIntervalCsv(
    [rows[0], ...rows.slice(1).reverse(), duplicate].join("\n"),
  );
  assert.equal(parsed.quality.duplicateIntervals, 1);
  assert.equal(parsed.points[0].kwh, 0.999);
});

test("rejects negative values, short ranges, long ranges and low coverage", () => {
  const rows = demoCsvTemplate().split("\n");
  assert.throws(
    () => parseIntervalCsv([rows[0], rows[1].replace(/,[^,]+$/, ",-1")].join("\n")),
    /non-negative/,
  );
  assert.throws(
    () => parseIntervalCsv(rows.slice(0, 1 + 6 * 48).join("\n")),
    /between 7 and 30/,
  );

  const longRows = [
    "timestamp,kwh",
    ...generateDemoLoad(31).map(
      (point) =>
        `${point.timestamp.slice(0, 16).replace("T", " ")},${point.kwh}`,
    ),
  ];
  assert.throws(
    () => parseIntervalCsv(longRows.join("\n")),
    /between 7 and 30/,
  );

  const sparseRows = [
    rows[0],
    ...rows.slice(1).filter((_, index) => index % 4 !== 0),
  ];
  assert.throws(() => parseIntervalCsv(sparseRows.join("\n")), /at least 80%/);
});

test("reconciles appliance estimates to the bill and keeps formulas traceable", () => {
  const analysis = analyzeHousehold(
    demoProfile,
    demoBill,
    demoAppliances,
    demoParameters,
    generateDemoLoad(),
  );
  const total = analysis.applianceEstimates.reduce(
    (sum, item) => sum + item.monthlyKwh,
    0,
  );
  assert.ok(Math.abs(total - demoBill.totalKwh) < 0.2);
  assert.equal(
    analysis.applianceEstimates.find(
      (item) => item.key === "air-conditioning",
    )?.monthlyKwh,
    210.6,
  );
  assert.ok(analysis.applianceEstimates.every((item) => !item.normalized));
});

test("normalizes over-attribution and applies plan caps and constraints", () => {
  const heavyAppliances = structuredClone(demoAppliances);
  heavyAppliances.airConditioning.ratedPowerKw = 5;
  heavyAppliances.refrigerator.replacementCostSgd = 500;
  const analysis = analyzeHousehold(
    demoProfile,
    demoBill,
    heavyAppliances,
    demoParameters,
    generateDemoLoad(),
  );
  const total = analysis.applianceEstimates.reduce(
    (sum, item) => sum + item.monthlyKwh,
    0,
  );
  assert.ok(Math.abs(total - demoBill.totalKwh) < 0.2);
  assert.ok(analysis.applianceEstimates.every((item) => item.normalized));
  assert.ok(
    analysis.plans.every(
      (plan) => plan.monthlySavingKwh <= demoBill.totalKwh * 0.3,
    ),
  );
  assert.equal(
    analysis.plans.find((plan) => plan.id === "carbon")?.feasible,
    false,
  );
});

test("tariff and grid parameters change money and carbon without changing kWh", () => {
  const base = analyzeHousehold(
    demoProfile,
    demoBill,
    demoAppliances,
    demoParameters,
    generateDemoLoad(),
  );
  const changed = analyzeHousehold(
    demoProfile,
    demoBill,
    demoAppliances,
    { tariffSgdPerKwh: 0.5, gridEmissionKgPerKwh: 0.8 },
    generateDemoLoad(),
  );
  assert.equal(
    base.plans[1].monthlySavingKwh,
    changed.plans[1].monthlySavingKwh,
  );
  assert.ok(changed.plans[1].monthlySavingSgd > base.plans[1].monthlySavingSgd);
  assert.ok(changed.plans[1].carbonSavingKg > base.plans[1].carbonSavingKg);
});

test("validates the request and requires six structured specialist findings", () => {
  const request = {
    locale: "en",
    profile: demoProfile,
    bill: demoBill,
    appliances: demoAppliances,
    parameters: demoParameters,
    loadPoints: generateDemoLoad(),
  };
  assert.equal(agentRequestSchema.safeParse(request).success, true);

  const findingNames = [
    "Consumption Detective",
    "Appliance Auditor",
    "Cost Optimizer",
    "Comfort Guardian",
    "Carbon Analyst",
    "Plan and Action Coach",
  ] as const;
  const decision = {
    recommendedPlanId: "balanced",
    rationale: ["Best feasible fit."],
    rejectedRisks: [],
    nextActions: ["Confirm the plan."],
    specialistFindings: findingNames.map((agent) => ({
      agent,
      task: "Reviewed supplied evidence.",
      result: "Completed.",
      evidence: "measured",
    })),
  };
  assert.equal(agentDecisionSchema.safeParse(decision).success, true);
  assert.equal(
    agentDecisionSchema.safeParse({
      ...decision,
      specialistFindings: decision.specialistFindings.slice(0, 5),
    }).success,
    false,
  );
});
