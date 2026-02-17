import { useState, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
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

const CustomTooltip = ({ active, payload, label, hoveredBar }) => {
  if (!active || !payload?.length) return null
  const data = payload[0]?.payload
  if (!data) return null

  const entries = hoveredBar
    ? payload.filter(p => p.dataKey === hoveredBar)
    : payload

  return (
    <div
      className="rounded-lg px-3 py-2 shadow-xl text-sm"
      style={{
        backgroundColor: '#1a1a2e',
        border: '1px solid rgba(255,255,255,0.1)',
      }}
    >
      <p className="font-medium mb-1" style={{ color: '#e5e7eb' }}>{data.fullName || label}</p>
      {entries.map((entry) => {
        const val = data[entry.dataKey]
        const isBaseline = entry.dataKey === 'baseline'
        const color = isBaseline
          ? '#9CA3AF'
          : data.projected >= data.baseline ? '#34D399' : '#F87171'
        return (
          <p key={entry.dataKey} style={{ color }}>
            {isBaseline ? 'Baseline' : 'Projected'}: {val?.toFixed(1)}
          </p>
        )
      })}
    </div>
  )
}

const CustomLegend = () => (
  <div className="flex items-center justify-center gap-4 mt-2 pb-1 text-xs">
    <div className="flex items-center gap-1.5">
      <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: '#4b5563' }} />
      <span style={{ color: '#9CA3AF' }}>Baseline</span>
    </div>
    <div className="flex items-center gap-1.5">
      <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: '#34D399' }} />
      <span style={{ color: '#9CA3AF' }}>Above Baseline</span>
    </div>
    <div className="flex items-center gap-1.5">
      <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: '#F87171' }} />
      <span style={{ color: '#9CA3AF' }}>Below Baseline</span>
    </div>
  </div>
)

export default function RippleChart({ predictions, height = 300 }) {
  const [stat, setStat] = useState('pts')
  const [hoveredBar, setHoveredBar] = useState(null)

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

  return (
    <div>
      {/* Stat selector */}
      <div className="flex items-center gap-1 mb-4">
        {STAT_OPTIONS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setStat(key)}
            className="px-3 py-1 text-xs font-medium rounded-md transition-all duration-200 cursor-pointer"
            style={
              stat === key
                ? { backgroundColor: '#FF6B35', color: 'white' }
                : { backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }
            }
          >
            {label}
          </button>
        ))}
      </div>

      <div style={{ backgroundColor: 'var(--bg-base)', borderRadius: '8px', padding: '12px 8px 4px' }}>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={chartData} margin={{ top: 5, right: 5, left: -10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis
              dataKey="name"
              tick={{ fill: '#d1d5db', fontSize: 12 }}
              axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: '#d1d5db', fontSize: 12 }}
              axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
              tickLine={false}
            />
            <Tooltip
              content={<CustomTooltip hoveredBar={hoveredBar} />}
              cursor={{ fill: 'rgba(148,163,184,0.08)' }}
            />
            <ReferenceLine y={0} stroke="rgba(255,255,255,0.1)" />
            <Bar
              dataKey="baseline"
              name="Baseline"
              fill="#4b5563"
              radius={[4, 4, 0, 0]}
              onMouseEnter={() => setHoveredBar('baseline')}
              onMouseLeave={() => setHoveredBar(null)}
            />
            <Bar
              dataKey="projected"
              name="Projected"
              radius={[4, 4, 0, 0]}
              onMouseEnter={() => setHoveredBar('projected')}
              onMouseLeave={() => setHoveredBar(null)}
            >
              {chartData.map((entry, index) => (
                <Cell
                  key={index}
                  fill={entry.projected >= entry.baseline ? '#34D399' : '#F87171'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <CustomLegend />
      </div>
    </div>
  )
}
