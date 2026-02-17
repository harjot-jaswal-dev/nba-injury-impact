import { MessageSquare } from 'lucide-react'

export default function ExampleQueries({ examples, onSelect }) {
  if (!examples?.length) return null

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-slate-400">
        <MessageSquare className="w-4 h-4" />
        <span>Try asking:</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {examples.map((example, idx) => (
          <button
            key={idx}
            onClick={() => onSelect(example)}
            className="text-sm text-slate-300 bg-slate-800 border border-slate-700 hover:border-blue-500/50 hover:bg-slate-750 px-3 py-2 rounded-lg transition-colors text-left cursor-pointer"
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  )
}
