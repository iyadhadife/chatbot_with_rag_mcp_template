import { useState, useRef, useEffect, useCallback } from 'react'
import ChatMessage from './components/ChatMessage'
import ChunksView from './components/ChunksView'
import Sidebar from './components/Sidebar'
import Composer from './components/Composer'
import Logo from './components/Logo'

const STORE_KEY = 'rag.conversations.v1'

const SUGGESTIONS = [
  { icon: '👤', text: 'À qui appartient le CV indexé ?' },
  { icon: '📝', text: 'Résume les documents indexés' },
  { icon: '💶', text: 'Quels montants apparaissent dans les devis ?' },
  { icon: '🛠️', text: 'Quelles compétences techniques sont mentionnées ?' },
]

let nextId = 1

const loadConversations = () => {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) || [] } catch { return [] }
}

const newConvId = () => `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState('chat')  // 'chat' | 'index'
  const [models, setModels] = useState([])
  const [model, setModel] = useState('')
  const [conversations, setConversations] = useState(loadConversations)
  const [activeId, setActiveId] = useState(newConvId)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const uploadRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Modèles Ollama installés localement
  useEffect(() => {
    fetch('/api/models')
      .then(r => r.json())
      .then(data => {
        setModels(data.models || [])
        setModel(data.default || (data.models && data.models[0]) || '')
      })
      .catch(() => { /* Ollama injoignable : le sélecteur reste vide */ })
  }, [])

  // Sauvegarde de la conversation courante (hors streaming en cours)
  useEffect(() => {
    if (busy || !messages.some(m => m.role === 'user')) return
    const firstQ = messages.find(m => m.role === 'user').content
    const title = firstQ.length > 60 ? firstQ.slice(0, 57) + '…' : firstQ
    setConversations(prev => {
      const entry = { id: activeId, title, messages: messages.map(({ isStreaming, ...m }) => m) }
      const next = [entry, ...prev.filter(c => c.id !== activeId)]
      try { localStorage.setItem(STORE_KEY, JSON.stringify(next.slice(0, 40))) } catch { /* quota */ }
      return next.slice(0, 40)
    })
  }, [messages, busy, activeId])

  const resetBackendHistory = () => { fetch('/api/reset', { method: 'POST' }).catch(() => {}) }

  const newChat = useCallback(() => {
    if (busy) return
    setMessages([])
    setActiveId(newConvId())
    setView('chat')
    resetBackendHistory()
    setTimeout(() => inputRef.current?.focus(), 0)
  }, [busy])

  const openConversation = useCallback((id) => {
    const conv = conversations.find(c => c.id === id)
    if (!conv || busy) return
    setMessages(conv.messages)
    setActiveId(id)
    setView('chat')
    resetBackendHistory()  // le contexte du serveur repart de zéro
  }, [conversations, busy])

  const deleteConversation = useCallback((id) => {
    setConversations(prev => {
      const next = prev.filter(c => c.id !== id)
      try { localStorage.setItem(STORE_KEY, JSON.stringify(next)) } catch { /* quota */ }
      return next
    })
    if (id === activeId) { setMessages([]); setActiveId(newConvId()) }
  }, [activeId])

  const pushMsg = useCallback((msg) => {
    setMessages(prev => [...prev, { id: nextId++, ...msg }])
  }, [])

  const sendMessage = useCallback(async (override) => {
    const text = (typeof override === 'string' ? override : input).trim()
    if (!text || busy) return

    setView('chat')
    setInput('')
    setBusy(true)
    pushMsg({ role: 'user', content: text })

    const assistantId = nextId++
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '', isStreaming: true }])

    try {
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, model }),
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
            if (statusMsgId !== null) {
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
          } else if (data.context) {
            setMessages(prev =>
              prev.map(m => m.id === assistantId
                ? { ...m, context: data.context, searchQuery: data.search_query || '' }
                : m)
            )
          } else if (data.chunk) {
            accumulated += data.chunk
            setMessages(prev =>
              prev.map(m => m.id === assistantId ? { ...m, content: accumulated } : m)
            )
          } else if (data.done) {
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
          m.id === assistantId
            ? { ...m, content: `❌ Erreur réseau : ${err.message}`, isStreaming: false }
            : m
        )
      )
    } finally {
      setBusy(false)
      inputRef.current?.focus()
    }
  }, [input, busy, model, pushMsg])

  const triggerIngest = useCallback(async () => {
    if (busy) return
    setView('chat')
    setBusy(true)
    pushMsg({ role: 'system', content: '📥 Réindexation complète en cours…' })
    try {
      const res = await fetch('/api/context', { method: 'POST' })
      const data = await res.json()
      pushMsg({
        role: 'system',
        content: data.status === 'success' ? `✅ ${data.message}` : `❌ ${data.message}`,
      })
    } catch (err) {
      pushMsg({ role: 'system', content: `❌ Erreur réseau : ${err.message}` })
    } finally {
      setBusy(false)
    }
  }, [busy, pushMsg])

  const uploadPdfs = useCallback(async (e) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    if (!files.length) return
    setView('chat')
    setBusy(true)
    pushMsg({ role: 'system', content: `📄 Ajout de ${files.length} PDF (${files.map(f => f.name).join(', ')})…` })
    try {
      const form = new FormData()
      files.forEach(f => form.append('files', f))
      const res = await fetch('/api/upload', { method: 'POST', body: form })
      const data = await res.json()
      pushMsg({ role: 'system', content: `${data.status === 'success' ? '✅' : '❌'} ${data.message}` })
    } catch (err) {
      pushMsg({ role: 'system', content: `❌ Erreur réseau : ${err.message}` })
    } finally {
      setBusy(false)
    }
  }, [pushMsg])

  const hasConversation = messages.length > 0
  const composer = (
    <Composer
      ref={inputRef}
      value={input}
      onChange={setInput}
      onSubmit={sendMessage}
      onAttach={() => uploadRef.current?.click()}
      disabled={busy}
    />
  )

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      <input ref={uploadRef} type="file" accept=".pdf" multiple hidden onChange={uploadPdfs} />

      {sidebarOpen && (
        <Sidebar
          view={view}
          onView={setView}
          busy={busy}
          conversations={conversations}
          activeId={activeId}
          onNewChat={newChat}
          onOpen={openConversation}
          onDelete={deleteConversation}
          onUpload={() => uploadRef.current?.click()}
          onReindex={triggerIngest}
          models={models}
          model={model}
          onModel={setModel}
          onCollapse={() => setSidebarOpen(false)}
        />
      )}

      <div className="flex-1 min-w-0 flex flex-col relative">
        {!sidebarOpen && (
          <button
            onClick={() => setSidebarOpen(true)}
            title="Afficher le panneau"
            className="absolute top-3 left-3 z-10 p-2 rounded-lg text-gray-400 hover:text-gray-100 hover:bg-gray-800"
          >
            <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2.5 3.5h11v9h-11zM6 3.5v9" />
            </svg>
          </button>
        )}

        {view === 'index' ? (
          <ChunksView />
        ) : !hasConversation ? (
          /* ── État vide : accueil centré ── */
          <main className="flex-1 overflow-y-auto flex items-center justify-center px-6">
            <div className="w-full max-w-2xl -mt-10">
              <Logo size={44} />
              <h1 className="mt-5 mb-6 text-3xl font-semibold tracking-tight text-gray-50">
                Bonjour, on interroge vos documents ?
              </h1>
              {composer}
              <ul className="mt-5 space-y-1">
                {SUGGESTIONS.map(s => (
                  <li key={s.text}>
                    <button
                      onClick={() => sendMessage(s.text)}
                      disabled={busy}
                      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-800/70 disabled:opacity-40 text-left transition-colors"
                    >
                      <span className="w-5 text-center text-gray-500">{s.icon}</span>
                      {s.text}
                    </button>
                  </li>
                ))}
                <li>
                  <button
                    onClick={triggerIngest}
                    disabled={busy}
                    className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-800/70 disabled:opacity-40 text-left transition-colors"
                  >
                    <span className="w-5 text-center text-gray-500">📥</span>
                    Indexer mes documents
                  </button>
                </li>
              </ul>
            </div>
          </main>
        ) : (
          /* ── Conversation ── */
          <>
            <main className="flex-1 overflow-y-auto">
              <div className="max-w-3xl mx-auto px-4 py-8 space-y-4">
                {messages.map(msg => (
                  <ChatMessage
                    key={msg.id}
                    role={msg.role}
                    content={msg.content}
                    context={msg.context}
                    searchQuery={msg.searchQuery}
                    isStreaming={msg.isStreaming}
                  />
                ))}
                <div ref={bottomRef} />
              </div>
            </main>
            <footer className="px-4 pb-5 pt-2 shrink-0">
              <div className="max-w-3xl mx-auto">{composer}</div>
            </footer>
          </>
        )}
      </div>
    </div>
  )
}
