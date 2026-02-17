import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Activity, ArrowRight, Zap } from 'lucide-react'
import { useUpcomingGames } from '../hooks/useUpcomingGames'
import { usePredictions } from '../hooks/usePredictions'
import GamesList from '../components/games/GamesList'
import InjuryContextBadges from '../components/predictions/InjuryContextBadges'
import RippleTable from '../components/predictions/RippleTable'
import RippleChart from '../components/predictions/RippleChart'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import ErrorCard from '../components/ui/ErrorCard'
import EmptyState from '../components/ui/EmptyState'
import TeamTag from '../components/ui/TeamTag'

export default function Dashboard() {
  const { games, source, gamesWithAbsences, loading: gamesLoading, error: gamesError } = useUpcomingGames()
  const [selectedGame, setSelectedGame] = useState(null)
  const [selectedTeam, setSelectedTeam] = useState(null)

  // Auto-select first game (prefer one with absences)
  useEffect(() => {
    if (games.length && !selectedGame) {
      setSelectedGame(games[0])
      setSelectedTeam(games[0].home_team)
    }
  }, [games, selectedGame])

  const { baseline, ripple, hasAbsences, loading: predLoading, error: predError } =
    usePredictions(selectedGame?.game_id, selectedTeam)

  const handleSelectGame = (game) => {
    setSelectedGame(game)
    setSelectedTeam(game.home_team)
  }

  const toggleTeam = (team) => {
    setSelectedTeam(team)
  }

  // Build baseline-only player list for games with no absences
  const baselinePlayers = baseline
    ? [...(selectedTeam === baseline.home_team ? baseline.home_players : baseline.away_players)]
        .sort((a, b) => (b.predictions?.pts ?? 0) - (a.predictions?.pts ?? 0))
    : []

  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className="text-center py-6">
        <div className="flex items-center justify-center gap-2 mb-2">
          <Activity className="w-6 h-6 text-blue-500" />
          <h1 className="text-2xl sm:text-3xl font-bold text-slate-100">
            Predicting How NBA Injuries Cascade Through Team Performance
          </h1>
        </div>
        <p className="text-slate-400 text-sm">
          Powered by machine learning and 3 seasons of historical data
        </p>
      </div>

      {/* Main content */}
      {gamesLoading ? (
        <LoadingSpinner text="Loading upcoming games..." />
      ) : gamesError ? (
        <ErrorCard message={gamesError} />
      ) : games.length === 0 ? (
        <EmptyState title="No games found" subtitle="Check back later for upcoming games" />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Games list — left panel */}
          <div className="lg:col-span-4">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
              Upcoming Games
            </h2>
            <GamesList
              games={games}
              source={source}
              gamesWithAbsences={gamesWithAbsences}
              selectedGameId={selectedGame?.game_id}
              onSelect={handleSelectGame}
            />
          </div>

          {/* Predictions detail — right panel */}
          <div className="lg:col-span-8">
            {!selectedGame ? (
              <EmptyState
                icon={Zap}
                title="Select a game"
                subtitle="Click on a game to see predictions"
              />
            ) : predLoading ? (
              <LoadingSpinner text="Loading predictions..." />
            ) : predError ? (
              <ErrorCard message={predError} />
            ) : (
              <div className="space-y-5">
                {/* Game header with team toggle */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <TeamTag abbr={selectedGame.away_team} />
                    <span className="text-slate-500">@</span>
                    <TeamTag abbr={selectedGame.home_team} />
                  </div>
                  <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-0.5 border border-slate-700">
                    <button
                      onClick={() => toggleTeam(selectedGame.home_team)}
                      className={`px-3 py-1 text-xs font-medium rounded-md transition-colors cursor-pointer ${
                        selectedTeam === selectedGame.home_team
                          ? 'bg-blue-500 text-white'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {selectedGame.home_team} (Home)
                    </button>
                    <button
                      onClick={() => toggleTeam(selectedGame.away_team)}
                      className={`px-3 py-1 text-xs font-medium rounded-md transition-colors cursor-pointer ${
                        selectedTeam === selectedGame.away_team
                          ? 'bg-blue-500 text-white'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {selectedGame.away_team} (Away)
                    </button>
                  </div>
                </div>

                {hasAbsences ? (
                  <>
                    {/* Injury context */}
                    <div className="card card-body">
                      <InjuryContextBadges
                        context={ripple.injury_context}
                        absentPlayers={ripple.absent_players}
                      />
                    </div>

                    {/* Ripple chart */}
                    <div className="card card-body">
                      <h3 className="text-sm font-semibold text-slate-300 mb-3">
                        Injury Ripple Effect
                      </h3>
                      <RippleChart predictions={ripple.player_predictions} />
                    </div>

                    {/* Ripple table */}
                    <div className="card card-body">
                      <h3 className="text-sm font-semibold text-slate-300 mb-3">
                        Player-by-Player Impact
                      </h3>
                      <RippleTable predictions={ripple.player_predictions} />
                    </div>

                    {ripple.absence_data_date && (
                      <p className="text-xs text-slate-500">
                        Injury data as of: {ripple.absence_data_date}
                      </p>
                    )}
                  </>
                ) : (
                  /* No absences — baseline only */
                  <div className="card card-body space-y-4">
                    <div className="flex items-center gap-2 text-sm text-slate-400 bg-slate-700/30 rounded-lg p-3">
                      <Activity className="w-4 h-4 text-blue-400 shrink-0" />
                      <span>
                        No key absences detected for this game.{' '}
                        <Link
                          to="/simulator"
                          className="text-blue-400 hover:text-blue-300 inline-flex items-center gap-1"
                        >
                          Use the Injury Simulator to explore what-if scenarios
                          <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      </span>
                    </div>

                    <h3 className="text-sm font-semibold text-slate-300">
                      Baseline Predictions — {selectedTeam}
                    </h3>
                    <RippleTable
                      predictions={baselinePlayers.map(p => ({
                        ...p,
                        baseline: p.predictions,
                        with_injuries: null,
                        ripple_effect: null,
                      }))}
                      showRipple={false}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
