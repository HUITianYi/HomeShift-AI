"use client";

import {
  Activity,
  AlertCircle,
  ArrowRight,
  BarChart3,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Database,
  Download,
  FileImage,
  FileSpreadsheet,
  Gauge,
  Home,
  Info,
  Languages,
  Leaf,
  LoaderCircle,
  LockKeyhole,
  MoonStar,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Thermometer,
  Upload,
  WandSparkles,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  aggregateDailyProfile,
  analyzeHousehold,
  assessLoadData,
  calculateCarbon,
  demoCsvTemplate,
  generateDemoLoad,
  parseIntervalCsv,
} from "@/lib/energy";
import {
  demoAppliances,
  demoBill,
  demoParameters,
  demoProfile,
} from "@/lib/demo-data";
import { t, type Locale } from "@/lib/i18n";
import type {
  AgentErrorResponse,
  AgentSuccessResponse,
  AnalysisParameters,
  ApplianceInputs,
  AppStage,
  BillInput,
  EnergyInsight,
  EnergyPlan,
  HouseholdProfile,
  LoadDataQuality,
  LoadPoint,
  PlanAction,
  SourceKind,
} from "@/lib/types";

const stageLabels: { id: AppStage; key: "baseline" | "diagnosis" | "plans"; step: string }[] =
  [
    { id: "baseline", key: "baseline", step: "01" },
    { id: "diagnosis", key: "diagnosis", step: "02" },
    { id: "plans", key: "plans", step: "03" },
  ];

const sourceCopy: Record<
  SourceKind,
  {
    title: "electricityBill" | "intervalData" | "applianceLabel";
    description: "billDescription" | "intervalDescription" | "labelDescription";
    accept: string;
    icon: typeof FileImage;
  }
> = {
  bill: {
    title: "electricityBill",
    description: "billDescription",
    accept: "image/*,.pdf",
    icon: FileImage,
  },
  interval: {
    title: "intervalData",
    description: "intervalDescription",
    accept: ".csv,text/csv",
    icon: FileSpreadsheet,
  },
  label: {
    title: "applianceLabel",
    description: "labelDescription",
    accept: "image/*",
    icon: Gauge,
  },
};

const specialistNames = [
  "Consumption Detective",
  "Appliance Auditor",
  "Cost Optimizer",
  "Comfort Guardian",
  "Carbon Analyst",
  "Plan and Action Coach",
] as const;

const sleep = (milliseconds: number) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency: "SGD",
    minimumFractionDigits: 2,
  }).format(value);
}

