import { createContext, useContext, useState, useCallback } from 'react'

const ChatContext = createContext(null)

export function ChatProvider({ children }) {
  const [messages, setMessages] = useState([])
  const [usage, setUsage] = useState(null)

  const addMessage = useCallback((msg) => {
    setMessages(prev => [...prev, msg])
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
  }, [])

  return (
    <ChatContext.Provider value={{ messages, addMessage, clearMessages, usage, setUsage }}>
      {children}
    </ChatContext.Provider>
  )
}

export const useChatContext = () => useContext(ChatContext)
