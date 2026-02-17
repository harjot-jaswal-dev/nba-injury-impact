import { useState, useEffect, useMemo } from 'react'
import { Zap, Search, UserX, Home, Plane } from 'lucide-react'
import { useSimulator } from '../hooks/useSimulator'
import { getTeams, getPlayers } from '../services/api'
import InjuryContextBadges from '../components/predictions/InjuryContextBadges'
import RippleTable from '../components/predictions/RippleTable'
import RippleChart from '../components/predictions/RippleChart'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import ErrorCard from '../components/ui/ErrorCard'
import EmptyState from '../components/ui/EmptyState'
import TeamTag from '../components/ui/TeamTag'
import { formatStat } from '../utils/formatters'

const STARTER_MINUTES_THRESHOLD = 24

export default function Simulator() {
  const { form, updateTeam, updateOpponent, togglePlayer, updateField, result, loading, error, run } =
    useSimulator()

  const [teams, setTeams] = useState([])
  const [players, setPlayers] = useState([])
  const [playersLoading, setPlayersLoading] = useState(false)
  const [rosterFilter, setRosterFilter] = useState('')

  // Load teams on mount
  useEffect(() => {
    getTeams().then(setTeams).catch(() => {})
  }, [])

  // Load players when team changes
  useEffect(() => {
    if (!form.team) {
      setPlayers([])
      return
    }
    setPlayersLoading(true)
    getPlayers({ team: form.team })
      .then(setPlayers)
      .catch(() => setPlayers([]))
      .finally(() => setPlayersLoading(false))
  }, [form.team])

  // Sort players by minutes, split into starters/bench
  const sortedPlayers = useMemo(() => {
    const sorted = [...players].sort(
      (a, b) => (b.season_avg_minutes ?? 0) - (a.season_avg_minutes ?? 0)
    )
    const filtered = rosterFilter
      ? sorted.filter(p => p.player_name.toLowerCase().includes(rosterFilter.toLowerCase()))
      : sorted
    return filtered
  }, [players, rosterFilter])

  const starterCount = useMemo(() => {
    return sortedPlayers.filter(p => (p.season_avg_minutes ?? 0) >= STARTER_MINUTES_THRESHOLD).length
  }, [sortedPlayers])

  const opponentTeams = teams.filter(t => t.team_abbr !== form.team)

  // Calculate summary stats from result
  const totalPtsRedistributed = result?.player_predictions?.reduce(
    (sum, p) => sum + Math.abs(p.ripple_effect?.pts ?? 0), 0
  ) ?? 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Injury Simulator</h1>
        <p className="text-slate-400 text-sm mt-1">
          Create custom what-if scenarios to explore how injuries impact team performance
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left panel — Configuration */}
        <div className="lg:col-span-4 space-y-4">
          {/* Team selector */}
          <div className="card card-body space-y-3">
            <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Select Team
            </label>
            <select
              value={form.team}
              onChange={(e) => updateTeam(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Choose a team...</option>
              {teams.map((t) => (
                <option key={t.team_abbr} value={t.team_abbr}>
                  {t.team_abbr} — {t.team_name}
                </option>
              ))}
            </select>
          </div>

          {/* Player roster */}
          {form.team && (
            <div className="card card-body space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Select Injured Players
                </label>
                {form.injured_player_ids.length > 0 && (
                  <span className="text-xs text-red-400">
                    {form.injured_player_ids.length} selected
                  </span>
                )}
              </div>

              {/* Search filter */}
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-slate-500" />
                <input
                  type="text"
                  placeholder="Filter players..."
                  value={rosterFilter}
                  onChange={(e) => setRosterFilter(e.target.value)}
                  className="w-full bg-slate-700 border border-slate-600 rounded-lg pl-8 pr-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {playersLoading ? (
                <LoadingSpinner size="sm" />
              ) : (
                <div className="max-h-80 overflow-y-auto space-y-0.5">
                  {sortedPlayers.map((player, idx) => {
                    const isSelected = form.injured_player_ids.includes(player.player_id)
                    const isStarter = (player.season_avg_minutes ?? 0) >= STARTER_MINUTES_THRESHOLD
                    const showDivider = idx === starterCount && starterCount > 0 && !rosterFilter

                    return (
                      <div key={player.player_id}>
                        {showDivider && (
                          <div className="flex items-center gap-2 py-1.5 px-1">
                            <div className="flex-1 h-px bg-slate-600" />
                            <span className="text-xs text-slate-500 font-medium">Bench</span>
                            <div className="flex-1 h-px bg-slate-600" />
                          </div>
                        )}
                        {idx === 0 && !rosterFilter && starterCount > 0 && (
                          <p className="text-xs text-slate-500 font-medium px-1 pb-1">Starters / Key Rotation</p>
                        )}
                        <button
                          onClick={() => togglePlayer(player.player_id)}
                          className={`w-full flex items-center gap-3 px-2.5 py-2 rounded-lg text-left transition-colors cursor-pointer ${
                            isSelected
                              ? 'bg-red-500/15 border border-red-500/30'
                              : 'hover:bg-slate-700/50 border border-transparent'
                          }`}
                        >
                          {isSelected && <UserX className="w-4 h-4 text-red-400 shrink-0" />}
                          <div className="flex-1 min-w-0">
                            <span className={`text-sm font-medium ${isSelected ? 'text-red-300 line-through' : 'text-slate-200'}`}>
                              {player.player_name}
                            </span>
                            <span className="text-xs text-slate-500 ml-2">
                              {player.position}
                            </span>
                          </div>
                          <span className="text-xs text-slate-500 shrink-0">
                            {formatStat(player.season_avg_pts)} ppg
                          </span>
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* Opponent & settings */}
          {form.team && (
            <div className="card card-body space-y-3">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Opponent
              </label>
              <select
                value={form.opponent}
                onChange={(e) => updateOpponent(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Choose opponent...</option>
                {opponentTeams.map((t) => (
                  <option key={t.team_abbr} value={t.team_abbr}>
                    {t.team_abbr} — {t.team_name}
                  </option>
                ))}
              </select>

              {/* Home/Away toggle */}
              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">
                  Venue
                </label>
                <div className="flex gap-1 bg-slate-700 rounded-lg p-0.5">
                  <button
                    onClick={() => updateField('home_or_away', 'HOME')}
                    className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors cursor-pointer ${
                      form.home_or_away === 'HOME'
                        ? 'bg-blue-500 text-white'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Home className="w-3.5 h-3.5" />
                    Home
                  </button>
                  <button
                    onClick={() => updateField('home_or_away', 'AWAY')}
                    className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors cursor-pointer ${
                      form.home_or_away === 'AWAY'
                        ? 'bg-blue-500 text-white'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Plane className="w-3.5 h-3.5" />
                    Away
                  </button>
                </div>
              </div>

              {/* Date */}
              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">
                  Game Date
                </label>
                <input
                  type="date"
                  value={form.date}
                  onChange={(e) => updateField('date', e.target.value)}
                  className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          )}

          {/* Run button */}
          {form.team && (
            <button
              onClick={run}
              disabled={loading || !form.opponent || form.injured_player_ids.length === 0}
              className="btn-primary w-full flex items-center justify-center gap-2"
            >
              <Zap className="w-4 h-4" />
              {loading ? 'Running Simulation...' : 'Run Simulation'}
            </button>
          )}
        </div>

        {/* Right panel — Results */}
        <div className="lg:col-span-8">
          {error && <ErrorCard message={error} />}

          {loading ? (
            <LoadingSpinner text="Running simulation..." />
          ) : !result ? (
            <EmptyState
              icon={Zap}
              title="Configure a scenario"
              subtitle="Select a team, mark players as injured, choose an opponent, and run the simulation to see projected impact"
            />
          ) : (
            <div className="space-y-5">
              {/* Summary line */}
              <div className="card card-body">
                <p className="text-sm text-slate-300">
                  With{' '}
                  <span className="text-red-400 font-medium">
                    {result.absent_players.map(p => p.player_name).join(', ')}
                  </span>{' '}
                  out,{' '}
                  <TeamTag abbr={result.team} size="sm" />{' '}
                  is projected to redistribute{' '}
                  <span className="text-blue-400 font-semibold">
                    {formatStat(totalPtsRedistributed)}
                  </span>{' '}
                  total points across the remaining roster.
                </p>
              </div>

              {/* Injury context */}
              <div className="card card-body">
                <InjuryContextBadges
                  context={result.injury_context}
                  absentPlayers={result.absent_players}
                />
              </div>

              {/* Chart */}
              <div className="card card-body">
                <h3 className="text-sm font-semibold text-slate-300 mb-3">
                  Ripple Effect Visualization
                </h3>
                <RippleChart predictions={result.player_predictions} />
              </div>

              {/* Table */}
              <div className="card card-body">
                <h3 className="text-sm font-semibold text-slate-300 mb-3">
                  Player-by-Player Impact
                </h3>
                <RippleTable predictions={result.player_predictions} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
