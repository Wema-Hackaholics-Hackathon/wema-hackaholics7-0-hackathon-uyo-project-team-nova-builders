import { Navigate, Route, Routes } from 'react-router-dom'
import DashboardLayout from '@/layouts/DashboardLayout'
import OverviewPage from '@/pages/OverviewPage'
import UsersPage from '@/pages/UsersPage'
import ApiKeysPage from '@/pages/ApiKeysPage'
import AppsPage from '@/pages/AppsPage'
import RequestLogsPage from '@/pages/RequestLogsPage'
import BillingPage from '@/pages/BillingPage'
import TeamPage from '@/pages/TeamPage'
import SettingsPage from '@/pages/SettingsPage'
import GoLivePage from '@/pages/GoLivePage'
import ProtectedRoute from '@/components/ProtectedRoute'
import LoginPage from '@/pages/auth/LoginPage'
import SignupPage from '@/pages/auth/SignupPage'
import VerifyEmailPage from '@/pages/auth/VerifyEmailPage'
import ForgotPasswordPage from '@/pages/auth/ForgotPasswordPage'
import AcceptInvitePage from '@/pages/auth/AcceptInvitePage'
import AccountPage from '@/pages/AccountPage'

export default function App() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route path="signup" element={<SignupPage />} />
      <Route path="verify-email" element={<VerifyEmailPage />} />
      <Route path="forgot-password" element={<ForgotPasswordPage />} />
      <Route path="invite/:token" element={<AcceptInvitePage />} />
      <Route element={<ProtectedRoute><DashboardLayout /></ProtectedRoute>}>
        <Route index element={<OverviewPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="api-keys" element={<ApiKeysPage />} />
        <Route path="apps" element={<AppsPage />} />
        <Route path="logs" element={<RequestLogsPage />} />
        <Route path="billing" element={<BillingPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="go-live" element={<GoLivePage />} />
        <Route path="account" element={<AccountPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
