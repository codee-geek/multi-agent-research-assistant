import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function ResearchReport({ title, summary, keyFindings, subQueries, totalSources, elapsed }) {
  const handleCopy = () => {
    navigator.clipboard.writeText(`# ${title}\n\n${summary}`)
  }

  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/50 overflow-hidden">
      {/* Report header */}
      <div className="px-6 py-5 border-b border-gray-800 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-900/60 text-green-400 border border-green-800/40">
              Research Complete
            </span>
            {elapsed != null && (
              <span className="text-xs text-gray-600">in {elapsed}s</span>
            )}
            {totalSources != null && (
              <span className="text-xs text-gray-600">· {totalSources} sources</span>
            )}
          </div>
          <h2 className="text-xl font-bold text-white leading-snug">{title}</h2>
        </div>
        <button
          onClick={handleCopy}
          className="flex-shrink-0 text-xs text-gray-500 hover:text-gray-300 px-3 py-1.5 rounded-lg border border-gray-800 hover:border-gray-700 transition-colors"
          title="Copy markdown"
        >
          Copy
        </button>
      </div>

      {/* Key findings */}
      {keyFindings?.length > 0 && (
        <div className="px-6 py-4 border-b border-gray-800 bg-gray-900/30">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Key Findings</p>
          <ul className="space-y-2">
            {keyFindings.map((finding, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm text-gray-300">
                <span className="mt-1 w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0" />
                {finding}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Full summary */}
      <div className="px-6 py-5">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">Full Summary</p>
        <div className="prose-research">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {summary ?? ''}
          </ReactMarkdown>
        </div>
      </div>

      {/* Sub-queries used */}
      {subQueries?.length > 0 && (
        <div className="px-6 py-4 border-t border-gray-800 bg-gray-950/40">
          <p className="text-xs text-gray-600 mb-2">Queries executed by the Planner agent:</p>
          <div className="flex flex-wrap gap-2">
            {subQueries.map((q, i) => (
              <span key={i} className="text-xs font-mono text-gray-500 bg-gray-900 border border-gray-800 px-2 py-1 rounded-md">
                {q}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
