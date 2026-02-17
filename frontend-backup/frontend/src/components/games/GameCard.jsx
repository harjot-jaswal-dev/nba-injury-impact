import { AlertCircle } from 'lucide-react'
import TeamTag from '../ui/TeamTag'
import { formatDate } from '../../utils/formatters'

export default function GameCard({ game, isSelected, hasAbsences, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-3 rounded-lg border transition-all cursor-pointer ${
        isSelected
          ? 'border-blue-500 bg-blue-500/10 ring-1 ring-blue-500/50'
          : 'border-slate-700 bg-slate-800 hover:border-slate-600 hover:bg-slate-750'
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <TeamTag abbr={game.away_team} size="sm" />
          <span className="text-slate-500 text-xs">@</span>
          <TeamTag abbr={game.home_team} size="sm" />
        </div>
        {hasAbsences && (
          <span className="inline-flex items-center gap-1 text-xs text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full">
            <AlertCircle className="w-3 h-3" />
            Injuries
          </span>
        )}
      </div>
      <div className="flex items-center justify-between mt-1.5">
        <span className="text-xs text-slate-500">{formatDate(game.game_date)}</span>
        {game.status === 'completed' && (
          <span className="text-xs text-slate-500 bg-slate-700/50 px-1.5 py-0.5 rounded">Final</span>
        )}
      </div>
    </button>
  )
}
