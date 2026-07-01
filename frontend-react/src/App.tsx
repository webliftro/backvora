import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import { ToastProvider } from './components/Toast';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import HomePage from './pages/HomePage';
import DashboardPage from './pages/DashboardPage';
import DomainsPage from './pages/DomainsPage';
import DomainDetailPage from './pages/DomainDetailPage';
import DomainAddPage from './pages/DomainAddPage';
import CompetitorsPage from './pages/CompetitorsPage';
import OutreachPage from './pages/OutreachPage';
import DealsPage from './pages/DealsPage';
import LoginPage from './pages/LoginPage';
import SettingsPage from './pages/SettingsPage';
import CheckMetricsPage from './pages/CheckMetricsPage';
import InboxPage from './pages/InboxPage';
import CampaignsPage from './pages/CampaignsPage';
import CampaignDetailPage from './pages/CampaignDetailPage';
import { TargetSitesListPage, TargetSiteDetailPage } from './pages/TargetSitesPage';

function RequireAuth({ children }: { children: React.ReactElement }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center text-gray-400">Loading...</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AppRoutes() {
  const { user, loading } = useAuth();
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={loading ? null : user ? <Navigate to="/domains" replace /> : <LoginPage />} />

      {/* Protected routes */}
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/domains" element={<DomainsPage />} />
        <Route path="/domains/new" element={<DomainAddPage />} />
        <Route path="/domains/:id" element={<DomainDetailPage />} />
        <Route path="/competitors" element={<CompetitorsPage />} />
        <Route path="/outreach" element={<OutreachPage />} />
        <Route path="/deals" element={<DealsPage />} />
        <Route path="/check-metrics" element={<CheckMetricsPage />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/campaigns" element={<CampaignsPage />} />
        <Route path="/campaigns/:id" element={<CampaignDetailPage />} />
        <Route path="/target-sites" element={<TargetSitesListPage />} />
        <Route path="/target-sites/:id" element={<TargetSiteDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <AppRoutes />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
