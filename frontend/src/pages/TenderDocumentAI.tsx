import { useState, useRef } from 'react';
import { Upload, FileText, Calendar, DollarSign, CheckSquare, AlertTriangle, List, BookOpen } from 'lucide-react';
import { runMultipartAgent } from '../api/client';
import WhatsAppShare from '../components/WhatsAppShare';

interface TenderDoc {
  tender_id: string;
  pdf_filename: string;
  deadlines: Record<string, string | null>;
  earnest_money: { amount_bdt: number; raw: string } | null;
  security_money: { value: number; type: string; raw: string } | null;
  eligibility_criteria: string[];
  document_checklist: string[];
  boq_summary: { total_items: number; items: Array<{ item_no: string; description: string; amount: string }> };
  key_terms: Array<{ label: string; value: string }>;
}

export default function TenderDocumentAI() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TenderDoc | null>(null);
  const [error, setError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError('');
    setResult(null);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('agent_id', 'agent-033-tender-document');
    try {
      const data = await runMultipartAgent('agent-033-tender-document', formData);
      setResult(data.output);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Extraction failed');
    } finally {
      setLoading(false);
    }
  };

  const formatBDT = (n: number) => `BDT ${n.toLocaleString('en-IN')}`;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <FileText className="text-primary-600" size={28} />
          Tender Document AI
        </h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Upload NTP, TDS, or tender PDF and extract deadlines, EMD, eligibility criteria, and checklist items
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Upload Document</h2>
            <div
              onClick={() => fileRef.current?.click()}
              className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl p-8 text-center cursor-pointer hover:border-primary-400 transition-colors"
            >
              <Upload size={36} className="mx-auto text-gray-400 mb-3" />
              <p className="text-sm text-gray-500 dark:text-gray-400">{file ? file.name : 'Click to select PDF'}</p>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="hidden"
              />
            </div>
            <button
              onClick={handleUpload}
              disabled={!file || loading}
              className="w-full mt-4 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-400 text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
            >
              {loading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <><FileText size={16} /> Extract & Analyze</>}
            </button>
            {error && <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded-lg text-sm">{error}</div>}
          </div>
        </div>

        <div className="lg:col-span-2 space-y-4">
          {result ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-1.5 mb-3"><Calendar size={14} className="text-primary-600" /> Key Deadlines</h3>
                  <div className="space-y-2 text-sm">
                    {Object.entries(result.deadlines || {}).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span className="text-gray-500 capitalize">{k.replace(/_/g, ' ')}</span>
                        <span className="text-gray-900 dark:text-white font-medium">{v || '—'}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-1.5 mb-3"><DollarSign size={14} className="text-green-600" /> Financial Details</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-500">Earnest Money</span>
                      <span className="font-medium text-green-600">{result.earnest_money ? formatBDT(result.earnest_money.amount_bdt) : '—'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Performance Security</span>
                      <span className="font-medium text-gray-900 dark:text-white">{result.security_money ? `${result.security_money.value}${result.security_money.type === 'percentage' ? '%' : ' BDT'}` : '—'}</span>
                    </div>
                  </div>
                </div>
              </div>

              {result.eligibility_criteria?.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-1.5 mb-3"><CheckSquare size={14} className="text-blue-600" /> Eligibility Criteria</h3>
                  <ul className="space-y-1">
                    {result.eligibility_criteria.map((c, i) => <li key={i} className="text-sm text-gray-600 dark:text-gray-400 flex items-start gap-2"><span className="text-blue-500 mt-0.5">•</span> {c}</li>)}
                  </ul>
                </div>
              )}

              {result.document_checklist?.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-1.5 mb-3"><List size={14} className="text-purple-600" /> Document Checklist</h3>
                  <ul className="space-y-1">
                    {result.document_checklist.map((d, i) => <li key={i} className="text-sm text-gray-600 dark:text-gray-400 flex items-start gap-2"><span className="text-purple-500 mt-0.5">•</span> {d}</li>)}
                  </ul>
                </div>
              )}

              {result.key_terms?.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-1.5 mb-3"><BookOpen size={14} className="text-orange-600" /> Key Contract Terms</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {result.key_terms.map((t, i) => (
                      <div key={i} className="p-2 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
                        <div className="text-xs text-gray-500">{t.label}</div>
                        <div className="text-sm font-medium text-gray-900 dark:text-white">{t.value}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {result.boq_summary?.items?.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-1.5 mb-3"><AlertTriangle size={14} className="text-red-600" /> BOQ Summary ({result.boq_summary.total_items} items)</h3>
                  <div className="overflow-x-auto max-h-48 overflow-y-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs text-gray-500 uppercase border-b dark:border-gray-700">
                          <th className="pb-2 pr-2">#</th>
                          <th className="pb-2 pr-2">Description</th>
                          <th className="pb-2 text-right">Amount</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                        {result.boq_summary.items.map((item, i) => (
                          <tr key={i}>
                            <td className="py-1.5 pr-2 text-gray-500">{item.item_no}</td>
                            <td className="py-1.5 pr-2 text-gray-700 dark:text-gray-300">{item.description}</td>
                            <td className="py-1.5 text-right font-mono text-gray-900 dark:text-white">{item.amount}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div className="flex items-center justify-between bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                <span className="text-sm text-gray-500">{result.pdf_filename}</span>
                <WhatsAppShare title="Tender Document Analysis" message={`Tender: ${result.tender_id || result.pdf_filename}`} />
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-96 text-gray-400 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
              <FileText size={64} className="mb-4 opacity-30" />
              <p className="text-sm">Upload a tender PDF to extract key information</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
