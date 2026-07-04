import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import {
  Link2, LogOut, Settings, Menu, X, LayoutDashboard, Globe, Crosshair,
  Target, Radar, Send, Handshake, Inbox, Gauge, type LucideIcon,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

interface NavItem { to: string; label: string; icon: LucideIcon; end?: boolean }
interface NavGroup { label: string | null; items: NavItem[] }

const navGroups: NavGroup[] = [
  {
    label: null,
    items: [{ to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, end: true }],
  },
  {
    label: 'Inventory',
    items: [
      { to: '/domains', label: 'Domains', icon: Globe },
      { to: '/target-sites', label: 'Target Sites', icon: Crosshair },
    ],
  },
  {
    label: 'Pipeline',
    items: [
      { to: '/campaigns', label: 'Campaigns', icon: Target },
      { to: '/competitors', label: 'Competitors', icon: Radar },
      { to: '/outreach', label: 'Outreach', icon: Send },
      { to: '/deals', label: 'Deals', icon: Handshake },
      { to: '/inbox', label: 'Inbox', icon: Inbox },
    ],
  },
  {
    label: 'Tools',
    items: [{ to: '/check-metrics', label: 'Check Metrics', icon: Gauge }],
  },
]

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return `relative flex items-center gap-2.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
    isActive
      ? 'bg-gray-700 text-white font-medium'
      : 'text-gray-400 hover:bg-gray-700/50 hover:text-gray-200'
  }`
}

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth()
  return (
    <div className="flex flex-col h-full">
      <NavLink to="/" onClick={onNavigate} className="brand-logo flex items-center gap-2 px-4 h-14 shrink-0">
        <span className="brand-logo-mark flex items-center justify-center w-7 h-7">
          <Link2 className="brand-logo-icon w-5 h-5 text-pink-500" />
        </span>
        <span className="brand-logo-word text-[15px] font-semibold tracking-tight">BackVora</span>
      </NavLink>

      <nav className="flex-1 overflow-y-auto px-2 pb-4 space-y-4">
        {navGroups.map((group) => (
          <div key={group.label ?? 'root'}>
            {group.label && (
              <div className="px-3 pb-1.5 pt-1 text-[11px] font-medium uppercase tracking-wider text-gray-500">
                {group.label}
              </div>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.end} onClick={onNavigate} className={navLinkClass}>
                  <item.icon className="w-5 h-5 shrink-0" />
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="shrink-0 border-t border-gray-700 px-2 py-3 space-y-0.5">
        <NavLink to="/settings" onClick={onNavigate} className={navLinkClass}>
          <Settings className="w-5 h-5 shrink-0" />
          Settings
        </NavLink>
        {user && (
          <div className="flex items-center gap-2 px-3 pt-2">
            <span className="flex-1 text-xs text-gray-500 truncate" title={user.email}>
              {user.name || user.email}
            </span>
            <button
              onClick={() => { logout(); onNavigate?.() }}
              className="p-1.5 rounded-md text-gray-400 hover:bg-gray-700/50 hover:text-gray-200 transition-colors"
              title="Logout"
              aria-label="Logout"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Layout() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const closeDrawer = () => setDrawerOpen(false)

  return (
    <div className="min-h-screen">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex flex-col fixed inset-y-0 left-0 w-60 bg-gray-800 border-r border-gray-700 z-40">
        <SidebarNav />
      </aside>

      {/* Mobile / tablet top bar */}
      <header className="lg:hidden sticky top-0 z-40 flex items-center gap-2 h-14 px-4 glass border-b border-gray-700">
        <button
          onClick={() => setDrawerOpen(true)}
          className="p-2 -ml-2 rounded-md text-gray-400 hover:text-gray-200 transition-colors"
          aria-label="Open menu"
        >
          <Menu className="w-5 h-5" />
        </button>
        <NavLink to="/" className="brand-logo flex items-center gap-2">
          <span className="brand-logo-mark flex items-center justify-center w-7 h-7">
            <Link2 className="brand-logo-icon w-5 h-5 text-pink-500" />
          </span>
          <span className="brand-logo-word text-[15px] font-semibold tracking-tight">BackVora</span>
        </NavLink>
      </header>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="lg:hidden fixed inset-0 z-50" role="dialog" aria-label="Navigation menu">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={closeDrawer} />
          <div className="absolute inset-y-0 left-0 w-64 max-w-[85vw] glass border-r border-gray-700">
            <button
              onClick={closeDrawer}
              className="absolute top-3 right-3 p-2 rounded-md text-gray-400 hover:text-gray-200 transition-colors"
              aria-label="Close menu"
            >
              <X className="w-5 h-5" />
            </button>
            <SidebarNav onNavigate={closeDrawer} />
          </div>
        </div>
      )}

      <main className="lg:pl-60">
        <div className="px-4 sm:px-6 lg:px-8 py-5 sm:py-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
