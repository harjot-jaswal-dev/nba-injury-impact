import { getTeamColor } from '../../utils/teamColors'

export default function TeamTag({ abbr, name, size = 'md' }) {
  const { primary } = getTeamColor(abbr)
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm'

  return (
    <span className={`inline-flex items-center gap-1.5 ${textSize} font-medium text-slate-200`}>
      <span
        className="w-2 h-2 rounded-full shrink-0"
        style={{ backgroundColor: primary }}
      />
      {abbr}
      {name && <span className="text-slate-400 font-normal">{name}</span>}
    </span>
  )
}
