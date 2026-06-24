import axios from 'axios';

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Retry interceptor for idempotent requests
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config || {};
    if (!config.retryCount) config.retryCount = 0;
    const isIdempotent = ['get', 'head', 'options'].includes(config.method || '');
    if (isIdempotent && config.retryCount < MAX_RETRIES) {
      config.retryCount += 1;
      await sleep(RETRY_DELAY_MS * config.retryCount);
      return api(config);
    }
    return Promise.reject(error);
  },
);

// Reactive token + CSRF sync
let cachedToken: string | null = null;
let cachedCsrf: string | null = null;

const syncTokenCache = () => {
  try {
    const stored = localStorage.getItem('procureflow-store');
    if (stored) {
      const parsed = JSON.parse(stored);
      cachedToken = parsed?.state?.auth?.token || null;
      cachedCsrf = parsed?.state?.auth?.csrfToken || null;
    }
  } catch {
    cachedToken = null;
    cachedCsrf = null;
  }
};

window.addEventListener('storage', (e) => {
  if (e.key === 'procureflow-store') syncTokenCache();
});

syncTokenCache();

api.interceptors.request.use((config) => {
  if (cachedToken) config.headers.Authorization = `Bearer ${cachedToken}`;
  if (cachedCsrf && config.method && !['get', 'head', 'options'].includes(config.method)) {
    config.headers['X-CSRF-Token'] = cachedCsrf;
  }
  return config;
});

// ── Types ─────────────────────────────────────────────────────────────────

export interface ComparisonItem {
  item_no: string;
  code: string;
  agency: string;
  work_type: string;
  desc: string;
  unit: string;
  qty: number;
  rate: number | null;
  sor_rate: number | null;
  diff: number | null;
  pct_diff: number | null;
  flag: string;
}

export interface SummaryRow {
  work_type: string;
  items: number;
  sor_amount: number;
  quoted_amount: number;
  saving: number;
  discount_pct: number;
  pct_of_total: number;
}

export interface ComparisonResult {
  success: boolean;
  data: ComparisonItem[];
  summary: { by_work_type: SummaryRow[] };
  flagged: ComparisonItem[];
  total_items: number;
  mismatches: number;
  variances: number;
  matches: number;
  excel_path?: string;
  docx_path?: string;
  filename?: string;
}

export interface ChatResponse {
  success: boolean;
  content: string;
  tokens_used: number;
  engine: string;
}

export interface SorAgency {
  id: string;
  name: string;
  total_rates: number;
}

export interface ClientRecord {
  id: string;
  name: string;
  slug: string;
  plan: string;
  is_active?: boolean;
  config?: Record<string, any>;
  subscription?: {
    status: string;
    tender_quota_used: number;
    tender_quota_limit: number;
    quota_remaining: number;
    billing_end: string;
  } | null;
  organization?: {
    name: string;
    email: string;
    phone: string;
  } | null;
  created_at?: string;
}

export interface ClientUsageLog {
  id: string;
  tender_id: string;
  action: string;
  quota_consumed: number;
  created_at: string;
}

export interface ClientUsageHistory {
  tenant_id: string;
  tenant_name?: string;
  days: number;
  logs: ClientUsageLog[];
  summary: {
    total_events: number;
    total_quota_consumed: number;
    by_action: Record<string, { count: number; quota_consumed: number }>;
    daily?: Array<{ date: string; quota_consumed: number }>;
  };
  error?: string;
}

export interface TenderBundleResult {
  success: boolean;
  tender_id: string;
  bundle_zip?: string;
  artifacts: any[];
  uploaded: Record<string, string>;
  manifest: any;
}

// ── Auth ──────────────────────────────────────────────────────────────────

export const login = async (email: string, password: string) => {
  const { data } = await api.post('/auth/login', { email, password });
  return data as { access_token: string; token_type: string; user: any };
};

export const register = async (email: string, password: string) => {
  const { data } = await api.post('/auth/register', { email, password });
  return data as { access_token: string; token_type: string; user: any };
};

export const getMe = async () => {
  const { data } = await api.get('/auth/me');
  return data as any;
};

// ── Upload ────────────────────────────────────────────────────────────────

export const uploadFile = async (file: File, fileType: string) => {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('file_type', fileType);
  const { data } = await api.post('/boq/upload', fd);
  return data as { success: boolean; file_id: string; filename: string; file_type: string };
};

