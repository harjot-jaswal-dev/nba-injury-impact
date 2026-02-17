import { NavLink } from 'react-router-dom'
import { Activity, LogOut, User } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

const navLinks = [
  { to: '/', label: 'Dashboard' },
  { to: '/simulator', label: 'Injury Simulator' },
  { to: '/chat', label: 'Chat' },
]

export default function Navbar() {
  const { user, loading, login, logout } = useAuth()

  return (
    <nav className="bg-slate-800 border-b border-slate-700 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <Activity className="w-6 h-6 text-blue-500" />
          <span className="text-lg font-bold text-slate-100 hidden sm:inline">
            NBA Injury Analyzer
          </span>
        </div>

        {/* Nav Links */}
        <div className="flex items-center gap-1">
          {navLinks.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'text-blue-400 bg-slate-700/50'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-700/30'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </div>

        {/* Auth */}
        <div className="flex items-center gap-3">
          {loading ? (
            <div className="w-20 h-8 bg-slate-700 rounded-lg animate-pulse" />
          ) : user ? (
            <>
              <div className="flex items-center gap-2 text-sm text-slate-300">
                <div className="w-7 h-7 rounded-full bg-blue-500/20 flex items-center justify-center">
                  <User className="w-4 h-4 text-blue-400" />
                </div>
                <span className="hidden md:inline">{user.email}</span>
              </div>
              <button
                onClick={logout}
                className="text-slate-400 hover:text-slate-100 transition-colors p-1.5 rounded-lg hover:bg-slate-700/50"
                title="Logout"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </>
          ) : (
            <button onClick={login} className="btn-primary text-sm py-1.5 px-3">
              Sign in with Google
            </button>
          )}
        </div>
      </div>
    </nav>
  )
}
