import { createContext, useContext, useState, useEffect } from 'react'
import { getMe, logout as apiLogout, getAuthUrl } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const login = async () => {
    try {
      const { auth_url } = await getAuthUrl()
      window.location.href = auth_url
    } catch {
      // Auth not configured — silently fail
    }
  }

  const handleLogout = async () => {
    try {
      await apiLogout()
    } finally {
      setUser(null)
    }
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout: handleLogout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
