import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Activity,
  BarChart3,
  Building2,
  ChevronRight,
  Clock3,
  Loader2,
  RefreshCw,
  Save,
  Sparkles,
  Users,
  Workflow,
  Zap,
} from 'lucide-react';
import {
  getClient,
  getClients,
  getClientQuota,
  getClientUsage,
  runClientPipeline,
  updateClientProfile,
  type ClientRecord,
} from '../api/client';

type DraftProfile = {
  preferred_agencies: string[];
  preferred_zones: string[];
  target_agencies: string[];
  target_zones: string[];
  experience_years: number;
  max_tender_value: number;
  min_tender_value: number;
  manpower: number;
  risk_appetite: string;
  margin_target: number;
  running_projects_count: number;
  bank_limit: number;
  current_commitment: number;
  need_for_work_score: number;
  recent_awards: string[];
  equipment: string[];
  client_note: string;
};

const formatCurrency = (value: number | string | null | undefined) => {
  const amount = Number(value || 0);
  return new Intl.NumberFormat('en-BD', {
    maximumFractionDigits: 0,
  }).format(amount);
};

const toArray = (value: unknown) => {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === 'string') {
    return value
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
};

const fromClient = (client?: ClientRecord | null): DraftProfile => {
  const config = client?.config || {};
  return {
    preferred_agencies: toArray(config.preferred_agencies),
    preferred_zones: toArray(config.preferred_zones),
    target_agencies: toArray(config.target_agencies),
    target_zones: toArray(config.target_zones),
    experience_years: Number(config.experience_years ?? 5),
    max_tender_value: Number(config.max_tender_value ?? 50000000),
    min_tender_value: Number(config.min_tender_value ?? 1000000),
    manpower: Number(config.manpower ?? 10),
    risk_appetite: String(config.risk_appetite ?? 'moderate'),
    margin_target: Number(config.margin_target ?? 12),
    running_projects_count: Number(config.running_projects_count ?? 0),
    bank_limit: Number(config.bank_limit ?? 0),
    current_commitment: Number(config.current_commitment ?? 0),
    need_for_work_score: Number(config.need_for_work_score ?? 50),
    recent_awards: toArray(config.recent_awards),
    equipment: toArray(config.equipment),
    client_note: String(config.client_note ?? ''),
  };
};

const parseText = (value: string) => value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);

