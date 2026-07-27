"use client";

import {
  Activity,
  ArrowRight,
  BarChart3,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  CloudUpload,
  Database,
  FileImage,
  FileSpreadsheet,
  Gauge,
  Home,
  Info,
  Leaf,
  Languages,
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
import {
  Children,
  cloneElement,
  isValidElement,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  buildInsights,
  calculateCarbon,
  calculateCost,
  compareActualToPlan,
  detectLoadPatterns,
  estimateAppliances,
  generateDemoLoad,
  generatePlans,
  parseIntervalCsv,
} from "@/lib/energy";
import { agentTrace, dailyTasks, demoProfile } from "@/lib/demo-data";
import { translate, type Locale } from "@/lib/i18n";
import type {
  AppStage,
  EnergyPlan,
  LoadPoint,
  SourceKind,
} from "@/lib/types";

const stageLabels: { id: AppStage; label: string; step: string }[] = [
  { id: "baseline", label: "Baseline", step: "01" },
  { id: "diagnosis", label: "Diagnosis", step: "02" },
  { id: "plans", label: "Plans", step: "03" },
  { id: "track", label: "Track", step: "04" },
];

const sourceCopy: Record<
  SourceKind,
  { title: string; description: string; accept: string; icon: typeof FileImage }
> = {
  bill: {
    title: "Electricity bill",
    description: "PNG, JPG or PDF",
    accept: "image/*,.pdf",
    icon: FileImage,
  },
  interval: {
    title: "Half-hour data",
    description: "CSV with time + kWh",
    accept: ".csv,text/csv",
    icon: FileSpreadsheet,
  },
  label: {
    title: "Appliance label",
    description: "Energy label photo",
    accept: "image/*",
    icon: Gauge,
  },
};

const sleep = (milliseconds: number) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency: "SGD",
    minimumFractionDigits: 2,
  }).format(value);
}

