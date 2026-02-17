import { AlertTriangle } from 'lucide-react'
import GameCard from './GameCard'

export default function GamesList({ games, source, gamesWithAbsences, selectedGameId, onSelect }) {
  return (
    <div className="space-y-2">
      {source === 'recent_completed' && (
        <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-400/10 border border-amber-400/20 rounded-lg px-3 py-2 mb-3">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span>Live schedule unavailable — showing recent games</span>
        </div>
      )}
      <div className="space-y-1.5 max-h-[calc(100vh-320px)] overflow-y-auto pr-1">
        {games.map((game) => (
          <GameCard
            key={game.game_id}
            game={game}
            isSelected={game.game_id === selectedGameId}
            hasAbsences={gamesWithAbsences.has(game.game_id)}
            onClick={() => onSelect(game)}
          />
        ))}
      </div>
    </div>
  )
}
