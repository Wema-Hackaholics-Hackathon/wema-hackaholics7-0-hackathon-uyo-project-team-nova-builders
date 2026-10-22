import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
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
import ForgotPasswordPage from './pages/auth/ForgotPasswordPage.tsx'
import ProtectedRoute from './components/ProtectedRoute.tsx'
import LandingPage from './pages/LandingPage.tsx'
import { CredentialProvider } from './contexts/CredentialContext.tsx'

export default function App() {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait">
    <Routes location={location} key={location.pathname}>
      {/* Landing page */}
      <Route path="/" element={<LandingPage />} />

      {/* Auth pages */}
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />

      <Route path="/dashboard" element={
        <ProtectedRoute>
          <CredentialProvider>
            <DashboardLayout />
          </CredentialProvider>
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
    </AnimatePresence>
  )
}
