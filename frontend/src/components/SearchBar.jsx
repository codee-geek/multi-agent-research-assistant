import { useState, useEffect } from 'react'

export default function SearchBar({ onSearch, disabled = false, initialQuery = '', compact = false }) {
  const [query, setQuery] = useState(initialQuery)
  const [maxSources, setMaxSources] = useState(5)

  useEffect(() => {
    if (initialQuery) setQuery(initialQuery)
  }, [initialQuery])

  const handleSubmit = (e) => {
    e.preventDefault()
    const trimmed = query.trim()
    if (trimmed.length < 5 || disabled) return
    onSearch(trimmed, maxSources)
  }

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className={`relative flex flex-col gap-2 ${compact ? '' : ''}`}>
        <div className="relative flex items-center">
          <span className="absolute left-4 text-gray-500 text-lg pointer-events-none">🔍</span>
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Ask a research question…"
            disabled={disabled}
            className={`
              w-full bg-gray-900 border border-gray-700 rounded-xl
              pl-11 pr-4 text-white placeholder-gray-600
              focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-colors
              ${compact ? 'py-3 text-sm' : 'py-4 text-base'}
            `}
          />
          <button
            type="submit"
            disabled={disabled || query.trim().length < 5}
            className={`
              absolute right-2 px-4 rounded-lg font-medium text-sm
              bg-brand-500 hover:bg-brand-600 text-white
              disabled:opacity-40 disabled:cursor-not-allowed
              transition-all flex items-center gap-2
              ${compact ? 'py-2' : 'py-2.5'}
            `}
          >
            {disabled ? (
              <>
                <Spinner />
                Researching…
              </>
            ) : (
              'Research'
            )}
          </button>
        </div>

        {!compact && (
          <div className="flex items-center gap-3 px-1">
            <label className="text-xs text-gray-500 whitespace-nowrap">Sources per query:</label>
            <input
              type="range"
              min={2}
              max={10}
              value={maxSources}
              onChange={e => setMaxSources(Number(e.target.value))}
              disabled={disabled}
              className="flex-1 accent-brand-500 disabled:opacity-50"
            />
            <span className="text-xs font-mono text-gray-400 w-4 text-center">{maxSources}</span>
          </div>
        )}
      </div>
    </form>
  )
}

function Spinner() {
  return (
    <svg className="animate-spin w-3.5 h-3.5" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}
