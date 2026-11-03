import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import RemixIcon from './RemixIcon'
import FoidWordmark from './FoidWordmark'
import { useAuth } from '../contexts/AuthContext'
import { docsLink } from '../lib/docs'

/* ── Design tokens ──────────────────────────────────────────────────── */
const SIDEBAR_BG   = '#F5F5F5'
const BRAND_ACTIVE = '#c026d3'   // brand-500
const BRAND_BG     = '#fae8ff'   // brand-100
const MUTED        = '#a1a1aa'   // neutral-400
const TEXT         = '#18181b'   // neutral-900

const COLLAPSED_W = 56

const NAV_ITEMS = [
  { to: '/dashboard',             icon: 'ri-dashboard-fill',    label: 'Overview'                 },
  { to: '/dashboard/identity',    icon: 'ri-fingerprint-line',  label: 'My Identity'              },
  { to: '/dashboard/banks',       icon: 'ri-bank-line',         label: 'Connected Banks'          },
  { to: '/dashboard/credentials', icon: 'ri-draft-line',        label: 'Verification Credentials' },
  { to: '/dashboard/consents',    icon: 'ri-file-list-3-line',  label: 'Consent Requests'         },
  { to: '/dashboard/ledger',      icon: 'ri-store-2-fill',      label: 'Business Ledger'          },
  { to: '/dashboard/history',     icon: 'ri-history-fill',      label: 'Ledger History'           },
  { to: '/dashboard/wallet',      icon: 'ri-quill-pen-line',    label: 'AI Credit Wallet'         },
  { to: '/dashboard/reports',     icon: 'ri-customer-service-2-fill', label: 'Reports & Insights' },
  { to: '/dashboard/settings',    icon: 'ri-settings-3-line',   label: 'Profile & Settings'       },
]

/* Label fade helper — used for the desktop collapse animation */
const labelStyle = (collapsed: boolean): React.CSSProperties => ({
  maxWidth: collapsed ? 0 : 160,
  opacity: collapsed ? 0 : 1,
  overflow: 'hidden',
  whiteSpace: 'nowrap',
  transition: 'max-width 220ms ease, opacity 180ms ease, margin 220ms ease',
})

