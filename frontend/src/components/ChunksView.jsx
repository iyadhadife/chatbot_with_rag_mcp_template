import { useState, useEffect, useCallback } from 'react'

const DOC_TYPE_COLORS = {
  CV:      'bg-emerald-900/40 text-emerald-300 border-emerald-700/50',
  DEVIS:   'bg-sky-900/40 text-sky-300 border-sky-700/50',
  FACTURE: 'bg-amber-900/40 text-amber-300 border-amber-700/50',
  CONTRAT: 'bg-violet-900/40 text-violet-300 border-violet-700/50',
  RAPPORT: 'bg-rose-900/40 text-rose-300 border-rose-700/50',
}

// Champs mis en avant dans la fiche du chunk (dans cet ordre)
const PRIORITY_FIELDS = [
  'section_type', 'section_name', 'skills', 'amounts', 'tva_rate',
  'dates', 'devis_number', 'keywords', 'local_summary',
  'importance_score', 'confidence_score', 'page_number',
]

// Champs techniques peu utiles à l'affichage détaillé
const HIDDEN_FIELDS = new Set(['source', 'doc_type', 'doc_title', 'document_id'])

function Badge({ children, className = '' }) {
  return (
    <span className={`inline-block text-[11px] px-2 py-0.5 rounded-full border ${className}`}>
      {children}
    </span>
  )
}

function isEmpty(v) {
  if (v === null || v === undefined || v === '') return true
  if (Array.isArray(v) && v.length === 0) return true
  return false
}

function MetaValue({ value }) {
  if (Array.isArray(value)) {
    return (
      <div className="flex flex-wrap gap-1">
        {value.map((v, i) => (
          <span key={i} className="text-[11px] bg-gray-700/60 text-gray-200 px-1.5 py-0.5 rounded">
            {String(v)}
          </span>
        ))}
      </div>
    )
  }
  if (typeof value === 'number') {
    return <span className="text-gray-200 font-mono text-xs">{value}</span>
  }
  return <span className="text-gray-200 break-words">{String(value)}</span>
}

function MetaRow({ label, value }) {
  return (
    <div className="grid grid-cols-[130px_1fr] gap-2 py-1 border-b border-gray-800/60 last:border-0">
      <span className="text-gray-500 text-xs font-medium">{label}</span>
      <div className="text-xs"><MetaValue value={value} /></div>
    </div>
  )
}

function ChunkCard({ chunk, index }) {
  const [showAll, setShowAll] = useState(false)
  const meta = chunk.metadata || {}

  const priority = PRIORITY_FIELDS
    .filter(k => k in meta && !isEmpty(meta[k]))
    .map(k => [k, meta[k]])

  const rest = Object.entries(meta)
    .filter(([k, v]) => !PRIORITY_FIELDS.includes(k) && !HIDDEN_FIELDS.has(k) && !isEmpty(v))

  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-xl overflow-hidden">
      {/* En-tête du chunk */}
      <div className="flex items-center justify-between gap-2 px-3 py-2 bg-gray-800/50 border-b border-gray-800">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[11px] font-mono text-gray-500 shrink-0">#{index}</span>
          {chunk.section_type && (
            <Badge className="bg-indigo-900/40 text-indigo-300 border-indigo-700/50">
              {chunk.section_type}
            </Badge>
          )}
          {chunk.section_name && chunk.section_name !== chunk.section_type && (
            <span className="text-xs text-gray-400 truncate">{chunk.section_name}</span>
          )}
        </div>
        <span className="text-[10px] font-mono text-gray-600 truncate max-w-[40%]" title={chunk.id}>
          {chunk.id}
        </span>
      </div>

      {/* Texte du chunk */}
      <pre className="px-3 py-2 text-xs text-gray-200 whitespace-pre-wrap font-sans leading-relaxed max-h-64 overflow-y-auto">
        {chunk.text}
      </pre>

      {/* Métadonnées prioritaires */}
      {priority.length > 0 && (
        <div className="px-3 py-2 bg-gray-950/40 border-t border-gray-800">
          {priority.map(([k, v]) => <MetaRow key={k} label={k} value={v} />)}
        </div>
      )}

      {/* Métadonnées complètes (repliées) */}
      {rest.length > 0 && (
        <div className="px-3 pb-2 bg-gray-950/40">
          <button
            onClick={() => setShowAll(s => !s)}
            className="text-[11px] text-indigo-400 hover:text-indigo-300 py-1"
          >
            {showAll ? '▾ Masquer' : `▸ Toutes les métadonnées (${rest.length})`}
          </button>
          {showAll && (
            <div className="mt-1">
              {rest.map(([k, v]) => <MetaRow key={k} label={k} value={v} />)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DocumentGroup({ doc }) {
  const [open, setOpen] = useState(true)
  const color = DOC_TYPE_COLORS[doc.doc_type] || 'bg-gray-700/40 text-gray-300 border-gray-600/50'

  return (
    <section className="border border-gray-800 rounded-2xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 bg-gray-900 hover:bg-gray-800/80 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-gray-500 text-sm">{open ? '▾' : '▸'}</span>
          <span className="text-2xl">📄</span>
          <div className="min-w-0 text-left">
            <div className="text-sm font-medium text-gray-100 truncate">
              {doc.doc_title || doc.source}
            </div>
            <div className="text-xs text-gray-500 truncate">{doc.source}</div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {doc.doc_type && <Badge className={color}>{doc.doc_type}</Badge>}
          <Badge className="bg-gray-800 text-gray-400 border-gray-700">
            {doc.chunk_count} chunk{doc.chunk_count > 1 ? 's' : ''}
          </Badge>
        </div>
      </button>

      {open && (
        <div className="p-3 space-y-3 bg-gray-950">
          {doc.chunks.map((c, i) => <ChunkCard key={c.id || i} chunk={c} index={i} />)}
        </div>
      )}
    </section>
  )
}

export default function ChunksView() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/chunks')
      const json = await res.json()
      if (json.error && (!json.documents || json.documents.length === 0)) {
        setError(json.error)
      }
      setData(json)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-4 py-5 space-y-4">
        {/* Barre d'état */}
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-400">
            {data && !loading && (
              <>
                <span className="text-gray-100 font-semibold">{data.total ?? 0}</span> chunks ·{' '}
                <span className="text-gray-100 font-semibold">{data.documents?.length ?? 0}</span> document(s)
              </>
            )}
            {loading && <span className="animate-pulse">Chargement de l'index…</span>}
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 rounded-lg transition-colors"
          >
            ↻ Rafraîchir
          </button>
        </div>

        {error && (
          <div className="text-sm text-red-400 bg-red-900/20 border border-red-800/50 rounded-xl px-4 py-3">
            ❌ {error}
          </div>
        )}

        {!loading && data && (!data.documents || data.documents.length === 0) && !error && (
          <div className="text-center text-gray-500 py-16">
            <div className="text-4xl mb-3">🗂️</div>
            <p className="text-sm">Aucun document indexé.</p>
            <p className="text-xs mt-1">Lancez l'indexation depuis l'onglet « Chat ».</p>
          </div>
        )}

        {data?.documents?.map(doc => (
          <DocumentGroup key={doc.document_id || doc.source} doc={doc} />
        ))}
      </div>
    </div>
  )
}
