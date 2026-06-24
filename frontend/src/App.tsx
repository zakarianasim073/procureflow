import { BrowserRouter, Routes, Route, useLocation, Navigate } from 'react-router-dom';
import { lazy, Suspense, useEffect } from 'react';
import Navbar from './components/Navbar';
import Footer from './components/Footer';
import ErrorBoundary from './components/ErrorBoundary';
import Layout from './components/Layout';
import { useAppStore } from './store/appStore';
import './admin.css';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const UploadCompare = lazy(() => import('./pages/UploadCompare'));
const Results = lazy(() => import('./pages/Results'));
const Pricing = lazy(() => import('./pages/Pricing'));
const AIChat = lazy(() => import('./pages/AIChat'));
const Settings = lazy(() => import('./pages/Settings'));
const Terms = lazy(() => import('./pages/Terms'));
const Privacy = lazy(() => import('./pages/Privacy'));
const NotFound = lazy(() => import('./pages/NotFound'));
const DataIntelligence = lazy(() => import('./pages/DataIntelligence'));
const BWDBMonitor = lazy(() => import('./pages/BWDBMonitor'));
const AgentPipeline = lazy(() => import('./pages/AgentPipeline'));
const SLTDashboard = lazy(() => import('./pages/SLTDashboard'));
const PPR2025Dashboard = lazy(() => import('./pages/PPR2025Dashboard'));
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'));
const LiveTenders = lazy(() => import('./pages/LiveTenders'));
const ExecutiveDashboard = lazy(() => import('./pages/ExecutiveDashboard'));
const WatchdogEngineer = lazy(() => import('./pages/WatchdogEngineer'));
const VatTaxCalculator = lazy(() => import('./pages/VatTaxCalculator'));
const TeamManagement = lazy(() => import('./pages/TeamManagement'));
const TenderDocumentAI = lazy(() => import('./pages/TenderDocumentAI'));
const EGPAlerts = lazy(() => import('./pages/EGPAlerts'));
const ClientProfile = lazy(() => import('./pages/ClientProfile'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const PurchaseRequestsPage = lazy(() => import('./pages/PurchaseRequestsPage'));
const PurchaseOrdersPage = lazy(() => import('./pages/PurchaseOrdersPage'));
const VendorsPage = lazy(() => import('./pages/VendorsPage'));
const ApprovalsPage = lazy(() => import('./pages/ApprovalsPage'));
const ContractsPage = lazy(() => import('./pages/ContractsPage'));
const RunningBillsPage = lazy(() => import('./pages/RunningBillsPage'));
const LettersOfCreditPage = lazy(() => import('./pages/LettersOfCreditPage'));

function RouteFallback() {
  return (
    <div className="flex min-h-[320px] items-center justify-center text-sm text-gray-500 dark:text-gray-400">
      Loading...
    </div>
  );
}

function AppLayout() {
  const { theme } = useAppStore();
  const location = useLocation();

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  const isFullPage = ['/terms', '/privacy', '/admin'].some(p => location.pathname.startsWith(p));
  const isAdminRoute = location.pathname.startsWith('/admin');

  return (
    <ErrorBoundary>
      <div className="flex min-h-screen items-stretch bg-gray-50 dark:bg-gray-900">
        {!isFullPage && !isAdminRoute && <Navbar />}
        <main className="flex flex-1 min-h-screen flex-col overflow-y-auto">
          <div className="flex-1">
            <Suspense fallback={<RouteFallback />}>
              <Routes>
                <Route path="/" element={<AgentPipeline />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/upload" element={<UploadCompare />} />
                <Route path="/results" element={<Results />} />
                <Route path="/pricing" element={<Pricing />} />
                <Route path="/chat" element={<AIChat />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/data-intelligence" element={<DataIntelligence />} />
                <Route path="/bwdb-monitor" element={<BWDBMonitor />} />
                <Route path="/agents" element={<AgentPipeline />} />
                <Route path="/tax-calculator" element={<VatTaxCalculator />} />
                <Route path="/team" element={<TeamManagement />} />
                <Route path="/tender-document-ai" element={<TenderDocumentAI />} />
                <Route path="/egp-alerts" element={<EGPAlerts />} />
                <Route path="/slt-dashboard" element={<SLTDashboard />} />
                <Route path="/ppr2025" element={<PPR2025Dashboard />} />
                <Route path="/analytics" element={<AnalyticsPage />} />
                <Route path="/live-tenders" element={<LiveTenders />} />
                <Route path="/executive" element={<ExecutiveDashboard />} />
                <Route path="/watchdog-engineer" element={<WatchdogEngineer />} />
                <Route path="/clients/:tenantId?" element={<ClientProfile />} />
                <Route path="/admin" element={<Layout />}>
                  <Route index element={<Navigate to="/admin/dashboard" replace />} />
                  <Route path="dashboard" element={<DashboardPage />} />
                  <Route path="purchase-requests" element={<PurchaseRequestsPage />} />
                  <Route path="purchase-orders" element={<PurchaseOrdersPage />} />
                  <Route path="vendors" element={<VendorsPage />} />
                  <Route path="approvals" element={<ApprovalsPage />} />
                  <Route path="contracts" element={<ContractsPage />} />
                  <Route path="running-bills" element={<RunningBillsPage />} />
                  <Route path="letters-of-credit" element={<LettersOfCreditPage />} />
                </Route>
                <Route path="/terms" element={<Terms />} />
                <Route path="/privacy" element={<Privacy />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </Suspense>
          </div>
          {!isAdminRoute && <Footer />}
        </main>
      </div>
    </ErrorBoundary>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  );
}
