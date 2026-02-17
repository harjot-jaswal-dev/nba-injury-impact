export default function StatBadge({ label, value, size = 'md' }) {
  const padding = size === 'sm' ? 'px-2.5 py-1.5' : 'px-3 py-2'
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm'
  const valueSize = size === 'sm' ? 'text-sm' : 'text-lg'

  return (
    <div className={`bg-slate-700/50 rounded-lg ${padding} text-center`}>
      <p className={`${textSize} text-slate-400 uppercase tracking-wide`}>{label}</p>
      <p className={`${valueSize} font-semibold text-slate-100 mt-0.5`}>{value}</p>
    </div>
  )
}
