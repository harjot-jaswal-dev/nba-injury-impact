import { Loader2 } from 'lucide-react'

export default function LoadingSpinner({ size = 'md', text }) {
  const sizeClass = size === 'sm' ? 'w-5 h-5' : 'w-8 h-8'

  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12">
      <Loader2 className={`${sizeClass} text-blue-500 animate-spin`} />
      {text && <p className="text-sm text-slate-400">{text}</p>}
    </div>
  )
}
