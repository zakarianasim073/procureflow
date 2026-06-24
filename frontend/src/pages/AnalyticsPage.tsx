import { useEffect, useState } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';
import {
  BarChart3, TrendingDown, Award, Building2, Users, DollarSign, RefreshCw
} from 'lucide-react';
import {
  getAnalyticsOverview, getAnalyticsNppTrends, getAnalyticsAwardTrends,
  getAnalyticsAgencyComparison, getAnalyticsContractorLeaderboard,
  getAnalyticsWinRate, getAnalyticsDiscountDistribution, getAnalyticsMonthlyTrends,
} from '../api/client';

const AGENCY_COLORS: Record<string, string> = {
  BBA: '#2563eb', BWDB: '#059669', LGED: '#7c3aed', PWD: '#d97706', RHD: '#dc2626',
  BADC: '#0891b2', BIWTA: '#8b5cf6', DISASTER: '#f59e0b', EDUCATION: '#0ea5e9', POWER: '#ef4444',
};

function KpiCard({ title, value, icon, color }: any) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2.5 rounded-lg ${color}`}>{icon}</div>
        <div>
          <div className="text-xs text-gray-500 dark:text-gray-400">{title}</div>
          <div className="text-xl font-bold text-gray-900 dark:text-white">{value ?? '—'}</div>
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

export default function AnalyticsPage() {
  const [months, setMonths] = useState(12);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [overview, setOverview] = useState<any>(null);
  const [nppTrends, setNppTrends] = useState<any[]>([]);
  const [awardTrends, setAwardTrends] = useState<any[]>([]);
  const [agencyComparison, setAgencyComparison] = useState<any[]>([]);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [winRate, setWinRate] = useState<any[]>([]);
  const [discountDist, setDiscountDist] = useState<any[]>([]);
  const [monthlyTrends, setMonthlyTrends] = useState<any[]>([]);

  const loadAll = async (m: number) => {
    setLoading(true); setError('');
    try {
      const [ov, npp, aw, ag, lb, wr, dd, mt] = await Promise.all([
        getAnalyticsOverview().then(r => r.data),
        getAnalyticsNppTrends(m).then(r => r.data),
        getAnalyticsAwardTrends(m).then(r => r.data),
        getAnalyticsAgencyComparison().then(r => r.data),
        getAnalyticsContractorLeaderboard(10).then(r => r.data),
        getAnalyticsWinRate().then(r => r.data),
        getAnalyticsDiscountDistribution().then(r => r.data),
        getAnalyticsMonthlyTrends(m).then(r => r.data),
      ]);
      setOverview(ov);
      setNppTrends(npp.trends || []);
      setAwardTrends(aw.award_trends || []);
      setAgencyComparison(ag.agencies || []);
      setLeaderboard(lb.leaderboard || []);
      setWinRate(wr.agencies || []);
      setDiscountDist(dd.distribution || []);
      setMonthlyTrends(mt.monthly_trends || []);
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadAll(months); }, [months]);

  if (loading) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <div className="mb-6"><div className="h-8 w-48 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" /></div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {Array.from({ length: 4 }).map((_, i) => (
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
            <BarChart3 className="text-primary-600" size={28} />
            Advanced Analytics
          </h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-0.5">
            NPP trends · Award volume · Agency comparison · Contractor performance
          </p>
        </div>
        <button onClick={() => loadAll(months)} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg text-gray-400 transition-colors" title="Refresh">
          <RefreshCw size={16} />
        </button>
      </div>

      {error && <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded-lg text-sm">{error}</div>}

      <div className="flex items-center gap-2 mb-4">
        {[6, 12, 24, 60].map(m => (
          <button key={m} onClick={() => setMonths(m)}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${months === m ? 'bg-primary-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'}`}>
            {m}m
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <KpiCard title="Total Tenders" value={overview?.total_tenders?.toLocaleString()} icon={<TrendingDown size={16} />} color="bg-blue-50 text-blue-600" />
        <KpiCard title="Awards Tracked" value={overview?.total_awards?.toLocaleString()} icon={<Award size={16} />} color="bg-green-50 text-green-600" />
        <KpiCard title="Agencies" value={overview?.total_agencies} icon={<Building2 size={16} />} color="bg-purple-50 text-purple-600" />
        <KpiCard title="Contractors" value={overview?.total_competitors?.toLocaleString()} icon={<Users size={16} />} color="bg-orange-50 text-orange-600" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <ChartCard title="NPP Discount Trends">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={nppTrends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="month" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10 }} domain={[0, 'auto']} />
              <Tooltip formatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
              <Legend />
              {Array.from(new Set(nppTrends.map((d: any) => d.agency))).map((a) => (
                <Line key={a as string} type="monotone" dataKey="avg_npp" data={nppTrends.filter((d: any) => d.agency === a)} stroke={AGENCY_COLORS[a as string] || '#888'} name={a as string} strokeWidth={2} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Award Volume by Month">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={awardTrends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="month" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Legend />
              <Bar dataKey="count" fill="#7c3aed" name="Awards" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <ChartCard title="Agency Comparison">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={agencyComparison} layout="vertical" margin={{ left: 80, right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis type="number" tick={{ fontSize: 10 }} />
              <YAxis dataKey="agency" type="category" tick={{ fontSize: 10 }} width={70} />
              <Tooltip />
              <Legend />
              <Bar dataKey="award_count" fill="#2563eb" name="Award Count" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Contractor Leaderboard">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={leaderboard.slice(0, 8)} layout="vertical" margin={{ left: 130, right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis type="number" tick={{ fontSize: 10 }} />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 9 }} width={125} />
              <Tooltip />
              <Legend />
              <Bar dataKey="total_awards" fill="#059669" name="Total Awards" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <ChartCard title="Win Rate by Agency">
          <div className="space-y-3 max-h-[300px] overflow-y-auto">
            {winRate.map((ag: any) => (
              <div key={ag.agency} className="p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg border border-gray-200 dark:border-gray-600">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-900 dark:text-white">{ag.agency}</span>
                  <span className="text-xs text-gray-500">{ag.total_awards} awards</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex-1 bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                    <div className="bg-purple-500 h-2 rounded-full" style={{ width: `${ag.concentration_pct}%` }} />
                  </div>
                  <span className="text-xs text-gray-500">{ag.concentration_pct}%</span>
                </div>
                <div className="text-xs text-gray-400 mt-1">Top contractor: {ag.top_contractors?.[0]?.name || '—'}</div>
              </div>
            ))}
          </div>
        </ChartCard>
        <ChartCard title="Discount Distribution">
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie data={discountDist} dataKey="count" nameKey="range" cx="50%" cy="50%" outerRadius={90} label={({ range, percent }: any) => `${range} (${(percent * 100).toFixed(0)}%)`}>
                {discountDist.map((_: any, i: number) => (<Cell key={i} fill={Object.values(AGENCY_COLORS)[i % Object.keys(AGENCY_COLORS).length] as string} />))}
              </Pie>
              <Tooltip formatter={(v: number) => v.toLocaleString()} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Monthly Activity">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={monthlyTrends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="month" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="awards" stroke="#7c3aed" name="Awards" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="award_value" stroke="#059669" name="Value (BDT)" strokeWidth={2} dot={false} yAxisId={0} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <ChartCard title="Award Value Trends">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={awardTrends}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="month" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v: number) => `BDT ${v.toLocaleString('en-IN')}`} />
            <Legend />
            <Line type="monotone" dataKey="total_value" stroke="#d97706" name="Total Value" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}
