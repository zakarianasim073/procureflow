import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import {
  LayoutDashboard, BrainCircuit, Building2, Database, TrendingUp,
  BarChart3, FileText, Cpu, AlertTriangle, Shield, GitBranch,
  Send, HardDrive, BookOpen, Activity, PlayCircle, CheckCircle2
} from 'lucide-react';
import { getExecutiveOverview, getExecutiveReport } from '../api/client';
import { getThemeClasses } from '../utils/styleMaps';

interface ExecutiveData {
  slt: { total_evaluations: number; evaluations: any[] };
  agents: { total: number; by_phase: Record<string, number>; phase_labels: Record<string, string>; agent_list: any[] };
  bwdb: { tenders_scanned: number; bwdb_matches: number; alerts: any[]; alert_count: number };
  embedding: { knowledge_total: number; by_domain: Record<string, number> };
  pipeline: { phases: any[]; total_agents_phased: number };
  predictions: { total_predictions: number; contractors_with_data: number };
  cross_check: { status: string; total_predictions: number; indexed_awards: number };
  npp: { total_npp_records: number; by_agency: Record<string, number>; agencies_with_data: string[] };
  documents: { reports_generated: number; services_available: string[] };
  storage: { knowledge_lake: number; bwdb_records: number; econtracts_records: number };
  timestamp: string;
}

function getExplanationText(explanation: any) {
  if (!explanation) return '';
  if (typeof explanation === 'string') return explanation;
  return explanation.summary || explanation.text || explanation.message || explanation.reason || explanation.note || '';
}

function getMetricValue(value: any, digits = 3) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value.toFixed(digits).replace(/\.?0+$/, '');
  }
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function formatPercent(value: any, digits = 1) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    const scaled = value <= 1 ? value * 100 : value;
    return `${scaled.toFixed(digits).replace(/\.0+$/, '')}%`;
  }
  if (typeof value === 'string' && value.trim()) return value;
  return '—';
}

