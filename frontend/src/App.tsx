import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Navigate,
  NavLink,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  BrainCircuit,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  CloudSun,
  Database,
  Download,
  FileBarChart,
  Gauge,
  HardDriveUpload,
  Languages,
  Leaf,
  LoaderCircle,
  LockKeyhole,
  Menu,
  MessageSquareText,
  PanelRightOpen,
  Play,
  RefreshCw,
  Route as RouteIcon,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ApiError,
  api,
  localText,
  type AgentRun,
  type Datasets,
  type Providers,
  type Status,
  type Workspace,
} from "./api";
import { type Locale, useCopy } from "./i18n";

const stages = [
  { id: "data", path: "/data", icon: Database },
  { id: "baseline", path: "/baseline", icon: Gauge },
  { id: "diagnosis", path: "/diagnosis", icon: BrainCircuit },
  { id: "plan", path: "/plan", icon: RouteIcon },
  { id: "track", path: "/track", icon: RefreshCw },
] as const;

type StageId = (typeof stages)[number]["id"];
type OperationKind =
  | "import"
  | "profile"
  | "diagnosis"
  | "proposal"
  | "commit"
  | "tracking"
  | "review";
type OperationController = {
  start: (kind: OperationKind) => void;
  finish: () => void;
};

function workflowOf(workspace: Workspace) {
  const workflow = workspace.runtime?.workflow;
  return {
    dataReady: workflow?.data_ready ?? workspace.baseline.available,
    diagnosisCompleted: workflow?.diagnosis_completed ?? false,
    planProposed: workflow?.plan_proposed ?? false,
    planCommitted: workflow?.plan_committed ?? Boolean(workspace.plans.has_committed_plan),
    trackingReady: workflow?.tracking_ready ?? workspace.track.available,
    reviewCompleted: workflow?.review_completed ?? false,
    lastOperation: workflow?.last_operation ?? null,
  };
}

function stageAccess(stage: StageId, workspace: Workspace) {
  const workflow = workflowOf(workspace);
  if (stage === "data") return { unlocked: true, completed: workflow.dataReady, requiredPath: "/data" };
  if (stage === "baseline") return { unlocked: workflow.dataReady, completed: workflow.dataReady, requiredPath: "/data" };
  if (stage === "diagnosis") return { unlocked: workflow.dataReady, completed: workflow.diagnosisCompleted, requiredPath: "/data" };
  if (stage === "plan") return { unlocked: workflow.diagnosisCompleted, completed: workflow.planCommitted, requiredPath: "/diagnosis" };
  return { unlocked: workflow.planCommitted, completed: workflow.trackingReady, requiredPath: "/plan" };
}

