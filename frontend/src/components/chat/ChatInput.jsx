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
      <div
        className="flex items-end gap-2 rounded-xl p-2 backdrop-blur-sm"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? 'Chat unavailable' : 'Ask about NBA injuries and predictions...'}
          disabled={disabled}
          maxLength={2000}
          rows={1}
          className="flex-1 bg-transparent text-sm placeholder-[#6B7280] resize-none focus:outline-none disabled:opacity-50 max-h-32 min-h-[36px] py-1.5 px-2"
          style={{ color: 'var(--text-primary)', height: 'auto', overflow: 'hidden' }}
          onInput={(e) => {
            e.target.style.height = 'auto'
            e.target.style.height = Math.min(e.target.scrollHeight, 128) + 'px'
          }}
        />
        <button
          onClick={onSend}
          disabled={disabled || !value.trim() || loading}
          className="p-2 rounded-lg text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 shrink-0 cursor-pointer"
          style={{ backgroundColor: '#FF6B35' }}
          onMouseEnter={(e) => { if (!e.currentTarget.disabled) e.currentTarget.style.backgroundColor = '#FF8C42' }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '#FF6B35' }}
        >
          {loading ? (
            <div style={{ width: 16, height: 16, animation: 'basketball-spin 1s linear infinite' }}>
              <svg width="16" height="16" viewBox="0 0 48 48" fill="none">
                <circle cx="24" cy="24" r="22" fill="white" stroke="rgba(255,255,255,0.5)" strokeWidth="1.5" />
                <path d="M2 24 C16 20, 32 28, 46 24" stroke="rgba(255,255,255,0.5)" strokeWidth="1.2" fill="none" />
                <path d="M24 2 C20 16, 28 32, 24 46" stroke="rgba(255,255,255,0.5)" strokeWidth="1.2" fill="none" />
              </svg>
            </div>
          ) : (
            <Send className="w-4 h-4" />
          )}
        </button>
      </div>
      {nearLimit && (
        <p className={`text-xs mt-1 text-right`} style={{ color: charCount >= 2000 ? 'var(--accent-red)' : 'var(--text-muted)' }}>
          {charCount}/2000
        </p>
      )}
    </div>
  )
}