export default function HomeShiftApp() {
  const [locale, setLocale] = useState<Locale>("en");
  const [stage, setStage] = useState<AppStage>("baseline");
  const [loadPoints, setLoadPoints] = useState<LoadPoint[]>(generateDemoLoad);
  const [files, setFiles] = useState<Record<SourceKind, string>>({
    bill: "synthetic_bill_may.png",
    interval: "synthetic_half_hour.csv",
    label: "synthetic_ac_label.jpg",
  });
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [traceVisible, setTraceVisible] = useState(0);
  const [selectedPlanId, setSelectedPlanId] =
    useState<EnergyPlan["id"]>("balanced");
  const [completedTasks, setCompletedTasks] = useState<number[]>([1, 2, 3]);
  const [comparisonReady, setComparisonReady] = useState(false);
  const [agentMode, setAgentMode] = useState<"demo" | "live">("demo");
  const [toast, setToast] = useState("");

  const sessionId = "homeshift-synthetic-household";
  const patterns = useMemo(() => detectLoadPatterns(loadPoints), [loadPoints]);
  const insights = useMemo(() => buildInsights(loadPoints), [loadPoints]);
  const appliances = useMemo(() => estimateAppliances(demoProfile), []);
  const plans = useMemo(() => generatePlans(demoProfile), []);
  const selectedPlan =
    plans.find((plan) => plan.id === selectedPlanId) ?? plans[1];
  const comparison = compareActualToPlan(
    demoProfile.monthlyKwh,
    383.5,
    selectedPlan,
  );
  const baselineCost = calculateCost(demoProfile.monthlyKwh);
  const baselineCarbon = calculateCarbon(demoProfile.monthlyKwh);
  const progress = Math.round((completedTasks.length / dailyTasks.length) * 100);

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

  async function handleFile(kind: SourceKind, file?: File) {
    if (!file) return;
    setFiles((current) => ({ ...current, [kind]: file.name }));

    if (kind === "interval") {
      try {
        const parsed = parseIntervalCsv(await file.text());
        setLoadPoints(parsed);
        showToast(`Loaded ${parsed.length} interval records`);
      } catch (error) {
        showToast(
          error instanceof Error ? error.message : "Could not read the CSV",
        );
      }
    } else {
      showToast(`${file.name} is ready for analysis`);
    }

    const form = new FormData();
    form.set("file", file);
    form.set("sessionId", sessionId);
    form.set("kind", kind);
    void fetch("/api/uploads", { method: "POST", body: form }).catch(() => {
      // The interactive demo remains usable when local cloud bindings are absent.
    });
  }

  function loadSyntheticDemo() {
    setLoadPoints(generateDemoLoad());
    setFiles({
      bill: "synthetic_bill_may.png",
      interval: "synthetic_half_hour.csv",
      label: "synthetic_ac_label.jpg",
    });
    setStage("baseline");
    setComparisonReady(false);
    setCompletedTasks([1, 2, 3]);
    showToast("Synthetic 4-room household reloaded");
  }

  async function runDiagnosis() {
    if (isAnalyzing) return;
    setIsAnalyzing(true);
    setTraceVisible(0);
    setStage("diagnosis");

    const liveRequest = fetch("/api/agent", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        sessionId,
        profile: demoProfile,
        patterns,
        requestedMode: "negotiate-plans",
      }),
    }).catch(() => null);

    for (let index = 1; index <= agentTrace.length; index += 1) {
      await sleep(230);
      setTraceVisible(index);
    }

    const response = await liveRequest;
    setAgentMode(response?.ok ? "live" : "demo");
    setIsAnalyzing(false);

    void fetch("/api/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        id: sessionId,
        householdName: "Tampines 4-room household",
        profile: demoProfile,
        baseline: { patterns, appliances, insights },
        plans,
        selectedPlan: selectedPlanId,
      }),
    }).catch(() => null);
  }

  function choosePlan(plan: EnergyPlan) {
    setSelectedPlanId(plan.id);
    setStage("track");
    setComparisonReady(false);
    showToast(`${plan.name} plan selected`);
  }

  function toggleTask(day: number) {
    setCompletedTasks((current) =>
      current.includes(day)
        ? current.filter((item) => item !== day)
        : [...current, day].sort(),
    );
  }

  async function verifyAfterData() {
    setComparisonReady(true);
    setCompletedTasks(dailyTasks.map((task) => task.day));
    showToast("Day-7 data verified — next week has been adjusted");

    void fetch("/api/check-in", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        sessionId,
        payload: { completedDays: 7, comfortScore: 4.6 },
        result: comparison,
      }),
    }).catch(() => null);
  }

  function showToast(message: string) {
    setToast(translate(locale, message));
    window.setTimeout(() => setToast(""), 2600);
  }

  return (
    <Localized locale={locale}>
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
              onClick={() => setStage(item.id)}
            >
              <span>{item.step}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="top-actions">
          <span className="demo-pill">
            <Sparkles size={13} />
            Synthetic demo
          </span>
          <button
            className="language-button"
            onClick={() => setLocale((current) => current === "en" ? "zh" : "en")}
            aria-label={locale === "en" ? "切换到中文" : "Switch to English"}
            data-testid="language-toggle"
          >
            <Languages size={15} />
            <span>{locale === "en" ? "中文" : "EN"}</span>
          </button>
          <button className="icon-button" onClick={loadSyntheticDemo} title="Reset demo">
            <RefreshCw size={17} />
          </button>
        </div>
      </header>

      <section className="content-wrap">
        {stage === "baseline" && (
          <BaselineView
            locale={locale}
            loadPoints={loadPoints}
            files={files}
            patterns={patterns}
            baselineCost={baselineCost}
            baselineCarbon={baselineCarbon}
            onFile={handleFile}
            onLoadDemo={loadSyntheticDemo}
            onAnalyze={runDiagnosis}
            isAnalyzing={isAnalyzing}
          />
        )}

        {stage === "diagnosis" && (
          <DiagnosisView
            locale={locale}
            loadPoints={loadPoints}
            insights={insights}
            appliances={appliances}
            traceVisible={traceVisible}
            isAnalyzing={isAnalyzing}
            agentMode={agentMode}
            onContinue={() => setStage("plans")}
          />
        )}

        {stage === "plans" && (
          <PlansView
            locale={locale}
            plans={plans}
            selectedPlanId={selectedPlanId}
            onSelect={setSelectedPlanId}
            onChoose={choosePlan}
          />
        )}

        {stage === "track" && (
          <TrackView
            locale={locale}
            plan={selectedPlan}
            completedTasks={completedTasks}
            progress={progress}
            comparisonReady={comparisonReady}
            comparison={comparison}
            onToggleTask={toggleTask}
            onVerify={verifyAfterData}
          />
        )}
      </section>

      <footer className="site-footer">
        <span>
          <ShieldCheck size={14} />
          Estimates are tool-calculated. No appliance is controlled automatically.
        </span>
        <span>Prototype · Agentic AI in Sustainability</span>
      </footer>

      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={18} />
          {toast}
        </div>
      )}
      </main>
    </Localized>
  );
}

