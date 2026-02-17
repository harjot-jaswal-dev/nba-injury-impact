import { Routes, Route, Navigate } from 'react-router-dom'
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
    <footer className="border-t border-slate-800 mt-12">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
          <div className="flex items-center gap-4">
            <span>NBA Injury Impact Analyzer — Statistical analysis tool. Not intended for gambling.</span>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setShowAbout(!showAbout)}
              className="inline-flex items-center gap-1 hover:text-slate-300 transition-colors cursor-pointer"
            >
              <Info className="w-3.5 h-3.5" />
              About
            </button>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 hover:text-slate-300 transition-colors"
            >
              <Github className="w-3.5 h-3.5" />
              GitHub
            </a>
          </div>
        </div>
        {showAbout && (
          <div className="mt-4 text-xs text-slate-400 bg-slate-800/50 rounded-lg p-4 border border-slate-700">
            Predictions use a gradient-boosted ML model trained on 3 seasons of NBA data.
            The Injury Ripple Effect shows how player absences redistribute stats across teammates.
          </div>
        )}
      </div>
    </footer>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <ChatProvider>
        <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col">
          <Navbar />
          <main className="max-w-7xl mx-auto px-4 py-6 flex-1 w-full">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/simulator" element={<Simulator />} />
              <Route path="/chat" element={<Chat />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
          <Footer />
        </div>
      </ChatProvider>
    </AuthProvider>
  )
}
