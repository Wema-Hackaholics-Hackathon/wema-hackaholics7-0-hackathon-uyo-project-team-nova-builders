import { Navigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import RemixIcon from './RemixIcon'

/** Waits for the session to restore (so a page refresh doesn't bounce to /login), then checks it. */
export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { member, loading } = useAuth()

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center gap-2 text-neutral-400 text-[13px]">
        <RemixIcon name="ri-loader-4-line" size={18} /> Loading console…
      </div>
    )
  }
  if (!member) return <Navigate to="/login" replace />
  if (!member.email_verified) return <Navigate to="/verify-email" replace />
  return <>{children}</>
}
