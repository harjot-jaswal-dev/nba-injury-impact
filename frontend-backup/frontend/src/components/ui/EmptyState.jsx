import { Inbox } from 'lucide-react'

export default function EmptyState({ icon, title, subtitle, children }) {
  const Icon = icon || Inbox

  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <Icon className="w-12 h-12 text-slate-600 mb-4" />
      <h3 className="text-lg font-medium text-slate-300">{title}</h3>
      {subtitle && <p className="text-sm text-slate-500 mt-1 max-w-md">{subtitle}</p>}
      {children && <div className="mt-4">{children}</div>}
    </div>
  )
}