function BaselineView({
  locale,
  loadPoints,
  files,
  patterns,
  baselineCost,
  baselineCarbon,
  onFile,
  onLoadDemo,
  onAnalyze,
  isAnalyzing,
}: {
  locale: Locale;
  loadPoints: LoadPoint[];
  files: Record<SourceKind, string>;
  patterns: ReturnType<typeof detectLoadPatterns>;
  baselineCost: number;
  baselineCarbon: number;
  onFile: (kind: SourceKind, file?: File) => void;
  onLoadDemo: () => void;
  onAnalyze: () => void;
  isAnalyzing: boolean;
}) {
  return (
    <Localized locale={locale}>
      <div className="view-stack">
      <div className="eyebrow-row">
        <span className="eyebrow">HOUSEHOLD ENERGY COPILOT</span>
        <span className="live-dot">
          <span />
          Data ready
        </span>
      </div>

      <section className="hero-grid">
        <div className="hero-copy">
          <p className="kicker">Cut bills, not comfort.</p>
          <h1>
            Turn your energy data into a plan your household will{" "}
            <em>actually follow.</em>
          </h1>
          <p className="hero-description">
            Seven specialist agents diagnose what drives your bill, negotiate
            cost against comfort and carbon, then adapt a practical seven-day
            plan as new data arrives.
          </p>
          <div className="hero-actions">
            <button
              className="primary-button"
              onClick={onAnalyze}
              disabled={isAnalyzing}
              data-testid="run-diagnosis"
            >
              {isAnalyzing ? (
                <LoaderCircle className="spin" size={18} />
              ) : (
                <WandSparkles size={18} />
              )}
              Run 7-agent diagnosis
              <ArrowRight size={17} />
            </button>
            <button className="text-button" onClick={onLoadDemo}>
              Reload synthetic case
            </button>
          </div>
          <div className="trust-row">
            <span>
              <LockKeyhole size={14} /> User-confirmed actions only
            </span>
            <span>
              <Database size={14} /> Deterministic calculations
            </span>
          </div>
        </div>

        <div className="baseline-card">
          <div className="baseline-card-head">
            <div>
              <span className="label">MAY BASELINE</span>
              <h2>Tampines household</h2>
            </div>
            <span className="verified-badge">
              <Check size={13} /> 3 sources
            </span>
          </div>
          <div className="big-metric">
            <span>420</span>
            <div>
              <strong>kWh</strong>
              <small>this month</small>
            </div>
          </div>
          <div className="goal-track" aria-label="10 percent reduction goal">
            <span style={{ width: "70%" }} />
            <i style={{ left: "60%" }}>goal</i>
          </div>
          <div className="mini-metrics">
            <div>
              <span>Est. bill</span>
              <strong>{formatMoney(baselineCost)}</strong>
            </div>
            <div>
              <span>Carbon</span>
              <strong>{baselineCarbon} kg</strong>
            </div>
            <div>
              <span>Target</span>
              <strong>−10%</strong>
            </div>
          </div>
          <div className="home-profile">
            <Home size={17} />
            <span>4-room HDB</span>
            <span>3 residents</span>
            <span>1 WFH</span>
          </div>
        </div>
      </section>

      <section className="data-grid">
        <div className="panel load-panel">
          <div className="panel-heading">
            <div>
              <span className="label">24-HOUR SIGNATURE</span>
              <h2>When the home uses energy</h2>
            </div>
            <span className="signal-chip">
              Peak {patterns.peakTime}
            </span>
          </div>
          <LoadChart points={loadPoints} />
          <div className="chart-notes">
            <span>
              <i className="dot lime" /> Daytime
            </span>
            <span>
              <i className="dot coral" /> Evening opportunity
            </span>
            <span className="chart-summary">
              <MoonStar size={14} />
              Overnight remains above target
            </span>
          </div>
        </div>

        <div className="panel source-panel">
          <div className="panel-heading">
            <div>
              <span className="label">DATA DESK</span>
              <h2>Bring your evidence</h2>
            </div>
            <InfoTooltip text="Demo files are synthetic. Real uploads are stored privately when cloud storage is connected." />
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
                    <strong>{source.title}</strong>
                    <small>{files[kind] || source.description}</small>
                  </span>
                  <span className="upload-state">
                    {files[kind] ? <Check size={15} /> : <Upload size={15} />}
                  </span>
                  <input
                    type="file"
                    accept={source.accept}
                    onChange={(event) => onFile(kind, event.target.files?.[0])}
                  />
                </label>
              );
            })}
          </div>
          <div className="constraint-strip">
            <Thermometer size={17} />
            <div>
              <strong>Comfort rules locked</strong>
              <span>25°C sleep · WFH protected · ≤ S$300</span>
            </div>
            <ChevronRight size={17} />
          </div>
        </div>
      </section>
      </div>
    </Localized>
  );
}