function numericValue(value: string, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export default function HomeShiftApp() {
  const [locale, setLocale] = useState<Locale>("en");
  const [stage, setStage] = useState<AppStage>("baseline");
  const [profile, setProfile] = useState<HouseholdProfile>({ ...demoProfile });
  const [bill, setBill] = useState<BillInput>({ ...demoBill });
  const [appliances, setAppliances] = useState<ApplianceInputs>(() =>
    structuredClone(demoAppliances),
  );
  const [parameters, setParameters] = useState<AnalysisParameters>({
    ...demoParameters,
  });
  const [tariffEdited, setTariffEdited] = useState(false);
  const [loadPoints, setLoadPoints] = useState<LoadPoint[]>(() =>
    generateDemoLoad(),
  );
  const [quality, setQuality] = useState<LoadDataQuality>(() =>
    assessLoadData(generateDemoLoad()),
  );
  const [files, setFiles] = useState<Record<SourceKind, string>>({
    bill: "synthetic_bill_may.pdf",
    interval: "synthetic_14_day_intervals.csv",
    label: "synthetic_appliance_label.jpg",
  });
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [agentResult, setAgentResult] =
    useState<AgentSuccessResponse | null>(null);
  const [agentError, setAgentError] = useState("");
  const [traceVisible, setTraceVisible] = useState(0);
  const [selectedPlanId, setSelectedPlanId] =
    useState<EnergyPlan["id"] | null>(null);
  const [toast, setToast] = useState("");

  const previewAnalysis = useMemo(() => {
    try {
      return analyzeHousehold(
        profile,
        bill,
        appliances,
        parameters,
        loadPoints,
      );
    } catch {
      return null;
    }
  }, [profile, bill, appliances, parameters, loadPoints]);

  const chartPoints = useMemo(
    () => aggregateDailyProfile(loadPoints),
    [loadPoints],
  );
  const activeAnalysis = agentResult ?? previewAnalysis;
  const baselineCarbon = calculateCarbon(
    bill.totalKwh,
    parameters.gridEmissionKgPerKwh,
  );
  const inputValid =
    profile.householdName.trim().length > 0 &&
    profile.homeType.trim().length > 0 &&
    profile.residents > 0 &&
    profile.comfortTemperature >= appliances.airConditioning.currentTemperature &&
    profile.monthlyTargetPercent > 0 &&
    bill.periodEnd >= bill.periodStart &&
    bill.totalKwh > 0 &&
    bill.totalCostSgd >= 0 &&
    parameters.tariffSgdPerKwh > 0 &&
    parameters.gridEmissionKgPerKwh > 0 &&
    quality.dayCount >= 7 &&
    quality.dayCount <= 30 &&
    quality.coveragePercent >= 80;
  const selectedPlan =
    activeAnalysis?.plans.find((plan) => plan.id === selectedPlanId) ??
    activeAnalysis?.plans.find(
      (plan) => plan.id === agentResult?.decision.recommendedPlanId,
    ) ??
    null;
  const isSynthetic = files.interval.startsWith("synthetic_");

  useEffect(() => {
    const saved = window.localStorage.getItem("homeshift-locale");
    const restore = window.setTimeout(() => {
      if (saved === "en" || saved === "zh") setLocale(saved);
    }, 0);
    return () => window.clearTimeout(restore);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
    window.localStorage.setItem("homeshift-locale", locale);
  }, [locale]);

  function resetAnalysis() {
    setAgentResult(null);
    setAgentError("");
    setSelectedPlanId(null);
    setTraceVisible(0);
    setStage("baseline");
  }

  async function handleFile(kind: SourceKind, file?: File) {
    if (!file) return;

    if (kind === "interval") {
      try {
        const parsed = parseIntervalCsv(await file.text());
        setLoadPoints(parsed.points);
        setQuality(parsed.quality);
        setFiles((current) => ({ ...current, interval: file.name }));
        resetAnalysis();
        showToast(
          locale === "zh"
            ? `已载入 ${parsed.quality.recordCount} 条半小时记录`
            : `Loaded ${parsed.quality.recordCount} half-hour records`,
        );
      } catch (error) {
        showToast(
          error instanceof Error ? error.message : "Could not read the CSV.",
        );
      }
      return;
    }

    setFiles((current) => ({ ...current, [kind]: file.name }));
    showToast(
      locale === "zh"
        ? `${file.name} 已作为本地证据选择`
        : `${file.name} selected as local evidence`,
    );
  }

  function loadSyntheticDemo() {
    const points = generateDemoLoad();
    setProfile({ ...demoProfile });
    setBill({ ...demoBill });
    setAppliances(structuredClone(demoAppliances));
    setParameters({ ...demoParameters });
    setTariffEdited(false);
    setLoadPoints(points);
    setQuality(assessLoadData(points));
    setFiles({
      bill: "synthetic_bill_may.pdf",
      interval: "synthetic_14_day_intervals.csv",
      label: "synthetic_appliance_label.jpg",
    });
    resetAnalysis();
    showToast(
      locale === "zh"
        ? "已重新载入完整合成案例"
        : "Complete synthetic case reloaded",
    );
  }

  function updateBill<K extends keyof BillInput>(key: K, value: BillInput[K]) {
    const next = { ...bill, [key]: value };
    setBill(next);
    if (
      !tariffEdited &&
      next.totalKwh > 0 &&
      (key === "totalKwh" || key === "totalCostSgd")
    ) {
      setParameters({
        ...parameters,
        tariffSgdPerKwh: Number(
          (next.totalCostSgd / next.totalKwh).toFixed(4),
        ),
      });
    }
    resetAnalysis();
  }

  async function runDiagnosis() {
    if (isAnalyzing || !inputValid) {
      if (!inputValid) showToast(t(locale, "cannotRun"));
      return;
    }

    setIsAnalyzing(true);
    setAgentError("");
    setAgentResult(null);
    setSelectedPlanId(null);
    setTraceVisible(0);
    setStage("diagnosis");

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 120_000);

    try {
      const response = await fetch("/api/agent", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          locale,
          profile,
          bill,
          appliances,
          parameters,
          loadPoints,
        }),
        signal: controller.signal,
      });
      const payload = (await response.json()) as
        | AgentSuccessResponse
        | AgentErrorResponse;

      if (!response.ok || payload.mode !== "live") {
        throw new Error(
          payload.mode === "error"
            ? liveAgentError(locale, payload.code, payload.message)
            : locale === "zh"
              ? "实时Agent运行未完成。"
              : "The live agent run did not complete.",
        );
      }

      setAgentResult(payload);
      setSelectedPlanId(payload.decision.recommendedPlanId);
      for (let index = 1; index <= payload.trace.length; index += 1) {
        await sleep(130);
        setTraceVisible(index);
      }
    } catch (error) {
      setAgentError(
        error instanceof DOMException && error.name === "AbortError"
          ? locale === "zh"
            ? "实时Agent运行超时，请检查网络后重试。"
            : "The live agent run timed out. Check the connection and retry."
          : error instanceof Error
            ? error.message
            : locale === "zh"
              ? "实时Agent运行未完成。"
              : "The live agent run did not complete.",
      );
    } finally {
      window.clearTimeout(timeout);
      setIsAnalyzing(false);
    }
  }

  function choosePlan(plan: EnergyPlan) {
    setSelectedPlanId(plan.id);
    showToast(t(locale, "selectedReady"));
  }

  function downloadTemplate() {
    const blob = new Blob([demoCsvTemplate()], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "homeshift-half-hour-template.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function showToast(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(""), 3200);
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <button
          className="brand"
          onClick={() => setStage("baseline")}
          aria-label="HomeShift AI home"
        >
          <span className="brand-mark">
            <Zap size={16} strokeWidth={2.6} />
          </span>
          <span>HomeShift AI</span>
        </button>

        <nav className="stage-nav" aria-label="Demo progress">
          {stageLabels.map((item) => (
            <button
              key={item.id}
              className={stage === item.id ? "active" : ""}
              disabled={item.id !== "baseline" && !agentResult}
              onClick={() => setStage(item.id)}
            >
              <span>{item.step}</span>
              {t(locale, item.key)}
            </button>
          ))}
        </nav>

        <div className="top-actions">
          <span className={`demo-pill ${isSynthetic ? "" : "real"}`}>
            <Sparkles size={13} />
            {isSynthetic
              ? t(locale, "syntheticDemo")
              : locale === "zh"
                ? "真实数据案例"
                : "Real-data case"}
          </span>
          <button
            className="language-button"
            onClick={() =>
              setLocale((current) => (current === "en" ? "zh" : "en"))
            }
            aria-label={
              locale === "en"
                ? t(locale, "switchChinese")
                : t(locale, "switchEnglish")
            }
            data-testid="language-toggle"
          >
            <Languages size={15} />
            <span>{locale === "en" ? "中文" : "EN"}</span>
          </button>
          <button
            className="icon-button"
            onClick={loadSyntheticDemo}
            title={t(locale, "reloadSynthetic")}
          >
            <RefreshCw size={17} />
          </button>
        </div>
      </header>

      <section className="content-wrap">
        {stage === "baseline" && (
          <BaselineView
            locale={locale}
            profile={profile}
            setProfile={(next) => {
              setProfile(next);
              resetAnalysis();
            }}
            bill={bill}
            updateBill={updateBill}
            appliances={appliances}
            setAppliances={(next) => {
              setAppliances(next);
              resetAnalysis();
            }}
            parameters={parameters}
            setParameters={(next) => {
              setParameters(next);
              resetAnalysis();
            }}
            setTariffEdited={setTariffEdited}
            files={files}
            quality={quality}
            chartPoints={chartPoints}
            patterns={previewAnalysis?.patterns ?? null}
            baselineCarbon={baselineCarbon}
            inputValid={inputValid}
            onFile={handleFile}
            onLoadDemo={loadSyntheticDemo}
            onDownloadTemplate={downloadTemplate}
            onAnalyze={runDiagnosis}
            isAnalyzing={isAnalyzing}
          />
        )}

        {stage === "diagnosis" && (
          <DiagnosisView
            locale={locale}
            chartPoints={chartPoints}
            analysis={agentResult ?? previewAnalysis}
            result={agentResult}
            error={agentError}
            traceVisible={traceVisible}
            isAnalyzing={isAnalyzing}
            onRetry={runDiagnosis}
            onContinue={() => setStage("plans")}
          />
        )}

        {stage === "plans" && agentResult && (
          <PlansView
            locale={locale}
            result={agentResult}
            selectedPlanId={selectedPlanId}
            selectedPlan={selectedPlan}
            parameters={parameters}
            profile={profile}
            bill={bill}
            onSelect={choosePlan}
          />
        )}
      </section>

      <footer className="site-footer">
        <span>
          <ShieldCheck size={14} />
          {t(locale, "footer")}
        </span>
        <span>{t(locale, "prototype")}</span>
      </footer>

      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={18} />
          {toast}
        </div>
      )}
    </main>
  );
}

