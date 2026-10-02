import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'

const TOOL_LABELS = {
  ingest_documents: '📥 Ingestion des documents…',
  search_documents: '🔍 Recherche documentaire…',
}

function ContextPanel({ context, searchQuery }) {
  const [open, setOpen] = useState(false)
  if (!context) return null

  // Parse blocks separated by "--- [...] ---"
  const blocks = context.split(/\n(?=---\s*\[)/).filter(Boolean)

  return (
    <div className="mt-2 border border-gray-700 rounded-xl overflow-hidden text-xs">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 bg-gray-700/50 hover:bg-gray-700 text-gray-300 transition-colors"
      >
        <div className="flex flex-col items-start gap-0.5">
          <span className="font-medium">📄 Sources RAG ({blocks.length} passage{blocks.length > 1 ? 's' : ''})</span>
          {searchQuery && (
            <span className="text-gray-500 font-normal italic">🔍 « {searchQuery} »</span>
          )}
        </div>
        <span className="text-gray-500 shrink-0 ml-2">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="divide-y divide-gray-700/50 max-h-80 overflow-y-auto">
          {blocks.map((block, i) => {
            // Extract header line "--- [...] ---" and body
            const headerMatch = block.match(/^---\s*\[(.+?)\]\s*---\n?/)
            const header = headerMatch ? headerMatch[1] : null
            const body = headerMatch ? block.slice(headerMatch[0].length) : block

            // Parse header fields (TYPE, SOURCE, SCORE, etc.)
            const fields = header
              ? Object.fromEntries(
                  header.split(' | ').map(f => {
                    const idx = f.indexOf(':')
                    return idx > -1
                      ? [f.slice(0, idx).trim(), f.slice(idx + 1).trim()]
                      : [f, '']
                  })
                )
              : {}

            const score = fields['SCORE'] ? parseFloat(fields['SCORE']) : null
            const scoreColor = score == null ? '' : score >= 0.7 ? 'text-green-400' : score >= 0.4 ? 'text-yellow-400' : 'text-red-400'

            return (
              <div key={i} className="px-3 py-2 bg-gray-800/40">
                {header && (
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 mb-1.5 text-[11px]">
                    {fields['TYPE'] && (
                      <span className="bg-indigo-900/60 text-indigo-300 px-1.5 py-0.5 rounded font-mono">
                        {fields['TYPE']}
                      </span>
                    )}
                    {fields['SOURCE'] && (
                      <span className="text-gray-400 truncate max-w-[200px]" title={fields['SOURCE']}>
                        📁 {fields['SOURCE']}
                      </span>
                    )}
                    {fields['EXTRAIT'] && (
                      <span className="text-gray-500 italic">{fields['EXTRAIT']}</span>
                    )}
                    {score != null && (
                      <span className={`ml-auto font-mono ${scoreColor}`}>
                        ≈{fields['SCORE']}
                      </span>
                    )}
                  </div>
                )}
                <pre className="whitespace-pre-wrap text-gray-300 leading-relaxed font-sans">{body.trim()}</pre>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function ChatMessage({ role, content, context, searchQuery, isStreaming }) {
  if (role === 'status') {
    return (
      <div className="flex justify-start px-4 py-1">
        <span className="text-xs text-indigo-400 italic animate-pulse">
          {TOOL_LABELS[content] ?? `⚙️ ${content}…`}
        </span>
      </div>
    )
  }

  if (role === 'system') {
    return (
      <div className="flex justify-center px-4 py-1">
        <span className="text-xs text-yellow-400/80 italic bg-yellow-900/20 px-3 py-1 rounded-full">
          {content}
        </span>
      </div>
    )
  }

  const isUser = role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} px-4 py-1`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center text-sm mr-2 mt-0.5 shrink-0">
          🤖
        </div>
      )}
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${
          isUser
            ? 'bg-indigo-600 text-white rounded-tr-sm'
            : 'bg-gray-800 text-gray-100 rounded-tl-sm border border-gray-700'
        }`}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{content}</span>
        ) : (
          <div className="prose-chat">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex]}
            >
              {content}
            </ReactMarkdown>
            {isStreaming && (
              <span className="inline-block w-2 h-4 bg-indigo-400 animate-pulse ml-0.5 align-middle" />
            )}
            <ContextPanel context={context} searchQuery={searchQuery} />
          </div>
        )}
      </div>
      {isUser && (
        <div className="w-7 h-7 rounded-full bg-gray-600 flex items-center justify-center text-sm ml-2 mt-0.5 shrink-0">
          👤
        </div>
      )}
    </div>
  )
}
