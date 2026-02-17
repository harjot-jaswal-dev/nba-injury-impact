export const formatStat = (val, decimals = 1) => {
  if (val == null) return '\u2014'
  return Number(val).toFixed(decimals)
}

export const formatDelta = (val) => {
  if (val == null) return '\u2014'
  const n = Number(val)
  if (Math.abs(n) < 0.05) return '0.0'
  return n >= 0 ? `+${n.toFixed(1)}` : n.toFixed(1)
}

export const getDeltaColor = (val) => {
  if (val == null) return 'text-slate-400'
  const n = Number(val)
  if (n > 0.05) return 'text-green-400'
  if (n < -0.05) return 'text-red-400'
  return 'text-slate-400'
}

export const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const d = new Date(dateStr + 'T12:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
