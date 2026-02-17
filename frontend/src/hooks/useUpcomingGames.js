import { useState, useEffect } from 'react'
import { getUpcomingGames, getRipple } from '../services/api'

export function useUpcomingGames(limit = 15) {
  const [data, setData] = useState(null)
  const [gamesWithAbsences, setGamesWithAbsences] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function fetchGames() {
      setLoading(true)
      setError(null)
      try {
        const result = await getUpcomingGames(limit)
        if (cancelled) return
        setData(result)

        // Prefetch ripple data for each game to detect absences
        const absenceSet = new Set()
        const rippleChecks = result.games.map(async (game) => {
          try {
            const ripple = await getRipple(game.game_id)
            if (ripple.absent_players && ripple.absent_players.length > 0) {
              absenceSet.add(game.game_id)
            }
          } catch {
            // Silently fail — absence check is best-effort
          }
        })

        await Promise.allSettled(rippleChecks)
        if (!cancelled) {
          setGamesWithAbsences(new Set(absenceSet))
        }
      } catch (err) {
        if (!cancelled) {
          setError(err?.response?.data?.detail ?? 'Failed to load games')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchGames()
    return () => { cancelled = true }
  }, [limit])

  // Sort games: absences first, then by date
  const sortedGames = data?.games
    ? [...data.games].sort((a, b) => {
        const aHas = gamesWithAbsences.has(a.game_id) ? 0 : 1
        const bHas = gamesWithAbsences.has(b.game_id) ? 0 : 1
        if (aHas !== bHas) return aHas - bHas
        return a.game_date.localeCompare(b.game_date)
      })
    : []

  return {
    games: sortedGames,
    source: data?.source,
    gamesWithAbsences,
    loading,
    error,
  }
}
