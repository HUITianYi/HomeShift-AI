import type {
  AnalysisParameters,
  ApplianceEstimate,
  ApplianceInputs,
  BillInput,
  EnergyInsight,
  EnergyPlan,
  HouseholdAnalysis,
  HouseholdProfile,
  LoadDataQuality,
  LoadPatterns,
  LoadPoint,
  ParsedLoadData,
  PlanAction,
} from "./types";

export const DEFAULT_TARIFF_SGD_PER_KWH = 0.3478;
export const DEFAULT_GRID_EMISSION_KG_PER_KWH = 0.402;

const SINGAPORE_OFFSET_MS = 8 * 60 * 60 * 1000;
const HALF_HOUR_MS = 30 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

export function calculateCost(
  kwh: number,
  tariffSgdPerKwh = DEFAULT_TARIFF_SGD_PER_KWH,
) {
  return round(kwh * tariffSgdPerKwh, 2);
}

export function calculateCarbon(
  kwh: number,
  gridEmissionKgPerKwh = DEFAULT_GRID_EMISSION_KG_PER_KWH,
) {
  return round(kwh * gridEmissionKgPerKwh, 1);
}

export function generateDemoLoad(days = 14): LoadPoint[] {
  const daySignature = Array.from({ length: 48 }, (_, index) => {
    const hour = index / 2;
    let kwh = 0.16;

    if (hour >= 6 && hour < 9) kwh += 0.18 + (hour - 6) * 0.04;
    if (hour >= 9 && hour < 17) kwh += 0.12;
    if (hour >= 12 && hour < 14) kwh += 0.12;
    if (hour >= 18 && hour < 23) {
      kwh += 0.42 + Math.max(0, 0.28 - Math.abs(hour - 20.5) * 0.1);
    }
    if (hour >= 23 || hour < 1) kwh += 0.18;
    return kwh;
  });

  const targetDailyKwh = 14;
  const scale =
    targetDailyKwh /
    daySignature.reduce((sum, intervalKwh) => sum + intervalKwh, 0);
  const startMs = singaporeLocalToEpoch(2026, 5, 1, 0, 0);

  return Array.from({ length: days * 48 }, (_, index) => {
    const slot = index % 48;
    const day = Math.floor(index / 48);
    const variation = 1 + Math.sin((day / Math.max(days, 1)) * Math.PI * 2) * 0.04;
    return pointFromEpoch(
      startMs + index * HALF_HOUR_MS,
      round(daySignature[slot] * scale * variation, 3),
    );
  });
}

export function demoCsvTemplate(): string {
  const rows = ["timestamp,kwh"];
  for (const point of generateDemoLoad(7)) {
    rows.push(`${point.timestamp.slice(0, 16).replace("T", " ")},${point.kwh}`);
  }
  return rows.join("\n");
}

export function parseIntervalCsv(content: string): ParsedLoadData {
  const trimmed = content.replace(/^\uFEFF/, "").trim();
  if (!trimmed) throw new Error("The CSV file is empty.");

  const lines = trimmed.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) {
    throw new Error("The CSV needs a header and half-hour data rows.");
  }

  const delimiter = detectDelimiter(lines[0]);
  const headers = splitRow(lines[0], delimiter).map(normalizeHeader);
  const timestampIndex = findHeaderIndex(headers, [
    "timestamp",
    "datetime",
    "dateandtime",
    "time",
  ]);
  const kwhIndex = findHeaderIndex(headers, [
    "kwh",
    "consumption",
    "usage",
    "energy",
  ]);

  if (timestampIndex < 0 || kwhIndex < 0) {
    throw new Error(
      "CSV headers must include timestamp/time and kwh/consumption/usage/energy.",
    );
  }

  const byTimestamp = new Map<number, LoadPoint>();
  let duplicateIntervals = 0;

  lines.slice(1).forEach((line, rowOffset) => {
    const rowNumber = rowOffset + 2;
    const cells = splitRow(line, delimiter);
    const timestampText = cells[timestampIndex]?.trim();
    const kwhText = cells[kwhIndex]?.trim();
    const epochMs = timestampText
      ? parseSingaporeTimestamp(timestampText)
      : Number.NaN;
    const kwh = Number(kwhText);

    if (!Number.isFinite(epochMs)) {
      throw new Error(`Row ${rowNumber} has an invalid timestamp.`);
    }
    if (!Number.isFinite(kwh) || kwh < 0) {
      throw new Error(`Row ${rowNumber} must contain a non-negative kWh value.`);
    }
    if (epochMs % HALF_HOUR_MS !== 0) {
      throw new Error(`Row ${rowNumber} is not aligned to a half-hour interval.`);
    }

    if (byTimestamp.has(epochMs)) duplicateIntervals += 1;
    byTimestamp.set(epochMs, pointFromEpoch(epochMs, round(kwh, 4)));
  });

  const points = [...byTimestamp.entries()]
    .sort(([left], [right]) => left - right)
    .map(([, point]) => point);

  if (points.length === 0) throw new Error("The CSV contains no usable rows.");

  return {
    points,
    quality: assessLoadData(points, duplicateIntervals, true),
  };
}

