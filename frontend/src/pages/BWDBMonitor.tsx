import { useEffect, useState } from 'react';
import {
  Bell, AlertTriangle, RefreshCw, DollarSign, Settings, Play, Power, PowerOff,
  ExternalLink, CheckCircle2, XCircle, MessageCircle, Mail, Filter, Clock, Building2,
  ToggleLeft, ToggleRight, Trash2, Search, Download,
} from 'lucide-react';
import api from '../api/client';

interface MonitorConfig {
  name: string;
  enabled: boolean;
  entity_keywords: string[];
  procurement_natures: string[];
  min_value_bdt: number;
  max_value_bdt: number;
  alert_channels: {
    email: { enabled: boolean; recipient: string };
    whatsapp: { enabled: boolean; phone: string };
  };
  schedule: { interval_minutes: number; auto_scan: boolean };
  filters: { only_deadline_active: boolean; exclude_expired: boolean };
  notify_on: string[];
  high_value_threshold_bdt: number;
}

const DEFAULT_CONFIG: MonitorConfig = {
  name: 'BWDB Monitor',
  enabled: true,
  entity_keywords: ['BWDB', 'Water Development Board'],
  procurement_natures: ['Works', 'Goods', 'Services'],
  min_value_bdt: 0,
  max_value_bdt: 0,
  alert_channels: { email: { enabled: true, recipient: 'z.nasim073@gmail.com' }, whatsapp: { enabled: false, phone: '' } },
  schedule: { interval_minutes: 60, auto_scan: true },
  filters: { only_deadline_active: true, exclude_expired: true },
  notify_on: ['new_tender', 'high_value'],
  high_value_threshold_bdt: 50000000,
};