function BaselineView({
  locale,
  profile,
  setProfile,
  bill,
  updateBill,
  appliances,
  setAppliances,
  parameters,
  setParameters,
  setTariffEdited,
  files,
  quality,
  chartPoints,
  patterns,
  baselineCarbon,
  inputValid,
  onFile,
  onLoadDemo,
  onDownloadTemplate,
  onAnalyze,
  isAnalyzing,
}: {
  locale: Locale;
  profile: HouseholdProfile;
  setProfile: (value: HouseholdProfile) => void;
  bill: BillInput;
  updateBill: <K extends keyof BillInput>(key: K, value: BillInput[K]) => void;
  appliances: ApplianceInputs;
  setAppliances: (value: ApplianceInputs) => void;
  parameters: AnalysisParameters;
  setParameters: (value: AnalysisParameters) => void;
  setTariffEdited: (value: boolean) => void;
  files: Record<SourceKind, string>;
  quality: LoadDataQuality;
  chartPoints: LoadPoint[];
  patterns: AgentSuccessResponse["patterns"] | null;
  baselineCarbon: number;
  inputValid: boolean;
  onFile: (kind: SourceKind, file?: File) => void;
  onLoadDemo: () => void;
  onDownloadTemplate: () => void;
  onAnalyze: () => void;
  isAnalyzing: boolean;
}) {
  const readySources = Object.values(files).filter(Boolean).length;

  return (
    <div className="view-stack">
      <div className="eyebrow-row">
        <span className="eyebrow">{t(locale, "eyebrow")}</span>
        <span className={`live-dot ${inputValid ? "" : "warning"}`}>
          <span />
          {inputValid
            ? t(locale, "dataReady")
            : t(locale, "dataNeedsAttention")}
        </span>
      </div>

      <section className="hero-grid">
        <div className="hero-copy">
          <p className="kicker">{t(locale, "kicker")}</p>
          <h1>
            {t(locale, "heroTitle")}{" "}
            <em>{t(locale, "heroAccent")}</em>
          </h1>
          <p className="hero-description">
            {t(locale, "heroDescription")}
          </p>
          <div className="hero-actions">
            <button
              className="primary-button"
              onClick={onAnalyze}
              disabled={isAnalyzing || !inputValid}
              data-testid="run-diagnosis"
            >
              {isAnalyzing ? (
                <LoaderCircle className="spin" size={18} />
              ) : (
                <WandSparkles size={18} />
              )}
              {isAnalyzing
                ? t(locale, "runningAgents")
                : t(locale, "runDiagnosis")}
              <ArrowRight size={17} />
            </button>
            <button className="text-button" onClick={onLoadDemo}>
              {t(locale, "reloadSynthetic")}
            </button>
          </div>
          {!inputValid && <p className="form-hint error">{t(locale, "cannotRun")}</p>}
          <div className="trust-row">
            <span>
              <LockKeyhole size={14} /> {t(locale, "userConfirmed")}
            </span>
            <span>
              <Database size={14} /> {t(locale, "deterministic")}
            </span>
          </div>
        </div>

        <div className="baseline-card">
          <div className="baseline-card-head">
            <div>
              <span className="label">{t(locale, "monthlyBaseline")}</span>
              <h2>{profile.householdName}</h2>
            </div>
            <span className="verified-badge">
              <Check size={13} /> {readySources} {t(locale, "sourcesReady")}
            </span>
          </div>
          <div className="big-metric">
            <span>{bill.totalKwh.toLocaleString()}</span>
            <div>
              <strong>kWh</strong>
              <small>{t(locale, "thisMonth")}</small>
            </div>
          </div>
          <div
            className="goal-track"
            aria-label={`${profile.monthlyTargetPercent}% reduction goal`}
          >
            <span style={{ width: `${Math.min(100, profile.monthlyTargetPercent * 5)}%` }} />
            <i style={{ left: `${Math.min(92, profile.monthlyTargetPercent * 5)}%` }}>
              {t(locale, "target")}
            </i>
          </div>
          <div className="mini-metrics">
            <div>
              <span>{t(locale, "estimatedBill")}</span>
              <strong>{formatMoney(bill.totalCostSgd)}</strong>
            </div>
            <div>
              <span>{t(locale, "carbon")}</span>
              <strong>{baselineCarbon} kg</strong>
            </div>
            <div>
              <span>{t(locale, "target")}</span>
              <strong>−{profile.monthlyTargetPercent}%</strong>
            </div>
          </div>
          <div className="home-profile">
            <Home size={17} />
            <span>{profile.homeType}</span>
            <span>
              {profile.residents} {t(locale, "residents")}
            </span>
            <span>
              {profile.workFromHome ? t(locale, "wfh") : t(locale, "noWfh")}
            </span>
          </div>
        </div>
      </section>

      <section className="data-grid">
        <div className="panel load-panel">
          <div className="panel-heading">
            <div>
              <span className="label">{t(locale, "dailySignature")}</span>
              <h2>{t(locale, "energyTiming")}</h2>
            </div>
            <span className="signal-chip">
              {t(locale, "peak")} {patterns?.peakTime ?? "—"}
            </span>
          </div>
          <LoadChart points={chartPoints} />
          <div className="chart-notes">
            <span>
              <i className="dot lime" /> {t(locale, "averageProfile")}
            </span>
            <span>
              <i className="dot coral" /> {t(locale, "eveningOpportunity")}
            </span>
            <span className="chart-summary">
              <MoonStar size={14} />
              {t(locale, "overnightMeasured")}
            </span>
          </div>
        </div>

        <div className="panel source-panel">
          <div className="panel-heading">
            <div>
              <span className="label">{t(locale, "dataDesk")}</span>
              <h2>{t(locale, "bringEvidence")}</h2>
            </div>
            <InfoTooltip text={t(locale, "manualEvidence")} />
          </div>
          <div className="upload-list">
            {(Object.keys(sourceCopy) as SourceKind[]).map((kind) => {
              const source = sourceCopy[kind];
              const Icon = source.icon;
              return (
                <label className="upload-row" key={kind}>
                  <span className="upload-icon">
                    <Icon size={19} />
                  </span>
                  <span className="upload-copy">
                    <strong>{t(locale, source.title)}</strong>
                    <small>
                      {files[kind] || t(locale, source.description)}
                    </small>
                  </span>
                  <span className="upload-state">
                    {files[kind] ? <Check size={15} /> : <Upload size={15} />}
                  </span>
                  <input
                    type="file"
                    accept={source.accept}
                    onChange={(event) =>
                      onFile(kind, event.target.files?.[0])
                    }
                  />
                </label>
              );
            })}
          </div>
          <button className="template-button" onClick={onDownloadTemplate}>
            <Download size={15} />
            {t(locale, "downloadTemplate")}
          </button>
          <DataQualityCard locale={locale} quality={quality} />
        </div>
      </section>

      <details className="panel setup-panel" open>
        <summary>
          <div>
            <span className="label">{t(locale, "calculationBasis")}</span>
            <h2>{t(locale, "setupTitle")}</h2>
            <p>{t(locale, "setupDescription")}</p>
          </div>
          <ChevronRight size={19} />
        </summary>

        <div className="setup-groups">
          <fieldset>
            <legend>{t(locale, "householdSection")}</legend>
            <div className="form-grid">
              <Field label={t(locale, "householdName")} wide>
                <input
                  value={profile.householdName}
                  onChange={(event) =>
                    setProfile({ ...profile, householdName: event.target.value })
                  }
                />
              </Field>
              <Field label={t(locale, "homeType")} wide>
                <input
                  value={profile.homeType}
                  onChange={(event) =>
                    setProfile({ ...profile, homeType: event.target.value })
                  }
                />
              </Field>
              <NumberField
                label={t(locale, "residentCount")}
                value={profile.residents}
                min={1}
                max={20}
                step={1}
                onChange={(value) =>
                  setProfile({ ...profile, residents: value })
                }
              />
              <Field label={t(locale, "workFromHome")}>
                <label className="toggle-field">
                  <input
                    type="checkbox"
                    checked={profile.workFromHome}
                    onChange={(event) =>
                      setProfile({
                        ...profile,
                        workFromHome: event.target.checked,
                      })
                    }
                  />
                  <span>
                    {profile.workFromHome
                      ? locale === "zh" ? "是" : "Yes"
                      : locale === "zh" ? "否" : "No"}
                  </span>
                </label>
              </Field>
              <NumberField
                label={t(locale, "maxSleepTemperature")}
                value={profile.comfortTemperature}
                min={20}
                max={30}
                step={0.5}
                onChange={(value) =>
                  setProfile({ ...profile, comfortTemperature: value })
                }
              />
              <NumberField
                label={t(locale, "budget")}
                value={profile.budgetSgd}
                min={0}
                step={10}
                onChange={(value) =>
                  setProfile({ ...profile, budgetSgd: value })
                }
              />
              <NumberField
                label={t(locale, "reductionTarget")}
                value={profile.monthlyTargetPercent}
                min={1}
                max={30}
                step={1}
                onChange={(value) =>
                  setProfile({ ...profile, monthlyTargetPercent: value })
                }
              />
            </div>
          </fieldset>

          <fieldset>
            <legend>{t(locale, "billSection")}</legend>
            <div className="form-grid">
              <Field label={t(locale, "periodStart")}>
                <input
                  type="date"
                  value={bill.periodStart}
                  onChange={(event) =>
                    updateBill("periodStart", event.target.value)
                  }
                />
              </Field>
              <Field label={t(locale, "periodEnd")}>
                <input
                  type="date"
                  value={bill.periodEnd}
                  onChange={(event) =>
                    updateBill("periodEnd", event.target.value)
                  }
                />
              </Field>
              <NumberField
                label={t(locale, "totalKwh")}
                value={bill.totalKwh}
                min={0.1}
                step={0.1}
                onChange={(value) => updateBill("totalKwh", value)}
              />
              <NumberField
                label={t(locale, "totalCost")}
                value={bill.totalCostSgd}
                min={0}
                step={0.01}
                onChange={(value) => updateBill("totalCostSgd", value)}
              />
              <NumberField
                label={t(locale, "tariff")}
                value={parameters.tariffSgdPerKwh}
                min={0.0001}
                step={0.0001}
                onChange={(value) => {
                  setTariffEdited(true);
                  setParameters({ ...parameters, tariffSgdPerKwh: value });
                }}
              />
              <NumberField
                label={t(locale, "gridFactor")}
                value={parameters.gridEmissionKgPerKwh}
                min={0.0001}
                step={0.001}
                onChange={(value) =>
                  setParameters({
                    ...parameters,
                    gridEmissionKgPerKwh: value,
                  })
                }
              />
            </div>
          </fieldset>

          <fieldset>
            <legend>{t(locale, "applianceSection")}</legend>
            <div className="form-grid">
              <NumberField
                label={t(locale, "acQuantity")}
                value={appliances.airConditioning.quantity}
                min={0}
                max={20}
                step={1}
                onChange={(value) =>
                  setAppliances({
                    ...appliances,
                    airConditioning: {
                      ...appliances.airConditioning,
                      quantity: value,
                    },
                  })
                }
              />
              <NumberField
                label={t(locale, "acPower")}
                value={appliances.airConditioning.ratedPowerKw}
                min={0}
                step={0.1}
                onChange={(value) =>
                  setAppliances({
                    ...appliances,
                    airConditioning: {
                      ...appliances.airConditioning,
                      ratedPowerKw: value,
                    },
                  })
                }
              />
              <NumberField
                label={t(locale, "acHours")}
                value={appliances.airConditioning.hoursPerDay}
                min={0}
                max={24}
                step={0.5}
                onChange={(value) =>
                  setAppliances({
                    ...appliances,
                    airConditioning: {
                      ...appliances.airConditioning,
                      hoursPerDay: value,
                    },
                  })
                }
              />
              <NumberField
                label={t(locale, "acTemperature")}
                value={appliances.airConditioning.currentTemperature}
                min={16}
                max={30}
                step={0.5}
                onChange={(value) =>
                  setAppliances({
                    ...appliances,
                    airConditioning: {
                      ...appliances.airConditioning,
                      currentTemperature: value,
                    },
                  })
                }
              />
              <NumberField
                label={t(locale, "refrigeratorAnnual")}
                value={appliances.refrigerator.annualKwh}
                min={0}
                step={1}
                onChange={(value) =>
                  setAppliances({
                    ...appliances,
                    refrigerator: {
                      ...appliances.refrigerator,
                      annualKwh: value,
                    },
                  })
                }
              />
              <NumberField
                label={t(locale, "refrigeratorCost")}
                value={appliances.refrigerator.replacementCostSgd}
                min={0}
                step={10}
                onChange={(value) =>
                  setAppliances({
                    ...appliances,
                    refrigerator: {
                      ...appliances.refrigerator,
                      replacementCostSgd: value,
                    },
                  })
                }
              />
              <NumberField
                label={t(locale, "heaterPower")}
                value={appliances.waterHeater.ratedPowerKw}
                min={0}
                step={0.1}
                onChange={(value) =>
                  setAppliances({
                    ...appliances,
                    waterHeater: {
                      ...appliances.waterHeater,
                      ratedPowerKw: value,
                    },
                  })
                }
              />
              <NumberField
                label={t(locale, "heaterMinutes")}
                value={appliances.waterHeater.minutesPerDay}
                min={0}
                step={1}
                onChange={(value) =>
                  setAppliances({
                    ...appliances,
                    waterHeater: {
                      ...appliances.waterHeater,
                      minutesPerDay: value,
                    },
                  })
                }
              />
              <NumberField
                label={t(locale, "washerCycle")}
                value={appliances.washingMachine.kwhPerCycle}
                min={0}
                step={0.1}
                onChange={(value) =>
                  setAppliances({
                    ...appliances,
                    washingMachine: {
                      ...appliances.washingMachine,
                      kwhPerCycle: value,
                    },
                  })
                }
              />
              <NumberField
                label={t(locale, "washerWeekly")}
                value={appliances.washingMachine.cyclesPerWeek}
                min={0}
                step={1}
                onChange={(value) =>
                  setAppliances({
                    ...appliances,
                    washingMachine: {
                      ...appliances.washingMachine,
                      cyclesPerWeek: value,
                    },
                  })
                }
              />
              <NumberField
                label={t(locale, "otherEnergy")}
                value={appliances.otherMonthlyKwh}
                min={0}
                step={1}
                onChange={(value) =>
                  setAppliances({ ...appliances, otherMonthlyKwh: value })
                }
              />
            </div>
          </fieldset>
        </div>
        <p className="manual-note">
          <Info size={15} />
          {t(locale, "manualValues")}
        </p>
      </details>
    </div>
  );
}

