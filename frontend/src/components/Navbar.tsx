import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Upload, FileSpreadsheet, MessageSquare,
  Settings, LogIn, LogOut, Moon, Sun, Cpu, DollarSign,
  Database, AlertTriangle, GitBranch, BarChart3, Shield, TrendingUp, FolderTree,
  Bell, FileText, Users
} from 'lucide-react';
import { useAppStore } from '../store/appStore';

export default function Navbar() {
  const navigate = useNavigate();
  const { theme, setTheme, auth, logout } = useAppStore();
  const navItems = [
    { to: '/', icon: GitBranch, label: 'Agents' },
    { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/executive', icon: Cpu, label: 'Executive' },
    { to: '/live-tenders', icon: FolderTree, label: 'Live Tenders' },
    { to: '/egp-alerts', icon: Bell, label: 'eGP Alerts' },
    { to: '/tender-document-ai', icon: FileText, label: 'Tender Doc AI' },
    { to: '/slt-dashboard', icon: BarChart3, label: 'SLT Dashboard' },
    { to: '/ppr2025', icon: Shield, label: 'PPR 2025' },
    { to: '/analytics', icon: TrendingUp, label: 'Analytics' },
    { to: '/tax-calculator', icon: DollarSign, label: 'VAT / Tax' },
    { to: '/upload', icon: Upload, label: 'Upload' },
    { to: '/results', icon: FileSpreadsheet, label: 'Results' },
    { to: '/chat', icon: MessageSquare, label: 'AI Chat' },
    { to: '/data-intelligence', icon: Database, label: 'Data Intel' },
    { to: '/bwdb-monitor', icon: AlertTriangle, label: 'BWDB Monitor' },
    { to: '/watchdog-engineer', icon: Shield, label: 'Watchdog & Engineer' },
    { to: '/clients', icon: Users, label: 'Clients' },
    { to: '/team', icon: Users, label: 'Team' },
    { to: '/admin/dashboard', icon: BarChart3, label: 'Admin' },
    { to: '/settings', icon: Settings, label: 'Settings' },
  ];

  return (
    <nav className="sticky top-0 h-screen w-64 shrink-0 overflow-y-auto bg-white border-r border-gray-200 flex flex-col dark:bg-gray-800 dark:border-gray-700">
      {/* Logo */}
      <div className="p-5 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-start gap-3">
          <div className="relative mt-0.5">
            <div className="absolute inset-0 rounded-2xl bg-primary-400/20 blur-xl" />
            <div className="relative flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-primary-500 via-cyan-500 to-emerald-500 text-white shadow-lg shadow-primary-500/20">
              <Cpu size={22} />
            </div>
          </div>
          <div className="brand-stack">
            <div className="brand-title">ProcureFlow</div>
            <div className="brand-handle">@zmnasim73</div>
            <div className="text-xs text-gray-400">a Procurement intelligence System</div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex-1 py-4 px-3 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50'
              }`
            }
          >
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
      </div>

      {/* Bottom actions */}
      <div className="p-3 border-t border-gray-200 dark:border-gray-700 space-y-2">
        {auth.user ? (
          <div className="flex items-center gap-2 px-3 py-2">
            <div className="w-7 h-7 rounded-full bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400 flex items-center justify-center text-xs font-bold">
              {auth.user.name?.charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-gray-900 dark:text-white truncate">
                {auth.user.name}
              </div>
              <div className="text-xs text-gray-400">{auth.user.plan}</div>
            </div>
            <button
              onClick={() => { logout(); navigate('/'); }}
              className="text-gray-400 hover:text-red-500 transition-colors"
              title="Logout"
            >
              <LogOut size={16} />
            </button>
          </div>
        ) : (
          <button
            onClick={() => navigate('/settings')}
            className="flex items-center gap-2 px-3 py-2 w-full text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg transition-colors"
          >
            <LogIn size={18} />
            Owner Login
          </button>
        )}

        {/* Theme toggle */}
        <button
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className="flex items-center gap-3 px-3 py-2 w-full text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-lg transition-colors"
        >
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
        </button>
      </div>
    </nav>
  );
}
