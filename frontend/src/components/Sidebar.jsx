import Logo from './Logo'

const Icon = ({ d, size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor"
       strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={d} />
  </svg>
)

const ICONS = {
  plus:   'M8 3v10M3 8h10',
  upload: 'M8 11V3M4.5 6.5 8 3l3.5 3.5M3 13h10',
  sync:   'M13 8a5 5 0 1 1-1.6-3.7M13 2.5v3h-3',
  trash:  'M3.5 4.5h9M6.5 4.5V3h3v1.5M5 4.5l.5 8h5l.5-8',
  panel:  'M2.5 3.5h11v9h-11zM6 3.5v9',
}

function NavButton({ icon, children, onClick, disabled, active }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-left transition-colors disabled:opacity-40 ${
        active ? 'bg-gray-800 text-gray-100' : 'text-gray-300 hover:bg-gray-800/70'
      }`}
    >
      <span className="text-gray-400"><Icon d={ICONS[icon]} /></span>
      {children}
    </button>
  )
}

export default function Sidebar({
  view, onView, busy, conversations, activeId,
  onNewChat, onOpen, onDelete, onUpload, onReindex,
  models, model, onModel, onCollapse,
}) {
  return (
    <aside className="w-64 shrink-0 bg-sidebar border-r border-gray-800 flex flex-col">
      {/* Marque */}
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <div className="flex items-center gap-2.5">
          <Logo size={26} />
          <span className="font-semibold text-gray-100">RAG Assistant</span>
        </div>
        <button onClick={onCollapse} title="Masquer le panneau"
                className="text-gray-500 hover:text-gray-200 p-1 rounded-md hover:bg-gray-800">
          <Icon d={ICONS.panel} />
        </button>
      </div>

      {/* Onglets Chat / Index */}
      <div className="px-3 pb-3">
        <div className="grid grid-cols-2 bg-gray-900 rounded-lg p-1 text-sm">
          {[['chat', 'Chat'], ['index', 'Index']].map(([key, label]) => (
            <button
              key={key}
              onClick={() => onView(key)}
              className={`py-1.5 rounded-md transition-colors ${
                view === key ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Actions */}
      <nav className="px-3 space-y-0.5">
        <NavButton icon="plus" onClick={onNewChat} disabled={busy} active={view === 'chat'}>
          Nouveau chat
        </NavButton>
        <NavButton icon="upload" onClick={onUpload} disabled={busy}>Ajouter des PDF</NavButton>
        <NavButton icon="sync" onClick={onReindex} disabled={busy}>
          {busy ? 'En cours…' : 'Tout réindexer'}
        </NavButton>
      </nav>

      {/* Conversations */}
      <div className="flex-1 min-h-0 overflow-y-auto px-3 mt-5">
        {conversations.length > 0 && (
          <p className="px-3 mb-1 text-xs text-gray-500">Conversations</p>
        )}
        <ul className="space-y-0.5">
          {conversations.map(c => (
            <li key={c.id} className="group relative">
              <button
                onClick={() => onOpen(c.id)}
                disabled={busy}
                title={c.title}
                className={`w-full text-left px-3 py-2 pr-8 rounded-lg text-sm truncate transition-colors disabled:opacity-60 ${
                  c.id === activeId && view === 'chat'
                    ? 'bg-gray-800 text-gray-100'
                    : 'text-gray-300 hover:bg-gray-800/70'
                }`}
              >
                {c.title}
              </button>
              <button
                onClick={() => onDelete(c.id)}
                title="Supprimer"
                className="absolute right-2 top-1/2 -translate-y-1/2 hidden group-hover:block text-gray-500 hover:text-red-400"
              >
                <Icon d={ICONS.trash} size={14} />
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* Pied : modèle + espace */}
      <div className="p-3 border-t border-gray-800 space-y-2">
        <select
          value={model}
          onChange={e => onModel(e.target.value)}
          disabled={busy || models.length === 0}
          title="Modèle Ollama (installé localement)"
          className="w-full text-xs bg-gray-900 border border-gray-700 rounded-lg px-2.5 py-2 text-gray-300 focus:outline-none focus:border-indigo-500 disabled:opacity-40"
        >
          {models.length === 0 && <option value="">Aucun modèle</option>}
          {models.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <div className="flex items-center gap-3 px-1 pt-1">
          <div className="w-8 h-8 rounded-full bg-gray-700 text-gray-200 flex items-center justify-center text-sm">
            L
          </div>
          <div className="leading-tight">
            <div className="text-sm text-gray-100">Local</div>
            <div className="text-xs text-gray-500">Ollama · ChromaDB</div>
          </div>
        </div>
      </div>
    </aside>
  )
}