function DiagnosisView({
  locale,
  loadPoints,
  insights,
  appliances,
  traceVisible,
  isAnalyzing,
  agentMode,
  onContinue,
}: {
  locale: Locale;
  loadPoints: LoadPoint[];
  insights: ReturnType<typeof buildInsights>;
  appliances: ReturnType<typeof estimateAppliances>;
  traceVisible: number;
  isAnalyzing: boolean;
  agentMode: "demo" | "live";
  onContinue: () => void;
}) {
  return (
    <Localized locale={locale}>
      <div className="view-stack">
      <PageIntro
        eyebrow="DIAGNOSIS"
        title="The bill is high for"
        accent="three specific reasons."
        description="HomeShift separates measured evidence from estimates, then shows how each specialist reached an actionable conclusion."
        side={
          <span className={`mode-badge ${agentMode}`}>
            {agentMode === "live" ? <Activity size={14} /> : <Database size={14} />}
            {agentMode === "live" ? "Live agent run" : "Transparent demo engine"}
          </span>
        }
      />

      <section className="diagnosis-grid">
        <div className="panel trace-panel">
          <div className="panel-heading">
            <div>
              <span className="label">AGENT WORKLOG</span>
              <h2>Six specialists, one decision</h2>
            </div>
            {isAnalyzing && <LoaderCircle className="spin" size={19} />}
          </div>
          <div className="trace-list">
            {agentTrace.map((entry, index) => {
              const visible = index < traceVisible;
              return (
                <div
                  className={`trace-row ${visible ? "visible" : ""}`}
                  key={entry.agent}
                >
                  <span className="trace-index">
                    {visible ? <Check size={14} /> : index + 1}
                  </span>
                  <div>
                    <strong>{entry.agent}</strong>
                    <span>{entry.task}</span>
                  </div>
                  <p>{visible ? entry.result : "Waiting for upstream evidence"}</p>
                </div>
              );
            })}
          </div>
          <div className="orchestrator-note">
            <Sparkles size={18} />
            <div>
              <strong>Orchestrator decision</strong>
              <span>
                Preserve sleep comfort, avoid purchases in week one, and target
                the evening cooling peak first.
              </span>
            </div>
          </div>
        </div>

        <div className="panel compact-chart-panel">
          <div className="panel-heading">
            <div>
              <span className="label">DETECTIVE VIEW</span>
              <h2>Peak concentration</h2>
            </div>
            <BarChart3 size={19} />
          </div>
          <LoadChart points={loadPoints} compact />
          <div className="peak-callout">
            <Zap size={18} />
            <span>
              <strong>38% cooling share</strong>
              Most addressable after 19:00
            </span>
          </div>
        </div>
      </section>

      <section className="insight-row">
        {insights.map((insight, index) => (
          <article className={`insight-card severity-${insight.severity}`} key={insight.id}>
            <div className="insight-top">
              <span>0{index + 1}</span>
              <strong>{insight.confidence}% confidence</strong>
            </div>
            <h3>{insight.title}</h3>
            <p>{insight.detail}</p>
            <small>
              <Info size={13} />
              {insight.evidence}
            </small>
          </article>
        ))}
      </section>

      <section className="panel appliance-panel">
        <div className="panel-heading">
          <div>
            <span className="label">APPLIANCE AUDIT</span>
            <h2>Estimated monthly contribution</h2>
          </div>
          <span className="estimation-note">Measured + label-informed estimates</span>
        </div>
        <div className="appliance-bars">
          {appliances.map((appliance) => (
            <div className="appliance-item" key={appliance.name}>
              <span>{appliance.name}</span>
              <div>
                <i style={{ width: `${appliance.sharePercent * 1.75}%` }} />
              </div>
              <strong>{appliance.monthlyKwh} kWh</strong>
              <InfoTooltip text={appliance.basis} />
            </div>
          ))}
        </div>
      </section>

      <div className="continue-row">
        <span>
          Diagnosis complete. All three proposed pathways satisfy the S$300
          hard budget limit.
        </span>
        <button
          className="primary-button"
          onClick={onContinue}
          disabled={isAnalyzing}
          data-testid="view-plans"
        >
          Compare three plans
          <ArrowRight size={17} />
        </button>
      </div>
      </div>
    </Localized>
  );
}

