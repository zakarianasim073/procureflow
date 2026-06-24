import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock3,
  Cpu,
  Database,
  GitBranch,
  LayoutGrid,
  Layers3,
  MessageSquare,
  Loader2,
  RefreshCw,
  Search,
  Shield,
  Send,
  Wrench,
  XCircle,
} from 'lucide-react';
import {
  approveThought,
  getBrainStatus,
  analyzeWatchdogError,
  diagnoseEngineerError,
  getEngineerStatus,
  getWatchdogDashboard,
  getWatchdogErrors,
  getWatchdogHealth,
  getWatchdogSessions,
  getPendingThoughts,
  getThoughtHistory,
  getThoughtStats,
  logUiEvent,
  listAgents,
  listPipelinePhases,
  proposeThought,
  rejectThought,
  sendBrainMessage,
} from '../api/client';

type PanelState = {
  loading: boolean;
  error: string;
};

const initialPanelState = { loading: false, error: '' };

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  tone = 'slate',
}: {
  title: string;
  value: string | number;
  subtitle: string;
  icon: any;
  tone?: 'slate' | 'blue' | 'green' | 'amber' | 'red' | 'purple';
}) {
  const toneClasses: Record<string, string> = {
    slate: 'from-slate-50 to-slate-100 text-slate-700 dark:from-slate-900/40 dark:to-slate-800/40 dark:text-slate-200',
    blue: 'from-blue-50 to-cyan-50 text-blue-700 dark:from-blue-900/30 dark:to-cyan-900/20 dark:text-blue-200',
    green: 'from-emerald-50 to-green-50 text-emerald-700 dark:from-emerald-900/30 dark:to-green-900/20 dark:text-emerald-200',
    amber: 'from-amber-50 to-yellow-50 text-amber-700 dark:from-amber-900/30 dark:to-yellow-900/20 dark:text-amber-200',
    red: 'from-red-50 to-rose-50 text-red-700 dark:from-red-900/30 dark:to-rose-900/20 dark:text-red-200',
    purple: 'from-violet-50 to-fuchsia-50 text-violet-700 dark:from-violet-900/30 dark:to-fuchsia-900/20 dark:text-violet-200',
  };

  return (
    <div className={`rounded-2xl border border-white/60 bg-gradient-to-br p-5 shadow-sm backdrop-blur ${toneClasses[tone]}`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.2em] opacity-70">{title}</div>
          <div className="mt-2 text-3xl font-bold">{value}</div>
          <div className="mt-1 text-sm opacity-70">{subtitle}</div>
        </div>
        <div className="rounded-2xl bg-white/70 p-3 shadow-sm dark:bg-black/20">
          <Icon size={22} />
        </div>
      </div>
    </div>
  );
}

function CardShell({
  title,
  icon: Icon,
  children,
  actions,
}: {
  title: string;
  icon: any;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="rounded-3xl border border-slate-200/80 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-900 dark:text-white">
          <Icon size={18} className="text-primary-600" />
          {title}
        </h2>
        {actions}
      </div>
      {children}
    </section>
  );
}

