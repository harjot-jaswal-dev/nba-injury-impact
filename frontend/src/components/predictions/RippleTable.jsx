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
          <tr className="border-b border-slate-700 text-slate-400 text-xs uppercase tracking-wider">
            <th className="text-left py-2 pr-3 font-medium">Player</th>
            {STATS.map(({ key, label }) => (
              <th key={key} className="text-right py-2 px-1.5 font-medium whitespace-nowrap">
                {showRipple ? (
                  <span className="flex flex-col items-end">
                    <span>{label}</span>
                    <span className="text-slate-500 font-normal normal-case">base / adj / &Delta;</span>
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
              className={`border-b border-slate-700/50 hover:bg-slate-700/20 ${
                idx % 2 === 0 ? 'bg-slate-800/30' : ''
              }`}
            >
              <td className="py-2.5 pr-3 font-medium text-slate-200 whitespace-nowrap">
                {player.player_name}
              </td>
              {STATS.map(({ key }) => (
                <td key={key} className="text-right py-2.5 px-1.5 whitespace-nowrap">
                  {showRipple ? (
                    <div className="flex items-center justify-end gap-2">
                      <span className="text-slate-400">{formatStat(player.baseline?.[key])}</span>
                      <span className="text-slate-200">{formatStat(player.with_injuries?.[key])}</span>
                      <span className="w-14 text-right">
                        <DeltaBadge value={player.ripple_effect?.[key]} showIcon={false} />
                      </span>
                    </div>
                  ) : (
                    <span className="text-slate-200">
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
        <p className="text-xs text-slate-500 mt-3 italic">
          Shooting percentages (FG%, FT%) omitted — single-game percentage predictions have high variance. Counting stats shown are more reliable.
        </p>
      )}
    </div>
  )
}
