import { AlertCircle } from 'lucide-react'
import TeamTag from '../ui/TeamTag'
import { formatDate } from '../../utils/formatters'

export default function GameCard({ game, isSelected, hasAbsences, onClick }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left p-3 rounded-lg transition-all duration-200 cursor-pointer"
      style={{
        backgroundColor: isSelected ? 'rgba(255,107,53,0.1)' : 'var(--bg-surface)',
        border: isSelected ? '1px solid #FF6B35' : '1px solid var(--border-subtle)',
        boxShadow: isSelected ? '0 0 0 1px rgba(255,107,53,0.3)' : 'none',
      }}
      onMouseEnter={(e) => {
        if (!isSelected) {
          e.currentTarget.style.transform = 'scale(1.02)'
          e.currentTarget.style.borderColor = 'rgba(255,107,53,0.3)'
          e.currentTarget.style.boxShadow = '0 4px 12px rgba(255,107,53,0.05)'
        }
      }}
      onMouseLeave={(e) => {
        if (!isSelected) {
          e.currentTarget.style.transform = 'scale(1)'
          e.currentTarget.style.borderColor = 'var(--border-subtle)'
          e.currentTarget.style.boxShadow = 'none'
        }
      }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <TeamTag abbr={game.away_team} size="sm" />
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>@</span>
          <TeamTag abbr={game.home_team} size="sm" />
        </div>
        {hasAbsences && (
          <span
            className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
            style={{
              color: '#FBBF24',
              backgroundColor: 'rgba(251,191,36,0.1)',
              border: '1px solid rgba(251,191,36,0.15)',
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: '#FBBF24', animation: 'basketball-pulse 2s ease-in-out infinite' }}
            />
            Injuries
          </span>
        )}
      </div>
      <div className="flex items-center justify-between mt-1.5">
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{formatDate(game.game_date)}</span>
        {game.status === 'completed' && (
          <span
            className="text-xs px-1.5 py-0.5 rounded"
            style={{ color: 'var(--text-muted)', backgroundColor: 'var(--bg-elevated)' }}
          >
            Final
          </span>
        )}
      </div>
    </button>
  )
}
