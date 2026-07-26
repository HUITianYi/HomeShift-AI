import type {
  ApplianceEstimate,
  ComparisonResult,
  EnergyInsight,
  EnergyPlan,
  HouseholdProfile,
  LoadPoint,
  PlanAction,
} from "./types";

export const TARIFF_SGD_PER_KWH = 0.3478;
export const GRID_EMISSION_KG_PER_KWH = 0.402;

export function calculateCost(kwh: number) {
  return round(kwh * TARIFF_SGD_PER_KWH, 2);
}

export function calculateCarbon(kwh: number) {
  return round(kwh * GRID_EMISSION_KG_PER_KWH, 1);
}

export function generateDemoLoad(): LoadPoint[] {
  const raw = Array.from({ length: 48 }, (_, index) => {
    const hour = index / 2;
    let kwh = 0.16;

    if (hour >= 6 && hour < 9) kwh += 0.18 + (hour - 6) * 0.04;
    if (hour >= 9 && hour < 17) kwh += 0.12;
    if (hour >= 12 && hour < 14) kwh += 0.12;
    if (hour >= 18 && hour < 23) {
      kwh += 0.42 + Math.max(0, 0.28 - Math.abs(hour - 20.5) * 0.1);
    }
    if (hour >= 23 || hour < 1) kwh += 0.18;
    if (index % 7 === 0) kwh += 0.025;

    return kwh;
  });

  const targetDailyKwh = 14;
  const scale = targetDailyKwh / raw.reduce((sum, value) => sum + value, 0);

  return raw.map((value, index) => {
    const hour = Math.floor(index / 2);
    const minute = index % 2 === 0 ? "00" : "30";
    const period =
      hour < 6
        ? "overnight"
        : hour >= 18
          ? "evening"
          : "daytime";

    return {
      time: `${String(hour).padStart(2, "0")}:${minute}`,
      kwh: round(value * scale, 3),
      period,
    };
  });
}

export function parseIntervalCsv(content: string): LoadPoint[] {
  const rows = content
    .trim()
    .split(/\r?\n/)
    .map((line) => line.split(",").map((cell) => cell.trim()))
    .filter((row) => row.length >= 2);

  const parsed = rows
    .map((row, index) => {
      const numericCell = row
        .slice(1)
        .map(Number)
        .find((value) => Number.isFinite(value));
      if (numericCell === undefined) return null;

      const rawTime = row[0] || `${String(Math.floor(index / 2)).padStart(2, "0")}:00`;
      const match = rawTime.match(/(\d{1,2}):(\d{2})/);
      const hour = match ? Number(match[1]) : (index / 2) % 24;
      const period =
        hour < 6
          ? "overnight"
          : hour >= 18
            ? "evening"
            : "daytime";

      return {
        time: match ? `${String(hour).padStart(2, "0")}:${match[2]}` : rawTime,
        kwh: round(numericCell, 3),
        period,
      } satisfies LoadPoint;
    })
    .filter((point): point is LoadPoint => point !== null);

  if (parsed.length < 8) {
    throw new Error("The CSV needs at least 8 timestamp and consumption rows.");
  }

  return parsed.slice(0, 96);
}

export function detectLoadPatterns(points: LoadPoint[]) {
  const peak = points.reduce((highest, point) =>
    point.kwh > highest.kwh ? point : highest,
  );
  const overnight = points.filter((point) => point.period === "overnight");
  const evening = points.filter((point) => point.period === "evening");
  const total = points.reduce((sum, point) => sum + point.kwh, 0);

  return {
    peakTime: peak.time,
    peakKwh: peak.kwh,
    overnightAverageKwh: round(
      overnight.reduce((sum, point) => sum + point.kwh, 0) /
        Math.max(overnight.length, 1),
      2,
    ),
    eveningSharePercent: round(
      (evening.reduce((sum, point) => sum + point.kwh, 0) /
        Math.max(total, 0.001)) *
        100,
      0,
    ),
  };
}

export function estimateAppliances(
  profile: HouseholdProfile,
): ApplianceEstimate[] {
  const shares = [
    ["Air conditioning", 0.38, "Evening peaks + 8 h/night usage"],
    ["Water heating", 0.17, "Three residents, daily showers"],
    ["Refrigeration", 0.13, "Energy label + continuous duty cycle"],
    ["Laundry", 0.07, "Four weekly warm-water cycles"],
    ["Lighting & plugs", 0.09, "Overnight baseload pattern"],
  ] as const;

  return shares.map(([name, share, basis]) => ({
    name,
    monthlyKwh: round(profile.monthlyKwh * share, 1),
    sharePercent: share * 100,
    basis,
  }));
}

