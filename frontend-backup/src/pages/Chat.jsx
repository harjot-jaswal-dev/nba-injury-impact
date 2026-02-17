import { useState, useEffect, useRef } from 'react'
import { Lock, MessageSquare } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useChatContext } from '../context/ChatContext'
import { sendChat, getChatExamples } from '../services/api'
import ChatBubble from '../components/chat/ChatBubble'
import ChatInput from '../components/chat/ChatInput'
import ExampleQueries from '../components/chat/ExampleQueries'
import UsageBar from '../components/chat/UsageBar'
import LoadingSpinner from '../components/ui/LoadingSpinner'

export default function Chat() {
  const { user, loading: authLoading, login } = useAuth()
  const { messages, addMessage, usage, setUsage } = useChatContext()
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [examples, setExamples] = useState([])
  const [rateLimitHit, setRateLimitHit] = useState(false)
  const messagesEndRef = useRef(null)

  // Load example queries
  useEffect(() => {
    getChatExamples()
      .then((data) => setExamples(data.examples || []))
      .catch(() => {})
  }, [])

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || sending || rateLimitHit) return

    setInput('')
    addMessage({ role: 'user', content: text })
    setSending(true)

    try {
      const response = await sendChat(text)
      addMessage({
        role: 'assistant',
        content: response.response,
        contextUsed: response.context_used,
        playersReferenced: response.players_referenced,
      })
      if (response.usage) {
        setUsage(response.usage)
        if (response.usage.remaining <= 0) {
          setRateLimitHit(true)
        }
      }
    } catch (err) {
      if (err?.response?.status === 429) {
        setRateLimitHit(true)
        addMessage({
          role: 'assistant',
          content: 'Daily chat limit reached. Your limit resets at midnight.',
        })
      } else if (err?.response?.status === 401) {
        addMessage({
          role: 'assistant',
          content: 'Please sign in to use the chat feature.',
        })
      } else {
        addMessage({
          role: 'assistant',
          content: err?.response?.data?.detail || 'Something went wrong. Please try again.',
        })
      }
    } finally {
      setSending(false)
    }
  }

  const handleExampleSelect = (text) => {
    setInput(text)
  }

  // Auth loading state — show spinner, not "please sign in"
  if (authLoading) {
    return <LoadingSpinner text="Checking authentication..." />
  }

  // Auth gate
  if (!user) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center">
          <Lock className="w-8 h-8 text-slate-500" />
        </div>
        <h2 className="text-xl font-semibold text-slate-200">Sign in to use Chat</h2>
        <p className="text-sm text-slate-400 max-w-md text-center">
          Chat with our AI about NBA injuries, player performance, and what-if scenarios. Powered by Claude.
        </p>
        <button onClick={login} className="btn-primary mt-2">
          Sign in with Google
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-[calc(100vh-140px)]">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-700 mb-4">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-blue-500" />
          <h1 className="text-lg font-bold text-slate-100">NBA Injury Chat</h1>
        </div>
        <div className="w-48">
          <UsageBar usage={usage} />
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && !sending && (
          <div className="py-8">
            <ExampleQueries examples={examples} onSelect={handleExampleSelect} />
          </div>
        )}

        {messages.map((msg, idx) => (
          <ChatBubble key={idx} message={msg} />
        ))}

        {/* Typing indicator */}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-slate-800 border border-slate-700 rounded-2xl rounded-bl-md px-4 py-3">
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Rate limit banner */}
      {rateLimitHit && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2 mb-3 text-sm text-red-300 text-center">
          Daily limit reached. Resets at midnight.
        </div>
      )}

      {/* Input */}
      <ChatInput
        value={input}
        onChange={setInput}
        onSend={handleSend}
        disabled={rateLimitHit}
        loading={sending}
      />
    </div>
  )
}
