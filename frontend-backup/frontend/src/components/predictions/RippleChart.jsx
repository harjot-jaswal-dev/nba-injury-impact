import { useState, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine,
} from 'recharts'

const STAT_OPTIONS = [
  { key: 'pts', label: 'PTS' },
  { key: 'ast', label: 'AST' },
  { key: 'reb', label: 'REB' },
  { key: 'minutes', label: 'MIN' },
]

function shortenName(name) {
  if (!name) return ''
  const parts = name.split(' ')
  if (parts.length < 2) return name
  return `${parts[0][0]}. ${parts.slice(1).join(' ')}`
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 shadow-xl text-sm">
      <p className="font-medium text-slate-200 mb-1">{label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: {entry.value?.toFixed(1)}
        </p>
      ))}
      {payload.length === 2 && (
        <p className="text-slate-400 mt-1 border-t border-slate-700 pt-1">
          Delta: {(payload[1].value - payload[0].value)?.toFixed(1)}
        </p>
      )}
    </div>
  )
}

export default function RippleChart({ predictions, height = 300 }) {
  const [stat, setStat] = useState('pts')

  const chartData = useMemo(() => {
    if (!predictions?.length) return []
    return [...predictions]
      .filter(p => p.ripple_effect && p.baseline)
      .sort((a, b) => Math.abs(b.ripple_effect[stat] ?? 0) - Math.abs(a.ripple_effect[stat] ?? 0))
      .slice(0, 8)
      .map(p => ({
        name: shortenName(p.player_name),
        fullName: p.player_name,
        baseline: p.baseline[stat],
        projected: p.with_injuries[stat],
      }))
  }, [predictions, stat])

  if (!chartData.length) return null

  const statLabel = STAT_OPTIONS.find(s => s.key === stat)?.label || stat.toUpperCase()

  return (
    <div>
      {/* Stat selector */}
      <div className="flex items-center gap-1 mb-4">
        {STAT_OPTIONS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setStat(key)}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors cursor-pointer ${
              stat === key
                ? 'bg-blue-500 text-white'
                : 'bg-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-600'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={chartData} margin={{ top: 5, right: 5, left: -10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="name"
            tick={{ fill: '#94A3B8', fontSize: 12 }}
            axisLine={{ stroke: '#475569' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#94A3B8', fontSize: 12 }}
            axisLine={{ stroke: '#475569' }}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(148,163,184,0.05)' }} />
          <Legend
            wrapperStyle={{ fontSize: 12, color: '#94A3B8' }}
          />
          <ReferenceLine y={0} stroke="#475569" />
          <Bar
            dataKey="baseline"
            name={`Baseline ${statLabel}`}
            fill="#475569"
            radius={[4, 4, 0, 0]}
          />
          <Bar
            dataKey="projected"
            name={`With Injuries ${statLabel}`}
            fill="#3B82F6"
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
