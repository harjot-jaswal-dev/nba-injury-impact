import { useState, useEffect } from 'react'
import { getPredictions, getRipple } from '../services/api'

export function usePredictions(gameId, team) {
  const [baseline, setBaseline] = useState(null)
  const [ripple, setRipple] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!gameId) {
      setBaseline(null)
      setRipple(null)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setError(null)
    setBaseline(null)
    setRipple(null)

    async function fetch() {
      try {
        const [baselineData, rippleData] = await Promise.all([
          getPredictions(gameId, { signal: controller.signal }),
          getRipple(gameId, team, null, { signal: controller.signal }),
        ])
        setBaseline(baselineData)
        setRipple(rippleData)
      } catch (err) {
        if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') return
        setError(err?.response?.data?.detail ?? 'Failed to load predictions')
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    fetch()
    return () => controller.abort()
  }, [gameId, team])

  const hasAbsences = ripple?.absent_players?.length > 0

  return { baseline, ripple, hasAbsences, loading, error }
}
