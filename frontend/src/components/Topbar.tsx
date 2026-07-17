import RemixIcon from './RemixIcon'
import { useAuth } from '../contexts/AuthContext'

export default function Topbar({ onMenuClick }: { onMenuClick?: () => void }) {
  const { user } = useAuth()

  const userDisplayName = user ? `${user.firstName} ${user.lastName}` : 'User'

  return (
    <header className="shrink-0 bg-white border-neutral-100 border-b font-bold flex items-center text-[16px] px-4 md:px-8 py-3.5 gap-4">
      {/* Mobile menu button */}
      {onMenuClick && (
        <button
          onClick={onMenuClick}
          aria-label="Open menu"
          className="md:hidden p-2 rounded-lg hover:bg-neutral-100 transition-colors"
        >
          <RemixIcon name="ri-menu-line" size={24} color="#18181b" clickable />
        </button>
      )}

      {/* Search - hidden on mobile */}
      <div className="relative flex-1 max-w-[500px] hidden md:flex justify-center py-2">
        <RemixIcon name="ri-search-fill" size={20} color="#a1a1aa" className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
        <input
          type="text"
          placeholder="Search your credentials, banks, transactions"
          aria-label="Search"
          className="w-full pl-11 pr-4 py-2 rounded-full bg-neutral-100 text-neutral-800 placeholder:text-neutral-400 focus:outline-none focus:border-brand-400"
        />
      </div>

      {/* Actions */}
      <div className="ml-auto flex items-center gap-3">
        {/* Bell */}
        <button
          aria-label="Notifications"
          className="w-10 h-10 rounded-full p-3 bg-neutral-100  flex items-center justify-center hover:bg-neutral-200 transition-colors"
        >
			<div className='relative'>
				<RemixIcon name="ri-notification-3-fill" size={16} color="#000000" clickable />
          		<span className="absolute top-1 right-0 w-2 h-2 rounded-full bg-brand-400 border-2 border-white" />
			</div>
        </button>

        {/* User chip - simplified on mobile */}
        <div className="flex items-center gap-2 pl-4 py-1 border-neutral-100 border-l bg-white">
          <img
            src="/avatar.png"
            alt={userDisplayName}
            className="w-8 h-8 md:w-10 md:h-10 rounded-full object-cover"
          />
          <div className="leading-tight gap-1.5 hidden md:block">
            <div className="text-[16px] font-semibold text-neutral-900">{userDisplayName}</div>
            <div className="bg-[#fae8ff] max-w-max px-4 rounded-full py-1.5 text-[12px] font-bold text-brand-500">Verified</div>
          </div>
        </div>
      </div>
    </header>
  )
}