function App() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [locale, setLocale] = useState<Locale>(
    () => (localStorage.getItem("homeshift-locale") as Locale) || "zh",
  );
  const [modelOpen, setModelOpen] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [latestRun, setLatestRun] = useState<AgentRun | null>(null);
  const [proposalIds, setProposalIds] = useState<string[]>([]);
  const [navOpen, setNavOpen] = useState(false);
  const [activeOperation, setActiveOperation] = useState<{ kind: OperationKind; startedAt: number } | null>(null);
  const [guideNotice, setGuideNotice] = useState<string | null>(null);
  const copy = useCopy(locale);

  useEffect(() => {
    localStorage.setItem("homeshift-locale", locale);
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [locale]);

  useEffect(() => {
    if (!guideNotice) return;
    const timer = window.setTimeout(() => setGuideNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [guideNotice]);

  const statusQuery = useQuery({ queryKey: ["status"], queryFn: api.status });
  const providersQuery = useQuery({ queryKey: ["providers"], queryFn: api.providers });
  const datasetsQuery = useQuery({ queryKey: ["datasets"], queryFn: api.datasets });
  const workspaceQuery = useQuery({ queryKey: ["workspace"], queryFn: api.workspace });

  const refresh = (workspace?: Workspace) => {
    if (workspace) {
      queryClient.setQueryData(["workspace"], workspace);
      if (!workflowOf(workspace).diagnosisCompleted) {
        setLatestRun(null);
        setProposalIds([]);
      }
    }
    void queryClient.invalidateQueries({ queryKey: ["status"] });
    void queryClient.invalidateQueries({ queryKey: ["workspace"] });
  };

  const acceptRun = (run: AgentRun, workspace?: Workspace) => {
    setLatestRun(run);
    if (run.proposal?.actions) {
      setProposalIds(run.proposal.actions.map((item: { id: string }) => item.id));
    }
    if (workspace) queryClient.setQueryData(["workspace"], workspace);
    refresh();
  };

  if (
    statusQuery.isPending ||
    providersQuery.isPending ||
    datasetsQuery.isPending ||
    workspaceQuery.isPending
  ) {
    return <FullScreenState icon={<LoaderCircle className="spin" />} title="HomeShift AI" detail="正在连接 Python 领域层…" />;
  }

  if (statusQuery.error || providersQuery.error || datasetsQuery.error || workspaceQuery.error) {
    return (
      <FullScreenState
        icon={<AlertTriangle />}
        title="无法连接 HomeShift API"
        detail={errorMessage(statusQuery.error || providersQuery.error || datasetsQuery.error || workspaceQuery.error)}
        action={
          <button className="button dark" onClick={() => window.location.reload()}>
            <RefreshCw size={15} /> 重新连接
          </button>
        }
      />
    );
  }

  const status = statusQuery.data!;
  const workspace = workspaceQuery.data!;
  const workflow = workflowOf(workspace);
  const operation: OperationController = {
    start: (kind) => setActiveOperation({ kind, startedAt: Date.now() }),
    finish: () => setActiveOperation(null),
  };

  const explainLockedStage = (stage: StageId) => {
    const message = stage === "plan"
      ? locale === "zh"
        ? "计划阶段尚未解锁：请先在诊断页完成一次 Agent 分析。"
        : "Plan is locked. Complete an agent diagnosis first."
      : stage === "track"
        ? locale === "zh"
          ? "追踪阶段尚未解锁：请先让 Agent 提案并由你确认正式计划。"
          : "Tracking is locked. Commit an agent-assisted plan first."
        : locale === "zh"
          ? "请先导入或建立一份家庭用电数据。"
          : "Import or create a household dataset first.";
    setGuideNotice(message);
  };

  return (
    <div className="app-shell">
      <Header
        locale={locale}
        setLocale={setLocale}
        status={status}
        onModel={() => setModelOpen(true)}
        onTrace={() => setTraceOpen(true)}
        onChat={() => setChatOpen(true)}
        navOpen={navOpen}
        setNavOpen={setNavOpen}
      />
      <aside className={`stage-rail ${navOpen ? "open" : ""}`}>
        <div className="rail-label">WORKFLOW / 05</div>
        <nav>
          {stages.map((stage, index) => {
            const Icon = stage.icon;
            const access = stageAccess(stage.id, workspace);
            if (!access.unlocked) {
              return (
                <button
                  key={stage.id}
                  type="button"
                  className="stage-link locked"
                  aria-label={`${copy[stage.id]} locked`}
                  onClick={() => {
                    explainLockedStage(stage.id);
                    setNavOpen(false);
                    navigate(access.requiredPath);
                  }}
                >
                  <span className="stage-number">0{index + 1}</span>
                  <Icon size={17} />
                  <strong>{copy[stage.id]}</strong>
                  <LockKeyhole size={13} />
                </button>
              );
            }
            return (
              <NavLink
                key={stage.id}
                to={stage.path}
                onClick={() => setNavOpen(false)}
                className={({ isActive }) => `stage-link ${isActive ? "active" : ""} ${access.completed ? "completed" : ""}`}
              >
                <span className="stage-number">0{index + 1}</span>
                <Icon size={17} />
                <strong>{copy[stage.id]}</strong>
                {access.completed ? <Check size={14} /> : <ChevronRight size={14} />}
              </NavLink>
            );
          })}
        </nav>
        <div className="rail-foot">
          <div className="mini-orbit"><Bot size={18} /></div>
          <p>{locale === "zh" ? "单编排器协调七个专业角色" : "One orchestrator, seven specialists"}</p>
        </div>
      </aside>

      <main className="page-shell">
        <Routes>
          <Route path="/" element={<Navigate to={status.ready ? "/baseline" : "/data"} replace />} />
          <Route
            path="/data"
            element={
              <DataPage
                locale={locale}
                status={status}
                datasets={datasetsQuery.data!}
                workspace={workspace}
                onRefresh={refresh}
                operation={operation}
              />
            }
          />
          <Route
            path="/baseline"
            element={
              <StageGate allowed={workflow.dataReady} locale={locale} requiredPath="/data" requiredStage="data">
                <BaselinePage locale={locale} workspace={workspace} />
              </StageGate>
            }
          />
          <Route
            path="/diagnosis"
            element={
              <DiagnosisPage
                locale={locale}
                workspace={workspace}
                latestRun={latestRun}
                onRun={acceptRun}
                openTrace={() => setTraceOpen(true)}
                operation={operation}
              />
            }
          />
          <Route
            path="/plan"
            element={
              <StageGate allowed={workflow.diagnosisCompleted} locale={locale} requiredPath="/diagnosis" requiredStage="diagnosis">
                <PlanPage
                  locale={locale}
                  workspace={workspace}
                  latestRun={latestRun}
                  proposalIds={proposalIds}
                  setProposalIds={setProposalIds}
                  onRun={acceptRun}
                  onRefresh={refresh}
                  openTrace={() => setTraceOpen(true)}
                  operation={operation}
                />
              </StageGate>
            }
          />
          <Route
            path="/track"
            element={
              <StageGate allowed={workflow.planCommitted} locale={locale} requiredPath="/plan" requiredStage="plan">
                <TrackPage
                  locale={locale}
                  workspace={workspace}
                  latestRun={latestRun}
                  onRun={acceptRun}
                  onRefresh={refresh}
                  openTrace={() => setTraceOpen(true)}
                  operation={operation}
                />
              </StageGate>
            }
          />
          <Route path="*" element={<Navigate to="/data" replace />} />
        </Routes>
      </main>

      <ModelDrawer
        open={modelOpen}
        onClose={() => setModelOpen(false)}
        providers={providersQuery.data!}
        locale={locale}
        onChanged={() => {
          void queryClient.invalidateQueries({ queryKey: ["providers"] });
          void queryClient.invalidateQueries({ queryKey: ["status"] });
        }}
      />
      <TraceDrawer
        open={traceOpen}
        onClose={() => setTraceOpen(false)}
        locale={locale}
        run={latestRun}
        fallbackTrace={workspace.agents.trace}
      />
      <ChatDrawer open={chatOpen} onClose={() => setChatOpen(false)} locale={locale} />
      {guideNotice && <GuideNotice message={guideNotice} onClose={() => setGuideNotice(null)} />}
      {activeOperation && <WorkInProgress operation={activeOperation} locale={locale} />}
    </div>
  );
}

function Header({
  locale,
  setLocale,
  status,
  onModel,
  onTrace,
  onChat,
  navOpen,
  setNavOpen,
}: {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  status: Status;
  onModel: () => void;
  onTrace: () => void;
  onChat: () => void;
  navOpen: boolean;
  setNavOpen: (open: boolean) => void;
}) {
  const copy = useCopy(locale);
  const needsAttention = status.model.kind === "mock" || status.model.explicit === false;
  return (
    <header className="app-header">
      <button className="icon-button mobile-menu" onClick={() => setNavOpen(!navOpen)} aria-label="menu">
        <Menu size={19} />
      </button>
      <div className="brand">
        <span className="brand-mark"><Zap size={18} /></span>
        <div><strong>HomeShift</strong><small>AI / CDS WORKSPACE</small></div>
      </div>
      <div className="context-strip">
        <span className={`status-chip ${status.data.kind === "real" ? "blue" : "lime"}`}>
          <span className="dot" />
          {status.data.kind === "real" ? copy.real : copy.synthetic}
        </span>
        <span><strong>{status.region?.name || "—"}</strong><small>{status.region?.currency || "—"}</small></span>
        <span><strong>{status.plan.active ? `v${status.plan.version}` : "—"}</strong><small>PLAN</small></span>
      </div>
      <div className="header-actions">
        <button className="header-button" onClick={onModel}>
          <Settings2 size={15} />
          <span>{copy.configureModel}</span>
          <i className={needsAttention ? "coral-dot" : "live-dot"} />
        </button>
        <button className="header-button" onClick={onTrace}><PanelRightOpen size={15} /><span>{copy.trace}</span></button>
        <a className="header-button" href={api.reportUrl} target="_blank" rel="noreferrer"><FileBarChart size={15} /><span>{copy.report}</span></a>
        <button className="header-button primary" onClick={onChat}><MessageSquareText size={15} /><span>{copy.chat}</span></button>
        <button
          className="language-button"
          onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
          title="Switch language"
        >
          <Languages size={15} /> {locale === "zh" ? "EN" : "中"}
        </button>
      </div>
    </header>
  );
}

function PageIntro({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <section className="page-intro">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions && <div className="intro-actions">{actions}</div>}
    </section>
  );
}

function DataPage({
  locale,
  status,
  datasets,
  workspace,
  onRefresh,
  operation,
}: {
  locale: Locale;
  status: Status;
  datasets: Datasets;
  workspace: Workspace;
  onRefresh: (workspace?: Workspace) => void;
  operation: OperationController;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [dataset, setDataset] = useState(status.data.dataset || "synthetic");
  const [file, setFile] = useState<File | null>(null);
  const [weather, setWeather] = useState("openmeteo");
  const [windowDays, setWindowDays] = useState(dataset === "synthetic" ? 56 : 63);
  const [timeCol, setTimeCol] = useState("");
  const [valueCol, setValueCol] = useState("");
  const [valueUnit, setValueUnit] = useState("kwh");
  const profileQuery = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const [profileDraft, setProfileDraft] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    if (profileQuery.data?.profile && !profileDraft) {
      setProfileDraft(structuredClone(profileQuery.data.profile));
    }
  }, [profileQuery.data, profileDraft]);

  const importMutation = useMutation({
    onMutate: () => operation.start("import"),
    mutationFn: async () => {
      let confirmed = true;
      if (status.data.available) {
        confirmed = window.confirm(
          locale === "zh"
            ? "导入新家庭会清空当前计划、复盘、长期记忆和 Agent 轨迹。确认继续？"
            : "Importing a new household resets the current plan, reviews, memories and agent trace. Continue?",
        );
      }
      if (!confirmed) throw new ApiError("cancelled", locale === "zh" ? "已取消导入" : "Import cancelled", 0);
      const form = new FormData();
      form.append("dataset", dataset);
      form.append("confirm_reset", String(status.data.available));
      form.append("weather_source", weather);
      form.append("window_days", String(windowDays));
      form.append("value_unit", valueUnit);
      if (timeCol) form.append("time_col", timeCol);
      if (valueCol) form.append("value_col", valueCol);
      if (file) form.append("file", file);
      return api.importDataset(form);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["workspace"], data.workspace);
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
      setProfileDraft(null);
      onRefresh(data.workspace);
      navigate("/baseline");
    },
    onSettled: () => operation.finish(),
  });

  const saveProfileMutation = useMutation({
    onMutate: () => operation.start("profile"),
    mutationFn: () => api.saveProfile(profileDraft || {}),
    onSuccess: (data) => {
      queryClient.setQueryData(["workspace"], data.workspace);
      queryClient.setQueryData(["profile"], { profile: data.profile });
      onRefresh(data.workspace);
    },
    onSettled: () => operation.finish(),
  });

  const selected = datasets.datasets.find((item) => item.id === dataset);
  const needsFile = selected?.manual;
  const provenance = workspace.meta.provenance;

  return (
    <>
      <PageIntro
        eyebrow="01 / DATA DESK"
        title={locale === "zh" ? "接入一个家庭，建立可信基线。" : "Connect one home. Build a trustworthy baseline."}
        description={locale === "zh"
          ? "选择公开数据、SP Group 导出、通用 CSV 或合成案例。列映射、单位换算、天气与质量判断全部由 Python 后端完成。"
          : "Choose a registered dataset, SP Group export, generic CSV or synthetic case. Python owns mapping, units, weather and quality."}
      />

      <section className="source-grid">
        {datasets.datasets.map((source) => (
          <button
            key={source.id}
            className={`source-card ${dataset === source.id ? "selected" : ""}`}
            onClick={() => {
              setDataset(source.id);
              setWindowDays(source.id === "synthetic" ? 56 : 63);
              setFile(null);
            }}
          >
            <span className="source-icon">
              {source.id === "synthetic" ? <Sparkles /> : source.manual ? <Upload /> : <Download />}
            </span>
            <small>{source.id.toUpperCase()}</small>
            <strong>{source.title}</strong>
            <p>{source.short}</p>
            <div className="source-meta">
              <span>{source.raw_resolution_minutes ? `${source.raw_resolution_minutes} min` : "AUTO"}</span>
              <span>{source.license || "—"}</span>
            </div>
            {dataset === source.id && <CheckCircle2 className="selected-check" size={19} />}
          </button>
        ))}
      </section>

      <section className="workbench two-column">
        <div className="panel">
          <PanelTitle icon={<HardDriveUpload />} label="IMPORT CONFIGURATION" title={locale === "zh" ? "导入与列映射" : "Import & mapping"} />
          <div className="form-grid">
            {needsFile && (
              <label className="file-drop wide">
                <Upload size={24} />
                <strong>{file ? file.name : locale === "zh" ? "选择 CSV 文件" : "Choose CSV file"}</strong>
                <span>{locale === "zh" ? "文件只发送到本地 FastAPI" : "Sent only to local FastAPI"}</span>
                <input type="file" accept=".csv,.txt" onChange={(event) => setFile(event.target.files?.[0] || null)} />
              </label>
            )}
            <Field label={locale === "zh" ? "窗口天数" : "Window days"}>
              <input type="number" min={7} max={365} value={windowDays} onChange={(event) => setWindowDays(Number(event.target.value))} />
            </Field>
            <Field label={locale === "zh" ? "天气来源" : "Weather source"}>
              <select value={weather} onChange={(event) => setWeather(event.target.value)}>
                <option value="openmeteo">Open-Meteo</option>
                <option value="datagovsg">data.gov.sg</option>
                <option value="none">{locale === "zh" ? "不使用天气" : "No weather"}</option>
              </select>
            </Field>
            {needsFile && (
              <>
                <Field label={locale === "zh" ? "时间列（留空自动）" : "Time column (auto)"}>
                  <input value={timeCol} onChange={(event) => setTimeCol(event.target.value)} placeholder="timestamp" />
                </Field>
                <Field label={locale === "zh" ? "用电列（留空自动）" : "Energy column (auto)"}>
                  <input value={valueCol} onChange={(event) => setValueCol(event.target.value)} placeholder="kwh" />
                </Field>
                <Field label={locale === "zh" ? "原始单位" : "Source unit"}>
                  <select value={valueUnit} onChange={(event) => setValueUnit(event.target.value)}>
                    <option value="kwh">kWh / interval</option>
                    <option value="wh">Wh / interval</option>
                    <option value="kw">kW power</option>
                    <option value="w">W power</option>
                  </select>
                </Field>
              </>
            )}
          </div>
          {selected?.recommended_for && <div className="info-strip"><Sparkles size={15} /><span>{selected.recommended_for}</span></div>}
          {importMutation.error && <ErrorBanner error={importMutation.error} />}
          <button
            className="button dark wide-button"
            disabled={importMutation.isPending || (!!needsFile && !file)}
            onClick={() => importMutation.mutate()}
          >
            {importMutation.isPending ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />}
            {locale === "zh" ? "导入并建立当前工作空间" : "Import into current workspace"}
          </button>
        </div>

        <div className="panel provenance-panel">
          <PanelTitle icon={<ShieldCheck />} label="PROVENANCE" title={locale === "zh" ? "出处与质量" : "Provenance & quality"} />
          {status.data.available ? (
            <>
              <div className="provenance-hero">
                <span className={`data-orb ${workspace.meta.data_kind}`}><Database /></span>
                <div>
                  <small>{localText(workspace.meta.data_badge, locale)}</small>
                  <strong>{provenance?.dataset?.title || status.data.dataset || "Current dataset"}</strong>
                  <p>{status.data.start} → {status.data.end}</p>
                </div>
              </div>
              <div className="quality-list">
                <Quality label={locale === "zh" ? "地区" : "Region"} value={workspace.meta.region.name || "—"} />
                <Quality label={locale === "zh" ? "币种" : "Currency"} value={workspace.meta.currency.code} />
                <Quality label={locale === "zh" ? "天气" : "Weather"} value={provenance?.weather?.source || "—"} />
                <Quality label={locale === "zh" ? "完整度" : "Completeness"} value={`${provenance?.window?.completeness_pct ?? "—"}%`} />
              </div>
              {(provenance?.known_limitations || []).map((item: string) => (
                <p className="limitation" key={item}><AlertTriangle size={14} />{item}</p>
              ))}
            </>
          ) : (
            <EmptyMini icon={<Database />} text={locale === "zh" ? "导入后在这里显示数据出处、完整度与已知局限。" : "Provenance, quality and limitations appear after import."} />
          )}
        </div>
      </section>

      {status.data.available && profileDraft && (
        <section className="panel profile-panel">
          <PanelTitle icon={<Settings2 />} label="HOUSEHOLD PROFILE" title={locale === "zh" ? "审核后端推断的家庭画像" : "Review the inferred household profile"} />
          <p className="section-lede">
            {locale === "zh"
              ? "观察值保留原始证据；下面只编辑家庭自述、生活模式、目标和舒适硬约束。"
              : "Observed evidence stays intact. Edit only household context, routines, goals and comfort constraints."}
          </p>
          <div className="form-grid profile-form">
            <Field label={locale === "zh" ? "住宅类型" : "Home type"}>
              <input value={profileDraft.home_type || ""} onChange={(e) => setProfileDraft({ ...profileDraft, home_type: e.target.value })} />
            </Field>
            <Field label={locale === "zh" ? "地区" : "Location"}>
              <input value={profileDraft.location || ""} onChange={(e) => setProfileDraft({ ...profileDraft, location: e.target.value })} />
            </Field>
            <Field label={locale === "zh" ? "当前空调温度" : "Current AC setpoint"}>
              <input type="number" value={profileDraft.ac_setpoint ?? 24} onChange={(e) => setProfileDraft({ ...profileDraft, ac_setpoint: Number(e.target.value) })} />
            </Field>
            <Field label={locale === "zh" ? "可接受最高温度" : "Maximum comfortable setpoint"}>
              <input
                type="number"
                value={profileDraft.comfort_preferences?.max_ac_setpoint ?? 26}
                onChange={(e) => setProfileDraft({
                  ...profileDraft,
                  comfort_preferences: { ...profileDraft.comfort_preferences, max_ac_setpoint: Number(e.target.value) },
                })}
              />
            </Field>
            <Field label={locale === "zh" ? "热水模式" : "Water heating"}>
              <select value={profileDraft.heater_mode || "unknown"} onChange={(e) => setProfileDraft({ ...profileDraft, heater_mode: e.target.value })}>
                <option value="always_on">Always on</option>
                <option value="timed">Timed</option>
                <option value="unknown">Unknown</option>
              </select>
            </Field>
            <Field label={locale === "zh" ? "洗衣模式" : "Wash mode"}>
              <select value={profileDraft.wash_mode || "warm"} onChange={(e) => setProfileDraft({ ...profileDraft, wash_mode: e.target.value })}>
                <option value="warm">Warm</option>
                <option value="cold">Cold</option>
              </select>
            </Field>
            <Field label={locale === "zh" ? "节省目标 %" : "Saving target %"}>
              <input
                type="number"
                value={profileDraft.goals?.monthly_saving_target_pct ?? 10}
                onChange={(e) => setProfileDraft({
                  ...profileDraft,
                  goals: { ...profileDraft.goals, monthly_saving_target_pct: Number(e.target.value) },
                })}
              />
            </Field>
            <Field label={locale === "zh" ? "目标优先级" : "Priority"}>
              <input
                value={profileDraft.goals?.priority || ""}
                onChange={(e) => setProfileDraft({ ...profileDraft, goals: { ...profileDraft.goals, priority: e.target.value } })}
              />
            </Field>
            <Field label={locale === "zh" ? "家庭与作息" : "Household & routine"} wide>
              <textarea value={profileDraft.household || ""} onChange={(e) => setProfileDraft({ ...profileDraft, household: e.target.value })} />
            </Field>
            <Field label={locale === "zh" ? "舒适规则说明" : "Comfort rule notes"} wide>
              <textarea
                value={profileDraft.comfort_preferences?.notes || ""}
                onChange={(e) => setProfileDraft({
                  ...profileDraft,
                  comfort_preferences: { ...profileDraft.comfort_preferences, notes: e.target.value },
                })}
              />
            </Field>
          </div>
          {saveProfileMutation.error && <ErrorBanner error={saveProfileMutation.error} />}
          <div className="panel-actions">
            <span><LockKeyhole size={14} /> {locale === "zh" ? "舒适规则将作为硬约束" : "Comfort rules become hard constraints"}</span>
            <button className="button lime" onClick={() => saveProfileMutation.mutate()} disabled={saveProfileMutation.isPending}>
              {saveProfileMutation.isPending ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />}
              {locale === "zh" ? "确认画像" : "Confirm profile"}
            </button>
          </div>
        </section>
      )}
    </>
  );
}