export default function ClientProfile() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = useParams();
  const [draft, setDraft] = useState<DraftProfile>(fromClient(null));
  const [pipelineTenderId, setPipelineTenderId] = useState('');
  const [pipelineContext, setPipelineContext] = useState('{"source":"client-profile","priority":"normal"}');
  const [saveNotice, setSaveNotice] = useState('');
  const [pipelineNotice, setPipelineNotice] = useState('');

  const clientsQuery = useQuery({
    queryKey: ['clients'],
    queryFn: getClients,
  });

  const selectedClientId = useMemo(() => {
    const clients = clientsQuery.data?.clients || [];
    const explicitId = tenantId || '';
    if (explicitId) return explicitId;
    const hassan = clients.find((client) => client.slug === 'hassan-brothers' || /hassan/i.test(client.name));
    return hassan?.id || clients[0]?.id || '';
  }, [clientsQuery.data?.clients, tenantId]);

  useEffect(() => {
    const clients = clientsQuery.data?.clients || [];
    if (!clients.length) return;
    const matching = clients.some((client) => client.id === tenantId);
    if (!tenantId && selectedClientId) {
      navigate(`/clients/${selectedClientId}`, { replace: true });
      return;
    }
    if (tenantId && !matching && selectedClientId) {
      navigate(`/clients/${selectedClientId}`, { replace: true });
    }
  }, [clientsQuery.data?.clients, navigate, selectedClientId, tenantId]);

  const clientQuery = useQuery({
    queryKey: ['client', selectedClientId],
    queryFn: () => getClient(selectedClientId),
    enabled: Boolean(selectedClientId),
  });

  const quotaQuery = useQuery({
    queryKey: ['client-quota', selectedClientId],
    queryFn: () => getClientQuota(selectedClientId),
    enabled: Boolean(selectedClientId),
  });

  const usageQuery = useQuery({
    queryKey: ['client-usage', selectedClientId],
    queryFn: () => getClientUsage(selectedClientId, 30),
    enabled: Boolean(selectedClientId),
  });

  useEffect(() => {
    setDraft(fromClient(clientQuery.data));
  }, [clientQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () => updateClientProfile(selectedClientId, {
      preferred_agencies: draft.preferred_agencies,
      preferred_zones: draft.preferred_zones,
      target_agencies: draft.target_agencies,
      target_zones: draft.target_zones,
      experience_years: draft.experience_years,
      max_tender_value: draft.max_tender_value,
      min_tender_value: draft.min_tender_value,
      manpower: draft.manpower,
      risk_appetite: draft.risk_appetite,
      margin_target: draft.margin_target,
      running_projects_count: draft.running_projects_count,
      bank_limit: draft.bank_limit,
      current_commitment: draft.current_commitment,
      need_for_work_score: draft.need_for_work_score,
      recent_awards: draft.recent_awards,
      equipment: draft.equipment,
      client_note: draft.client_note,
    }),
    onSuccess: async () => {
      setSaveNotice('Client profile saved to the database.');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['client', selectedClientId] }),
        queryClient.invalidateQueries({ queryKey: ['clients'] }),
        queryClient.invalidateQueries({ queryKey: ['client-quota', selectedClientId] }),
        queryClient.invalidateQueries({ queryKey: ['client-usage', selectedClientId] }),
      ]);
      window.setTimeout(() => setSaveNotice(''), 3000);
    },
  });

  const pipelineMutation = useMutation({
    mutationFn: () => {
      let parsedContext: Record<string, any> = {};
      try {
        parsedContext = pipelineContext.trim() ? JSON.parse(pipelineContext) : {};
      } catch {
        parsedContext = { note: pipelineContext.trim() };
      }
      return runClientPipeline(selectedClientId, {
        ...parsedContext,
        tender_id: pipelineTenderId.trim(),
      });
    },
    onSuccess: (data) => {
      setPipelineNotice(`Pipeline finished${data?.status ? `: ${data.status}` : ''}.`);
      window.setTimeout(() => setPipelineNotice(''), 4000);
      queryClient.invalidateQueries({ queryKey: ['client-usage', selectedClientId] });
    },
  });

  const selectedClient = clientQuery.data;
  const quota = quotaQuery.data;
  const usage = usageQuery.data;
  const clients = clientsQuery.data?.clients || [];
  const headroom = Math.max(0, draft.bank_limit - draft.current_commitment);
  const quotaUsed = Number(selectedClient?.subscription?.tender_quota_used ?? quota?.used ?? 0);
  const quotaLimit = Number(selectedClient?.subscription?.tender_quota_limit ?? quota?.limit ?? 0);
  const quotaRemaining = Number(selectedClient?.subscription?.quota_remaining ?? quota?.remaining ?? 0);
  const quotaUsedPct = quotaLimit > 0 ? Math.min(100, Math.round((quotaUsed / quotaLimit) * 100)) : 0;
  const recentLogs = usage?.logs || [];

  return (
    <div className="relative min-h-full overflow-hidden px-4 py-6 sm:px-6 lg:px-8">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(14,165,233,0.14),_transparent_35%),radial-gradient(circle_at_bottom_right,_rgba(16,185,129,0.12),_transparent_30%)]" />
      <div className="relative mx-auto max-w-7xl space-y-6">
        <section className="overflow-hidden rounded-[2rem] border border-slate-200 bg-white/90 p-6 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur dark:border-slate-700 dark:bg-slate-900/85">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-primary-200 bg-primary-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.3em] text-primary-700 dark:border-primary-900 dark:bg-primary-950/40 dark:text-primary-200">
                <Sparkles size={12} />
                DB-backed client profile
              </div>
              <h1 className="mt-4 text-3xl font-semibold text-slate-900 dark:text-white sm:text-4xl">
                Client Profile
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-300">
                Review the live tenant record, tune its bid intelligence settings, and keep quota and usage aligned with the database-backed client manager.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <button
                type="button"
                onClick={() => {
                  queryClient.invalidateQueries({ queryKey: ['clients'] });
                  queryClient.invalidateQueries({ queryKey: ['client', selectedClientId] });
                  queryClient.invalidateQueries({ queryKey: ['client-quota', selectedClientId] });
                  queryClient.invalidateQueries({ queryKey: ['client-usage', selectedClientId] });
                }}
                className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 shadow-sm transition hover:border-primary-300 hover:text-primary-700 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-200"
              >
                <RefreshCw size={16} />
                Refresh data
              </button>
              <button
                type="button"
                onClick={() => selectedClientId && navigate(`/clients/${selectedClientId}`)}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-900 px-4 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
              >
                <Building2 size={16} />
                Open record
              </button>
              <button
                type="button"
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending || !selectedClientId}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-primary-600 px-4 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                Save profile
              </button>
            </div>
          </div>
          {saveNotice && <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200">{saveNotice}</div>}
          {clientsQuery.isError && (
            <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200">
              Unable to load clients.
            </div>
          )}
        </section>

        <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="space-y-4">
            <section className="rounded-[1.75rem] border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Clients</div>
                  <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">{clients.length} records</div>
                </div>
                <Users size={18} className="text-primary-600" />
              </div>
              <div className="space-y-2">
                {clientsQuery.isLoading && (
                  <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-500 dark:bg-slate-800/50">Loading clients...</div>
                )}
                {clients.map((client) => {
                  const active = client.id === selectedClientId;
                  return (
                    <button
                      key={client.id}
                      type="button"
                      onClick={() => navigate(`/clients/${client.id}`)}
                      className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                        active
                          ? 'border-primary-300 bg-primary-50 text-primary-800 shadow-sm dark:border-primary-800 dark:bg-primary-950/40 dark:text-primary-100'
                          : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950/50 dark:text-slate-200'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold">{client.name}</div>
                          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{client.slug}</div>
                        </div>
                        <ChevronRight size={16} className={active ? 'text-primary-600' : 'text-slate-400'} />
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.18em]">
                        <span className="rounded-full bg-slate-100 px-2 py-1 text-slate-500 dark:bg-slate-800 dark:text-slate-300">{client.plan}</span>
                        <span className={`rounded-full px-2 py-1 ${client.is_active ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300'}`}>
                          {client.is_active ? 'active' : 'inactive'}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="rounded-[1.75rem] border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
                <Clock3 size={16} className="text-primary-600" />
                Quota snapshot
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Used</div>
                  <div className="mt-2 text-xl font-semibold text-slate-900 dark:text-white">{quotaUsed}</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3 dark:bg-slate-800/60">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Remaining</div>
                  <div className="mt-2 text-xl font-semibold text-slate-900 dark:text-white">{quotaRemaining}</div>
                </div>
              </div>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                <div className="h-full rounded-full bg-gradient-to-r from-primary-500 to-cyan-500" style={{ width: `${quotaUsedPct}%` }} />
              </div>
              <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                {quotaUsedPct}% of the current subscription limit.
              </div>
            </section>
          </aside>

          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-[1.5rem] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Plan</div>
                    <div className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{selectedClient?.plan || '—'}</div>
                  </div>
                  <Sparkles size={18} className="text-primary-600" />
                </div>
              </div>
              <div className="rounded-[1.5rem] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Quota</div>
                    <div className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{quotaUsed}/{quotaLimit || '—'}</div>
                  </div>
                  <Workflow size={18} className="text-primary-600" />
                </div>
              </div>
              <div className="rounded-[1.5rem] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Headroom</div>
                    <div className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{formatCurrency(headroom)}</div>
                  </div>
                  <BarChart3 size={18} className="text-primary-600" />
                </div>
              </div>
              <div className="rounded-[1.5rem] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Usage events</div>
                    <div className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{usage?.summary?.total_events ?? 0}</div>
                  </div>
                  <Activity size={18} className="text-primary-600" />
                </div>
              </div>
            </div>

            <section className="rounded-[1.75rem] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Selected client</div>
                  <h2 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{selectedClient?.name || 'Select a client'}</h2>
                  <div className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                    {selectedClient?.slug || 'No slug'}
                    {selectedClient?.organization?.email ? ` • ${selectedClient.organization.email}` : ''}
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-300">
                  <div className="font-semibold text-slate-900 dark:text-white">Subscription</div>
                  <div className="mt-1">
                    {selectedClient?.subscription?.status || 'unknown'} • resets {selectedClient?.subscription?.billing_end || 'n/a'}
                  </div>
                </div>
              </div>

              <div className="mt-6 grid gap-6 lg:grid-cols-2">
                <div className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Experience years</div>
                      <input
                        type="number"
                        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                        value={draft.experience_years}
                        onChange={(e) => setDraft((current) => ({ ...current, experience_years: Number(e.target.value || 0) }))}
                      />
                    </label>
                    <label className="block">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Margin target %</div>
                      <input
                        type="number"
                        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                        value={draft.margin_target}
                        onChange={(e) => setDraft((current) => ({ ...current, margin_target: Number(e.target.value || 0) }))}
                      />
                    </label>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Max tender value</div>
                      <input
                        type="number"
                        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                        value={draft.max_tender_value}
                        onChange={(e) => setDraft((current) => ({ ...current, max_tender_value: Number(e.target.value || 0) }))}
                      />
                    </label>
                    <label className="block">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Min tender value</div>
                      <input
                        type="number"
                        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                        value={draft.min_tender_value}
                        onChange={(e) => setDraft((current) => ({ ...current, min_tender_value: Number(e.target.value || 0) }))}
                      />
                    </label>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Bank limit</div>
                      <input
                        type="number"
                        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                        value={draft.bank_limit}
                        onChange={(e) => setDraft((current) => ({ ...current, bank_limit: Number(e.target.value || 0) }))}
                      />
                    </label>
                    <label className="block">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Current commitment</div>
                      <input
                        type="number"
                        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                        value={draft.current_commitment}
                        onChange={(e) => setDraft((current) => ({ ...current, current_commitment: Number(e.target.value || 0) }))}
                      />
                    </label>
                  </div>

                  <label className="block">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Risk appetite</div>
                    <select
                      className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                      value={draft.risk_appetite}
                      onChange={(e) => setDraft((current) => ({ ...current, risk_appetite: e.target.value }))}
                    >
                      <option value="conservative">Conservative</option>
                      <option value="moderate">Moderate</option>
                      <option value="aggressive">Aggressive</option>
                    </select>
                  </label>

                  <label className="block">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Client note</div>
                    <textarea
                      rows={3}
                      className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                      value={draft.client_note}
                      onChange={(e) => setDraft((current) => ({ ...current, client_note: e.target.value }))}
                      placeholder="Notes about this client"
                    />
                  </label>
                </div>

                <div className="space-y-4">
                  <label className="block">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Preferred agencies</div>
                    <textarea
                      rows={3}
                      className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                      value={draft.preferred_agencies.join(', ')}
                      onChange={(e) => setDraft((current) => ({ ...current, preferred_agencies: parseText(e.target.value) }))}
                    />
                  </label>
                  <label className="block">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Preferred zones</div>
                    <textarea
                      rows={3}
                      className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                      value={draft.preferred_zones.join(', ')}
                      onChange={(e) => setDraft((current) => ({ ...current, preferred_zones: parseText(e.target.value) }))}
                    />
                  </label>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Target agencies</div>
                      <textarea
                        rows={3}
                        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                        value={draft.target_agencies.join(', ')}
                        onChange={(e) => setDraft((current) => ({ ...current, target_agencies: parseText(e.target.value) }))}
                      />
                    </label>
                    <label className="block">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Target zones</div>
                      <textarea
                        rows={3}
                        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                        value={draft.target_zones.join(', ')}
                        onChange={(e) => setDraft((current) => ({ ...current, target_zones: parseText(e.target.value) }))}
                      />
                    </label>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Equipment</div>
                      <textarea
                        rows={3}
                        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                        value={draft.equipment.join(', ')}
                        onChange={(e) => setDraft((current) => ({ ...current, equipment: parseText(e.target.value) }))}
                      />
                    </label>
                    <label className="block">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Recent awards</div>
                      <textarea
                        rows={3}
                        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                        value={draft.recent_awards.join(', ')}
                        onChange={(e) => setDraft((current) => ({ ...current, recent_awards: parseText(e.target.value) }))}
                      />
                    </label>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Manpower</div>
                      <input
                        type="number"
                        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                        value={draft.manpower}
                        onChange={(e) => setDraft((current) => ({ ...current, manpower: Number(e.target.value || 0) }))}
                      />
                    </label>
                    <label className="block">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Running projects</div>
                      <input
                        type="number"
                        className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                        value={draft.running_projects_count}
                        onChange={(e) => setDraft((current) => ({ ...current, running_projects_count: Number(e.target.value || 0) }))}
                      />
                    </label>
                  </div>
                </div>
              </div>
            </section>

            <section className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
              <div className="rounded-[1.75rem] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
                  <BarChart3 size={16} className="text-primary-600" />
                  Usage summary
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl bg-slate-50 p-4 dark:bg-slate-800/60">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Events</div>
                    <div className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{usage?.summary?.total_events ?? 0}</div>
                  </div>
                  <div className="rounded-2xl bg-slate-50 p-4 dark:bg-slate-800/60">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Quota consumed</div>
                    <div className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{usage?.summary?.total_quota_consumed ?? 0}</div>
                  </div>
                </div>
                <div className="mt-4 space-y-3">
                  {Object.entries(usage?.summary?.by_action || {}).map(([action, info]) => (
                    <div key={action} className="rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/40">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium text-slate-900 dark:text-white">{action}</span>
                        <span className="text-slate-500 dark:text-slate-400">{info.count} events</span>
                      </div>
                      <div className="mt-2 h-2 rounded-full bg-slate-100 dark:bg-slate-700">
                        <div
                          className="h-2 rounded-full bg-gradient-to-r from-cyan-500 to-emerald-500"
                          style={{
                            width: `${usage?.summary?.total_quota_consumed
                              ? Math.max(6, Math.round((info.quota_consumed / usage.summary.total_quota_consumed) * 100))
                              : 0}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                  {!Object.keys(usage?.summary?.by_action || {}).length && (
                    <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-500 dark:bg-slate-800/40 dark:text-slate-400">
                      No quota activity in the selected window.
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-[1.75rem] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
                    <Zap size={16} className="text-primary-600" />
                    Run client pipeline
                  </div>
                  <button
                    type="button"
                    onClick={() => pipelineMutation.mutate()}
                    disabled={pipelineMutation.isPending || !selectedClientId}
                    className="inline-flex items-center gap-2 rounded-2xl bg-primary-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {pipelineMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Workflow size={16} />}
                    Execute
                  </button>
                </div>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <label className="block">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Tender ID</div>
                    <input
                      value={pipelineTenderId}
                      onChange={(e) => setPipelineTenderId(e.target.value)}
                      className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                      placeholder="Optional tender id"
                    />
                  </label>
                  <label className="block">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Context JSON</div>
                    <textarea
                      rows={3}
                      value={pipelineContext}
                      onChange={(e) => setPipelineContext(e.target.value)}
                      className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-primary-400 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                    />
                  </label>
                </div>
                {pipelineNotice && <div className="mt-4 rounded-2xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm text-cyan-800 dark:border-cyan-900 dark:bg-cyan-950/30 dark:text-cyan-200">{pipelineNotice}</div>}
                {pipelineMutation.data && (
                  <pre className="mt-4 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-2xl bg-slate-950 p-4 text-xs text-slate-100">
                    {JSON.stringify(pipelineMutation.data, null, 2)}
                  </pre>
                )}
              </div>
            </section>

            <section className="rounded-[1.75rem] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
                  <Activity size={16} className="text-primary-600" />
                  Recent usage logs
                </div>
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">{usage?.days ?? 30} day window</div>
              </div>
              <div className="mt-4 space-y-3">
                {recentLogs.slice(0, 8).map((log) => (
                  <div key={log.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/40">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <div className="text-sm font-medium text-slate-900 dark:text-white">{log.action}</div>
                        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{log.tender_id}</div>
                      </div>
                      <div className="text-sm text-slate-600 dark:text-slate-300">
                        {log.quota_consumed} quota
                      </div>
                    </div>
                    <div className="mt-2 text-xs text-slate-400">{log.created_at}</div>
                  </div>
                ))}
                {!recentLogs.length && (
                  <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-500 dark:bg-slate-800/40 dark:text-slate-400">
                    No usage logs found for this client in the selected period.
                  </div>
                )}
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
