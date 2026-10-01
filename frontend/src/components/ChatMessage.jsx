import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'

const TOOL_LABELS = {
  search_cv: '🔍 Recherche dans les CVs…',
  search_cv_skills: '🛠️ Recherche compétences…',
  search_devis: '📄 Recherche dans les devis…',
  search_global: '🌐 Recherche globale…',
  ingest_documents: '📥 Ingestion des documents…',
}

export default function ChatMessage({ role, content, status, isStreaming }) {
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
