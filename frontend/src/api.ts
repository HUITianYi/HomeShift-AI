import { z } from "zod";

const bilingualSchema = z.object({ zh: z.string(), en: z.string() });
const moneySchema = z.object({
  value: z.number().nullable(),
  display: z.string(),
  currency: z.string(),
});
const quantitySchema = z.object({
  value: z.number().nullable(),
  display: z.string(),
  unit: z.string(),
});
const actionSchema = z.object({
  id: z.string(),
  title: bilingualSchema,
  description: bilingualSchema,
  category: z.string(),
  selected: z.boolean(),
  savings: z.object({
    kwh_per_month: z.number(),
    cost_per_month: moneySchema,
    co2_kg_per_month: z.number(),
  }),
  comfort_impact: z.object({ level: z.string(), label: bilingualSchema }),
  effort: z.object({ level: z.string(), label: bilingualSchema }),
  notes: z.string().optional(),
}).passthrough();

export const workspaceSchema = z.object({
  meta: z.object({
    schema_version: z.string(),
    data_kind: z.string(),
    data_badge: bilingualSchema,
    region: z.object({
      code: z.string().nullable().optional(),
      name: z.string().nullable().optional(),
      timezone: z.string().nullable().optional(),
      climate: z.string().nullable().optional(),
    }),
    currency: z.object({ code: z.string(), symbol: z.string() }),
    tariff: z.object({
      plan: z.string().nullable().optional(),
      rate_per_kwh: z.number(),
      gst_rate: z.number().nullable().optional(),
      note: z.string(),
    }),
    carbon: z.object({
      grid_emission_factor_kg_per_kwh: z.number(),
      note: z.string(),
    }),
    provenance: z.object({
      dataset: z.any().optional(),
      window: z.any().optional(),
      weather: z.any().optional(),
      known_limitations: z.array(z.string()).optional(),
    }).optional(),
  }).passthrough(),
  household: z.object({
    name: bilingualSchema,
    location: z.string(),
    summary: bilingualSchema,
    tags: z.array(z.string()),
    profile_origin: bilingualSchema,
    assumptions: z.array(z.string()),
    comfort_rules: z.array(z.any()),
    goal: z.any(),
  }).passthrough(),
  baseline: z.object({
    available: z.boolean(),
    period: z.any().optional(),
    headline: z.object({
      kwh_this_month: quantitySchema,
      avg_daily_kwh: quantitySchema,
      est_bill: moneySchema,
      carbon_kg: quantitySchema,
      sources_count: z.number(),
    }).optional(),
    extremes: z.any().optional(),
    signature_24h: z.any().optional(),
    daily_series: z.array(z.any()).optional(),
    evidence: z.array(z.any()).optional(),
  }).passthrough(),
  diagnosis: z.object({
    available: z.boolean(),
    period: z.any().optional(),
    days: z.number().optional(),
    avg_daily_total_kwh: z.number().optional(),
    categories: z.array(z.any()).optional(),
    findings: z.array(z.any()).optional(),
    method: z.any().optional(),
    accuracy: z.any().optional(),
    daily_series: z.array(z.any()).optional(),
  }).passthrough(),
  plans: z.object({
    available: z.boolean(),
    has_committed_plan: z.boolean().optional(),
    version: z.number().nullable().optional(),
    rationale: z.string().optional(),
    expected_per_month: z.any().optional(),
    potential_per_month: z.any().optional(),
    candidates: z.array(actionSchema).optional(),
    vetoed_by_comfort: z.array(actionSchema).optional(),
    comfort_summary: z.any().optional(),
    seven_day_schedule: z.array(z.any()).optional(),
  }).passthrough(),
  track: z.object({
    available: z.boolean(),
    status: z.string().optional(),
    message: z.any().optional(),
    plan_version: z.number().optional(),
    comparison_bars: z.array(z.any()).optional(),
    saving: z.any().optional(),
    overall_achievement_pct: z.number().nullable().optional(),
    per_action: z.array(z.any()).optional(),
    category_delta: z.any().optional(),
    weather_normalization: z.any().optional(),
  }).passthrough(),
  agents: z.object({
    count: z.number(),
    orchestration: bilingualSchema,
    agents: z.array(z.any()),
    trace: z.array(z.any()),
  }),
  memory: z.object({
    count: z.number(),
    items: z.array(z.any()),
  }).optional(),
  runtime: z.object({
    model: z.any(),
    tracking: z.any(),
    workflow: z.object({
      data_ready: z.boolean(),
      diagnosis_completed: z.boolean(),
      diagnosis_completed_at: z.string().nullable().optional(),
      plan_proposed: z.boolean(),
      plan_committed: z.boolean(),
      tracking_ready: z.boolean(),
      review_completed: z.boolean(),
      review_completed_at: z.string().nullable().optional(),
      last_operation: z.string().nullable().optional(),
      last_run: z.any().optional(),
    }).optional(),
  }).optional(),
  disclaimers: z.any(),
}).passthrough();