export function assessLoadData(
  points: LoadPoint[],
  duplicateIntervals = 0,
  enforceDemoRange = false,
): LoadDataQuality {
  if (points.length === 0) {
    return {
      startDate: "",
      endDate: "",
      dayCount: 0,
      recordCount: 0,
      expectedIntervals: 0,
      missingIntervals: 0,
      duplicateIntervals,
      coveragePercent: 0,
      warnings: ["No interval data loaded."],
    };
  }

  const sorted = [...points].sort(
    (left, right) =>
      parseSingaporeTimestamp(left.timestamp) -
      parseSingaporeTimestamp(right.timestamp),
  );
  const startDate = sorted[0].timestamp.slice(0, 10);
  const endDate = sorted.at(-1)!.timestamp.slice(0, 10);
  const dayCount =
    Math.floor(
      (calendarDayNumber(endDate) - calendarDayNumber(startDate)) / DAY_MS,
    ) + 1;
  const expectedIntervals = dayCount * 48;
  const missingIntervals = Math.max(0, expectedIntervals - sorted.length);
  const coveragePercent = round(
    (Math.min(sorted.length, expectedIntervals) /
      Math.max(expectedIntervals, 1)) *
      100,
    1,
  );
  const warnings: string[] = [];

  if (duplicateIntervals > 0) {
    warnings.push(
      `${duplicateIntervals} duplicate interval${duplicateIntervals === 1 ? "" : "s"} replaced by the latest row.`,
    );
  }
  if (missingIntervals > 0) {
    warnings.push(`${missingIntervals} half-hour intervals are missing.`);
  }
  if (coveragePercent >= 80 && coveragePercent < 95) {
    warnings.push(
      "Coverage is below 95%; findings will carry lower confidence.",
    );
  }

  if (enforceDemoRange && (dayCount < 7 || dayCount > 30)) {
    throw new Error("Interval data must cover between 7 and 30 calendar days.");
  }
  if (enforceDemoRange && coveragePercent < 80) {
    throw new Error(
      `Interval coverage is ${coveragePercent}%; at least 80% is required.`,
    );
  }

  return {
    startDate,
    endDate,
    dayCount,
    recordCount: sorted.length,
    expectedIntervals,
    missingIntervals,
    duplicateIntervals,
    coveragePercent,
    warnings,
  };
}

export function aggregateDailyProfile(points: LoadPoint[]): LoadPoint[] {
  const slots = Array.from({ length: 48 }, () => [] as number[]);
  for (const point of points) {
    const [hour, minute] = point.time.split(":").map(Number);
    const slot = hour * 2 + (minute >= 30 ? 1 : 0);
    if (slot >= 0 && slot < 48) slots[slot].push(point.kwh);
  }

  return slots.map((values, slot) => {
    const hour = Math.floor(slot / 2);
    const minute = slot % 2 === 0 ? "00" : "30";
    const time = `${String(hour).padStart(2, "0")}:${minute}`;
    return {
      timestamp: `2026-01-01T${time}:00+08:00`,
      time,
      kwh:
        values.length > 0
          ? round(
              values.reduce((sum, value) => sum + value, 0) / values.length,
              3,
            )
          : 0,
      period: periodForHour(hour),
    };
  });
}

