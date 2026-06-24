import { useState, useEffect } from 'react';
import { Key, User, Bot, Server, Cpu, LogIn, LogOut, ExternalLink, Mail, Send, CheckCircle, XCircle, HelpCircle, Eye, EyeOff, MessageCircle, Smartphone } from 'lucide-react';
import { useAppStore } from '../store/appStore';
import { getSmtpSettings, updateSmtpSettings, testSmtpSettings, getWhatsappSettings, updateWhatsappSettings } from '../api/client';

export default function Settings() {
  const {
    auth, login, logout,
    openaiKey, setOpenaiKey,
    anthropicKey, setAnthropicKey,
    ollamaUrl, setOllamaUrl,
    ollamaModel, setOllamaModel,
    smtpHost, setSmtpHost,
    smtpPort, setSmtpPort,
    smtpUser, setSmtpUser,
    smtpPass, setSmtpPass,
    smtpFrom, setSmtpFrom,
    alertEmail, setAlertEmail,
  } = useAppStore();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loggingIn, setLoggingIn] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // SMTP state
  const [smtpSaving, setSmtpSaving] = useState(false);
  const [smtpTesting, setSmtpTesting] = useState(false);
  const [smtpTestEmail, setSmtpTestEmail] = useState('');
  const [smtpStatus, setSmtpStatus] = useState<{ok: boolean; msg: string} | null>(null);
  const [showAppPass, setShowAppPass] = useState(false);

  // WhatsApp state
  const [whatsappPhone, setWhatsappPhone] = useState('');
  const [whatsappSaving, setWhatsappSaving] = useState(false);
  const [whatsappStatus, setWhatsappStatus] = useState<{ok: boolean; msg: string} | null>(null);

  // Load SMTP settings on mount
  useEffect(() => {
    getSmtpSettings().then((res) => {
      if (res.smtp_host) setSmtpHost(res.smtp_host);
      if (res.smtp_port) setSmtpPort(res.smtp_port);
      if (res.smtp_user) setSmtpUser(res.smtp_user);
      if (res.smtp_from) setSmtpFrom(res.smtp_from);
      if (res.alert_email) setAlertEmail(res.alert_email);
    }).catch(() => {});

    // Load WhatsApp settings
    getWhatsappSettings().then((res) => {
      if (res.phone) setWhatsappPhone(res.phone);
    }).catch(() => {});
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoggingIn(true);
    setError('');
    try {
      const ok = await login(email, password);
      if (ok) {
        setSuccess('Logged in successfully!');
        setEmail('');
        setPassword('');
      } else {
        setError('Login failed. Check your credentials.');
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Login failed');
    } finally {
      setLoggingIn(false);
    }
  };

  const copyKey = (key: string) => {
    navigator.clipboard.writeText(key);
    setSuccess('Copied to clipboard!');
    setTimeout(() => setSuccess(''), 2000);
  };

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">Settings</h1>

      {/* Auth Section */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <User size={20} className="text-primary-600" />
          Account
        </h2>

        {auth.user ? (
          <div>
            <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg mb-3">
              <div className="w-10 h-10 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center text-primary-600 font-bold">
                {auth.user.name?.charAt(0).toUpperCase()}
              </div>
              <div>
                <div className="font-medium text-gray-900 dark:text-white">{auth.user.name}</div>
                <div className="text-sm text-gray-500 dark:text-gray-400">Plan: {auth.user.plan}</div>
              </div>
            </div>
            <button
              onClick={logout}
              className="flex items-center gap-2 text-sm text-red-600 hover:text-red-700 transition-colors"
            >
              <LogOut size={16} /> Sign Out
            </button>
          </div>
        ) : (
          <form onSubmit={handleLogin} className="space-y-4">
            <div className="rounded-lg border border-primary-200 bg-primary-50 px-3 py-3 text-sm text-primary-800 dark:border-primary-800 dark:bg-primary-900/20 dark:text-primary-200">
              <div className="font-medium">Owner Access</div>
              <div className="mt-1">Use the credentials configured for your ProcureFlow owner account.</div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="owner@example.com"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                required
              />
            </div>
            {error && (
              <div className="text-sm text-red-600 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">
                {error}
              </div>
            )}
            {success && (
              <div className="text-sm text-green-600 bg-green-50 dark:bg-green-900/20 px-3 py-2 rounded-lg">
                {success}
              </div>
            )}
            <button
              type="submit"
              disabled={loggingIn}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors text-sm font-medium"
            >
              <LogIn size={16} />
              {loggingIn ? 'Signing in...' : 'Enter Owner Dashboard'}
            </button>
          </form>
        )}
      </section>

      {/* API Keys */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Key size={20} className="text-primary-600" />
          AI Provider Keys
        </h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              OpenAI API Key
            </label>
            <input
              type="password"
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
              placeholder="sk-..."
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Anthropic Claude API Key
            </label>
            <input
              type="password"
              value={anthropicKey}
              onChange={(e) => setAnthropicKey(e.target.value)}
              placeholder="sk-ant-..."
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
            />
          </div>
        </div>
      </section>

      {/* AI Models */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Bot size={20} className="text-primary-600" />
          Local Models (Ollama)
        </h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Ollama Server URL
            </label>
            <input
              type="url"
              value={ollamaUrl}
              onChange={(e) => setOllamaUrl(e.target.value)}
              placeholder="http://localhost:11434"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Ollama Model
            </label>
            <input
              type="text"
              value={ollamaModel}
              onChange={(e) => setOllamaModel(e.target.value)}
              placeholder="llama3.2"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
            />
          </div>
        </div>
      </section>

      {/* Email / SMTP (Gmail App Password) */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Mail size={20} className="text-primary-600" />
          Email (Gmail App Password)
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Configure Gmail SMTP with an App Password to receive tender alerts and reports.
          Generate one at{' '}
          <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer"
             className="text-primary-600 hover:underline">myaccount.google.com/apppasswords</a>
        </p>
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">SMTP Host</label>
              <input type="text" value={smtpHost} onChange={(e) => setSmtpHost(e.target.value)}
                placeholder="smtp.gmail.com"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">SMTP Port</label>
              <input type="number" value={smtpPort} onChange={(e) => setSmtpPort(Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Gmail Address</label>
            <input type="email" value={smtpUser} onChange={(e) => setSmtpUser(e.target.value)}
              placeholder="you@gmail.com"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Gmail App Password
              <span className="ml-1 text-xs text-gray-400">(16 characters, no spaces)</span>
            </label>
            <div className="relative">
              <input type={showAppPass ? 'text' : 'password'} value={smtpPass}
                onChange={(e) => setSmtpPass(e.target.value)}
                placeholder="xxxx xxxx xxxx xxxx"
                className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
              <button type="button" onClick={() => setShowAppPass(!showAppPass)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                {showAppPass ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">From Name/Email</label>
              <input type="text" value={smtpFrom} onChange={(e) => setSmtpFrom(e.target.value)}
                placeholder="alerts@procureflow.ai"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Alert Email (recipient)</label>
              <input type="email" value={alertEmail} onChange={(e) => setAlertEmail(e.target.value)}
                placeholder="z.nasim073@gmail.com"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
            </div>
          </div>

          {smtpStatus && (
            <div className={`flex items-start gap-2 text-sm p-3 rounded-lg ${smtpStatus.ok ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'}`}>
              {smtpStatus.ok ? <CheckCircle size={16} className="mt-0.5 shrink-0" /> : <XCircle size={16} className="mt-0.5 shrink-0" />}
              <span>{smtpStatus.msg}</span>
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            <button onClick={async () => {
              setSmtpSaving(true); setSmtpStatus(null);
              try {
                const res = await updateSmtpSettings({
                  smtp_host: smtpHost, smtp_port: smtpPort,
                  smtp_user: smtpUser, smtp_pass: smtpPass,
                  smtp_from: smtpFrom, alert_email: alertEmail,
                });
                setSmtpStatus({ ok: true, msg: res.message || 'Saved!' });
              } catch (e: any) {
                setSmtpStatus({ ok: false, msg: e?.response?.data?.detail || 'Failed to save' });
              } finally { setSmtpSaving(false); }
            }} disabled={smtpSaving}
              className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm font-medium">
              <Send size={16} /> {smtpSaving ? 'Saving...' : 'Save Settings'}
            </button>
            <div className="flex items-center gap-2">
              <input type="email" value={smtpTestEmail} onChange={(e) => setSmtpTestEmail(e.target.value)}
                placeholder="test@example.com"
                className="w-52 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
              <button onClick={async () => {
                if (!smtpTestEmail) return;
                setSmtpTesting(true); setSmtpStatus(null);
                try {
                  const res = await testSmtpSettings(smtpTestEmail);
                  setSmtpStatus({ ok: res.success, msg: res.message });
                } catch (e: any) {
                  setSmtpStatus({ ok: false, msg: e?.response?.data?.detail || 'Test failed' });
                } finally { setSmtpTesting(false); }
              }} disabled={smtpTesting || !smtpTestEmail}
                className="flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 text-sm">
                {smtpTesting ? 'Sending...' : 'Test Email'}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* WhatsApp */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <MessageCircle size={20} className="text-primary-600" />
          WhatsApp Notifications (wa.me)
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Set your WhatsApp number (with country code, no + sign) to receive tender alerts directly.
          Clicking "Share on WhatsApp" will open wa.me with a pre-formatted tender message.
        </p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              WhatsApp Number (e.g. 8801712345678)
            </label>
            <div className="flex gap-2">
              <input type="text" value={whatsappPhone} onChange={(e) => setWhatsappPhone(e.target.value.replace(/[^0-9]/g, ''))}
                placeholder="8801712345678"
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
              <button onClick={async () => {
                setWhatsappSaving(true); setWhatsappStatus(null);
                try {
                  const res = await updateWhatsappSettings(whatsappPhone);
                  setWhatsappStatus({ ok: true, msg: 'WhatsApp number saved!' });
                } catch (e: any) {
                  setWhatsappStatus({ ok: false, msg: 'Failed to save' });
                } finally { setWhatsappSaving(false); }
              }} disabled={whatsappSaving}
                className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm font-medium">
                <Smartphone size={16} /> {whatsappSaving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
          {whatsappStatus && (
            <div className={`flex items-start gap-2 text-sm p-3 rounded-lg ${whatsappStatus.ok ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'}`}>
              {whatsappStatus.ok ? <CheckCircle size={16} className="mt-0.5 shrink-0" /> : <XCircle size={16} className="mt-0.5 shrink-0" />}
              <span>{whatsappStatus.msg}</span>
            </div>
          )}
          {whatsappPhone && (
            <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <CheckCircle size={16} className="text-green-500 shrink-0" />
              <span>WhatsApp configured. Go to the <strong>BWDB Monitor</strong> page to share tenders via WhatsApp.</span>
            </div>
          )}
        </div>
      </section>

      {/* System Status */}
      <section className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Server size={20} className="text-primary-600" />
          System
        </h2>
        <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
          <p>Backend API: <code className="text-primary-600">/api/health</code></p>
          <p>27 Agents: <code className="text-primary-600">/api/agents</code></p>
          <p>Pipeline: <code className="text-primary-600">/api/pipeline/phases</code></p>
        </div>
      </section>
    </div>
  );
}
