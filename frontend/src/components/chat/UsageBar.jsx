export default function UsageBar({ usage }) {
  if (!usage) return null

  const { used, limit, remaining } = usage
  const pct = Math.min((used / limit) * 100, 100)
  const isLow = remaining <= 2
  const isExhausted = remaining <= 0

  const barColor = isExhausted ? '#EF4444' : isLow ? '#F59E0B' : 'var(--accent-blue)'

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--bg-elevated)' }}>
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, backgroundColor: barColor }}
        />
      </div>
      <span
        className="text-xs font-medium whitespace-nowrap"
        style={{
          color: isExhausted ? '#F87171' : isLow ? '#FBBF24' : 'var(--text-secondary)',
        }}
      >
        {used}/{limit} used today
      </span>
    </div>
  )
}
