const AGENT_META = {
  planner: {
    label: 'Research Planner',
    icon: '🗺️',
    color: 'from-blue-500 to-blue-600',
    ring: 'ring-blue-500/30',
    bg: 'bg-blue-950/30',
    border: 'border-blue-800/40',
    badge: 'bg-blue-900/60 text-blue-300',
  },
  retriever: {
    label: 'Web Retriever',
    icon: '🔍',
    color: 'from-emerald-500 to-teal-600',
    ring: 'ring-emerald-500/30',
    bg: 'bg-emerald-950/30',
    border: 'border-emerald-800/40',
    badge: 'bg-emerald-900/60 text-emerald-300',
  },
  summarizer: {
    label: 'Synthesizer',
    icon: '📝',
    color: 'from-violet-500 to-purple-600',
    ring: 'ring-violet-500/30',
    bg: 'bg-violet-950/30',
    border: 'border-violet-800/40',
    badge: 'bg-violet-900/60 text-violet-300',
  },
  citation_formatter: {
    label: 'Citation Formatter',
    icon: '📚',
    color: 'from-amber-500 to-orange-600',
    ring: 'ring-amber-500/30',
    bg: 'bg-amber-950/30',
    border: 'border-amber-800/40',
    badge: 'bg-amber-900/60 text-amber-300',
  },
}

export default function AgentTimeline({ agents, isStreaming }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Agent Pipeline</h2>
        {isStreaming && (
          <span className="flex items-center gap-1.5 text-xs text-brand-400">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse-slow"></span>
            Running
          </span>
        )}
      </div>

      <div className="relative">
        {/* Connector line */}
        <div className="absolute left-5 top-8 bottom-8 w-px bg-gray-800 z-0" />

        <div className="space-y-3 relative z-10">
          {agents.map((agent, i) => (
            <AgentCard key={agent.name} agent={agent} index={i} />
          ))}
        </div>
      </div>
    </div>
  )
}

function AgentCard({ agent, index }) {
  const meta = AGENT_META[agent.name] ?? {
    label: agent.label ?? agent.name,
    icon: agent.icon ?? '🤖',
    color: 'from-gray-500 to-gray-600',
    ring: 'ring-gray-500/30',
    bg: 'bg-gray-900/30',
    border: 'border-gray-700/40',
    badge: 'bg-gray-800 text-gray-400',
  }

  const isDone = agent.status === 'done'
  const isRunning = agent.status === 'running'

  return (
    <div className={`rounded-xl border p-4 transition-all duration-300 ${meta.bg} ${meta.border} ${isRunning ? `ring-2 ${meta.ring}` : ''}`}>
      <div className="flex items-start gap-3">
        {/* Icon badge */}
        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${meta.color} flex items-center justify-center text-xl flex-shrink-0 shadow-sm`}>
          {isRunning ? <PulsingDot /> : meta.icon}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium text-white">{agent.label ?? meta.label}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${meta.badge}`}>
              {isRunning ? 'running' : 'done'}
            </span>
            {isRunning && <span className="text-xs text-gray-500 animate-pulse">{agent.message}</span>}
          </div>

          {/* Output preview */}
          {isDone && agent.output && (
            <AgentOutput agent={agent} meta={meta} />
          )}
        </div>
      </div>
    </div>
  )
}

function AgentOutput({ agent, meta }) {
  const { output, name } = agent

  if (name === 'planner' && output?.sub_queries) {
    return (
      <div className="mt-2 space-y-1">
        <p className="text-xs text-gray-500 mb-1.5">Generated {output.sub_queries.length} sub-queries:</p>
        {output.sub_queries.map((q, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <span className={`mt-0.5 text-xs font-mono ${meta.badge} px-1.5 py-0.5 rounded flex-shrink-0`}>{i + 1}</span>
            <span className="text-gray-300">{q}</span>
          </div>
        ))}
      </div>
    )
  }

  if (name === 'retriever' && output?.total_results != null) {
    return (
      <div className="mt-2">
        <p className="text-xs text-gray-400">
          Retrieved <span className="text-white font-medium">{output.total_results} sources</span> across {output.sources?.length ?? 0} unique URLs
        </p>
        <div className="mt-1.5 flex flex-wrap gap-1">
          {(output.sources ?? []).slice(0, 5).map((s, i) => (
            <a
              key={i}
              href={s.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-gray-500 hover:text-gray-300 truncate max-w-[200px] hover:underline"
            >
              {new URL(s.url).hostname.replace('www.', '')}
            </a>
          ))}
        </div>
      </div>
    )
  }

  if (name === 'summarizer' && output?.title) {
    return (
      <div className="mt-2">
        <p className="text-xs font-medium text-white mb-1.5">{output.title}</p>
        <div className="flex flex-wrap gap-1">
          {(output.key_findings ?? []).slice(0, 2).map((f, i) => (
            <span key={i} className="text-xs text-gray-400 bg-gray-800/60 px-2 py-1 rounded-md">
              {f.length > 80 ? f.slice(0, 80) + '…' : f}
            </span>
          ))}
        </div>
      </div>
    )
  }

  if (name === 'citation_formatter' && output?.citations) {
    return (
      <div className="mt-2">
        <p className="text-xs text-gray-400">
          Formatted <span className="text-white font-medium">{output.citations.length} citations</span>
        </p>
      </div>
    )
  }

  return null
}

function PulsingDot() {
  return (
    <span className="flex gap-0.5">
      {[0, 1, 2].map(i => (
        <span
          key={i}
          className="w-1.5 h-1.5 bg-white rounded-full animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  )
}
