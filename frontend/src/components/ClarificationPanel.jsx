import { useState } from 'react'

export default function ClarificationPanel({
  query,
  question,
  ambiguities = [],
  onSubmit,
  disabled = false,
}) {
  const [answer, setAnswer] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    const trimmed = answer.trim()
    if (trimmed.length < 3 || disabled) return
    onSubmit(trimmed)
  }

  const pickAmbiguity = (text) => {
    setAnswer(text)
  }

  return (
    <div className="animate-slide-up rounded-xl border border-amber-800/50 bg-amber-950/20 p-5 space-y-4">
      <div className="flex items-start gap-3">
        <span className="text-2xl mt-0.5">🗺️</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-amber-200">Research Planner needs clarification</p>
          <p className="text-xs text-gray-500 mt-1">
            Your query: <span className="text-gray-400">{query}</span>
          </p>
        </div>
      </div>

      <p className="text-sm text-gray-200 leading-relaxed">{question}</p>

      {ambiguities.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Possible interpretations</p>
          <div className="flex flex-col gap-2">
            {ambiguities.map((item, i) => (
              <button
                key={i}
                type="button"
                onClick={() => pickAmbiguity(item)}
                disabled={disabled}
                className="text-left text-sm text-gray-300 px-3 py-2.5 rounded-lg border border-gray-800 hover:border-amber-700/60 hover:bg-gray-900/60 transition-all disabled:opacity-50"
              >
                <span className="text-amber-500/80 mr-2">{i + 1}.</span>
                {item}
              </button>
            ))}
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-3">
        <textarea
          value={answer}
          onChange={e => setAnswer(e.target.value)}
          placeholder="Describe what you mean, or pick an option above…"
          disabled={disabled}
          rows={3}
          className="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 disabled:opacity-50 resize-none"
        />
        <button
          type="submit"
          disabled={disabled || answer.trim().length < 3}
          className="px-4 py-2.5 rounded-lg text-sm font-medium bg-amber-600 hover:bg-amber-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {disabled ? 'Continuing research…' : 'Continue research'}
        </button>
      </form>
    </div>
  )
}
