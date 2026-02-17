import { Database, User, Bot } from 'lucide-react'
import TeamTag from '../ui/TeamTag'

export default function ChatBubble({ message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[80%] ${isUser ? 'order-1' : 'order-1'}`}>
        {/* Icon */}
        <div className={`flex items-start gap-2.5 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
          <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
            isUser ? 'bg-blue-500/20' : 'bg-slate-700'
          }`}>
            {isUser ? (
              <User className="w-4 h-4 text-blue-400" />
            ) : (
              <Bot className="w-4 h-4 text-slate-400" />
            )}
          </div>

          <div className={`rounded-2xl px-4 py-2.5 ${
            isUser
              ? 'bg-blue-600 text-white rounded-br-md'
              : 'bg-slate-800 text-slate-200 border border-slate-700 rounded-bl-md'
          }`}>
            {/* Message content */}
            <div className="text-sm whitespace-pre-wrap leading-relaxed">
              {message.content}
            </div>

            {/* Context badge */}
            {!isUser && message.contextUsed === 'prediction_data' && (
              <div className="flex items-center gap-1 mt-2 pt-2 border-t border-slate-600/50">
                <Database className="w-3 h-3 text-blue-400" />
                <span className="text-xs text-blue-400">ML model data used</span>
              </div>
            )}

            {/* Referenced players */}
            {!isUser && message.playersReferenced?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2 pt-2 border-t border-slate-600/50">
                {message.playersReferenced.map((p) => (
                  <span key={p.player_id} className="inline-flex items-center gap-1">
                    <TeamTag abbr={p.team_abbr} size="sm" />
                    <span className="text-xs text-slate-400">{p.player_name}</span>
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
