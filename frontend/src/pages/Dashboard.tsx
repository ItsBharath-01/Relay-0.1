import React, { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap, AlertCircle, Plug, CheckCircle, AlertTriangle, ArrowRight } from 'lucide-react'
import { useGoalStore } from '../stores/goalStore'
import { useUIStore } from '../stores/uiStore'
import { useConnectionStore } from '../stores/connectionStore'
import { useTranslation } from '../i18n/i18nContext'
import { AppShell } from '../components/layout/AppShell'

const EXAMPLE_GOALS = [
  'Search for the top 5 open source LLM frameworks released in 2024 and summarize their key differences.',
  'Read the latest blog post from openai.com and give me a 3-bullet summary.',
  'Find the current weather in Bangalore and write a short travel recommendation.',
]

function ConnectionHealthBar() {
  const { connections, catalog, fetchConnections, fetchCatalog } = useConnectionStore()
  const navigate = useNavigate()

  useEffect(() => {
    if (connections.length === 0) fetchConnections()
    if (catalog.length === 0) fetchCatalog()
  }, [connections.length, catalog.length, fetchConnections, fetchCatalog])

  const catalogMap = new Map(catalog.map((a) => [a.app_id, a]))
  const active = connections.filter((c) => c.status !== 'not_connected')
  const degraded = active.filter((c) => c.status === 'needs_reconnection')
  const healthy = active.filter((c) => c.status === 'connected')

  if (connections.length === 0 && catalog.length === 0) return null

  return (
    <div className="mb-6 bg-white border border-slate-200 rounded-xl shadow-subtle p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Plug size={14} className="text-slate-400" />
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Connected Apps</span>
        </div>
        <button
          onClick={() => navigate('/connections')}
          className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 transition-colors"
        >
          Manage <ArrowRight size={11} />
        </button>
      </div>

      {active.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Plug size={14} />
          <span>No apps connected. <button onClick={() => navigate('/connections')} className="text-blue-600 hover:underline">Connect apps</button> to enable real actions.</span>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {active.map((conn) => {
            const def = catalogMap.get(conn.app_id)
            const emoji = def?.icon_emoji ?? '🔌'
            const isHealthy = conn.status === 'connected'
            return (
              <button
                key={conn.id}
                onClick={() => navigate(`/connections/${conn.app_id}`)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition-colors hover:bg-slate-50"
                style={{ borderColor: isHealthy ? '#d1fae5' : '#fecaca', backgroundColor: isHealthy ? '#f0fdf4' : '#fff5f5' }}
              >
                <span>{emoji}</span>
                <span style={{ color: isHealthy ? '#065f46' : '#991b1b' }}>{def?.name ?? conn.app_id}</span>
                {isHealthy
                  ? <CheckCircle size={10} style={{ color: '#10b981' }} />
                  : <AlertTriangle size={10} style={{ color: '#ef4444' }} />
                }
              </button>
            )
          })}

          {degraded.length > 0 && (
            <div className="w-full mt-1 text-xs text-amber-700 flex items-center gap-1">
              <AlertTriangle size={11} /> {degraded.length} connection{degraded.length > 1 ? 's' : ''} need attention
            </div>
          )}

          <div className="w-full mt-1 text-xs text-slate-400 flex items-center gap-1">
            <CheckCircle size={11} className="text-green-500" />
            {healthy.length} of {active.length} apps healthy
          </div>
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { t } = useTranslation()
  const { llmHealth } = useUIStore()
  const { analyzeGoal, setGoalText, isAnalyzing, error } = useGoalStore()
  const navigate = useNavigate()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [localText, setLocalText] = useState('')

  const isLLMReady = llmHealth?.status === 'ready'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const text = localText.trim()
    if (!text || !isLLMReady || isAnalyzing) return

    setGoalText(text)
    try {
      await analyzeGoal(text)
      navigate('/goal/current/understand')
    } catch {
      // error shown inline
    }
  }

  const handleExampleClick = (example: string) => {
    setLocalText(example)
    textareaRef.current?.focus()
  }

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`
  }, [localText])

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto px-4 py-8">
        {/* LLM warning banner */}
        {llmHealth && llmHealth.status !== 'ready' && (
          <div className="mb-6 flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-xl">
            <AlertCircle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-amber-800">
                {llmHealth.status === 'backend_unavailable' ? t('llm.backend_unavailable')
                  : llmHealth.status === 'model_missing' ? t('llm.model_missing')
                  : t('llm.unavailable')}
              </p>
              <p className="text-xs text-amber-700 mt-0.5">
                {llmHealth.error || 'Relay requires Ollama running locally with qwen3:4b model. Goal analysis is disabled until the LLM is reachable.'}
              </p>
            </div>
          </div>
        )}

        {/* Connection health bar */}
        <ConnectionHealthBar />

        {/* Goal input card */}
        <div className="bg-white border border-slate-200 rounded-2xl shadow-subtle overflow-hidden">
          <div className="px-5 pt-5">
            <h1 className="text-lg font-bold text-slate-900 mb-1">{t('dash.what_accomplish')}</h1>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="px-5 py-3">
              <textarea
                ref={textareaRef}
                value={localText}
                onChange={(e) => setLocalText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit(e as unknown as React.FormEvent)
                }}
                placeholder={t('dash.placeholder')}
                rows={3}
                className="w-full text-sm text-slate-900 placeholder-slate-400 resize-none focus:outline-none leading-relaxed"
                disabled={isAnalyzing}
              />
            </div>

            {error && (
              <div className="px-5 pb-3">
                <p className="text-xs text-rose-600 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5" /> {error}
                </p>
              </div>
            )}

            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 bg-slate-50">
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <kbd className="px-1.5 py-0.5 bg-white border border-slate-200 rounded text-xs">⌘ Enter</kbd>
                <span>to run</span>
              </div>
              <button
                type="submit"
                disabled={!localText.trim() || !isLLMReady || isAnalyzing}
                className="flex items-center gap-2 bg-primary-600 text-white text-sm font-semibold px-5 py-2 rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isAnalyzing ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Analyzing…
                  </>
                ) : (
                  <>
                    <Zap className="w-3.5 h-3.5" />
                    {t('dash.run_relay')}
                  </>
                )}
              </button>
            </div>
          </form>
        </div>

        {/* Example goals */}
        {!isAnalyzing && (
          <div className="mt-6">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">Example goals</p>
            <div className="space-y-2">
              {EXAMPLE_GOALS.map((eg) => (
                <button
                  key={eg}
                  onClick={() => handleExampleClick(eg)}
                  disabled={!isLLMReady}
                  className="w-full text-left text-sm text-slate-600 px-4 py-3 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 hover:border-primary-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {eg}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Loading skeleton while analyzing */}
        {isAnalyzing && (
          <div className="mt-8 p-6 bg-white border border-slate-200 rounded-2xl">
            <div className="flex items-center gap-3 mb-4">
              <span className="w-5 h-5 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
              <span className="text-sm font-medium text-slate-700">Analyzing your goal…</span>
            </div>
            <div className="space-y-2">
              <div className="h-3 bg-slate-100 rounded animate-pulse w-3/4" />
              <div className="h-3 bg-slate-100 rounded animate-pulse w-1/2" />
              <div className="h-3 bg-slate-100 rounded animate-pulse w-2/3" />
            </div>
          </div>
        )}

        {/* Quick links */}
        <div className="mt-6 grid grid-cols-3 gap-3">
          {[
            { label: 'Connections', icon: '🔌', path: '/connections', desc: 'Manage app connections' },
            { label: 'History', icon: '📋', path: '/history', desc: 'View past executions' },
            { label: 'Approvals', icon: '✅', path: '/approvals', desc: 'Pending approvals' },
          ].map(({ label, icon, path, desc }) => (
            <button
              key={path}
              onClick={() => navigate(path)}
              className="flex flex-col items-start p-3 bg-white border border-slate-200 rounded-xl hover:border-primary-300 hover:bg-slate-50 transition-colors text-left"
            >
              <span className="text-xl mb-1">{icon}</span>
              <span className="text-xs font-semibold text-slate-700">{label}</span>
              <span className="text-xs text-slate-400">{desc}</span>
            </button>
          ))}
        </div>
      </div>
    </AppShell>
  )
}
