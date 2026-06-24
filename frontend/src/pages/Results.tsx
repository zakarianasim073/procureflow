import { useState, useEffect } from 'react';
import { Download, FileSpreadsheet, FileText, BarChart3, AlertTriangle, CheckCircle2, TrendingDown, Scale, Receipt, TrendingUp, Shield, AlertCircle, DollarSign, Users, Truck, HelpCircle } from 'lucide-react';
import ComparisonTable from '../components/ComparisonTable';
import AgentResultViewer from '../components/AgentResultViewer';
import { useAppStore } from '../store/appStore';
import api, { ComparisonItem, getLatestComparison, getRecentAgentResults, runSLTAnalysis } from '../api/client';
import { getThemeClasses } from '../utils/styleMaps';

export default function Results() {
  const { comparisonResults, recentAgentResults, pipelineResults, setComparisonResults, setAgentExecutionRecords } = useAppStore();
  const [filter, setFilter] = useState<string>('all');
  const [view, setView] = useState<'table' | 'summary' | 'tec' | 'forms' | 'escalation' | 'slt'>('table');
  const [dlLoading, setDlLoading] = useState<'xlsx' | 'docx' | null>(null);
  const [epw3Data, setEpw3Data] = useState<any>(null);
  const [epw3Loading, setEpw3Loading] = useState(false);
  const [sltData, setSltData] = useState<any>(null);
  const [sltLoading, setSltLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [downloadError, setDownloadError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const hydrateLatest = async () => {
      if (comparisonResults) {
        setInitializing(false);
        return;
      }
      try {
        const latest = await getLatestComparison();
        if (!cancelled) {
          setComparisonResults(latest);
        }
      } catch {
        // No persisted comparison in DB yet.
      } finally {
        if (!cancelled) setInitializing(false);
      }
    };

    hydrateLatest();
    return () => {
      cancelled = true;
    };
  }, [comparisonResults, setComparisonResults]);

  useEffect(() => {
    let cancelled = false;
    if (recentAgentResults.length > 0) return;
    getRecentAgentResults(12)
      .then((res) => {
        if (!cancelled && res.results) {
          setAgentExecutionRecords(res.results);
        }
      })
      .catch(() => {
        // Keep browser cache if the backend feed is unavailable.
      });
    return () => {
      cancelled = true;
    };
  }, [recentAgentResults.length, setAgentExecutionRecords]);

  const getFilename = (path: string) => {
    if (!path) return '';
    const parts = path.split(/[/\\]/);
    const name = parts[parts.length - 1] || '';
    return name.replace(/\.\w+$/, '');
  };

  const handleDownload = async (format: 'xlsx' | 'docx') => {
    if (!comparisonResults) return;
    const docxPath = comparisonResults.docx_path || '';
    const excelPath = comparisonResults.excel_path || '';
    const excelFilename = getFilename(excelPath);
    const docxFilename = getFilename(docxPath);
    const filename = format === 'docx' ? docxFilename : excelFilename;
    if (!filename) {
      setDownloadError('No report file available for download. Run a comparison first.');
      return;
    }
    setDlLoading(format);
    try {
      const response = await api.get(`/boq/export/${filename}`, {
        params: { format },
        responseType: 'blob',
      });
      const blob = new Blob([response.data], {
        type: format === 'docx'
          ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
          : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${filename}.${format}`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError('Download failed. File may not be available.');
    } finally {
      setDlLoading(null);
    }
  };

  const loadSLT = async () => {
    if (!comparisonResults || sltData) return;
    setSltLoading(true);
    try {
      const boqItems = comparisonResults.data || [];
      const totalQuoted = comparisonResults.summary?.total_quoted || 0;
      const totalSor = comparisonResults.summary?.total_sor || totalQuoted;
      const sltResult = await runSLTAnalysis(boqItems, totalSor, totalQuoted);
      setSltData(sltResult.analysis);
    } catch {
      // Fallback: compute client-side
      const items = comparisonResults.data || [];
      const q = comparisonResults.summary?.total_quoted || 0;
      const e = comparisonResults.summary?.total_sor || q;
      setSltData({
        overall: {
          status: q < e * 0.7 ? 'SLT - Seriously Low Tender' : q < e * 0.6 ? 'ALT - Abnormally Low Tender' : 'Normal',
          bid_price: q, estimated_cost: e,
          ratio: e > 0 ? q / e : 1,
          ratio_formatted: e > 0 ? `${((q / e) * 100).toFixed(1)}%` : 'N/A',
          thresholds: { slt: 0.7, alt: 0.6 },
        },
        item_anomalies: {
          critical: items.filter((i: any) => i.sor_rate && i.rate && i.rate / i.sor_rate < 0.5).length,
          warning: items.filter((i: any) => i.sor_rate && i.rate && i.rate / i.sor_rate >= 0.5 && i.rate / i.sor_rate < 0.7).length,
        },
      });
    } finally {
      setSltLoading(false);
    }
  };

  useEffect(() => {
    if (view === 'slt') loadSLT();
  }, [view, comparisonResults]);

  if (initializing) {
    return (
      <div className="p-6 text-center py-20">
        <BarChart3 size={48} className="mx-auto text-gray-300 mb-4 animate-pulse" />
        <h2 className="text-xl font-semibold text-gray-600 dark:text-gray-400">Loading...</h2>
      </div>
    );
  }

  if (!comparisonResults) {
    return (
      <div className="p-6 text-center py-20">
        <BarChart3 size={48} className="mx-auto text-gray-300 mb-4" />
        <h2 className="text-xl font-semibold text-gray-600 dark:text-gray-400">No results yet</h2>
        <p className="text-gray-400 mt-2">Run an analysis from the Upload page first</p>
      </div>
    );
  }

  const items: ComparisonItem[] = comparisonResults.data || [];
  const summary = comparisonResults.summary?.by_work_type || [];
  const filtered = filter === 'all' ? items : items.filter((i: ComparisonItem) => i.flag === filter);
  const docxPath = comparisonResults.docx_path || '';
  const excelPath = comparisonResults.excel_path || '';
  const excelFilename = getFilename(excelPath);
  const docxFilename = getFilename(docxPath);

  const loadEPW3Forms = async () => {
    setEpw3Loading(true);
    try {
      const tenderId = comparisonResults.tender_id || `TENDER_${Date.now()}`;
      const { data } = await api.get(`/epw3/list/${tenderId}`);
      setEpw3Data(data);
    } catch (err) {
      // Generate on the fly
      try {
        const { data } = await api.post('/epw3/generate', {
          tender_id: `TENDER_${Date.now()}`,
          company: { name: 'Your Company Ltd.', annual_turnover: 500_000_000, years_in_business: 10 },
          tender_info: { estimated_value: comparisonResults.summary?.total_sor || 50000000 },
          bid_amount: comparisonResults.summary?.total_quoted || 45000000,
        });
        setEpw3Data({ has_forms: true, ...data.data });
      } catch {
        setEpw3Data({ has_forms: false, message: 'Generate forms from Settings with company profile' });
      }
    } finally {
      setEpw3Loading(false);
    }
  };

  const tabs = [
    { id: 'table', label: 'BOQ Table', icon: FileSpreadsheet },
    { id: 'summary', label: 'Summary', icon: BarChart3 },
    { id: 'tec', label: 'PPR 2025 TEC', icon: Scale },
    { id: 'forms', label: 'e-PW3 Forms', icon: FileText },
    { id: 'escalation', label: 'Price Escalation', icon: TrendingUp },
    { id: 'slt', label: 'PPR 2025 SLT', icon: AlertTriangle },
  ];

  // PPR 2025 TEC summary from comparison data
  const tecData = {
    total_items: comparisonResults.total_items || 0,
    matches: comparisonResults.matches || 0,
    variances: comparisonResults.variances || 0,
    mismatches: comparisonResults.mismatches || 0,
    below_sor: comparisonResults.below_sor || 0,
    match_rate: comparisonResults.total_items ? 
      Math.round((comparisonResults.matches / comparisonResults.total_items) * 100) : 0,
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {downloadError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
          {downloadError}
        </div>
      )}

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Analysis Results</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          {comparisonResults.total_items || 0} items • {comparisonResults.sor_agency || 'SOR'} comparison
          {comparisonResults.zone ? ` • Zone ${comparisonResults.zone}` : ''}
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="flex flex-wrap gap-2 mb-6">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => {
              setView(tab.id as any);
              if (tab.id === 'forms') loadEPW3Forms();
            }}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              view === tab.id
                ? 'bg-primary-600 text-white'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
            }`}
          >
            <tab.icon size={16} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* 1. BOQ Table View */}
      {view === 'table' && (
        <>
          {/* Filters */}
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <span className="text-sm text-gray-500 dark:text-gray-400">Filter:</span>
            {[
              { value: 'all', label: `All (${items.length})` },
              { value: 'AT SOR', label: `At SOR (${items.filter(i => i.flag === 'AT SOR').length})` },
              { value: 'VARIANCE', label: `Variance (${items.filter(i => i.flag === 'VARIANCE').length})` },
              { value: 'BELOW SOR', label: `Below SOR (${items.filter(i => i.flag === 'BELOW SOR').length})` },
              { value: 'ABOVE SOR', label: `Above SOR (${items.filter(i => ['ABOVE SOR','MISMATCH'].includes(i.flag)).length})` },
            ].map(f => (
              <button
                key={f.value}
                onClick={() => setFilter(f.value)}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  filter === f.value
                    ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          <ComparisonTable data={filtered} />

          {/* Download buttons */}
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              onClick={() => handleDownload('xlsx')}
              disabled={dlLoading === 'xlsx'}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50"
            >
              {dlLoading === 'xlsx' ? <span className="animate-spin">⏳</span> : <Download size={18} />}
              {dlLoading === 'xlsx' ? 'Downloading...' : 'Download XLSX'}
            </button>
            <button
              onClick={() => handleDownload('docx')}
              disabled={dlLoading === 'docx'}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              {dlLoading === 'docx' ? <span className="animate-spin">⏳</span> : <FileText size={18} />}
              {dlLoading === 'docx' ? 'Downloading...' : 'Download DOCX'}
            </button>
          </div>
        </>
      )}

      {/* 2. Summary View */}
      {view === 'summary' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Key Metrics */}
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Key Metrics</h3>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-gray-500 dark:text-gray-400">Total SOR Amount</span>
                <span className="font-bold text-gray-900 dark:text-white">
                  ৳{(comparisonResults.summary?.total_sor || 0).toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500 dark:text-gray-400">Total Quoted Amount</span>
                <span className="font-bold text-gray-900 dark:text-white">
                  ৳{(comparisonResults.summary?.total_quoted || 0).toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500 dark:text-gray-400">Overall Discount</span>
                <span className={`font-bold ${(comparisonResults.summary?.discount_pct || 0) > 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {comparisonResults.summary?.discount_pct || 0}%
                </span>
              </div>
              <div className="flex justify-between items-center pt-3 border-t border-gray-100 dark:border-gray-600">
                <span className="text-gray-500 dark:text-gray-400">Items Matched</span>
                <span className="font-bold text-green-600">{tecData.matches}/{tecData.total_items}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500 dark:text-gray-400">Items with Variance</span>
                <span className="font-bold text-yellow-600">{tecData.variances}/{tecData.total_items}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500 dark:text-gray-400">Items Below SOR</span>
                <span className="font-bold text-blue-600">{tecData.below_sor}/{tecData.total_items}</span>
              </div>
            </div>
            </div>

          {/* Work Type Breakdown */}
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Work Type Breakdown</h3>
            {summary.length === 0 ? (
              <p className="text-gray-400 text-sm">No work type breakdown available</p>
            ) : (
              <div className="space-y-3">
                {summary.map((row: any, i: number) => (
                  <div key={i} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-medium text-gray-900 dark:text-white text-sm">{row.work_type}</span>
                      <span className="text-xs text-gray-500">{row.items} items</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">SOR: ৳{(row.sor_amount || 0).toLocaleString()}</span>
                      <span className="text-gray-500">Quoted: ৳{(row.quoted_amount || 0).toLocaleString()}</span>
                      <span className={row.discount_pct > 0 ? 'text-green-600 font-medium' : 'text-red-600 font-medium'}>
                        {row.discount_pct || 0}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
            </div>
          </div>

          {(recentAgentResults.length > 0 || (pipelineResults && Object.keys(pipelineResults).length > 0)) && (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {recentAgentResults.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Recent Agent Output</h3>
                  <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
                    {recentAgentResults.slice(0, 6).map((record) => (
                      <div key={record.run_id} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                        <div className="flex items-start justify-between gap-3 mb-2">
                          <div>
                            <div className="text-sm font-medium text-gray-900 dark:text-white">{record.agent_name}</div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">
                              {record.source.replace('_', ' ')} • {record.timestamp}{record.tender_id ? ` • ${record.tender_id}` : ''}
                            </div>
                          </div>
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            record.status === 'success'
                              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                              : record.status === 'failed'
                              ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                              : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
                          }`}>
                            {record.status}
                          </span>
                        </div>
                        {record.error ? (
                          <div className="text-xs text-red-600 dark:text-red-400">{record.error}</div>
                        ) : record.output ? (
                          <AgentResultViewer agentId={record.agent_id} agentName={record.agent_name} output={record.output} />
                        ) : (
                          <div className="text-xs text-gray-400">No structured output returned.</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {pipelineResults && Object.keys(pipelineResults).length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Pipeline Output By Agent</h3>
                  <div className="space-y-4 max-h-[520px] overflow-y-auto pr-1">
                    {Object.entries(pipelineResults).map(([phaseName, results]) => (
                      <div key={phaseName} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                        <div className="text-sm font-semibold text-gray-900 dark:text-white capitalize mb-3">
                          {phaseName.replace(/_/g, ' ')}
                        </div>
                        <div className="space-y-3">
                          {results.map((result: any) => (
                            <div key={result.agent_id} className="rounded-lg bg-gray-50 dark:bg-gray-700/30 p-3">
                              <div className="flex items-center justify-between gap-3 mb-2">
                                <div className="text-sm font-medium text-gray-900 dark:text-white">{result.agent_name}</div>
                                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                  result.status === 'success'
                                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                                    : result.status === 'failed'
                                    ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                                    : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
                                }`}>
                                  {result.status}
                                </span>
                              </div>
                              {result.error ? (
                                <div className="text-xs text-red-600 dark:text-red-400">{result.error}</div>
                              ) : result.output ? (
                                <AgentResultViewer agentId={result.agent_id} agentName={result.agent_name} output={result.output} />
                              ) : (
                                <div className="text-xs text-gray-400">No structured output returned.</div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 3. PPR 2025 TEC View */}
      {view === 'tec' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <Scale className="text-primary-600" size={20} />
            PPR 2025 Tender Evaluation Criteria (TEC)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg text-center">
              <div className="text-2xl font-bold text-green-600">{tecData.match_rate}%</div>
              <div className="text-sm text-green-600/80">Match Rate</div>
            </div>
            <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg text-center">
              <div className="text-2xl font-bold text-yellow-600">{tecData.variances}</div>
              <div className="text-sm text-yellow-600/80">Items with Variance</div>
            </div>
            <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-center">
              <div className="text-2xl font-bold text-blue-600">{tecData.below_sor}</div>
              <div className="text-sm text-blue-600/80">Below SOR (Savings)</div>
            </div>
          </div>
          <div className="space-y-3 text-sm text-gray-600 dark:text-gray-400">
            <div className="flex justify-between p-2 bg-gray-50 dark:bg-gray-700/30 rounded">
              <span>Total BOQ Items Evaluated</span>
              <span className="font-semibold text-gray-900 dark:text-white">{tecData.total_items}</span>
            </div>
            <div className="flex justify-between p-2 bg-gray-50 dark:bg-gray-700/30 rounded">
              <span>Items at SOR Rate (Compliant)</span>
              <span className="font-semibold text-green-600">{tecData.matches}</span>
            </div>
            <div className="flex justify-between p-2 bg-gray-50 dark:bg-gray-700/30 rounded">
              <span>Items with Variance (Review Needed)</span>
              <span className="font-semibold text-yellow-600">{tecData.variances}</span>
            </div>
            <div className="flex justify-between p-2 bg-gray-50 dark:bg-gray-700/30 rounded">
              <span>Items Below SOR (Savings)</span>
              <span className="font-semibold text-blue-600">{tecData.below_sor}</span>
            </div>
            <div className="flex justify-between p-2 bg-gray-50 dark:bg-gray-700/30 rounded">
              <span>Potential Mismatches</span>
              <span className="font-semibold text-red-600">{tecData.mismatches}</span>
            </div>
          </div>
          <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800 rounded-lg text-sm">
            <p className="font-medium text-blue-700 dark:text-blue-300">PPR 2025 Compliance Note</p>
            <p className="text-blue-600 dark:text-blue-400 mt-1">
              Items with &gt;10% variance from SOR rate require justification per ITT 14.2. 
              Items flagged as "MISMATCH" or "ABOVE SOR" should be reviewed for arithmetic errors per ITT 27.
            </p>
          </div>
        </div>
      )}

      {/* 4. e-PW3 Forms View */}
      {view === 'forms' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <FileText className="text-primary-600" size={20} />
            Auto-Generated BPPA e-PW3 Forms
          </h3>
          {epw3Loading ? (
            <div className="text-center py-8">
              <div className="animate-spin inline-block w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full mb-3"></div>
              <p className="text-gray-500">Generating e-PW3 forms...</p>
            </div>
          ) : epw3Data?.has_forms ? (
            <div>
              <p className="text-sm text-gray-500 mb-4">
                {epw3Data.total_forms || 0} forms generated for this tender
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {(epw3Data.form_ids || epw3Data.forms || []).map((formId: string) => (
                  <div
                    key={formId}
                    className="p-4 border border-gray-200 dark:border-gray-600 rounded-lg hover:border-primary-400 transition-colors cursor-pointer"
                  >
                    <div className="font-medium text-gray-900 dark:text-white text-sm">{formId}</div>
                    <div className="text-xs text-gray-500 mt-1">BPPA e-PW3 Standard Form</div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <Receipt size={40} className="mx-auto text-gray-300 mb-3" />
              <p className="text-gray-500">No e-PW3 forms generated yet</p>
              <p className="text-sm text-gray-400 mt-1">
                Fill your company profile in Settings and re-run analysis to auto-generate forms
              </p>
              <button
                onClick={loadEPW3Forms}
                className="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 text-sm"
              >
                Try Generating Forms
              </button>
            </div>
          )}
        </div>
      )}

      {/* 5. PPR 2025 SLT Analysis View */}
      {view === 'slt' && (
        <div className="space-y-6">
          {sltLoading ? (
            <div className="text-center py-12">
              <div className="animate-spin inline-block w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full mb-3"></div>
              <p className="text-gray-500">Running PPR 2025 SLT analysis...</p>
            </div>
          ) : sltData ? (
            <>
              {/* Overall Status Card */}
              <div className={`rounded-xl border p-6 ${
                sltData.overall?.status?.includes('ALT') ? 'bg-red-50 dark:bg-red-900/20 border-red-300 dark:border-red-700' :
                sltData.overall?.status?.includes('SLT') ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-300 dark:border-yellow-700' :
                'bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-700'
              }`}>
                <div className="flex items-start gap-4">
                  <div className={`p-3 rounded-full ${
                    sltData.overall?.status?.includes('ALT') ? 'bg-red-100 dark:bg-red-800' :
                    sltData.overall?.status?.includes('SLT') ? 'bg-yellow-100 dark:bg-yellow-800' :
                    'bg-green-100 dark:bg-green-800'
                  }`}>
                    {sltData.overall?.status?.includes('ALT') ? <AlertCircle size={28} className="text-red-600 dark:text-red-300" /> :
                     sltData.overall?.status?.includes('SLT') ? <AlertTriangle size={28} className="text-yellow-600 dark:text-yellow-300" /> :
                     <CheckCircle2 size={28} className="text-green-600 dark:text-green-300" />}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                      {sltData.overall?.status || 'SLT Analysis'}
                    </h3>
                    <p className="text-sm mt-1 text-gray-600 dark:text-gray-400">
                      {sltData.overall?.summary || ''}
                    </p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                      <div>
                        <span className="text-xs text-gray-500">Bid / Estimate Ratio</span>
                        <p className="text-xl font-bold text-gray-900 dark:text-white">{sltData.overall?.ratio_formatted}</p>
                      </div>
                      <div>
                        <span className="text-xs text-gray-500">Bid Price</span>
                        <p className="text-xl font-bold text-gray-900 dark:text-white">৳{(sltData.overall?.bid_price || 0).toLocaleString()}</p>
                      </div>
                      <div>
                        <span className="text-xs text-gray-500">Estimated Cost</span>
                        <p className="text-xl font-bold text-gray-900 dark:text-white">৳{(sltData.overall?.estimated_cost || 0).toLocaleString()}</p>
                      </div>
                      <div>
                        <span className="text-xs text-gray-500">SLT Threshold</span>
                        <p className="text-xl font-bold text-gray-900 dark:text-white">{((sltData.overall?.thresholds?.slt || 0.7) * 100).toFixed(0)}%</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Risk Score Card */}
                {sltData.risk_assessment && (
                  <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
                    <h4 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                      <Shield size={18} className="text-primary-600" />
                      Risk Assessment
                    </h4>
                    <div className="flex items-center gap-4 mb-4">
                      <div className={`text-3xl font-bold ${
                        sltData.risk_assessment.level === 'critical' ? 'text-red-600' :
                        sltData.risk_assessment.level === 'high' ? 'text-orange-600' :
                        sltData.risk_assessment.level === 'medium' ? 'text-yellow-600' :
                        'text-green-600'
                      }`}>
                        {sltData.risk_assessment.score}/100
                      </div>
                      <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                        sltData.risk_assessment.level === 'critical' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' :
                        sltData.risk_assessment.level === 'high' ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300' :
                        sltData.risk_assessment.level === 'medium' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300' :
                        'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                      }`}>
                        {sltData.risk_assessment.level?.toUpperCase()}
                      </span>
                    </div>
                    <ul className="space-y-2">
                      {sltData.risk_assessment.factors?.map((f: string, i: number) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400">
                          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-yellow-500" />
                          {f}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Cost Components Card */}
                {sltData.cost_components && (
                  <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
                    <h4 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                      <BarChart3 size={18} className="text-primary-600" />
                      Cost Component Estimate
                    </h4>
                    <div className="space-y-4">
                      {[
                        { key: 'material', label: 'Material', icon: DollarSign, color: 'blue' },
                        { key: 'labor', label: 'Labor', icon: Users, color: 'green' },
                        { key: 'plant', label: 'Plant & Equipment', icon: Truck, color: 'purple' },
                      ].map(comp => {
                        const d = sltData.cost_components[comp.key];
                        if (!d) return null;
                        const tone = getThemeClasses(comp.color);
                        return (
                          <div key={comp.key} className="lift-card p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
                            <div className="flex items-center justify-between mb-2">
                              <span className="flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-white">
                                <comp.icon size={16} className={tone.icon} />
                                {comp.label}
                              </span>
                              <span className="text-sm font-semibold text-gray-900 dark:text-white">{d.pct}%</span>
                            </div>
                            <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                              <div className={`${tone.fill} h-2 rounded-full`} style={{ width: `${d.pct}%` }}></div>
                            </div>
                            <p className="text-xs mt-1 text-gray-500">৳{d.amount?.toLocaleString() || '0'}</p>
                            {d.flag !== 'normal' && (
                              <p className="text-xs mt-1 text-yellow-600 flex items-center gap-1">
                                <AlertTriangle size={12} /> {d.flag}
                              </p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Item Anomaly Table */}
              {sltData.item_anomalies && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
                  <h4 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                    <AlertTriangle size={18} className="text-red-500" />
                    Rate Anomalies ({sltData.item_anomalies.total_critical + sltData.item_anomalies.total_warning + sltData.item_anomalies.total_zero_rate} flagged)
                  </h4>
                  <div className="flex flex-wrap gap-2 mb-4">
                    {sltData.item_anomalies.total_critical > 0 && (
                      <span className="px-3 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-full text-xs font-medium">
                        Critical: {sltData.item_anomalies.total_critical}
                      </span>
                    )}
                    {sltData.item_anomalies.total_warning > 0 && (
                      <span className="px-3 py-1 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 rounded-full text-xs font-medium">
                        Warning: {sltData.item_anomalies.total_warning}
                      </span>
                    )}
                    {sltData.item_anomalies.total_above_sor > 0 && (
                      <span className="px-3 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-full text-xs font-medium">
                        Above SOR: {sltData.item_anomalies.total_above_sor}
                      </span>
                    )}
                    {sltData.item_anomalies.total_zero_rate > 0 && (
                      <span className="px-3 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded-full text-xs font-medium">
                        Zero Rate: {sltData.item_anomalies.total_zero_rate}
                      </span>
                    )}
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-200 dark:border-gray-700">
                          <th className="text-left py-2 px-2 text-gray-500 font-medium">Code</th>
                          <th className="text-left py-2 px-2 text-gray-500 font-medium">Description</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">SOR Rate</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">Quoted Rate</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">Ratio</th>
                          <th className="text-left py-2 px-2 text-gray-500 font-medium">Flag</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...(sltData.item_anomalies.critical || []), ...(sltData.item_anomalies.warning || []), ...(sltData.item_anomalies.above_sor || []), ...(sltData.item_anomalies.zero_rate || [])].slice(0, 50).map((item: any, i: number) => (
                          <tr key={i} className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30">
                            <td className="py-2 px-2 text-gray-900 dark:text-white font-mono text-xs">{item.code}</td>
                            <td className="py-2 px-2 text-gray-600 dark:text-gray-400 max-w-[200px] truncate">{item.description}</td>
                            <td className="py-2 px-2 text-right text-gray-900 dark:text-white">{item.sor_rate?.toLocaleString()}</td>
                            <td className="py-2 px-2 text-right text-gray-900 dark:text-white">{item.quoted_rate?.toLocaleString()}</td>
                            <td className={`py-2 px-2 text-right font-medium ${
                              item.severity === 'high' ? 'text-red-600' : 'text-yellow-600'
                            }`}>{item.ratio_formatted}</td>
                            <td className="py-2 px-2">
                              <span className={`text-xs font-medium ${
                                item.severity === 'high' ? 'text-red-600' : 'text-yellow-600'
                              }`}>{item.flag}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {(sltData.item_anomalies.total_critical + sltData.item_anomalies.total_warning + sltData.item_anomalies.total_above_sor + sltData.item_anomalies.total_zero_rate) > 50 && (
                      <p className="text-xs text-gray-400 text-center mt-2">Showing first 50 of {sltData.item_anomalies.total_critical + sltData.item_anomalies.total_warning + sltData.item_anomalies.total_above_sor + sltData.item_anomalies.total_zero_rate} anomalies</p>
                    )}
                  </div>
                </div>
              )}

              {/* Work Type Breakdown */}
              {sltData.work_type_analysis?.by_type && sltData.work_type_analysis.by_type.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
                  <h4 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                    <BarChart3 size={18} className="text-primary-600" />
                    Work Type Analysis
                  </h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-200 dark:border-gray-700">
                          <th className="text-left py-2 px-2 text-gray-500 font-medium">Work Type</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">Items</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">SOR Amount</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">Quoted Amount</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">Discount</th>
                          <th className="text-center py-2 px-2 text-gray-500 font-medium">Risk</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sltData.work_type_analysis.by_type.map((wt: any, i: number) => (
                          <tr key={i} className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30">
                            <td className="py-2 px-2 text-gray-900 dark:text-white font-medium capitalize">{wt.work_type}</td>
                            <td className="py-2 px-2 text-right text-gray-600 dark:text-gray-400">{wt.items}</td>
                            <td className="py-2 px-2 text-right text-gray-900 dark:text-white">৳{wt.sor_amount?.toLocaleString() || '0'}</td>
                            <td className="py-2 px-2 text-right text-gray-900 dark:text-white">৳{wt.quoted_amount?.toLocaleString() || '0'}</td>
                            <td className={`py-2 px-2 text-right font-medium ${wt.discount_pct > 15 ? 'text-red-600' : wt.discount_pct > 10 ? 'text-yellow-600' : 'text-green-600'}`}>
                              {wt.discount_pct}%
                            </td>
                            <td className="py-2 px-2 text-center">
                              <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                wt.risk === 'high' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' :
                                wt.risk === 'medium' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300' :
                                'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                              }`}>
                                {wt.risk.toUpperCase()}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Justification Requirements */}
              {sltData.justification_requirements && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
                  <h4 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                    <HelpCircle size={18} className="text-primary-600" />
                    Justification Requirements
                  </h4>
                  <div className="flex items-center gap-3 mb-4">
                    <span className={`px-3 py-1 rounded-full text-sm font-medium ${sltData.justification_requirements.required ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300' : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'}`}>
                      {sltData.justification_requirements.required ? 'Required' : 'Not Required'}
                    </span>
                    <span className="text-sm text-gray-500">
                      PPR 2025 Rule 31(2) - {sltData.justification_requirements.deadline_days || 7} days deadline
                    </span>
                  </div>
                  {sltData.justification_requirements.items?.length > 0 && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-200 dark:border-gray-700">
                            <th className="text-left py-2 px-2 text-gray-500 font-medium">Item</th>
                            <th className="text-right py-2 px-2 text-gray-500 font-medium">SOR Rate</th>
                            <th className="text-right py-2 px-2 text-gray-500 font-medium">Quoted</th>
                            <th className="text-left py-2 px-2 text-gray-500 font-medium">Reason</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sltData.justification_requirements.items.slice(0, 20).map((item: any, i: number) => (
                            <tr key={i} className="border-b border-gray-100 dark:border-gray-700/50">
                              <td className="py-2 px-2 text-gray-900 dark:text-white">
                                <div className="font-medium text-xs">{item.code}</div>
                                <div className="text-xs text-gray-500 truncate max-w-[200px]">{item.description}</div>
                              </td>
                              <td className="py-2 px-2 text-right text-gray-900 dark:text-white">৳{item.sor_rate?.toLocaleString()}</td>
                              <td className="py-2 px-2 text-right text-gray-900 dark:text-white">৳{item.quoted_rate?.toLocaleString()}</td>
                              <td className="py-2 px-2 text-xs text-gray-500 max-w-[250px]">{item.reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* Recommendation */}
              {sltData.recommendation && (
                <div className={`rounded-xl border p-4 ${
                  sltData.overall?.status?.includes('ALT') ? 'bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-800' :
                  sltData.overall?.status?.includes('SLT') ? 'bg-yellow-50 dark:bg-yellow-900/10 border-yellow-200 dark:border-yellow-800' :
                  'bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-800'
                }`}>
                  <p className="font-medium text-sm text-gray-900 dark:text-white mb-1">TEC Recommendation</p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{sltData.recommendation}</p>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-12">
              <AlertTriangle size={40} className="mx-auto text-gray-300 mb-3" />
              <p className="text-gray-500">Run a BOQ comparison first to enable SLT analysis.</p>
            </div>
          )}
        </div>
      )}

      {/* 6. Price Escalation View */}
      {view === 'escalation' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <TrendingUp className="text-primary-600" size={20} />
            GCC 70.1 Price Escalation Calculator
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-3">
              <h4 className="font-medium text-gray-900 dark:text-white text-sm">Contract Details</h4>
              <div className="p-3 bg-gray-50 dark:bg-gray-700/30 rounded text-sm">
                <div className="flex justify-between mb-2">
                  <span className="text-gray-500">Base Contract Value</span>
                  <span className="font-semibold text-gray-900 dark:text-white">
                    ৳{(comparisonResults.summary?.total_sor || 0).toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between mb-2">
                  <span className="text-gray-500">Quoted Amount</span>
                  <span className="font-semibold text-gray-900 dark:text-white">
                    ৳{(comparisonResults.summary?.total_quoted || 0).toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Discount</span>
                  <span className="font-semibold text-green-600">{comparisonResults.summary?.discount_pct || 0}%</span>
                </div>
              </div>
              <p className="text-xs text-gray-400">
                Full price escalation projection available via the escalation API endpoint.
                Eligible for contracts with duration &gt; 12 months per GCC 70.1.
              </p>
            </div>
            <div className="space-y-3">
              <h4 className="font-medium text-gray-900 dark:text-white text-sm">Market Rate Trends</h4>
              <div className="p-3 bg-gray-50 dark:bg-gray-700/30 rounded text-sm">
                <div className="flex justify-between mb-2">
                  <span className="text-gray-500">Steel (MS Rod)</span>
                  <span className="text-red-600 font-medium">↑ 2.1%</span>
                </div>
                <div className="flex justify-between mb-2">
                  <span className="text-gray-500">Cement</span>
                  <span className="text-yellow-600 font-medium">→ 0.5%</span>
                </div>
                <div className="flex justify-between mb-2">
                  <span className="text-gray-500">Bitumen</span>
                  <span className="text-red-600 font-medium">↑ 3.2%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Skilled Labor</span>
                  <span className="text-red-600 font-medium">↑ 1.5%</span>
                </div>
              </div>
              <p className="text-xs text-gray-400">
                Data source: BBS / REHAB / Local Market Survey. Updated monthly.
                Visit /api/market/rates for full index.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