function DiagnosisView({
  locale,
  chartPoints,
  analysis,
  result,
  error,
  traceVisible,
  isAnalyzing,
  onRetry,
  onContinue,
}: {
  locale: Locale;
  chartPoints: LoadPoint[];
  analysis: AgentSuccessResponse | ReturnType<typeof analyzeHousehold> | null;
  result: AgentSuccessResponse | null;
  error: string;
  traceVisible: number;
  isAnalyzing: boolean;
  onRetry: () => void;
  onContinue: () => void;
}) {
  const trace = result?.trace ?? [];
  const decision = result?.decision;

  return (
    <div className="view-stack">
      <PageIntro
        eyebrow={t(locale, "diagnosisEyebrow")}
        title={t(locale, "diagnosisTitle")}
        accent={t(locale, "diagnosisAccent")}
        description={t(locale, "diagnosisDescription")}
        side={
          <span className="mode-badge live">
            <Activity size={14} />
            {t(locale, "liveAgentRun")}
          </span>
        }
      />

      {error && (
        <div className="agent-error" role="alert">
          <AlertCircle size={21} />
          <div>
            <strong>
              {locale === "zh" ? "实时分析未完成" : "Live analysis did not complete"}
            </strong>
            <span>{error}</span>
          </div>
          <button className="secondary-button" onClick={onRetry}>
            <RefreshCw size={15} />
            {t(locale, "retry")}
          </button>
        </div>
      )}

      <section className="diagnosis-grid">
        <div className="panel trace-panel">
          <div className="panel-heading">
            <div>
              <span className="label">{t(locale, "agentWorklog")}</span>
              <h2>{t(locale, "sixSpecialists")}</h2>
            </div>
            {isAnalyzing && <LoaderCircle className="spin" size={19} />}
          </div>
          <div className="trace-list">
            {(result ? trace : specialistNames).map((entry, index) => {
              const finding = typeof entry === "string" ? null : entry;
              const agentName =
                typeof entry === "string" ? entry : entry.agent;
              const visible = Boolean(result) && index < traceVisible;
              return (
                <div
                  className={`trace-row ${visible ? "visible" : ""}`}
                  key={agentName}
                >
                  <span className="trace-index">
                    {visible ? <Check size={14} /> : index + 1}
                  </span>
                  <div>
                    <strong>{agentName}</strong>
                    <span>
                      {visible
                        ? finding?.task
                        : t(locale, "waitingForAgents")}
                    </span>
                  </div>
                  <p>
                    {visible ? (
                      <>
                        {finding?.result}
                        <small className="evidence-chip">
                          {evidenceLabel(locale, finding?.evidence)}
                        </small>
                      </>
                    ) : (
                      "—"
                    )}
                  </p>
                </div>
              );
            })}
          </div>

          {decision && (
            <div className="orchestrator-note">
              <Sparkles size={18} />
              <div>
                <strong>{t(locale, "orchestratorDecision")}</strong>
                <span>
                  {planName(locale, decision.recommendedPlanId)} ·{" "}
                  {decision.rationale[0]}
                </span>
              </div>
            </div>
          )}
        </div>

        <div className="panel compact-chart-panel">
          <div className="panel-heading">
            <div>
              <span className="label">{t(locale, "detectiveView")}</span>
              <h2>{t(locale, "peakConcentration")}</h2>
            </div>
            <BarChart3 size={19} />
          </div>
          <LoadChart points={chartPoints} />
          {analysis && (
            <div className="fact-grid">
              <span>
                <small>{t(locale, "peak")}</small>
                <strong>{analysis.patterns.peakTime}</strong>
              </span>
              <span>
                <small>{locale === "zh" ? "晚间占比" : "Evening share"}</small>
                <strong>{analysis.patterns.eveningSharePercent}%</strong>
              </span>
              <span>
                <small>{locale === "zh" ? "日均用电" : "Daily average"}</small>
                <strong>{analysis.patterns.dailyAverageKwh} kWh</strong>
              </span>
            </div>
          )}
        </div>
      </section>

      {analysis && (
        <>
          <section className="insight-grid">
            {analysis.insights.map((insight) => (
              <InsightCard key={insight.id} insight={insight} locale={locale} />
            ))}
          </section>

          <section className="panel appliance-panel">
            <div className="panel-heading">
              <div>
                <span className="label">{t(locale, "applianceAudit")}</span>
                <h2>{t(locale, "estimatedContribution")}</h2>
              </div>
              <Gauge size={19} />
            </div>
            <div className="appliance-list">
              {analysis.applianceEstimates.map((appliance) => (
                <div className="appliance-row" key={appliance.key}>
                  <div>
                    <strong>{applianceName(locale, appliance.key)}</strong>
                    <span>
                      {applianceBasis(
                        locale,
                        appliance.key,
                        appliance.normalized,
                      )}
                    </span>
                  </div>
                  <div className="appliance-bar">
                    <span
                      style={{
                        width: `${Math.min(100, appliance.sharePercent)}%`,
                      }}
                    />
                  </div>
                  <b>{appliance.monthlyKwh} kWh</b>
                  <small>
                    {appliance.sharePercent}%
                    {appliance.normalized
                      ? ` · ${t(locale, "normalized")}`
                      : ""}
                  </small>
                </div>
              ))}
            </div>
          </section>
        </>
      )}

      {decision && (
        <section className="decision-grid">
          <DecisionList
            icon={<Sparkles size={17} />}
            title={t(locale, "rationale")}
            items={decision.rationale}
          />
          <DecisionList
            icon={<ShieldCheck size={17} />}
            title={t(locale, "rejectedRisks")}
            items={
              decision.rejectedRisks.length
                ? decision.rejectedRisks
                : [t(locale, "noRejectedRisks")]
            }
          />
          <DecisionList
            icon={<ArrowRight size={17} />}
            title={t(locale, "nextActions")}
            items={decision.nextActions}
          />
        </section>
      )}

      <div className="view-actions">
        <button
          className="primary-button"
          onClick={onContinue}
          disabled={!result}
        >
          {t(locale, "continuePlans")}
          <ArrowRight size={17} />
        </button>
      </div>
    </div>
  );
}

