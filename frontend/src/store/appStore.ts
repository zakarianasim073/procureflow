import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import api from '../api/client';

interface UploadedFile {
  fileId: string;
  filename: string;
  type: string;
}

export interface AgentExecutionRecord {
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
}

interface AuthState {
  token: string | null;
  user: { id: string; email: string; plan: string; name: string } | null;
}

interface AppState {
  // Theme
  theme: 'light' | 'dark';
  
  // Auth
  auth: AuthState;
  
  // Uploads
  uploadedBOQ: UploadedFile | null;
  uploadedSOR: UploadedFile | null;
  comparisonResults: any | null;
  recentAgentResults: AgentExecutionRecord[];
  pipelineResults: Record<string, any[]> | null;
  
  // API Keys
  openaiKey: string;
  anthropicKey: string;
  ollamaUrl: string;
  ollamaModel: string;

  // SMTP / Email
  smtpHost: string;
  smtpPort: number;
  smtpUser: string;
  smtpPass: string;
  smtpFrom: string;
  alertEmail: string;
  
  // Actions
  setTheme: (t: 'light' | 'dark') => void;
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => void;
  setToken: (token: string) => void;
  setUploadedBOQ: (f: UploadedFile | null) => void;
  setUploadedSOR: (f: UploadedFile | null) => void;
  setComparisonResults: (r: any) => void;
  addAgentExecutionRecord: (record: AgentExecutionRecord) => void;
  setAgentExecutionRecords: (records: AgentExecutionRecord[]) => void;
  clearAgentExecutionRecords: () => void;
  setPipelineResults: (results: Record<string, any[]> | null) => void;
  setOpenaiKey: (k: string) => void;
  setAnthropicKey: (k: string) => void;
  setOllamaUrl: (u: string) => void;
  setOllamaModel: (m: string) => void;
  setSmtpHost: (v: string) => void;
  setSmtpPort: (v: number) => void;
  setSmtpUser: (v: string) => void;
  setSmtpPass: (v: string) => void;
  setSmtpFrom: (v: string) => void;
  setAlertEmail: (v: string) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // Defaults
      theme: 'light',
      auth: { token: null, user: null },
      uploadedBOQ: null,
      uploadedSOR: null,
      comparisonResults: null,
      recentAgentResults: [],
      pipelineResults: null,
      openaiKey: '',
      anthropicKey: '',
      ollamaUrl: 'http://localhost:11434',
      ollamaModel: 'qwen2.5:7b',

      // SMTP defaults
      smtpHost: 'smtp.gmail.com',
      smtpPort: 587,
      smtpUser: '',
      smtpPass: '',
      smtpFrom: 'alerts@procureflow.ai',
      alertEmail: '',

      // Auth actions
      login: async (email: string, password: string) => {
        try {
          const response = await api.post('/auth/login', { email, password });
          const { access_token, user } = response.data as any;
          
          if (access_token) {
            set({ auth: { token: access_token, user } });
            // Update API client default header
            api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
            return true;
          }
          return false;
        } catch (error) {
          console.error('Login failed:', error);
          return false;
        }
      },

      logout: () => {
        set({ auth: { token: null, user: null } });
        delete api.defaults.headers.common['Authorization'];
      },

      setToken: (token: string) => {
        set((state) => ({ auth: { ...state.auth, token } }));
        api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      },

      // Theme
      setTheme: (t) => {
        document.documentElement.classList.toggle('dark', t === 'dark');
        set({ theme: t });
      },
      
      // Uploads
      setUploadedBOQ: (f) => set({ uploadedBOQ: f }),
      setUploadedSOR: (f) => set({ uploadedSOR: f }),
      setComparisonResults: (r) => set({ comparisonResults: r }),
      addAgentExecutionRecord: (record) =>
        set((state) => ({
          recentAgentResults: [
            record,
            ...state.recentAgentResults.filter((item) => item.run_id !== record.run_id),
          ].slice(0, 12),
        })),
      setAgentExecutionRecords: (records) => set({ recentAgentResults: records.slice(0, 12) }),
      clearAgentExecutionRecords: () => set({ recentAgentResults: [] }),
      setPipelineResults: (results) => set({ pipelineResults: results }),
      
      // API Keys
      setOpenaiKey: (k) => set({ openaiKey: k }),
      setAnthropicKey: (k) => set({ anthropicKey: k }),
      setOllamaUrl: (u) => set({ ollamaUrl: u }),
      setOllamaModel: (m) => set({ ollamaModel: m }),

      // SMTP
      setSmtpHost: (v) => set({ smtpHost: v }),
      setSmtpPort: (v) => set({ smtpPort: v }),
      setSmtpUser: (v) => set({ smtpUser: v }),
      setSmtpPass: (v) => set({ smtpPass: v }),
      setSmtpFrom: (v) => set({ smtpFrom: v }),
      setAlertEmail: (v) => set({ alertEmail: v }),
    }),
    {
      name: 'procureflow-store',
      partialize: (state) => ({
        theme: state.theme,
        auth: state.auth,
        uploadedBOQ: state.uploadedBOQ,
        uploadedSOR: state.uploadedSOR,
        comparisonResults: state.comparisonResults,
        recentAgentResults: state.recentAgentResults,
        pipelineResults: state.pipelineResults,
        openaiKey: state.openaiKey,
        anthropicKey: state.anthropicKey,
        ollamaUrl: state.ollamaUrl,
        ollamaModel: state.ollamaModel,
        smtpHost: state.smtpHost,
        smtpPort: state.smtpPort,
        smtpUser: state.smtpUser,
        smtpPass: state.smtpPass,
        smtpFrom: state.smtpFrom,
        alertEmail: state.alertEmail,
      }),
    }
  )
);
