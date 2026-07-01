import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Link2, LogOut, Settings, Mail, Target, Globe, Menu, X } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const navItems = [
  { to: '/dashboard', label: 'Dashboard', end: true },
  { to: '/domains', label: 'Domains' },
  { to: '/target-sites', label: 'Target Sites', icon: Globe },
  { to: '/campaigns', label: 'Campaigns', icon: Target },
  { to: '/competitors', label: 'Competitors' },
  { to: '/outreach', label: 'Outreach' },
  { to: '/deals', label: 'Deals' },
  { to: '/inbox', label: 'Inbox', icon: Mail },
  { to: '/check-metrics', label: 'Check Metrics' },
]

export default function Layout() {
  const { user, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="min-h-screen">
      <nav className="bg-gray-800 border-b border-gray-700">
        <div className="w-full px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <NavLink to="/" className="flex items-center shrink-0">
              <Link2 className="w-5 h-5 text-pink-500" />
              <span className="ml-2 text-lg font-semibold">BackVora</span>
            </NavLink>

            {/* Desktop Navigation */}
            <div className="hidden md:flex items-center space-x-1 flex-1 ml-10">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `px-3 py-2 rounded-md text-sm font-medium transition-colors flex items-center gap-1 ${
                      isActive ? 'bg-gray-700 text-white' : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                    }`
                  }
                >
                  {item.icon && <item.icon className="w-4 h-4" />}
                  {item.label}
                </NavLink>
              ))}
            </div>

            {/* Desktop User Menu */}
            {user && (
              <div className="hidden md:flex items-center space-x-3 ml-auto">
                <span className="text-sm text-gray-400 truncate max-w-[150px]">{user.name || user.email}</span>
                <NavLink to="/settings" className="text-gray-400 hover:text-white transition-colors" title="Settings">
                  <Settings className="w-4 h-4" />
                </NavLink>
                <button onClick={logout} className="text-gray-400 hover:text-white transition-colors" title="Logout">
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Mobile Menu Button */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-2 text-gray-400 hover:text-white transition-colors"
              aria-label="Toggle menu"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>

          {/* Mobile Menu */}
          {mobileMenuOpen && (
            <div className="md:hidden pb-4 pt-2">
              <div className="space-y-1">
                {navItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    onClick={() => setMobileMenuOpen(false)}
                    className={({ isActive }) =>
                      `block px-3 py-2 rounded-md text-base font-medium transition-colors flex items-center gap-2 ${
                        isActive ? 'bg-gray-700 text-white' : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                      }`
                    }
                  >
                    {item.icon && <item.icon className="w-5 h-5" />}
                    {item.label}
                  </NavLink>
                ))}
              </div>
              {user && (
                <div className="mt-4 pt-4 border-t border-gray-700 space-y-2">
                  <div className="px-3 py-2 text-sm text-gray-400">{user.name || user.email}</div>
                  <NavLink
                    to="/settings"
                    onClick={() => setMobileMenuOpen(false)}
                    className="block px-3 py-2 rounded-md text-base font-medium text-gray-300 hover:bg-gray-700 hover:text-white transition-colors flex items-center gap-2"
                  >
                    <Settings className="w-5 h-5" />
                    Settings
                  </NavLink>
                  <button
                    onClick={() => { logout(); setMobileMenuOpen(false); }}
                    className="w-full text-left px-3 py-2 rounded-md text-base font-medium text-gray-300 hover:bg-gray-700 hover:text-white transition-colors flex items-center gap-2"
                  >
                    <LogOut className="w-5 h-5" />
                    Logout
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </nav>
      <main className="w-full px-4 sm:px-6 lg:px-8 py-4 sm:py-8">
        <Outlet />
      </main>
    </div>
  )
}
