export default function StatBadge({ label, value, size = 'md' }) {
  const padding = size === 'sm' ? 'px-2.5 py-1.5' : 'px-3 py-2'
  const textSize = size === 'sm' ? 'text-[10px]' : 'text-xs'
  const valueSize = size === 'sm' ? 'text-sm' : 'text-lg'

  return (
    <div
      className={`rounded-lg ${padding} text-center transition-all duration-150`}
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      <p className={`${textSize} uppercase tracking-widest`} style={{ color: 'var(--text-muted)' }}>{label}</p>
      <p className={`${valueSize} font-bold mt-0.5`} style={{ color: 'white' }}>{value}</p>
    </div>
  )
}
