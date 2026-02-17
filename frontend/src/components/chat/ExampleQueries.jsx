import { MessageSquare } from 'lucide-react'

export default function ExampleQueries({ examples, onSelect }) {
  if (!examples?.length) return null

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
        <MessageSquare className="w-4 h-4" />
        <span>Try asking:</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {examples.map((example, idx) => (
          <button
            key={idx}
            onClick={() => onSelect(example)}
            className="text-sm px-3 py-2 rounded-full transition-all duration-200 text-left cursor-pointer hover:scale-[1.02]"
            style={{
              color: 'var(--text-secondary)',
              backgroundColor: 'transparent',
              border: '1px solid var(--border-medium)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255,107,53,0.5)'
              e.currentTarget.style.backgroundColor = 'rgba(255,107,53,0.1)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border-medium)'
              e.currentTarget.style.backgroundColor = 'transparent'
            }}
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  )
}
