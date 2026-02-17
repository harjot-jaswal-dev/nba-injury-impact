import { getTeamColor } from '../../utils/teamColors'

export default function TeamTag({ abbr, name, size = 'md' }) {
  const { primary } = getTeamColor(abbr)
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm'

  return (
    <span className={`inline-flex items-center gap-1.5 ${textSize} font-medium`} style={{ color: 'var(--text-primary)' }}>
      <span
        className="w-2 h-2 rounded-full shrink-0"
        style={{ backgroundColor: primary, boxShadow: `0 0 6px ${primary}` }}
      />
      {abbr}
      {name && <span style={{ color: 'var(--text-secondary)' }} className="font-normal">{name}</span>}
    </span>
  )
}