export function detectLoadPatterns(
  points: LoadPoint[],
  quality = assessLoadData(points),
): LoadPatterns {
  const profile = aggregateDailyProfile(points);
  const peak = profile.reduce((highest, point) =>
    point.kwh > highest.kwh ? point : highest,
  );
  const overnight = points
    .filter((point) => point.period === "overnight")
    .map((point) => point.kwh);
  const evening = points.filter((point) => point.period === "evening");
  const total = points.reduce((sum, point) => sum + point.kwh, 0);
  const overnightAverage =
    overnight.reduce((sum, value) => sum + value, 0) /
    Math.max(overnight.length, 1);
  const overnightTarget = percentile(overnight, 0.2);

  return {
    peakTime: peak.time,
    peakKwh: peak.kwh,
    overnightAverageKwh: round(overnightAverage, 3),
    overnightTargetKwh: round(overnightTarget, 3),
    overnightSavingPotentialKwh: round(
      Math.max(overnightAverage - overnightTarget, 0) * 12 * 30,
      1,
    ),
    eveningSharePercent: round(
      (evening.reduce((sum, point) => sum + point.kwh, 0) /
        Math.max(total, 0.001)) *
        100,
      0,
    ),
    dailyAverageKwh: round(total / Math.max(quality.dayCount, 1), 1),
    recordCount: quality.recordCount,
    dayCount: quality.dayCount,
  };
}

export function estimateAppliances(
  bill: BillInput,
  inputs: ApplianceInputs,
): ApplianceEstimate[] {
  const raw = [
    {
      key: "air-conditioning" as const,
      name: "Air conditioning",
      monthlyKwh:
        inputs.airConditioning.quantity *
        inputs.airConditioning.ratedPowerKw *
        inputs.airConditioning.hoursPerDay *
        30 *
        0.65,
      basis: "Quantity × rated power × daily hours × 30 × 0.65 duty factor",
    },
    {
      key: "refrigeration" as const,
      name: "Refrigeration",
      monthlyKwh: inputs.refrigerator.annualKwh / 12,
      basis: "Declared annual energy ÷ 12",
    },
    {
      key: "water-heating" as const,
      name: "Water heating",
      monthlyKwh:
        inputs.waterHeater.ratedPowerKw *
        (inputs.waterHeater.minutesPerDay / 60) *
        30,
      basis: "Rated power × daily minutes × 30",
    },
    {
      key: "laundry" as const,
      name: "Laundry",
      monthlyKwh:
        inputs.washingMachine.kwhPerCycle *
        inputs.washingMachine.cyclesPerWeek *
        (52 / 12),
      basis: "Energy per cycle × weekly cycles × 52 ÷ 12",
    },
    {
      key: "other" as const,
      name: "Other / unattributed",
      monthlyKwh: inputs.otherMonthlyKwh,
      basis: "Declared other use plus any unallocated bill energy",
    },
  ];

  const rawTotal = raw.reduce(
    (sum, appliance) => sum + Math.max(appliance.monthlyKwh, 0),
    0,
  );
  const normalized = rawTotal > bill.totalKwh && rawTotal > 0;
  const scale = normalized ? bill.totalKwh / rawTotal : 1;
  const residual = normalized ? 0 : Math.max(bill.totalKwh - rawTotal, 0);

  return raw.map((appliance) => {
    const monthlyKwh =
      appliance.key === "other"
        ? appliance.monthlyKwh * scale + residual
        : appliance.monthlyKwh * scale;
    return {
      ...appliance,
      monthlyKwh: round(monthlyKwh, 1),
      sharePercent: round(
        (monthlyKwh / Math.max(bill.totalKwh, 0.001)) * 100,
        1,
      ),
      normalized,
      basis: normalized
        ? `${appliance.basis}; normalized to the bill total`
        : appliance.basis,
    };
  });
}

export function buildInsights(
  patterns: LoadPatterns,
  appliances: ApplianceEstimate[],
  quality: LoadDataQuality,
): EnergyInsight[] {
  const topAppliance = [...appliances].sort(
    (left, right) => right.monthlyKwh - left.monthlyKwh,
  )[0];
  const measuredConfidence = Math.round(quality.coveragePercent);
  const estimatedConfidence = Math.round(
    Math.min(85, quality.coveragePercent * 0.82),
  );

  return [
    {
      id: "peak",
      title: "Daily demand concentrates around the measured peak",
      detail:
        "The multi-day average profile identifies the most repeatable high-load interval.",
      evidence: `${patterns.eveningSharePercent}% of measured energy occurs after 18:00; the average peak is ${patterns.peakTime}.`,
      evidenceKind: "measured",
      confidence: measuredConfidence,
      severity: patterns.eveningSharePercent >= 35 ? "high" : "medium",
    },
    {
      id: "baseload",
      title: "Overnight baseload has a measurable reduction range",
      detail:
        "The lower overnight observations provide a household-specific target without using a generic benchmark.",
      evidence: `${patterns.overnightAverageKwh.toFixed(3)} kWh average versus ${patterns.overnightTargetKwh.toFixed(3)} kWh at the overnight 20th percentile.`,
      evidenceKind: "measured",
      confidence: measuredConfidence,
      severity:
        patterns.overnightSavingPotentialKwh >= 10 ? "medium" : "low",
    },
    {
      id: "top-appliance",
      title: `${topAppliance.name} is the largest estimated end use`,
      detail:
        "The estimate uses the household's declared equipment and schedule, then reconciles totals to the bill.",
      evidence: `${topAppliance.monthlyKwh.toFixed(1)} kWh/month, or ${topAppliance.sharePercent.toFixed(1)}% of the bill baseline.`,
      evidenceKind: "estimated",
      confidence: estimatedConfidence,
      severity: topAppliance.sharePercent >= 30 ? "high" : "medium",
    },
  ];
}

