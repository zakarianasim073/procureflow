import { useEffect, useState } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, AreaChart, Area, PieChart, Pie, Cell
} from 'recharts';
import {
  Shield, TrendingDown, Award, Target, Building2,
  Users, FileText, CheckSquare, AlertTriangle, RefreshCw, BrainCircuit,
  BarChart3, Activity, ClipboardList, FileCheck, Database, X
} from 'lucide-react';
import {
  getPprOverview, getPprNppTrends, getPprAwardStats, getPprPredictions,
  getPprContractors, getPprRates, getPprDocumentChecklist, getPprEvaluations,
  evaluatePprTec, evaluatePprFinancial, evaluatePprWorks,
} from '../api/client';

const AGENCY_COLORS: Record<string, string> = {
  BBA: '#2563eb', BWDB: '#059669', LGED: '#7c3aed', PWD: '#d97706', RHD: '#dc2626',
};
const MONTH_OPTIONS = [
  { value: 12, label: '1Y' }, { value: 24, label: '2Y' }, { value: 60, label: '5Y' }, { value: 120, label: 'All' },
];
const TABS = [
  { id: 'overview', label: 'Overview', icon: BarChart3 },
  { id: 'tec', label: 'TEC Evaluation', icon: ClipboardList },
  { id: 'ppr', label: 'PPR Evaluation', icon: FileCheck },
  { id: 'slt', label: 'Works Evaluation', icon: AlertTriangle },
  { id: 'documents', label: 'Documents', icon: FileText },
];

function formatBDT(n: number) {
  if (n >= 1e7) return `BDT ${(n / 1e7).toFixed(1)} Cr`;
  if (n >= 1e5) return `BDT ${(n / 1e5).toFixed(1)} L`;
  return `BDT ${n.toLocaleString('en-IN')}`;
}

function KpiCard({ title, value, icon, color, subtitle }: any) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2.5 rounded-lg ${color}`}>{icon}</div>
        <div>
          <div className="text-xs text-gray-500 dark:text-gray-400">{title}</div>
          <div className="text-xl font-bold text-gray-900 dark:text-white">{value ?? '—'}</div>
          {subtitle && <div className="text-xs text-gray-400">{subtitle}</div>}
        </div>
      </div>
    </div>
  );
}

function ChartCard({ title, children, className }: any) {
  return (
    <div className={`bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 ${className || ''}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900 dark:text-white">{title}</h3>
      </div>
      {children}
    </div>
  );
}

