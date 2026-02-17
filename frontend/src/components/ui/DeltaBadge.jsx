import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { formatDelta, getDeltaColor } from '../../utils/formatters'

export default function DeltaBadge({ value, showIcon = true }) {
  const color = getDeltaColor(value)
  const n = Number(value)

  let Icon = Minus
  if (n > 0.05) Icon = TrendingUp
  else if (n < -0.05) Icon = TrendingDown

  return (
    <span className={`inline-flex items-center gap-1 font-medium ${color}`}>
      {showIcon && <Icon className="w-3.5 h-3.5" />}
      {formatDelta(value)}
    </span>
  )
}