export function generatePlans(
  profile: HouseholdProfile,
  bill: BillInput,
  inputs: ApplianceInputs,
  applianceEstimates: ApplianceEstimate[],
  patterns: LoadPatterns,
  parameters: AnalysisParameters,
): EnergyPlan[] {
  const estimate = (key: ApplianceEstimate["key"]) =>
    applianceEstimates.find((item) => item.key === key)?.monthlyKwh ?? 0;
  const acKwh = estimate("air-conditioning");
  const refrigeratorKwh = estimate("refrigeration");
  const laundryKwh = estimate("laundry");
  const temperatureHeadroom = Math.max(
    profile.comfortTemperature - inputs.airConditioning.currentTemperature,
    0,
  );
  const balancedDelta = Math.min(temperatureHeadroom, 1);
  const maximumDelta = Math.min(temperatureHeadroom, 2);
  const afterSleepFraction =
    inputs.airConditioning.hoursPerDay > 0
      ? Math.max(inputs.airConditioning.hoursPerDay - 1.5, 0) /
        inputs.airConditioning.hoursPerDay
      : 0;
  const balancedAcSaving =
    acKwh * balancedDelta * 0.06 * afterSleepFraction;
  const maximumAcSaving = acKwh * maximumDelta * 0.06;
  const balancedBaseload = patterns.overnightSavingPotentialKwh * 0.5;
  const maximumBaseload = patterns.overnightSavingPotentialKwh * 0.8;
  const balancedLaundry = laundryKwh * 0.15;
  const maximumLaundry = laundryKwh * 0.25;
  const balancedTotal =
    balancedAcSaving + balancedBaseload + balancedLaundry;

  const moneyActions: PlanAction[] = [
    {
      code: "ac-maximum",
      title: "Use the full comfortable cooling range",
      detail: `Raise the overnight setpoint by up to ${maximumDelta.toFixed(0)}°C, never above ${profile.comfortTemperature}°C.`,
      monthlySavingKwh: maximumAcSaving,
      effort: "Medium",
    },
    {
      code: "baseload-maximum",
      title: "Remove most avoidable overnight baseload",
      detail:
        "Use labelled shutdown groups while preserving the work-from-home setup.",
      monthlySavingKwh: maximumBaseload,
      effort: "Medium",
    },
    {
      code: "laundry-maximum",
      title: "Use cold-water cycles consistently",
      detail:
        "Cold-wash routine changes reduce energy; time shifting alone is not counted as a saving.",
      monthlySavingKwh: maximumLaundry,
      effort: "Medium",
    },
  ];

  const balancedActions: PlanAction[] = [
    {
      code: "ac-balanced",
      title: "Use AC smart sleep mode",
      detail: `Start at ${inputs.airConditioning.currentTemperature}°C and step up ${balancedDelta.toFixed(0)}°C after 90 minutes.`,
      monthlySavingKwh: balancedAcSaving,
      effort: "Low",
    },
    {
      code: "baseload-balanced",
      title: "Create a selective night shutdown routine",
      detail:
        "Target half of the measured baseload opportunity and keep work equipment available.",
      monthlySavingKwh: balancedBaseload,
      effort: "Low",
    },
    {
      code: "laundry-balanced",
      title: "Switch selected loads to cold water",
      detail:
        "Apply cold-water settings to repeatable weekly cycles; no saving is assigned to time shifting alone.",
      monthlySavingKwh: balancedLaundry,
      effort: "Low",
    },
  ];

  const carbonActions: PlanAction[] = [
    {
      code: "balanced-routine",
      title: "Adopt the balanced routine",
      detail:
        "Keep the same comfort-preserving cooling, baseload and laundry routine.",
      monthlySavingKwh: balancedTotal,
      effort: "Low",
    },
    {
      code: "refrigerator-upgrade",
      title: "Plan an efficient refrigerator replacement",
      detail:
        "A conservative 25% reduction is counted against the declared refrigerator energy.",
      monthlySavingKwh: refrigeratorKwh * 0.25,
      effort: "Medium",
    },
    {
      code: "cooling-maintenance",
      title: "Tune cooling maintenance",
      detail:
        "Clean filters and seal the cooled room; a conservative 3% cooling reduction is counted.",
      monthlySavingKwh: acKwh * 0.03,
      effort: "Medium",
    },
  ];

  return [
    createPlan({
      id: "money",
      name: "Maximum Savings",
      shortName: "Save most",
      description:
        "Uses the full declared comfort range and the strongest no-purchase routine.",
      accent: "#ff7b57",
      actions: moneyActions,
      upfrontCostSgd: 0,
      comfortScore: maximumDelta > 1 ? 82 : 88,
      difficulty: "Moderate",
      rationale:
        "Largest no-purchase reduction that stays within the household's declared comfort limit.",
      profile,
      bill,
      parameters,
    }),
    createPlan({
      id: "balanced",
      name: "Balanced",
      shortName: "Comfort first",
      description:
        "Targets measured opportunities after protecting sleep and work routines.",
      accent: "#c8f547",
      actions: balancedActions,
      upfrontCostSgd: 0,
      comfortScore: 94,
      difficulty: "Easy",
      rationale:
        "Low-effort measures tied directly to the household's load shape and declared schedule.",
      profile,
      bill,
      parameters,
    }),
    createPlan({
      id: "carbon",
      name: "Low Carbon",
      shortName: "Cut carbon",
      description:
        "Adds a planned appliance upgrade and maintenance to the balanced routine.",
      accent: "#6f8cff",
      actions: carbonActions,
      upfrontCostSgd: inputs.refrigerator.replacementCostSgd,
      comfortScore: 92,
      difficulty: "Moderate",
      rationale:
        "Greatest modeled energy and carbon reduction, subject to the declared replacement budget.",
      profile,
      bill,
      parameters,
    }),
  ];
}

