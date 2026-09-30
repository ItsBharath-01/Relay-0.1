import React, { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap, AlertCircle } from 'lucide-react'
import { useGoalStore } from '../stores/goalStore'
import { useUIStore } from '../stores/uiStore'
import { useTranslation } from '../i18n/i18nContext'
import { AppShell } from '../components/layout/AppShell'

const EXAMPLE_GOALS = [
  'Search for the top 5 open source LLM frameworks released in 2024 and summarize their key differences.',
  'Read the latest blog post from openai.com and give me a 3-bullet summary.',
  'Find the current weather in Bangalore and write a short travel recommendation.',
]

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
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit(e as any)
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
              <span className="text-sm font-medium text-slate-600">Relay is analyzing your goal with qwen3:4b…</span>
            </div>
            <div className="space-y-2">
              {[80, 60, 90].map((w, i) => (
                <div key={i} className="h-3 bg-slate-100 rounded animate-pulse" style={{ width: `${w}%` }} />
              ))}
            </div>
            <p className="mt-4 text-xs text-slate-400">This can take 90–150 seconds on CPU. The LLM is reasoning through your goal.</p>
          </div>
        )}
      </div>
    </AppShell>
  )
}
