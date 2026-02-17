import { formatDelta } from '../../utils/formatters'

export default function DeltaBadge({ value, showIcon = true }) {
  const n = Number(value)
  const isPositive = n > 0.05
  const isNegative = n < -0.05

  const color = isPositive ? '#34D399' : isNegative ? '#F87171' : 'var(--text-secondary)'
  const bgColor = isPositive ? 'rgba(52,211,153,0.1)' : isNegative ? 'rgba(248,113,113,0.1)' : 'transparent'
  const arrow = isPositive ? '▲ ' : isNegative ? '▼ ' : ''

  return (
    <span
      className="inline-flex items-center gap-0.5 font-medium px-2 py-0.5 rounded-full text-xs"
      style={{ color, backgroundColor: bgColor }}
    >
      {showIcon && arrow}
      {formatDelta(value)}
    </span>
  )
}