export default function BWDBMonitor() {
  const [tab, setTab] = useState<'dashboard' | 'config' | 'alerts'>('dashboard');
  const [config, setConfig] = useState<MonitorConfig>(DEFAULT_CONFIG);
  const [editing, setEditing] = useState<MonitorConfig>(DEFAULT_CONFIG);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [scanResult, setScanResult] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [keywordInput, setKeywordInput] = useState('');
  const [sharing, setSharing] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => { loadAll(); }, []);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [cfg, st, al] = await Promise.all([
        api.get('/monitor/config').then(r => { setConfig(r.data); setEditing(r.data); return r.data; }),
        api.get('/monitor/stats').then(r => setStats(r.data)),
        api.get('/monitor/alerts?limit=50').then(r => setAlerts(r.data.alerts || [])),
      ]);
    } catch (e) { console.error('Load failed', e); }
    setLoading(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const { data } = await api.post('/monitor/config', editing);
      setConfig(data.config);
      setEditing(data.config);
    } catch (e: any) { console.error('Save failed', e); }
    setSaving(false);
  };

  const handleScan = async () => {
    setScanning(true);
    setScanResult(null);
    try {
      const { data } = await api.post('/monitor/scan');
      setScanResult(data.results);
      const al = await api.get('/monitor/alerts?limit=50');
      setAlerts(al.data.alerts || []);
      const st = await api.get('/monitor/stats');
      setStats(st.data);
    } catch (e: any) { setScanResult({ error: e.message }); }
    setScanning(false);
  };

  const handleToggle = async () => {
    try {
      const { data } = await api.post('/monitor/toggle', { enabled: !config.enabled });
      setConfig(p => ({ ...p, enabled: data.enabled }));
    } catch (e) { console.error('Toggle failed', e); }
  };

  const handleReset = async () => {
    if (!confirm('Reset to default config?')) return;
    try {
      const { data } = await api.post('/monitor/config/reset');
      setConfig(data.config);
      setEditing(data.config);
    } catch (e) { console.error('Reset failed', e); }
  };

  const addKeyword = () => {
    const kw = keywordInput.trim();
    if (kw && !editing.entity_keywords.includes(kw)) {
      setEditing(p => ({ ...p, entity_keywords: [...p.entity_keywords, kw] }));
      setKeywordInput('');
    }
  };

  const removeKeyword = (kw: string) => {
    setEditing(p => ({ ...p, entity_keywords: p.entity_keywords.filter(k => k !== kw) }));
  };

  const handleWhatsAppShare = async (tender: any) => {
    const tid = tender?.tender_id || tender?.tenderId || '';
    if (!tid) return;
    setSharing(tid);
    try {
      const { data } = await api.post('/whatsapp/share-tender', { tender_id: tid, phone: '', language: 'bn' });
      if (data.wa_link) window.open(data.wa_link, '_blank');
    } catch (e) { console.error('Share failed', e); }
    setSharing(null);
  };

  const toggleNature = (n: string) => {
    setEditing(p => ({
      ...p,
      procurement_natures: p.procurement_natures.includes(n)
        ? p.procurement_natures.filter(x => x !== n)
        : [...p.procurement_natures, n],
    }));
  };

  const formatCurrency = (val: number) => {
    if (!val) return '—';
    if (val >= 10_000_000) return `৳${(val / 10_000_000).toFixed(2)} Cr`;
    if (val >= 100_000) return `৳${(val / 100_000).toFixed(1)} L`;
    return `৳${val.toLocaleString()}`;
  };

  const formatDate = (d: string) => {
    if (!d) return '';
    try { return new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }); }
    catch { return d.slice(0, 11); }
  };

  if (loading && !stats) {
    return <div className="p-6 text-center text-gray-400">Loading monitor dashboard...</div>;
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Bell className="text-red-500" size={24} />
            Monitor & Alert Dashboard
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Configure monitoring criteria and receive alerts for BWDB tenders
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={handleToggle}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              config.enabled
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}>
            {config.enabled ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
            {config.enabled ? 'Active' : 'Paused'}
          </button>
          <button onClick={loadAll}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-700">
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-gray-100 dark:bg-gray-800 p-1 rounded-lg w-fit">
        {(['dashboard', 'config', 'alerts'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium capitalize transition-colors ${
              tab === t ? 'bg-white dark:bg-gray-700 shadow-sm text-gray-900 dark:text-white' : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}>
            {t === 'dashboard' && <><Play size={14} className="inline mr-1" />Dashboard</>}
            {t === 'config' && <><Settings size={14} className="inline mr-1" />Configuration</>}
            {t === 'alerts' && <><Bell size={14} className="inline mr-1" />Alerts ({alerts.length})</>}
          </button>
        ))}
      </div>

      {/* ── DASHBOARD TAB ── */}
      {tab === 'dashboard' && (
        <>
          {/* Stats Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <div className="text-sm text-gray-500 dark:text-gray-400">Monitor Status</div>
              <div className={`text-lg font-bold mt-1 flex items-center gap-1 ${config.enabled ? 'text-green-600' : 'text-gray-400'}`}>
                {config.enabled ? <><CheckCircle2 size={16} /> Active</> : <><XCircle size={16} /> Paused</>}
              </div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <div className="text-sm text-gray-500 dark:text-gray-400">BWDB Tenders Tracked</div>
              <div className="text-lg font-bold mt-1 text-gray-900 dark:text-white">{stats?.tender_count || 0}</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <div className="text-sm text-gray-500 dark:text-gray-400">Alert Channels</div>
              <div className="text-lg font-bold mt-1 text-gray-900 dark:text-white flex gap-2">
                {config.alert_channels.email.enabled && <Mail size={18} className="text-blue-500" />}
                {config.alert_channels.whatsapp.enabled && <MessageCircle size={18} className="text-green-500" />}
                {!config.alert_channels.email.enabled && !config.alert_channels.whatsapp.enabled && <span className="text-sm text-gray-400">None</span>}
              </div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <div className="text-sm text-gray-500 dark:text-gray-400">Total Alerts</div>
              <div className="text-lg font-bold mt-1 text-gray-900 dark:text-white">{stats?.total_alerts || 0}</div>
            </div>
          </div>

          {/* Config Summary */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 mb-6">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
              <Filter size={16} className="text-primary-600" />
              Active Filters
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <span className="text-gray-400">Entities</span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {config.entity_keywords.map(k => <span key={k} className="px-2 py-0.5 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded text-xs">{k}</span>)}
                </div>
              </div>
              <div>
                <span className="text-gray-400">Natures</span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {config.procurement_natures.map(n => <span key={n} className="px-2 py-0.5 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 rounded text-xs">{n}</span>)}
                </div>
              </div>
              <div>
                <span className="text-gray-400">Value Range</span>
                <p className="font-medium text-gray-700 dark:text-gray-300">
                  {config.min_value_bdt ? `Min: ${formatCurrency(config.min_value_bdt)}` : 'No min'}
                  {' | '}
                  {config.max_value_bdt ? `Max: ${formatCurrency(config.max_value_bdt)}` : 'No max'}
                </p>
              </div>
              <div>
                <span className="text-gray-400">Schedule</span>
                <p className="font-medium text-gray-700 dark:text-gray-300">
                  Every {config.schedule.interval_minutes} min
                  {config.schedule.auto_scan ? ' (auto)' : ' (manual)'}
                </p>
              </div>
            </div>
          </div>

          {/* Scan Button + Latest Results */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                <Search size={16} className="text-primary-600" />
                Scan Results
              </h3>
              <button onClick={handleScan} disabled={scanning}
                className="flex items-center gap-1.5 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 text-sm font-medium">
                <Bell size={14} /> {scanning ? 'Scanning...' : 'Run Scan Now'}
              </button>
            </div>

            {scanResult && (
              <div className="mb-4 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg text-sm">
                <div className="flex items-center gap-2 text-green-700 dark:text-green-300 font-medium mb-1">
                  <CheckCircle2 size={14} /> Scan Complete
                </div>
                <div className="text-green-600 dark:text-green-400">
                  Scanned {scanResult.total_scanned} tenders → matched {scanResult.total_matched}
                  {scanResult.total_matched > 0 && ` (${scanResult.alerts_sent?.length || 0} alerts generated)`}
                </div>
              </div>
            )}

            {scanResult?.matched_tenders?.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-700 text-gray-500">
                      <th className="text-left py-2 px-2">APP ID</th>
                      <th className="text-left py-2 px-2">Live ID</th>
                      <th className="text-left py-2 px-2">Title</th>
                      <th className="text-left py-2 px-2">Nature</th>
                      <th className="text-left py-2 px-2">Source</th>
                      <th className="text-right py-2 px-2">Value</th>
                      <th className="text-left py-2 px-2">Deadline</th>
                      <th className="text-center py-2 px-2">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scanResult.matched_tenders.slice(0, 20).map((t: any) => (
                      <tr key={t.tender_id} className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30">
                        <td className="py-2 px-2 font-mono text-xs text-gray-600">{t.app_tender_id || t.tender_id}</td>
                        <td className="py-2 px-2 font-mono text-xs text-gray-500">{t.live_tender_id || '—'}</td>
                        <td className="py-2 px-2 max-w-xs truncate text-gray-900 dark:text-white">{t.app_work_name || t.title}</td>
                        <td className="py-2 px-2"><span className="px-2 py-0.5 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 rounded text-xs">{t.detected_nature}</span></td>
                        <td className="py-2 px-2">
                          <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded text-xs">
                            {t.estimated_value_source || 'LIVE'}
                          </span>
                        </td>
                        <td className="py-2 px-2 text-right font-medium">{formatCurrency(t.estimated_value_bdt)}</td>
                        <td className="py-2 px-2 text-xs">{formatDate(t.deadline)}</td>
                        <td className="py-2 px-2">
                          <div className="flex justify-center gap-1">
                            <button onClick={() => handleWhatsAppShare(t)}
                              className="p-1.5 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded"
                              title="Share on WhatsApp"><MessageCircle size={14} /></button>
                            <a href={`https://www.eprocure.gov.bd/resources/common/ViewTender.jsp?id=${t.tender_id}`}
                              target="_blank" rel="noopener noreferrer"
                              className="p-1.5 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded"
                              title="View on eGP"><ExternalLink size={14} /></a>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {scanResult.matched_tenders.length > 20 && (
                  <p className="text-center text-xs text-gray-400 mt-2">+{scanResult.matched_tenders.length - 20} more</p>
                )}
              </div>
            )}

            {scanResult?.matched_tenders?.length === 0 && (
              <div className="text-center py-8 text-gray-400">
                <Search size={32} className="mx-auto mb-2 opacity-50" />
                <p>No tenders matched current filters.</p>
                <p className="text-xs mt-1">Try adjusting entity keywords or value range in Configuration.</p>
              </div>
            )}

            {!scanResult && (
              <div className="text-center py-8 text-gray-400">
                <Bell size={32} className="mx-auto mb-2 opacity-50" />
                <p>Click "Run Scan Now" to check for matching tenders.</p>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── CONFIG TAB ── */}
      {tab === 'config' && (
        <div className="space-y-6">
          {/* Monitor Name & Status */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">General</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Monitor Name</label>
                <input type="text" value={editing.name} onChange={e => setEditing(p => ({ ...p, name: e.target.value }))}
                  className="w-full max-w-md px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
              </div>
              <div className="flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Enabled</label>
                <button onClick={() => setEditing(p => ({ ...p, enabled: !p.enabled }))}
                  className={`px-3 py-1 rounded-lg text-sm ${editing.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                  {editing.enabled ? 'Active' : 'Paused'}
                </button>
              </div>
            </div>
          </div>

          {/* Entity Keywords */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Entity Keywords</h3>
            <p className="text-xs text-gray-400 mb-3">Tenders matching any keyword in entity name or title will be captured.</p>
            <div className="flex flex-wrap gap-2 mb-3">
              {editing.entity_keywords.map(kw => (
                <span key={kw} className="flex items-center gap-1 px-2 py-1 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded-lg text-sm">
                  {kw}
                  <button onClick={() => removeKeyword(kw)} className="hover:text-red-500"><XCircle size={14} /></button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input type="text" value={keywordInput} onChange={e => setKeywordInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addKeyword()}
                placeholder="Add keyword (e.g. BWDB, LGED, Water Resources)"
                className="flex-1 max-w-md px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
              <button onClick={addKeyword} className="px-3 py-2 bg-primary-600 text-white rounded-lg text-sm hover:bg-primary-700">Add</button>
            </div>
          </div>

          {/* Procurement Natures */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Procurement Natures</h3>
            <p className="text-xs text-gray-400 mb-3">Select which types of procurement to monitor.</p>
            <div className="flex flex-wrap gap-3">
              {['Works', 'Goods', 'Services'].map(n => (
                <button key={n} onClick={() => toggleNature(n)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    editing.procurement_natures.includes(n)
                      ? 'bg-purple-50 dark:bg-purple-900/20 border-purple-300 dark:border-purple-700 text-purple-700 dark:text-purple-300'
                      : 'bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400'
                  }`}>
                  {editing.procurement_natures.includes(n) ? '✓ ' : ''}{n}
                </button>
              ))}
            </div>
          </div>

          {/* Value Range */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Value Range (BDT)</h3>
            <p className="text-xs text-gray-400 mb-3">Set to 0 for no limit. Leave both at 0 to monitor all values.</p>
            <div className="grid grid-cols-2 gap-4 max-w-md">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Minimum Value</label>
                <input type="number" value={editing.min_value_bdt} onChange={e => setEditing(p => ({ ...p, min_value_bdt: Number(e.target.value) }))}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Maximum Value</label>
                <input type="number" value={editing.max_value_bdt} onChange={e => setEditing(p => ({ ...p, max_value_bdt: Number(e.target.value) }))}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
              </div>
            </div>
            <div className="mt-3">
              <label className="block text-xs text-gray-500 mb-1">High-Value Threshold (≥ gets "high_value" tag)</label>
              <input type="number" value={editing.high_value_threshold_bdt} onChange={e => setEditing(p => ({ ...p, high_value_threshold_bdt: Number(e.target.value) }))}
                className="w-full max-w-md px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
            </div>
          </div>

          {/* Alert Channels */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Alert Channels</h3>
            <p className="text-xs text-gray-400 mb-3">Configure how you receive alerts.</p>
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <input type="checkbox" checked={editing.alert_channels.email.enabled}
                  onChange={e => setEditing(p => ({ ...p, alert_channels: { ...p.alert_channels, email: { ...p.alert_channels.email, enabled: e.target.checked } } }))}
                  className="rounded border-gray-300" />
                <Mail size={16} className="text-blue-500" />
                <div className="flex-1">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Email Alerts</label>
                  <input type="email" value={editing.alert_channels.email.recipient}
                    onChange={e => setEditing(p => ({ ...p, alert_channels: { ...p.alert_channels, email: { ...p.alert_channels.email, recipient: e.target.value } } }))}
                    placeholder="recipient@example.com"
                    className="mt-1 w-full max-w-md px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" disabled={!editing.alert_channels.email.enabled} />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <input type="checkbox" checked={editing.alert_channels.whatsapp.enabled}
                  onChange={e => setEditing(p => ({ ...p, alert_channels: { ...p.alert_channels, whatsapp: { ...p.alert_channels.whatsapp, enabled: e.target.checked } } }))}
                  className="rounded border-gray-300" />
                <MessageCircle size={16} className="text-green-500" />
                <div className="flex-1">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">WhatsApp Alerts (wa.me)</label>
                  <input type="text" value={editing.alert_channels.whatsapp.phone}
                    onChange={e => setEditing(p => ({ ...p, alert_channels: { ...p.alert_channels, whatsapp: { ...p.alert_channels.whatsapp, phone: e.target.value.replace(/[^0-9]/g, '') } } }))}
                    placeholder="8801712345678"
                    className="mt-1 w-full max-w-md px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" disabled={!editing.alert_channels.whatsapp.enabled} />
                </div>
              </div>
            </div>
          </div>

          {/* Schedule */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Scan Schedule</h3>
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <input type="checkbox" checked={editing.schedule.auto_scan}
                  onChange={e => setEditing(p => ({ ...p, schedule: { ...p.schedule, auto_scan: e.target.checked } }))}
                  className="rounded border-gray-300" />
                <label className="text-sm text-gray-700 dark:text-gray-300">Enable automatic recurring scans</label>
              </div>
              <div className="flex items-center gap-3">
                <label className="text-sm text-gray-700 dark:text-gray-300">Scan every</label>
                <input type="number" value={editing.schedule.interval_minutes}
                  onChange={e => setEditing(p => ({ ...p, schedule: { ...p.schedule, interval_minutes: Number(e.target.value) } }))}
                  className="w-20 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm text-center" />
                <label className="text-sm text-gray-500">minutes</label>
              </div>
            </div>
          </div>

          {/* Save / Reset */}
          <div className="flex gap-3">
            <button onClick={handleSave} disabled={saving}
              className="flex items-center gap-2 px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm font-medium">
              {saving ? 'Saving...' : 'Save Configuration'}
            </button>
            <button onClick={handleReset}
              className="flex items-center gap-2 px-4 py-2 border border-red-300 text-red-600 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-sm">
              <Trash2 size={14} /> Reset to Defaults
            </button>
          </div>
        </div>
      )}

      {/* ── ALERTS TAB ── */}
      {tab === 'alerts' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <Bell size={16} className="text-red-500" />
              Alert History ({alerts.length})
            </h3>
            <div className="flex gap-2">
              <button onClick={() => setShowRaw(!showRaw)}
                className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-gray-500 hover:bg-gray-50">
                {showRaw ? 'Formatted' : 'Raw JSON'}
              </button>
              <button onClick={() => { const b = new Blob([JSON.stringify(alerts, null, 2)], { type: 'application/json' }); const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'alerts.json'; a.click(); }}
                className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-gray-500 hover:bg-gray-50 flex items-center gap-1">
                <Download size={12} /> Export
              </button>
            </div>
          </div>

          {alerts.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <Bell size={40} className="mx-auto mb-3 opacity-50" />
              <p>No alerts yet. Run a scan from the Dashboard tab.</p>
            </div>
          ) : showRaw ? (
            <pre className="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/50 p-4 rounded-lg overflow-auto max-h-96">
              {JSON.stringify(alerts, null, 2)}
            </pre>
          ) : (
            <div className="space-y-3 max-h-[600px] overflow-y-auto">
              {alerts.map((a: any, i: number) => (
                <div key={i} className={`p-4 rounded-lg border ${
                  a.alert_type === 'high_value'
                    ? 'bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-800/30'
                    : 'bg-amber-50 dark:bg-amber-900/10 border-amber-200 dark:border-amber-800/30'
                }`}>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                          a.alert_type === 'high_value' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                        }`}>
                          {a.alert_type === 'high_value' ? 'HIGH VALUE' : 'NEW TENDER'}
                        </span>
                        <span className="text-xs text-gray-400">{a.tender_id}</span>
                        <span className="text-xs text-gray-400">{a.nature}</span>
                      </div>
                      <p className="font-medium text-gray-900 dark:text-white text-sm">{a.title}</p>
                      <div className="flex flex-wrap gap-4 mt-2 text-xs text-gray-500">
                        <span>Value: <strong>{formatCurrency(a.value)}</strong></span>
                        <span>Entity: {a.entity?.slice(0, 40)}</span>
                        <span>Deadline: {formatDate(a.deadline)}</span>
                        <span>Channels: {(a.channels || []).join(', ') || 'local'}</span>
                      </div>
                    </div>
                    <div className="flex gap-1 ml-3">
                      <button onClick={() => handleWhatsAppShare(a)}
                        className="p-1.5 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded"
                        title="Share on WhatsApp"><MessageCircle size={14} /></button>
                      <a href={`https://www.eprocure.gov.bd/resources/common/ViewTender.jsp?id=${a.tender_id}`}
                        target="_blank" rel="noopener noreferrer"
                        className="p-1.5 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded">
                        <ExternalLink size={14} />
                      </a>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
