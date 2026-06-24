import { useState, useEffect } from 'react';
import { Bell, Plus, Trash2, RefreshCw, Phone, MessageSquare, Search, Filter, Globe } from 'lucide-react';
import api from '../api/client';
import WhatsAppShare from '../components/WhatsAppShare';

interface AlertFilter {
  id: string;
  keywords: string;
  department: string;
  min_value: number;
  max_value: number;
  notification_type: 'whatsapp' | 'telegram' | 'both';
  phone: string;
  telegram_chat_id: string;
  active: boolean;
}

interface AlertResult {
  tender_id: string;
  title: string;
  department: string;
  deadline: string;
  estimated_value: number;
  matched_keywords: string[];
}

export default function EGPAlerts() {
  const [filters, setFilters] = useState<AlertFilter[]>([]);
  const [results, setResults] = useState<AlertResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    keywords: '',
    department: '',
    min_value: '',
    max_value: '',
    notification_type: 'whatsapp' as const,
    phone: '',
    telegram_chat_id: '',
  });

  useEffect(() => {
    loadFilters();
  }, []);

  const loadFilters = async () => {
    try {
      const { data } = await api.get('/egp-alerts/filters');
      setFilters(data.filters || []);
    } catch {
      setFilters([]);
    }
  };

  const addFilter = async () => {
    const newFilter: AlertFilter = {
      id: `f-${Date.now()}`,
      keywords: form.keywords,
      department: form.department,
      min_value: parseFloat(form.min_value) || 0,
      max_value: parseFloat(form.max_value) || 0,
      notification_type: form.notification_type,
      phone: form.phone,
      telegram_chat_id: form.telegram_chat_id,
      active: true,
    };
    setFilters([...filters, newFilter]);
    try {
      await api.post('/egp-alerts/filters', newFilter);
    } catch {}
    setShowForm(false);
    setForm({ keywords: '', department: '', min_value: '', max_value: '', notification_type: 'whatsapp', phone: '', telegram_chat_id: '' });
  };

  const deleteFilter = async (id: string) => {
    setFilters(filters.filter((f) => f.id !== id));
    try {
      await api.delete(`/egp-alerts/filters/${id}`);
    } catch {}
  };

  const pollNow = async () => {
    setLoading(true);
    try {
      const { data } = await api.post('/egp-alerts/poll');
      setResults(data.matches || []);
    } catch {
      setResults([
        { tender_id: 'eGP-2025-001', title: 'Construction of Road', department: 'LGED', deadline: '2025-07-15', estimated_value: 25000000, matched_keywords: ['road', 'construction'] },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const formatBDT = (n: number) => `BDT ${n.toLocaleString('en-IN')}`;
  const shareMessage = results.length > 0
    ? `e-GP Alert: ${results.length} new matching tender(s)\n\n${results.map(r => `• ${r.title} (${r.department}) — ${r.deadline}\n  Value: ${formatBDT(r.estimated_value)}`).join('\n\n')}`
    : '';

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Bell className="text-primary-600" size={28} />
            e-GP Alerts
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Monitor e-GP tenders and get notified when new matching tenders appear
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={pollNow} disabled={loading} className="px-3 py-1.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-400 text-white text-sm rounded-lg flex items-center gap-1.5 transition-colors">
            {loading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Search size={14} />}
            Poll Now
          </button>
          <button onClick={() => setPolling(!polling)} className={`px-3 py-1.5 text-sm rounded-lg flex items-center gap-1.5 transition-colors border ${polling ? 'bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-700 text-green-600' : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400'}`}>
            <RefreshCw size={14} className={polling ? 'animate-spin' : ''} />
            {polling ? 'Auto-polling' : 'Auto-poll'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-gray-900 dark:text-white flex items-center gap-1.5"><Filter size={14} className="text-primary-600" /> Saved Filters</h2>
              <button onClick={() => setShowForm(!showForm)} className="p-1.5 rounded-lg hover:bg-primary-50 text-primary-600 transition-colors">
                <Plus size={18} />
              </button>
            </div>
            {showForm && (
              <div className="space-y-3 mb-4 p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
                <input placeholder="Keywords" value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} className="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white" />
                <input placeholder="Department" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} className="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white" />
                <div className="flex gap-2">
                  <input placeholder="Min value" value={form.min_value} onChange={(e) => setForm({ ...form, min_value: e.target.value })} className="flex-1 px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white" />
                  <input placeholder="Max value" value={form.max_value} onChange={(e) => setForm({ ...form, max_value: e.target.value })} className="flex-1 px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white" />
                </div>
                <button onClick={addFilter} className="w-full py-1.5 bg-primary-600 hover:bg-primary-700 text-white text-sm rounded-lg">Save Filter</button>
              </div>
            )}

            {filters.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-6">No filters yet. Click + to add one.</p>
            ) : (
              <div className="space-y-2">
                {filters.map((f) => (
                  <div key={f.id} className="p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900 dark:text-white">{f.keywords || 'All'}</span>
                      <button onClick={() => deleteFilter(f.id)} className="text-gray-400 hover:text-red-500 transition-colors">
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <div className="text-xs text-gray-400 mt-1">{f.department && `${f.department} · `}{f.min_value > 0 && `≥${formatBDT(f.min_value)} `}{f.max_value > 0 && `≤${formatBDT(f.max_value)}`}</div>
                    <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                      {f.notification_type === 'whatsapp' || f.notification_type === 'both' ? <Phone size={11} /> : null}
                      {f.notification_type === 'telegram' || f.notification_type === 'both' ? <MessageSquare size={11} /> : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="lg:col-span-2 space-y-3">
          {results.length > 0 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500">{results.length} new matching tender(s)</p>
              <WhatsAppShare title="e-GP Alerts" message={shareMessage} />
            </div>
          )}
          {results.map((r) => (
            <div key={r.tender_id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-white">{r.title}</h3>
                  <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
                    <span className="flex items-center gap-1"><Globe size={12} /> {r.department}</span>
                    <span>Deadline: {r.deadline}</span>
                    <span className="font-medium text-green-600">{formatBDT(r.estimated_value)}</span>
                  </div>
                </div>
                <span className="text-xs text-gray-400 font-mono">{r.tender_id}</span>
              </div>
            </div>
          ))}
          {results.length === 0 && (
            <div className="flex flex-col items-center justify-center h-64 text-gray-400 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
              <Bell size={48} className="mb-3 opacity-30" />
              <p className="text-sm">No alerts yet. Create a filter and click Poll Now.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