// ── BOQ Comparison ────────────────────────────────────────────────────────

export const compareBOQ = async (
  boqFileId: string,
  zone?: string,
  agency?: string,
  tenderInfo?: any
) => {
  const fd = new FormData();
  fd.append('boq_file_id', boqFileId);
  fd.append('sor_agency', agency || 'ALL');
  fd.append('zone', zone || '');
  if (tenderInfo) fd.append('tender_info', JSON.stringify(tenderInfo));
  const { data } = await api.post('/boq/compare', fd);
  return data as ComparisonResult;
};

export const getLatestComparison = async () => {
  const { data } = await api.get('/boq/latest');
  return data as ComparisonResult & { created_at?: string; boq_file_id?: string };
};

// ── SOR ───────────────────────────────────────────────────────────────────

export const getSorAgencies = async () => {
  const { data } = await api.get('/sor/agencies');
  return data as { agencies: SorAgency[] };
};

// ── Clients ──────────────────────────────────────────────────────────────

export const getClients = async () => {
  const { data } = await api.get('/clients');
  return data as { clients: ClientRecord[] };
};

export const getClient = async (tenantId: string) => {
  const { data } = await api.get(`/clients/${tenantId}`);
  return data as ClientRecord;
};

export const updateClientProfile = async (tenantId: string, profile: Record<string, any>) => {
  const { data } = await api.post(`/clients/${tenantId}/profile`, profile);
  return data as { status?: string; tenant_id?: string; error?: string } | Record<string, any>;
};

export const getClientQuota = async (tenantId: string) => {
  const { data } = await api.get(`/clients/${tenantId}/quota`);
  return data as Record<string, any>;
};

export const getClientUsage = async (tenantId: string, days = 30) => {
  const { data } = await api.get(`/clients/${tenantId}/usage`, { params: { days } });
  return data as ClientUsageHistory;
};

export const runClientPipeline = async (tenantId: string, context: Record<string, any> = {}) => {
  const { data } = await api.post(`/clients/${tenantId}/pipeline`, context);
  return data as Record<string, any>;
};

export const lookupSorRate = async (code: string, agency = 'BWDB', zone?: string) => {
  const { data } = await api.get('/sor/lookup', { params: { code, agency, zone } });
  return data as any;
};

// ── Chat ──────────────────────────────────────────────────────────────────

export const sendChat = async (
  messages: { role: string; content: string }[],
  language = 'en',
  engine = 'auto'
) => {
  const { data } = await api.post('/chat', { messages, language, engine });
  return data as ChatResponse;
};

// ── Dashboard ─────────────────────────────────────────────────────────────

export const getStats = async () => {
  const { data } = await api.get('/dashboard/stats');
  return data as { success: boolean; stats: any };
};

export const getAnalytics = async () => {
  const { data } = await api.get('/dashboard/analytics');
  return data as { success: boolean; analytics: any };
};

// ── Tender Bundle ─────────────────────────────────────────────────────────

export const processTenderBundle = async (payload: {
  notice?: File | null;
  tds?: File | null;
  tds_2?: File | null;
  boq?: File | null;
  sor?: File | null;
  docxTemplates?: File[];
  xlsxTemplates?: File[];
  tenderId?: string;
  sorAgency?: string;
  zone?: string;
}) => {
  const fd = new FormData();
  if (payload.notice) fd.append('notice', payload.notice);
  if (payload.tds) fd.append('tds', payload.tds);
  if (payload.tds_2) fd.append('tds_2', payload.tds_2);
  if (payload.boq) fd.append('boq', payload.boq);
  if (payload.sor) fd.append('sor', payload.sor);
  for (const file of payload.docxTemplates || []) fd.append('docx_templates', file);
  for (const file of payload.xlsxTemplates || []) fd.append('xlsx_templates', file);

  const { data } = await api.post('/tender/upload', fd, {
    params: {
      tender_id: payload.tenderId || '',
      sor_agency: payload.sorAgency || 'BWDB',
      zone: payload.zone || '',
    },
  });
  return data as TenderBundleResult;
};

export const downloadTenderBundle = async (tenderId: string) => {
  const response = await api.get(`/tender/${tenderId}/bundle`, {
    responseType: 'blob',
  });
  return response.data as Blob;
};

// ── Agent System ──────────────────────────────────────────────────────────

export const listAgents = async () => {
  const { data } = await api.get('/agents');
  return data as { total: number; agents: any[] };
};

