import { useEffect, useState } from 'react';
import { Search, Building2, FolderTree, ChevronRight, RefreshCw, Info } from 'lucide-react';
import { getDeptTreeMinistries, logUiEvent, searchLiveTenders } from '../api/client';

// Whitelist of actual live tender status values
const LIVE_STATUSES = ['live', 'live_tender_shell', 'open', 'ongoing'];

const formatTenderAmount = (value: unknown) => {
  const amount = Number(value || 0);
  if (!Number.isFinite(amount) || amount <= 0) return '—';
  if (amount >= 1e7) return `BDT ${(amount / 1e7).toFixed(2)} Cr`;
  if (amount >= 1e5) return `BDT ${(amount / 1e5).toFixed(2)} Lakh`;
  return `BDT ${amount.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
};

const formatAppEstimate = (value: unknown, source?: string) => {
  const amount = Number(value || 0);
  if (!Number.isFinite(amount) || amount <= 0) return '—';
  if (amount >= 1e7) return `BDT ${(amount / 1e7).toFixed(2)} Cr`;
  if (amount >= 1e5) return `BDT ${(amount / 1e5).toFixed(2)} Lakh`;
  if ((source || '').toUpperCase() === 'APP' && amount >= 1) {
    return `BDT ${amount.toFixed(0)} Lakh`;
  }
  return `BDT ${amount.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
};

const getAppEstimateDisplay = (t: any) => {
  const display = t?.notice_data?.app_estimated_value_display || t?.app_estimated_value_display;
  if (display) return String(display);
  const value = t?.notice_data?.app_estimated_value_bdt || t?.notice_data?.estimated_amount_bdt || t?.notice_data?.estimated_cost_bdt || t?.estimated_value_bdt;
  return formatAppEstimate(value, t?.estimated_value_source || 'APP');
};

const inferMinistry = (procuringEntity?: string, fallback?: string) => {
  const raw = String(procuringEntity || '').trim();
  if (raw) {
    const first = raw.split(/,,|,| \| /).map((part) => part.trim()).filter(Boolean)[0];
    if (first) return first;
  }
  return fallback || 'Unknown Ministry';
};

export default function LiveTenders() {
  const [ministries, setMinistries] = useState<any[]>([]);
  const [selectedMinistry, setSelectedMinistry] = useState<any>(null);
  const [offices, setOffices] = useState<any[]>([]);
  const [tenders, setTenders] = useState<any[]>([]);
  const [tenderTotal, setTenderTotal] = useState(0);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [selectedTender, setSelectedTender] = useState<any>(null);

  const getTenderId = (t: any) => t?.notice_data?.tender_id || t?.notice_data?.app_tender_id || t?.notice_data?.live_tender_id || t?.tender_id || '—';
  const getPackageNo = (t: any) => t?.notice_data?.package_no || t?.package_no || '—';
  const getWorkName = (t: any) => t?.notice_data?.app_work_name || t?.notice_data?.live_work_name || t?.notice_data?.work_name || t?.title || '—';
  const getProcuringEntity = (t: any) => t?.notice_data?.procuring_entity || t?.procuring_entity || '—';
  const getMinistry = (t: any) => inferMinistry(getProcuringEntity(t), t?.notice_data?.ministry || t?.ministry);

  const loadMinistries = async () => {
    setLoading(true); setError('');
    try {
      const data = await getDeptTreeMinistries();
      setMinistries(data);
      if (data.length === 1) {
        await selectMinistry(data[0]);
      }
      await logUiEvent({
        feature: 'live_tenders',
        action: 'load_ministries',
        data: { ministries: data.length },
      });
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  };

  const selectMinistry = async (ministry: any) => {
    setLoading(true);
    setError('');
    try {
      setSelectedMinistry(ministry);
      setOffices(ministry.offices || []);
      setSelectedTender(null);
      await searchTenders(1, ministry);
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  };

  const searchTenders = async (p = 1, ministryOverride?: any) => {
    setLoading(true);
    try {
      const ministry = ministryOverride || selectedMinistry;
      const data = await searchLiveTenders({
        department_id: ministry?.id || '',
        keyword: keyword || undefined,
        page: p,
        page_size: 50,
      });
      setTenders(data.tenders || []);
      setTenderTotal(data.total || 0);
      setPage(p);
      setSelectedTender((data.tenders || [])[0] || null);
      await logUiEvent({
        feature: 'live_tenders',
        action: 'search_live',
        data: {
          department_id: ministry?.id || '',
          keyword: keyword || '',
          page: p,
          total: data.total || 0,
          returned: (data.tenders || []).length,
          statuses: Array.from(new Set((data.tenders || []).map((t: any) => String(t.status || '').toLowerCase()))),
        },
      });
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadMinistries(); }, []);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <FolderTree className="text-primary-600" size={28} />
          Live Tenders — Notice-First View
        </h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-0.5">Browse live tenders by tender ID, then open a notice panel for primary data and APP estimate.</p>
      </div>

      {error && <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded-lg text-sm">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-1 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="font-semibold text-gray-900 dark:text-white text-sm mb-3 flex items-center gap-2">
            <Building2 size={16} className="text-primary-600" /> Ministries
          </h3>
          {loading && !selectedMinistry ? (
            <div className="space-y-2">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-9 bg-gray-100 dark:bg-gray-700 rounded animate-pulse" />)}</div>
          ) : (
            <div className="space-y-1 max-h-[calc(100vh-280px)] overflow-y-auto">
              {ministries.map((m: any) => (
                <button key={m.id} onClick={() => selectMinistry(m)}
                  className={`w-full p-2.5 rounded-lg text-left text-xs transition-colors flex items-center justify-between ${
                    selectedMinistry?.id === m.id ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300 border border-primary-200 dark:border-primary-700' : 'hover:bg-gray-50 dark:hover:bg-gray-700/30 text-gray-700 dark:text-gray-300'
                  }`}>
                  <div>
                    <div className="font-medium truncate max-w-[160px]">{m.name}</div>
                    <div className="text-gray-400">{m.type || 'Agency tree'}</div>
                  </div>
                  <ChevronRight size={14} className="text-gray-400 shrink-0" />
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="lg:col-span-3 space-y-4">
          {!selectedMinistry ? (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 text-center text-gray-400 flex flex-col items-center gap-2">
              <FolderTree size={48} className="opacity-30" />
              <p className="text-sm">Select a ministry to view its procuring entities and packages</p>
            </div>
          ) : (
            <>
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-gray-900 dark:text-white text-sm">
                    {selectedMinistry.name} — {selectedMinistry.office_count} PE Offices
                  </h3>
                </div>
                <div className="flex gap-2 mb-3">
                  <div className="flex-1 relative">
                    <Search size={14} className="absolute left-2.5 top-2.5 text-gray-400" />
                    <input value={keyword} onChange={e => setKeyword(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchTenders(1)} placeholder="Search packages by keyword..." className="w-full pl-8 pr-3 py-2 text-xs border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white" />
                  </div>
                  <button onClick={() => searchTenders(1)} className="px-3 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-xs font-medium transition-colors">Search</button>
                </div>
                {offices.length > 0 && (
                  <div className="flex gap-1 flex-wrap">
                    {offices.slice(0, 20).map((o: any) => (
                      <span key={o.id} className="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded text-xs cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-600" title={`${o.package_count} packages · BDT ${(o.total_estimated_bdt / 1e7).toFixed(1)} Cr`}>
                        {o.name.length > 30 ? o.name.slice(0, 30) + '...' : o.name}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-gray-900 dark:text-white text-sm">Tender IDs ({tenderTotal.toLocaleString()})</h3>
                  <button onClick={() => searchTenders(page)} className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded text-gray-400 transition-colors"><RefreshCw size={14} /></button>
                </div>
                {loading ? (
                  <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-12 bg-gray-100 dark:bg-gray-700 rounded animate-pulse" />)}</div>
                ) : tenders.length === 0 ? (
                  <div className="py-8 text-center text-gray-400 text-sm">No live tenders found. Try a different ministry or keyword.</div>
                ) : (
                  <div className="space-y-2 max-h-[500px] overflow-y-auto">
                    {tenders
                      .filter((t: any) => LIVE_STATUSES.some((s) => String(t.status || '').toLowerCase().includes(s)))
                      .map((t: any, i: number) => (
                        <button
                          key={i}
                          onClick={() => setSelectedTender(t)}
                          className={`w-full p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg border text-left transition-colors ${
                            selectedTender?.tender_id === t.tender_id
                              ? 'border-primary-400 ring-1 ring-primary-400 dark:border-primary-600'
                              : 'border-gray-200 dark:border-gray-600 hover:border-primary-300'
                          }`}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1 min-w-0">
                              <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-gray-900 dark:text-white">
                                <span className="bg-green-100 dark:bg-green-800 text-green-800 dark:text-green-200 text-xs font-semibold px-2.5 py-0.5 rounded">Live</span>
                                <span className="font-semibold">Tender ID {getTenderId(t)}</span>
                                <span className="text-gray-400">•</span>
                                <span className="text-gray-600 dark:text-gray-300">Package No {getPackageNo(t)}</span>
                              </div>
                              <div className="text-xs text-gray-500 mt-0.5 truncate">
                                {getWorkName(t)}
                              </div>
                            </div>
                            <ChevronRight size={14} className="text-gray-400 shrink-0 ml-3" />
                          </div>
                        </button>
                      ))}
                  </div>
                )}
                {tenderTotal > 50 && (
                  <div className="flex items-center justify-center gap-2 mt-3">
                    <button disabled={page <= 1} onClick={() => searchTenders(page - 1)} className="px-3 py-1.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded-lg disabled:opacity-40 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors">Previous</button>
                    <span className="text-xs text-gray-400">Page {page} of {Math.ceil(tenderTotal / 50)}</span>
                    <button disabled={page * 50 >= tenderTotal} onClick={() => searchTenders(page + 1)} className="px-3 py-1.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded-lg disabled:opacity-40 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors">Next</button>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
        <div className="lg:col-span-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-900 dark:text-white text-sm flex items-center gap-2">
            <Info size={16} className="text-primary-600" />
            Tender Notice Detail
          </h3>
            {selectedTender && (
              <div className="text-xs text-gray-400 font-mono">{getTenderId(selectedTender)}</div>
            )}
          </div>
          {!selectedTender ? (
            <div className="py-8 text-center text-gray-400 text-sm">Click a tender ID to see the primary notice data and APP estimate.</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
              {[
                ['Tender ID', getTenderId(selectedTender)],
                ['Package No', getPackageNo(selectedTender)],
                ['Work Name', getWorkName(selectedTender)],
                ['Procuring Entity', getProcuringEntity(selectedTender)],
                ['Ministry', getMinistry(selectedTender)],
                ['Published Date', selectedTender.notice_data?.published_date || selectedTender.published_date],
                ['Deadline', selectedTender.notice_data?.deadline || selectedTender.deadline],
                ['APP Estimate', getAppEstimateDisplay(selectedTender)],
                ['Live Estimate', formatTenderAmount(selectedTender.notice_data?.live_estimated_value_bdt || selectedTender.notice_data?.live_value_bdt)],
                ['Estimate Source', selectedTender.estimated_value_source || (Number(selectedTender.notice_data?.app_estimated_value_bdt || selectedTender.notice_data?.estimated_amount_bdt || selectedTender.notice_data?.estimated_cost_bdt || selectedTender.estimated_value_bdt || 0) > 0 ? 'APP' : 'LIVE')],
                ['Category', selectedTender.notice_data?.category || selectedTender.category],
                ['Financial Year', selectedTender.notice_data?.financial_year || '—'],
                ['Status', selectedTender.status],
                ['APP Code', selectedTender.notice_data?.app_code || '—'],
              ].map(([label, value]) => (
                <div key={label as string} className="rounded-lg border border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/30 px-3 py-2">
                  <div className="text-[10px] uppercase tracking-[0.2em] text-gray-400">{label as string}</div>
                  <div className="mt-1 text-gray-900 dark:text-white font-medium break-words">{String(value ?? '—')}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
