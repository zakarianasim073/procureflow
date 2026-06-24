import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Loader2, Building2, MapPin, Archive, FileText, Download, CheckCircle2 } from 'lucide-react';
import FileUploader from '../components/FileUploader';
import {
  uploadFile,
  compareBOQ,
  getSorAgencies,
  processTenderBundle,
  downloadTenderBundle,
} from '../api/client';
import { useAppStore } from '../store/appStore';
import type { SorAgency } from '../api/client';

export default function UploadCompare() {
  const navigate = useNavigate();
  const { setUploadedBOQ, setComparisonResults } = useAppStore();
  const [boqFile, setBoqFile] = useState<File | null>(null);
  const [zone, setZone] = useState('D');
  const [agency, setAgency] = useState('BWDB');
  const [agencies, setAgencies] = useState<SorAgency[]>([]);
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<'upload' | 'processing' | 'done'>('upload');
  const [statusMsg, setStatusMsg] = useState('');
  const [noticeFile, setNoticeFile] = useState<File | null>(null);
  const [tdsFile, setTdsFile] = useState<File | null>(null);
  const [tds2File, setTds2File] = useState<File | null>(null);
  const [sorFile, setSorFile] = useState<File | null>(null);
  const [bundleBoqFile, setBundleBoqFile] = useState<File | null>(null);
  const [docxTemplates, setDocxTemplates] = useState<File[]>([]);
  const [xlsxTemplates, setXlsxTemplates] = useState<File[]>([]);
  const [bundleLoading, setBundleLoading] = useState(false);
  const [bundleMsg, setBundleMsg] = useState('');
  const [bundleResult, setBundleResult] = useState<any>(null);
  const [bundleTenderId, setBundleTenderId] = useState('');

  useEffect(() => {
    getSorAgencies().then(r => setAgencies(r.agencies)).catch(() => {});
  }, []);

  const handleCompare = async () => {
    if (!boqFile) return;
    setLoading(true);
    setStep('processing');
    setStatusMsg('Uploading BOQ file...');
    try {
      const b = await uploadFile(boqFile, 'boq');
      setUploadedBOQ({ fileId: b.file_id, filename: b.filename, type: 'boq' });
      setStatusMsg('Running rate comparison against BWDB, PWD and LGED SOR...');
      const result = await compareBOQ(b.file_id, zone, 'ALL', {
        tender_id: bundleTenderId || `manual-${Date.now()}`,
        entity: 'BWDB / PWD / LGED',
      });
      setComparisonResults(result);
      setStep('done');
      setStatusMsg(`Analysis complete! ${result.total_items} items compared.`);
      setTimeout(() => navigate('/results'), 1500);
    } catch (e: any) {
      setStatusMsg(`Error: ${e.message || 'Analysis failed'}`);
      setStep('upload');
    } finally {
      setLoading(false);
    }
  };

  const handleBundleProcess = async () => {
    if (!noticeFile && !tdsFile && !tds2File && !bundleBoqFile && !sorFile && docxTemplates.length === 0 && xlsxTemplates.length === 0) {
      setBundleMsg('Select at least one tender file.');
      return;
    }
    setBundleLoading(true);
    setBundleMsg('Processing full tender bundle...');
    try {
      const result = await processTenderBundle({
        notice: noticeFile,
        tds: tdsFile,
        tds_2: tds2File,
        boq: bundleBoqFile,
        sor: sorFile,
        docxTemplates,
        xlsxTemplates,
        tenderId: bundleTenderId || undefined,
        sorAgency: agency,
        zone,
      });
      setBundleResult(result);
      setBundleMsg(`Bundle created for tender ${result.tender_id}.`);
    } catch (e: any) {
      setBundleMsg(`Error: ${e.message || 'Bundle processing failed'}`);
    } finally {
      setBundleLoading(false);
    }
  };

  const handleBundleDownload = async () => {
    if (!bundleResult?.tender_id) return;
    const blob = await downloadTenderBundle(bundleResult.tender_id);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${bundleResult.tender_id}_bundle.zip`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6 rounded-2xl bg-gradient-to-r from-slate-950 via-blue-950 to-slate-900 p-6 text-white shadow-xl">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-200">Enterprise Tender Automation</p>
        <h1 className="mt-2 text-3xl font-bold">BWDB / LGED / PWD Tender Processing Suite</h1>
        <p className="mt-2 max-w-3xl text-sm text-blue-100">
          Upload tender PDFs, SOR, BOQ and templates once; generate filled DOCX, BOQ workbook, work plan, validation reports and ZIP package.
        </p>
      </div>

      <div className="space-y-6">
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 text-sm text-blue-700 dark:text-blue-300">
          <Building2 size={16} className="inline mr-1" />
          <strong>SOR Rates loaded:</strong>{' '}
          {agencies.map(a => `${a.id} (${a.total_rates} rates)`).join(', ') || 'Loading...'}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            BOQ File (PDF from e-GP system)
          </label>
          <FileUploader
            label="Upload BOQ PDF"
            accept={{ 'application/pdf': ['.pdf'] }}
            onFileSelected={setBoqFile}
            selectedFile={boqFile}
            onClear={() => { setBoqFile(null); }}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              <MapPin size={14} className="inline mr-1" />Zone
            </label>
            <select value={zone} onChange={e => setZone(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm">
              <option value="A">Zone A — Dhaka, Mymensingh</option>
              <option value="B">Zone B — Chattogram, Sylhet</option>
              <option value="C">Zone C — Rajshahi, Rangpur</option>
              <option value="D">Zone D — Khulna, Barishal</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              <Building2 size={14} className="inline mr-1" />Compare SOR Sources
            </label>
            <div className="w-full px-3 py-2 rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300 text-sm">
              BWDB, PWD and LGED are compared together on every run.
            </div>
          </div>
        </div>

        {statusMsg && (
          <div className={`p-3 rounded-lg text-sm ${
            statusMsg.includes('Error')
              ? 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
              : statusMsg.includes('complete')
              ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400'
              : 'bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400'
          }`}>
            {step === 'processing' && <Loader2 size={16} className="inline mr-2 animate-spin" />}
            {statusMsg}
          </div>
        )}

        <button onClick={handleCompare} disabled={!boqFile || loading}
          className="w-full py-3 px-6 rounded-xl bg-primary-600 text-white font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2">
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Play size={18} />}
          {loading ? 'Processing...' : 'Run Rate Comparison'}
        </button>

        <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-900 space-y-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3">
              <span className="rounded-xl bg-primary-50 p-3 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300">
                <Archive size={22} />
              </span>
              <div>
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Full Tender Bundle</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">Single process button for upload → extract → match → fill → package.</p>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800"><strong className="block text-gray-900 dark:text-white">47/47</strong>BOQ rows</div>
              <div className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800"><strong className="block text-gray-900 dark:text-white">3</strong>SOR agencies</div>
              <div className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800"><strong className="block text-gray-900 dark:text-white">ZIP</strong>audit output</div>
            </div>
          </div>

          <label className="block">
            <span className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Tender ID (optional)</span>
            <input
              value={bundleTenderId}
              onChange={(e) => setBundleTenderId(e.target.value)}
              placeholder="1264860"
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
            />
          </label>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FileUploader label="Upload Notice PDF" accept={{ 'application/pdf': ['.pdf'] }} onFileSelected={setNoticeFile} selectedFile={noticeFile} onClear={() => setNoticeFile(null)} />
            <FileUploader label="Upload TDS PDF" accept={{ 'application/pdf': ['.pdf'] }} onFileSelected={setTdsFile} selectedFile={tdsFile} onClear={() => setTdsFile(null)} />
            <FileUploader label="Upload TDS-2 PDF" accept={{ 'application/pdf': ['.pdf'] }} onFileSelected={setTds2File} selectedFile={tds2File} onClear={() => setTds2File(null)} />
            <FileUploader label="Upload BOQ PDF" accept={{ 'application/pdf': ['.pdf'] }} onFileSelected={setBundleBoqFile} selectedFile={bundleBoqFile} onClear={() => setBundleBoqFile(null)} />
            <FileUploader label="Upload SOR PDF" accept={{ 'application/pdf': ['.pdf'] }} onFileSelected={setSorFile} selectedFile={sorFile} onClear={() => setSorFile(null)} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">DOCX Templates</span>
              <input
                type="file"
                multiple
                accept=".docx"
                onChange={(e) => setDocxTemplates(Array.from(e.target.files || []))}
                className="block w-full text-sm text-gray-600 dark:text-gray-300 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100 dark:file:bg-gray-800 dark:file:text-gray-200"
              />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">XLSX Templates</span>
              <input
                type="file"
                multiple
                accept=".xlsx,.xls"
                onChange={(e) => setXlsxTemplates(Array.from(e.target.files || []))}
                className="block w-full text-sm text-gray-600 dark:text-gray-300 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100 dark:file:bg-gray-800 dark:file:text-gray-200"
              />
            </label>
          </div>

          <button
            onClick={handleBundleProcess}
            disabled={bundleLoading}
            className="w-full py-3 px-6 rounded-xl bg-gradient-to-r from-slate-950 to-blue-800 text-white font-semibold shadow-lg hover:from-black hover:to-blue-900 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
          >
            {bundleLoading ? <Loader2 size={18} className="animate-spin" /> : <Archive size={18} />}
            {bundleLoading ? 'Building bundle...' : 'Process Full Bundle'}
          </button>

          {bundleMsg && (
            <div className="p-3 rounded-lg text-sm bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300">
              {bundleMsg}
            </div>
          )}

          {bundleResult?.tender_id && (
            <div className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-900/60 dark:bg-emerald-900/20">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="text-emerald-600" size={24} />
                  <div>
                    <p className="font-semibold text-gray-900 dark:text-white">Tender ID: {bundleResult.tender_id}</p>
                    <p className="text-sm text-gray-600 dark:text-gray-300">{bundleResult.artifacts?.length || 0} generated artifacts ready for audit.</p>
                  </div>
                </div>
                <button
                  onClick={handleBundleDownload}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700"
                >
                  <Download size={16} />
                  Download ZIP
                </button>
              </div>
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                {(bundleResult.artifacts || []).slice(0, 8).map((artifact: any) => (
                  <div key={`${artifact.kind}-${artifact.filename}`} className="flex items-center gap-2 rounded-lg bg-white/80 px-3 py-2 text-sm text-gray-700 dark:bg-gray-800 dark:text-gray-200">
                    <FileText size={15} className="text-primary-600" />
                    <span className="font-medium uppercase text-xs text-gray-500">{artifact.kind}</span>
                    <span className="truncate">{artifact.filename}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