export const getRecentAgentResults = async (limit = 12) => {
  const { data } = await api.get('/agent-results/recent', { params: { limit } });
  return data as {
    total: number;
    results: Array<{
      run_id: string;
      source: 'single' | 'pipeline' | 'prompt' | 'tender_process' | 'database';
      timestamp: string;
      tender_id?: string;
      agent_id: string;
      agent_name: string;
      status: string;
      output?: any;
      error?: string;
      execution_time_ms?: number;
    }>;
  };
};

export const getWatchdogHealth = async () => {
  const { data } = await api.get('/watchdog/health');
  return data as any;
};

export const getWatchdogDashboard = async () => {
  const { data } = await api.get('/watchdog/dashboard');
  return data as any;
};

export const getWatchdogErrors = async (limit = 20) => {
  const { data } = await api.get('/watchdog/errors', { params: { limit } });
  return data as any;
};

export const getWatchdogSessions = async (limit = 10) => {
  const { data } = await api.get('/watchdog/sessions', { params: { limit } });
  return data as any;
};

export const analyzeWatchdogError = async (payload: {
  source: string;
  error_message: string;
  error_type?: string;
}) => {
  const { data } = await api.post('/watchdog/analyze', payload);
  return data as any;
};

export const getEngineerStatus = async () => {
  const { data } = await api.get('/engineer/status');
  return data as any;
};

export const diagnoseEngineerError = async (payload: {
  source: string;
  error_message: string;
  error_type?: string;
  context?: any;
}) => {
  const { data } = await api.post('/engineer/diagnose', payload);
  return data as any;
};

export const getEngineerComponents = async (componentType?: string) => {
  const { data } = await api.get(componentType ? `/engineer/components/${componentType}` : '/engineer/components');
  return data as any;
};

export const getEngineerFixes = async (fixType?: string) => {
  const { data } = await api.get(fixType ? `/engineer/fixes/${fixType}` : '/engineer/fixes');
  return data as any;
};

export const getBrainStatus = async () => {
  const { data } = await api.get('/brain/status');
  return data as any;
};

export const sendBrainMessage = async (payload: {
  sender?: string;
  recipient: string;
  subject: string;
  body: any;
}) => {
  const { data } = await api.post('/brain/message', payload);
  return data as any;
};

export const getThoughtStats = async () => {
  const { data } = await api.get('/thoughts/stats');
  return data as any;
};

export const getPendingThoughts = async (agentId?: string) => {
  const { data } = await api.get('/thoughts/pending', { params: agentId ? { agent_id: agentId } : {} });
  return data as any;
};

export const getThoughtHistory = async (status = 'approved', limit = 10) => {
  const { data } = await api.get('/thoughts/history', { params: { status, limit } });
  return data as any;
};

export const proposeThought = async (payload: {
  agent_id: string;
  agent_name: string;
  thought_type: string;
  title: string;
  description: string;
  evidence?: any;
  tender_id?: string;
  impact?: string;
  confidence?: number;
  key_data?: any;
}) => {
  const { data } = await api.post('/thoughts/propose', payload);
  return data as any;
};

export const approveThought = async (thoughtId: string, comment = '') => {
  const { data } = await api.post(`/thoughts/${thoughtId}/approve`, null, {
    params: { comment },
  });
  return data as any;
};

export const rejectThought = async (thoughtId: string, comment = '') => {
  const { data } = await api.post(`/thoughts/${thoughtId}/reject`, null, {
    params: { comment },
  });
  return data as any;
};

export const logUiEvent = async (payload: {
  feature: string;
  action: string;
  data: any;
}) => {
  const { data } = await api.post('/ui-log', payload);
  return data as any;
};

export const runAgent = async (agentId: string, context: any = {}) => {
  const { data } = await api.post(`/agents/${agentId}/run`, context);
  return data as any;
};

