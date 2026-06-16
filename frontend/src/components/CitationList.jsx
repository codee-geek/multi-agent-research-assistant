import { useState } from 'react'

export default function CitationList({ citations = [], apaRefs = [] }) {
  const [showApa, setShowApa] = useState(false)

  if (!citations.length) return null

  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/50 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">📚</span>
          <h3 className="text-sm font-semibold text-white">
            References <span className="text-gray-500 font-normal">({citations.length})</span>
          </h3>
        </div>
        {apaRefs.length > 0 && (
          <button
            onClick={() => setShowApa(v => !v)}
            className="text-xs text-gray-500 hover:text-gray-300 px-3 py-1.5 rounded-lg border border-gray-800 hover:border-gray-700 transition-colors"
          >
            {showApa ? 'Hide APA' : 'Show APA'}
          </button>
        )}
      </div>

      {showApa && apaRefs.length > 0 && (
        <div className="px-6 py-4 border-b border-gray-800 bg-gray-950/40">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">APA 7th Edition</p>
          <ol className="space-y-2">
            {apaRefs.map((ref, i) => (
              <li key={i} className="text-xs font-mono text-gray-400 leading-relaxed">
                {i + 1}. {ref}
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="divide-y divide-gray-800/60">
        {citations.map((cit) => (
          <CitationCard key={cit.index} citation={cit} />
        ))}
      </div>
    </div>
  )
}

function CitationCard({ citation }) {
  let hostname = ''
  try {
    hostname = new URL(citation.url).hostname.replace('www.', '')
  } catch { hostname = citation.url }

  return (
    <div className="px-6 py-4 hover:bg-gray-800/20 transition-colors group">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 w-6 h-6 rounded-md bg-gray-800 text-gray-500 text-xs font-mono flex items-center justify-center flex-shrink-0">
          {citation.index}
        </span>
        <div className="flex-1 min-w-0">
          <a
            href={citation.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium text-gray-200 group-hover:text-white hover:underline transition-colors line-clamp-2"
          >
            {citation.title}
          </a>
          <div className="flex items-center gap-2 mt-1 mb-2">
            <span className="text-xs text-gray-600">{hostname}</span>
            <span className="text-gray-700">·</span>
            <a
              href={citation.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-brand-500 hover:text-brand-400 truncate max-w-[220px]"
            >
              {citation.url}
            </a>
          </div>
          {citation.excerpt && (
            <blockquote className="text-xs text-gray-400 italic border-l-2 border-gray-700 pl-3 my-2 leading-relaxed">
              "{citation.excerpt}"
            </blockquote>
          )}
          {citation.relevance && (
            <p className="text-xs text-gray-500">{citation.relevance}</p>
          )}
        </div>
      </div>
    </div>
  )
}