/* ── Shared nav list ─────────────────────────────────────────────────── */
function NavList({
  collapsed,
  onLinkClick,
}: {
  collapsed: boolean
  onLinkClick?: () => void
}) {
  const navigate = useNavigate()
  const { logout } = useAuth()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex flex-col flex-1 overflow-y-auto">
      <nav className="flex-1 flex flex-col gap-2 py-4">
        {NAV_ITEMS.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/dashboard'}
            title={collapsed ? item.label : undefined}
            onClick={onLinkClick}
            className={({ isActive }) =>
              [
                'flex items-center gap-2.5 rounded-lg transition-colors',
                collapsed ? 'justify-center px-0 py-2' : 'px-3 py-2.5',
                isActive ? '' : 'hover:bg-neutral-200 hover:text-neutral-800',
              ].join(' ')
            }
            style={({ isActive }) =>
              isActive
                ? { background: collapsed ? 'transparent' : BRAND_BG, color: BRAND_ACTIVE }
                : { color: '#B2B2B2' }
            }
          >
            {({ isActive }) => (
              <>
                <RemixIcon name={item.icon} size={20} clickable />
                <span
                  className={`text-[14px] ${isActive ? 'font-semibold' : 'font-medium'}`}
                  style={collapsed ? labelStyle(true) : { whiteSpace: 'nowrap' }}
                >
                  {item.label}
                </span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Help centre (opens the docs site) + Logout */}
      <div className="flex flex-col gap-1">
        <a
          href={docsLink('/help/')}
          target="_blank"
          rel="noreferrer"
          title={collapsed ? 'Help centre' : undefined}
          className={[
            'flex items-center gap-2.5 rounded-lg transition-colors hover:bg-neutral-200 hover:text-neutral-800',
            collapsed ? 'justify-center px-0 py-2' : 'px-3 py-2',
          ].join(' ')}
          style={{ color: '#B2B2B2' }}
        >
          <RemixIcon name="ri-question-line" size={20} clickable />
          <span className="text-[13px] font-medium" style={collapsed ? labelStyle(true) : { whiteSpace: 'nowrap' }}>
            Help centre
          </span>
        </a>
        <button
          onClick={handleLogout}
          title={collapsed ? 'Logout' : undefined}
          className={[
            'flex items-center gap-2.5 rounded-lg text-red-500 hover:bg-red-50 transition-colors w-full',
            collapsed ? 'justify-center px-0 py-2' : 'px-3 py-2',
          ].join(' ')}
        >
          <RemixIcon name="ri-logout-box-line" size={20} color="#ef4444" clickable />
          <span
            className="text-[13px] font-medium"
            style={collapsed ? labelStyle(true) : { whiteSpace: 'nowrap' }}
          >
            Logout
          </span>
        </button>
      </div>
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════════════
   Main Sidebar
   - Desktop: persistent, collapsible icon rail
   - Mobile: hidden; slides in from left as a drawer with dark overlay
═══════════════════════════════════════════════════════════════════════ */
interface SidebarProps {
  drawerOpen: boolean
  onDrawerClose: () => void
}

export default function Sidebar({ drawerOpen, onDrawerClose }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false)

  /* Close drawer on any nav (already handled via onLinkClick), but also
     lock body scroll while drawer is open on mobile */
  useEffect(() => {
    if (drawerOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => { document.body.style.overflow = '' }
  }, [drawerOpen])

  /* ── Shared logo header ── */
  const LogoHeader = ({ showCollapse }: { showCollapse: boolean }) => (
    <div
      className="flex items-center"
      style={{
        justifyContent: collapsed && showCollapse ? 'center' : 'flex-start',
        gap: collapsed && showCollapse ? 0 : 8,
        transition: 'gap 220ms ease',
        paddingBottom: 16,
      }}
    >
      <img
        src="/logo.png"
        alt="FOID logo"
        style={{
          width: 28,
          height: 32,
          objectFit: 'contain',
          flexShrink: 0,
          display: 'block',
          ...(showCollapse ? labelStyle(collapsed) : {}),
        }}
      />
      {(!collapsed || !showCollapse) && (
        <FoidWordmark color={TEXT} height={20} />
      )}
      {showCollapse && (
        <RemixIcon
          name="ri-layout-left-line"
          size={20}
          color={MUTED}
          clickable
          onClick={() => setCollapsed(prev => !prev)}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="p-1 rounded hover:bg-neutral-200 transition-colors"
          style={{ marginLeft: collapsed ? 0 : 'auto' }}
        />
      )}
      {!showCollapse && (
        <button
          onClick={onDrawerClose}
          className="ml-auto p-1 rounded hover:bg-neutral-200 transition-colors"
          aria-label="Close menu"
        >
          <RemixIcon name="ri-close-line" size={22} color={MUTED} clickable />
        </button>
      )}
    </div>
  )

  return (
    <>
      {/* ── DESKTOP sidebar (hidden on mobile) ── */}
      <aside
        style={{
          width: collapsed ? COLLAPSED_W : undefined,
          minWidth: collapsed ? COLLAPSED_W : undefined,
          background: SIDEBAR_BG,
          transition: 'width 220ms ease, min-width 220ms ease',
        }}
        className="hidden md:flex shrink-0 flex-col overflow-y-auto overflow-x-hidden p-4"
      >
        <LogoHeader showCollapse={true} />
        <NavList collapsed={collapsed} />
      </aside>

      {/* ── MOBILE overlay backdrop ── */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          style={{ background: 'rgba(0,0,0,0.45)' }}
          onClick={onDrawerClose}
          aria-hidden="true"
        />
      )}

      {/* ── MOBILE drawer ── */}
      <aside
        className="fixed top-0 left-0 h-full z-50 flex flex-col p-4 md:hidden"
        style={{
          width: 272,
          background: SIDEBAR_BG,
          transform: drawerOpen ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 280ms cubic-bezier(.4,0,.2,1)',
          boxShadow: drawerOpen ? '4px 0 24px rgba(0,0,0,0.18)' : 'none',
          overflowY: 'auto',
        }}
        aria-label="Mobile navigation"
      >
        <LogoHeader showCollapse={false} />
        <NavList collapsed={false} onLinkClick={onDrawerClose} />
      </aside>
    </>
  )
}