export const runMultipartAgent = async (agentId: string, formData: FormData) => {
  const { data } = await api.post(`/agents/${agentId}/run`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data as any;
};

export const runPipeline = async (mode = 'full', phase?: string, context: any = {}) => {
  const { data } = await api.post('/pipeline/run', { mode, phase, context });
  return data as any;
};

export const listPipelinePhases = async () => {
  const { data } = await api.get('/pipeline/phases');
  return data as any;
};

// ── Ollama Agent Runner ──────────────────────────────────────────────────

export const ollamaRunAgent = async (prompt: string, language = 'en') => {
  const { data } = await api.post('/agents/ollama-run', { prompt, language });
  return data as any;
};

// ── Tender Process with Agents (Pipeline → Document Gen bridge) ──────────

export const processTenderWithAgents = async (tenderId: string, sorAgency = 'BWDB', zone?: string) => {
  const { data } = await api.post(`/tender/${tenderId}/process-with-agents?${new URLSearchParams({ sor_agency: sorAgency, ...(zone ? { zone } : {}) })}`);
  return data as any;
};

// ── WhatsApp Share (used by Settings.tsx) ──────────────────────────────

export const getWhatsappSettings = async () => {
  const { data } = await api.get('/whatsapp/settings');
  return data as any;
};

export const updateWhatsappSettings = async (phone: string) => {
  const { data } = await api.post('/whatsapp/settings', { phone });
  return data as any;
};

// ── PPR 2025 SLT Analysis ────────────────────────────────────────────

export const runSLTAnalysis = async (
  boqItems: any[],
  estimatedCost: number,
  bidPrice: number
) => {
  const { data } = await api.post('/ppr/slt-analysis', {
    boq_items: boqItems,
    estimated_cost: estimatedCost,
    bid_price: bidPrice,
  });
  return data as { success: boolean; analysis: any };
};

// ── SMTP / Email Settings ──────────────────────────────────────────────

export const getSmtpSettings = async () => {
  const { data } = await api.get('/settings/smtp');
  return data as any;
};

export const updateSmtpSettings = async (settings: {
  smtp_host?: string;
  smtp_port?: number;
  smtp_user?: string;
  smtp_pass?: string;
  smtp_from?: string;
  alert_email?: string;
}) => {
  const { data } = await api.post('/settings/smtp', settings);
  return data as { success: boolean; message: string };
};

export const testSmtpSettings = async (email: string) => {
  const { data } = await api.post('/settings/smtp/test', { email });
  return data as { success: boolean; message: string };
};

// ── Export / Download ─────────────────────────────────────────────────────

export const downloadExcel = async (fileId: string) => {
  const response = await api.get(`/boq/export/${fileId}`, {
    params: { format: 'xlsx' },
    responseType: 'blob',
  });
  return response.data as Blob;
};

export const downloadDocx = async (fileId: string) => {
  const response = await api.get(`/boq/export/${fileId}`, {
    params: { format: 'docx' },
    responseType: 'blob',
  });
  return response.data as Blob;
};

// ── PPR 2025 Dashboard ────────────────────────────────────────────────────

export const getPprOverview = async () => {
  const { data } = await api.get('/ppr2025/overview');
  return data as { success: boolean; data: any };
};

export const getPprNppTrends = async (months = 24, agency?: string) => {
  const { data } = await api.get('/ppr2025/npp-trends', { params: { months, agency } });
  return data as { success: boolean; data: { trends: any[] } };
};

export const getPprPredictions = async () => {
  const { data } = await api.get('/ppr2025/predictions');
  return data as { success: boolean; data: { predictions: any[] } };
};

export const getPprContractors = async (limit = 15) => {
  const { data } = await api.get('/ppr2025/contractors', { params: { limit } });
  return data as { success: boolean; data: { contractors: any[]; total: number } };
};

export const getPprRates = async () => {
  const { data } = await api.get('/ppr2025/rates');
  return data as { success: boolean; data: any };
};

export const getPprModelStatus = async () => {
  const { data } = await api.get('/ppr2025/model/status');
  return data as { success: boolean; data: any };
};

export const getPprModelExplain = async (payload: Record<string, any>) => {
  const { data } = await api.post('/ppr2025/model/explain', payload);
  return data as {
    success: boolean;
    data: {
      prediction: any;
      explanation: any;
      evidence: any;
      model_version?: string;
    };
  };
};

export const getPprAwardStats = async () => {
  const { data } = await api.get('/ppr2025/award-stats');
  return data as { success: boolean; data: any };
};

export const getPprEvaluations = async (limit = 50) => {
  const { data } = await api.get('/ppr2025/evaluations', { params: { limit } });
  return data as { evaluations: any[] };
};

export const getPprDocumentChecklist = async (tenderType: string) => {
  const { data } = await api.get('/ppr2025/document-checklist', { params: { tender_type: tenderType } });
  return data as { success: boolean; data: any };
};

export const evaluatePprTec = async (payload: any) => {
  const { data } = await api.post('/ppr2025/evaluate/tec', payload);
  return data as { evaluation: any };
};

export const evaluatePprFinancial = async (payload: any) => {
  const { data } = await api.post('/ppr2025/evaluate/ppr', payload);
  return data as { evaluation: any };
};

export const evaluatePprWorks = async (payload: any) => {
  const { data } = await api.post('/ppr2025/evaluate/works', payload);
  return data as { evaluation: any };
};

// ── Analytics Suite ────────────────────────────────────────────────────────

export const getAnalyticsOverview = async () => {
  const { data } = await api.get('/analytics/overview');
  return data as { success: boolean; data: any };
};

export const getAnalyticsNppTrends = async (months = 12) => {
  const { data } = await api.get('/analytics/npp-trends', { params: { months } });
  return data as { success: boolean; data: { trends: any[] } };
};

export const getAnalyticsAwardTrends = async (months = 12) => {
  const { data } = await api.get('/analytics/award-trends', { params: { months } });
  return data as { success: boolean; data: { award_trends: any[] } };
};

export const getAnalyticsAgencyComparison = async () => {
  const { data } = await api.get('/analytics/agency-comparison');
  return data as { success: boolean; data: { agencies: any[] } };
};

export const getAnalyticsContractorLeaderboard = async (limit = 10) => {
  const { data } = await api.get('/analytics/contractor-leaderboard', { params: { limit } });
  return data as { success: boolean; data: { leaderboard: any[] } };
};

export const getAnalyticsWinRate = async () => {
  const { data } = await api.get('/analytics/win-rate');
  return data as { success: boolean; data: { agencies: any[] } };
};

export const getAnalyticsDiscountDistribution = async () => {
  const { data } = await api.get('/analytics/discount-distribution');
  return data as { success: boolean; data: { distribution: any[] } };
};

export const getAnalyticsMonthlyTrends = async (months = 12) => {
  const { data } = await api.get('/analytics/monthly-trends', { params: { months } });
  return data as { success: boolean; data: { monthly_trends: any[] } };
};

export const getAnalyticsBoqAnalytics = async () => {
  const { data } = await api.get('/analytics/boq-analytics');
  return data as { success: boolean; data: any };
};

// ── Department Tree ───────────────────────────────────────────────────────

export const getDeptTreeTargets = async () => {
  const { data } = await api.get('/deptree/targets');
  return data as Record<string, { id: string; name: string }>;
};

export const getDeptTreeMinistries = async () => {
  const { data } = await api.get('/deptree/ministries');
  return data as Array<{ id: string; name: string; type: string; office_count: number; total_packages: number }>;
};

export const getMinistryDetail = async (id: string) => {
  const { data } = await api.get(`/deptree/ministry/${id}`);
  return data as any;
};

export const getOffices = async (orgId: string) => {
  const { data } = await api.get(`/deptree/offices/${orgId}`);
  return data as any;
};

export const searchDeptTree = async (query: string) => {
  const { data } = await api.get('/deptree/search', { params: { query } });
  return data as any;
};

export const searchLiveTenders = async (params: {
  department_id?: string;
  office_id?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
}) => {
  const { data } = await api.get('/deptree/live-tenders', { params });
  return data as {
    tenders: Array<{
      tender_id: string;
      app_tender_id?: string;
      live_tender_id?: string;
      title: string;
      app_work_name?: string;
      live_work_name?: string;
      procuring_entity: string;
      published_date: string;
      deadline: string;
      estimated_value_bdt: number;
      app_estimated_value_bdt?: number;
      live_estimated_value_bdt?: number;
      estimated_value_source?: string;
      notice_data?: {
        app_tender_id?: string;
        live_tender_id?: string;
        package_no?: string;
        work_name?: string;
        app_work_name?: string;
        live_work_name?: string;
        estimated_amount_bdt?: number;
        estimated_cost_bdt?: number;
        app_estimated_value_bdt?: number;
        app_estimated_value_display?: string;
        app_estimated_value_unit?: string;
        live_estimated_value_bdt?: number;
        live_value_bdt?: number;
      };
      category: string;
      location: string;
      status: string;
    }>;
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  };
};

// ── Predictions ───────────────────────────────────────────────────────────

export const getNppStats = async () => {
  const { data } = await api.get('/predict/npp/stats');
  return data as any;
};

export const getBidPredictionStats = async () => {
  const { data } = await api.get('/predict/bid/stats');
  return data as any;
};

export const getCrossCheckAccuracy = async () => {
  const { data } = await api.get('/predict/bid/cross-check/auto');
  return data as {
    total_checked: number;
    winner_accuracy_pct: number;
    correct_winners: number;
    total_predictions: number;
    details: Array<{
      contractor: string;
      predicted_winner: boolean;
      actual_wins: number;
      winner_correct: boolean;
    }>;
  };
};

export const predictBid = async (payload: {
  tender_id: string;
  agency: string;
  estimate: number;
  work_type?: string;
  interested_contractors?: string[];
}) => {
  const { data } = await api.post('/predict/bid/predict', payload);
  return data as any;
};

// ── Executive Dashboard ───────────────────────────────────────────────────

export const getExecutiveOverview = async () => {
  const { data } = await api.get('/executive/overview');
  return data as any;
};

export const getExecutiveReport = async () => {
  const { data } = await api.get('/executive/report');
  return data as any;
};

export const getIntelImportStatus = async () => {
  const { data } = await api.get('/intel/import/status');
  return data as any;
};

export const getIntelAgentFeed = async (agency?: string, limit = 25) => {
  const { data } = await api.get('/intel/agent-feed', { params: { agency, limit } });
  return data as any;
};

// ── eExperience / eCMS (Execution) ────────────────────────────────────

export const getEexperienceList = async (params?: {
  agency?: string; contractor?: string; source?: string; work_status?: string;
  date_from?: string; date_to?: string; min_value?: number; max_value?: number;
  limit?: number; offset?: number;
}) => {
  const { data } = await api.get('/intel/eexperience', { params });
  return data as any;
};

export const getEexperienceCompleted = async (params?: Record<string, any>) => {
  const { data } = await api.get('/intel/eexperience/completed', { params });
  return data as any;
};

export const getEexperienceOngoing = async (params?: Record<string, any>) => {
  const { data } = await api.get('/intel/eexperience/ongoing', { params });
  return data as any;
};

export const getEexperienceStats = async (source?: string) => {
  const { data } = await api.get('/intel/eexperience/stats', { params: { source } });
  return data as any;
};

export const getEexperienceCompletedStats = async () => {
  const { data } = await api.get('/intel/eexperience/completed/stats');
  return data as any;
};

export const getEexperienceOngoingStats = async () => {
  const { data } = await api.get('/intel/eexperience/ongoing/stats');
  return data as any;
};

export const getEexperienceIntelligence = async (agency?: string, source?: string, limit = 8) => {
  const { data } = await api.get('/intel/eexperience/intelligence', { params: { agency, source, limit } });
  return data as any;
};

export const getEexperienceAgencies = async (source?: string) => {
  const { data } = await api.get('/intel/eexperience/agencies', { params: { source } });
  return data as any;
};

export const getEexperienceContractor = async (name: string, source?: string) => {
  const { data } = await api.get(`/intel/eexperience/contractor/${encodeURIComponent(name)}`, { params: { source } });
  return data as any;
};

export const getEexperienceTimeline = async (source?: string, granularity = 'month', year?: number) => {
  const { data } = await api.get('/intel/eexperience/timeline', { params: { source, granularity, year } });
  return data as any;
};

export const getEexperienceAgencyComparison = async (source?: string) => {
  const { data } = await api.get('/intel/eexperience/agency-comparison', { params: { source } });
  return data as any;
};

// ── Execution Analytics ────────────────────────────────────────────────

export const getExecutionOverview = async (source?: string) => {
  const { data } = await api.get('/analytics/execution/overview', { params: { source } });
  return data as any;
};

export const getExecutionTimeline = async (source?: string, granularity = 'month', year?: number) => {
  const { data } = await api.get('/analytics/execution/timeline', { params: { source, granularity, year } });
  return data as any;
};

export const getExecutionAgencies = async (source?: string) => {
  const { data } = await api.get('/analytics/execution/agencies', { params: { source } });
  return data as any;
};

export const getExecutionContractor = async (name: string, source?: string) => {
  const { data } = await api.get(`/analytics/execution/contractor/${encodeURIComponent(name)}`, { params: { source } });
  return data as any;
};

export const getCrawlStatus = async () => {
  const { data } = await api.get('/intel/crawl/status');
  return data as any;
};

export default api;
