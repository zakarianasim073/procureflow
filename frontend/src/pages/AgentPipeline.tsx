import { useState, useEffect, useRef } from 'react';
import {
  Play, Loader2, Bot, User, Languages, AlertCircle,
  CheckCircle2, Clock, SkipForward, ChevronDown, ChevronRight,
  Cpu, FileText, Search, TrendingUp, Shield, DollarSign,
  BarChart, BookOpen, Eye, Zap, Download, Database
} from 'lucide-react';
import { getRecentAgentResults, listAgents, listPipelinePhases, runAgent, runPipeline, ollamaRunAgent, processTenderWithAgents } from '../api/client';
import AgentResultViewer from '../components/AgentResultViewer';
import { useAppStore } from '../store/appStore';

const phaseIcons: Record<string, any> = {
  discovery: Search,
  intelligence: FileText,
  evaluation: Shield,
  pricing: DollarSign,
  competitor: TrendingUp,
  decision: Zap,
  execution: Database,
  reporting: BarChart,
  learning: BookOpen,
  post_award: Eye,
};

const phaseColors: Record<string, string> = {
  discovery: 'bg-blue-500',
  intelligence: 'bg-purple-500',
  evaluation: 'bg-orange-500',
  pricing: 'bg-green-500',
  competitor: 'bg-rose-500',
  decision: 'bg-amber-500',
  execution: 'bg-cyan-500',
  reporting: 'bg-indigo-500',
  learning: 'bg-teal-500',
  post_award: 'bg-pink-500',
};

const statusBadge: Record<string, { icon: any; color: string; bg: string }> = {
  idle: { icon: Clock, color: 'text-gray-500', bg: 'bg-gray-100 dark:bg-gray-700' },
  running: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-100 dark:bg-blue-900/30' },
  success: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-100 dark:bg-green-900/30' },
  failed: { icon: AlertCircle, color: 'text-red-500', bg: 'bg-red-100 dark:bg-red-900/30' },
  skipped: { icon: SkipForward, color: 'text-yellow-500', bg: 'bg-yellow-100 dark:bg-yellow-900/30' },
  blocked: { icon: AlertCircle, color: 'text-orange-500', bg: 'bg-orange-100 dark:bg-orange-900/30' },
};

interface LogEntry {
  type: 'prompt' | 'result' | 'error' | 'info';
  message: string;
  timestamp: string;
  agent?: string;
  output?: any;
}

interface AgentResultData {
  agent_id: string;
  agent_name: string;
  status: string;
  output?: any;
  error?: string;
  execution_time_ms?: number;
}

interface ExecutionRecord extends AgentResultData {
  run_id: string;
  source: 'single' | 'pipeline' | 'prompt' | 'tender_process';
  timestamp: string;
  tender_id?: string;
}

