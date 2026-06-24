import { useEffect, useState } from 'react';
import {
  Database, Download, RefreshCw, Award, TrendingUp, Building2,
  AlertTriangle, Activity, Play, Clock, FileText, Bot, GitBranch
} from 'lucide-react';
import StatsCard from '../components/StatsCard';
import api, { getIntelAgentFeed, getIntelImportStatus } from '../api/client';

export default function DataIntelligence() {
  const [stats, setStats] = useState<any>(null);
  const [importStatus, setImportStatus] = useState<any>(null);
  const [agentFeed, setAgentFeed] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [collecting, setCollecting] = useState(false);
  const [collectResult, setCollectResult] = useState<any>(null);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    setLoading(true);
    try {
      const [{ data }, importData, feedData] = await Promise.all([
        api.get('/dashboard/data-intelligence'),
        getIntelImportStatus(),
        getIntelAgentFeed(undefined, 12),
      ]);
      setStats(data);
      setImportStatus(importData.status);
      setAgentFeed(feedData.data);
    } catch (e) {
      console.error('Failed to load data intel stats', e);
    }
    setLoading(false);
  };

  const triggerCollect = async (mode: string) => {
    setCollecting(true);
    setCollectResult(null);
    try {
      const { data } = await api.post('/dashboard/data-intelligence/collect', { mode });
      setCollectResult(data.result);
      loadStats();
    } catch (e: any) {
      setCollectResult({ error: e.message });
    }
    setCollecting(false);
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Data Intelligence
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Local storage — tender & award collection
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => triggerCollect('live')} disabled={collecting}
            className="btn btn-sm btn-outline flex items-center gap-1.5">
            <Activity size={14} /> {collecting ? 'Collecting...' : 'Collect Live'}
          </button>
          <button onClick={() => triggerCollect('awards')} disabled={collecting}
            className="btn btn-sm btn-outline flex items-center gap-1.5">
            <Award size={14} /> Get Awards
          </button>
          <button onClick={() => triggerCollect('all_tabs')} disabled={collecting}
            className="btn btn-sm btn-primary flex items-center gap-1.5">
            <Play size={14} /> Full Scan
          </button>
          <button onClick={() => triggerCollect('bulk')} disabled={collecting}
            className="btn btn-sm bg-purple-600 text-white flex items-center gap-1.5">
            <Database size={14} /> Bulk (1000+)
          </button>
        </div>
      </div>

      {/* Stats Grid */}
      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading...</div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <StatsCard title="Tenders Collected" value={stats?.total_tenders_collected ?? 0} icon={FileText} color="blue" />
            <StatsCard title="Awards Collected" value={stats?.total_awards_collected ?? 0} icon={Award} color="green" />
            <StatsCard title="Unique Agencies" value={stats?.unique_agencies ?? 0} icon={Building2} color="purple" />
            <StatsCard title="BWDB 5Cr+ Alerts" value={stats?.bwdb_high_value_tenders ?? 0} icon={AlertTriangle} color="red" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                <Database size={18} className="text-primary-600" />
                PostgreSQL Import Status
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-gray-500 dark:text-gray-400">State</span>
                  <span className="font-semibold text-gray-900 dark:text-white">{importStatus?.current_phase || importStatus?.state || 'unknown'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-gray-500 dark:text-gray-400">Progress</span>
                  <span className="font-semibold text-gray-900 dark:text-white">{importStatus?.progress_pct ?? 0}%</span>
                </div>
                <div className="h-2 w-full rounded-full bg-gray-100 dark:bg-gray-700">
                  <div
                    className="h-full rounded-full bg-primary-600 transition-all"
                    style={{ width: `${Math.max(0, Math.min(100, importStatus?.progress_pct ?? (importStatus?.state === 'completed' ? 100 : 0)))}%` }}
                  />
                </div>
                {(importStatus?.summary || importStatus?.records) && (
                  <div className="grid grid-cols-2 gap-2 pt-2 text-xs">
                    {Object.entries(importStatus.summary || importStatus.records || {}).slice(0, 8).map(([key, value]) => (
                      <div key={key} className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-700/40">
                        <div className="text-gray-400">{key.replace(/_/g, ' ')}</div>
                        <div className="font-semibold text-gray-900 dark:text-white">{String(value)}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                <GitBranch size={18} className="text-primary-600" />
                Match Quality
              </h3>
              <div className="space-y-3">
                <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-3">
                  <div className="text-xs text-gray-400">Matched Lifecycle Records</div>
                  <div className="text-2xl font-bold text-gray-900 dark:text-white">{agentFeed?.lifecycle_stats?.matched_total?.toLocaleString?.() ?? 0}</div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    Package exact: {agentFeed?.lifecycle_stats?.matched_packages?.toLocaleString?.() ?? 0}
                    {' · '}
                    Title similarity: {agentFeed?.lifecycle_stats?.title_similarity_matches?.toLocaleString?.() ?? 0}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="rounded-lg bg-green-50 px-3 py-2 dark:bg-green-900/20">
                    <div className="text-xs text-green-600 dark:text-green-300">Match Rate</div>
                    <div className="font-semibold text-green-800 dark:text-green-200">
                      {agentFeed?.lifecycle_stats?.match_rate_pct?.toLocaleString?.() ?? 0}%
                    </div>
                  </div>
                  <div className="rounded-lg bg-blue-50 px-3 py-2 dark:bg-blue-900/20">
                    <div className="text-xs text-blue-600 dark:text-blue-300">Contractor DNA</div>
                    <div className="font-semibold text-blue-800 dark:text-blue-200">{agentFeed?.contractor_stats?.total_contractors?.toLocaleString?.() ?? 0}</div>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="rounded-lg bg-amber-50 px-3 py-2 dark:bg-amber-900/20">
                    <div className="text-xs text-amber-600 dark:text-amber-300">Live Tender Source Rows</div>
                    <div className="font-semibold text-amber-800 dark:text-amber-200">
                      {agentFeed?.live_tender_stats?.total_live_tenders?.toLocaleString?.() ?? 0}
                    </div>
                  </div>
                  <div className="rounded-lg bg-indigo-50 px-3 py-2 dark:bg-indigo-900/20">
                    <div className="text-xs text-indigo-600 dark:text-indigo-300">eExperience Records</div>
                    <div className="font-semibold text-indigo-800 dark:text-indigo-200">
                      {agentFeed?.eexperience_stats?.total_records?.toLocaleString?.() ?? 0}
                    </div>
                  </div>
                </div>
                <div className="rounded-lg bg-rose-50 px-3 py-3 dark:bg-rose-900/20">
                  <div className="text-xs text-rose-600 dark:text-rose-300">Award Dedup Removed</div>
                  <div className="text-xl font-bold text-rose-800 dark:text-rose-200">
                    {agentFeed?.data_quality?.duplicates_removed?.toLocaleString?.() ?? stats?.data_quality?.duplicates_removed?.toLocaleString?.() ?? 0}
                  </div>
                  <div className="mt-1 text-xs text-rose-700 dark:text-rose-300/80">
                    Raw: {agentFeed?.data_quality?.raw_awards?.toLocaleString?.() ?? stats?.data_quality?.raw_awards?.toLocaleString?.() ?? 0}
                    {' · '}
                    Canonical: {agentFeed?.data_quality?.canonical_awards?.toLocaleString?.() ?? stats?.data_quality?.canonical_awards?.toLocaleString?.() ?? 0}
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                <Bot size={18} className="text-primary-600" />
                Live Agent Feed
              </h3>
              <div className="space-y-2 max-h-72 overflow-y-auto">
                {(agentFeed?.recent_lifecycle || []).slice(0, 6).map((item: any) => (
                  <div key={item.id} className="rounded-lg border border-gray-100 px-3 py-2 dark:border-gray-700">
                    <div className="text-sm font-medium text-gray-900 dark:text-white line-clamp-2">{item.title || item.package_no}</div>
                    <div className="mt-1 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                      <span>{item.package_no}</span>
                      <span>{item.match_type}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Live Tender Source</h3>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-3">
                  <div className="text-xs text-gray-400">Total Rows</div>
                  <div className="font-semibold text-gray-900 dark:text-white">{agentFeed?.live_tender_stats?.total_live_tenders?.toLocaleString?.() ?? 0}</div>
                </div>
                <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-3">
                  <div className="text-xs text-gray-400">With Real Estimate</div>
                  <div className="font-semibold text-gray-900 dark:text-white">{agentFeed?.live_tender_stats?.with_real_estimate?.toLocaleString?.() ?? 0}</div>
                </div>
                <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-3">
                  <div className="text-xs text-gray-400">Active Agencies</div>
                  <div className="font-semibold text-gray-900 dark:text-white">{agentFeed?.live_tender_stats?.active_agencies?.toLocaleString?.() ?? 0}</div>
                </div>
                <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-3">
                  <div className="text-xs text-gray-400">Latest Deadline</div>
                  <div className="font-semibold text-gray-900 dark:text-white">{agentFeed?.live_tender_stats?.latest_deadline || '—'}</div>
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-3">eExperience Intelligence</h3>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-3">
                  <div className="text-xs text-gray-400">Execution Records</div>
                  <div className="font-semibold text-gray-900 dark:text-white">{agentFeed?.eexperience_stats?.total_records?.toLocaleString?.() ?? 0}</div>
                </div>
                <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-3">
                  <div className="text-xs text-gray-400">Unique Agencies</div>
                  <div className="font-semibold text-gray-900 dark:text-white">{agentFeed?.eexperience_stats?.unique_agencies?.toLocaleString?.() ?? 0}</div>
                </div>
                <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-3">
                  <div className="text-xs text-gray-400">Unique Contractors</div>
                  <div className="font-semibold text-gray-900 dark:text-white">{agentFeed?.eexperience_stats?.unique_contractors?.toLocaleString?.() ?? 0}</div>
                </div>
                <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-3">
                  <div className="text-xs text-gray-400">Total Contract Value</div>
                  <div className="font-semibold text-gray-900 dark:text-white">{Math.round(agentFeed?.eexperience_stats?.total_value_bdt ?? 0).toLocaleString()}</div>
                </div>
                <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-3">
                  <div className="text-xs text-gray-400">Completed Records</div>
                  <div className="font-semibold text-gray-900 dark:text-white">{agentFeed?.eexperience_stats?.completed_records?.toLocaleString?.() ?? 0}</div>
                </div>
                <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-3">
                  <div className="text-xs text-gray-400">Delayed Records</div>
                  <div className="font-semibold text-gray-900 dark:text-white">{agentFeed?.eexperience_stats?.delayed_records?.toLocaleString?.() ?? 0}</div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 mb-6">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
              <TrendingUp size={18} className="text-primary-600" />
              Execution Intelligence
            </h3>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-1 space-y-3">
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-lg bg-emerald-50 px-3 py-3 dark:bg-emerald-900/20">
                    <div className="text-xs text-emerald-600 dark:text-emerald-300">Completion Rate</div>
                    <div className="font-semibold text-emerald-800 dark:text-emerald-200">
                      {agentFeed?.execution_intelligence?.summary?.completion_rate_pct?.toLocaleString?.() ?? 0}%
                    </div>
                  </div>
                  <div className="rounded-lg bg-blue-50 px-3 py-3 dark:bg-blue-900/20">
                    <div className="text-xs text-blue-600 dark:text-blue-300">On-Time Rate</div>
                    <div className="font-semibold text-blue-800 dark:text-blue-200">
                      {agentFeed?.execution_intelligence?.summary?.on_time_rate_pct?.toLocaleString?.() ?? 0}%
                    </div>
                  </div>
                  <div className="rounded-lg bg-amber-50 px-3 py-3 dark:bg-amber-900/20">
                    <div className="text-xs text-amber-600 dark:text-amber-300">Avg Progress</div>
                    <div className="font-semibold text-amber-800 dark:text-amber-200">
                      {agentFeed?.execution_intelligence?.summary?.avg_progress_pct?.toLocaleString?.() ?? 0}%
                    </div>
                  </div>
                  <div className="rounded-lg bg-rose-50 px-3 py-3 dark:bg-rose-900/20">
                    <div className="text-xs text-rose-600 dark:text-rose-300">Avg Delay</div>
                    <div className="font-semibold text-rose-800 dark:text-rose-200">
                      {agentFeed?.execution_intelligence?.summary?.avg_delay_days?.toLocaleString?.() ?? 0} days
                    </div>
                  </div>
                </div>
                <div className="rounded-xl bg-gray-50 dark:bg-gray-700/40 p-4">
                  <div className="text-xs text-gray-400">Completed Work Value</div>
                  <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
                    {Math.round(agentFeed?.execution_intelligence?.summary?.completed_value_bdt ?? 0).toLocaleString()}
                  </div>
                  <div className="mt-3 space-y-2">
                    {(agentFeed?.execution_intelligence?.status_breakdown || []).slice(0, 5).map((row: any) => (
                      <div key={row.status} className="flex items-center justify-between text-sm">
                        <span className="text-gray-500 dark:text-gray-400 capitalize">{String(row.status || 'unknown').replace(/_/g, ' ')}</span>
                        <span className="font-semibold text-gray-900 dark:text-white">{row.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="lg:col-span-2">
                <div className="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">Recent Execution Records</div>
                <div className="space-y-3 max-h-[28rem] overflow-y-auto pr-1">
                  {(agentFeed?.execution_intelligence?.recent_records || []).slice(0, 8).map((item: any) => (
                    <div key={item.id} className="rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="font-medium text-gray-900 dark:text-white line-clamp-2">
                            {item.title || item.package_no}
                          </div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                            {item.package_no} {item.contractor_name ? `• ${item.contractor_name}` : ''} {item.agency_code ? `• ${item.agency_code}` : ''}
                          </div>
                        </div>
                        <div className="shrink-0 rounded-full bg-gray-100 px-2.5 py-1 text-xs font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                          {item.completion_status || item.work_status || item.status || 'unknown'}
                        </div>
                      </div>
                      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                        <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-2">
                          <div className="text-xs text-gray-400">Progress</div>
                          <div className="font-semibold text-gray-900 dark:text-white">{Math.round(item.progress_pct ?? 0)}%</div>
                        </div>
                        <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-2">
                          <div className="text-xs text-gray-400">Delay</div>
                          <div className="font-semibold text-gray-900 dark:text-white">{item.delay_days ?? 0} days</div>
                        </div>
                        <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-2">
                          <div className="text-xs text-gray-400">Planned End</div>
                          <div className="font-semibold text-gray-900 dark:text-white">{item.planned_completion_date || item.contract_end_date || '—'}</div>
                        </div>
                        <div className="rounded-lg bg-gray-50 dark:bg-gray-700/40 px-3 py-2">
                          <div className="text-xs text-gray-400">Actual End</div>
                          <div className="font-semibold text-gray-900 dark:text-white">{item.actual_completion_date || '—'}</div>
                        </div>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-4 text-xs text-gray-500 dark:text-gray-400">
                        <span>Contract Value: {Math.round(item.contract_value_bdt ?? 0).toLocaleString()}</span>
                        <span>Completed Value: {Math.round(item.completed_value_bdt ?? 0).toLocaleString()}</span>
                        <span>On Time: {item.completed_on_time === true ? 'Yes' : item.completed_on_time === false ? 'No' : 'Unknown'}</span>
                        {item.performance_rating && <span>Rating: {item.performance_rating}</span>}
                      </div>
                      {item.remarks && (
                        <div className="mt-2 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
                          {item.remarks}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Top Agencies */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 mb-6">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
              <Building2 size={18} className="text-primary-600" />
              Top Agencies by Tender Count
            </h3>
            <div className="space-y-2">
              {(stats?.top_agencies || []).slice(0, 15).map((a: any, i: number) => (
                <div key={i} className="flex items-center justify-between py-1.5 border-b border-gray-100 dark:border-gray-700 last:border-0">
                  <span className="text-sm text-gray-700 dark:text-gray-300 truncate flex-1">{a.name}</span>
                  <span className="text-sm font-semibold text-gray-900 dark:text-white ml-4">{a.count}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 mb-6">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
              <Award size={18} className="text-primary-600" />
              Top Contractors from PostgreSQL
            </h3>
            <div className="space-y-2">
              {(agentFeed?.top_contractors || []).slice(0, 10).map((contractor: any) => (
                <div key={contractor.id} className="flex items-center justify-between gap-4 border-b border-gray-100 py-2 text-sm last:border-0 dark:border-gray-700">
                  <div className="min-w-0">
                    <div className="truncate font-medium text-gray-900 dark:text-white">{contractor.contractor_name}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">{(contractor.agencies_worked || []).slice(0, 3).join(', ') || 'No agency tags'}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold text-gray-900 dark:text-white">{Number(contractor.total_amount_bdt || 0).toLocaleString()}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">{contractor.total_contracts} awards</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Collection Log */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
              <Clock size={18} className="text-primary-600" />
              Collection History
            </h3>
            {(stats?.collections || []).length === 0 ? (
              <p className="text-gray-400 text-sm">No collections yet. Click a button above to start.</p>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {[...(stats?.collections || [])].reverse().map((c: any, i: number) => (
                  <div key={i} className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 text-sm">
                    <div>
                      <span className="font-medium text-gray-700 dark:text-gray-300">{c.type}</span>
                      <span className="text-gray-400 ml-2">{c.timestamp}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-gray-900 dark:text-white font-semibold">{c.count} records</span>
                      {c.file && <span className="text-xs text-gray-400">{c.file}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Collect Result */}
          {collectResult && (
            <div className="mt-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
              <h4 className="font-semibold text-gray-700 dark:text-gray-300 mb-2">Last Collection Result</h4>
              <pre className="text-xs text-gray-500 dark:text-gray-400 overflow-auto max-h-40">
                {JSON.stringify(collectResult, null, 2)}
              </pre>
            </div>
          )}
        </>
      )}
    </div>
  );
}
