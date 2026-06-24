import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Upload, FileSpreadsheet, MessageSquare, TrendingDown, AlertTriangle,
  CheckCircle2, Radar, Activity, Zap, Building2, PlayCircle, BrainCircuit,
  Cpu, Award
} from 'lucide-react';
import StatsCard from '../components/StatsCard';
import { useAppStore } from '../store/appStore';
import { getStats, listAgents, listPipelinePhases } from '../api/client';
import { getThemeClasses } from '../utils/styleMaps';

export default function Dashboard() {
  const navigate = useNavigate();
  const { comparisonResults, auth } = useAppStore();
  const [stats, setStats] = useState<any>(null);
  const [agents, setAgents] = useState<any[]>([]);
  const [phases, setPhases] = useState<any>(null);

  useEffect(() => {
    // Load dashboard data
    getStats().then(r => setStats(r.stats)).catch(() => {});
    listAgents().then(r => setAgents(r.agents || [])).catch(() => {});
    listPipelinePhases().then(r => setPhases(r)).catch(() => {});
  }, []);

  const agentCounts = {
    running: agents.filter(a => a.status === 'running').length,
    idle: agents.filter(a => ['idle', 'success'].includes(a.status)).length,
  };

  const brandTone = getThemeClasses('blue');

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="hero-shell mb-8">
        <div className="hero-orb -top-10 -right-6 h-28 w-28 bg-primary-400/20" />
        <div className="hero-orb bottom-0 left-10 h-20 w-20 bg-emerald-400/10" style={{ animationDelay: '-2s' }} />
        <div className="relative flex flex-col gap-5 p-6 md:p-8 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary-200/70 dark:border-primary-800/60 bg-white/70 dark:bg-gray-900/40 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.24em] text-primary-700 dark:text-primary-300">
              <span className={`h-2 w-2 rounded-full ${brandTone.fill} animate-pulse`} />
              Live procurement intelligence
            </div>
            <div>
              <h1 className="text-3xl md:text-4xl font-black tracking-tight text-gray-900 dark:text-white">
                ProcureFlow
              </h1>
              <div className="brand-handle mt-2 text-sm md:text-base">@zmnasim73</div>
            </div>
            <p className="max-w-2xl text-sm md:text-base text-gray-600 dark:text-gray-300">
              a Procurement intelligence System for live tender scanning, SOR intelligence, and calibrated decision support.
              {auth.user && (
                <span className="ml-2 inline-flex items-center rounded-full border border-primary-200/70 dark:border-primary-800/60 bg-primary-50/90 dark:bg-primary-900/20 px-2.5 py-0.5 text-xs font-semibold text-primary-700 dark:text-primary-300">
                  {auth.user.plan}
                </span>
              )}
            </p>
          </div>
          <button
            onClick={() => navigate('/settings')}
            className="lift-card inline-flex items-center justify-center rounded-xl border border-gray-200/80 dark:border-gray-700 bg-white/80 dark:bg-gray-900/40 px-4 py-3 text-sm font-semibold text-gray-700 dark:text-gray-200 backdrop-blur transition-colors hover:border-primary-300 dark:hover:border-primary-600"
          >
            {auth.user ? auth.user.name : 'Owner Login'} ⚙️
          </button>
        </div>
      </div>

      {/* Top Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <StatsCard
          title="Total Tenders"
          value={stats?.total_tenders ?? '—'}
          icon={Building2}
          color="blue"
          subtitle={stats ? 'All time' : undefined}
        />
        <StatsCard
          title="Comparisons"
          value={stats?.total_comparisons ?? '—'}
          icon={FileSpreadsheet}
          color="green"
        />
        <StatsCard
          title="BOQ Items"
          value={stats?.total_boq_items ?? '—'}
          icon={Activity}
          color="purple"
        />
        <StatsCard
          title="Agents Registered"
          value={agents.length || '—'}
          icon={Cpu}
          color={agents.length > 0 ? 'green' : 'yellow'}
          subtitle={`${agentCounts.running} currently running`}
        />
      </div>

      {/* Agent Pipeline Status */}
      {phases?.phases && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 mb-8">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <BrainCircuit size={18} className="text-primary-600" />
            {agents.length}-Agent Pipeline
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {Object.entries(phases.phases).map(([phase, info]: [string, any]) => (
              <div
                key={phase}
                className="p-3 rounded-lg bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600"
              >
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  {phase}
                </div>
                <div className="text-sm font-semibold text-gray-900 dark:text-white mt-1">
                  {info.count} agents
                </div>
                <div className="text-xs text-gray-400 mt-0.5 truncate">
                  {info.agents.map((a: string) => a.replace('agent-0', '')).join(', ')}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Comparison Results Summary */}
      {comparisonResults && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 mb-8">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3">
            Last BOQ Analysis Summary
          </h3>
          <div className="flex flex-wrap gap-4 text-sm">
            <span className="inline-flex items-center gap-1.5 text-green-600">
              <CheckCircle2 size={16} /> {comparisonResults.matches} Matches
            </span>
            <span className="inline-flex items-center gap-1.5 text-yellow-600">
              <TrendingDown size={16} /> {comparisonResults.variances} Variances
            </span>
            <span className="inline-flex items-center gap-1.5 text-red-600">
              <AlertTriangle size={16} /> {comparisonResults.mismatches} Mismatches
            </span>
            <span className="inline-flex items-center gap-1.5 text-gray-500">
              <FileSpreadsheet size={16} /> {comparisonResults.total_items} Total Items
            </span>
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <button onClick={() => navigate('/upload')}
          className="lift-card p-6 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 hover:border-primary-300 dark:hover:border-primary-600 transition-all group text-left">
          <div className="p-3 rounded-lg bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 w-fit mb-4 group-hover:scale-110 transition-transform">
            <Upload size={24} />
          </div>
          <h3 className="font-semibold text-gray-900 dark:text-white">New Analysis</h3>
          <p className="text-sm text-gray-500 mt-1">Upload BOQ for SOR rate comparison</p>
        </button>

        <button onClick={() => navigate('/results')}
          className="lift-card p-6 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 hover:border-primary-300 dark:hover:border-primary-600 transition-all group text-left">
          <div className="p-3 rounded-lg bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 w-fit mb-4 group-hover:scale-110 transition-transform">
            <FileSpreadsheet size={24} />
          </div>
          <h3 className="font-semibold text-gray-900 dark:text-white">View Results</h3>
          <p className="text-sm text-gray-500 mt-1">See comparison table and export</p>
        </button>

        <button onClick={() => navigate('/chat')}
          className="lift-card p-6 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 hover:border-primary-300 dark:hover:border-primary-600 transition-all group text-left">
          <div className="p-3 rounded-lg bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400 w-fit mb-4 group-hover:scale-110 transition-transform">
            <MessageSquare size={24} />
          </div>
          <h3 className="font-semibold text-gray-900 dark:text-white">AI Chat</h3>
          <p className="text-sm text-gray-500 mt-1">Ask about BOQ, SOR, and tenders</p>
        </button>

        <button onClick={() => navigate('/settings')}
          className="lift-card p-6 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 hover:border-primary-300 dark:hover:border-primary-600 transition-all group text-left">
          <div className="p-3 rounded-lg bg-orange-50 dark:bg-orange-900/20 text-orange-600 dark:text-orange-400 w-fit mb-4 group-hover:scale-110 transition-transform">
            <Award size={24} />
          </div>
          <h3 className="font-semibold text-gray-900 dark:text-white">Settings</h3>
          <p className="text-sm text-gray-500 mt-1">Configure API keys and agents</p>
        </button>
      </div>
    </div>
  );
}
