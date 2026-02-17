import { UserX } from 'lucide-react'
import StatBadge from '../ui/StatBadge'
import { formatStat } from '../../utils/formatters'

export default function InjuryContextBadges({ context, absentPlayers }) {
  if (!context || !absentPlayers?.length) return null

  return (
    <div className="space-y-3">
      {/* Absent player pills */}
      <div className="flex flex-wrap gap-2">
        {absentPlayers.map((p) => (
          <span
            key={p.player_id}
            className="inline-flex items-center gap-1.5 text-sm px-2.5 py-1 rounded-full"
            style={{
              color: '#FCA5A5',
              backgroundColor: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.15)',
            }}
          >
            <UserX className="w-3.5 h-3.5" />
            {p.player_name}
          </span>
        ))}
      </div>

      {/* Severity metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatBadge label="Starters Out" value={context.n_starters_out} size="sm" />
        <StatBadge label="PTS Lost" value={formatStat(context.total_pts_lost)} size="sm" />
        <StatBadge label="AST Lost" value={formatStat(context.total_ast_lost)} size="sm" />
        <StatBadge label="MIN Lost" value={formatStat(context.total_minutes_lost)} size="sm" />
      </div>
    </div>
  )
}
