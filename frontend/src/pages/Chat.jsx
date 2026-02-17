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
        <div
          className="w-16 h-16 rounded-full flex items-center justify-center"
          style={{ backgroundColor: 'var(--bg-surface)', boxShadow: '0 0 30px rgba(255,107,53,0.1)' }}
        >
          <Lock className="w-8 h-8" style={{ color: '#FF6B35' }} />
        </div>
        <h2 className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>Sign in to use Chat</h2>
        <p className="text-sm max-w-md text-center" style={{ color: 'var(--text-secondary)' }}>
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
      <div className="flex items-center justify-between pb-4 mb-4" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center gap-2">
          <MessageSquare className="w-5 h-5" style={{ color: '#FF6B35' }} />
          <h1 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>NBA Injury Chat</h1>
        </div>
        <div className="w-48">
          <UsageBar usage={usage} />
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && !sending && (
          <div className="flex flex-col items-center justify-center py-16">
            <svg width="40" height="40" viewBox="0 0 48 48" fill="none" className="mb-4 opacity-30">
              <circle cx="24" cy="24" r="22" fill="#FF6B35" stroke="#CC5529" strokeWidth="1.5" />
              <path d="M2 24 C16 20, 32 28, 46 24" stroke="#CC5529" strokeWidth="1.2" fill="none" />
              <path d="M24 2 C20 16, 28 32, 24 46" stroke="#CC5529" strokeWidth="1.2" fill="none" />
            </svg>
            <p className="text-sm mb-6" style={{ color: 'var(--text-muted)' }}>
              Ask about NBA injuries, predictions, and what-if scenarios
            </p>
            <ExampleQueries examples={examples} onSelect={handleExampleSelect} />
          </div>
        )}

        {messages.map((msg, idx) => (
          <ChatBubble key={idx} message={msg} />
        ))}

        {/* Typing indicator */}
        {sending && (
          <div className="flex justify-start">
            <div
              className="rounded-2xl rounded-bl-md px-4 py-3"
              style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}
            >
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: '#FF6B35', animation: 'dot-pulse 1.4s ease-in-out infinite' }} />
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: '#FF6B35', animation: 'dot-pulse 1.4s ease-in-out 0.2s infinite' }} />
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: '#FF6B35', animation: 'dot-pulse 1.4s ease-in-out 0.4s infinite' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Rate limit banner */}
      {rateLimitHit && (
        <div
          className="rounded-lg px-4 py-2 mb-3 text-sm text-center"
          style={{
            backgroundColor: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.2)',
            color: '#FCA5A5',
          }}
        >
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