function BaselinePage({ locale, workspace }: { locale: Locale; workspace: Workspace }) {
  if (!workspace.baseline.available || !workspace.baseline.headline) return <NoData locale={locale} />;
  const baseline = workspace.baseline;
  const headline = baseline.headline!;
  const signature = baseline.signature_24h?.slots || [];
  const daily = baseline.daily_series || [];
  return (
    <>
      <PageIntro
        eyebrow="02 / BASELINE"
        title={locale === "zh" ? "先看清每一度电去了哪里。" : "See the load before changing it."}
        description={localText(workspace.household.profile_origin, locale)}
        actions={<DataBadge workspace={workspace} locale={locale} />}
      />
      <AnalysisStateBanner locale={locale} complete kind="baseline" />
      <section className="metric-grid">
        <Metric icon={<Zap />} label={locale === "zh" ? "折算月用电" : "Monthly energy"} value={headline.kwh_this_month.display} accent="lime" />
        <Metric icon={<Gauge />} label={locale === "zh" ? "日均用电" : "Daily average"} value={headline.avg_daily_kwh.display} />
        <Metric icon={<CircleDollarSign />} label={locale === "zh" ? "预计账单" : "Projected bill"} value={headline.est_bill.display} accent="coral" />
        <Metric icon={<Leaf />} label={locale === "zh" ? "折算碳排" : "Carbon"} value={headline.carbon_kg.display} accent="blue" />
      </section>
      <section className="chart-grid">
        <div className="panel chart-panel wide-chart">
          <PanelTitle icon={<Zap />} label="24-HOUR SIGNATURE" title={locale === "zh" ? "48 时段平均曲线" : "Average 48-slot signature"} />
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={signature}>
                <defs>
                  <linearGradient id="limeFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#c8f547" stopOpacity={0.55} />
                    <stop offset="100%" stopColor="#c8f547" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="#dddcd3" />
                <XAxis dataKey="time" interval={7} tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} unit=" kWh" width={64} />
                <Tooltip contentStyle={tooltipStyle} formatter={(value) => [`${value} kWh`, locale === "zh" ? "半小时均值" : "Half-hour avg"]} />
                <Area type="monotone" dataKey="kwh" stroke="#1c211c" strokeWidth={2.5} fill="url(#limeFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="band-notes">
            {(baseline.signature_24h?.bands || []).map((band: any) => (
              <div key={band.id}><small>{localText(band.label, locale)} · {band.start}—{band.end}</small><p>{localText(band.note, locale)}</p></div>
            ))}
          </div>
        </div>
        <div className="panel chart-panel">
          <PanelTitle icon={<CloudSun />} label="DAILY + WEATHER" title={locale === "zh" ? "逐日用电与气温" : "Daily energy & temperature"} />
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={daily}>
                <CartesianGrid vertical={false} stroke="#dddcd3" />
                <XAxis dataKey="date" interval="preserveStartEnd" tickLine={false} axisLine={false} tickFormatter={(v) => v.slice(5)} />
                <YAxis yAxisId="energy" tickLine={false} axisLine={false} />
                <YAxis yAxisId="temp" orientation="right" tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar yAxisId="energy" dataKey="kwh" fill="#6f8cff" radius={[4, 4, 0, 0]} />
                <Line yAxisId="temp" type="monotone" dataKey="temp_c" stroke="#ff7b57" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>
      <section className="evidence-grid">
        <div className="panel evidence-panel">
          <PanelTitle icon={<FileBarChart />} label="DATA EVIDENCE" title={locale === "zh" ? "证据文件" : "Evidence files"} />
          {(baseline.evidence || []).map((item: any) => (
            <div className="evidence-row" key={item.file}>
              <span className={item.available ? "evidence-status ok" : "evidence-status"}>{item.available ? <Check size={13} /> : <X size={13} />}</span>
              <div><strong>{localText(item.label, locale)}</strong><small>{item.file}</small></div>
              <span>{item.rows ? `${item.rows.toLocaleString()} rows` : "—"}</span>
            </div>
          ))}
        </div>
        <div className="panel household-card">
          <span className="eyebrow">CURRENT HOUSEHOLD</span>
          <h2>{localText(workspace.household.name, locale)}</h2>
          <p>{localText(workspace.household.summary, locale)}</p>
          <div className="tag-row">{workspace.household.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
          <div className="goal-block"><small>{locale === "zh" ? "当前目标" : "Current goal"}</small><strong>{workspace.household.goal?.display || "—"}</strong><p>{workspace.household.goal?.priority}</p></div>
        </div>
      </section>
    </>
  );
}