function PlansView({
  locale,
  plans,
  selectedPlanId,
  onSelect,
  onChoose,
}: {
  locale: Locale;
  plans: EnergyPlan[];
  selectedPlanId: EnergyPlan["id"];
  onSelect: (id: EnergyPlan["id"]) => void;
  onChoose: (plan: EnergyPlan) => void;
}) {
  return (
    <Localized locale={locale}>
      <div className="view-stack">
      <PageIntro
        eyebrow="NEGOTIATED OPTIONS"
        title="Choose the trade-off,"
        accent="not a generic tip."
        description="Cost, comfort and carbon agents score every measure. Hard constraints are enforced before a plan reaches you."
        side={
          <div className="constraint-badges">
            <span><MoonStar size={13} /> Sleep protected</span>
            <span><CircleDollarSign size={13} /> Under S$300</span>
          </div>
        }
      />

      <section className="plan-grid">
        {plans.map((plan) => {
          const selected = plan.id === selectedPlanId;
          return (
            <article
              className={`plan-card ${selected ? "selected" : ""}`}
              style={{ "--plan-accent": plan.accent } as React.CSSProperties}
              key={plan.id}
              onClick={() => onSelect(plan.id)}
            >
              <div className="plan-card-top">
                <span className="plan-dot" />
                <span className="plan-tag">{plan.shortName}</span>
                {plan.id === "balanced" && (
                  <span className="recommended-tag">
                    <Sparkles size={12} /> Best fit
                  </span>
                )}
              </div>
              <h2>{plan.name}</h2>
              <p>{plan.description}</p>
              <div className="plan-hero-metric">
                <span>−{Math.round((plan.monthlySavingKwh / demoProfile.monthlyKwh) * 100)}%</span>
                <small>monthly energy</small>
              </div>
              <div className="plan-stats">
                <div>
                  <span>Bill saving</span>
                  <strong>{formatMoney(plan.monthlySavingSgd)}<small>/mo</small></strong>
                </div>
                <div>
                  <span>CO₂ avoided</span>
                  <strong>{plan.carbonSavingKg}<small> kg/mo</small></strong>
                </div>
                <div>
                  <span>Comfort</span>
                  <strong>{plan.comfortScore}<small>/100</small></strong>
                </div>
                <div>
                  <span>Upfront</span>
                  <strong>{formatMoney(plan.upfrontCostSgd)}</strong>
                </div>
              </div>
              <div className="action-list">
                {plan.actions.map((action) => (
                  <div key={action.title}>
                    <CheckCircle2 size={16} />
                    <span>
                      <strong>{action.title}</strong>
                      <small>{action.detail}</small>
                    </span>
                  </div>
                ))}
              </div>
              <div className="plan-rationale">
                <Info size={14} />
                <span>{plan.rationale}</span>
              </div>
              <button
                className={selected ? "primary-button" : "outline-button"}
                onClick={(event) => {
                  event.stopPropagation();
                  onChoose(plan);
                }}
                data-testid={`choose-${plan.id}`}
              >
                Choose {plan.name}
                <ArrowRight size={16} />
              </button>
            </article>
          );
        })}
      </section>

      <section className="calculation-strip">
        <div>
          <ShieldCheck size={20} />
          <span>
            <strong>Tool-verified math</strong>
            Tariff: S$0.3478/kWh · Grid factor: 0.402 kg CO₂/kWh
          </span>
        </div>
        <div>
          <Thermometer size={20} />
          <span>
            <strong>Hard constraints</strong>
            No recommendation violates 25°C sleep comfort or WFH availability
          </span>
        </div>
        <div>
          <CloudUpload size={20} />
          <span>
            <strong>Adaptive</strong>
            Week-two actions change when verified performance differs from plan
          </span>
        </div>
      </section>
      </div>
    </Localized>
  );
}

