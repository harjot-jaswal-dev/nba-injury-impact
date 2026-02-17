import { Inbox } from 'lucide-react'

export default function EmptyState({ icon, title, subtitle, children }) {
  const Icon = icon || Inbox

  return (
    <div className="flex flex-col items-center justify-center py-16 text-center" style={{ animation: 'fade-in 300ms ease-out' }}>
      <Icon className="w-12 h-12 mb-4" style={{ color: 'var(--text-muted)' }} />
      <h3 className="text-lg font-medium" style={{ color: 'var(--text-secondary)' }}>{title}</h3>
      {subtitle && <p className="text-sm mt-1 max-w-md" style={{ color: 'var(--text-muted)' }}>{subtitle}</p>}
      {children && <div className="mt-4">{children}</div>}
    </div>
  )
}