function DiagnosisPage({
  locale,
  workspace,
  latestRun,
  onRun,
  openTrace,
  operation,
}: {
  locale: Locale;
  workspace: Workspace;
  latestRun: AgentRun | null;
  onRun: (run: AgentRun, workspace?: Workspace) => void;
  openTrace: () => void;
  operation: OperationController;
}) {
  const workflow = workflowOf(workspace);
  const diagnosisRun = latestRun?.operation === "diagnose" ? latestRun : null;
  const mutation = useMutation({
    onMutate: () => operation.start("diagnosis"),
    mutationFn: () => api.diagnose(locale),
    onSuccess: (data) => onRun(data.run, data.workspace),
    onSettled: () => operation.finish(),
  });
  if (!workspace.diagnosis.available) return <NoData locale={locale} />;
  const diagnosis = workspace.diagnosis;
  return (
    <>
      <PageIntro
        eyebrow="03 / DIAGNOSIS"
        title={locale === "zh" ? "确定性诊断，Agent 负责解释与协商。" : "Deterministic diagnosis. Agent reasoning on top."}
        description={locale === "zh"
          ? "NILM、金额、碳排与候选节省由 Python 工具计算；模型读取摘要与证据，不接触完整 CSV。"
          : "Python computes NILM, cost, carbon and candidate savings. The model sees summaries and evidence, not the full CSV."}
        actions={
          <button className="button lime" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? <LoaderCircle className="spin" size={16} /> : <BrainCircuit size={16} />}
            {locale === "zh" ? "运行本次 Agent 诊断" : "Run agent diagnosis"}
          </button>
        }
      />
      {mutation.error && <ErrorBanner error={mutation.error} />}
      <AnalysisStateBanner
        locale={locale}
        complete={workflow.diagnosisCompleted}
        pending={mutation.isPending}
        kind="diagnosis"
        traceCount={diagnosisRun?.trace.length || (workflow.lastOperation === "diagnosis" ? workspace.agents.trace.length : 0)}
      />
      {diagnosisRun?.mode === "mock" && <MockBanner locale={locale} />}
      <section className="diagnosis-layout">
        <div className="panel">
          <PanelTitle icon={<Gauge />} label={`NILM / ${diagnosis.days || 28} DAYS`} title={locale === "zh" ? "六类负载分解" : "Six-category disaggregation"} />
          <div className="category-list">
            {(diagnosis.categories || []).map((category: any) => (
              <div className="category-row" key={category.id}>
                <div className={`category-rank rank-${category.rank}`}>{String(category.rank).padStart(2, "0")}</div>
                <div className="category-main">
                  <div><strong>{localText(category.label, locale)}</strong><span>{category.cost_per_month.display} / mo</span></div>
                  <div className="progress-track"><span style={{ width: `${Math.min(category.share_pct, 100)}%` }} /></div>
                  <small>{category.kwh_per_month} kWh/mo · {category.co2_kg_per_month} kg CO₂</small>
                </div>
                <strong className="share">{category.share_pct}%</strong>
              </div>
            ))}
          </div>
          <div className="method-note">
            <ShieldCheck size={17} />
            <div><strong>{localText(diagnosis.method?.name, locale)}</strong><p>{locale === "zh" ? "这是从总表推断的估算，不是分表测量。" : "This is inferred from the main meter, not directly sub-metered."}</p></div>
          </div>
        </div>
        <div className="right-stack">
          <div className="panel">
            <PanelTitle icon={<Sparkles />} label="TOP FINDINGS" title={locale === "zh" ? "前三项证据发现" : "Top evidence-backed findings"} />
            <div className="findings-list">
              {(diagnosis.findings || []).map((finding: any, index: number) => (
                <article key={finding.id}>
                  <span>0{index + 1}</span>
                  <div><strong>{localText(finding.title, locale)}</strong><p>{finding.metric?.kwh_per_day} kWh/day · {finding.metric?.cost_per_month?.display}/mo</p></div>
                </article>
              ))}
            </div>
          </div>
          <AccuracyCard accuracy={diagnosis.accuracy} locale={locale} />
        </div>
      </section>
      <AgentSection
        workspace={workspace}
        locale={locale}
        latestRun={diagnosisRun}
        openTrace={openTrace}
        fallbackEnabled={workflow.lastOperation === "diagnosis"}
      />
      {diagnosisRun && (
        <AgentMemo run={diagnosisRun} locale={locale} />
      )}
    </>
  );
}

function PlanPage({
  locale,
  workspace,
  latestRun,
  proposalIds,
  setProposalIds,
  onRun,
  onRefresh,
  openTrace,
  operation,
}: {
  locale: Locale;
  workspace: Workspace;
  latestRun: AgentRun | null;
  proposalIds: string[];
  setProposalIds: (ids: string[]) => void;
  onRun: (run: AgentRun, workspace?: Workspace) => void;
  onRefresh: (workspace?: Workspace) => void;
  openTrace: () => void;
  operation: OperationController;
}) {
  const workflow = workflowOf(workspace);
  const proposalRun = latestRun?.operation === "plan_proposal" ? latestRun : null;
  const candidates = workspace.plans.candidates || [];
  const committedSelectionKey = candidates
    .filter((item: any) => item.selected)
    .map((item: any) => item.id)
    .join("|");
  const [selectedIds, setSelectedIds] = useState<string[]>(proposalIds);
  const [rationale, setRationale] = useState("");
  useEffect(() => {
    if (proposalIds.length) {
      setSelectedIds(proposalIds);
    } else if (workspace.plans.has_committed_plan) {
      setSelectedIds(committedSelectionKey ? committedSelectionKey.split("|") : []);
    }
  }, [proposalIds, workspace.plans.has_committed_plan, workspace.plans.version, committedSelectionKey]);
  const propose = useMutation({
    onMutate: () => operation.start("proposal"),
    mutationFn: () => api.propose(locale),
    onSuccess: (data) => {
      const ids = (data.run.proposal?.actions || []).map((item: { id: string }) => item.id);
      setProposalIds(ids);
      setSelectedIds(ids);
      setRationale(data.run.proposal?.rationale || "");
      onRun(data.run, data.workspace);
    },
    onSettled: () => operation.finish(),
  });
  const commit = useMutation({
    onMutate: () => operation.start("commit"),
    mutationFn: () => api.commit(selectedIds, rationale || (locale === "zh" ? "用户在 Web 界面确认的动作组合" : "Actions confirmed by the user in the Web interface")),
    onSuccess: (data) => onRefresh(data.workspace),
    onSettled: () => operation.finish(),
  });
  if (!workspace.plans.available) return <NoData locale={locale} />;
  const plans = workspace.plans;
  return (
    <>
      <PageIntro
        eyebrow="04 / PLAN"
        title={locale === "zh" ? "不制造三套方案，只选择值得执行的动作。" : "No artificial packages. Choose actions worth doing."}
        description={locale === "zh"
          ? "Agent 提交建议，Comfort Guardian 审查硬约束；你可以增删动作，确认后才产生正式计划版本。"
          : "The agent proposes, Comfort Guardian enforces hard constraints, and only your confirmation creates a plan version."}
        actions={
          <button className="button lime" onClick={() => propose.mutate()} disabled={propose.isPending}>
            {propose.isPending ? <LoaderCircle className="spin" size={16} /> : <BrainCircuit size={16} />}
            {locale === "zh" ? "让 Agent 提出建议" : "Ask agent to propose"}
          </button>
        }
      />
      {propose.error && <ErrorBanner error={propose.error} />}
      {commit.error && <ErrorBanner error={commit.error} />}
      <AnalysisStateBanner
        locale={locale}
        complete={proposalIds.length > 0}
        pending={propose.isPending}
        kind="proposal"
        traceCount={proposalRun?.trace.length || (workflow.lastOperation === "plan_proposal" ? workspace.agents.trace.length : 0)}
      />
      {proposalRun?.mode === "mock" && <MockBanner locale={locale} />}
      <section className="plan-summary-strip">
        <div><small>{locale === "zh" ? "全部可行潜力" : "Feasible potential"}</small><strong>{plans.potential_per_month?.kwh ?? "—"} kWh</strong></div>
        <div><small>{locale === "zh" ? "金额" : "Cost"}</small><strong>{plans.potential_per_month?.cost?.display || "—"}</strong></div>
        <div><small>CO₂</small><strong>{plans.potential_per_month?.co2_kg ?? "—"} kg</strong></div>
        <div><small>{locale === "zh" ? "正式版本" : "Committed version"}</small><strong>{plans.has_committed_plan ? `v${plans.version}` : locale === "zh" ? "尚未提交" : "Not committed"}</strong></div>
      </section>
      <section className="plan-cards">
        {candidates.map((action: any) => {
          const selected = selectedIds.includes(action.id);
          return (
            <article className={`action-card ${selected ? "selected" : ""} ${proposalIds.length ? "" : "awaiting-proposal"}`} key={action.id}>
              <button
                className="action-select"
                disabled={!proposalIds.length}
                onClick={() => setSelectedIds(selected
                  ? selectedIds.filter((id) => id !== action.id)
                  : [...selectedIds, action.id])}
                aria-label={`select ${action.id}`}
              >
                {selected ? <Check size={15} /> : <span />}
              </button>
              <div className="action-top">
                <span className="category-pill">{action.category}</span>
                <span className="effort-pill">{localText(action.effort.label, locale)}</span>
              </div>
              <h3>{localText(action.title, locale)}</h3>
              <p>{localText(action.description, locale)}</p>
              <div className="action-metrics">
                <span><Zap size={14} /><strong>{action.savings.kwh_per_month}</strong><small>kWh/mo</small></span>
                <span><CircleDollarSign size={14} /><strong>{action.savings.cost_per_month.display}</strong><small>/mo</small></span>
                <span><Leaf size={14} /><strong>{action.savings.co2_kg_per_month}</strong><small>kg CO₂</small></span>
              </div>
              <div className="comfort-line"><ShieldCheck size={15} /><span>{locale === "zh" ? "舒适影响" : "Comfort"} · {localText(action.comfort_impact.label, locale)}</span></div>
            </article>
          );
        })}
      </section>
      {(plans.vetoed_by_comfort || []).length > 0 && (
        <section className="veto-panel">
          <div className="veto-heading"><ShieldCheck /><div><span className="eyebrow">COMFORT GUARDIAN VETO</span><h2>{locale === "zh" ? "主动放弃的收益" : "Savings deliberately declined"}</h2></div></div>
          {(plans.vetoed_by_comfort || []).map((action: any) => (
            <div className="veto-row" key={action.id}>
              <X size={16} />
              <div><strong>{localText(action.title, locale)}</strong><p>{action.comfort_verdict?.reason || action.notes}</p></div>
              <span>{action.savings.cost_per_month.display}/mo</span>
            </div>
          ))}
        </section>
      )}
      <section className="commit-panel">
        <div>
          <span className="eyebrow">USER CONFIRMATION GATE</span>
          <h2>{locale === "zh" ? `确认 ${selectedIds.length} 项动作` : `Confirm ${selectedIds.length} actions`}</h2>
          <p>{locale === "zh" ? "此按钮是唯一会写入正式计划版本的入口。" : "This is the only action that persists an active plan version."}</p>
          {!proposalIds.length && <p className="gate-hint"><LockKeyhole size={12} />{locale === "zh" ? "先运行上方 Agent 提案，才可选择并提交动作。" : "Run the agent proposal before selecting and committing actions."}</p>}
        </div>
        <textarea
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          placeholder={locale === "zh" ? "为什么选择这组动作（可编辑）" : "Why this action set (editable)"}
        />
        <button className="button lime" disabled={!proposalIds.length || !selectedIds.length || commit.isPending} onClick={() => commit.mutate()}>
          {commit.isPending ? <LoaderCircle className="spin" size={16} /> : <LockKeyhole size={16} />}
          {locale === "zh" ? "确认并提交正式计划" : "Confirm & commit plan"}
        </button>
      </section>
      {plans.has_committed_plan && <Schedule schedule={plans.seven_day_schedule || []} locale={locale} version={plans.version} />}
      <AgentSection
        workspace={workspace}
        locale={locale}
        latestRun={proposalRun}
        openTrace={openTrace}
        compact
        fallbackEnabled={workflow.lastOperation === "plan_proposal"}
      />
      {proposalRun?.proposal && <AgentMemo run={proposalRun} locale={locale} />}
    </>
  );
}

