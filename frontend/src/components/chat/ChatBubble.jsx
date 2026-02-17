import { Database, User, Bot } from 'lucide-react'
import TeamTag from '../ui/TeamTag'

export default function ChatBubble({ message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[80%] ${isUser ? 'order-1' : 'order-1'}`}>
        {/* Icon */}
        <div className={`flex items-start gap-2.5 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5"
            style={{
              backgroundColor: isUser ? 'rgba(255,107,53,0.2)' : 'var(--bg-elevated)',
            }}
          >
            {isUser ? (
              <User className="w-4 h-4" style={{ color: '#FF6B35' }} />
            ) : (
              <Bot className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
            )}
          </div>

          <div
            className={`rounded-2xl px-4 py-2.5 ${isUser ? 'rounded-br-md' : 'rounded-bl-md'}`}
            style={{
              backgroundColor: isUser ? 'rgba(255,107,53,0.9)' : 'var(--bg-surface)',
              color: isUser ? 'white' : 'var(--text-primary)',
              border: isUser ? 'none' : '1px solid var(--border-subtle)',
            }}
          >
            {/* Message content */}
            <div className="text-sm whitespace-pre-wrap leading-relaxed">
              {message.content}
            </div>

            {/* Context badge */}
            {!isUser && message.contextUsed === 'prediction_data' && (
              <div className="flex items-center gap-1 mt-2 pt-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <Database className="w-3 h-3" style={{ color: 'var(--accent-blue)' }} />
                <span className="text-xs" style={{ color: 'var(--accent-blue)' }}>ML model data used</span>
              </div>
            )}

            {/* Referenced players */}
            {!isUser && message.playersReferenced?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2 pt-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                {message.playersReferenced.map((p) => (
                  <span key={p.player_id} className="inline-flex items-center gap-1">
                    <TeamTag abbr={p.team_abbr} size="sm" />
                    <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{p.player_name}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