function FactorList({ title, factors }: { title: string; factors: any[] }) {
  const rows = Array.isArray(factors) ? factors.slice(0, 4) : [];
  return (
    <div className="rounded-xl border border-gray-100 dark:border-gray-700 bg-gray-50/60 dark:bg-gray-900/20 p-3">
      <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-2">{title}</div>
      {rows.length > 0 ? (
        <div className="space-y-2">
          {rows.map((factor, idx) => {
            const impact = typeof factor?.impact_logit === 'number' ? factor.impact_logit : 0;
            const isPositive = impact > 0;
            const label = String(factor?.feature || 'feature').replace(/_/g, ' ');
            return (
              <div key={`${title}-${idx}`} className="flex items-start justify-between gap-2 text-xs">
                <div className="min-w-0">
                  <div className="font-medium text-gray-900 dark:text-white capitalize">{label}</div>
                  <div className="text-gray-400">{factor?.direction || 'neutral'}</div>
                </div>
                <div className={`shrink-0 font-semibold ${isPositive ? 'text-green-600' : impact < 0 ? 'text-red-600' : 'text-gray-500'}`}>
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

export default function PPR2025Dashboard() {
  const [activeTab, setActiveTab] = useState('overview');
  const [months, setMonths] = useState(24);
  const [overview, setOverview] = useState<any>(null);
  const [nppTrends, setNppTrends] = useState<any[]>([]);
  const [predictions, setPredictions] = useState<any[]>([]);
  const [contractors, setContractors] = useState<any[]>([]);
  const [contractorTotal, setContractorTotal] = useState(0);
  const [rateData, setRateData] = useState<any>(null);
  const [awardSummary, setAwardSummary] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedAgency, setSelectedAgency] = useState('');

  const [tecVendor, setTecVendor] = useState('Test Contractor Ltd.');
  const [tecTenderId, setTecTenderId] = useState('TEC-TEST-001');
  const [tecType, setTecType] = useState('works');
  const [tecExperience, setTecExperience] = useState('8');
  const [tecTurnover, setTecTurnover] = useState('50000000');
  const [tecContracts, setTecContracts] = useState('5');
  const [tecResult, setTecResult] = useState<any>(null);
  const [tecLoading, setTecLoading] = useState(false);

  const [pprBidPrice, setPprBidPrice] = useState('4800000');
  const [pprEstimate, setPprEstimate] = useState('5000000');
  const [pprBidSecurity, setPprBidSecurity] = useState('500000');
  const [pprValidity, setPprValidity] = useState('90');
  const [pprResult, setPprResult] = useState<any>(null);
  const [pprLoading, setPprLoading] = useState(false);

  const [sltEstimate, setSltEstimate] = useState('5000000');
  const [sltBidPrice, setSltBidPrice] = useState('3500000');
  const [sltTenderOpenDate, setSltTenderOpenDate] = useState(new Date().toISOString().slice(0, 10));
  const [sltAgency, setSltAgency] = useState('BWDB');
  const [sltDistrict, setSltDistrict] = useState('');
  const [sltMethod, setSltMethod] = useState('OTM');
  const [sltWorkType, setSltWorkType] = useState('Works');
  const [sltCustomNppDefinitionId, setSltCustomNppDefinitionId] = useState('custom_npp');
  const [sltBidderName, setSltBidderName] = useState('Current Bidder');
  const [sltBoqItems, setSltBoqItems] = useState('[]');
  const [sltResult, setSltResult] = useState<any>(null);
  const [sltLoading, setSltLoading] = useState(false);

  const [savedEvals, setSavedEvals] = useState<any[]>([]);
  const [evalFilter, setEvalFilter] = useState('');
  const [docType, setDocType] = useState('works');
  const [docData, setDocData] = useState<any>(null);
  const [phase1Loaded, setPhase1Loaded] = useState(false);
  const modelStatus = overview?.model_status || {};
  const modelReport = overview?.model_report || {};
  const latestWinSlice = latestTemporalSlice(modelReport?.summary?.temporal_validation?.win);
  const latestSltSlice = latestTemporalSlice(modelReport?.summary?.temporal_validation?.slt);
  const temporalValidationSeries = buildTemporalValidationSeries(
    modelReport?.summary?.temporal_validation?.win,
    modelReport?.summary?.temporal_validation?.slt,
  );
  const winAggregate = modelReport?.summary?.validation?.win || modelReport?.validation?.win;
  const driftAlert = buildDriftAlert(winAggregate, latestWinSlice);

  const loadAll = async (m: number) => {
    setLoading(true); setError('');
    setPhase1Loaded(false);
    try {
      const [ov, npp, awStats] = await Promise.all([
        getPprOverview().then(r => r.data),
        getPprNppTrends(m, selectedAgency || undefined).then(r => r.data),
        getPprAwardStats().then(r => r.data),
      ]);
      setOverview(ov); setNppTrends(npp.trends || []); setAwardSummary(awStats.summary || []);
      setPhase1Loaded(true);
      const [pred, contr, rates] = await Promise.all([
        getPprPredictions().then(r => r.data),
        getPprContractors(15).then(r => r.data),
        getPprRates().then(r => r.data),
      ]);
      setPredictions(pred.predictions || []);
      setContractors(contr.contractors || []); setContractorTotal(contr.total || 0);
      setRateData(rates);
      const [docs, evals] = await Promise.all([
        getPprDocumentChecklist(docType).then(r => r.data),
        getPprEvaluations(50),
      ]);
      setDocData(docs); setSavedEvals(evals.evaluations || []);
    } catch (err: any) { setError(err.message || 'Failed to load'); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadAll(months); }, [months, selectedAgency, docType]);

  const runTecEval = async () => {
    setTecLoading(true); setTecResult(null);
    try {
      const data = await evaluatePprTec({
        vendor_name: tecVendor, tender_id: tecTenderId,
        tender_type: tecType, experience_years: parseInt(tecExperience) || 0,
        annual_turnover: parseFloat(tecTurnover) || 0, similar_contracts: parseInt(tecContracts) || 0,
        equipment_available: true, qualified_personnel: 10,
      });
      setTecResult(data.evaluation);
    } catch (err: any) { setError(err.message); }
    finally { setTecLoading(false); }
  };

  const runPprEval = async () => {
    setPprLoading(true); setPprResult(null);
    try {
      const data = await evaluatePprFinancial({
        bid_price: parseFloat(pprBidPrice) || 0, estimated_cost: parseFloat(pprEstimate) || 0,
        bid_security: parseFloat(pprBidSecurity) || 0, validity_days: parseInt(pprValidity) || 0,
      });
      setPprResult(data.evaluation);
    } catch (err: any) { setError(err.message); }
    finally { setPprLoading(false); }
  };

  const runSltEval = async () => {
    setSltLoading(true); setSltResult(null);
    try {
      let boqItems = [];
      try { boqItems = JSON.parse(sltBoqItems || '[]'); } catch {}
      const data = await evaluatePprWorks({
        tender_id: `WORKS-${Date.now()}`,
        tender_open_date: sltTenderOpenDate,
        official_estimate: parseFloat(sltEstimate) || 0,
        agency: sltAgency, district: sltDistrict, method: sltMethod,
        work_type: sltWorkType, custom_npp_definition_id: sltCustomNppDefinitionId,
        boq_items: boqItems,
        responsive_bidders: [{
          bidder_name: sltBidderName, quoted_amount: parseFloat(sltBidPrice) || 0,
          documents_complete: true, signed: true, bid_validity_days: 90,
          qualification_passed: true, bid_security_amount: Math.max((parseFloat(sltEstimate) || 0) * 0.01, 0),
          boq_items: boqItems,
        }],
      });
      setSltResult(data.evaluation);
    } catch (err: any) { setError(err.message); }
    finally { setSltLoading(false); }
  };

  if (loading && !phase1Loaded) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <div className="mb-6">
          <div className="h-8 w-64 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mb-2" />
          <div className="h-4 w-96 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 animate-pulse">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-gray-200 dark:bg-gray-700 rounded-lg" />
                <div className="flex-1"><div className="h-3 w-20 bg-gray-200 dark:bg-gray-700 rounded mb-2" /><div className="h-6 w-16 bg-gray-200 dark:bg-gray-700 rounded" /></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Shield className="text-primary-600" size={28} />
            PPR 2025 Evaluation Dashboard
          </h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-0.5">
            {overview?.total_awards?.toLocaleString()} awards · {overview?.total_npp_records?.toLocaleString()} NPP records · {overview?.total_contractors?.toLocaleString()} contractor profiles
          </p>
        </div>
        <button onClick={() => loadAll(months)} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg text-gray-400 transition-colors" title="Refresh">
          <RefreshCw size={16} />
        </button>
      </div>

      <div className="flex gap-1 mb-6 border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
        {TABS.map(tab => {
          const Icon = tab.icon;
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-primary-600 text-primary-600 dark:text-primary-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
              }`}>
              <Icon size={16} /> {tab.label}
            </button>
          );
        })}
      </div>

      {error && <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded-lg text-sm">{error}</div>}

      {driftAlert && (
        <div className={`mb-4 p-3 rounded-lg border text-sm ${
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

      {activeTab === 'overview' && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
            <KpiCard title="Awards Tracked" value={overview?.total_awards?.toLocaleString()} icon={<Award size={16} />} color="bg-blue-50 text-blue-600" />
            <KpiCard title="NPP Records" value={overview?.total_npp_records?.toLocaleString()} icon={<TrendingDown size={16} />} color="bg-green-50 text-green-600" />
            <KpiCard title="Contractor DNA" value={overview?.total_contractors?.toLocaleString()} icon={<Users size={16} />} color="bg-purple-50 text-purple-600" />
            <KpiCard title="Agencies" value={overview?.total_agencies} icon={<Building2 size={16} />} color="bg-teal-50 text-teal-600" subtitle={(overview?.agencies || []).slice(0, 5).join(', ')} />
            <KpiCard title="Award Corpus" value={(awardSummary || []).reduce((s: number, a: any) => s + a.count, 0).toLocaleString()} icon={<Database size={16} />} color="bg-red-50 text-red-600" />
            <KpiCard
              title="Model Status"
              value={modelStatus?.trained ? 'Trained' : 'Pending'}
              icon={<BrainCircuit size={16} />}
              color={modelStatus?.trained ? 'bg-indigo-50 text-indigo-600' : 'bg-yellow-50 text-yellow-600'}
              subtitle={`${getMetricValue(modelReport?.summary?.win_auc || modelReport?.win_auc || modelReport?.metrics?.win_auc, 3)} win AUC · ${getMetricValue(modelReport?.summary?.slt_recall || modelReport?.slt_recall || modelReport?.metrics?.slt_recall, 3)} SLT recall`}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            <ChartCard title="Model Intelligence" className="lg:col-span-2">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-700/30 border border-gray-100 dark:border-gray-600">
                  <div className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">Training State</div>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${modelStatus?.trained ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
                      {modelStatus?.trained ? 'Ready' : 'Not ready'}
                    </span>
                    <span className="text-xs text-gray-500">{modelStatus?.model_version || modelReport?.model_version || 'model version unavailable'}</span>
                  </div>
                  <div className="text-sm text-gray-600 dark:text-gray-300 mt-3">
                    {modelStatus?.message || modelReport?.summary?.status || 'Hybrid rules-first model with calibrated SLT and win scoring.'}
                  </div>
                </div>
                <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-700/30 border border-gray-100 dark:border-gray-600">
                  <div className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">Calibration Snapshot</div>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <div className="text-gray-500 text-xs">Win AUC</div>
                      <div className="font-semibold text-gray-900 dark:text-white">{getMetricValue(modelReport?.summary?.win_auc || modelReport?.win_auc || modelReport?.metrics?.win_auc)}</div>
                    </div>
                    <div>
                      <div className="text-gray-500 text-xs">PR-AUC</div>
                      <div className="font-semibold text-gray-900 dark:text-white">{getMetricValue(modelReport?.summary?.win_pr_auc || modelReport?.win_pr_auc || modelReport?.metrics?.win_pr_auc)}</div>
                    </div>
                    <div>
                      <div className="text-gray-500 text-xs">SLT Recall</div>
                      <div className="font-semibold text-gray-900 dark:text-white">{getMetricValue(modelReport?.summary?.slt_recall || modelReport?.slt_recall || modelReport?.metrics?.slt_recall)}</div>
                    </div>
                    <div>
                      <div className="text-gray-500 text-xs">Brier</div>
                      <div className="font-semibold text-gray-900 dark:text-white">{getMetricValue(modelReport?.summary?.win_brier || modelReport?.win_brier || modelReport?.metrics?.win_brier)}</div>
                    </div>
                    <div>
                      <div className="text-gray-500 text-xs">Calib A</div>
                      <div className="font-semibold text-gray-900 dark:text-white">{getMetricValue(modelReport?.summary?.calibration?.win?.a)}</div>
                    </div>
                    <div>
                      <div className="text-gray-500 text-xs">Calib B</div>
                      <div className="font-semibold text-gray-900 dark:text-white">{getMetricValue(modelReport?.summary?.calibration?.win?.b)}</div>
                    </div>
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
            </ChartCard>
            <ChartCard title="Evidence Notes">
              <div className="space-y-3">
                <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-900/10 border border-blue-100 dark:border-blue-900/30">
                  <div className="text-[10px] uppercase tracking-wider text-blue-500 font-bold mb-1">Data coverage</div>
                  <div className="text-sm text-gray-700 dark:text-gray-300">
                    {getMetricValue(modelReport?.dataset?.train_samples || modelReport?.dataset?.samples || modelReport?.dataset?.records)} training rows
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/10 border border-emerald-100 dark:border-emerald-900/30">
                  <div className="text-[10px] uppercase tracking-wider text-emerald-500 font-bold mb-1">Explainability</div>
                  <div className="text-sm text-gray-700 dark:text-gray-300">
                    {getExplanationText(modelReport?.summary?.explanation || modelReport?.explanation) || 'Rule-based explanations are attached to each prediction for auditability.'}
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/10 border border-amber-100 dark:border-amber-900/30">
                  <div className="text-[10px] uppercase tracking-wider text-amber-500 font-bold mb-1">Validation target</div>
                  <div className="text-sm text-gray-700 dark:text-gray-300">
                    Time-based splits with PPR 2025 as the holdout regime.
                  </div>
                </div>
                {Array.isArray(modelReport?.summary?.temporal_validation?.win) && modelReport.summary.temporal_validation.win.length > 0 && (
                  <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-900/20 border border-slate-100 dark:border-slate-700">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1">Temporal validation</div>
                    <div className="text-xs text-slate-700 dark:text-slate-300">
                      {modelReport.summary.temporal_validation.win.length} monthly slices tracked for drift and calibration.
                    </div>
                  </div>
                )}
                {Array.isArray(modelReport?.summary?.audit?.warnings) && modelReport.summary.audit.warnings.length > 0 && (
                  <div className="p-3 rounded-lg bg-orange-50 dark:bg-orange-900/10 border border-orange-100 dark:border-orange-900/30">
                    <div className="text-[10px] uppercase tracking-wider text-orange-500 font-bold mb-1">Audit warnings</div>
                    <div className="space-y-1">
                      {modelReport.summary.audit.warnings.slice(0, 3).map((w: string, idx: number) => (
                        <div key={idx} className="text-xs text-orange-800 dark:text-orange-200">{w}</div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </ChartCard>
          </div>

          <div className="flex items-center gap-2 mb-4">
            <select value={selectedAgency} onChange={(e) => setSelectedAgency(e.target.value)}
              className="px-2 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white">
              <option value="">All Agencies</option>
              {(overview?.agencies || []).map((a: string) => <option key={a} value={a}>{a}</option>)}
            </select>
            {MONTH_OPTIONS.map(opt => (
              <button key={opt.value} onClick={() => setMonths(opt.value)}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${months === opt.value ? 'bg-primary-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'}`}>
                {opt.label}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            <ChartCard title="NPP Discount Trends (Rule 89)">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={nppTrends}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="month" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 10 }} unit="%" domain={[0, 'auto']} />
                  <Tooltip formatter={(v: number) => `${v.toFixed(1)}%`} />
                  <Legend />
                  {Array.from(new Set(nppTrends.map((d: any) => d.agency))).map((a) => (
                    <Line key={a as string} type="monotone" dataKey="avg_npp" data={nppTrends.filter((d: any) => d.agency === a)} stroke={AGENCY_COLORS[a as string] || '#888'} name={a as string} strokeWidth={2} dot={false} connectNulls={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title="Award Distribution by Agency">
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie data={awardSummary} dataKey="count" nameKey="agency" cx="50%" cy="50%" outerRadius={90} label={({ agency, percent }: any) => `${agency} (${(percent * 100).toFixed(0)}%)`}>
                    {awardSummary.map((entry: any, idx: number) => (
                      <Cell key={`${entry.agency || 'agency'}-${idx}`} fill={AGENCY_COLORS[entry.agency] || '#888'} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => v.toLocaleString()} />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            <ChartCard title="Top Contractors by Wins">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={contractors.slice(0, 10)} layout="vertical" margin={{ left: 130, right: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" tick={{ fontSize: 10 }} />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 9 }} width={125} />
                  <Tooltip />
                  <Bar dataKey="total_wins" fill="#7c3aed" name="Wins" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title="PPR Bid Predictions">
              {predictions.length > 0 ? (
                <div className="space-y-2 max-h-[260px] overflow-y-auto">
                  {predictions.map((p: any, idx: number) => (
                    <div key={`${p.tender_id || 'prediction'}-${idx}`} className="p-2.5 bg-gray-50 dark:bg-gray-700/30 rounded-lg text-xs border border-gray-200 dark:border-gray-600">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono text-gray-500">{p.tender_id}</span>
                        <span className={`px-1.5 py-0.5 text-xs rounded-full font-medium ${p.prediction?.confidence === 'high' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>{p.prediction?.confidence}</span>
                      </div>
                      <div className="grid grid-cols-3 gap-1">
                        <span className="text-gray-400">{p.agency}</span>
                        <span className="font-medium text-primary-600 truncate" title={p.prediction?.winner}>{p.prediction?.winner}</span>
                        <span className="text-right text-green-600">{(p.prediction?.winning_discount * 100).toFixed(1)}% disc</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-center justify-center h-48 text-gray-400 text-sm">No predictions</div>
              )}
            </ChartCard>
          </div>

          <ChartCard title="NPP Discount Heatmap by Agency & Month">
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={nppTrends.filter((d: any) => parseInt(d.count) > 0)}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="month" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} unit="%" domain={[0, 'auto']} />
                <Tooltip formatter={(v: number) => `${v.toFixed(1)}%`} />
                <Legend />
                {Array.from(new Set(nppTrends.map((d: any) => d.agency))).map((a) => (
                  <Area key={a as string} type="monotone" dataKey="avg_npp" data={nppTrends.filter((d: any) => d.agency === a && parseInt(d.count) > 0)} stroke={AGENCY_COLORS[a as string] || '#888'} fill={AGENCY_COLORS[a as string] || '#888'} fillOpacity={0.1} name={a as string} strokeWidth={2} connectNulls={false} />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>
        </>
      )}

      {activeTab === 'tec' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
              <ClipboardList size={16} className="text-primary-600" /> TEC Evaluation — Schedule {tecType === 'works' ? '5' : tecType === 'goods' ? '4' : '6'}
            </h3>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div><label className="text-xs text-gray-500 mb-1 block">Vendor Name</label><input value={tecVendor} onChange={e => setTecVendor(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
                <div><label className="text-xs text-gray-500 mb-1 block">Tender ID</label><input value={tecTenderId} onChange={e => setTecTenderId(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="text-xs text-gray-500 mb-1 block">Tender Type</label><select value={tecType} onChange={e => setTecType(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white"><option value="works">Works</option><option value="goods">Goods</option><option value="services">Services</option></select></div>
                <div><label className="text-xs text-gray-500 mb-1 block">Experience (years)</label><input type="number" value={tecExperience} onChange={e => setTecExperience(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="text-xs text-gray-500 mb-1 block">Annual Turnover (BDT)</label><input type="number" value={tecTurnover} onChange={e => setTecTurnover(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
                <div><label className="text-xs text-gray-500 mb-1 block">Similar Contracts</label><input type="number" value={tecContracts} onChange={e => setTecContracts(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
              </div>
              <button onClick={runTecEval} disabled={tecLoading}
                className="w-full py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-400 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors">
                {tecLoading ? <><RefreshCw size={14} className="animate-spin" /> Evaluating...</> : <>Run TEC Evaluation</>}
              </button>
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
              <CheckSquare size={16} className="text-green-600" /> TEC Results
            </h3>
            {tecResult ? (
              <div className="space-y-3">
                <div className={`p-3 rounded-lg text-sm font-medium ${tecResult.output?.overall_passed ? 'bg-green-50 dark:bg-green-900/10 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800' : 'bg-red-50 dark:bg-red-900/10 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800'}`}>
                  {tecResult.output?.overall_passed ? 'TEC PASSED' : 'TEC FAILED'}
                  <span className="ml-2 text-xs opacity-75">Score: {(tecResult.output?.overall_score * 100).toFixed(0)}%</span>
                </div>
                {tecResult.output?.schedule_evaluation?.criteria?.map((c: any, i: number) => (
                  <div key={i} className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-700/30 rounded-lg text-sm">
                    <span className="text-gray-700 dark:text-gray-300">{c.name}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400">{c.score}/{c.max_score}</span>
                      {c.passed ? <CheckSquare size={14} className="text-green-500" /> : <X size={14} className="text-red-500" />}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-64 text-gray-400">
                <ClipboardList size={36} className="mb-2 opacity-30" />
                <p className="text-sm">Enter vendor data and run TEC evaluation</p>
                <p className="text-xs mt-1">Evaluates compliance with Schedule {tecType === 'works' ? '5' : tecType === 'goods' ? '4' : '6'} of PPR 2025</p>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'ppr' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
              <FileCheck size={16} className="text-primary-600" /> PPR Bid Evaluation — Compliance Review
            </h3>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div><label className="text-xs text-gray-500 mb-1 block">Bid Price (BDT)</label><input type="number" value={pprBidPrice} onChange={e => setPprBidPrice(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
                <div><label className="text-xs text-gray-500 mb-1 block">Estimated Cost (BDT)</label><input type="number" value={pprEstimate} onChange={e => setPprEstimate(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="text-xs text-gray-500 mb-1 block">Bid Security (BDT)</label><input type="number" value={pprBidSecurity} onChange={e => setPprBidSecurity(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
                <div><label className="text-xs text-gray-500 mb-1 block">Validity (days)</label><input type="number" value={pprValidity} onChange={e => setPprValidity(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
              </div>
              <button onClick={runPprEval} disabled={pprLoading}
                className="w-full py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-400 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors">
                {pprLoading ? <><RefreshCw size={14} className="animate-spin" /> Evaluating...</> : <>Run PPR Evaluation</>}
              </button>
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
              <Target size={16} className="text-green-600" /> Evaluation Results
            </h3>
            {pprResult ? (
              <div className="space-y-3">
                <div className={`p-3 rounded-lg text-sm font-medium ${pprResult.output?.responsive ? 'bg-green-50 dark:bg-green-900/10 text-green-700 border border-green-200' : 'bg-red-50 dark:bg-red-900/10 text-red-700 border border-red-200'}`}>
                  {pprResult.output?.responsive ? 'Responsive — All PPR 2025 checks passed' : 'Non-responsive'}
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="p-2 bg-gray-50 dark:bg-gray-700/30 rounded-lg"><span className="text-xs text-gray-500">Responsiveness</span><div className="font-medium text-gray-900 dark:text-white">{pprResult.output?.responsive ? 'Passed' : 'Failed'}</div></div>
                  <div className="p-2 bg-gray-50 dark:bg-gray-700/30 rounded-lg"><span className="text-xs text-gray-500">Qualification</span><div className="font-medium text-gray-900 dark:text-white">{pprResult.output?.qualification_met ? 'Met' : 'Not Met'}</div></div>
                  <div className="p-2 bg-gray-50 dark:bg-gray-700/30 rounded-lg"><span className="text-xs text-gray-500">PPR Rules</span><div className="font-medium text-gray-900 dark:text-white">{pprResult.output?.ppr_rules_validated ? 'Valid' : 'Violations'}</div></div>
                  <div className="p-2 bg-gray-50 dark:bg-gray-700/30 rounded-lg"><span className="text-xs text-gray-500">Arithmetic Errors</span><div className="font-medium text-orange-600">{(pprResult.output?.arithmetic_error_pct || 0).toFixed(1)}%</div></div>
                </div>
                <div className={`p-3 rounded-lg border text-sm ${pprResult.output?.slt_analysis?.status === 'Normal' ? 'bg-green-50 border-green-200 text-green-700' : pprResult.output?.slt_analysis?.status === 'SLT' ? 'bg-yellow-50 border-yellow-200 text-yellow-700' : 'bg-red-50 border-red-200 text-red-700'}`}>
                  <div className="font-medium">{pprResult.output?.slt_analysis?.status || 'Unknown'}</div>
                  <div className="text-xs mt-1">Ratio: {pprResult.output?.slt_analysis?.ratio_formatted} — {pprResult.output?.slt_analysis?.recommendation}</div>
                </div>
                {pprResult.ml_assessment && (
                  <div className="space-y-3 p-3 rounded-lg bg-indigo-50 dark:bg-indigo-900/10 border border-indigo-100 dark:border-indigo-900/30 text-sm">
                    <div>
                      <div className="text-xs font-bold uppercase tracking-wider text-indigo-500 mb-1">Model assessment</div>
                      <div className="font-medium text-gray-900 dark:text-white">
                        Win {getMetricValue((pprResult.ml_assessment.win?.probability || 0) * 100, 1)}% · SLT risk {getMetricValue((pprResult.ml_assessment.slt?.risk || 0) * 100, 1)}%
                      </div>
                      <div className="text-xs text-gray-600 dark:text-gray-300 mt-1">
                        {getExplanationText(pprResult.ml_assessment.explanation) || 'Calibrated model output with rule-first compliance checks.'}
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      <FactorList title="Win drivers" factors={pprResult.ml_assessment.win?.factors || []} />
                      <FactorList title="SLT drivers" factors={pprResult.ml_assessment.slt?.factors || []} />
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-64 text-gray-400">
                <FileCheck size={36} className="mb-2 opacity-30" />
                <p className="text-sm">Enter bid details and run PPR evaluation</p>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'slt' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
              <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
                <AlertTriangle size={16} className="text-orange-600" /> Works Evaluation — Rule 52
              </h3>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div><label className="text-xs text-gray-500 mb-1 block">Tender Open Date</label><input type="date" value={sltTenderOpenDate} onChange={e => setSltTenderOpenDate(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
                  <div><label className="text-xs text-gray-500 mb-1 block">Agency</label><input value={sltAgency} onChange={e => setSltAgency(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div><label className="text-xs text-gray-500 mb-1 block">Official Estimate</label><input type="number" value={sltEstimate} onChange={e => setSltEstimate(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
                  <div><label className="text-xs text-gray-500 mb-1 block">Quoted Bid Price</label><input type="number" value={sltBidPrice} onChange={e => setSltBidPrice(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div><label className="text-xs text-gray-500 mb-1 block">District</label><input value={sltDistrict} onChange={e => setSltDistrict(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
                  <div><label className="text-xs text-gray-500 mb-1 block">Method</label><input value={sltMethod} onChange={e => setSltMethod(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div><label className="text-xs text-gray-500 mb-1 block">Work Type</label><input value={sltWorkType} onChange={e => setSltWorkType(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
                  <div><label className="text-xs text-gray-500 mb-1 block">Bidder Name</label><input value={sltBidderName} onChange={e => setSltBidderName(e.target.value)} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white" /></div>
                </div>
                <div><label className="text-xs text-gray-500 mb-1 block">BOQ Items (JSON)</label>
                  <textarea value={sltBoqItems} onChange={e => setSltBoqItems(e.target.value)} rows={3} className="w-full px-2.5 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-xs font-mono text-gray-900 dark:text-white" placeholder='[{"item_no":"1","description":"Earthwork","rate":400,"sor_rate":500}]' />
                </div>
                <button onClick={runSltEval} disabled={sltLoading}
                  className="w-full py-2.5 bg-orange-600 hover:bg-orange-700 disabled:bg-orange-400 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors">
                  {sltLoading ? <><RefreshCw size={14} className="animate-spin" /> Evaluating...</> : <>Run Works Evaluation</>}
                </button>
              </div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
              <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
                <Activity size={16} className="text-green-600" /> Rule 52 Result
              </h3>
              {sltResult ? (() => {
                const evaluation = sltResult?.evaluation || {};
                const shortlist = sltResult?.market_facts?.contractor_shortlist || [];
                const responsive = evaluation.financially_responsive_bidders || [];
                const nonResponsive = evaluation.financially_non_responsive_bidders || evaluation.non_responsive_bidders || [];
                const winner = sltResult?.prediction?.likely_lert || {};
                return (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div className="p-2 bg-gray-50 dark:bg-gray-700/30 rounded-lg"><span className="text-xs text-gray-500">Mode</span><div className="font-medium text-gray-900 dark:text-white capitalize">{evaluation.mode || '—'}</div></div>
                      <div className="p-2 bg-gray-50 dark:bg-gray-700/30 rounded-lg"><span className="text-xs text-gray-500">Responsive</span><div className="font-medium text-gray-900 dark:text-white">{evaluation.responsive_bidders_count ?? responsive.length}</div></div>
                    </div>
                    <div className={`p-4 rounded-lg border text-sm ${
                      evaluation.mode === 'multi_bidder_rule_52'
                        ? 'bg-amber-50 dark:bg-amber-900/10 border-amber-300'
                        : evaluation.mode === 'single_bidder_rule_52_6'
                        ? 'bg-blue-50 dark:bg-blue-900/10 border-blue-300'
                        : 'bg-green-50 dark:bg-green-900/10 border-green-300'
                    }`}>
                      <div className="font-medium text-gray-900 dark:text-white">{evaluation.mode || 'No evaluation mode'}</div>
                      <div className="text-xs mt-1 text-gray-600 dark:text-gray-400">{evaluation.notes?.[0] || sltResult?.disclaimer}</div>
                      {winner?.contractor_name && (
                        <div className="mt-2 text-sm"><span className="text-gray-500">Likely winner:</span> <span className="font-semibold text-gray-900 dark:text-white">{winner.contractor_name}</span></div>
                      )}
                    </div>
                    <div className="p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg text-sm">
                      <span className="text-xs text-gray-500 block mb-1">Recommendation</span>
                      <div className="font-medium text-gray-900 dark:text-white">{evaluation.recommendation || sltResult?.disclaimer}</div>
                    </div>
                    {sltResult?.ml_assessment && (
                      <div className="space-y-3 p-3 rounded-lg bg-indigo-50 dark:bg-indigo-900/10 border border-indigo-100 dark:border-indigo-900/30 text-sm">
                        <div>
                          <div className="text-xs font-bold uppercase tracking-wider text-indigo-500 mb-1">Model assessment</div>
                          <div className="font-medium text-gray-900 dark:text-white">
                            Win {getMetricValue((sltResult.ml_assessment.win?.probability || 0) * 100, 1)}% · SLT risk {getMetricValue((sltResult.ml_assessment.slt?.risk || 0) * 100, 1)}%
                          </div>
                          <div className="text-xs text-gray-600 dark:text-gray-300 mt-1">
                            {getExplanationText(sltResult.ml_assessment.explanation) || 'Calibrated model output with rule-first compliance checks.'}
                          </div>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                          <FactorList title="Win drivers" factors={sltResult.ml_assessment.win?.factors || []} />
                          <FactorList title="SLT drivers" factors={sltResult.ml_assessment.slt?.factors || []} />
                        </div>
                      </div>
                    )}
                    {nonResponsive.length > 0 && (
                      <div>
                        <div className="text-sm font-medium text-gray-900 dark:text-white mb-2">Non-Responsive Bidders</div>
                        <div className="space-y-1 max-h-28 overflow-y-auto">
                          {nonResponsive.slice(0, 4).map((b: any, i: number) => (
                            <div key={i} className="p-2 bg-red-50 dark:bg-red-900/10 rounded-lg text-xs text-red-700">{b.bidder_name} - {b.financial_reason || 'Rejected'}</div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })() : (
                <div className="flex flex-col items-center justify-center h-64 text-gray-400">
                  <AlertTriangle size={36} className="mb-2 opacity-30" />
                  <p className="text-sm">Enter values and run works evaluation</p>
                </div>
              )}
            </div>
          </div>
          <ChartCard title="Saved Evaluation History">
            <div className="flex gap-2 mb-3">
              {['', 'tec', 'ppr', 'works', 'slt'].map(t => (
                <button key={t} onClick={() => setEvalFilter(t)}
                  className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${evalFilter === t ? 'bg-primary-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}>
                  {t || 'All'}
                </button>
              ))}
            </div>
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {savedEvals.filter((e: any) => !evalFilter || e.evaluation_type === evalFilter).map((e: any, i: number) => (
                <div key={i} className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-700/30 rounded-lg text-xs">
                  <div className="flex items-center gap-2">
                    <span className={`px-1.5 py-0.5 rounded font-medium ${e.evaluation_type === 'tec' ? 'bg-blue-100 text-blue-700' : e.evaluation_type === 'ppr' ? 'bg-green-100 text-green-700' : e.evaluation_type === 'works' ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 text-gray-700'}`}>
                      {e.evaluation_type?.toUpperCase()}
                    </span>
                    <span className="text-gray-500 font-mono">{e.timestamp?.slice(0, 19).replace('T', ' ')}</span>
                  </div>
                </div>
              ))}
              {savedEvals.length === 0 && <p className="text-sm text-gray-400 text-center py-4">No saved evaluations yet</p>}
            </div>
          </ChartCard>
        </div>
      )}

      {activeTab === 'documents' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
              <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
                <FileText size={16} className="text-primary-600" /> Tender Type
              </h3>
              <div className="space-y-2">
                {['works', 'goods', 'services'].map(t => (
                  <button key={t} onClick={() => setDocType(t)}
                    className={`w-full p-3 rounded-lg text-left text-sm transition-colors border ${
                      docType === t
                        ? 'bg-primary-50 dark:bg-primary-900/20 border-primary-300 text-primary-700'
                        : 'bg-gray-50 dark:bg-gray-700/30 border-gray-200 text-gray-700 hover:border-primary-300'
                    }`}>
                    <div className="font-medium capitalize">{t}</div>
                    <div className="text-xs text-gray-400 mt-0.5">Schedule {t === 'works' ? '5' : t === 'goods' ? '4' : '6'}</div>
                  </button>
                ))}
              </div>
              {docData && (
                <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg text-sm">
                  <div className="font-medium text-gray-900 dark:text-white mt-1">{docData.required_documents?.length} Required Documents</div>
                  <div className="text-xs text-gray-400 mt-1">TEC Pass: {docData.tec_pass_threshold}%</div>
                </div>
              )}
            </div>
          </div>
          <div className="lg:col-span-2">
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
              <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
                <FileText size={16} className="text-primary-600" /> Required Documents
              </h3>
              {docData ? (
                <div className="space-y-2">
                  {(docData.required_documents || []).map((doc: any, i: number) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg border border-gray-200 dark:border-gray-600">
                      <div>
                        <div className="text-sm font-medium text-gray-900 dark:text-white">{doc.name}</div>
                        <div className="text-xs text-gray-500">{doc.rule} {doc.validity ? `· ${doc.validity}` : ''}</div>
                      </div>
                      <span className={`px-2 py-0.5 text-xs rounded-full font-medium ${doc.mandatory ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'}`}>
                        {doc.mandatory ? 'Mandatory' : 'Optional'}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-center justify-center h-48 text-gray-400">Select a tender type</div>
              )}
            </div>
            {docData && (
              <div className="mt-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
                  <BarChart3 size={16} className="text-primary-600" /> Evaluation Criteria
                </h3>
                <div className="space-y-3">
                  {(docData.evaluation_criteria || []).map((c: any, i: number) => (
                    <div key={i}>
                      <div className="flex items-center justify-between text-sm mb-1">
                        <span className="text-gray-700 dark:text-gray-300">{c.name}</span>
                        <span className="text-xs text-gray-500">Min pass: {c.min_pass}/{c.max_marks} ({Math.round(c.min_pass / c.max_marks * 100)}%)</span>
                      </div>
                      <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                        <div className="bg-primary-600 h-2 rounded-full" style={{ width: `${(c.min_pass / c.max_marks) * 100}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