export default function WatchdogEngineer() {
  const navigate = useNavigate();
  const [watchdogHealth, setWatchdogHealth] = useState<any>(null);
  const [watchdogDashboard, setWatchdogDashboard] = useState<any>(null);
  const [watchdogErrors, setWatchdogErrors] = useState<any[]>([]);
  const [watchdogSessions, setWatchdogSessions] = useState<any[]>([]);
  const [engineerStatus, setEngineerStatus] = useState<any>(null);
  const [agentStats, setAgentStats] = useState<any>(null);
  const [pipelineStats, setPipelineStats] = useState<any>(null);
  const [panel, setPanel] = useState<PanelState>(initialPanelState);
  const [diagnosticSource, setDiagnosticSource] = useState('agent-014-award-intelligence');
  const [diagnosticType, setDiagnosticType] = useState('RuntimeError');
  const [diagnosticMessage, setDiagnosticMessage] = useState('Sample error for system verification.');
  const [diagnosticContext, setDiagnosticContext] = useState('');
  const [watchdogAnalysis, setWatchdogAnalysis] = useState<any>(null);
  const [engineerAnalysis, setEngineerAnalysis] = useState<any>(null);
  const [brainStatus, setBrainStatus] = useState<any>(null);
  const [brainMessageRecipient, setBrainMessageRecipient] = useState('agent-003-corrigendum-watchdog');
  const [brainSubject, setBrainSubject] = useState('UI smoke check');
  const [brainBody, setBrainBody] = useState('{"tender_id":"UI-CHECK-001","note":"Confirm internal agent messaging"}');
  const [brainResponse, setBrainResponse] = useState<any>(null);
  const [thoughtStats, setThoughtStats] = useState<any>(null);
  const [pendingThoughts, setPendingThoughts] = useState<any[]>([]);
  const [thoughtHistory, setThoughtHistory] = useState<any[]>([]);
  const [thoughtSourceAgent, setThoughtSourceAgent] = useState('agent-022-executive-decision');
  const [thoughtSourceName, setThoughtSourceName] = useState('Executive Decision');
  const [thoughtType, setThoughtType] = useState('insight');
  const [thoughtTitle, setThoughtTitle] = useState('UI thoughts check');
  const [thoughtDescription, setThoughtDescription] = useState('Confirm the thought engine can accept a proposed insight from the UI.');
  const [thoughtEvidence, setThoughtEvidence] = useState('{"source":"ui","check":"thoughts"}');
  const [thoughtTenderId, setThoughtTenderId] = useState('UI-CHECK-001');
  const [thoughtImpact, setThoughtImpact] = useState('medium');
  const [thoughtConfidence, setThoughtConfidence] = useState('0.6');
  const [thoughtResponse, setThoughtResponse] = useState<any>(null);
  const [actioningThoughtId, setActioningThoughtId] = useState<string | null>(null);
  const [thoughtActionError, setThoughtActionError] = useState('');
  const [selectedComponentType, setSelectedComponentType] = useState<'agent' | 'endpoint' | 'table' | 'pipeline' | 'service'>('agent');

  const loadAll = async () => {
    setPanel({ loading: true, error: '' });
    try {
      const [health, dashboard, errors, sessions, engineer, agents, pipeline, thoughtStatsRes, pendingThoughtsRes, thoughtHistoryRes] = await Promise.all([
        getWatchdogHealth(),
        getWatchdogDashboard(),
        getWatchdogErrors(8),
        getWatchdogSessions(8),
        getEngineerStatus(),
        listAgents(),
        listPipelinePhases(),
        getThoughtStats(),
        getPendingThoughts(),
        getThoughtHistory('approved', 8),
      ]);
      const brain = await getBrainStatus();
      setWatchdogHealth(health);
      setWatchdogDashboard(dashboard);
      setWatchdogErrors(errors.errors || []);
      setWatchdogSessions(sessions.sessions || []);
      setEngineerStatus(engineer);
      setAgentStats(agents);
      setPipelineStats(pipeline);
      setBrainStatus(brain);
      setThoughtStats(thoughtStatsRes);
      setPendingThoughts(pendingThoughtsRes.pending_thoughts || []);
      setThoughtHistory(thoughtHistoryRes.thoughts || []);
      await logUiEvent({
        feature: 'watchdog_engineer',
        action: 'load_all',
        data: {
          agents: agents?.agents?.length ?? 0,
          phases: pipeline?.phases ? Object.keys(pipeline.phases).length : 0,
          watchdog_status: health?.status,
          brain_agents: brain?.agents_registered ?? 0,
          thought_pending: pendingThoughtsRes?.count ?? 0,
        },
      });
    } catch (error: any) {
      setPanel({ loading: false, error: error?.response?.data?.detail || error?.message || 'Failed to load watchdog/engineer data' });
      return;
    }
    setPanel({ loading: false, error: '' });
  };

  useEffect(() => {
    loadAll();
  }, []);

  const componentMap = engineerStatus?.component_map || {};
  const systemSummary = engineerStatus?.system_knowledge || {};
  const componentTypes = useMemo(() => Object.keys(componentMap), [componentMap]);
  const selectedComponents = componentMap[selectedComponentType] || [];
  const watchdogStatus = watchdogHealth?.status || watchdogDashboard?.status || 'unknown';
  const healthTone = watchdogStatus === 'healthy' ? 'green' : watchdogStatus === 'degraded' ? 'amber' : watchdogStatus === 'critical' ? 'red' : 'slate';

  const refreshAnalysis = async () => {
    setPanel((current) => ({ ...current, loading: true, error: '' }));
    try {
      const parsedContext = (() => {
        const text = diagnosticContext.trim();
        if (!text) return {};
        try {
          return JSON.parse(text);
        } catch {
          return {};
        }
      })();
      const payload = {
        source: diagnosticSource.trim(),
        error_message: diagnosticMessage.trim(),
        error_type: diagnosticType.trim() || 'Unknown',
      };
      const [watchdogResult, engineerResult] = await Promise.all([
        analyzeWatchdogError(payload),
        diagnoseEngineerError({ ...payload, context: parsedContext }),
      ]);
      setWatchdogAnalysis(watchdogResult);
      setEngineerAnalysis(engineerResult);
      await logUiEvent({
        feature: 'watchdog_engineer',
        action: 'diagnostics',
        data: { watchdog: watchdogResult, engineer: engineerResult },
      });
    } catch (error: any) {
      setPanel((current) => ({ ...current, error: error?.response?.data?.detail || error?.message || 'Diagnostics failed' }));
    } finally {
      setPanel((current) => ({ ...current, loading: false }));
    }
  };

  const runBrainMessage = async () => {
    setPanel((current) => ({ ...current, loading: true, error: '' }));
    try {
      const parsedBody = (() => {
        const text = brainBody.trim();
        if (!text) return {};
        try {
          return JSON.parse(text);
        } catch {
          return { message: text };
        }
      })();
      const response = await sendBrainMessage({
        sender: 'ui-watchdog',
        recipient: brainMessageRecipient.trim(),
        subject: brainSubject.trim() || 'UI smoke check',
        body: parsedBody,
      });
      setBrainResponse(response);
      await logUiEvent({
        feature: 'watchdog_engineer',
        action: 'brain_message',
        data: response,
      });
    } catch (error: any) {
      setPanel((current) => ({ ...current, error: error?.response?.data?.detail || error?.message || 'Brain message failed' }));
    } finally {
      setPanel((current) => ({ ...current, loading: false }));
    }
  };

  const refreshThoughts = async () => {
    const [pendingThoughtsRes, thoughtHistoryRes, thoughtStatsRes] = await Promise.all([
      getPendingThoughts(),
      getThoughtHistory('approved', 8),
      getThoughtStats(),
    ]);
    setPendingThoughts(pendingThoughtsRes.pending_thoughts || []);
    setThoughtHistory(thoughtHistoryRes.thoughts || []);
    setThoughtStats(thoughtStatsRes);
  };

  const handleThoughtAction = async (thoughtId: string, action: 'approve' | 'reject') => {
    setActioningThoughtId(thoughtId);
    setThoughtActionError('');
    try {
      if (action === 'approve') {
        await approveThought(thoughtId);
      } else {
        await rejectThought(thoughtId);
      }
      await refreshThoughts();
      await logUiEvent({
        feature: 'watchdog_engineer',
        action: `thought_${action}`,
        data: { thought_id: thoughtId },
      });
    } catch (error: any) {
      setThoughtActionError(error?.response?.data?.detail || error?.message || `Failed to ${action} thought`);
    } finally {
      setActioningThoughtId(null);
    }
  };

  const runThoughtPropose = async () => {
    setPanel((current) => ({ ...current, loading: true, error: '' }));
    try {
      const parsedEvidence = (() => {
        const text = thoughtEvidence.trim();
        if (!text) return {};
        try {
          return JSON.parse(text);
        } catch {
          return { note: text };
        }
      })();
      const response = await proposeThought({
        agent_id: thoughtSourceAgent.trim() || 'api',
        agent_name: thoughtSourceName.trim() || 'API User',
        thought_type: thoughtType.trim() || 'insight',
        title: thoughtTitle.trim(),
        description: thoughtDescription.trim(),
        evidence: parsedEvidence,
        tender_id: thoughtTenderId.trim(),
        impact: thoughtImpact.trim() || 'medium',
        confidence: Number(thoughtConfidence) || 0,
        key_data: parsedEvidence,
      });
      setThoughtResponse(response);
      await logUiEvent({
        feature: 'watchdog_engineer',
        action: 'thought_propose',
        data: response,
      });
    } catch (error: any) {
      setPanel((current) => ({ ...current, error: error?.response?.data?.detail || error?.message || 'Thought proposal failed' }));
    } finally {
      setPanel((current) => ({ ...current, loading: false }));
    }
  };

  const recentErrorCount = watchdogErrors.length;
  const recentSessionCount = watchdogSessions.length;
  const registeredAgents = agentStats?.agents?.length ?? agentStats?.total ?? engineerStatus?.system_knowledge?.agents ?? 0;
  const pipelinePhaseCount = pipelineStats?.phases ? Object.keys(pipelineStats.phases).length : pipelineStats?.phases?.length ?? 0;

  return (
    <div className="min-h-full bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.14),_transparent_40%),linear-gradient(180deg,#f8fafc_0%,#eef2ff_100%)] px-4 py-6 dark:bg-[radial-gradient(circle_at_top,_rgba(15,23,42,0.7),_transparent_45%),linear-gradient(180deg,#020617_0%,#0f172a_100%)] sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <div className="flex flex-col gap-4 rounded-3xl border border-white/60 bg-white/80 p-6 shadow-sm backdrop-blur dark:border-slate-700 dark:bg-slate-900/80 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-primary-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-primary-700 dark:bg-primary-900/30 dark:text-primary-200">
              <Shield size={14} />
              Watchdog and Engineer
            </div>
            <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              Core system verification console
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">
              Live health, agent registry, watchdog logs, and engineer diagnostics in one view. Use this to confirm that the orchestration layer, diagnostics, and the agent core paths are actually responding.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={loadAll}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
            >
              <RefreshCw size={16} />
              Refresh all
            </button>
            <button
              onClick={() => navigate('/agents')}
              className="inline-flex items-center gap-2 rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
            >
              <GitBranch size={16} />
              Agent pipeline
            </button>
          </div>
        </div>

        {panel.error && (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
            {panel.error}
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatCard
            title="Agents"
            value={registeredAgents}
            subtitle="Registry and brain visibility"
            icon={Bot}
            tone="blue"
          />
          <StatCard
            title="Pipeline"
            value={pipelinePhaseCount}
            subtitle="Registered phases"
            icon={GitBranch}
            tone="purple"
          />
          <StatCard
            title="Watchdog"
            value={watchdogStatus.toUpperCase()}
            subtitle={`${recentErrorCount} recent errors`}
            icon={AlertTriangle}
            tone={healthTone as any}
          />
          <StatCard
            title="Engineer"
            value={systemSummary.total_components ?? 0}
            subtitle="Known system components"
            icon={Wrench}
            tone="green"
          />
        </div>

        <div className="grid gap-6 xl:grid-cols-2">
          <CardShell
            title="Watchdog health"
            icon={Activity}
            actions={<span className="text-xs font-medium uppercase tracking-[0.2em] text-slate-400">Live API</span>}
          >
            {watchdogHealth ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Status</div>
                    <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{watchdogHealth.status || 'unknown'}</div>
                  </div>
                  <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Uptime</div>
                    <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{watchdogHealth.uptime_s ?? watchdogDashboard?.uptime_s ?? '—'}s</div>
                  </div>
                  <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Errors</div>
                    <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{watchdogHealth.error_count ?? recentErrorCount}</div>
                  </div>
                  <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">DB</div>
                    <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{watchdogHealth.database?.status || 'unknown'}</div>
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/40">
                  <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
                    <CheckCircle2 size={16} className="text-green-500" />
                    Recent watchdog findings
                  </div>
                  <div className="space-y-2">
                    {(watchdogHealth.recent_errors || watchdogErrors).slice(0, 4).map((item: any) => (
                      <div key={item.id || `${item.source}-${item.timestamp}`} className="rounded-xl bg-white px-3 py-2 text-sm text-slate-600 shadow-sm dark:bg-slate-900/60 dark:text-slate-300">
                        <span className="font-medium text-slate-900 dark:text-white">{item.source || item.src || 'system'}</span>
                        <span className="mx-2 text-slate-300">•</span>
                        {item.error_message || item.msg || item.message || 'No message'}
                      </div>
                    ))}
                    {(watchdogHealth.recent_errors || watchdogErrors).length === 0 && (
                      <div className="text-sm text-slate-400">No recent errors captured.</div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-sm text-slate-400">Loading watchdog health...</div>
            )}
          </CardShell>

          <CardShell title="Engineer knowledge" icon={Layers3}>
            {engineerStatus ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Agents</div>
                    <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{systemSummary.agents ?? 0}</div>
                  </div>
                  <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Endpoints</div>
                    <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{systemSummary.endpoints ?? 0}</div>
                  </div>
                  <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Tables</div>
                    <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{systemSummary.tables ?? 0}</div>
                  </div>
                  <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Fixes</div>
                    <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{systemSummary.fix_library_entries ?? 0}</div>
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/40">
                  <div className="mb-3 flex items-center justify-between">
                    <div className="text-sm font-semibold text-slate-900 dark:text-white">Component types</div>
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">{componentTypes.length} buckets</div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    {componentTypes.map((type) => (
                      <button
                        key={type}
                        onClick={() => setSelectedComponentType(type as any)}
                        className={`rounded-2xl border px-3 py-2 text-left transition ${
                          selectedComponentType === type
                            ? 'border-primary-300 bg-primary-50 text-primary-700 dark:border-primary-700 dark:bg-primary-900/30 dark:text-primary-200'
                            : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300'
                        }`}
                      >
                        <div className="text-sm font-medium capitalize">{type}</div>
                        <div className="text-xs opacity-70">{componentMap[type].length} items</div>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/40">
                  <div className="mb-3 flex items-center justify-between">
                    <div className="text-sm font-semibold text-slate-900 dark:text-white capitalize">{selectedComponentType} components</div>
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Inspect live map</div>
                  </div>
                  <div className="max-h-64 space-y-2 overflow-auto pr-1">
                    {selectedComponents.slice(0, 10).map((component: any) => (
                      <div key={component.id} className="rounded-xl bg-white px-3 py-2 shadow-sm dark:bg-slate-900/60">
                        <div className="text-sm font-medium text-slate-900 dark:text-white">{component.name}</div>
                        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{component.desc || component.file || component.file_path || 'No description'}</div>
                      </div>
                    ))}
                    {selectedComponents.length === 0 && <div className="text-sm text-slate-400">No components for this type.</div>}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-sm text-slate-400">Loading engineer status...</div>
            )}
          </CardShell>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <CardShell
            title="Brain messaging"
            icon={MessageSquare}
            actions={
              <button
                onClick={runBrainMessage}
                disabled={panel.loading}
                className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
              >
                <Send size={16} />
                Send message
              </button>
            }
          >
            <div className="grid gap-4 md:grid-cols-2">
              <label className="block">
                <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Recipient agent</div>
                <input
                  value={brainMessageRecipient}
                  onChange={(e) => setBrainMessageRecipient(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Subject</div>
                <input
                  value={brainSubject}
                  onChange={(e) => setBrainSubject(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                />
              </label>
            </div>
            <label className="mt-4 block">
              <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Body JSON</div>
              <textarea
                value={brainBody}
                onChange={(e) => setBrainBody(e.target.value)}
                rows={4}
                className="w-full rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
              />
            </label>
            <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/40">
              <div className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">Brain status</div>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-600 dark:text-slate-300">
                {brainStatus ? JSON.stringify(brainStatus, null, 2) : 'No brain status loaded.'}
              </pre>
            </div>
            <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/40">
              <div className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">Last brain response</div>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-600 dark:text-slate-300">
                {brainResponse ? JSON.stringify(brainResponse, null, 2) : 'No message sent yet.'}
              </pre>
            </div>
          </CardShell>

          <CardShell
            title="Thought engine"
            icon={Bot}
            actions={
              <button
                onClick={runThoughtPropose}
                disabled={panel.loading}
                className="inline-flex items-center gap-2 rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
              >
                <Wrench size={16} />
                Propose thought
              </button>
            }
          >
            <div className="grid gap-4 md:grid-cols-2">
              <label className="block">
                <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Agent ID</div>
                <input
                  value={thoughtSourceAgent}
                  onChange={(e) => setThoughtSourceAgent(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Agent name</div>
                <input
                  value={thoughtSourceName}
                  onChange={(e) => setThoughtSourceName(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Thought type</div>
                <input
                  value={thoughtType}
                  onChange={(e) => setThoughtType(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Impact / confidence</div>
                <div className="flex gap-2">
                  <input
                    value={thoughtImpact}
                    onChange={(e) => setThoughtImpact(e.target.value)}
                    className="w-1/2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                  />
                  <input
                    value={thoughtConfidence}
                    onChange={(e) => setThoughtConfidence(e.target.value)}
                    className="w-1/2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                  />
                </div>
              </label>
            </div>
            <label className="mt-4 block">
              <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Title</div>
              <input
                value={thoughtTitle}
                onChange={(e) => setThoughtTitle(e.target.value)}
                className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
              />
            </label>
            <label className="mt-4 block">
              <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Description</div>
              <textarea
                value={thoughtDescription}
                onChange={(e) => setThoughtDescription(e.target.value)}
                rows={3}
                className="w-full rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
              />
            </label>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <label className="block">
                <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Tender ID</div>
                <input
                  value={thoughtTenderId}
                  onChange={(e) => setThoughtTenderId(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Evidence JSON</div>
                <textarea
                  value={thoughtEvidence}
                  onChange={(e) => setThoughtEvidence(e.target.value)}
                  rows={3}
                  className="w-full rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                />
              </label>
            </div>
            <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/40">
              <div className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">Thought response</div>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-600 dark:text-slate-300">
                {thoughtResponse ? JSON.stringify(thoughtResponse, null, 2) : 'No thought proposed yet.'}
              </pre>
            </div>
          </CardShell>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <CardShell title="Thought stats" icon={LayoutGrid}>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: 'Pending', value: thoughtStats?.pending_count ?? pendingThoughts.length },
                { label: 'Approved', value: thoughtStats?.approved_count ?? thoughtHistory.length },
                { label: 'Rejected', value: thoughtStats?.rejected_count ?? 0 },
                { label: 'Auto-exec', value: thoughtStats?.auto_executed_count ?? 0 },
              ].map((item) => (
                <div key={item.label} className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/40">
                  <div className="text-xs uppercase tracking-[0.2em] text-slate-400">{item.label}</div>
                  <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{item.value}</div>
                </div>
              ))}
            </div>
          </CardShell>

          <CardShell title="Pending thoughts" icon={Clock3}>
            <div className="space-y-2">
              {pendingThoughts.slice(0, 5).map((item: any) => (
                <div key={item.id} className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/40">
                  <div className="text-sm font-medium text-slate-900 dark:text-white">{item.title}</div>
                  <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.agent_name} • {item.thought_type}</div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleThoughtAction(item.id, 'approve')}
                      disabled={actioningThoughtId === item.id}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {actioningThoughtId === item.id ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
                      Approve
                    </button>
                    <button
                      type="button"
                      onClick={() => handleThoughtAction(item.id, 'reject')}
                      disabled={actioningThoughtId === item.id}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {actioningThoughtId === item.id ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={12} />}
                      Reject
                    </button>
                  </div>
                </div>
              ))}
              {pendingThoughts.length === 0 && <div className="text-sm text-slate-400">No pending thoughts.</div>}
            </div>
          </CardShell>
          {thoughtActionError && (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/30 dark:text-rose-200">
              {thoughtActionError}
            </div>
          )}
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <CardShell title="Core function check list" icon={LayoutGrid}>
            <div className="space-y-3">
              {[
                { label: 'Agent registry', value: `${registeredAgents} detected`, ok: registeredAgents > 0 },
                { label: 'Pipeline phases', value: `${pipelinePhaseCount} detected`, ok: pipelinePhaseCount > 0 },
                { label: 'Watchdog health', value: watchdogStatus, ok: watchdogStatus === 'healthy' },
                { label: 'Engineer map', value: `${systemSummary.total_components ?? 0} components`, ok: (systemSummary.total_components ?? 0) > 0 },
                { label: 'Brain queue', value: `${brainStatus?.queue_size ?? 0}`, ok: true },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between gap-3 rounded-2xl bg-slate-50 px-4 py-3 dark:bg-slate-800/40">
                  <div>
                    <div className="text-sm font-medium text-slate-900 dark:text-white">{item.label}</div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">{item.value}</div>
                  </div>
                  <div className={`flex h-8 w-8 items-center justify-center rounded-full ${item.ok ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-300' : 'bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300'}`}>
                    {item.ok ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                  </div>
                </div>
              ))}
            </div>
          </CardShell>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <CardShell
            title="Diagnostics"
            icon={Search}
            actions={
              <button
                onClick={refreshAnalysis}
                disabled={panel.loading}
                className="inline-flex items-center gap-2 rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
              >
                <RefreshCw size={16} className={panel.loading ? 'animate-spin' : ''} />
                Run checks
              </button>
            }
          >
            <div className="grid gap-4 md:grid-cols-2">
              <label className="block">
                <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Source</div>
                <input
                  value={diagnosticSource}
                  onChange={(e) => setDiagnosticSource(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                  placeholder="agent-014-award-intelligence"
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Error type</div>
                <input
                  value={diagnosticType}
                  onChange={(e) => setDiagnosticType(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                  placeholder="RuntimeError"
                />
              </label>
            </div>
            <label className="mt-4 block">
              <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Error message</div>
              <textarea
                value={diagnosticMessage}
                onChange={(e) => setDiagnosticMessage(e.target.value)}
                rows={4}
                className="w-full rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
              />
            </label>
            <label className="mt-4 block">
              <div className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Context JSON</div>
              <textarea
                value={diagnosticContext}
                onChange={(e) => setDiagnosticContext(e.target.value)}
                rows={4}
                className="w-full rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-0 focus:border-primary-400 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                placeholder='{"tender_id":"T-001"}'
              />
            </label>

            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/40">
                <div className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">Watchdog analysis</div>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-600 dark:text-slate-300">
                  {watchdogAnalysis ? JSON.stringify(watchdogAnalysis, null, 2) : 'No analysis run yet.'}
                </pre>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/40">
                <div className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">Engineer diagnosis</div>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-600 dark:text-slate-300">
                  {engineerAnalysis ? JSON.stringify(engineerAnalysis, null, 2) : 'No diagnosis run yet.'}
                </pre>
              </div>
            </div>
          </CardShell>

          <div className="space-y-6">
            <CardShell title="Recent errors" icon={AlertTriangle}>
              <div className="space-y-2">
                {watchdogErrors.slice(0, 6).map((entry: any) => (
                  <div key={entry.id} className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-medium text-slate-900 dark:text-white">{entry.source}</div>
                      <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500 dark:bg-slate-900 dark:text-slate-300">
                        {entry.severity || 'error'}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{entry.error_message || entry.msg}</div>
                  </div>
                ))}
                {watchdogErrors.length === 0 && <div className="text-sm text-slate-400">No errors returned by the API.</div>}
              </div>
            </CardShell>

            <CardShell title="Recent sessions" icon={Clock3}>
              <div className="space-y-2">
                {watchdogSessions.slice(0, 6).map((entry: any) => (
                  <div key={entry.session_id || entry.timestamp} className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <div className="text-sm font-medium text-slate-900 dark:text-white">{entry.session_id || 'session'}</div>
                    <div className="mt-1 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                      <span>{entry.status || 'ok'}</span>
                      <span>{entry.timestamp || '—'}</span>
                    </div>
                  </div>
                ))}
                {watchdogSessions.length === 0 && <div className="text-sm text-slate-400">No sessions returned by the API.</div>}
              </div>
            </CardShell>
          </div>
        </div>
      </div>
    </div>
  );
}