function TrackView({
  locale,
  plan,
  completedTasks,
  progress,
  comparisonReady,
  comparison,
  onToggleTask,
  onVerify,
}: {
  locale: Locale;
  plan: EnergyPlan;
  completedTasks: number[];
  progress: number;
  comparisonReady: boolean;
  comparison: ReturnType<typeof compareActualToPlan>;
  onToggleTask: (day: number) => void;
  onVerify: () => void;
}) {
  return (
    <Localized locale={locale}>
      <div className="view-stack">
      <PageIntro
        eyebrow="ACTION LOOP"
        title="Seven small shifts."
        accent="One measurable result."
        description={`The ${plan.name} pathway turns recommendations into household-sized tasks, then checks the observed data before adapting.`}
        side={
          <div className="progress-orb">
            <span>{progress}%</span>
            <small>week complete</small>
          </div>
        }
      />

      <section className="track-grid">
        <div className="panel task-panel">
          <div className="panel-heading">
            <div>
              <span className="label">WEEK ONE</span>
              <h2>Your action board</h2>
            </div>
            <span className="signal-chip">{completedTasks.length}/7 done</span>
          </div>
          <div className="week-progress">
            <span style={{ width: `${progress}%` }} />
          </div>
          <div className="task-list">
            {dailyTasks.map((task) => {
              const complete = completedTasks.includes(task.day);
              return (
                <button
                  className={`task-row ${complete ? "complete" : ""}`}
                  key={task.day}
                  onClick={() => onToggleTask(task.day)}
                >
                  <span className="task-check">
                    {complete ? <Check size={15} /> : task.day}
                  </span>
                  <span className="task-copy">
                    <strong>{task.title}</strong>
                    <small>{task.detail}</small>
                  </span>
                  <span className="task-impact">
                    {task.impactKwh > 0 ? `−${task.impactKwh} kWh/day` : "Setup"}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="track-side">
          <div className="panel forecast-panel">
            <div className="panel-heading">
              <div>
                <span className="label">LIVE FORECAST</span>
                <h2>On course</h2>
              </div>
              <span className="forecast-icon"><Leaf size={18} /></span>
            </div>
            <div className="forecast-number">
              <span>{plan.monthlySavingKwh}</span>
              <div><strong>kWh</strong><small>planned monthly reduction</small></div>
            </div>
            <div className="forecast-grid">
              <div><span>Bill</span><strong>−{formatMoney(plan.monthlySavingSgd)}</strong></div>
              <div><span>Carbon</span><strong>−{plan.carbonSavingKg} kg</strong></div>
              <div><span>Comfort</span><strong>{plan.comfortScore}/100</strong></div>
            </div>
          </div>

          <div className="panel verify-panel">
            <span className="label">DAY-7 CHECK-IN</span>
            <h2>Close the loop</h2>
            <p>
              Import the preloaded after-data to compare forecast with observed
              performance.
            </p>
            <button
              className="primary-button full-width"
              onClick={onVerify}
              data-testid="verify-after-data"
            >
              <Upload size={17} />
              Verify after-data
            </button>
            <small>
              <FileSpreadsheet size={13} />
              synthetic_week1_after.csv · clearly labelled
            </small>
          </div>
        </div>
      </section>

      {comparisonReady && (
        <section className="result-panel">
          <div className="result-lead">
            <span className="result-check"><Check size={25} /></span>
            <div>
              <span className="label">VERIFIED RESULT</span>
              <h2>{comparison.actualSavingPercent}% less energy observed</h2>
              <p>
                Slightly below the 10% target, with strong comfort compliance.
                The coach keeps the cooling routine and strengthens the plug-load
                reminder next week.
              </p>
            </div>
          </div>
          <div className="result-metrics">
            <div>
              <span>Actual use</span>
              <strong>{comparison.actualMonthlyKwh} kWh</strong>
              <small>420 kWh baseline</small>
            </div>
            <div>
              <span>Bill saved</span>
              <strong>{formatMoney(comparison.actualSavingSgd)}</strong>
              <small>tool calculated</small>
            </div>
            <div>
              <span>CO₂ avoided</span>
              <strong>{comparison.actualCarbonSavingKg} kg</strong>
              <small>grid factor applied</small>
            </div>
            <div>
              <span>Vs. plan</span>
              <strong>{comparison.varianceKwh} kWh</strong>
              <small>adjust next week</small>
            </div>
          </div>
          <div className="adjustment-note">
            <RefreshCw size={17} />
            <span>
              <strong>Plan adjusted:</strong> keep 25°C start temperature; add
              an automatic 00:00 plug reminder on three nights.
            </span>
          </div>
        </section>
      )}
      </div>
    </Localized>
  );
}

function LoadChart({
  points,
  compact = false,
}: {
  points: LoadPoint[];
  compact?: boolean;
}) {
  return (
    <div className={compact ? "chart compact" : "chart"}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={points}
          margin={{ top: 10, right: 8, bottom: 0, left: compact ? -25 : -18 }}
        >
          <defs>
            <linearGradient id="energyFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#c8f547" stopOpacity={0.58} />
              <stop offset="100%" stopColor="#c8f547" stopOpacity={0.04} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#deded8" strokeDasharray="3 6" vertical={false} />
          <XAxis
            dataKey="time"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#777871", fontSize: 11 }}
            interval={compact ? 11 : 7}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#777871", fontSize: 11 }}
            width={38}
          />
          <Tooltip
            cursor={{ stroke: "#1c211c", strokeDasharray: "3 3" }}
            contentStyle={{
              background: "#1c211c",
              border: "none",
              borderRadius: "10px",
              color: "#fff",
              fontSize: "12px",
            }}
            formatter={(value) => [`${Number(value).toFixed(2)} kWh`, "Usage"]}
          />
          <Area
            type="monotone"
            dataKey="kwh"
            stroke="#1c211c"
            strokeWidth={2}
            fill="url(#energyFill)"
            animationDuration={700}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
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
  side: React.ReactNode;
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

function InfoTooltip({ text }: { text: string }) {
  return (
    <span className="info-tooltip" data-tooltip={text} tabIndex={0}>
      <Info size={15} />
    </span>
  );
}

function Localized({
  locale,
  children,
}: {
  locale: Locale;
  children: ReactNode;
}) {
  return <>{localizeNode(children, locale)}</>;
}

function localizeNode(node: ReactNode, locale: Locale): ReactNode {
  if (typeof node === "string") return translate(locale, node);
  if (node === null || node === undefined || typeof node === "boolean") {
    return node;
  }
  if (Array.isArray(node)) {
    return node.map((child) => localizeNode(child, locale));
  }
  if (!isValidElement(node)) return node;

  const props = node.props as Record<string, unknown>;
  const translatedProps: Record<string, unknown> = {};
  const stringProps = [
    "aria-label",
    "title",
    "description",
    "accent",
    "eyebrow",
    "text",
    "data-tooltip",
  ];

  for (const key of stringProps) {
    if (typeof props[key] === "string") {
      translatedProps[key] = translate(locale, props[key]);
    }
  }

  if (props.side !== undefined) {
    translatedProps.side = localizeNode(props.side as ReactNode, locale);
  }
  if (props.children !== undefined) {
    translatedProps.children = Children.map(
      props.children as ReactNode,
      (child) => localizeNode(child, locale),
    );
  }

  return cloneElement(node, translatedProps);
}
