export default function SelfReviewPanel({ review }) {
  if (!review || review.quality_score == null) return null

  const score = review.quality_score
  const scoreColor =
    score >= 8 ? 'text-green-400' : score >= 6 ? 'text-yellow-400' : 'text-red-400'
  const scoreBg =
    score >= 8 ? 'bg-green-900/40 border-green-800/40' : score >= 6 ? 'bg-yellow-900/40 border-yellow-800/40' : 'bg-red-900/40 border-red-800/40'

  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/50 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">🔎</span>
          <h3 className="text-sm font-semibold text-white">Self-Review</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded-full border ${scoreBg} ${scoreColor} font-medium`}>
            {score.toFixed(1)} / 10
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            review.approved
              ? 'bg-green-900/60 text-green-400 border border-green-800/40'
              : 'bg-red-900/60 text-red-400 border border-red-800/40'
          }`}>
            {review.approved ? 'Approved' : 'Needs improvement'}
          </span>
        </div>
      </div>

      {review.overall_assessment && (
        <div className="px-6 py-4 border-b border-gray-800">
          <p className="text-sm text-gray-300 leading-relaxed">{review.overall_assessment}</p>
        </div>
      )}

      <div className="grid sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-gray-800">
        {review.strengths?.length > 0 && (
          <ReviewSection title="Strengths" items={review.strengths} color="text-green-400" />
        )}
        {review.weaknesses?.length > 0 && (
          <ReviewSection title="Weaknesses" items={review.weaknesses} color="text-yellow-400" />
        )}
      </div>

      {review.hallucination_risks?.length > 0 && (
        <div className="px-6 py-4 border-t border-gray-800 bg-red-950/20">
          <p className="text-xs font-medium text-red-400 uppercase tracking-wider mb-2">Hallucination Risks</p>
          <ul className="space-y-1.5">
            {review.hallucination_risks.map((r, i) => (
              <li key={i} className="text-xs text-red-300/80 flex items-start gap-2">
                <span className="mt-0.5 text-red-500">⚠</span>{r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {review.improvement_suggestions?.length > 0 && (
        <div className="px-6 py-4 border-t border-gray-800 bg-gray-950/40">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Suggestions</p>
          <ul className="space-y-1.5">
            {review.improvement_suggestions.map((s, i) => (
              <li key={i} className="text-xs text-gray-400 flex items-start gap-2">
                <span className="mt-0.5 text-brand-500">→</span>{s}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function ReviewSection({ title, items, color }) {
  return (
    <div className="px-6 py-4">
      <p className={`text-xs font-medium uppercase tracking-wider mb-2 ${color}`}>{title}</p>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="text-xs text-gray-400 flex items-start gap-2">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-gray-600 flex-shrink-0" />
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}
