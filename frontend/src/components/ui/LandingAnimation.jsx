import { useState } from 'react'

export default function LandingAnimation({ onComplete }) {
  const [fading, setFading] = useState(false)

  const handleBounceEnd = () => {
    setFading(true)
  }

  const handleFadeEnd = () => {
    onComplete()
  }

  return (
    <div
      className={`fixed inset-0 z-[100] flex items-center justify-center pointer-events-none`}
      style={{
        backgroundColor: 'rgba(10,10,10,0.9)',
        animation: fading ? 'landing-fade-out 300ms ease-out forwards' : undefined,
      }}
      onAnimationEnd={fading ? handleFadeEnd : undefined}
    >
      <div
        style={{
          animation: 'basketball-bounce 800ms ease-out forwards',
        }}
        onAnimationEnd={handleBounceEnd}
      >
        {/* Basketball SVG */}
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
          <circle cx="24" cy="24" r="22" fill="#FF6B35" stroke="#CC5529" strokeWidth="1.5" />
          {/* Horizontal seam */}
          <path d="M2 24 C16 20, 32 28, 46 24" stroke="#CC5529" strokeWidth="1.2" fill="none" />
          {/* Vertical seam */}
          <path d="M24 2 C20 16, 28 32, 24 46" stroke="#CC5529" strokeWidth="1.2" fill="none" />
          {/* Left curve */}
          <path d="M8 6 C14 18, 14 30, 8 42" stroke="#CC5529" strokeWidth="0.8" fill="none" />
          {/* Right curve */}
          <path d="M40 6 C34 18, 34 30, 40 42" stroke="#CC5529" strokeWidth="0.8" fill="none" />
        </svg>
      </div>
    </div>
  )
}
