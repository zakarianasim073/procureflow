import { useEffect, useState } from 'react';
import { Users, Plus, Trash2, Mail, Shield, UserCog, Eye, UserPlus, Activity, Building2, Check, X, RefreshCw } from 'lucide-react';
import api from '../api/client';

interface Member { user_id: string; email: string; name: string; role: string; status: string; joined_at: string; }
interface Org { id: string; name: string; slug: string; plan: string; created_at: string; member_count: number; }
interface Invitation { id: string; email: string; role: string; token: string; status: string; created_at: string; expires_at: string; }
interface AuditActivity { id: string; action: string; entity_type: string; created_at: string; metadata: any; }

const ROLE_OPTIONS = [
  { value: 'admin', label: 'Admin', icon: Shield, desc: 'Full access' },
  { value: 'estimator', label: 'Estimator', icon: UserCog, desc: 'Can analyze and run agents' },
  { value: 'viewer', label: 'Viewer', icon: Eye, desc: 'Read-only access' },
];

export default function TeamManagement() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [selectedOrg, setSelectedOrg] = useState<Org | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [activity, setActivity] = useState<AuditActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateOrg, setShowCreateOrg] = useState(false);
  const [orgName, setOrgName] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('viewer');
  const [copied, setCopied] = useState('');

  useEffect(() => {
    loadOrgs().finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedOrg) loadOrgData(selectedOrg.id);
  }, [selectedOrg]);

  const loadOrgs = async () => {
    try {
      const { data } = await api.get('/team/organizations');
      setOrgs(data.organizations || []);
      if (data.organizations?.length > 0 && !selectedOrg) setSelectedOrg(data.organizations[0]);
    } catch {}
  };

  const loadOrgData = async (orgId: string) => {
    try {
      const [mRes, iRes, aRes] = await Promise.all([
        api.get(`/team/organizations/${orgId}/members`),
        api.get('/team/invitations'),
        api.get('/team/activity', { params: { org_id: orgId, limit: 30 } }),
      ]);
      setMembers(mRes.data.members || []);
      setInvitations(iRes.data.invitations || []);
      setActivity(aRes.data.activity || []);
    } catch {}
  };

  const createOrg = async () => {
    if (!orgName.trim()) return;
    try {
      const { data } = await api.post('/team/organizations', { name: orgName });
      setOrgs([...orgs, data.organization]);
      setSelectedOrg(data.organization);
      setShowCreateOrg(false);
      setOrgName('');
    } catch {}
  };

  const inviteMember = async () => {
    if (!inviteEmail.trim() || !selectedOrg) return;
    try {
      const { data } = await api.post(`/team/organizations/${selectedOrg.id}/invite`, { email: inviteEmail, role: inviteRole });
      setInvitations([...invitations, data.invitation]);
      setInviteEmail('');
      setCopied(data.invite_link || '');
      setTimeout(() => setCopied(''), 3000);
    } catch {}
  };

  const removeMember = async (userId: string) => {
    if (!selectedOrg) return;
    try {
      await api.delete(`/team/organizations/${selectedOrg.id}/members/${userId}`);
      setMembers(members.filter((m) => m.user_id !== userId));
    } catch {}
  };

  const RoleBadge = ({ role }: { role: string }) => {
    const colors: Record<string, string> = {
      admin: 'bg-purple-100 dark:bg-purple-900/30 text-purple-600',
      estimator: 'bg-blue-100 dark:bg-blue-900/30 text-blue-600',
      viewer: 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400',
    };
    return <span className={`px-2 py-0.5 text-xs rounded-full font-medium ${colors[role] || colors.viewer}`}>{role}</span>;
  };

  if (loading) return <div className="p-6 max-w-5xl mx-auto flex items-center justify-center h-96 text-gray-400"><RefreshCw size={20} className="animate-spin mr-2" /> Loading...</div>;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2"><Users className="text-primary-600" size={28} /> Team & Collaboration</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Manage organizations, invites, and collaboration activity</p>
        </div>
        <button onClick={() => setShowCreateOrg(!showCreateOrg)} className="px-3 py-1.5 bg-primary-600 hover:bg-primary-700 text-white text-sm rounded-lg flex items-center gap-1.5 transition-colors">
          <Plus size={14} /> New Organization
        </button>
      </div>

      {showCreateOrg && (
        <div className="mb-6 p-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Create Organization</h3>
          <div className="flex gap-3">
            <input value={orgName} onChange={(e) => setOrgName(e.target.value)} placeholder="Organization name" className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
            <button onClick={createOrg} className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm rounded-lg">Create</button>
            <button onClick={() => setShowCreateOrg(false)} className="p-2 text-gray-400 hover:text-gray-600"><X size={18} /></button>
          </div>
        </div>
      )}

      {orgs.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-gray-400 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <Building2 size={48} className="mb-3 opacity-30" />
          <p className="text-sm">No organizations yet</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <div className="space-y-2">
            {orgs.map((org) => (
              <button key={org.id} onClick={() => setSelectedOrg(org)} className={`w-full p-3 rounded-xl text-left transition-colors border ${selectedOrg?.id === org.id ? 'bg-primary-50 dark:bg-primary-900/20 border-primary-200 dark:border-primary-700' : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-primary-300 dark:hover:border-primary-600'}`}>
                <div className="font-medium text-sm text-gray-900 dark:text-white">{org.name}</div>
                <div className="text-xs text-gray-400 mt-1">{org.member_count} members · {org.plan}</div>
              </button>
            ))}
          </div>

          {selectedOrg && (
            <div className="lg:col-span-3 space-y-6">
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2"><Users size={16} className="text-primary-600" /> Members ({members.length})</h3>
                </div>
                <div className="space-y-2">
                  {members.map((m) => (
                    <div key={m.user_id} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400 flex items-center justify-center text-xs font-bold">{m.name?.charAt(0) || m.email?.charAt(0) || '?'}</div>
                        <div>
                          <div className="text-sm font-medium text-gray-900 dark:text-white">{m.name || m.email}</div>
                          <div className="text-xs text-gray-400">{m.email}</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <RoleBadge role={m.role} />
                        <button onClick={() => removeMember(m.user_id)} className="text-gray-400 hover:text-red-500 transition-colors" title="Remove"><Trash2 size={14} /></button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4"><UserPlus size={16} className="text-green-600" /> Invite Member</h3>
                <div className="flex gap-3">
                  <input value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} placeholder="Email address" type="email" className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
                  <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm">
                    {ROLE_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                  </select>
                  <button onClick={inviteMember} className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm rounded-lg flex items-center gap-1.5"><Mail size={14} /> Send Invite</button>
                </div>
                {copied && <div className="mt-2 flex items-center gap-2 text-xs text-green-600"><Check size={12} /> Invite generated</div>}
              </div>

              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4"><Activity size={16} className="text-primary-600" /> Recent Activity</h3>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {activity.map((a) => (
                    <div key={a.id} className="flex items-center gap-3 text-sm text-gray-600 dark:text-gray-400 py-1.5 border-b border-gray-100 dark:border-gray-700 last:border-0">
                      <span className="text-xs font-mono text-gray-400 w-16 shrink-0">{new Date(a.created_at).toLocaleDateString()}</span>
                      <span className="capitalize">{a.action.replace(/_/g, ' ')}</span>
                      <span className="text-xs text-gray-400">{a.entity_type}</span>
                    </div>
                  ))}
                  {activity.length === 0 && <p className="text-sm text-gray-400 text-center py-4">No activity yet</p>}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