export function analyzeHousehold(
  profile: HouseholdProfile,
  bill: BillInput,
  appliances: ApplianceInputs,
  parameters: AnalysisParameters,
  loadPoints: LoadPoint[],
): HouseholdAnalysis {
  const quality = assessLoadData(loadPoints, 0, true);
  const patterns = detectLoadPatterns(loadPoints, quality);
  const applianceEstimates = estimateAppliances(bill, appliances);
  const insights = buildInsights(patterns, applianceEstimates, quality);
  const plans = generatePlans(
    profile,
    bill,
    appliances,
    applianceEstimates,
    patterns,
    parameters,
  );
  return { quality, patterns, applianceEstimates, insights, plans };
}

function createPlan({
  id,
  name,
  shortName,
  description,
  accent,
  actions,
  upfrontCostSgd,
  comfortScore,
  difficulty,
  rationale,
  profile,
  bill,
  parameters,
}: {
  id: EnergyPlan["id"];
  name: string;
  shortName: string;
  description: string;
  accent: string;
  actions: PlanAction[];
  upfrontCostSgd: number;
  comfortScore: number;
  difficulty: EnergyPlan["difficulty"];
  rationale: string;
  profile: HouseholdProfile;
  bill: BillInput;
  parameters: AnalysisParameters;
}): EnergyPlan {
  const cap = bill.totalKwh * 0.3;
  const positiveActions = actions.map((action) => ({
    ...action,
    monthlySavingKwh: Math.max(action.monthlySavingKwh, 0),
  }));
  const rawSaving = positiveActions.reduce(
    (sum, action) => sum + action.monthlySavingKwh,
    0,
  );
  const scale = rawSaving > cap && rawSaving > 0 ? cap / rawSaving : 1;
  const normalizedActions = positiveActions.map((action) => ({
    ...action,
    monthlySavingKwh: round(action.monthlySavingKwh * scale, 1),
  }));
  const monthlySavingKwh = round(
    normalizedActions.reduce(
      (sum, action) => sum + action.monthlySavingKwh,
      0,
    ),
    1,
  );
  const monthlySavingSgd = calculateCost(
    monthlySavingKwh,
    parameters.tariffSgdPerKwh,
  );
  const feasible = upfrontCostSgd <= profile.budgetSgd;
  const constraintNotes = [
    feasible
      ? `Upfront cost is within the S$${profile.budgetSgd.toFixed(0)} budget.`
      : `Upfront cost exceeds the S$${profile.budgetSgd.toFixed(0)} budget.`,
    `Cooling actions never exceed ${profile.comfortTemperature}°C.`,
    profile.workFromHome
      ? "Work-from-home equipment remains available."
      : "No work-from-home availability constraint declared.",
  ];

  return {
    id,
    name,
    shortName,
    description,
    accent,
    monthlySavingKwh,
    monthlySavingSgd,
    annualSavingSgd: round(monthlySavingSgd * 12, 2),
    carbonSavingKg: calculateCarbon(
      monthlySavingKwh,
      parameters.gridEmissionKgPerKwh,
    ),
    upfrontCostSgd: round(upfrontCostSgd, 2),
    paybackMonths:
      upfrontCostSgd > 0 && monthlySavingSgd > 0
        ? round(upfrontCostSgd / monthlySavingSgd, 1)
        : null,
    comfortScore,
    difficulty,
    actions: normalizedActions,
    rationale,
    feasible,
    meetsTarget:
      monthlySavingKwh >=
      bill.totalKwh * (profile.monthlyTargetPercent / 100),
    constraintNotes,
  };
}

