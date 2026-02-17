import { AlertCircle, RefreshCw } from 'lucide-react'

export default function ErrorCard({ message, onRetry }) {
  return (
    <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex items-start gap-3">
      <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-red-300">{message || 'Something went wrong'}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-red-400 hover:text-red-300 transition-colors p-1 rounded-lg hover:bg-red-500/10 shrink-0"
          title="Retry"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}
