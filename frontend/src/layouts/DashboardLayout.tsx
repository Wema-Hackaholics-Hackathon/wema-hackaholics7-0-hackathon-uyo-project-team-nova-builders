import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import Sidebar from '@/components/Sidebar.tsx'
import Topbar from '@/components/Topbar.tsx'
import AiChat from '@/components/AiChat.tsx'
import VerificationBanner from '@/components/VerificationBanner.tsx'

export default function DashboardLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar drawerOpen={drawerOpen} onDrawerClose={() => setDrawerOpen(false)} />
      <div className="flex flex-col flex-1 overflow-hidden min-w-0">
        <Topbar onMenuClick={() => setDrawerOpen(true)} />
        <VerificationBanner />
        <main className="flex-1 overflow-y-auto py-8 md:py-12 bg-white px-4 md:px-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              style={{ height: '100%' }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <AiChat />
    </div>
  )
}
