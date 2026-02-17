export default function LoadingSpinner({ size = 'md', text }) {
  const dim = size === 'sm' ? 20 : 32

  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12">
      <div style={{ width: dim, height: dim, animation: 'basketball-spin 1s linear infinite' }}>
        <svg width={dim} height={dim} viewBox="0 0 48 48" fill="none">
          <circle cx="24" cy="24" r="22" fill="#FF6B35" stroke="#CC5529" strokeWidth="1.5" />
          <path d="M2 24 C16 20, 32 28, 46 24" stroke="#CC5529" strokeWidth="1.2" fill="none" />
          <path d="M24 2 C20 16, 28 32, 24 46" stroke="#CC5529" strokeWidth="1.2" fill="none" />
          <path d="M8 6 C14 18, 14 30, 8 42" stroke="#CC5529" strokeWidth="0.8" fill="none" />
          <path d="M40 6 C34 18, 34 30, 40 42" stroke="#CC5529" strokeWidth="0.8" fill="none" />
        </svg>
      </div>
      {text && <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{text}</p>}
    </div>
  )
}
