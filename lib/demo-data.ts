import type {
  AnalysisParameters,
  ApplianceInputs,
  BillInput,
  HouseholdProfile,
} from "./types";

export const demoProfile: HouseholdProfile = {
  householdName: "Tampines 4-room household",
  homeType: "4-room HDB",
  residents: 3,
  workFromHome: true,
  monthlyTargetPercent: 10,
  comfortTemperature: 25,
  budgetSgd: 300,
};

export const demoBill: BillInput = {
  periodStart: "2026-05-01",
  periodEnd: "2026-05-31",
  totalKwh: 420,
  totalCostSgd: 146.08,
};

export const demoAppliances: ApplianceInputs = {
  airConditioning: {
    quantity: 2,
    ratedPowerKw: 0.9,
    hoursPerDay: 6,
    currentTemperature: 23,
  },
  refrigerator: {
    annualKwh: 480,
    replacementCostSgd: 180,
  },
  waterHeater: {
    ratedPowerKw: 3,
    minutesPerDay: 12,
  },
  washingMachine: {
    kwhPerCycle: 0.8,
    cyclesPerWeek: 4,
  },
  otherMonthlyKwh: 35,
};

export const demoParameters: AnalysisParameters = {
  tariffSgdPerKwh: 0.3478,
  gridEmissionKgPerKwh: 0.402,
};