export type Workspace = z.infer<typeof workspaceSchema>;

export const statusSchema = z.object({
  ready: z.boolean(),
  data: z.object({
    available: z.boolean(),
    kind: z.string().nullable(),
    dataset: z.string().nullable(),
    start: z.string().nullable(),
    end: z.string().nullable(),
    tracking_kind: z.string().nullable().optional(),
  }),
  region: z.any(),
  plan: z.object({ active: z.boolean(), version: z.number().nullable() }),
  memory_count: z.number(),
  model: z.object({
    provider: z.string(),
    kind: z.string(),
    label: z.string(),
    model: z.string().nullable(),
    configured: z.boolean(),
    explicit: z.boolean().optional(),
    reason: z.string().nullable().optional(),
  }),
});
export type Status = z.infer<typeof statusSchema>;

export const providersSchema = z.object({
  providers: z.array(z.object({
    name: z.string(),
    label: z.string(),
    kind: z.string(),
    default_model: z.string().nullable(),
    configured: z.boolean(),
    notes: z.string(),
    selected: z.boolean(),
  })),
  current: z.any(),
});
export type Providers = z.infer<typeof providersSchema>;

export const datasetsSchema = z.object({
  datasets: z.array(z.object({
    id: z.string(),
    title: z.string(),
    short: z.string(),
    manual: z.boolean(),
    license: z.string().nullable(),
    period: z.string().nullable().optional(),
    raw_resolution_minutes: z.number().nullable(),
    recommended_for: z.string().nullable(),
    region: z.any().optional(),
    manual_hint: z.string().nullable().optional(),
  })),
});
export type Datasets = z.infer<typeof datasetsSchema>;

const runSchema = z.object({
  operation: z.string(),
  mode: z.enum(["live", "mock"]),
  provider: z.string(),
  model: z.string(),
  final_text: z.string(),
  trace: z.array(z.any()),
  proposal: z.any().optional(),
});
export type AgentRun = z.infer<typeof runSchema>;

const operationSchema = z.object({
  run: runSchema,
  workspace: workspaceSchema,
});

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;

  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("json") ? await response.json() : await response.text();
  if (!response.ok) {
    const error = (payload as any)?.error;
    throw new ApiError(
      error?.code || "request_failed",
      error?.message || `HTTP ${response.status}`,
      response.status,
      error?.details,
    );
  }
  return payload;
}

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  status: async () => statusSchema.parse(await request("/status")),
  providers: async () => providersSchema.parse(await request("/providers")),
  datasets: async () => datasetsSchema.parse(await request("/datasets")),
  workspace: async () => workspaceSchema.parse(await request("/workspace")),
  profile: async () => z.object({ profile: z.any() }).parse(await request("/profile")),
  selectModel: async (provider: string, model: string | null, mode: "live" | "mock") =>
    request("/settings/model", jsonInit("PUT", { provider, model, mode })),
  importDataset: async (form: FormData) =>
    z.object({ workspace: workspaceSchema }).passthrough().parse(
      await request("/datasets/import", { method: "POST", body: form }),
    ),
  saveProfile: async (profile: Record<string, unknown>) =>
    z.object({ profile: z.any(), workspace: workspaceSchema }).parse(
      await request("/profile", jsonInit("PUT", { profile })),
    ),
  diagnose: async (locale: "zh" | "en") =>
    operationSchema.parse(await request("/diagnose", jsonInit("POST", { locale }))),
  propose: async (locale: "zh" | "en") =>
    operationSchema.parse(await request("/plan/propose", jsonInit("POST", { locale }))),
  commit: async (actionIds: string[], rationale: string) =>
    z.object({ plan: z.any(), workspace: workspaceSchema }).parse(
      await request("/plan/commit", jsonInit("POST", {
        action_ids: actionIds,
        rationale,
        confirmed_by_user: true,
      })),
    ),
  simulateWeek: async (adherence: number) =>
    z.object({ tracking: z.any(), workspace: workspaceSchema }).parse(
      await request("/tracking/simulate-week", jsonInit("POST", { adherence })),
    ),
  importTracking: async (form: FormData) =>
    z.object({ tracking: z.any(), workspace: workspaceSchema }).parse(
      await request("/tracking/import", { method: "POST", body: form }),
    ),
  review: async (locale: "zh" | "en") =>
    operationSchema.parse(await request("/review", jsonInit("POST", { locale }))),
  chat: async (
    message: string,
    locale: "zh" | "en",
    history: { role: "user" | "assistant"; text: string }[],
  ) => z.object({ run: runSchema }).parse(
    await request("/chat", jsonInit("POST", { message, locale, history })),
  ),
  reportUrl: `${API_BASE}/report`,
};

export function localText(value: { zh: string; en: string } | string | undefined, locale: "zh" | "en") {
  if (!value) return "—";
  return typeof value === "string" ? value : value[locale] || value.zh;
}