function TrackPage({
  locale,
  workspace,
  latestRun,
  onRun,
  onRefresh,
  openTrace,
  operation,
}: {
  locale: Locale;
  workspace: Workspace;
  latestRun: AgentRun | null;
  onRun: (run: AgentRun, workspace?: Workspace) => void;
  onRefresh: (workspace?: Workspace) => void;
  openTrace: () => void;
  operation: OperationController;
}) {
  const workflow = workflowOf(workspace);
  const reviewRun = latestRun?.operation === "review" ? latestRun : null;
  const [adherence, setAdherence] = useState(85);
  const [trackingFile, setTrackingFile] = useState<File | null>(null);
  const simulate = useMutation({
    onMutate: () => operation.start("tracking"),
    mutationFn: () => api.simulateWeek(adherence / 100),
    onSuccess: (data) => onRefresh(data.workspace),
    onSettled: () => operation.finish(),
  });
  const upload = useMutation({
    onMutate: () => operation.start("tracking"),
    mutationFn: () => {
      if (!trackingFile) throw new ApiError("invalid_input", "请选择实施后 CSV", 422);
      const form = new FormData();
      form.append("file", trackingFile);
      form.append("value_unit", "kwh");
      form.append("weather_source", "openmeteo");
      return api.importTracking(form);
    },
    onSuccess: (data) => onRefresh(data.workspace),
    onSettled: () => operation.finish(),
  });
  const review = useMutation({
    onMutate: () => operation.start("review"),
    mutationFn: () => api.review(locale),
    onSuccess: (data) => onRun(data.run, data.workspace),
    onSettled: () => operation.finish(),
  });
  if (!workspace.plans.has_committed_plan) {
    return (
      <>
        <PageIntro eyebrow="05 / TRACK" title={locale === "zh" ? "追踪从一份正式计划开始。" : "Tracking starts with a committed plan."} description={locale === "zh" ? "先在计划页选择动作并确认提交。" : "Choose actions and confirm them on the Plan page first."} />
        <EmptyState icon={<RouteIcon />} title={locale === "zh" ? "尚无正式计划" : "No committed plan"} action={<NavLink className="button lime" to="/plan">{locale === "zh" ? "前往计划" : "Go to plan"}<ArrowRight size={15} /></NavLink>} />
      </>
    );
  }
  const track = workspace.track;
  const trackingKind = workspace.runtime?.tracking?.kind;
  return (
    <>
      <PageIntro
        eyebrow="05 / TRACK + MEMORY"
        title={locale === "zh" ? "验证行动，而不是相信预测。" : "Verify action. Do not merely trust forecasts."}
        description={locale === "zh"
          ? "模拟快进与真实实施后数据是两条明确分开的路径；复盘使用天气归一化，并把可靠结论写入长期记忆。"
          : "Synthetic fast-forward and real post-plan data stay visibly separate. Review is weather-normalized and stores durable insights."}
        actions={
          <button className="button dark" onClick={() => review.mutate()} disabled={!track.available || review.isPending}>
            {review.isPending ? <LoaderCircle className="spin" size={16} /> : <BrainCircuit size={16} />}
            {locale === "zh" ? "运行复盘 Agent" : "Run review agent"}
          </button>
        }
      />
      {trackingKind === "synthetic" && <MockDataBanner locale={locale} />}
      {[simulate.error, upload.error, review.error].filter(Boolean).map((error, index) => <ErrorBanner error={error} key={index} />)}
      <AnalysisStateBanner
        locale={locale}
        complete={workflow.trackingReady}
        pending={simulate.isPending || upload.isPending}
        kind="tracking"
      />
      {workflow.trackingReady && (
        <AnalysisStateBanner
          locale={locale}
          complete={workflow.reviewCompleted}
          pending={review.isPending}
          kind="review"
          traceCount={reviewRun?.trace.length || (workflow.lastOperation === "review" ? workspace.agents.trace.length : 0)}
        />
      )}
      <section className="tracking-entry-grid">
        <div className="panel fast-forward">
          <PanelTitle icon={<Play />} label="DEMO FAST-FORWARD" title={locale === "zh" ? "演示快进一周" : "Fast-forward one week"} />
          <p>{locale === "zh" ? "根据正式计划生成七天实施后合成读数。该标记永久保留，不会伪装成实测。" : "Generate seven synthetic post-plan days. The synthetic marker never disappears."}</p>
          <label className="range-field">
            <span>{locale === "zh" ? "执行依从度" : "Adherence"} <strong>{adherence}%</strong></span>
            <input type="range" min={0} max={100} value={adherence} onChange={(event) => setAdherence(Number(event.target.value))} />
          </label>
          <button className="button coral" onClick={() => simulate.mutate()} disabled={simulate.isPending}>
            {simulate.isPending ? <LoaderCircle className="spin" size={15} /> : <Play size={15} />}
            {locale === "zh" ? "生成合成实施后数据" : "Generate synthetic after-data"}
          </button>
        </div>
        <div className="panel actual-upload">
          <PanelTitle icon={<Upload />} label="ACTUAL AFTER-DATA" title={locale === "zh" ? "上传真实实施后 CSV" : "Upload real post-plan CSV"} />
          <p>{locale === "zh" ? "时间必须晚于当前基线及已有数据；后端以追加模式写入，不覆盖计划版本。" : "Timestamps must follow existing data. Python appends without overwriting the plan version."}</p>
          <label className="compact-file">
            <Upload size={19} /><span>{trackingFile?.name || (locale === "zh" ? "选择半小时 kWh CSV" : "Choose half-hour kWh CSV")}</span>
            <input type="file" accept=".csv" onChange={(event) => setTrackingFile(event.target.files?.[0] || null)} />
          </label>
          <button className="button outline" onClick={() => upload.mutate()} disabled={!trackingFile || upload.isPending}>
            {upload.isPending ? <LoaderCircle className="spin" size={15} /> : <Upload size={15} />}
            {locale === "zh" ? "追加真实数据" : "Append real data"}
          </button>
        </div>
      </section>
      {track.available ? (
        <>
          <section className="metric-grid">
            <Metric icon={<Zap />} label={locale === "zh" ? "月度节省投影" : "Monthly saving"} value={`${track.saving?.kwh_per_month} kWh`} accent="lime" />
            <Metric icon={<CircleDollarSign />} label={locale === "zh" ? "金额节省" : "Cost saving"} value={track.saving?.cost_per_month?.display || "—"} accent="coral" />
            <Metric icon={<Leaf />} label={locale === "zh" ? "减排" : "Avoided carbon"} value={`${track.saving?.co2_kg_per_month} kg`} accent="blue" />
            <Metric icon={<Gauge />} label={locale === "zh" ? "总体达成率" : "Achievement"} value={track.overall_achievement_pct == null ? "not_measurable" : `${track.overall_achievement_pct}%`} />
          </section>
          <section className="chart-grid tracking-results">
            <div className="panel chart-panel">
              <PanelTitle icon={<Gauge />} label="WEATHER-NORMALIZED" title={locale === "zh" ? "基线、预期与实际" : "Baseline, expected & actual"} />
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={track.comparison_bars || []}>
                    <CartesianGrid vertical={false} stroke="#dddcd3" />
                    <XAxis dataKey={(item: any) => localText(item.label, locale)} tickLine={false} axisLine={false} />
                    <YAxis tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="kwh" fill="#1c211c" radius={[7, 7, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="chart-note">{track.weather_normalization?.note}</p>
            </div>
            <div className="panel">
              <PanelTitle icon={<RouteIcon />} label="ACTION ATTRIBUTION" title={locale === "zh" ? "分行动可信度" : "Action-level reliability"} />
              <div className="attribution-list">
                {(track.per_action || []).map((item: any) => (
                  <div key={item.action_id}>
                    <span className={`reliability ${item.status}`}>{item.status}</span>
                    <div><strong>{localText(item.title, locale)}</strong><small>{item.note || item.reliability_note || "—"}</small></div>
                    <span>{item.achievement_pct == null ? "—" : `${item.achievement_pct}%`}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </>
      ) : (
        <EmptyState icon={<Gauge />} title={localText(track.message, locale)} />
      )}
      <section className="memory-panel">
        <div className="memory-heading">
          <span className="memory-icon"><BrainCircuit /></span>
          <div><span className="eyebrow">LONG-TERM MEMORY / {workspace.memory?.count || 0}</span><h2>{locale === "zh" ? "跨周保留的可解释记忆" : "Explainable memories across weeks"}</h2></div>
        </div>
        <div className="memory-list">
          {(workspace.memory?.items || []).length ? (workspace.memory?.items || []).map((item: any) => (
            <article key={item.id}><small>{item.kind} · {item.created_at}</small><p>{item.note}</p></article>
          )) : <p className="muted">{locale === "zh" ? "复盘产生可靠结论后写入；聊天记录本身不会冒充长期记忆。" : "Written only after a justified review; chat history is not treated as memory."}</p>}
        </div>
      </section>
      <AgentSection
        workspace={workspace}
        locale={locale}
        latestRun={reviewRun}
        openTrace={openTrace}
        compact
        fallbackEnabled={workflow.lastOperation === "review"}
      />
      {reviewRun && <AgentMemo run={reviewRun} locale={locale} />}
    </>
  );
}

function AgentSection({
  workspace,
  locale,
  latestRun,
  openTrace,
  compact = false,
  fallbackEnabled = false,
}: {
  workspace: Workspace;
  locale: Locale;
  latestRun: AgentRun | null;
  openTrace: () => void;
  compact?: boolean;
  fallbackEnabled?: boolean;
}) {
  const trace = latestRun?.trace || (fallbackEnabled ? workspace.agents.trace : []);
  const showCalls = Boolean(latestRun) || fallbackEnabled;
  return (
    <section className={`agent-section ${compact ? "compact" : ""}`}>
      <div className="agent-section-head">
        <div><span className="eyebrow">SEVEN-ROLE ORCHESTRATION</span><h2>{locale === "zh" ? "同一个编排器，七种责任边界。" : "One orchestrator. Seven responsibility boundaries."}</h2><p>{localText(workspace.agents.orchestration, locale)}</p></div>
        <button className="button outline" onClick={openTrace}><PanelRightOpen size={15} />{locale === "zh" ? `查看本次 ${trace.length} 步` : `View ${trace.length} steps`}</button>
      </div>
      <div className="agent-roster">
        {workspace.agents.agents.map((agent: any) => (
          <article key={agent.id} className={agent.has_veto ? "veto-agent" : ""}>
            <span className="agent-order">0{agent.order}</span>
            <div className="agent-avatar">{agent.has_veto ? <ShieldCheck /> : <Bot />}</div>
            <strong>{localText(agent.name, locale)}</strong>
            <p>{localText(agent.mission, locale)}</p>
            <small>{showCalls ? agent.calls_in_last_run : 0} calls</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function AgentMemo({ run, locale }: { run: AgentRun; locale: Locale }) {
  return (
    <section className="agent-memo">
      <div className="memo-meta">
        <span className={run.mode === "mock" ? "mode-badge mock" : "mode-badge live"}>{run.mode}</span>
        <span>{run.provider}</span>
        <span>{run.model}</span>
      </div>
      <div className="memo-body">
        <span className="eyebrow">ORCHESTRATOR MEMO</span>
        <pre>{run.final_text}</pre>
      </div>
      <p className="memo-foot"><ShieldCheck size={14} />{locale === "zh" ? "文本由模型生成；所有业务数字必须来自 Python 工具。" : "The model writes the narrative; Python tools own every business number."}</p>
    </section>
  );
}

function ModelDrawer({
  open,
  onClose,
  providers,
  locale,
  onChanged,
}: {
  open: boolean;
  onClose: () => void;
  providers: Providers;
  locale: Locale;
  onChanged: () => void;
}) {
  const [provider, setProvider] = useState(providers.current.provider);
  const [model, setModel] = useState(providers.current.model || "");
  const selected = providers.providers.find((item) => item.name === provider);
  const mutation = useMutation({
    mutationFn: () => api.selectModel(provider, model || null, provider === "mock" ? "mock" : "live"),
    onSuccess: () => {
      onChanged();
      onClose();
    },
  });
  const available = providers.providers.filter((item) => item.configured);
  return (
    <Drawer open={open} onClose={onClose} title={locale === "zh" ? "模型与运行模式" : "Model & run mode"} eyebrow="MODEL ROUTER">
      <p className="drawer-lede">{locale === "zh" ? "网页只显示环境变量已配置的提供方，不接收或回显 API Key。" : "The Web UI only lists providers configured via environment variables. It never accepts or reveals keys."}</p>
      <div className="provider-list">
        {available.map((item) => (
          <button key={item.name} className={provider === item.name ? "selected" : ""} onClick={() => {
            setProvider(item.name);
            setModel(item.default_model || "");
          }}>
            <span className={item.kind === "mock" ? "provider-icon mock" : "provider-icon"}>{item.kind === "mock" ? <Play /> : <Sparkles />}</span>
            <div><strong>{item.label}</strong><small>{item.name} · {item.default_model || "custom"}</small><p>{item.notes}</p></div>
            {provider === item.name && <CheckCircle2 size={18} />}
          </button>
        ))}
      </div>
      {provider !== "mock" && (
        <Field label={locale === "zh" ? "模型名" : "Model name"}>
          <input value={model} onChange={(event) => setModel(event.target.value)} />
        </Field>
      )}
      {provider === "mock" && <MockBanner locale={locale} />}
      {mutation.error && <ErrorBanner error={mutation.error} />}
      <button className="button dark wide-button" onClick={() => mutation.mutate()} disabled={!selected || mutation.isPending}>
        {mutation.isPending ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}
        {locale === "zh" ? "应用选择" : "Apply selection"}
      </button>
    </Drawer>
  );
}

function TraceDrawer({
  open,
  onClose,
  locale,
  run,
  fallbackTrace,
}: {
  open: boolean;
  onClose: () => void;
  locale: Locale;
  run: AgentRun | null;
  fallbackTrace: any[];
}) {
  const trace = run?.trace || fallbackTrace || [];
  return (
    <Drawer open={open} onClose={onClose} title={locale === "zh" ? "本次 Agent 工作记录" : "Current agent run"} eyebrow="AUDIT TRACE">
      <div className="trace-summary">
        <span>{trace.length}</span>
        <div><strong>{locale === "zh" ? "次工具调用" : "tool calls"}</strong><p>{run ? `${run.provider} · ${run.model}` : "latest persisted run"}</p></div>
      </div>
      {!trace.length && <EmptyMini icon={<PanelRightOpen />} text={locale === "zh" ? "运行诊断、规划或复盘后显示本次轨迹。" : "Run diagnosis, planning or review to see this trace."} />}
      <div className="trace-list">
        {trace.map((step: any, index: number) => (
          <article key={`${step.step}-${step.tool}-${index}`}>
            <span className="trace-line" />
            <span className="trace-step">{String(step.step || index + 1).padStart(2, "0")}</span>
            <div>
              <small>{step.role_name?.[locale] || step.role_name || step.role} · {step.elapsed_ms}ms</small>
              <strong>{step.tool}</strong>
              <p>{step.output_preview}</p>
            </div>
            <span className={step.ok ? "trace-ok" : "trace-error"}>{step.ok ? <Check size={13} /> : <X size={13} />}</span>
          </article>
        ))}
      </div>
    </Drawer>
  );
}

function ChatDrawer({ open, onClose, locale }: { open: boolean; onClose: () => void; locale: Locale }) {
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<{ role: "user" | "assistant"; text: string }[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const mutation = useMutation({
    mutationFn: (text: string) => api.chat(text, locale, history),
    onSuccess: (data, text) => {
      setHistory((items) => [...items, { role: "user", text }, { role: "assistant", text: data.run.final_text }]);
      setMessage("");
    },
  });
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [history, mutation.isPending]);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (message.trim() && !mutation.isPending) mutation.mutate(message.trim());
  };
  return (
    <Drawer open={open} onClose={onClose} title={locale === "zh" ? "问 HomeShift" : "Ask HomeShift"} eyebrow="CONTEXTUAL CHAT">
      <p className="drawer-lede">{locale === "zh" ? "对话继承当前家庭、正式计划与长期记忆；数字仍必须通过工具读取。" : "Chat inherits the current home, committed plan and durable memories. Numbers still require tools."}</p>
      <div className="chat-history" ref={scrollRef}>
        {!history.length && (
          <div className="chat-welcome"><span><Bot /></span><strong>HomeShift AI</strong><p>{locale === "zh" ? "你可以追问诊断依据、某个动作如何执行，或本周为何没有达标。" : "Ask about diagnosis evidence, how to execute an action, or why this week missed target."}</p></div>
        )}
        {history.map((item, index) => <div key={index} className={`chat-bubble ${item.role}`}><pre>{item.text}</pre></div>)}
        {mutation.isPending && <div className="chat-bubble assistant thinking"><LoaderCircle className="spin" size={16} /> Python 工具与 Agent 正在协作…</div>}
      </div>
      {mutation.error && <ErrorBanner error={mutation.error} />}
      <form className="chat-form" onSubmit={submit}>
        <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder={locale === "zh" ? "问一个与当前家庭有关的问题…" : "Ask about the current household…"} />
        <button disabled={!message.trim() || mutation.isPending}><Send size={17} /></button>
      </form>
    </Drawer>
  );
}

function Drawer({ open, onClose, title, eyebrow, children }: { open: boolean; onClose: () => void; title: string; eyebrow: string; children: ReactNode }) {
  return (
    <>
      <button className={`drawer-backdrop ${open ? "open" : ""}`} onClick={onClose} aria-label="close drawer" />
      <aside className={`drawer ${open ? "open" : ""}`} aria-hidden={!open}>
        <div className="drawer-head"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div><button className="icon-button" onClick={onClose}><X size={19} /></button></div>
        <div className="drawer-body">{children}</div>
      </aside>
    </>
  );
}

function Schedule({ schedule, locale, version }: { schedule: any[]; locale: Locale; version: number | null | undefined }) {
  return (
    <section className="schedule-panel panel">
      <PanelTitle icon={<RouteIcon />} label={`COMMITTED PLAN / V${version}`} title={locale === "zh" ? "七日执行日历" : "Seven-day execution calendar"} />
      <div className="schedule-grid">
        {schedule.map((day) => (
          <article key={day.date}>
            <small>DAY {day.day}</small><strong>{day.date.slice(5)}</strong>
            <div>{day.items.length ? day.items.map((item: any) => <span key={`${day.date}-${item.action_id}`}><CheckCircle2 size={12} />{item.title}</span>) : <em>{locale === "zh" ? "保持习惯" : "Maintain habits"}</em>}</div>
          </article>
        ))}
      </div>
    </section>
  );
}

function AccuracyCard({ accuracy, locale }: { accuracy: any; locale: Locale }) {
  return (
    <div className={`panel accuracy-card ${accuracy?.available ? "has-truth" : ""}`}>
      <PanelTitle icon={<ShieldCheck />} label="NILM VALIDATION" title={accuracy?.available ? "MAE / ground truth" : locale === "zh" ? "无分表真值" : "No sub-meter truth"} />
      <p>{localText(accuracy?.note, locale)}</p>
      {accuracy?.available && <div className="mae-list">{Object.entries(accuracy.per_category || {}).map(([key, value]: [string, any]) => <span key={key}><strong>{key}</strong>{value.mae_kwh_per_day ?? value.mae}</span>)}</div>}
    </div>
  );
}

function Metric({ icon, label, value, accent = "" }: { icon: ReactNode; label: string; value: string; accent?: string }) {
  return <article className={`metric-card ${accent}`}><span>{icon}</span><small>{label}</small><strong>{value}</strong></article>;
}

function PanelTitle({ icon, label, title }: { icon: ReactNode; label: string; title: string }) {
  return <div className="panel-title"><span>{icon}</span><div><small>{label}</small><h2>{title}</h2></div></div>;
}

function Field({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return <label className={`field ${wide ? "wide" : ""}`}><span>{label}</span>{children}</label>;
}

function Quality({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function DataBadge({ workspace, locale }: { workspace: Workspace; locale: Locale }) {
  return <span className={`large-data-badge ${workspace.meta.data_kind}`}><Database size={16} />{localText(workspace.meta.data_badge, locale)}</span>;
}

function StageGate({
  allowed,
  locale,
  requiredPath,
  requiredStage,
  children,
}: {
  allowed: boolean;
  locale: Locale;
  requiredPath: string;
  requiredStage: "data" | "diagnosis" | "plan";
  children: ReactNode;
}) {
  if (allowed) return <>{children}</>;
  const messages = {
    data: {
      zh: ["先建立数据基线。", "上传真实 CSV 或建立合成家庭后，才能进入后续分析。", "前往数据接入"],
      en: ["Build the data baseline first.", "Upload a real CSV or create a synthetic household before continuing.", "Go to Data"],
    },
    diagnosis: {
      zh: ["计划阶段尚未解锁。", "当前候选数字来自 Python 预计算；请先完成一次 Agent 诊断，形成可审计分析记录。", "前往诊断"],
      en: ["The Plan stage is locked.", "Candidate numbers are Python pre-calculations. Complete an agent diagnosis to create an auditable analysis.", "Go to Diagnosis"],
    },
    plan: {
      zh: ["追踪阶段尚未解锁。", "请先让 Agent 提出建议，并由你确认提交一份正式计划。", "前往计划"],
      en: ["The Track stage is locked.", "Ask the agent for a proposal and confirm a committed plan first.", "Go to Plan"],
    },
  }[requiredStage][locale];
  return (
    <>
      <PageIntro eyebrow="WORKFLOW GATE" title={messages[0]} description={messages[1]} />
      <EmptyState
        icon={<LockKeyhole />}
        title={messages[0]}
        action={<NavLink className="button lime" to={requiredPath}>{messages[2]}<ArrowRight size={15} /></NavLink>}
      />
    </>
  );
}

function AnalysisStateBanner({
  locale,
  complete,
  pending = false,
  kind,
  traceCount = 0,
}: {
  locale: Locale;
  complete: boolean;
  pending?: boolean;
  kind: "baseline" | "diagnosis" | "proposal" | "tracking" | "review";
  traceCount?: number;
}) {
  const content = {
    baseline: {
      waiting: {
        zh: ["当前基线由 Python 现场计算", "这些指标和曲线不是预置截图；它们来自当前工作空间的数据。重新导入 CSV 后会重新计算。"],
        en: ["Baseline computed by Python", "These metrics and charts are not preset screenshots. They come from the current workspace and are recomputed after every import."],
      },
      complete: {
        zh: ["当前基线由 Python 现场计算", "这些指标和曲线不是预置截图；它们来自当前工作空间的数据。重新导入 CSV 后会重新计算。"],
        en: ["Baseline computed by Python", "These metrics and charts are not preset screenshots. They come from the current workspace and are recomputed after every import."],
      },
    },
    diagnosis: {
      waiting: {
        zh: ["Agent 尚未开始本次诊断", "下方 NILM 与发现是 Python 的确定性预分析。点击“运行本次 Agent 诊断”后，模型才会读取摘要、调用七角色工具并解锁计划阶段。"],
        en: ["The agent has not run this diagnosis", "The NILM and findings below are deterministic Python pre-analysis. Run the agent to interpret evidence, invoke seven-role tools and unlock Plan."],
      },
      complete: {
        zh: ["本次 Agent 诊断已完成", `已形成 ${traceCount} 步可审计工具轨迹，计划阶段现已解锁。`],
        en: ["Agent diagnosis completed", `${traceCount} auditable tool steps were produced. Plan is now unlocked.`],
      },
    },
    proposal: {
      waiting: {
        zh: ["候选潜力已计算，Agent 尚未提案", "卡片中的 kWh、金额和碳排来自 Python；运行 Agent 提案后才会高亮建议动作并开放用户提交。"],
        en: ["Potential calculated; no agent proposal yet", "Python owns the kWh, cost and carbon values. Run the proposal before actions can be selected and committed."],
      },
      complete: {
        zh: ["Agent 建议草案已生成", `建议动作已高亮，并保留 ${traceCount} 步工具轨迹；只有你的确认才会写入正式计划。`],
        en: ["Agent proposal is ready", `Suggested actions are highlighted with ${traceCount} tool steps. Only your confirmation persists a plan.`],
      },
    },
    tracking: {
      waiting: {
        zh: ["等待实施后数据", "请选择演示快进或上传真实 CSV；没有实施后证据时不会开放复盘。"],
        en: ["Waiting for post-plan data", "Choose demo fast-forward or upload a real CSV. Review stays locked without after-data evidence."],
      },
      complete: {
        zh: ["实施后数据已经接入", "追踪指标已由 Python 重新计算，现在可以运行天气归一化复盘 Agent。"],
        en: ["Post-plan data connected", "Python has recomputed tracking metrics. The weather-normalized review agent is now available."],
      },
    },
    review: {
      waiting: {
        zh: ["复盘 Agent 尚未运行", "当前对比图是 Python 计算结果；运行复盘后，Agent 才会解释异常、判断归因可信度并写入可靠记忆。"],
        en: ["The review agent has not run", "The comparison chart is a Python result. Run review to explain anomalies, assess attribution and store justified memories."],
      },
      complete: {
        zh: ["本次复盘已完成", `已形成 ${traceCount} 步工具轨迹，并仅将有依据的结论写入长期记忆。`],
        en: ["Review completed", `${traceCount} tool steps were recorded and only justified conclusions entered durable memory.`],
      },
    },
  }[kind];
  const state = pending ? "pending" : complete ? "complete" : "waiting";
  const text = pending
    ? locale === "zh"
      ? ["请求正在执行", "请保持页面开启；下方过程窗口会持续显示当前工作。"]
      : ["Request in progress", "Keep this page open. The live work panel shows the current activity."]
    : content[complete ? "complete" : "waiting"][locale];
  return (
    <div className={`analysis-state ${state}`}>
      <span>{pending ? <LoaderCircle className="spin" /> : complete ? <CheckCircle2 /> : <Sparkles />}</span>
      <div><strong>{text[0]}</strong><p>{text[1]}</p></div>
    </div>
  );
}

function GuideNotice({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="guide-notice" role="alert">
      <span><LockKeyhole size={17} /></span>
      <div><strong>WORKFLOW GUIDE</strong><p>{message}</p></div>
      <button onClick={onClose} aria-label="close guide"><X size={15} /></button>
    </div>
  );
}

function WorkInProgress({
  operation,
  locale,
}: {
  operation: { kind: OperationKind; startedAt: number };
  locale: Locale;
}) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    setElapsed(0);
    const timer = window.setInterval(
      () => setElapsed(Math.max(0, Math.floor((Date.now() - operation.startedAt) / 1000))),
      500,
    );
    return () => window.clearInterval(timer);
  }, [operation.kind, operation.startedAt]);

  const operationContent: Record<OperationKind, Record<Locale, [string, string, string[]]>> = {
    import: {
      zh: ["正在建立家庭工作空间", "Python 正在读取真实数据并重建全部基线。", ["校验文件、列和单位", "排序并检查缺失时段", "接入天气与数据出处", "生成画像、指标与负荷曲线"]],
      en: ["Building the household workspace", "Python is reading the dataset and rebuilding the complete baseline.", ["Validate file, columns and units", "Sort and inspect missing intervals", "Attach weather and provenance", "Build profile, metrics and load curves"]],
    },
    profile: {
      zh: ["正在更新家庭约束", "舒适规则与目标将进入后续 Agent 决策。", ["验证画像字段", "保存舒适硬约束", "重算候选行动", "刷新工作空间"]],
      en: ["Updating household constraints", "Comfort rules and goals will shape later agent decisions.", ["Validate profile fields", "Persist hard comfort rules", "Recompute candidate actions", "Refresh workspace"]],
    },
    diagnosis: {
      zh: ["AI 正在分析当前家庭数据", "确定性工具与七个专业角色正在协作。", ["读取负荷、天气与家庭画像", "运行六类 NILM 负载分解", "成本、碳排与舒适角色核验", "总控整理证据与诊断结论"]],
      en: ["AI is analysing this household", "Deterministic tools and seven specialist roles are collaborating.", ["Read load, weather and household profile", "Run six-category NILM", "Check cost, carbon and comfort", "Orchestrator assembles evidence and findings"]],
    },
    proposal: {
      zh: ["Agent 正在形成行动建议", "所有节省数字由 Python 计算，模型负责取舍。", ["读取诊断证据", "量化全部候选动作", "Comfort Guardian 执行否决", "生成不落盘的建议草案"]],
      en: ["Agent is preparing an action proposal", "Python owns the savings numbers; the model makes trade-offs.", ["Read diagnosis evidence", "Quantify all candidate actions", "Apply Comfort Guardian vetoes", "Create a non-persisted proposal"]],
    },
    commit: {
      zh: ["正在提交正式计划", "系统只保存你刚刚确认的动作组合。", ["复核动作 ID 与约束", "创建计划版本", "计算正式预期收益", "生成七日执行日历"]],
      en: ["Committing the formal plan", "Only the action set you confirmed will be persisted.", ["Verify action IDs and constraints", "Create plan version", "Compute committed benefits", "Generate seven-day schedule"]],
    },
    tracking: {
      zh: ["正在整理实施后数据", "Python 正在追加数据并重新计算追踪证据。", ["检查时间必须晚于基线", "追加真实或合成读数", "同步天气信息", "重算计划达成指标"]],
      en: ["Processing post-plan data", "Python is appending readings and recomputing tracking evidence.", ["Verify timestamps follow baseline", "Append real or synthetic readings", "Align weather evidence", "Recompute plan achievement"]],
    },
    review: {
      zh: ["AI 正在进行天气归一化复盘", "Agent 正在核验真实节省、异常与可写入记忆的结论。", ["读取正式计划与实施后数据", "计算天气归一化预期", "判断分行动归因可信度", "生成复盘并更新长期记忆"]],
      en: ["AI is running a weather-normalized review", "The agent is checking savings, anomalies and justified memories.", ["Read plan and post-plan evidence", "Compute weather-normalized expectation", "Assess action attribution reliability", "Write review and durable memory"]],
    },
  };
  const content = operationContent[operation.kind][locale];
  const steps = content[2];
  const activeIndex = Math.min(Math.floor(elapsed / 3), steps.length - 1);
  const visualProgress = Math.min(18 + elapsed * 5, 92);
  return (
    <div className="work-overlay" role="status" aria-live="polite" aria-label={content[0]}>
      <section className="work-card">
        <div className="agent-loader" aria-hidden="true">
          <span className="loader-ring ring-one" />
          <span className="loader-ring ring-two" />
          <span className="loader-core"><Bot size={26} /></span>
          {Array.from({ length: 7 }, (_, index) => <i key={index} style={{ "--node": index } as CSSProperties} />)}
        </div>
        <span className="eyebrow">LIVE WORK / {String(elapsed).padStart(2, "0")}S</span>
        <h2>{content[0]}</h2>
        <p className="work-lede">{content[1]}</p>
        <div className="work-progress"><span style={{ width: `${visualProgress}%` }} /></div>
        <ol className="work-steps">
          {steps.map((step, index) => (
            <li key={step} className={index < activeIndex ? "done" : index === activeIndex ? "active" : ""}>
              <span>{index < activeIndex ? <Check size={12} /> : index === activeIndex ? <LoaderCircle className="spin" size={12} /> : index + 1}</span>
              <strong>{step}</strong>
            </li>
          ))}
        </ol>
        <p className="work-disclaimer">
          <ShieldCheck size={13} />
          {locale === "zh"
            ? "过程提示表示当前请求的工作范围；最终完成状态与真实工具轨迹以 API 返回为准。"
            : "Activity labels describe the current request scope. Completion and tool trace are confirmed only by the API response."}
        </p>
      </section>
    </div>
  );
}

function MockBanner({ locale }: { locale: Locale }) {
  return <div className="warning-banner"><Play size={18} /><div><strong>{locale === "zh" ? "离线 Mock 彩排" : "Offline Mock rehearsal"}</strong><p>{locale === "zh" ? "工具执行与业务数字真实；下一步调用顺序由剧本驱动，不是实时模型推理。" : "Tool execution and business numbers are real; tool order is playbook-driven, not live model reasoning."}</p></div></div>;
}

function MockDataBanner({ locale }: { locale: Locale }) {
  return <div className="synthetic-banner"><Sparkles size={18} /><div><strong>{locale === "zh" ? "当前追踪使用合成实施后数据" : "Current tracking uses synthetic after-data"}</strong><p>{locale === "zh" ? "这些读数只用于演示闭环，不代表真实执行结果。" : "These readings demonstrate the loop and are not real-world outcomes."}</p></div></div>;
}

function ErrorBanner({ error }: { error: unknown }) {
  const code = error instanceof ApiError ? error.code : "error";
  return <div className="error-banner"><AlertTriangle size={17} /><div><strong>{code}</strong><p>{errorMessage(error)}</p></div></div>;
}

function EmptyMini({ icon, text }: { icon: ReactNode; text: string }) {
  return <div className="empty-mini"><span>{icon}</span><p>{text}</p></div>;
}

function EmptyState({ icon, title, action }: { icon: ReactNode; title: string; action?: ReactNode }) {
  return <section className="empty-state"><span>{icon}</span><h2>{title}</h2>{action}</section>;
}

function NoData({ locale }: { locale: Locale }) {
  return (
    <>
      <PageIntro eyebrow="WORKSPACE REQUIRED" title={locale === "zh" ? "先建立当前家庭工作空间。" : "Create the current household workspace first."} description={locale === "zh" ? "Python 后端需要一份可用的基线数据和家庭画像。" : "The Python backend needs baseline data and a household profile."} />
      <EmptyState icon={<Database />} title={locale === "zh" ? "没有可分析的数据" : "No analyzable data"} action={<NavLink className="button lime" to="/data">{locale === "zh" ? "前往数据接入" : "Go to data"}<ArrowRight size={15} /></NavLink>} />
    </>
  );
}

function FullScreenState({ icon, title, detail, action }: { icon: ReactNode; title: string; detail: string; action?: ReactNode }) {
  return <div className="full-screen-state"><span>{icon}</span><h1>{title}</h1><p>{detail}</p>{action}</div>;
}

function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return String(error || "Unknown error");
}

const tooltipStyle = {
  background: "#1c211c",
  border: "none",
  borderRadius: 10,
  color: "#fbfaf5",
  fontSize: 12,
};

export default App;
