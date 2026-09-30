import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Brain, Clock, Users, AlertCircle, ChevronRight, Edit2, Loader2 } from 'lucide-react'
import { useGoalStore } from '../stores/goalStore'
import { useTranslation } from '../i18n/i18nContext'
import { AppShell } from '../components/layout/AppShell'
import type { ClarificationQuestion } from '../types'

function CapabilityChip({ cap }: { cap: string }) {
  const labels: Record<string, string> = {
    web_search: '🔍 Web Search', web_read: '📄 Web Read', browser_navigate: '🌐 Browser',
    calendar_read: '📅 Cal Read', calendar_create: '📅 Cal Create', calendar_delete: '🗑️ Cal Delete',
    email_read: '📧 Email Read', email_draft: '📧 Email Draft', email_send: '📧 Email Send',
    message_send: '💬 Message', issue_create: '🐛 Issue', document_summarize: '📝 Summarize',
    file_read: '📂 File Read', api_request: '🔌 API', mcp_call: '🤖 MCP',
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full bg-primary-50 text-primary-700 border border-primary-200">
      {labels[cap] || cap}
    </span>
  )
}

function ClarificationCard({
  question,
  answer,
  onAnswer,
}: {
  question: ClarificationQuestion
  answer: string
  onAnswer: (id: string, val: string) => void
}) {
  return (
    <div className="p-4 bg-violet-50 border border-violet-200 rounded-xl">
      <p className="text-sm font-medium text-violet-900 mb-3">{question.question}</p>
      {question.options.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {question.options.map((opt) => (
            <button
              key={opt.id}
              onClick={() => onAnswer(question.id, opt.label)}
              className={`text-xs px-3 py-1.5 rounded-lg border font-medium transition-colors ${
                answer === opt.label
                  ? 'bg-violet-600 text-white border-violet-600'
                  : 'bg-white text-violet-700 border-violet-300 hover:bg-violet-50'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
      {question.allow_custom && (
        <input
          type="text"
          value={answer}
          onChange={(e) => onAnswer(question.id, e.target.value)}
          placeholder="Or type your answer…"
          className="w-full text-sm px-3 py-2 border border-violet-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500 bg-white"
        />
      )}
    </div>
  )
}

export default function GoalUnderstand() {
  const { t } = useTranslation()
  const {
    understanding, currentGoalText, isAnalyzing, isGeneratingPlan, error,
    generatePlan, clarificationAnswers, setClarificationAnswer, submitClarifications,
  } = useGoalStore()
  const navigate = useNavigate()
  const [submitted, setSubmitted] = useState(false)

  if (!understanding && !isAnalyzing) {
    return (
      <AppShell>
        <div className="max-w-2xl mx-auto px-4 py-12 text-center">
          <p className="text-slate-500">No goal analyzed yet.</p>
          <button onClick={() => navigate('/dashboard')} className="mt-4 text-primary-600 font-medium text-sm hover:underline">
            ← Go to Dashboard
          </button>
        </div>
      </AppShell>
    )
  }

  const handleCreatePlan = async () => {
    // If clarification needed and not yet submitted
    if (understanding?.clarification_needed && !submitted) {
      try {
        setSubmitted(true)
        await submitClarifications()
      } catch { return }
    }

    try {
      await generatePlan()
      navigate(`/goal/current/plan`)
    } catch { /* error shown inline */ }
  }

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="flex items-center gap-2 mb-6">
          <Brain className="w-5 h-5 text-primary-600" />
          <h1 className="text-xl font-bold text-slate-900">{t('understand.title')}</h1>
        </div>

        {isAnalyzing && (
          <div className="flex items-center gap-3 p-6 bg-white border border-slate-200 rounded-2xl mb-4">
            <Loader2 className="w-5 h-5 text-primary-600 animate-spin shrink-0" />
            <p className="text-sm text-slate-600">Relay is understanding your goal… (~90–150s on CPU)</p>
          </div>
        )}

        {understanding && (
          <div className="space-y-4">
            {/* Goal text */}
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Your Goal</p>
              <p className="text-sm text-slate-700">{currentGoalText}</p>
            </div>

            {/* Objective */}
            <div className="bg-white border border-slate-200 rounded-xl p-5">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">{t('understand.objective')}</p>
              <p className="text-sm text-slate-800 leading-relaxed">{understanding.objective}</p>
            </div>

            {/* Grid: constraints + participants + deadline */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {understanding.constraints.length > 0 && (
                <div className="bg-white border border-slate-200 rounded-xl p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">{t('understand.constraints')}</p>
                  <ul className="space-y-1">
                    {understanding.constraints.map((c, i) => (
                      <li key={i} className="text-xs text-slate-700 flex items-start gap-1.5">
                        <span className="mt-1 w-1.5 h-1.5 rounded-full bg-slate-400 shrink-0" />
                        {c}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {understanding.participants.length > 0 && (
                <div className="bg-white border border-slate-200 rounded-xl p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                    <Users className="w-3 h-3 inline mr-1" />{t('understand.participants')}
                  </p>
                  <ul className="space-y-1">
                    {understanding.participants.map((p, i) => (
                      <li key={i} className="text-xs text-slate-700">{p}</li>
                    ))}
                  </ul>
                </div>
              )}

              {understanding.deadline && (
                <div className="bg-white border border-slate-200 rounded-xl p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                    <Clock className="w-3 h-3 inline mr-1" />{t('understand.deadline')}
                  </p>
                  <p className="text-xs text-slate-700">{understanding.deadline}</p>
                </div>
              )}
            </div>

            {/* Capabilities */}
            {understanding.required_capabilities.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl p-5">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">{t('understand.capabilities')}</p>
                <div className="flex flex-wrap gap-2">
                  {understanding.required_capabilities.map((cap) => (
                    <CapabilityChip key={cap} cap={cap} />
                  ))}
                </div>
              </div>
            )}

            {/* Clarification questions */}
            {understanding.clarification_needed && understanding.clarification_questions.length > 0 && (
              <div className="bg-white border border-violet-200 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-4">
                  <AlertCircle className="w-4 h-4 text-violet-600" />
                  <p className="text-sm font-semibold text-violet-900">{t('understand.clarification_title')}</p>
                </div>
                <p className="text-xs text-violet-700 mb-4">{t('understand.clarification_desc')}</p>
                <div className="space-y-3">
                  {understanding.clarification_questions.map((q) => (
                    <ClarificationCard
                      key={q.id}
                      question={q}
                      answer={clarificationAnswers[q.id] || ''}
                      onAnswer={setClarificationAnswer}
                    />
                  ))}
                </div>
              </div>
            )}

            {error && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-700 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" /> {error}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-between pt-2">
              <button
                onClick={() => navigate('/dashboard')}
                className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700"
              >
                <Edit2 className="w-4 h-4" /> {t('understand.edit_goal')}
              </button>
              <button
                onClick={handleCreatePlan}
                disabled={isGeneratingPlan || isAnalyzing}
                className="flex items-center gap-2 bg-primary-600 text-white text-sm font-semibold px-5 py-2.5 rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isGeneratingPlan ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Generating plan…</>
                ) : (
                  <>{t('understand.create_plan')} <ChevronRight className="w-4 h-4" /></>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  )
}