export function buildInsights(points: LoadPoint[]): EnergyInsight[] {
  const patterns = detectLoadPatterns(points);

  return [
    {
      id: "cooling-peak",
      title: "Cooling drives the evening peak",
      detail:
        "The steep rise after 19:00 is consistent with overlapping air-conditioning and shower demand.",
      evidence: `${patterns.eveningSharePercent}% of daily use occurs after 18:00; highest interval is ${patterns.peakTime}.`,
      confidence: 92,
      severity: "high",
    },
    {
      id: "baseload",
      title: "Overnight baseload stays elevated",
      detail:
        "Always-on plugs and an older refrigerator appear to keep demand above a comparable-home benchmark.",
      evidence: `${patterns.overnightAverageKwh.toFixed(2)} kWh per half-hour versus a 0.18 kWh target.`,
      confidence: 84,
      severity: "medium",
    },
    {
      id: "laundry",
      title: "Laundry compounds the 20:00 peak",
      detail:
        "Moving two weekly cycles and using cold water reduces peak overlap without changing total household routines.",
      evidence: "Four recurring step changes align with the declared washing schedule.",
      confidence: 76,
      severity: "low",
    },
  ];
}

function createPlan(
  id: EnergyPlan["id"],
  name: string,
  shortName: string,
  description: string,
  accent: string,
  actions: PlanAction[],
  upfrontCostSgd: number,
  comfortScore: number,
  difficulty: EnergyPlan["difficulty"],
  rationale: string,
): EnergyPlan {
  const monthlySavingKwh = round(
    actions.reduce((sum, action) => sum + action.monthlySavingKwh, 0),
    1,
  );
  const monthlySavingSgd = calculateCost(monthlySavingKwh);

  return {
    id,
    name,
    shortName,
    description,
    accent,
    monthlySavingKwh,
    monthlySavingSgd,
    annualSavingSgd: round(monthlySavingSgd * 12, 2),
    carbonSavingKg: calculateCarbon(monthlySavingKwh),
    upfrontCostSgd,
    paybackMonths:
      upfrontCostSgd > 0 ? round(upfrontCostSgd / monthlySavingSgd, 1) : null,
    comfortScore,
    difficulty,
    actions,
    rationale,
  };
}

export function generatePlans(profile: HouseholdProfile): EnergyPlan[] {
  const money = createPlan(
    "money",
    "Maximum Savings",
    "Save most",
    "Sharper changes for the lowest monthly bill.",
    "#ff7b57",
    [
      {
        title: "Raise overnight AC to 27°C",
        detail: "Use sleep mode from 23:30 and a fan for the first hour.",
        monthlySavingKwh: 39,
        effort: "Medium",
      },
      {
        title: "Cut the hidden baseload",
        detail: "Switch off the entertainment and office power strips overnight.",
        monthlySavingKwh: 16,
        effort: "Low",
      },
      {
        title: "Cold-wash and line-dry",
        detail: "Move three weekly cycles outside the evening peak.",
        monthlySavingKwh: 10,
        effort: "Medium",
      },
    ],
    35,
    78,
    "Moderate",
    "Highest bill reduction while staying inside the S$300 budget, with a noticeable change to sleep temperature.",
  );

  const balanced = createPlan(
    "balanced",
    "Balanced",
    "Recommended",
    "Meets the 10% goal while protecting sleep and work comfort.",
    "#c8f547",
    [
      {
        title: "Use AC smart sleep mode",
        detail: `Start at ${profile.comfortTemperature}°C, then step up by 1°C after 90 minutes.`,
        monthlySavingKwh: 24,
        effort: "Low",
      },
      {
        title: "Create a night shutdown routine",
        detail: "Switch two plug groups off at 00:00; keep the work setup available.",
        monthlySavingKwh: 11,
        effort: "Low",
      },
      {
        title: "Shift two laundry cycles",
        detail: "Cold-wash on Tuesday and Saturday before 18:00.",
        monthlySavingKwh: 7,
        effort: "Low",
      },
    ],
    0,
    92,
    "Easy",
    "The only plan that reaches the target with no purchase and keeps every hard comfort constraint intact.",
  );

  const carbon = createPlan(
    "carbon",
    "Low Carbon",
    "Cut carbon",
    "The largest energy reduction with a small equipment upgrade.",
    "#6f8cff",
    [
      {
        title: "Adopt the balanced routine",
        detail: "Keep the same comfort-preserving schedule as the recommended plan.",
        monthlySavingKwh: 42,
        effort: "Low",
      },
      {
        title: "Replace the oldest refrigerator",
        detail: "Move to a five-tick model at the next planned replacement.",
        monthlySavingKwh: 23,
        effort: "Medium",
      },
      {
        title: "Tune cooling maintenance",
        detail: "Clean filters monthly and seal the bedroom door gap.",
        monthlySavingKwh: 9,
        effort: "Medium",
      },
    ],
    180,
    86,
    "Moderate",
    "Greatest carbon benefit and still within budget; payback is longer than the seven-day trial.",
  );

  return [money, balanced, carbon];
}

export function compareActualToPlan(
  baselineKwh: number,
  actualMonthlyKwh: number,
  plan: EnergyPlan,
): ComparisonResult {
  const actualSavingKwh = round(baselineKwh - actualMonthlyKwh, 1);

  return {
    actualMonthlyKwh,
    actualSavingKwh,
    actualSavingPercent: round((actualSavingKwh / baselineKwh) * 100, 1),
    plannedSavingKwh: plan.monthlySavingKwh,
    varianceKwh: round(actualSavingKwh - plan.monthlySavingKwh, 1),
    actualSavingSgd: calculateCost(actualSavingKwh),
    actualCarbonSavingKg: calculateCarbon(actualSavingKwh),
  };
}

function round(value: number, digits: number) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
