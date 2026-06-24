import {
  AlertCircle,
  Award,
  BarChart3,
  BrainCircuit,
  CheckCircle2,
  DollarSign,
  FileText,
  Shield,
  Target,
  Users,
  XCircle,
} from 'lucide-react';

interface AgentResultViewerProps {
  agentId: string;
  agentName: string;
  output: any;
}

function DataRow({ label, value, highlight }: { label: string; value: any; highlight?: boolean }) {
  return (
    <div className={`flex items-center justify-between gap-4 rounded-lg px-3 py-2 ${highlight ? 'bg-primary-50 dark:bg-primary-900/10' : ''}`}>
      <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      <span className={`text-right text-sm font-semibold ${highlight ? 'text-primary-600 dark:text-primary-400' : 'text-gray-900 dark:text-white'}`}>
        {typeof value === 'number' ? value.toLocaleString() : String(value ?? '—')}
      </span>
    </div>
  );
}

function Section({ title, icon: Icon, children }: { title: string; icon: any; children: React.ReactNode }) {
  return (
    <div className="mb-4 last:mb-0">
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
        <Icon size={14} />
        {title}
      </h4>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function StatusBadgeInline({ status }: { status: string }) {
  const normalized = (status || '').toLowerCase();
  const positive = ['success', 'passed', 'approved', 'proceed', 'bid'].includes(normalized);
  const negative = ['failed', 'rejected', 'no_bid'].includes(normalized);
  const color = positive
    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
    : negative
      ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
      : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300';
  const Icon = positive ? CheckCircle2 : negative ? XCircle : AlertCircle;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      <Icon size={12} />
      {status}
    </span>
  );
}

function DefaultView({ output }: { output: any }) {
  return (
    <div className="space-y-1">
      {Object.entries(output || {}).slice(0, 10).map(([key, value]) => (
        <DataRow key={key} label={key.replace(/_/g, ' ')} value={Array.isArray(value) ? `${value.length} items` : typeof value === 'object' ? JSON.stringify(value).slice(0, 80) : value} />
      ))}
    </div>
  );
}

function AwardView({ output }: { output: any }) {
  const awards = output.awards ?? output.recent_awards ?? [];
  return (
    <div className="space-y-3">
      <Section title="Award Intelligence" icon={Award}>
        <DataRow label="Awards Collected" value={output.awards_collected ?? output.total_awards ?? awards.length} highlight />
        {output.total_value != null && <DataRow label="Total Value" value={`BDT ${Number(output.total_value).toLocaleString()}`} />}
        {output.avg_discount != null && <DataRow label="Average Discount" value={`${output.avg_discount}%`} />}
      </Section>
      {awards.length > 0 && (
        <Section title="Recent Awards" icon={FileText}>
          {awards.slice(0, 5).map((award: any, index: number) => (
            <div key={`${award.tender_id ?? index}`} className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-700/30">
              <div className="text-sm font-medium text-gray-900 dark:text-white">{award.winner ?? award.contractor_name ?? 'Unknown'}</div>
              <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {(award.title ?? '').slice(0, 96)}
              </div>
            </div>
          ))}
        </Section>
      )}
    </div>
  );
}

function BidPositionView({ output }: { output: any }) {
  return (
    <div className="space-y-3">
      <Section title="Bid Position" icon={Target}>
        <DataRow label="Recommended Discount" value={`${output.recommended_discount ?? output.optimal_discount ?? 0}%`} highlight />
        <DataRow label="Win Probability" value={`${output.win_probability ?? output.win_chance ?? 0}%`} />
        <DataRow label="Expected Margin" value={`${output.estimated_margin_pct ?? output.expected_margin ?? 0}%`} />
      </Section>
    </div>
  );
}

function CompetitorView({ output }: { output: any }) {
  const profiles = output.profiles ?? output.competitors ?? [];
  return (
    <div className="space-y-3">
      <Section title="Competitor Profiles" icon={Users}>
        {profiles.slice(0, 5).map((profile: any, index: number) => (
          <div key={`${profile.name ?? index}`} className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-700/30">
            <div className="text-sm font-medium text-gray-900 dark:text-white">{profile.name ?? profile.contractor_name}</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Awards: {profile.total_awards ?? 0} | Avg Discount: {profile.avg_discount_pct ?? 0}%
            </div>
          </div>
        ))}
      </Section>
    </div>
  );
}

function ComplianceView({ output }: { output: any }) {
  return (
    <div className="space-y-3">
      <div className="mb-3 flex items-center gap-3">
        <span className="text-2xl font-bold text-gray-900 dark:text-white">{output.overall_score ?? output.score ?? 0}%</span>
        <StatusBadgeInline status={output.overall_passed ?? output.passed ? 'passed' : 'failed'} />
      </div>
      {output.recommendations?.length > 0 && (
        <Section title="Recommendations" icon={Shield}>
          {output.recommendations.slice(0, 5).map((item: string, index: number) => (
            <p key={index} className="py-0.5 text-sm text-gray-600 dark:text-gray-400">• {item}</p>
          ))}
        </Section>
      )}
      <DefaultView output={output} />
    </div>
  );
}

function ExecutiveDecisionView({ output }: { output: any }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <span className="text-lg font-bold text-gray-900 dark:text-white">{output.decision ?? output.recommendation ?? 'Review'}</span>
        <StatusBadgeInline status={String(output.decision ?? output.recommendation ?? 'pending')} />
      </div>
      {output.reasoning && (
        <Section title="Reasoning" icon={BrainCircuit}>
          <p className="whitespace-pre-wrap text-sm text-gray-600 dark:text-gray-400">{output.reasoning}</p>
        </Section>
      )}
      {output.factors && (
        <Section title="Decision Factors" icon={BarChart3}>
          {Object.entries(output.factors).map(([key, value]) => (
            <DataRow key={key} label={key.replace(/_/g, ' ')} value={value} />
          ))}
        </Section>
      )}
    </div>
  );
}

const AGENT_VIEWERS: Record<string, React.FC<{ output: any }>> = {
  'agent-007-eligibility-compliance': ComplianceView,
  'agent-009-ppr-evaluation': ComplianceView,
  'agent-013-competitor-intelligence': CompetitorView,
  'agent-014-award-intelligence': AwardView,
  'agent-016-win-probability': BidPositionView,
  'agent-017-bid-position-optimizer': BidPositionView,
  'agent-021-executive-decision': ExecutiveDecisionView,
};

export default function AgentResultViewer({ agentId, agentName, output }: AgentResultViewerProps) {
  const Viewer = AGENT_VIEWERS[agentId] ?? DefaultView;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">{agentName}</div>
          <div className="text-xs text-gray-400">{agentId}</div>
        </div>
      </div>
      <Viewer output={output} />
    </div>
  );
}
