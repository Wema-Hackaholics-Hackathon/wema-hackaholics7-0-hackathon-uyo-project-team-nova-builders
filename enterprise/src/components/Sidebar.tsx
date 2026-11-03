import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import RemixIcon from './RemixIcon'
import FoidWordmark from './FoidWordmark'
import { useMode } from '@/contexts/ModeContext'
import { useAuth } from '@/contexts/AuthContext'
import { useFetch } from '@/lib/useFetch'
import { CreateBusiness } from '@/pages/AccountPage'

/* ── Design tokens ──────────────────────────────────────────────────── */
const SIDEBAR_BG   = '#F5F5F5'
const BRAND_ACTIVE = '#c026d3'   // brand-500
const BRAND_BG     = '#fae8ff'   // brand-100
const MUTED        = '#a1a1aa'   // neutral-400
const TEXT         = '#18181b'   // neutral-900

const COLLAPSED_W = 56

const NAV_ITEMS = [
  { to: '/',          icon: 'ri-dashboard-fill',     label: 'Overview'            },
  { to: '/users',     icon: 'ri-group-line',         label: 'Users', badge: true },
  { to: '/api-keys',  icon: 'ri-key-2-line',         label: 'API keys & webhooks' },
  { to: '/apps',      icon: 'ri-login-circle-line',  label: 'Sign-in apps'        },
  { to: '/logs',      icon: 'ri-terminal-box-line',  label: 'Request logs'        },
  { to: '/billing',   icon: 'ri-file-list-3-line',   label: 'Usage & Billing'     },
  { to: '/team',      icon: 'ri-team-line',          label: 'Team'                },
  { to: '/settings',  icon: 'ri-settings-3-line',    label: 'Settings'            },
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
  const { org, mode } = useMode()
  const users = useFetch<{ counts: { all: number } }>(org ? `/business/organisations/${org.id}/users?env=${mode}&limit=1` : null)
  const userCount = users.data?.counts.all
  const { pathname } = useLocation()
  const reloadUsers = users.reload
  useEffect(() => { void reloadUsers() }, [pathname, reloadUsers])   // keep the badge fresh as you move around
  const handleLogout = () => { void logout().then(() => navigate('/login')) }

  return (
    <div className="flex flex-col flex-1 overflow-y-auto">
      <nav className="flex-1 flex flex-col gap-2 py-4">
        {NAV_ITEMS.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
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
                {item.badge && !collapsed && (
                  <span className="ml-auto text-[11px] font-semibold text-neutral-400 bg-neutral-200 rounded-full px-2 py-0.5">{userCount?.toLocaleString() ?? '–'}</span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Logout */}
      <div>
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
/* ── Org switcher + Test / Live toggle (hidden when collapsed) ────────── */
function OrgHeader() {
  const { orgs, org, selectOrg, mode, setMode, liveUnlocked } = useMode()
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const navigate = useNavigate()
  const pick = (m: 'test' | 'live') => {
    if (m === 'live' && !liveUnlocked) { navigate('/go-live'); return }   // documents first
    setMode(m)
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <button onClick={() => setOpen(o => !o)} aria-expanded={open}
          className="w-full flex items-center gap-2.5 p-2 rounded-xl border-2 text-left" style={{ borderColor: BRAND_ACTIVE, background: BRAND_BG }}>
          <span className="w-8 h-8 rounded-lg bg-white flex items-center justify-center text-[14px] font-bold shrink-0" style={{ color: BRAND_ACTIVE }}>
            {org?.name.slice(0, 1).toUpperCase() ?? '·'}
          </span>
          <span className="flex-1 min-w-0 leading-tight">
            <span className="block text-[14px] font-semibold text-neutral-900 truncate">{org?.name ?? 'Loading…'}</span>
            <span className="block text-[10px] text-neutral-500">{org ? `${org.plan} plan` : ''}</span>
          </span>
          <RemixIcon name="ri-expand-up-down-line" size={18} color={BRAND_ACTIVE} />
        </button>
        {open && (
          <div className="absolute z-20 left-0 right-0 mt-1 bg-white rounded-xl shadow-lg border border-neutral-200 py-1">
            {orgs.map(o => (
              <button key={o.id} onClick={() => { selectOrg(o.id); setOpen(false); navigate('/') }}
                className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-[13px] hover:bg-neutral-50">
                <span className="truncate font-medium">{o.name}</span>
                <span className="text-[11px] text-neutral-400 capitalize">{o.id === org?.id ? '✓ ' : ''}{o.role}</span>
              </button>
            ))}
            <button onClick={() => { setOpen(false); setCreating(true) }}
              className="w-full flex items-center gap-2 px-3 py-2 text-left text-[13px] font-semibold text-[#c026d3] hover:bg-neutral-50 border-t border-neutral-100">
              <RemixIcon name="ri-add-line" size={15} /> Create another business
            </button>
          </div>
        )}
      </div>
      {creating && <CreateBusiness onClose={() => { setCreating(false); navigate('/') }} />}
      <div className="grid grid-cols-2 p-1 rounded-full bg-neutral-200/70">
        {(['test', 'live'] as const).map(m => (
          <button key={m} onClick={() => pick(m)}
            title={m === 'live' && !liveUnlocked ? 'Submit your business documents to go live' : undefined}
            className={`flex items-center justify-center gap-1 py-1.5 rounded-full text-[12px] font-semibold transition-colors ${mode === m ? 'text-white' : 'text-neutral-400'}`}
            style={mode === m ? { background: m === 'test' ? '#f97316' : BRAND_ACTIVE } : undefined}>
            {m === 'live' && !liveUnlocked && <RemixIcon name="ri-lock-line" size={12} />}
            {m === 'test' ? 'Test Mode' : 'Live'}
          </button>
        ))}
      </div>
    </div>
  )
}

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
        {!collapsed && <OrgHeader />}
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
        <OrgHeader />
        <NavList collapsed={false} onLinkClick={onDrawerClose} />
      </aside>
    </>
  )
}