function detectDelimiter(header: string) {
  const candidates = [",", ";", "\t"] as const;
  return candidates.reduce((best, candidate) =>
    header.split(candidate).length > header.split(best).length
      ? candidate
      : best,
  );
}

function splitRow(row: string, delimiter: string) {
  return row.split(delimiter).map((cell) => cell.replace(/^"|"$/g, ""));
}

function normalizeHeader(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function findHeaderIndex(headers: string[], aliases: string[]) {
  const normalizedAliases = aliases.map(normalizeHeader);
  return headers.findIndex((header) => normalizedAliases.includes(header));
}

function parseSingaporeTimestamp(value: string): number {
  const trimmed = value.trim();
  const local = trimmed.match(
    /^(\d{4})[-/](\d{1,2})[-/](\d{1,2})[T\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?$/,
  );
  if (local) {
    const [, year, month, day, hour, minute, second = "0"] = local;
    const epoch = singaporeLocalToEpoch(
      Number(year),
      Number(month),
      Number(day),
      Number(hour),
      Number(minute),
      Number(second),
    );
    const canonical = canonicalSingaporeParts(epoch);
    if (
      canonical.year !== Number(year) ||
      canonical.month !== Number(month) ||
      canonical.day !== Number(day) ||
      canonical.hour !== Number(hour) ||
      canonical.minute !== Number(minute)
    ) {
      return Number.NaN;
    }
    return epoch;
  }

  if (/Z$|[+-]\d{2}:?\d{2}$/.test(trimmed)) {
    return Date.parse(trimmed);
  }
  return Number.NaN;
}

function singaporeLocalToEpoch(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
  second = 0,
) {
  return (
    Date.UTC(year, month - 1, day, hour, minute, second) -
    SINGAPORE_OFFSET_MS
  );
}

function canonicalSingaporeParts(epochMs: number) {
  const shifted = new Date(epochMs + SINGAPORE_OFFSET_MS);
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
    hour: shifted.getUTCHours(),
    minute: shifted.getUTCMinutes(),
    second: shifted.getUTCSeconds(),
  };
}

function pointFromEpoch(epochMs: number, kwh: number): LoadPoint {
  const parts = canonicalSingaporeParts(epochMs);
  const time = `${String(parts.hour).padStart(2, "0")}:${String(parts.minute).padStart(2, "0")}`;
  return {
    timestamp: `${parts.year}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}T${time}:${String(parts.second).padStart(2, "0")}+08:00`,
    time,
    kwh,
    period: periodForHour(parts.hour),
  };
}

function periodForHour(hour: number): LoadPoint["period"] {
  if (hour < 6) return "overnight";
  if (hour >= 18) return "evening";
  return "daytime";
}

function calendarDayNumber(date: string) {
  const [year, month, day] = date.split("-").map(Number);
  return Date.UTC(year, month - 1, day);
}

function percentile(values: number[], fraction: number) {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.min(
    sorted.length - 1,
    Math.max(0, Math.floor((sorted.length - 1) * fraction)),
  );
  return sorted[index];
}

function round(value: number, digits: number) {
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}
