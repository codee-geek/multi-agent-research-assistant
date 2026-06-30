const SEVERITY_STYLE = {
  critical: 'border-red-700/60 bg-red-950/30 text-red-300',
  high: 'border-orange-700/60 bg-orange-950/30 text-orange-300',
  medium: 'border-amber-700/60 bg-amber-950/30 text-amber-300',
  low: 'border-gray-700/60 bg-gray-900/40 text-gray-400',
}

const VERDICT_STYLE = {
  ok: 'text-green-400 border-green-800/50 bg-green-950/20',
  warn: 'text-amber-400 border-amber-800/50 bg-amber-950/20',
  fail: 'text-red-400 border-red-800/50 bg-red-950/20',
}

export default function BugBotPanel({ flags = [], report = null }) {
  if (!flags.length && !report) return null

  return (
    <div className="animate-slide-up rounded-xl border border-gray-800 bg-gray-900/40 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-lg">🤖</span>
        <div>
          <p className="text-sm font-medium text-white">BugBot Monitor</p>
          <p className="text-xs text-gray-500">Pipeline quality & expectation checks</p>
        </div>
        {report && (
          <span
            className={`ml-auto text-xs font-mono uppercase px-2 py-1 rounded-md border ${VERDICT_STYLE[report.verdict] ?? VERDICT_STYLE.warn}`}
          >
            {report.verdict}
          </span>
        )}
      </div>

      {flags.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500 uppercase tracking-wider">
            Live flags ({flags.length})
          </p>
          {flags.map((flag, i) => (
            <div
              key={i}
              className={`rounded-lg border px-3 py-2 text-xs ${SEVERITY_STYLE[flag.severity] ?? SEVERITY_STYLE.medium}`}
            >
              <div className="flex items-center gap-2 mb-0.5">
                <span className="font-mono uppercase text-[10px] opacity-80">{flag.severity}</span>
                <span className="opacity-60">·</span>
                <span className="font-medium">{flag.agent}</span>
                <span className="opacity-60">·</span>
                <span className="opacity-80">{flag.category}</span>
              </div>
              <p>{flag.message}</p>
              {flag.detail && <p className="mt-1 opacity-70">{flag.detail}</p>}
            </div>
          ))}
        </div>
      )}

      {report && (
        <div className="grid sm:grid-cols-2 gap-3 text-xs">
          {report.performed_well?.length > 0 && (
            <div>
              <p className="text-green-500/80 uppercase tracking-wider mb-1.5">Performed well</p>
              <ul className="space-y-1">
                {report.performed_well.map((item, i) => (
                  <li key={i} className="text-gray-400">+ {item}</li>
                ))}
              </ul>
            </div>
          )}
          {report.failed?.length > 0 && (
            <div>
              <p className="text-red-400/80 uppercase tracking-wider mb-1.5">Needs attention</p>
              <ul className="space-y-1">
                {report.failed.map((item, i) => (
                  <li key={i} className="text-gray-400">− {item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {report?.observations_file && (
        <p className="text-[10px] text-gray-600 font-mono truncate">
          Log: {report.observations_file}
        </p>
      )}
    </div>
  )
}