function FactorList({ title, factors }: { title: string; factors: any[] }) {
  const rows = Array.isArray(factors) ? factors.slice(0, 4) : [];
  return (
    <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white/60 dark:bg-gray-900/20 p-3">
      <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-2">{title}</div>
      {rows.length > 0 ? (
        <div className="space-y-2">
          {rows.map((factor, idx) => {
            const impact = typeof factor?.impact_logit === 'number' ? factor.impact_logit : 0;
            const label = String(factor?.feature || 'feature').replace(/_/g, ' ');
            return (
              <div key={`${title}-${idx}`} className="flex items-start justify-between gap-2 text-xs">
                <div className="min-w-0">
                  <div className="font-medium text-gray-900 dark:text-white capitalize">{label}</div>
                  <div className="text-gray-400">{factor?.direction || 'neutral'}</div>
                </div>
                <div className={`shrink-0 font-semibold ${impact > 0 ? 'text-green-600' : impact < 0 ? 'text-red-600' : 'text-gray-500'}`}>
                  {impact > 0 ? '+' : ''}
                  {impact.toFixed(3)}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-xs text-gray-400">No contributions available.</div>
      )}
    </div>
  );
}

function latestTemporalSlice(series: any) {
  if (!Array.isArray(series) || series.length === 0) return null;
  return series[series.length - 1];
}

function buildTemporalValidationSeries(winSeries: any[], sltSeries: any[]) {
  const series = new Map<string, any>();
  for (const item of Array.isArray(winSeries) ? winSeries : []) {
    if (!item?.period) continue;
    series.set(item.period, {
      period: item.period,
      win_avg_prob: item.avg_prob,
      win_brier: item.brier,
      win_n: item.n,
    });
  }
  for (const item of Array.isArray(sltSeries) ? sltSeries : []) {
    if (!item?.period) continue;
    const current = series.get(item.period) || { period: item.period };
    series.set(item.period, {
      ...current,
      slt_avg_prob: item.avg_prob,
      slt_brier: item.brier,
      slt_n: item.n,
    });
  }
  return Array.from(series.values()).sort((a, b) => String(a.period).localeCompare(String(b.period)));
}

function buildDriftAlert(aggregate: any, latest: any) {
  if (!aggregate || !latest) return null;
  const baseline = typeof aggregate?.brier === 'number' ? aggregate.brier : null;
  const latestBrier = typeof latest?.brier === 'number' ? latest.brier : null;
  if (baseline === null || latestBrier === null) return null;
  const delta = latestBrier - baseline;
  const pct = baseline > 0 ? (delta / baseline) * 100 : 0;
  if (delta > 0.02 || pct > 15) {
    return {
      tone: 'red',
      title: 'Drift alert',
      message: `${latest.period} Brier worsened by ${getMetricValue(delta, 3)} (${getMetricValue(pct, 1)}%) vs aggregate.`,
    };
  }
  if (delta > 0.01 || pct > 7.5) {
    return {
      tone: 'amber',
      title: 'Drift watch',
      message: `${latest.period} Brier is up by ${getMetricValue(delta, 3)} (${getMetricValue(pct, 1)}%) vs aggregate.`,
    };
  }
  return {
    tone: 'green',
    title: 'Drift stable',
    message: `${latest.period} Brier is ${getMetricValue(Math.abs(delta), 3)} ${delta <= 0 ? 'below' : 'above'} aggregate.`,
  };
}

export default function ExecutiveDashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<ExecutiveData | null>(null);
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reportLoading, setReportLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    getExecutiveOverview()
      .then(res => setData(res.data ?? res))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));

    setReportLoading(true);
    getExecutiveReport()
      .then(res => setReport(res.report || res.data?.report))
      .catch(() => {})
      .finally(() => setReportLoading(false));
  }, []);

  if (loading) return (
    <div className="p-8 flex items-center justify-center min-h-[400px]">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
    </div>
  );

  if (error) return (
    <div className="p-8 text-center text-red-500 min-h-[400px] flex flex-col items-center justify-center">
      <AlertTriangle size={40} className="mb-3 opacity-50" />
      <p>Failed to load executive overview: {error}</p>
    </div>
  );

  if (!data) return null;

  const domainIcons: Record<string, any> = {
    tenders: Building2, awards: BarChart3, npp: TrendingUp,
    app: FileText, matches: GitBranch, contractor_dna: BrainCircuit,
    contractor_aliases: BookOpen,
  };
  const domainColors: Record<string, string> = {
    tenders: 'blue', awards: 'green', npp: 'purple',
    app: 'orange', matches: 'indigo', contractor_dna: 'pink',
    contractor_aliases: 'teal',
  };

  const nppAgencies = Object.entries(data.npp.by_agency).sort((a, b) => b[1] - a[1]);
  const latestWinSlice = latestTemporalSlice(report?.model_intelligence?.model_report?.summary?.temporal_validation?.win);
  const latestSltSlice = latestTemporalSlice(report?.model_intelligence?.model_report?.summary?.temporal_validation?.slt);
  const temporalValidationSeries = buildTemporalValidationSeries(
    report?.model_intelligence?.model_report?.summary?.temporal_validation?.win,
    report?.model_intelligence?.model_report?.summary?.temporal_validation?.slt,
  );
  const winAggregate = report?.model_intelligence?.model_report?.summary?.validation?.win || report?.model_intelligence?.model_report?.validation?.win;
  const driftAlert = buildDriftAlert(winAggregate, latestWinSlice);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <LayoutDashboard className="text-primary-600" size={28} />
            Executive Dashboard
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            System-wide intelligence overview — Knowledge Lake, NPP, Pipeline & Storage
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <Activity size={14} />
          {new Date(data.timestamp).toLocaleString()}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-8">
        <StatCard icon={BrainCircuit} label="Agents" value={data.agents.total} color="indigo" />
        <StatCard icon={Database} label="Knowledge Lake" value={data.embedding.knowledge_total} color="blue" />
        <StatCard icon={Building2} label="Tenders Scanned" value={data.bwdb.tenders_scanned} color="cyan" />
        <StatCard icon={GitBranch} label="BWDB Matches" value={data.bwdb.bwdb_matches} color="purple" />
        <StatCard icon={TrendingUp} label="NPP Records" value={data.npp.total_npp_records} color="green" />
        <StatCard icon={Shield} label="SLT Evals" value={data.slt.total_evaluations} color="orange" />
      </div>

      {driftAlert && (
        <div className={`mb-6 p-3 rounded-lg border text-sm ${
          driftAlert.tone === 'red'
            ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800'
            : driftAlert.tone === 'amber'
            ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800'
            : 'bg-green-50 dark:bg-green-900/10 text-green-700 dark:text-green-300 border-green-200 dark:border-green-800'
        }`}>
          <div className="font-semibold">{driftAlert.title}</div>
          <div className="text-xs mt-1">{driftAlert.message}</div>
        </div>
      )}

      {/* AI Decision Support Report for Procurement Head */}
      {report && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-8 shadow-sm">
          <div className="flex items-center gap-2 mb-6 border-b border-gray-100 dark:border-gray-700 pb-4">
            <BrainCircuit className="text-primary-600 animate-pulse" size={24} />
            <div>
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">Procurement Head Decision Support Report</h2>
              <p className="text-xs text-gray-400">Synthesized intelligence report from all pipeline agents</p>
            </div>
          </div>
          
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Bid Suggestion & Win Prediction */}
            <div className="lg:col-span-2 space-y-6">
              <div className="p-4 rounded-xl bg-primary-50 dark:bg-primary-900/10 border border-primary-100 dark:border-primary-900/30">
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <h3 className="text-xs font-bold text-primary-500 uppercase tracking-wider">AI Bid Suggestion</h3>
                    <div className="text-lg font-bold text-gray-900 dark:text-white mt-1">{report.bid_suggestion.decision}</div>
                  </div>
                  <div className="text-right">
                    <span className="text-xs text-gray-400">Optimal Discount</span>
                    <div className="text-lg font-extrabold text-primary-600 dark:text-primary-400">{report.bid_suggestion.optimal_discount}</div>
                  </div>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-2 italic">"{report.bid_suggestion.strategy}"</p>
              </div>

              <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-900/25 border border-gray-100 dark:border-gray-700/50">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Win Probability Model</h3>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                    report.win_prediction.confidence === 'High' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' :
                    report.win_prediction.confidence === 'Medium' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' :
                    'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300'
                  }`}>
                    {report.win_prediction.confidence} Confidence
                  </span>
                </div>
                <div className="flex items-baseline gap-2 mb-3">
                  <span className="text-3xl font-extrabold text-gray-900 dark:text-white">{report.win_prediction.probability}</span>
                  <span className="text-xs text-gray-400 font-normal"> estimated chance</span>
                </div>
                <div className="space-y-1.5">
                  <div className="text-xs font-medium text-gray-500 dark:text-gray-400">Key Supporting Factors:</div>
                  {report.win_prediction.factors.map((f: string, idx: number) => (
                    <div key={idx} className="flex items-start gap-2 text-xs text-gray-600 dark:text-gray-300">
                      <CheckCircle2 size={12} className="text-green-500 mt-0.5 shrink-0" />
                      <span>{f}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-4 rounded-xl bg-indigo-50 dark:bg-indigo-900/10 border border-indigo-100 dark:border-indigo-900/30">
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <h3 className="text-xs font-bold text-indigo-500 uppercase tracking-wider">Model Intelligence</h3>
                    <div className="text-lg font-bold text-gray-900 dark:text-white mt-1">
                      Win {report.model_intelligence?.win_probability ?? '—'} · SLT risk {formatPercent(report.model_intelligence?.slt_risk)}
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-xs text-gray-400">Confidence</span>
                    <div className="text-sm font-semibold text-indigo-600 dark:text-indigo-300">{report.model_intelligence?.confidence || '—'}</div>
                  </div>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  {getExplanationText(report.model_intelligence?.explanation) || 'Rules-first scoring with calibrated probability estimates.'}
                </p>
                <div className="grid grid-cols-2 gap-2 mt-4 text-xs text-gray-600 dark:text-gray-300">
                  <div className="p-2 rounded-lg bg-white/70 dark:bg-gray-900/20 border border-gray-100 dark:border-gray-700">
                    <div className="text-[10px] uppercase tracking-wider text-gray-400">Evidence</div>
                    <div className="font-semibold text-gray-900 dark:text-white">{getMetricValue(report.model_intelligence?.evidence?.score, 2)}</div>
                  </div>
                  <div className="p-2 rounded-lg bg-white/70 dark:bg-gray-900/20 border border-gray-100 dark:border-gray-700">
                    <div className="text-[10px] uppercase tracking-wider text-gray-400">Version</div>
                    <div className="font-semibold text-gray-900 dark:text-white">{report.model_intelligence?.model_report?.model_version || report.model_intelligence?.model_version || '—'}</div>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-3">
                  <FactorList title="Win drivers" factors={report.model_intelligence?.factors?.win || []} />
                  <FactorList title="SLT drivers" factors={report.model_intelligence?.factors?.slt || []} />
                </div>
                {latestWinSlice && (
                  <div className="mt-3 p-3 rounded-lg bg-white/70 dark:bg-gray-900/20 border border-gray-100 dark:border-gray-700 text-xs">
                    <div className="font-bold uppercase tracking-wider text-gray-400 mb-1">Latest month</div>
                    <div className="text-gray-700 dark:text-gray-200">
                      {latestWinSlice.period}: {getMetricValue(latestWinSlice.avg_prob, 3)} avg prob, {getMetricValue(latestWinSlice.brier, 3)} Brier, n={getMetricValue(latestWinSlice.n, 0)}
                    </div>
                    {latestSltSlice && (
                      <div className="text-gray-500 dark:text-gray-400 mt-1">
                        SLT {getMetricValue(latestSltSlice.avg_prob, 3)} avg prob, {getMetricValue(latestSltSlice.brier, 3)} Brier
                      </div>
                    )}
                  </div>
                )}
                {temporalValidationSeries.length > 0 && (
                  <div className="mt-3 p-3 rounded-lg bg-white/70 dark:bg-gray-900/20 border border-gray-100 dark:border-gray-700">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-2">Temporal validation chart</div>
                    <ResponsiveContainer width="100%" height={220}>
                      <LineChart data={temporalValidationSeries}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                        <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                        <YAxis domain={[0, 1]} tick={{ fontSize: 10 }} />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="win_avg_prob" name="Win avg prob" stroke="#2563eb" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="slt_avg_prob" name="SLT avg prob" stroke="#f97316" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="win_brier" name="Win Brier" stroke="#16a34a" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="slt_brier" name="SLT Brier" stroke="#dc2626" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            </div>

            {/* BOQ & Market Rate Analysis */}
            <div className="space-y-6">
              {/* BOQ Analysis */}
              <div className="p-4 rounded-xl border border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-900/10">
                <h3 className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">BOQ Intelligence</h3>
                {report.boq_analysis.compared ? (
                  <div className="space-y-3">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">Items Scanned:</span>
                      <span className="font-semibold text-gray-900 dark:text-white">{report.boq_analysis.items}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">At SOR Rate:</span>
                      <span className="font-semibold text-green-600">{report.boq_analysis.matches}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">Rate Variances:</span>
                      <span className="font-semibold text-yellow-600">{report.boq_analysis.variances}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">Unmatched/Mismatches:</span>
                      <span className="font-semibold text-red-600">{report.boq_analysis.mismatches}</span>
                    </div>
                    <button 
                      onClick={() => navigate('/results')}
                      className="w-full text-center mt-2 px-3 py-1.5 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-xs font-medium rounded-lg text-gray-700 dark:text-gray-300 transition-colors"
                    >
                      View Full BOQ Analysis
                    </button>
                  </div>
                ) : (
                  <div className="text-center py-6 text-sm text-gray-400">
                    No active BOQ comparison found.
                    <button 
                      onClick={() => navigate('/upload')}
                      className="mt-3 px-3 py-1.5 bg-primary-600 hover:bg-primary-700 text-white text-xs font-medium rounded-lg block mx-auto transition-colors"
                    >
                      Upload & Compare BOQ
                    </button>
                  </div>
                )}
              </div>

              {/* Market Rate Analysis */}
              <div className="p-4 rounded-xl border border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-900/10">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Market Price Index</h3>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-bold ${
                    report.market_rate.trend === 'stable' ? 'bg-green-100 text-green-700 dark:bg-green-900/30' : 'bg-red-100 text-red-700 dark:bg-red-900/30'
                  }`}>
                    {report.market_rate.trend}
                  </span>
                </div>
                <div className="flex items-baseline gap-2 mb-2">
                  <span className="text-2xl font-bold text-gray-900 dark:text-white">{report.market_rate.deviation_pct}</span>
                  <span className="text-xs text-gray-400 font-normal"> variance from SOR</span>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{report.market_rate.notes}</p>
              </div>

              <div className="p-4 rounded-xl border border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-900/10">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Model Health</h3>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-bold ${
                    report.model_intelligence?.model_report?.trained ? 'bg-green-100 text-green-700 dark:bg-green-900/30' : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30'
                  }`}>
                    {report.model_intelligence?.model_report?.trained ? 'trained' : 'pending'}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <div className="text-gray-500 text-xs">Win AUC</div>
                    <div className="font-semibold text-gray-900 dark:text-white">{getMetricValue(report.model_intelligence?.model_report?.summary?.win_auc || report.model_intelligence?.model_report?.win_auc || report.model_intelligence?.model_report?.metrics?.win_auc)}</div>
                  </div>
                  <div>
                    <div className="text-gray-500 text-xs">SLT Recall</div>
                    <div className="font-semibold text-gray-900 dark:text-white">{getMetricValue(report.model_intelligence?.model_report?.summary?.slt_recall || report.model_intelligence?.model_report?.slt_recall || report.model_intelligence?.model_report?.metrics?.slt_recall)}</div>
                  </div>
                  <div>
                    <div className="text-gray-500 text-xs">Brier</div>
                    <div className="font-semibold text-gray-900 dark:text-white">{getMetricValue(report.model_intelligence?.model_report?.summary?.win_brier || report.model_intelligence?.model_report?.win_brier || report.model_intelligence?.model_report?.metrics?.win_brier)}</div>
                  </div>
                  <div>
                    <div className="text-gray-500 text-xs">Rows</div>
                    <div className="font-semibold text-gray-900 dark:text-white">{getMetricValue(report.model_intelligence?.model_report?.dataset?.train_samples || report.model_intelligence?.model_report?.dataset?.records || report.model_intelligence?.model_report?.dataset?.samples, 0)}</div>
                  </div>
                </div>
                {Array.isArray(report.model_intelligence?.model_report?.summary?.temporal_validation?.win) && report.model_intelligence.model_report.summary.temporal_validation.win.length > 0 && (
                  <div className="mt-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-900/20 border border-slate-100 dark:border-slate-700">
                    <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1">Temporal validation</div>
                    <div className="text-xs text-slate-700 dark:text-slate-300">
                      {report.model_intelligence.model_report.summary.temporal_validation.win.length} monthly slices tracked for drift and calibration.
                    </div>
                  </div>
                )}
                {Array.isArray(report.model_intelligence?.model_report?.summary?.audit?.warnings) && report.model_intelligence.model_report.summary.audit.warnings.length > 0 && (
                  <div className="mt-3 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/10 border border-amber-100 dark:border-amber-900/30">
                    <div className="text-[10px] uppercase tracking-wider font-bold text-amber-600 mb-2">Audit warnings</div>
                    <div className="space-y-1">
                      {report.model_intelligence.model_report.summary.audit.warnings.slice(0, 3).map((warning: string, idx: number) => (
                        <div key={idx} className="text-xs text-amber-800 dark:text-amber-200">{warning}</div>
                      ))}
                    </div>
                  </div>
                )}
                {Array.isArray(report.model_intelligence?.model_report?.summary?.audit?.notes) && report.model_intelligence.model_report.summary.audit.notes.length > 0 && (
                  <div className="mt-3 p-3 rounded-lg bg-blue-50 dark:bg-blue-900/10 border border-blue-100 dark:border-blue-900/30">
                    <div className="text-[10px] uppercase tracking-wider font-bold text-blue-600 mb-2">Audit notes</div>
                    <div className="space-y-1">
                      {report.model_intelligence.model_report.summary.audit.notes.slice(0, 3).map((note: string, idx: number) => (
                        <div key={idx} className="text-xs text-blue-800 dark:text-blue-200">{note}</div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Procurement Head Final Recommendation */}
          <div className="mt-6 pt-5 border-t border-gray-100 dark:border-gray-700 flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
            <div className="flex-1 min-w-0">
              <span className="text-[10px] uppercase tracking-wider font-bold text-gray-400">Procurement Head Decision Support Summary</span>
              <p className="text-sm font-medium text-gray-800 dark:text-gray-200 mt-1">{report.procurement_head_decision.summary}</p>
            </div>
            <div className="flex flex-col items-start gap-2">
              <button
                type="button"
                disabled
                title="Approval workflow is available in the admin approvals screen."
                className="px-4 py-2 bg-green-600/50 text-white rounded-lg text-xs font-semibold shadow-sm cursor-not-allowed opacity-80"
              >
                Approve Bid Package
              </button>
              <span className="text-[10px] text-gray-400">Use Admin → Approvals for the persisted workflow.</span>
              <div className="flex gap-2">
              <button 
                onClick={() => navigate('/chat')}
                className="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg text-xs font-semibold transition-colors"
              >
                Consult AI Assistant
              </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <BookOpen size={18} className="text-primary-600" />
            Knowledge Lake — Domain Breakdown
          </h3>
          <div className="space-y-2">
            {Object.entries(data.embedding.by_domain).map(([domain, count]) => {
              const Icon = domainIcons[domain] || FileText;
                const color = domainColors[domain] || 'gray';
                const tone = getThemeClasses(color);
              const maxCount = Math.max(...Object.values(data.embedding.by_domain), 1);
              return (
                <div key={domain} className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-lg ${tone.panel} flex items-center justify-center`}>
                      <Icon size={16} className={tone.icon} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between text-sm">
                      <span className="font-medium text-gray-700 dark:text-gray-300 capitalize">{domain.replace(/_/g, ' ')}</span>
                      <span className="text-gray-500">{count}</span>
                    </div>
                    <div className="w-full h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full mt-1">
                        <div className={`h-full rounded-full ${tone.fill}`} style={{ width: `${(count / maxCount) * 100}%` }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <TrendingUp size={18} className="text-primary-600" />
            NPP Statistics by Agency
          </h3>
          {nppAgencies.length > 0 ? (
            <div className="space-y-2">
              {nppAgencies.map(([agency, count]) => (
                <div key={agency} className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                    <Building2 size={16} className="text-green-600 dark:text-green-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between text-sm">
                      <span className="font-medium text-gray-700 dark:text-gray-300">{agency}</span>
                      <span className="text-gray-500">{count.toLocaleString()}</span>
                    </div>
                    <div className="w-full h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full mt-1">
                      <div className="h-full rounded-full bg-green-500" style={{ width: `${(count / Math.max(...nppAgencies.map(a => a[1]), 1)) * 100}%` }} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 text-center py-8">No NPP data available</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <HardDrive size={18} className="text-primary-600" />
            Storage Overview
          </h3>
          <div className="grid grid-cols-3 gap-4">
            {[ 
              { label: 'Knowledge Lake', value: data.storage.knowledge_lake, icon: Database, color: 'blue' },
              { label: 'BWDB Records', value: data.storage.bwdb_records, icon: GitBranch, color: 'purple' },
              { label: 'EContracts', value: data.storage.econtracts_records, icon: FileText, color: 'green' },
            ].map((item, i) => {
              const tone = getThemeClasses(item.color);
              return (
                <div key={i} className={`p-4 rounded-xl ${tone.panel} ${tone.border} text-center`}>
                  <item.icon size={24} className={`${tone.icon} mx-auto mb-2`} />
                  <div className={`text-xl font-bold ${tone.text}`}>{item.value}</div>
                  <div className={`text-xs ${tone.text} mt-1`}>{item.label}</div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <Cpu size={18} className="text-primary-600" />
            Agents & Pipeline
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800">
              <div className="flex items-center gap-2 mb-2">
                <Cpu size={18} className="text-indigo-600 dark:text-indigo-400" />
                <span className="text-sm font-medium text-indigo-700 dark:text-indigo-300">Total Agents</span>
              </div>
              <div className="text-2xl font-bold text-indigo-800 dark:text-indigo-200">{data.agents.total}</div>
            </div>
            <div className="p-4 rounded-xl bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800">
              <div className="flex items-center gap-2 mb-2">
                <GitBranch size={18} className="text-purple-600 dark:text-purple-400" />
                <span className="text-sm font-medium text-purple-700 dark:text-purple-300">Pipeline Phased</span>
              </div>
              <div className="text-2xl font-bold text-purple-800 dark:text-purple-200">{data.pipeline.total_agents_phased}</div>
            </div>
            <div className="p-4 rounded-xl bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
              <div className="flex items-center gap-2 mb-2">
                <BarChart3 size={18} className="text-green-600 dark:text-green-400" />
                <span className="text-sm font-medium text-green-700 dark:text-green-300">Predictions</span>
              </div>
              <div className="text-2xl font-bold text-green-800 dark:text-green-200">{data.predictions.total_predictions}</div>
            </div>
            <div className="p-4 rounded-xl bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800">
              <div className="flex items-center gap-2 mb-2">
                <BrainCircuit size={18} className="text-orange-600 dark:text-orange-400" />
                <span className="text-sm font-medium text-orange-700 dark:text-orange-300">Contractor DNA</span>
              </div>
              <div className="text-2xl font-bold text-orange-800 dark:text-orange-200">{data.predictions.contractors_with_data}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <FileText size={18} className="text-primary-600" />
            Documents & Services
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-teal-50 dark:bg-teal-900/20">
              <div className="text-sm text-teal-700 dark:text-teal-300">Reports Generated</div>
              <div className="text-2xl font-bold text-teal-800 dark:text-teal-200">{data.documents.reports_generated}</div>
            </div>
            <div className="p-4 rounded-xl bg-cyan-50 dark:bg-cyan-900/20">
              <div className="text-sm text-cyan-700 dark:text-cyan-300">Services</div>
              <div className="text-lg font-bold text-cyan-800 dark:text-cyan-200">{data.documents.services_available.length}</div>
            </div>
          </div>
          <div className="mt-4 space-y-1">
            {data.documents.services_available.map(s => (
              <div key={s} className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <CheckCircle2 size={12} className="text-green-500" /> {s}
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <PlayCircle size={18} className="text-primary-600" />
            Quick Actions
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {[
              { label: 'Agent Pipeline', icon: GitBranch, to: '/agents', color: 'purple' },
              { label: 'PPR 2025', icon: Shield, to: '/ppr2025', color: 'indigo' },
              { label: 'Analytics', icon: TrendingUp, to: '/analytics', color: 'green' },
              { label: 'SLT Dashboard', icon: BarChart3, to: '/slt-dashboard', color: 'blue' },
              { label: 'Data Intel', icon: Database, to: '/data-intelligence', color: 'cyan' },
              { label: 'BWDB Monitor', icon: AlertTriangle, to: '/bwdb-monitor', color: 'yellow' },
            ].map((item, i) => {
              const tone = getThemeClasses(item.color);
              return (
                <button
                  key={i}
                  onClick={() => navigate(item.to)}
                  className={`p-4 rounded-xl ${tone.panel} ${tone.border} hover:scale-[1.02] transition-all text-center`}
                >
                  <item.icon size={20} className={`${tone.icon} mx-auto mb-1`} />
                  <div className={`text-xs font-medium ${tone.text}`}>{item.label}</div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color }: { icon: any; label: string; value: number; color: string }) {
  const tone = getThemeClasses(color);
  return (
    <div className={`bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
        <Icon size={20} className={tone.icon} />
        {value ?? '—'}
      </div>
    </div>
  );
}
