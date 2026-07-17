import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import RemixIcon from './RemixIcon'

/* ── Design tokens ──────────────────────────────────────────────────── */
const SIDEBAR_BG   = '#F5F5F5'
const BRAND_ACTIVE = '#c026d3'   // brand-500
const BRAND_BG     = '#fae8ff'   // brand-100
const MUTED        = '#a1a1aa'   // neutral-400
const TEXT         = '#18181b'   // neutral-900

const COLLAPSED_W = 56

const NAV_ITEMS = [
  { to: '/dashboard',             icon: 'ri-dashboard-line',    label: 'Overview'                 },
  { to: '/dashboard/identity',    icon: 'ri-fingerprint-line',  label: 'My Identity'              },
  { to: '/dashboard/banks',       icon: 'ri-bank-line',         label: 'Connected Banks'          },
  { to: '/dashboard/credentials', icon: 'ri-draft-line', label: 'Verification Credentials' },
  { to: '/dashboard/consents',    icon: 'ri-file-list-3-line',  label: 'Consent Requests'         },
  { to: '/dashboard/ledger',      icon: 'ri-store-2-line',    label: 'Business Ledger'          },
  { to: '/dashboard/history',     icon: 'ri-history-fill',      label: 'Ledger History'           },
  { to: '/dashboard/wallet',      icon: 'ri-quill-pen-line',       label: 'AI Credit Wallet'         },
  { to: '/dashboard/reports',     icon: 'ri-customer-service-2-fill',    label: 'Reports & Insights'       },
  { to: '/dashboard/settings',    icon: 'ri-settings-3-line',   label: 'Profile & Settings'       },
]

/* Inline transition for label text — always in DOM, fades + clips */
const labelStyle = (collapsed: boolean): React.CSSProperties => ({
  maxWidth: collapsed ? 0 : 160,
  opacity: collapsed ? 0 : 1,
  overflow: 'hidden',
  whiteSpace: 'nowrap',
  transition: 'max-width 220ms ease, opacity 180ms ease, margin 220ms ease',
})

export default function Sidebar() {
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)

  return (
    <aside
      style={{
        width: collapsed ? COLLAPSED_W : undefined,
        minWidth: collapsed ? COLLAPSED_W : undefined,
        background: SIDEBAR_BG,
        transition: 'width 220ms ease, min-width 220ms ease',
      }}
      className="shrink-0 flex flex-col overflow-y-auto overflow-x-hidden p-4"
    >
      {/* ── Header: logo + "FOID" + collapse toggle ── */}
      <div
        className="flex items-center"
        style={{
          justifyContent: collapsed ? 'center' : 'flex-start',
          gap: collapsed ? 0 : 1.5,
          transition: 'gap 220ms ease',
                  paddingBottom: 16
        }}
      >
        {/* Logo image — always visible */}
        <img
          src="/logo.png"
          alt="FOID logo"
          style={{
            width: 28,
            height: 32,
            objectFit: 'contain',
            flexShrink: 0,
            display: 'block',
                        ...labelStyle(collapsed),
          }}
        />

        {/* Brand name — fades out when collapsed */}
        <span
          style={{
            fontFamily: "'Neue Machina', sans-serif",
            fontWeight: 800,
            fontSize: 20,
            color: TEXT,
            letterSpacing: '-0.3px',
            ...labelStyle(collapsed),
          }}
        >
          FOID
        </span>

        {/* Toggle — pushed right when expanded, invisible space when collapsed */}
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
      </div>

      {/* ── Nav ── */}
      <nav
        className="flex-1 flex flex-col gap-2"
        style={{
          paddingBottom: 16,
          paddingTop: 16,
                  transition: 'padding 220ms ease',
        }}
      >
        {NAV_ITEMS.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/dashboard'}
            title={collapsed ? item.label : undefined}
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
                  style={labelStyle(collapsed)}
                >
                  {item.label}
                </span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* ── Logout ── */}
      <div
        style={{
          transition: 'padding 220ms ease',
        }}
      >
        <button
          onClick={() => navigate('/')}
          title={collapsed ? 'Logout' : undefined}
          className={[
            'flex items-center gap-2.5 rounded-lg text-red-500 hover:bg-red-50 transition-colors w-full',
            collapsed ? 'justify-center px-0 py-2' : 'px-3 py-2',
          ].join(' ')}
        >
          <RemixIcon name="ri-logout-box-r-line" size={20} color="#ef4444" clickable />
          <span
            className="text-[13px] font-medium"
            style={labelStyle(collapsed)}
          >
            Logout
          </span>
        </button>
      </div>
    </aside>
  )
}
