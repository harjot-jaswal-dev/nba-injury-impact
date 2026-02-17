import { AlertCircle, RefreshCw } from 'lucide-react'

export default function ErrorCard({ message, onRetry }) {
  return (
    <div
      className="rounded-xl p-4 flex items-start gap-3"
      style={{
        backgroundColor: 'rgba(239,68,68,0.08)',
        border: '1px solid rgba(239,68,68,0.15)',
      }}
    >
      <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" style={{ color: '#F87171' }} />
      <div className="flex-1 min-w-0">
        <p className="text-sm" style={{ color: '#FCA5A5' }}>{message || 'Something went wrong'}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="transition-all duration-200 p-1 rounded-lg shrink-0 cursor-pointer"
          style={{ color: '#F87171' }}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#FF6B35'; e.currentTarget.style.backgroundColor = 'rgba(255,107,53,0.1)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = '#F87171'; e.currentTarget.style.backgroundColor = 'transparent' }}
          title="Retry"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}
