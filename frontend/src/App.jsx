import { useState, useRef, useEffect, useCallback } from 'react'
import ChatMessage from './components/ChatMessage'

const WELCOME = {
  id: 0,
  role: 'assistant',
  content: '## Bonjour ! 👋\n\nJe suis votre assistant RAG. Posez-moi une question sur vos documents (CVs, devis, contrats…) ou demandez-moi d\'**indexer vos documents** pour commencer.',
}

let nextId = 1

export default function App() {
  const [messages, setMessages] = useState([WELCOME])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const pushMsg = useCallback((msg) => {
    setMessages(prev => [...prev, { id: nextId++, ...msg }])
  }, [])

  const updateLast = useCallback((patch) => {
    setMessages(prev => {
      const copy = [...prev]
      copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch }
      return copy
    })
  }, [])

  const sendMessage = useCallback(async (e) => {
    e?.preventDefault()
    const text = input.trim()
    if (!text || busy) return

    setInput('')
    setBusy(true)
    pushMsg({ role: 'user', content: text })

    // placeholder for streaming assistant reply
    const assistantId = nextId++
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '', isStreaming: true }])

    try {
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let accumulated = ''
      let statusMsgId = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const raw = decoder.decode(value, { stream: true })
        for (const line of raw.split('\n')) {
          if (!line.startsWith('data: ')) continue
          let data
          try { data = JSON.parse(line.slice(6)) } catch { continue }

          if (data.status) {
            // Show tool status as a transient system message above the assistant bubble
            if (statusMsgId !== null) {
              // update existing status
              setMessages(prev =>
                prev.map(m => m.id === statusMsgId ? { ...m, content: data.status } : m)
              )
            } else {
              statusMsgId = nextId++
              setMessages(prev => {
                const copy = [...prev]
                const idx = copy.findIndex(m => m.id === assistantId)
                copy.splice(idx, 0, { id: statusMsgId, role: 'status', content: data.status })
                return copy
              })
            }
          } else if (data.chunk) {
            accumulated += data.chunk
            setMessages(prev =>
              prev.map(m => m.id === assistantId ? { ...m, content: accumulated } : m)
            )
          } else if (data.done) {
            // remove status message, mark streaming done
            setMessages(prev =>
              prev
                .filter(m => m.id !== statusMsgId)
                .map(m => m.id === assistantId ? { ...m, isStreaming: false } : m)
            )
          } else if (data.error) {
            setMessages(prev =>
              prev
                .filter(m => m.id !== statusMsgId)
                .map(m =>
                  m.id === assistantId
                    ? { ...m, content: `❌ Erreur : ${data.error}`, isStreaming: false }
                    : m
                )
            )
          }
        }
      }
    } catch (err) {
      setMessages(prev =>
        prev.map(m =>
          m.id === (nextId - 1)
            ? { ...m, content: `❌ Erreur réseau : ${err.message}`, isStreaming: false }
            : m
        )
      )
    } finally {
      setBusy(false)
      inputRef.current?.focus()
    }
  }, [input, busy, pushMsg])

  const triggerIngest = useCallback(async () => {
    setBusy(true)
    pushMsg({ role: 'system', content: '📥 Indexation des documents en cours…' })
    try {
      const res = await fetch('/api/context', { method: 'POST' })
      const data = await res.json()
      pushMsg({
        role: 'system',
        content: data.status === 'success' ? '✅ Documents indexés avec succès.' : `❌ ${data.message}`,
      })
    } catch (err) {
      pushMsg({ role: 'system', content: `❌ Erreur réseau : ${err.message}` })
    } finally {
      setBusy(false)
    }
  }, [busy, pushMsg])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) sendMessage(e)
  }

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="flex items-center justify-between px-5 py-3 bg-gray-900 border-b border-gray-800 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xl">🤖</span>
          <h1 className="text-base font-semibold text-white">Assistant RAG & MCP</h1>
          <span className="text-xs text-gray-500 hidden sm:inline">· qwen2.5:0.5b</span>
        </div>
        <button
          onClick={triggerIngest}
          disabled={busy}
          className="text-xs px-3 py-1.5 bg-indigo-700 hover:bg-indigo-600 disabled:opacity-40 rounded-lg transition-colors"
        >
          {busy ? '⏳ En cours…' : '📥 Indexer les documents'}
        </button>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto py-4 space-y-1">
        {messages.map(msg => (
          <ChatMessage
            key={msg.id}
            role={msg.role}
            content={msg.content}
            isStreaming={msg.isStreaming}
          />
        ))}
        <div ref={bottomRef} />
      </main>

      {/* Input */}
      <footer className="px-4 py-3 bg-gray-900 border-t border-gray-800 shrink-0">
        <form onSubmit={sendMessage} className="flex gap-2 items-end max-w-4xl mx-auto">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={busy}
            rows={1}
            placeholder="Posez votre question… (Entrée pour envoyer, Shift+Entrée pour saut de ligne)"
            className="flex-1 resize-none bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-indigo-500 disabled:opacity-40 max-h-40 overflow-y-auto"
            style={{ fieldSizing: 'content' }}
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 rounded-xl text-sm font-medium transition-colors shrink-0"
          >
            Envoyer ↑
          </button>
        </form>
        <p className="text-center text-xs text-gray-600 mt-1.5">
          LaTeX supporté : <code className="text-gray-500">$...$</code> inline · <code className="text-gray-500">$$...$$</code> display
        </p>
      </footer>
    </div>
  )
}