function PlansView({
  locale,
  result,
  selectedPlanId,
  selectedPlan,
  parameters,
  profile,
  bill,
  onSelect,
}: {
  locale: Locale;
  result: AgentSuccessResponse;
  selectedPlanId: EnergyPlan["id"] | null;
  selectedPlan: EnergyPlan | null;
  parameters: AnalysisParameters;
  profile: HouseholdProfile;
  bill: BillInput;
  onSelect: (plan: EnergyPlan) => void;
}) {
  return (
    <div className="view-stack">
      <PageIntro
        eyebrow={t(locale, "plansEyebrow")}
        title={t(locale, "plansTitle")}
        accent={t(locale, "plansAccent")}
        description={t(locale, "plansDescription")}
        side={
          <div className="parameter-chip">
            S${parameters.tariffSgdPerKwh.toFixed(4)}/kWh ·{" "}
            {parameters.gridEmissionKgPerKwh.toFixed(3)} kg CO₂/kWh
          </div>
        }
      />

      <section className="plan-grid">
        {result.plans.map((plan) => {
          const recommended =
            plan.id === result.decision.recommendedPlanId;
          const selected = plan.id === selectedPlanId;
          return (
            <article
              className={`plan-card ${recommended ? "recommended" : ""} ${selected ? "selected" : ""} ${plan.feasible ? "" : "infeasible"}`}
              key={plan.id}
              style={{ "--plan-accent": plan.accent } as React.CSSProperties}
            >
              <div className="plan-card-head">
                <div>
                  <span>{planShortName(locale, plan.id)}</span>
                  <h2>{planName(locale, plan.id)}</h2>
                </div>
                {recommended && (
                  <span className="recommended-badge">
                    <Sparkles size={13} />
                    {t(locale, "recommended")}
                  </span>
                )}
              </div>
              <p>{planDescription(locale, plan.id)}</p>
              <div className="plan-status-row">
                <span className={plan.feasible ? "good" : "bad"}>
                  {plan.feasible
                    ? t(locale, "feasible")
                    : t(locale, "infeasible")}
                </span>
                <span className={plan.meetsTarget ? "good" : "neutral"}>
                  {plan.meetsTarget
                    ? t(locale, "targetMet")
                    : t(locale, "targetMissed")}
                </span>
              </div>
              <div className="plan-energy">
                <strong>−{plan.monthlySavingKwh}</strong>
                <span>kWh / month</span>
                <small>
                  −{Math.round((plan.monthlySavingKwh / bill.totalKwh) * 100)}%
                  {" "}
                  {locale === "zh" ? "账单基线" : "of bill baseline"}
                </small>
              </div>
              <div className="plan-metrics">
                <Metric
                  icon={<CircleDollarSign size={17} />}
                  label={t(locale, "billSaving")}
                  value={`${formatMoney(plan.monthlySavingSgd)}/mo`}
                />
                <Metric
                  icon={<Leaf size={17} />}
                  label={t(locale, "avoidedCarbon")}
                  value={`${plan.carbonSavingKg} kg/mo`}
                />
                <Metric
                  icon={<Thermometer size={17} />}
                  label={t(locale, "comfort")}
                  value={`${plan.comfortScore}/100`}
                />
                <Metric
                  icon={<CircleDollarSign size={17} />}
                  label={t(locale, "upfront")}
                  value={formatMoney(plan.upfrontCostSgd)}
                />
              </div>
              <button
                className={selected ? "selected-button" : "plan-button"}
                onClick={() => onSelect(plan)}
                disabled={!plan.feasible}
              >
                {selected ? <Check size={16} /> : <ChevronRight size={16} />}
                {selected ? t(locale, "selectedPlan") : t(locale, "selectPlan")}
              </button>
            </article>
          );
        })}
      </section>

      {selectedPlan && (
        <section className="selected-plan-panel">
          <div className="selected-plan-copy">
          <span className="label">{t(locale, "planActions")}</span>
            <h2>{planName(locale, selectedPlan.id)}</h2>
            <p>{planRationale(locale, selectedPlan.id)}</p>
            <div className="action-list">
              {selectedPlan.actions.map((action, index) => (
                <div className="action-row" key={action.code}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <strong>{actionTitle(locale, action)}</strong>
                    <p>{actionDetail(locale, action)}</p>
                  </div>
                  <b>−{action.monthlySavingKwh} kWh</b>
                </div>
              ))}
            </div>
          </div>
          <aside className="decision-memo">
            <span className="label">{t(locale, "finalDecision")}</span>
            <h3>{t(locale, "rationale")}</h3>
            <ul>
              {result.decision.rationale.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <h3>{t(locale, "hardConstraints")}</h3>
            <ul>
              {selectedPlan.constraintNotes.map((item) => (
                <li key={item}>{constraintNote(locale, item)}</li>
              ))}
            </ul>
            <div className="assumption-note">
              <Info size={16} />
              <span>
                <strong>{t(locale, "calculationBasis")}</strong>
                {t(locale, "assumptions")}
              </span>
            </div>
            <small>
              {profile.householdName} · {result.model}
            </small>
          </aside>
        </section>
      )}
    </div>
  );
}

function DataQualityCard({
  locale,
  quality,
}: {
  locale: Locale;
  quality: LoadDataQuality;
}) {
  return (
    <div
      className={`quality-card ${quality.coveragePercent < 95 ? "warning" : ""}`}
    >
      <div>
        <span className="label">{t(locale, "dataQuality")}</span>
        <strong>{quality.coveragePercent}% {t(locale, "coverage")}</strong>
      </div>
      <div className="quality-metrics">
        <span>
          <b>{quality.dayCount}</b> {t(locale, "days")}
        </span>
        <span>
          <b>{quality.recordCount}</b> {t(locale, "records")}
        </span>
        <span>
          <b>{quality.missingIntervals}</b> {t(locale, "missing")}
        </span>
        {quality.duplicateIntervals > 0 && (
          <span>
            <b>{quality.duplicateIntervals}</b> {t(locale, "duplicates")}
          </span>
        )}
      </div>
      {quality.warnings.map((warning) => (
        <small key={warning}>{warning}</small>
      ))}
    </div>
  );
}

function Field({
  label,
  wide = false,
  children,
}: {
  label: string;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={`form-field ${wide ? "wide" : ""}`}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label}>
      <input
        type="number"
        value={Number.isFinite(value) ? value : ""}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(numericValue(event.target.value))}
      />
    </Field>
  );
}

