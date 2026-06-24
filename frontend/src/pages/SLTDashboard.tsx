import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Cpu, AlertTriangle, CheckCircle2, Activity,
  BrainCircuit, BarChart3, TrendingUp, Clock, Send, ShieldAlert,
  Zap, Building2, FileText, GitBranch, PlayCircle
} from 'lucide-react';
import api from '../api/client';
import { getThemeClasses } from '../utils/styleMaps';

interface SLTData {
  system: {
    app: string;
    version: string;
    agents_total: number;
    agents_idle: number;
    agents_active?: number;
  };
  pipeline_phases: Record<string, {
    total: number;
    registered: number;
    agents: string[];
  }>;
  monitor: {
    config: any;
    stats: any;
    recent_alerts: any[];
  };
  embeddings: any;
  total_tenders_monitored: number;
  alerts_sent: number;
  pipeline_ready: boolean;
}

export default function SLTDashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<SLTData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    api.get('/slt/dashboard')
      .then(r => setData(r.data.slt))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="p-8 flex items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
    </div>
  );

  if (error) return (
    <div className="p-8 text-center text-red-500">
      <ShieldAlert size={40} className="mx-auto mb-3 opacity-50" />
      <p>Failed to load SLT dashboard: {error}</p>
    </div>
  );

  if (!data) return null;

  const phaseColors: Record<string, string> = {
    discovery: 'blue', intelligence: 'indigo', evaluation: 'purple',
    pricing: 'green', competitor: 'orange', decision: 'red',
    execution: 'pink', reporting: 'teal', learning: 'cyan',
    post_award: 'yellow', alerting: 'emerald',
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <LayoutDashboard className="text-primary-600" size={28} />
            SLT Executive Dashboard
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            {data.system.app} v{data.system.version} — Senior Leadership Team View
          </p>
        </div>
        <button onClick={() => navigate('/agents')}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 text-sm">
          <PlayCircle size={16} /> Run Pipeline
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">System Status</span>
            <div className={`w-2 h-2 rounded-full ${data.pipeline_ready ? 'bg-green-500' : 'bg-yellow-500'}`} />
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Cpu className="text-primary-500" size={20} />
            {data.system.agents_total}
          </div>
          <div className="text-xs text-gray-400 mt-1">
            {data.system.agents_active ?? data.system.agents_idle} active right now
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Tenders</span>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Building2 className="text-blue-500" size={20} />
            {data.total_tenders_monitored}
          </div>
          <div className="text-xs text-gray-400 mt-1">Monitored & Indexed</div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Alerts Sent</span>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Send className="text-green-500" size={20} />
            {data.alerts_sent}
          </div>
          <div className="text-xs text-gray-400 mt-1">Email + WhatsApp</div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Pipeline</span>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <GitBranch className="text-purple-500" size={20} />
            {Object.keys(data.pipeline_phases).length}
          </div>
          <div className="text-xs text-gray-400 mt-1">Active Phases</div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Pipeline Ready</span>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            {data.pipeline_ready
              ? <CheckCircle2 className="text-green-500" size={20} />
              : <AlertTriangle className="text-yellow-500" size={20} />
            }
            {data.pipeline_ready ? 'All Go' : 'Review'}
          </div>
          <div className="text-xs text-gray-400 mt-1">
            {data.pipeline_ready ? 'All agents registered' : 'Missing agents'}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <Activity size={18} className="text-primary-600" />
            Pipeline Health — All Phases
          </h3>
          <div className="space-y-2">
            {Object.entries(data.pipeline_phases).map(([phase, info]) => {
              const color = phaseColors[phase] || 'gray';
              const tone = getThemeClasses(color);
              return (
                <div key={phase} className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/30">
                  <div className={`w-8 h-8 rounded-lg ${tone.panel} flex items-center justify-center`}>
                    <div className={`w-2 h-2 rounded-full ${tone.fill}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 dark:text-white capitalize">{phase.replace(/_/g, ' ')}</div>
                    <div className="text-xs text-gray-400 truncate">{info.agents.join(', ')}</div>
                  </div>
                  <div className={`text-xs font-semibold px-2 py-1 rounded-full ${
                    info.registered === info.total
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                      : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                  }`}>
                    {info.registered}/{info.total}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <BarChart3 size={18} className="text-primary-600" />
            BWDB Monitor
          </h3>
          {data.monitor.stats && (
            <div className="grid grid-cols-2 gap-3 mb-4">
            {[
              { label: 'Scanned', value: data.monitor.stats.total_scanned, color: 'blue' },
              { label: 'Matched', value: data.monitor.stats.total_matched, color: 'green' },
              { label: 'BWDB Tenders', value: data.monitor.stats.total_bwdb_tenders, color: 'purple' },
              { label: 'Last Scan', value: data.monitor.stats.last_scan ? new Date(data.monitor.stats.last_scan).toLocaleDateString() : '—', color: 'gray' },
              ].map((item, i) => {
                const tone = getThemeClasses(item.color);
                return (
                  <div key={i} className={`p-3 rounded-lg ${tone.panel}`}>
                    <div className={`text-lg font-bold ${tone.text}`}>{item.value ?? '—'}</div>
                    <div className={`text-xs ${tone.text}`}>{item.label}</div>
                  </div>
                );
              })}
            </div>
          )}

          {data.monitor.recent_alerts && data.monitor.recent_alerts.length > 0 && (
            <>
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Recent Alerts</h4>
              <div className="space-y-2">
                {data.monitor.recent_alerts.map((alert: any, i: number) => (
                  <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-gray-50 dark:bg-gray-700/30">
                    <AlertTriangle size={14} className="text-yellow-500 mt-0.5 shrink-0" />
                    <div className="text-xs text-gray-600 dark:text-gray-400 min-w-0">
                      <div className="font-medium text-gray-800 dark:text-gray-200 truncate">
                        {alert.title || alert.tender_id}
                      </div>
                      <div className="mt-0.5">
                        <span className="font-mono">{alert.tender_id}</span>
                        {alert.value ? ` • BDT ${Number(alert.value).toLocaleString()}` : ''}
                        {alert.entity ? ` • ${alert.entity}` : ''}
                      </div>
                      {alert.deadline && <div className="mt-0.5 text-gray-500">{alert.deadline}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {(!data.monitor.recent_alerts || data.monitor.recent_alerts.length === 0) && (
            <p className="text-sm text-gray-400 text-center py-4">No recent alerts</p>
          )}
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Zap size={18} className="text-primary-600" />
          Quick Actions
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {[ 
              { label: 'Agent Pipeline', icon: GitBranch, to: '/agents', color: 'purple' },
              { label: 'BWDB Monitor', icon: AlertTriangle, to: '/bwdb-monitor', color: 'yellow' },
              { label: 'Data Intel', icon: FileText, to: '/data-intelligence', color: 'blue' },
              { label: 'Upload Tenders', icon: Building2, to: '/upload', color: 'green' },
              { label: 'View Results', icon: BarChart3, to: '/results', color: 'orange' },
              { label: 'AI Chat', icon: BrainCircuit, to: '/chat', color: 'indigo' },
              { label: 'WhatsApp', icon: Send, to: '/whatsapp', color: 'emerald' },
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
  );
}
