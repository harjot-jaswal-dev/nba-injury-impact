export default function UsageBar({ usage }) {
  if (!usage) return null

  const { used, limit, remaining } = usage
  const pct = Math.min((used / limit) * 100, 100)
  const isLow = remaining <= 2
  const isExhausted = remaining <= 0

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${
            isExhausted ? 'bg-red-500' : isLow ? 'bg-amber-500' : 'bg-blue-500'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-xs font-medium whitespace-nowrap ${
        isExhausted ? 'text-red-400' : isLow ? 'text-amber-400' : 'text-slate-400'
      }`}>
        {used}/{limit} used today
      </span>
    </div>
  )
}
