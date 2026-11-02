import { useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import Sidebar from '@/components/Sidebar.tsx'
import Topbar from '@/components/Topbar.tsx'
import RemixIcon from '@/components/RemixIcon'
import { useMode } from '@/contexts/ModeContext'
import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/ui'
import { api, apiErrorMessage } from '@/lib/api'

/** Replaces the page when the business can't be used right now (deactivated, or 2FA required). */
function Gate() {
  const { org, can, reloadOrgs } = useMode()
  const { member } = useAuth()
  const [err, setErr] = useState('')
  if (org?.status === 'suspended') {
    const until = org.deactivated_at ? new Date(new Date(org.deactivated_at).getTime() + 30 * 864e5).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : ''
    return (
      <div className="max-w-[560px] flex flex-col gap-3">
        <h1 className="text-[26px] font-bold">{org.name} is deactivated</h1>
        <p className="text-[14px] text-neutral-600">API access and webhooks are off. Everything is deleted on {until} unless an owner reactivates it.</p>
        {can('owner') ? <div><Button onClick={() => void api.post(`/business/organisations/${org.id}/reactivate`).then(reloadOrgs).catch(e => setErr(apiErrorMessage(e)))}>Reactivate</Button></div>
          : <p className="text-[13px] text-neutral-500">Ask an owner to reactivate it.</p>}
        {err && <p className="text-[13px] text-red-500">{err}</p>}
      </div>
    )
  }
  if (org?.require_2fa && !member?.two_factor_enabled) {
    return (
      <div className="max-w-[560px] flex flex-col gap-3">
        <h1 className="text-[26px] font-bold">Turn on two-step sign-in</h1>
        <p className="text-[14px] text-neutral-600">{org.name} requires two-step sign-in for everyone on the team. It takes a minute with an authenticator app.</p>
        <div><Link to="/account" className="inline-flex px-5 py-2.5 rounded-full text-white text-[14px] font-semibold bg-[#C800DE]">Set it up in My account</Link></div>
      </div>
    )
  }
  return null
}

/** Orange strip shown in Test mode so nobody mistakes sandbox data for real users. */
function TestModeBanner() {
  const { mode, liveUnlocked, kyb } = useMode()
  if (mode !== 'test') return null
  return (
    <div className="shrink-0 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 px-4 py-2 bg-orange-50 border-b border-orange-200 text-[12.5px] text-orange-700">
      <RemixIcon name="ri-flask-line" size={15} />
      <span><b>Test mode</b> — sandbox data and test keys only. No real users, no charges.</span>
      {!liveUnlocked && (
        <Link to="/go-live" className="font-semibold underline underline-offset-2">
          {kyb === 'pending' ? 'Documents in review' : 'Submit documents to go live'}
        </Link>
      )}
    </div>
  )
}

export default function DashboardLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const { mode, org } = useMode()
  const { member } = useAuth()
  const location = useLocation()
  const blocked = location.pathname !== '/account'
    && (org?.status === 'suspended' || (!!org?.require_2fa && !member?.two_factor_enabled))

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar drawerOpen={drawerOpen} onDrawerClose={() => setDrawerOpen(false)} />
      <div className="flex flex-col flex-1 overflow-hidden min-w-0">
        <Topbar onMenuClick={() => setDrawerOpen(true)} />
        <TestModeBanner />
        <main className="flex-1 overflow-y-auto py-8 md:py-12 bg-white px-4 md:px-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname + mode}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              style={{ height: '100%' }}
            >
              {blocked ? <Gate /> : <Outlet />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  )
}
