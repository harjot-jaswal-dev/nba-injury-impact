import { Send } from 'lucide-react'

export default function ChatInput({ value, onChange, onSend, disabled, loading }) {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (value.trim() && !disabled) onSend()
    }
  }

  const charCount = value.length
  const nearLimit = charCount > 1800

  return (
    <div className="relative">
      <div className="flex items-end gap-2 bg-slate-800 border border-slate-700 rounded-xl p-2">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? 'Chat unavailable' : 'Ask about NBA injuries and predictions...'}
          disabled={disabled}
          maxLength={2000}
          rows={1}
          className="flex-1 bg-transparent text-sm text-slate-200 placeholder-slate-500 resize-none focus:outline-none disabled:opacity-50 max-h-32 min-h-[36px] py-1.5 px-2"
          style={{ height: 'auto', overflow: 'hidden' }}
          onInput={(e) => {
            e.target.style.height = 'auto'
            e.target.style.height = Math.min(e.target.scrollHeight, 128) + 'px'
          }}
        />
        <button
          onClick={onSend}
          disabled={disabled || !value.trim() || loading}
          className="p-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0 cursor-pointer"
        >
          {loading ? (
            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
        </button>
      </div>
      {nearLimit && (
        <p className={`text-xs mt-1 text-right ${charCount >= 2000 ? 'text-red-400' : 'text-slate-500'}`}>
          {charCount}/2000
        </p>
      )}
    </div>
  )
}
