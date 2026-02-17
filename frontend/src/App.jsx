import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { ChatProvider } from './context/ChatContext'
import Navbar from './components/layout/Navbar'
import Dashboard from './pages/Dashboard'
import Simulator from './pages/Simulator'
import Chat from './pages/Chat'
import { Activity, Github, Info } from 'lucide-react'
import { useState } from 'react'

function Footer() {
  const [showAbout, setShowAbout] = useState(false)

  return (
    <footer className="mt-12" style={{ borderTop: '1px solid var(--border-subtle)' }}>
      <div className="max-w-7xl mx-auto px-4 py-6" style={{ background: 'linear-gradient(to top, var(--bg-deep), transparent)' }}>
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 text-xs" style={{ color: 'var(--text-muted)' }}>
          <div className="flex items-center gap-4">
            <span>NBA Injury Impact Analyzer — Statistical analysis tool. Not intended for gambling.</span>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setShowAbout(!showAbout)}
              className="inline-flex items-center gap-1 transition-colors duration-200 cursor-pointer hover:text-[#FF6B35]"
            >
              <Info className="w-3.5 h-3.5" />
              About
            </button>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 transition-colors duration-200 hover:text-[#FF6B35]"
            >
              <Github className="w-3.5 h-3.5" />
              GitHub
            </a>
          </div>
        </div>
        {showAbout && (
          <div className="mt-4 text-xs rounded-lg p-4" style={{ color: 'var(--text-secondary)', backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>
            Predictions use a gradient-boosted ML model trained on 3 seasons of NBA data.
            The Injury Ripple Effect shows how player absences redistribute stats across teammates.
          </div>
        )}
      </div>
    </footer>
  )
}

function AnimatedRoutes() {
  const location = useLocation()

  return (
    <div key={location.pathname} className="page-enter">
      <Routes location={location}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/simulator" element={<Simulator />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <ChatProvider>
        <div className="min-h-screen flex flex-col" style={{ backgroundColor: 'var(--bg-base)', color: 'var(--text-primary)' }}>
          <Navbar />
          <main className="max-w-7xl mx-auto px-4 py-6 flex-1 w-full">
            <AnimatedRoutes />
          </main>
          <Footer />
        </div>
      </ChatProvider>
    </AuthProvider>
  )
}
