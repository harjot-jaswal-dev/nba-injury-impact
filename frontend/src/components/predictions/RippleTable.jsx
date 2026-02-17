import { useMemo } from 'react'
import DeltaBadge from '../ui/DeltaBadge'
import { formatStat } from '../../utils/formatters'

const STATS = [
  { key: 'pts', label: 'PTS' },
  { key: 'ast', label: 'AST' },
  { key: 'reb', label: 'REB' },
  { key: 'stl', label: 'STL' },
  { key: 'blk', label: 'BLK' },
  { key: 'minutes', label: 'MIN' },
]

export default function RippleTable({ predictions, showRipple = true }) {
  const sorted = useMemo(() => {
    if (!predictions?.length) return []
    return [...predictions].sort(
      (a, b) => Math.abs(b.ripple_effect?.pts ?? 0) - Math.abs(a.ripple_effect?.pts ?? 0)
    )
  }, [predictions])

  if (!sorted.length) return null

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
            <th
              className="text-left py-2 pr-3 font-medium uppercase tracking-widest"
              style={{ color: 'var(--text-muted)', fontSize: '11px' }}
            >
              Player
            </th>
            {STATS.map(({ key, label }) => (
              <th
                key={key}
                className="text-right py-2 px-1.5 font-medium whitespace-nowrap uppercase tracking-widest"
                style={{ color: 'var(--text-muted)', fontSize: '11px' }}
              >
                {showRipple ? (
                  <span className="flex flex-col items-end">
                    <span>{label}</span>
                    <span className="font-normal normal-case" style={{ color: 'var(--text-muted)' }}>base / adj / &Delta;</span>
                  </span>
                ) : (
                  label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((player, idx) => (
            <tr
              key={player.player_id}
              className="transition-colors duration-150"
              style={{
                borderBottom: '1px solid rgba(255,255,255,0.03)',
                backgroundColor: idx % 2 === 0 ? 'rgba(20,20,24,0.5)' : 'transparent',
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--bg-hover)'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = idx % 2 === 0 ? 'rgba(20,20,24,0.5)' : 'transparent'}
            >
              <td className="py-3 pr-3 font-semibold whitespace-nowrap" style={{ color: 'rgba(255,255,255,0.9)' }}>
                {player.player_name}
              </td>
              {STATS.map(({ key }) => (
                <td key={key} className="text-right py-3 px-1.5 whitespace-nowrap">
                  {showRipple ? (
                    <div className="flex items-center justify-end gap-2">
                      <span style={{ color: 'var(--text-muted)' }}>{formatStat(player.baseline?.[key])}</span>
                      <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>{formatStat(player.with_injuries?.[key])}</span>
                      <span className="w-14 text-right">
                        <DeltaBadge value={player.ripple_effect?.[key]} showIcon={false} />
                      </span>
                    </div>
                  ) : (
                    <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {formatStat(player.baseline?.[key] ?? player.predictions?.[key])}
                    </span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {showRipple && (
        <p className="text-xs mt-3 italic" style={{ color: 'var(--text-muted)' }}>
          Shooting percentages (FG%, FT%) omitted — single-game percentage predictions have high variance. Counting stats shown are more reliable.
        </p>
      )}
    </div>
  )
}