export default function AgentPipeline() {
  const [agents, setAgents] = useState<any[]>([]);
  const [phases, setPhases] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [runningAgents, setRunningAgents] = useState<Set<string>>(new Set());
  const [runningPhase, setRunningPhase] = useState<string | null>(null);
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set(['discovery', 'intelligence']));
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [prompt, setPrompt] = useState('');
  const [promptLoading, setPromptLoading] = useState(false);
  const [lang, setLang] = useState<'en' | 'bn'>('en');
  const [tenderId, setTenderId] = useState('');
  const [processLoading, setProcessLoading] = useState(false);
  const [processResult, setProcessResult] = useState<any>(null);
  const [expandedResults, setExpandedResults] = useState<Set<string>>(new Set());
  const {
    recentAgentResults,
    pipelineResults,
    addAgentExecutionRecord,
    setAgentExecutionRecords,
    clearAgentExecutionRecords,
    setPipelineResults,
  } = useAppStore();
  const logEndRef = useRef<HTMLDivElement>(null);

  const retryRef = useRef(0);
  useEffect(() => {
    retryRef.current = 0;
    loadData();
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const addLog = (entry: LogEntry) => {
    setLogs(prev => [...prev, entry]);
  };

  const addExecutionRecord = (record: ExecutionRecord) => {
    addAgentExecutionRecord(record);
  };

  const normalizeExecutionRecord = (
    result: any,
    fallback: { agentId: string; agentName: string; source: ExecutionRecord['source'] },
  ): ExecutionRecord => ({
    run_id: `${fallback.source}-${result.agent_id || fallback.agentId}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    source: fallback.source,
    timestamp: new Date().toLocaleTimeString(),
    tender_id: tenderId.trim() || undefined,
    agent_id: result.agent_id || fallback.agentId,
    agent_name: result.agent_name || fallback.agentName,
    status: result.status || 'success',
    output: result.output,
    error: result.error,
    execution_time_ms: result.execution_time_ms,
  });

  const loadData = async () => {
    setLoading(true);
    try {
      const [agentsRes, phasesRes, recentRes] = await Promise.all([
        listAgents(),
        listPipelinePhases(),
        getRecentAgentResults(12),
      ]);
      if (agentsRes?.agents) {
        setAgents(agentsRes.agents);
      }
      if (phasesRes?.phases) {
        setPhases(phasesRes.phases);
      }
      if (recentRes?.results) {
        setAgentExecutionRecords(recentRes.results);
      }
    } catch (e) {
      if (retryRef.current < 3) {
        retryRef.current += 1;
        setTimeout(loadData, 1500 * retryRef.current);
      } else {
        addLog({ type: 'error', message: 'Failed to load agents after retries', timestamp: new Date().toLocaleTimeString() });
      }
    }
    setLoading(false);
  };

  const agentMap = new Map(agents.map(a => [a.agent_id, a]));
  const agentInPhase = (phaseAgents: string[]) =>
    phaseAgents.map(id => agentMap.get(id)).filter(Boolean);

  const buildContext = () => ({
    ...(tenderId.trim() ? { tender_id: tenderId.trim() } : {}),
  });

  const handleRunAgent = async (agentId: string, agentName: string) => {
    setRunningAgents(prev => new Set(prev).add(agentId));
    addLog({ type: 'info', message: `Starting agent: ${agentName} (${agentId})`, timestamp: new Date().toLocaleTimeString(), agent: agentName });
    try {
      const result = await runAgent(agentId, buildContext());
      const status = result.status || 'success';
      if (status === 'success') {
        addExecutionRecord(normalizeExecutionRecord(result, { agentId, agentName, source: 'single' }));
        addLog({ type: 'result', message: `${agentName} completed in ${(result.execution_time_ms || 0).toFixed(0)}ms`, timestamp: new Date().toLocaleTimeString(), agent: agentName, output: result.output });
      } else {
        addExecutionRecord(normalizeExecutionRecord(result, { agentId, agentName, source: 'single' }));
        addLog({ type: 'error', message: `${agentName} failed: ${result.error || 'Unknown error'}`, timestamp: new Date().toLocaleTimeString(), agent: agentName });
      }
    } catch (e: any) {
      addLog({ type: 'error', message: `${agentName} error: ${e.message}`, timestamp: new Date().toLocaleTimeString(), agent: agentName });
    }
    loadData();
    setRunningAgents(prev => { const n = new Set(prev); n.delete(agentId); return n; });
  };

  const handleRunPhase = async (phaseName: string, phaseAgentIds: string[]) => {
    setRunningPhase(phaseName);
    addLog({ type: 'info', message: `Starting phase: ${phaseName} (${phaseAgentIds.length} agents)`, timestamp: new Date().toLocaleTimeString() });
    setPipelineResults(null);
    try {
      const result = await runPipeline('phase', phaseName, buildContext());
      const phaseResult = result.output?.[phaseName];
      if (phaseResult) {
        const succeeded = phaseResult.all_succeeded ? 'All succeeded' : `${phaseResult.failed_agents?.length || 0} failed`;
        addLog({ type: 'result', message: `Phase "${phaseName}" complete: ${succeeded}`, timestamp: new Date().toLocaleTimeString() });
        // Store detailed results
        if (phaseResult.agent_results) {
          const results = Object.values(phaseResult.agent_results) as AgentResultData[];
          setPipelineResults({ [phaseName]: results });
        }
      }
    } catch (e: any) {
      addLog({ type: 'error', message: `Phase "${phaseName}" error: ${e.message}`, timestamp: new Date().toLocaleTimeString() });
    }
    loadData();
    setRunningPhase(null);
  };

  const handleRunFullPipeline = async () => {
    setRunningPhase('full');
    addLog({ type: 'info', message: `Starting full pipeline${tenderId.trim() ? ` for tender ${tenderId.trim()}` : ''}`, timestamp: new Date().toLocaleTimeString() });
    setPipelineResults(null);
    try {
      const result = await runPipeline('full', undefined, buildContext());
      const output = result.output || {};
      const phasesSummary = output.phases || {};
      const phasesCompleted = output.phases_completed || 0;
      addLog({ type: 'result', message: `Full pipeline complete: ${phasesCompleted} phases`, timestamp: new Date().toLocaleTimeString(), output: phasesSummary });
      // Reconstruct per-agent results from the detailed response
      const allResults: Record<string, AgentResultData[]> = {};
      for (const phaseName of Object.keys(phasesSummary)) {
        const phaseData = output[phaseName];
        if (phaseData?.agent_results) {
          allResults[phaseName] = Object.values(phaseData.agent_results) as AgentResultData[];
        }
      }
      if (Object.keys(allResults).length > 0) {
        setPipelineResults(allResults);
        setExpandedResults(new Set(Object.keys(allResults).slice(0, 3)));
      }
    } catch (e: any) {
      addLog({ type: 'error', message: `Full pipeline error: ${e.message}`, timestamp: new Date().toLocaleTimeString() });
    }
    loadData();
    setRunningPhase(null);
  };

  const handleOllamaPrompt = async () => {
    if (!prompt.trim() || promptLoading) return;
    setPromptLoading(true);
    addLog({ type: 'prompt', message: prompt, timestamp: new Date().toLocaleTimeString() });
    try {
      const result = await ollamaRunAgent(prompt, lang);
      if (result.agent_id) {
        addLog({
          type: 'info',
          message: `Ollama routed to: ${result.agent_name || result.agent_id}`,
          timestamp: new Date().toLocaleTimeString(),
          agent: result.agent_name,
        });
      }
      if (result.result) {
        const output = result.result.output || {};
        addExecutionRecord(normalizeExecutionRecord(result.result, {
          agentId: result.agent_id || 'ollama-agent',
          agentName: result.agent_name || 'Ollama Agent',
          source: 'prompt',
        }));
        const outputStr = Object.keys(output).length > 0
          ? JSON.stringify(output).substring(0, 2000)
          : 'No output data';
        addLog({
          type: 'result',
          message: `${result.agent_name || 'Agent'} result: ${outputStr}`,
          timestamp: new Date().toLocaleTimeString(),
          agent: result.agent_name,
          output,
        });
      }
      if (result.message) {
        addLog({ type: 'info', message: result.message, timestamp: new Date().toLocaleTimeString() });
      }
      loadData();
    } catch (e: any) {
      addLog({ type: 'error', message: `Ollama command error: ${e.message}`, timestamp: new Date().toLocaleTimeString() });
    }
    setPromptLoading(false);
    setPrompt('');
  };

  const handleProcessTender = async () => {
    const tid = tenderId.trim();
    if (!tid) {
      addLog({ type: 'error', message: 'Please enter a Tender ID first', timestamp: new Date().toLocaleTimeString() });
      return;
    }
    setProcessLoading(true);
    addLog({ type: 'info', message: `Processing tender ${tid}: running agents → generating documents...`, timestamp: new Date().toLocaleTimeString() });
    setProcessResult(null);
    try {
      const result = await processTenderWithAgents(tid);
      setProcessResult(result);
      const pipelineStatus = result.pipeline_result?.status || 'success';
      addExecutionRecord({
        run_id: `tender-process-${tid}-${Date.now()}`,
        source: 'tender_process',
        timestamp: new Date().toLocaleTimeString(),
        tender_id: tid,
        agent_id: 'pipeline-process',
        agent_name: 'Tender Processing Pipeline',
        status: pipelineStatus,
        output: {
          tender_id: result.tender_id,
          pipeline_status: pipelineStatus,
          generated_artifacts: result.documents?.artifacts || [],
        },
        execution_time_ms: result.pipeline_result?.execution_time_ms,
      });
      addLog({ type: 'result', message: `Tender ${tid} processed successfully! Documents generated.`, timestamp: new Date().toLocaleTimeString() });
      if (result.documents?.artifacts) {
        result.documents.artifacts.forEach((a: any) => {
          addLog({ type: 'info', message: `  Artifact: ${a.filename} (${a.kind})`, timestamp: new Date().toLocaleTimeString() });
        });
      }
    } catch (e: any) {
      addLog({ type: 'error', message: `Tender processing failed: ${e.message}`, timestamp: new Date().toLocaleTimeString() });
    }
    setProcessLoading(false);
  };

  const togglePhase = (phase: string) => {
    setExpandedPhases(prev => {
      const n = new Set(prev);
      if (n.has(phase)) n.delete(phase); else n.add(phase);
      return n;
    });
  };

  const toggleResult = (phaseName: string) => {
    setExpandedResults(prev => {
      const n = new Set(prev);
      if (n.has(phaseName)) n.delete(phaseName); else n.add(phaseName);
      return n;
    });
  };

  const StatusBadge = ({ status }: { status: string }) => {
    const s = statusBadge[status] || statusBadge.idle;
    const Icon = s.icon;
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${s.bg} ${s.color}`}>
        <Icon size={12} className={status === 'running' ? 'animate-spin' : ''} />
        {status}
      </span>
    );
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Agent Pipeline</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Full pipeline orchestration system — {agents.length} agents registered
          </p>
        </div>
        <div className="flex items-center gap-3">
          {loading && <Loader2 size={18} className="animate-spin text-gray-400" />}
          <button
            onClick={() => { loadData(); addLog({ type: 'info', message: 'Refreshed agent status', timestamp: new Date().toLocaleTimeString() }); }}
            className="px-3 py-1.5 text-sm rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Tender ID Input */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <div className="flex items-center gap-2 mb-3">
          <Database size={16} className="text-primary-600" />
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Tender Context</h2>
        </div>
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Tender ID</label>
            <input
              value={tenderId}
              onChange={e => setTenderId(e.target.value)}
              placeholder="e.g. 1264860 or eGP-2024-12345"
              className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
            />
          </div>
          <button
            onClick={handleProcessTender}
            disabled={processLoading || !tenderId.trim()}
            className="px-5 py-2.5 rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2 text-sm font-medium"
          >
            {processLoading ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
            {processLoading ? 'Processing...' : 'Run Agents & Generate Documents'}
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          Enter a tender ID to scope agent execution. Then run individual agents, phases, or the full pipeline. The "Run Agents & Generate Documents" button runs the full pipeline then generates DOCX/XLSX documents.
        </p>
      </div>

      {/* Process Result Summary */}
      {processResult && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-xl p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-green-800 dark:text-green-300 font-medium">
              <CheckCircle2 size={18} />
              Tender {processResult.tender_id} — Processed Successfully
            </div>
            <button onClick={() => setProcessResult(null)} className="text-green-600 dark:text-green-400 text-xs hover:underline">Dismiss</button>
          </div>
          <div className="mt-2 text-sm text-green-700 dark:text-green-400">
            <p>Pipeline: {processResult.pipeline_result?.status}</p>
            {processResult.documents?.artifacts && (
              <div className="mt-1">
                <span className="font-medium">Generated artifacts:</span>
                <ul className="list-disc list-inside ml-2 text-xs mt-1">
                  {processResult.documents.artifacts.map((a: any, i: number) => (
                    <li key={i}>{a.filename} <span className="text-green-500">({a.kind})</span></li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Native Language Command Input */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Bot size={16} /> Native Language Agent Command
          </h2>
          <button
            onClick={() => setLang(prev => prev === 'en' ? 'bn' : 'en')}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-gray-100 dark:bg-gray-700 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
          >
            <Languages size={14} /> {lang === 'en' ? 'বাংলা' : 'English'}
          </button>
        </div>
        <div className="flex gap-2">
          <input
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleOllamaPrompt()}
            placeholder={lang === 'en'
              ? 'Type a command in English or Bengali... (e.g., "Show me award intelligence for BWDB")'
              : 'ইংরেজি বা বাংলায় কমান্ড লিখুন... (যেমন: "BWDB এর পুরস্কার তথ্য দেখান")'}
            className="flex-1 px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
          />
          <button
            onClick={handleOllamaPrompt}
            disabled={!prompt.trim() || promptLoading}
            className="px-4 py-2.5 rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2 text-sm"
          >
            {promptLoading ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
            Run
          </button>
        </div>
      </div>

      {/* Execution Log */}
      {logs.length > 0 && (
        <div className="bg-gray-950 dark:bg-black rounded-xl border border-gray-800 p-4 font-mono text-xs max-h-48 overflow-y-auto custom-scrollbar">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-[10px] uppercase tracking-wider font-sans">Execution Log</span>
            <button onClick={() => setLogs([])} className="text-gray-500 hover:text-gray-300 text-[10px] font-sans">
              Clear
            </button>
          </div>
          {logs.map((log, i) => (
            <div key={i} className="flex gap-2 py-0.5">
              <span className="text-gray-600 shrink-0 w-16">[{log.timestamp}]</span>
              <span className={
                log.type === 'prompt' ? 'text-yellow-300' :
                log.type === 'result' ? 'text-green-400' :
                log.type === 'error' ? 'text-red-400' : 'text-blue-300'
              }>
                {log.agent && <span className="text-purple-400">[{log.agent}] </span>}
                {log.message}
              </span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}

      {/* Recent Agent Output Dashboard */}
      {recentAgentResults.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
              <Bot size={16} /> Recent Agent Output
            </div>
            <button
              onClick={clearAgentExecutionRecords}
              className="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
            >
              Clear
            </button>
          </div>
          <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-3">
            {recentAgentResults.map((record) => (
              <div key={record.run_id} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/30 p-3">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-gray-900 dark:text-white truncate">{record.agent_name}</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400">
                      {record.source.replace('_', ' ')} • {record.timestamp}{record.tender_id ? ` • ${record.tender_id}` : ''}
                    </div>
                  </div>
                  <StatusBadge status={record.status} />
                </div>
                {record.execution_time_ms && (
                  <div className="mb-2 text-[11px] text-gray-400">{record.execution_time_ms.toFixed(0)}ms</div>
                )}
                {record.error ? (
                  <div className="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 rounded p-2">{record.error}</div>
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

      {/* Agent Results Panel */}
      {pipelineResults && Object.keys(pipelineResults).length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
              <BarChart size={16} /> Agent Results
            </div>
            <button
              onClick={() => setPipelineResults(null)}
              className="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
            >
              Clear
            </button>
          </div>
          <div className="divide-y divide-gray-100 dark:divide-gray-700/50">
            {Object.entries(pipelineResults).map(([phaseName, results]) => {
              const isOpen = expandedResults.has(phaseName);
              const successCount = results.filter(r => r.status === 'success').length;
              return (
                <div key={phaseName}>
                  <button
                    onClick={() => toggleResult(phaseName)}
                    className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors text-left"
                  >
                    <div className="flex-1">
                      <span className="text-sm font-medium text-gray-900 dark:text-white capitalize">{phaseName.replace(/_/g, ' ')}</span>
                      <span className="ml-2 text-xs text-gray-500">{successCount}/{results.length} succeeded</span>
                    </div>
                    {isOpen ? <ChevronDown size={16} className="text-gray-400" /> : <ChevronRight size={16} className="text-gray-400" />}
                  </button>
                  {isOpen && (
                    <div className="px-4 pb-3 space-y-2">
                      {results.map((r) => (
                        <div key={r.agent_id} className="bg-gray-50 dark:bg-gray-750 rounded-lg p-3 text-sm">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-medium text-gray-900 dark:text-white">{r.agent_name}</span>
                            <StatusBadge status={r.status} />
                          </div>
                          {r.execution_time_ms && (
                            <span className="text-xs text-gray-400">{r.execution_time_ms.toFixed(0)}ms</span>
                          )}
                          {r.error && (
                            <div className="mt-1 text-xs text-red-500 bg-red-50 dark:bg-red-900/20 rounded p-1.5">{r.error}</div>
                          )}
                          {r.output && Object.keys(r.output).length > 0 && (
                            <div className="mt-2">
                              <AgentResultViewer agentId={r.agent_id} agentName={r.agent_name} output={r.output} />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Pipeline Phases */}
      <div className="space-y-4">
        {Object.entries(phases).map(([phaseName, phaseData]: [string, any]) => {
          const Icon = phaseIcons[phaseName] || Cpu;
          const color = phaseColors[phaseName] || 'bg-gray-500';
          const phaseAgents = agentInPhase(phaseData.agents || []);
          const isExpanded = expandedPhases.has(phaseName);

          return (
            <div key={phaseName} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              {/* Phase Header */}
              <div className="flex items-center gap-3 p-4 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors text-left">
                <button
                  type="button"
                  onClick={() => togglePhase(phaseName)}
                  className="flex flex-1 items-center gap-3 text-left"
                >
                  <div className={`w-8 h-8 rounded-lg ${color} flex items-center justify-center text-white`}>
                    <Icon size={16} />
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-gray-900 dark:text-white capitalize">
                      {phaseName.replace(/_/g, ' ')}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {phaseData.agents?.length || 0} agents
                    </div>
                  </div>
                  {isExpanded ? <ChevronDown size={18} className="text-gray-400" /> : <ChevronRight size={18} className="text-gray-400" />}
                </button>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => handleRunPhase(phaseName, phaseData.agents || [])}
                    disabled={runningPhase === phaseName}
                    className="px-3 py-1.5 rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 text-xs font-medium transition-colors flex items-center gap-1.5"
                  >
                    {runningPhase === phaseName
                      ? <><Loader2 size={12} className="animate-spin" /> Running...</>
                      : <><Play size={12} /> Run Phase</>}
                  </button>
                </div>
              </div>

              {/* Phase Agents */}
              {isExpanded && (
                <div className="border-t border-gray-200 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700/50">
                  {phaseAgents.length === 0 && (
                    <div className="p-4 text-sm text-gray-400 text-center">No agents loaded</div>
                  )}
                  {phaseAgents.map((agent: any) => (
                    <div key={agent.agent_id} className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors">
                      <StatusBadge status={agent.status} />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-900 dark:text-white truncate">
                          {agent.agent_name}
                        </div>
                        <div className="text-xs text-gray-400 truncate">{agent.description}</div>
                      </div>
                      <div className="text-xs text-gray-400 font-mono shrink-0">{agent.agent_id}</div>
                      <button
                        onClick={() => handleRunAgent(agent.agent_id, agent.agent_name)}
                        disabled={runningAgents.has(agent.agent_id)}
                        className="px-2.5 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 text-xs font-medium transition-colors flex items-center gap-1"
                      >
                        {runningAgents.has(agent.agent_id)
                          ? <Loader2 size={12} className="animate-spin" />
                          : <Play size={12} />}
                        {runningAgents.has(agent.agent_id) ? 'Running' : 'Run'}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Full Pipeline Run */}
      <div className="flex justify-center gap-4">
        <button
          onClick={handleRunFullPipeline}
          disabled={runningPhase === 'full'}
          className="px-6 py-3 rounded-xl bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors font-medium flex items-center gap-2"
        >
          {runningPhase === 'full'
            ? <><Loader2 size={18} className="animate-spin" /> Running Full Pipeline...</>
            : <><Play size={18} /> Run Full Pipeline (All Phases)</>}
        </button>
      </div>
    </div>
  );
}
