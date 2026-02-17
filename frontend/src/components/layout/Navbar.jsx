import { NavLink } from 'react-router-dom'
import { LogOut, User } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

const navLinks = [
  { to: '/', label: 'Dashboard' },
  { to: '/simulator', label: 'Injury Simulator' },
  { to: '/chat', label: 'Chat' },
]

export default function Navbar() {
  const { user, loading, login, logout } = useAuth()

  return (
    <nav
      className="sticky top-0 z-50 backdrop-blur-xl"
      style={{
        backgroundColor: 'rgba(10,10,10,0.85)',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
      }}
    >
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center">
        {/* Logo */}
        <div className="flex-1 flex items-center gap-2.5">
          <svg width="24" height="24" viewBox="0 0 48 48" fill="none" className="shrink-0">
            <circle cx="24" cy="24" r="22" fill="#FF6B35" stroke="#CC5529" strokeWidth="1.5" />
            <path d="M2 24 C16 20, 32 28, 46 24" stroke="#CC5529" strokeWidth="1.2" fill="none" />
            <path d="M24 2 C20 16, 28 32, 24 46" stroke="#CC5529" strokeWidth="1.2" fill="none" />
          </svg>
          <span className="text-lg font-bold hidden sm:inline">
            <span className="text-white">NBA</span>{' '}
            <span style={{ color: 'var(--text-secondary)' }}>Injury</span>{' '}
            <span style={{ color: '#FF6B35' }}>Impact</span>{' '}
            <span style={{ color: 'var(--text-secondary)' }}>Analyzer</span>
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
                `relative px-3 py-2 text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'text-white'
                    : 'text-[#9CA3AF] hover:text-white'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {label}
                  {isActive && (
                    <span
                      className="absolute bottom-0 left-3 right-3 h-0.5 rounded-full"
                      style={{ backgroundColor: '#FF6B35' }}
                    />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </div>

        {/* Auth */}
        <div className="flex-1 flex items-center justify-end gap-3">
          {loading ? (
            <div className="w-20 h-8 rounded-lg animate-pulse" style={{ backgroundColor: 'var(--bg-surface)' }} />
          ) : user ? (
            <>
              <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                <div
                  className="w-7 h-7 rounded-full flex items-center justify-center"
                  style={{ backgroundColor: 'rgba(255,107,53,0.2)' }}
                >
                  <User className="w-4 h-4" style={{ color: '#FF6B35' }} />
                </div>
                <span className="hidden md:inline">{user.email}</span>
              </div>
              <button
                onClick={logout}
                className="transition-all duration-200 p-1.5 rounded-lg cursor-pointer"
                style={{ color: 'var(--text-secondary)' }}
                onMouseEnter={(e) => e.currentTarget.style.color = 'white'}
                onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-secondary)'}
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
