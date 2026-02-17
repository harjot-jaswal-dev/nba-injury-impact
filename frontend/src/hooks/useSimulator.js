import { useState, useCallback } from 'react'
import { simulate } from '../services/api'

const initialForm = {
  team: '',
  opponent: '',
  home_or_away: 'HOME',
  date: new Date().toISOString().split('T')[0],
  injured_player_ids: [],
}

export function useSimulator() {
  const [form, setForm] = useState(initialForm)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const updateTeam = useCallback((newTeam) => {
    setForm(prev => ({ ...prev, team: newTeam, injured_player_ids: [] }))
    setResult(null)
    setError(null)
  }, [])

  const updateOpponent = useCallback((newOpponent) => {
    setForm(prev => ({ ...prev, opponent: newOpponent }))
  }, [])

  const togglePlayer = useCallback((playerId) => {
    setForm(prev => {
      const ids = prev.injured_player_ids
      const next = ids.includes(playerId)
        ? ids.filter(id => id !== playerId)
        : [...ids, playerId]
      return { ...prev, injured_player_ids: next }
    })
  }, [])

  const updateField = useCallback((field, value) => {
    setForm(prev => ({ ...prev, [field]: value }))
  }, [])

  const run = useCallback(async () => {
    if (!form.team || !form.opponent || form.injured_player_ids.length === 0) {
      setError('Select a team, opponent, and at least one injured player')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await simulate(form)
      setResult(res)
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Simulation failed')
    } finally {
      setLoading(false)
    }
  }, [form])

  return { form, updateTeam, updateOpponent, togglePlayer, updateField, result, loading, error, run }
}