function LoadChart({ points }: { points: LoadPoint[] }) {
  return (
    <div className="load-chart" aria-label="Average half-hour energy chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points}>
          <defs>
            <linearGradient id="load-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#c8f547" stopOpacity={0.42} />
              <stop offset="100%" stopColor="#c8f547" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(255,255,255,0.07)" vertical={false} />
          <XAxis
            dataKey="time"
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#87908f", fontSize: 11 }}
            interval={7}
          />
          <YAxis hide />
          <Tooltip
            contentStyle={{
              background: "#17201f",
              border: "1px solid rgba(255,255,255,.12)",
              borderRadius: 12,
              color: "#f8faf7",
            }}
            formatter={(value) => [`${Number(value).toFixed(3)} kWh`, "Average"]}
          />
          <Area
            type="monotone"
            dataKey="kwh"
            stroke="#c8f547"
            strokeWidth={2.3}
            fill="url(#load-fill)"
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function InsightCard({
  insight,
  locale,
}: {
  insight: EnergyInsight;
  locale: Locale;
}) {
  return (
    <article className={`insight-card ${insight.severity}`}>
      <div>
        <span className="severity-dot" />
        <small>{evidenceLabel(locale, insight.evidenceKind)}</small>
      </div>
      <h3>{insightTitle(locale, insight)}</h3>
      <p>{insightDetail(locale, insight)}</p>
      <blockquote>{insightEvidence(locale, insight)}</blockquote>
      <strong>
        {insight.confidence}% {locale === "zh" ? "置信度" : "confidence"}
      </strong>
    </article>
  );
}

function DecisionList({
  icon,
  title,
  items,
}: {
  icon: ReactNode;
  title: string;
  items: string[];
}) {
  return (
    <article className="decision-list">
      <div>
        {icon}
        <strong>{title}</strong>
      </div>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </article>
  );
}

function PageIntro({
  eyebrow,
  title,
  accent,
  description,
  side,
}: {
  eyebrow: string;
  title: string;
  accent: string;
  description: string;
  side?: ReactNode;
}) {
  return (
    <section className="page-intro">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>
          {title} <em>{accent}</em>
        </h1>
        <p>{description}</p>
      </div>
      {side}
    </section>
  );
}

function Metric({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="metric-row">
      <span>{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function InfoTooltip({ text }: { text: string }) {
  return (
    <span className="info-tooltip" tabIndex={0}>
      <Info size={16} />
      <span>{text}</span>
    </span>
  );
}

function evidenceLabel(
  locale: Locale,
  evidence?: "measured" | "estimated" | "tool-calculated",
) {
  if (evidence === "measured") return t(locale, "measured");
  if (evidence === "tool-calculated") return t(locale, "toolCalculated");
  return t(locale, "estimated");
}

function applianceName(
  locale: Locale,
  key: AgentSuccessResponse["applianceEstimates"][number]["key"],
) {
  if (locale === "en") {
    return {
      "air-conditioning": "Air conditioning",
      refrigeration: "Refrigeration",
      "water-heating": "Water heating",
      laundry: "Laundry",
      other: "Other / unattributed",
    }[key];
  }
  return {
    "air-conditioning": "空调",
    refrigeration: "冰箱",
    "water-heating": "热水器",
    laundry: "洗衣",
    other: "其他 / 未归因",
  }[key];
}

function planName(locale: Locale, id: EnergyPlan["id"]) {
  const labels = {
    en: { money: "Maximum Savings", balanced: "Balanced", carbon: "Low Carbon" },
    zh: { money: "最大节省", balanced: "均衡方案", carbon: "低碳方案" },
  };
  return labels[locale][id];
}

function planShortName(locale: Locale, id: EnergyPlan["id"]) {
  const labels = {
    en: { money: "Save most", balanced: "Comfort first", carbon: "Cut carbon" },
    zh: { money: "节省最多", balanced: "舒适优先", carbon: "减少碳排" },
  };
  return labels[locale][id];
}

function planDescription(locale: Locale, id: EnergyPlan["id"]) {
  if (locale === "en") {
    return {
      money: "Uses the full declared comfort range and strongest no-purchase routine.",
      balanced: "Targets measured opportunities while protecting sleep and work routines.",
      carbon: "Adds an appliance upgrade and maintenance to the balanced routine.",
    }[id];
  }
  return {
    money: "在舒适温度上限内采用最积极的零购置行动。",
    balanced: "优先保护睡眠和工作习惯，再利用实测节能机会。",
    carbon: "在均衡行动基础上加入设备升级和维护。",
  }[id];
}

function actionTitle(locale: Locale, action: PlanAction) {
  if (locale === "en") return action.title;
  return {
    "ac-maximum": "充分利用可接受的空调温度范围",
    "ac-balanced": "使用空调智能睡眠模式",
    "baseload-maximum": "削减大部分可避免的夜间基荷",
    "baseload-balanced": "建立选择性夜间断电流程",
    "laundry-maximum": "持续使用冷水洗涤",
    "laundry-balanced": "将部分洗涤改为冷水模式",
    "balanced-routine": "采用均衡行动组合",
    "refrigerator-upgrade": "规划高效冰箱替换",
    "cooling-maintenance": "优化空调维护",
  }[action.code];
}

function actionDetail(locale: Locale, action: PlanAction) {
  if (locale === "en") return action.detail;
  return {
    "ac-maximum": "提高夜间设定温度，但绝不超过用户填写的舒适温度上限。",
    "ac-balanced": "入睡90分钟后小幅提高设定温度。",
    "baseload-maximum": "关闭可停用插座组，同时保留居家办公设备。",
    "baseload-balanced": "只实现一半实测基荷潜力，降低执行负担。",
    "laundry-maximum": "以冷水洗涤产生节能，不把单纯错峰计为节能量。",
    "laundry-balanced": "在可重复的每周洗涤中使用冷水设置。",
    "balanced-routine": "保持舒适优先的空调、基荷和洗衣组合。",
    "refrigerator-upgrade": "按申报冰箱耗电量保守计算25%的替换潜力。",
    "cooling-maintenance": "清洁滤网并改善密封，按空调耗电量的3%计算。",
  }[action.code];
}

function insightTitle(locale: Locale, insight: EnergyInsight) {
  if (locale === "en") return insight.title;
  return {
    peak: "日常用电集中在实测峰值时段",
    baseload: "夜间基荷存在可量化的削减范围",
    "top-appliance": "申报设备中存在主要耗电来源",
  }[insight.id];
}

function insightDetail(locale: Locale, insight: EnergyInsight) {
  if (locale === "en") return insight.detail;
  return {
    peak: "多日平均曲线用于识别最稳定、可重复的高负荷时段。",
    baseload: "使用家庭自身较低的夜间观测值建立目标，不采用通用家庭基准。",
    "top-appliance": "估算使用用户申报的设备和使用时间，并与账单总量进行校准。",
  }[insight.id];
}

function insightEvidence(locale: Locale, insight: EnergyInsight) {
  if (locale === "en") return insight.evidence;
  if (insight.id === "peak") {
    const match = insight.evidence.match(
      /^([\d.]+)%.*?average peak is ([\d:]+)\.$/,
    );
    return match
      ? `实测用电中有 ${match[1]}% 发生在18:00以后；平均峰值时段为 ${match[2]}。`
      : insight.evidence;
  }
  if (insight.id === "baseload") {
    const values = insight.evidence.match(/[\d.]+/g);
    return values?.length
      ? `夜间平均每半小时 ${values[0]} kWh，夜间第20百分位为 ${values[1]} kWh。`
      : insight.evidence;
  }
  const values = insight.evidence.match(/[\d.]+/g);
  return values?.length
    ? `估算月耗电 ${values[0]} kWh，占账单基线的 ${values[1]}%。`
    : insight.evidence;
}

function applianceBasis(
  locale: Locale,
  key: AgentSuccessResponse["applianceEstimates"][number]["key"],
  normalized: boolean,
) {
  if (locale === "en") {
    const text = {
      "air-conditioning":
        "Quantity × rated power × daily hours × 30 × 0.65 duty factor",
      refrigeration: "Declared annual energy ÷ 12",
      "water-heating": "Rated power × daily minutes × 30",
      laundry: "Energy per cycle × weekly cycles × 52 ÷ 12",
      other: "Declared other use plus any unallocated bill energy",
    }[key];
    return normalized ? `${text}; normalized to the bill total` : text;
  }
  const text = {
    "air-conditioning": "数量 × 额定功率 × 每日时长 × 30 × 0.65负载系数",
    refrigeration: "申报年耗电量 ÷ 12",
    "water-heating": "额定功率 × 每日分钟数 × 30",
    laundry: "单次耗电 × 每周次数 × 52 ÷ 12",
    other: "申报的其他耗电加上未归因账单用电",
  }[key];
  return normalized ? `${text}；已按账单总量归一化` : text;
}

function planRationale(locale: Locale, id: EnergyPlan["id"]) {
  if (locale === "en") {
    return {
      money:
        "Largest no-purchase reduction that stays within the household's declared comfort limit.",
      balanced:
        "Low-effort measures tied directly to the household's load shape and declared schedule.",
      carbon:
        "Greatest modeled energy and carbon reduction, subject to the declared replacement budget.",
    }[id];
  }
  return {
    money: "在家庭申报的舒适温度范围内，实现最大的零购置节能。",
    balanced: "低执行难度，且每项行动都对应实测负荷或申报时间表。",
    carbon: "在替换预算允许时，实现模型估算中最大的能源和碳减排。",
  }[id];
}

function constraintNote(locale: Locale, note: string) {
  if (locale === "en") return note;
  const budget = note.match(/S\$([\d.]+)/);
  if (note.startsWith("Upfront cost is within")) {
    return `前期投入不超过 S$${budget?.[1] ?? "—"} 预算。`;
  }
  if (note.startsWith("Upfront cost exceeds")) {
    return `前期投入超过 S$${budget?.[1] ?? "—"} 预算。`;
  }
  const temperature = note.match(/([\d.]+)°C/);
  if (temperature) {
    return `所有空调行动均不超过 ${temperature[1]}°C。`;
  }
  if (note.startsWith("Work-from-home")) {
    return "居家办公设备保持可用。";
  }
  return "未申报居家办公可用性约束。";
}

function liveAgentError(
  locale: Locale,
  code: AgentErrorResponse["code"],
  fallback: string,
) {
  if (locale !== "zh") return fallback;
  if (code === "configuration_missing") {
    return "未配置 OPENAI_API_KEY，实时多Agent演示无法运行。配置后请重新诊断。";
  }
  if (code === "invalid_input") {
    return "提交的数据未通过校验，请返回基线页检查输入后重试。";
  }
  return "实时多Agent调用失败，请检查模型配置或网络后重新运行。";
}
