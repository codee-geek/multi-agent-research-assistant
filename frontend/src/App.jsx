import { useState, useRef, useCallback } from 'react'
import SearchBar from './components/SearchBar'
import AgentTimeline from './components/AgentTimeline'
import ResearchReport from './components/ResearchReport'
import CitationList from './components/CitationList'
import SelfReviewPanel from './components/SelfReviewPanel'
import ClarificationPanel from './components/ClarificationPanel'
import BugBotPanel from './components/BugBotPanel'

const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

const INITIAL_STATE = {
  status: 'idle',        // idle | streaming | clarification | complete | error
  query: '',
  sessionId: null,
  agents: [],            // array of agent step objects
  result: null,
  error: null,
  elapsed: null,
  clarification: null,   // { question, ambiguities }
  maxSources: 5,
  bugbotFlags: [],
  bugbotReport: null,
}

export default function App() {
  const [state, setState] = useState(INITIAL_STATE)
  const esRef = useRef(null)

  const updateAgent = useCallback((agentName, patch) => {
    setState(prev => {
      const agents = [...prev.agents]
      const idx = agents.findIndex(a => a.name === agentName)
      if (idx === -1) {
        agents.push({ name: agentName, status: 'running', output: null, ...patch })
      } else {
        agents[idx] = { ...agents[idx], ...patch }
      }
      return { ...prev, agents }
    })
  }, [])

  const handleSearch = useCallback((query, maxSources, clarification = null) => {
    // Reset state (keep agents when resuming after clarification)
    setState(prev => ({
      ...INITIAL_STATE,
      status: 'streaming',
      query,
      maxSources,
      agents: clarification ? prev.agents : [],
    }))

    // Close any existing stream
    if (esRef.current) {
      esRef.current.close()
    }

    // Open SSE stream via POST workaround using fetch + ReadableStream
    const run = async () => {
      let response
      try {
        response = await fetch(`${API_BASE}/research`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
          body: JSON.stringify({
            query,
            max_sources: maxSources,
            ...(clarification ? { clarification } : {}),
          }),
        })
      } catch (err) {
        setState(prev => ({ ...prev, status: 'error', error: 'Cannot connect to API. Is the backend running?' }))
        return
      }

      if (!response.ok) {
        const text = await response.text()
        setState(prev => ({ ...prev, status: 'error', error: `API error ${response.status}: ${text}` }))
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      let pendingEventType = null
      let pendingDataLine = ''

      const dispatchPending = () => {
        if (!pendingDataLine) return
        try {
          const payload = JSON.parse(pendingDataLine)
          dispatchSSE(pendingEventType ?? 'message', payload)
        } catch { /* malformed, skip */ }
        pendingEventType = null
        pendingDataLine = ''
      }

      const processEvents = (raw, flush = false) => {
        const lines = (buffer + raw).split('\n')
        buffer = flush ? '' : (lines.pop() ?? '')

        for (const line of lines) {
          const normalized = line.replace(/\r$/, '')
          if (normalized.startsWith('event:')) {
            pendingEventType = normalized.slice(6).trim()
          } else if (normalized.startsWith('data:')) {
            pendingDataLine = normalized.slice(5).trim()
          } else if (normalized === '' && pendingDataLine) {
            dispatchPending()
          }
        }

        if (flush && pendingDataLine) dispatchPending()
      }

      const dispatchSSE = (type, payload) => {
        switch (type) {
          case 'session':
            setState(prev => ({ ...prev, sessionId: payload.session_id }))
            break

          case 'step_start':
            updateAgent(payload.agent, {
              name: payload.agent,
              label: payload.label,
              icon: payload.icon,
              status: 'running',
              message: payload.message,
              step: payload.step,
              output: null,
            })
            break

          case 'step_output':
            updateAgent(payload.agent, { status: 'done', output: payload })
            break

          case 'clarification_needed':
            setState(prev => ({
              ...prev,
              status: 'clarification',
              clarification: {
                question: payload.clarification_question,
                ambiguities: payload.ambiguities ?? [],
              },
            }))
            break

          case 'bugbot_flag':
            setState(prev => ({
              ...prev,
              bugbotFlags: [...prev.bugbotFlags, payload],
            }))
            break

          case 'bugbot_report':
            setState(prev => ({ ...prev, bugbotReport: payload }))
            break

          case 'complete':
            setState(prev => ({
              ...prev,
              status: 'complete',
              result: payload,
              elapsed: payload.elapsed_seconds,
            }))
            // Mark all agents done
            setState(prev => ({
              ...prev,
              agents: prev.agents.map(a => ({ ...a, status: 'done' })),
            }))
            break

          case 'error':
            setState(prev => ({
              ...prev,
              status: 'error',
              error: payload.message ?? 'Unknown error',
            }))
            break

          default:
            break
        }
      }

      // Read stream
      try {
        while (true) {
          const { value, done } = await reader.read()
          if (done) {
            processEvents(decoder.decode(), true)
            break
          }
          processEvents(decoder.decode(value, { stream: true }))
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          setState(prev => ({
            ...prev,
            status: 'error',
            error: prev.status === 'complete' ? prev.error : 'Stream interrupted.',
          }))
        }
      }
    }

    run()
  }, [updateAgent])

  const { status, query, agents, result, error, elapsed, clarification, maxSources, bugbotFlags, bugbotReport } = state
  const isStreaming = status === 'streaming'
  const isClarification = status === 'clarification'
  const isComplete = status === 'complete'
  const isError = status === 'error'
  const isActive = isStreaming || isClarification || isComplete

  const handleClarificationSubmit = useCallback((answer) => {
    handleSearch(query, maxSources, answer)
  }, [handleSearch, query, maxSources])

  const handleReset = () => {
    if (esRef.current) esRef.current.close()
    setState(INITIAL_STATE)
  }

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* ── Header ── */}
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center text-white font-bold text-sm">
              RA
            </div>
            <div>
              <h1 className="text-sm font-semibold text-white leading-tight">Research Assistant</h1>
              <p className="text-xs text-gray-500">LangGraph · MCP · GPT-4o</p>
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span className="hidden sm:flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse-slow"></span>
              6-agent pipeline
            </span>
            {(isStreaming || isComplete || isClarification) && (
              <button
                onClick={handleReset}
                className="px-3 py-1.5 rounded-md bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors"
              >
                New research
              </button>
            )}
          </div>
        </div>
      </header>

      {/* ── Main ── */}
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 py-8 space-y-8">

        {/* Hero + search (idle state) */}
        {status === 'idle' && (
          <div className="animate-fade-in flex flex-col items-center text-center pt-12 pb-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center mb-6 shadow-lg shadow-brand-500/20">
              <span className="text-3xl">🔬</span>
            </div>
            <h2 className="text-3xl font-bold text-white mb-3">
              Multi-Agent Research Assistant
            </h2>
            <p className="text-gray-400 max-w-lg mb-2">
              A 6-agent LangGraph pipeline — <span className="text-gray-300">Planner → Retriever → Evidence Validator → Summarizer → Citation Formatter → Self-Review</span> — orchestrated with MCP tool integration and GPT-4o structured output.
            </p>
            <p className="text-gray-600 text-sm mb-10">Enter any research question below to begin.</p>
            <div className="w-full max-w-2xl">
              <SearchBar onSearch={handleSearch} disabled={isStreaming} />
            </div>
            <ExampleQueries onSelect={q => handleSearch(q, 5)} />
          </div>
        )}

        {/* Search bar (active state) */}
        {isActive && (
          <div className="animate-slide-up">
            <SearchBar
              onSearch={handleSearch}
              disabled={isStreaming}
              initialQuery={query}
              compact
            />
          </div>
        )}

        {/* Clarification prompt */}
        {isClarification && clarification && (
          <ClarificationPanel
            query={query}
            question={clarification.question}
            ambiguities={clarification.ambiguities}
            onSubmit={handleClarificationSubmit}
            disabled={isStreaming}
          />
        )}

        {/* BugBot monitor */}
        {isActive && (bugbotFlags.length > 0 || bugbotReport) && (
          <BugBotPanel flags={bugbotFlags} report={bugbotReport} />
        )}

        {/* Error banner */}
        {isError && (
          <div className="animate-slide-up rounded-xl border border-red-800 bg-red-950/40 p-4 flex items-start gap-3">
            <span className="text-red-400 text-xl mt-0.5">⚠️</span>
            <div>
              <p className="text-red-300 font-medium text-sm">Pipeline error</p>
              <p className="text-red-400 text-sm mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {/* Agent timeline */}
        {isActive && agents.length > 0 && (
          <div className="animate-fade-in">
            <AgentTimeline agents={agents} isStreaming={isStreaming} />
          </div>
        )}

        {/* Research report */}
        {isComplete && result && (
          <div className="animate-slide-up space-y-6">
            <ResearchReport
              title={result.summary?.title}
              summary={result.summary?.summary}
              keyFindings={result.summary?.key_findings}
              subQueries={result.plan?.sub_queries}
              totalSources={result.total_sources}
              validatedSources={result.validated_sources}
              elapsed={elapsed}
            />
            <CitationList
              citations={result.citations?.citations}
              apaRefs={result.citations?.apa_references}
            />
            <SelfReviewPanel review={result.self_review} />
          </div>
        )}
      </main>

      {/* ── Footer ── */}
      <footer className="border-t border-gray-900 py-4 text-center text-xs text-gray-700">
        Multi-Agent Research Assistant · LangGraph + MCP + GPT-4o · FastAPI backend
      </footer>
    </div>
  )
}


function ExampleQueries({ onSelect }) {
  const examples = [
    'What are the key breakthroughs in quantum computing in 2024-2025?',
    'How does Retrieval-Augmented Generation (RAG) work and what are its limitations?',
    'What is the current state of nuclear fusion energy research?',
    'Explain the differences between LangGraph and AutoGen for multi-agent AI systems',
  ]

  return (
    <div className="mt-8 w-full max-w-2xl">
      <p className="text-xs text-gray-600 mb-3 text-left">Try an example:</p>
      <div className="flex flex-col gap-2">
        {examples.map((q, i) => (
          <button
            key={i}
            onClick={() => onSelect(q)}
            className="text-left text-sm text-gray-400 hover:text-gray-200 px-3 py-2.5 rounded-lg border border-gray-800 hover:border-gray-600 hover:bg-gray-900 transition-all"
          >
            <span className="text-gray-600 mr-2">→</span>
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}
