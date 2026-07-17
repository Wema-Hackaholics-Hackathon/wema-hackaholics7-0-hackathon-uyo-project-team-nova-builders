import { Routes, Route, Navigate } from 'react-router-dom'
import DashboardLayout from './layouts/DashboardLayout.tsx'
import OverviewPage from './pages/dashboard/OverviewPage.tsx'
import MyIdentityPage from './pages/dashboard/MyIdentityPage.tsx'
import VerificationCredentialsPage from './pages/dashboard/VerificationCredentialsPage.tsx'
import ConnectedBankPage from './pages/dashboard/ConnectedBankPage.tsx'
import ConsentPage from './pages/dashboard/ConsentPage.tsx'
import BusinessLedger from './pages/dashboard/BusinessLedgerPage.tsx'
import LedgerHistory from './pages/dashboard/LedgerHistoryPage.tsx'
import AiCreditWallet from './pages/dashboard/AICreditWalletPage.tsx'
import ReportsPage from './pages/dashboard/ReportsPage.tsx'
import ProfileSettingsPage from './pages/dashboard/ProfileSettingsPage.tsx'
import SignupPage from './pages/auth/SignupPage.tsx'
import LoginPage from './pages/auth/LoginPage.tsx'
import ProtectedRoute from './components/ProtectedRoute.tsx'
import LandingPage from './pages/LandingPage.tsx'

export default function App() {
  return (
    <Routes>
      {/* Landing page */}
      <Route path="/" element={<LandingPage />} />

      {/* Auth pages */}
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/login" element={<LoginPage />} />

      <Route path="/dashboard" element={
        <ProtectedRoute>
          <DashboardLayout />
        </ProtectedRoute>
      }>
        <Route index element={<OverviewPage />} />
        <Route path="identity" element={<MyIdentityPage />} />
        <Route path="credentials" element={<VerificationCredentialsPage />} />
        <Route path="banks" element={<ConnectedBankPage />} />
        <Route path="consents" element={<ConsentPage />} />
        <Route path="ledger" element={<BusinessLedger />} />
        <Route path="history" element={<LedgerHistory />} />
        <Route path="wallet" element={<AiCreditWallet />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="settings" element={<ProfileSettingsPage />} />
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
