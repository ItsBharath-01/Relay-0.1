import React, { useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Pause, Play, X, CheckCircle, XCircle, AlertTriangle, Shield,
  RefreshCw, Zap, Clock
} from 'lucide-react'
import { useExecutionStore } from '../stores/executionStore'
import { useTranslation } from '../i18n/i18nContext'
import { AppShell } from '../components/layout/AppShell'
import type { ExecutionEvent, Approval } from '../types'

// ── Approval Modal ─────────────────────────────────────────────────────────
function ApprovalModal({ approval, onDecide }: {
  approval: Approval
  onDecide: (decision: 'approved' | 'rejected') => void
}) {
  const { t } = useTranslation()
  const [deciding, setDeciding] = React.useState(false)

  const handle = async (d: 'approved' | 'rejected') => {
    setDeciding(true)
    await onDecide(d)
    setDeciding(false)
  }

  const riskColors: Record<string, string> = {
    low: 'bg-emerald-50 border-emerald-300 text-emerald-800',
    medium: 'bg-amber-50 border-amber-300 text-amber-800',
    high: 'bg-orange-50 border-orange-300 text-orange-800',
    critical: 'bg-rose-50 border-rose-300 text-rose-800',
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div className="relative bg-white rounded-2xl shadow-2xl max-w-lg w-full p-6 border border-slate-200">
        {/* Header */}
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-full bg-violet-100 flex items-center justify-center">
            <Shield className="w-5 h-5 text-violet-600" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900">{t('approval.title')}</h2>
            <p className="text-xs text-slate-500">Risk: <span className="font-semibold">{approval.risk}</span></p>
          </div>
        </div>

        {/* Risk badge */}
        <div className={`mb-4 px-3 py-2 rounded-lg border text-xs font-medium ${riskColors[approval.risk] || riskColors.high}`}>
          ⚠️ This action is classified as <strong>{approval.risk}</strong> risk.
        </div>

        <div className="space-y-3 text-sm">
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5">{t('approval.action_label')}</p>
            <p className="text-slate-800 font-medium">{approval.action}</p>
          </div>
          {approval.target && (
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5">{t('approval.target_label')}</p>
              <p className="text-slate-700">{approval.target}</p>
            </div>
          )}
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5">{t('approval.reason_label')}</p>
            <p className="text-slate-700">{approval.reason}</p>
          </div>
          {approval.consequences && (
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5">{t('approval.consequences_label')}</p>
              <p className="text-slate-700">{approval.consequences}</p>
            </div>
          )}
          {/* Content preview */}
          {Object.keys(approval.content).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5">{t('approval.content_preview')}</p>
              <pre className="text-xs bg-slate-50 border border-slate-200 rounded-lg p-3 overflow-auto max-h-28 text-slate-700 font-mono">
                {JSON.stringify(approval.content, null, 2)}
              </pre>
            </div>
          )}
          {/* Payload hash */}
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-0.5">{t('approval.payload_hash')}</p>
            <p className="text-xs font-mono text-slate-500 truncate">{approval.payload_hash}</p>
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button
            onClick={() => handle('rejected')}
            disabled={deciding}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg border border-rose-300 text-rose-700 text-sm font-semibold hover:bg-rose-50 transition-colors disabled:opacity-50"
          >
            <XCircle className="w-4 h-4" /> {t('approval.reject_button')}
          </button>
          <button
            onClick={() => handle('approved')}
            disabled={deciding}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-50"
          >
            {deciding ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
            {t('approval.approve_button')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Event row ─────────────────────────────────────────────────────────────
function EventRow({ event }: { event: ExecutionEvent }) {
  const iconMap: Record<string, React.ReactNode> = {
    execution_started: <Zap className="w-3.5 h-3.5 text-blue-500" />,
    task_started: <Play className="w-3.5 h-3.5 text-blue-500" />,
    tool_selected: <Zap className="w-3.5 h-3.5 text-primary-500" />,
    action_started: <RefreshCw className="w-3.5 h-3.5 text-blue-400 animate-spin" />,
    action_completed: <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />,
    task_completed: <CheckCircle className="w-3.5 h-3.5 text-emerald-600" />,
    task_failed: <XCircle className="w-3.5 h-3.5 text-rose-500" />,
    verification_started: <Shield className="w-3.5 h-3.5 text-slate-400" />,
    verification_completed: <Shield className="w-3.5 h-3.5 text-emerald-500" />,
    approval_required: <Shield className="w-3.5 h-3.5 text-violet-500" />,
    approval_received: <CheckCircle className="w-3.5 h-3.5 text-violet-500" />,
    recovery_started: <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />,
    recovery_completed: <RefreshCw className="w-3.5 h-3.5 text-amber-600" />,
    execution_completed: <CheckCircle className="w-3.5 h-3.5 text-emerald-600" />,
    execution_failed: <XCircle className="w-3.5 h-3.5 text-rose-500" />,
  }
  const icon = iconMap[event.type] || <Clock className="w-3.5 h-3.5 text-slate-400" />
  const time = new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-slate-100 last:border-0">
      <div className="mt-0.5 shrink-0">{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-slate-700 leading-relaxed">{event.message}</p>
        {event.tool_id && (
          <span className="text-[10px] text-slate-400 font-mono">{event.tool_id}</span>
        )}
      </div>
      <span className="text-[10px] text-slate-400 font-mono shrink-0">{time}</span>
    </div>
  )
}

export default function ExecutionWorkspace() {
  const { executionId } = useParams<{ executionId: string }>()
  const { t } = useTranslation()
  const {
    execution, events, pendingApproval, recoveries, verifications,
    isStreaming, isReconnecting, error,
    fetchExecution, subscribeToStream, pauseExecution, resumeExecution,
    cancelExecution, decideApproval, unsubscribeFromStream,
  } = useExecutionStore()
  const navigate = useNavigate()
  const feedRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!executionId) return
    fetchExecution(executionId)
    subscribeToStream(executionId)
    return () => unsubscribeFromStream()
  }, [executionId])

  // Auto-scroll feed
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight
    }
  }, [events.length])

  // Navigate to summary when done
  useEffect(() => {
    if (execution?.status === 'completed') {
      setTimeout(() => navigate(`/execution/${executionId}/summary`), 2000)
    }
  }, [execution?.status])

  if (!execution) {
    return (
      <AppShell>
        <div className="flex items-center justify-center h-full">
          <div className="w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </AppShell>
    )
  }

  const progress = Math.round((execution.progress || 0) * 100)
  const statusColors: Record<string, string> = {
    running: 'text-blue-600', paused: 'text-amber-600',
    waiting_approval: 'text-violet-600', completed: 'text-emerald-600',
    failed: 'text-rose-600', cancelled: 'text-slate-500',
  }
  const statusColor = statusColors[execution.status] || 'text-slate-600'

  return (
    <AppShell>
      {/* Approval modal */}
      {pendingApproval && (
        <ApprovalModal
          approval={pendingApproval}
          onDecide={(d) => decideApproval(pendingApproval.id, d)}
        />
      )}

      <div className="max-w-3xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h1 className="text-lg font-bold text-slate-900">
                {t(`exec.${execution.status}` as any) || execution.status}
              </h1>
              {execution.outcome && (
                <span className={`px-2 py-0.5 text-xs font-semibold rounded-full border ${
                  execution.outcome === 'COMPLETED' ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
                  : execution.outcome === 'PARTIALLY_COMPLETED' ? 'bg-amber-100 text-amber-800 border-amber-300'
                  : execution.outcome === 'BLOCKED' ? 'bg-orange-100 text-orange-800 border-orange-300'
                  : 'bg-rose-100 text-rose-800 border-rose-300'
                }`}>
                  Outcome: {execution.outcome}
                </span>
              )}
              {execution.evidence_level && (
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                  {execution.evidence_level}
                </span>
              )}
            </div>
            <p className="text-sm text-slate-500 truncate max-w-md">{execution.goal_text}</p>
          </div>
          <div className="flex items-center gap-2">
            {execution.status === 'running' && (
              <button onClick={pauseExecution} className="p-2 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 transition-colors" title="Pause">
                <Pause className="w-4 h-4" />
              </button>
            )}
            {execution.status === 'paused' && (
              <button onClick={resumeExecution} className="p-2 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 transition-colors" title="Resume">
                <Play className="w-4 h-4" />
              </button>
            )}
            {['running', 'paused'].includes(execution.status) && (
              <button onClick={cancelExecution} className="p-2 rounded-lg border border-rose-200 text-rose-600 hover:bg-rose-50 transition-colors" title="Cancel">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Outcome Summary Banner if finished */}
        {execution.outcome_summary && (
          <div className={`mb-5 p-4 rounded-xl border text-sm ${
            execution.outcome === 'COMPLETED' ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
            : execution.outcome === 'BLOCKED' ? 'bg-amber-50 border-amber-200 text-amber-900'
            : execution.outcome === 'PARTIALLY_COMPLETED' ? 'bg-amber-50 border-amber-200 text-amber-900'
            : 'bg-rose-50 border-rose-200 text-rose-900'
          }`}>
            <div className="flex items-start gap-2.5">
              <Shield className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold mb-0.5">Outcome Assessment ({execution.outcome || execution.status})</p>
                <p className="text-xs leading-relaxed opacity-95">{execution.outcome_summary}</p>
              </div>
            </div>
          </div>
        )}

        {/* Progress bar */}
        <div className="mb-5">
          <div className="flex items-center justify-between text-xs text-slate-500 mb-1.5">
            <span className={`font-semibold ${statusColor}`}>{execution.current_action || '…'}</span>
            <span>{progress}%</span>
          </div>
          <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                execution.status === 'completed' ? 'bg-emerald-500'
                : execution.status === 'failed' ? 'bg-rose-500'
                : execution.status === 'waiting_approval' ? 'bg-violet-500'
                : 'bg-primary-600'
              } ${execution.status === 'running' ? 'animate-subtle-pulse' : ''}`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Reconnecting banner */}
        {isReconnecting && (
          <div className="mb-4 flex items-center gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 px-3 py-2 rounded-lg">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" /> {t('exec.reconnecting')}
          </div>
        )}

        {/* Approval waiting banner */}
        {execution.status === 'waiting_approval' && pendingApproval && (
          <div className="mb-4 flex items-center gap-3 p-4 bg-violet-50 border border-violet-300 rounded-xl">
            <Shield className="w-5 h-5 text-violet-600 shrink-0" />
            <p className="text-sm font-medium text-violet-900">
              Relay needs your approval before continuing. Review the action above.
            </p>
          </div>
        )}

        {/* Recovery cards */}
        {recoveries.length > 0 && (
          <div className="mb-4 space-y-2">
            {recoveries.map((rec) => (
              <div key={rec.id} className={`flex items-start gap-3 p-3 rounded-xl border text-xs ${
                rec.status === 'succeeded' ? 'bg-amber-50 border-amber-200' : 'bg-rose-50 border-rose-200'
              }`}>
                <RefreshCw className={`w-4 h-4 shrink-0 mt-0.5 ${rec.status === 'succeeded' ? 'text-amber-600' : 'text-rose-600'}`} />
                <div>
                  <p className="font-semibold text-slate-700">{t('recovery.title')}</p>
                  <p className="text-slate-600">{rec.problem}</p>
                  {rec.alternative_tool_id && (
                    <p className="text-slate-600 mt-0.5">
                      Switched to: <span className="font-mono">{rec.alternative_tool_id}</span> — {rec.reason}
                    </p>
                  )}
                  <p className={`mt-0.5 font-medium ${rec.status === 'succeeded' ? 'text-emerald-700' : 'text-rose-700'}`}>
                    {rec.status === 'succeeded' ? t('recovery.successful') : 'Recovery failed'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Verification cards */}
        {verifications.length > 0 && (
          <div className="mb-4 space-y-2">
            {verifications.map((v) => (
              <div key={v.id} className={`flex items-start gap-3 p-3 rounded-xl border text-xs ${
                v.result === 'passed' ? 'bg-emerald-50 border-emerald-200' : 'bg-rose-50 border-rose-200'
              }`}>
                <Shield className={`w-4 h-4 shrink-0 mt-0.5 ${v.result === 'passed' ? 'text-emerald-600' : 'text-rose-600'}`} />
                <div>
                  <p className="font-semibold text-slate-700">{t('verify.title')}: {v.criterion}</p>
                  <p className={`font-medium ${v.result === 'passed' ? 'text-emerald-700' : 'text-rose-700'}`}>
                    {v.result === 'passed' ? t('verify.passed') : t('verify.failed')}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Goal Success Criteria Evaluations */}
        {execution.criteria_evaluations && execution.criteria_evaluations.length > 0 && (
          <div className="mb-4 bg-white border border-slate-200 rounded-xl p-4">
            <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-primary-600" />
              Success Criteria Evaluation
            </h3>
            <div className="space-y-2">
              {execution.criteria_evaluations.map((c, idx) => (
                <div key={idx} className={`p-2.5 rounded-lg border text-xs flex items-start gap-2.5 ${
                  c.status === 'met' ? 'bg-emerald-50/60 border-emerald-200 text-emerald-950'
                  : c.status === 'not_verifiable' ? 'bg-amber-50/60 border-amber-200 text-amber-950'
                  : 'bg-rose-50/60 border-rose-200 text-rose-950'
                }`}>
                  {c.status === 'met' ? (
                    <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  ) : c.status === 'not_verifiable' ? (
                    <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                  ) : (
                    <XCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                  )}
                  <div className="flex-1">
                    <p className="font-semibold">{c.criterion}</p>
                    <p className="text-[11px] text-slate-600 mt-0.5">{c.reason}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Live feed */}
        <div className="bg-white border border-slate-200 rounded-xl">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-700">{t('exec.activity_feed')}</h2>
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <span className={`w-1.5 h-1.5 rounded-full ${isStreaming && !isReconnecting ? 'bg-blue-500 animate-pulse' : 'bg-slate-300'}`} />
              {events.length} events
            </div>
          </div>
          <div ref={feedRef} className="h-72 overflow-y-auto px-4 py-2">
            {events.length === 0 ? (
              <div className="flex items-center justify-center h-full text-sm text-slate-400">
                Waiting for events…
              </div>
            ) : (
              [...events].reverse().map((ev) => <EventRow key={ev.id || ev.seq} event={ev} />)
            )}
          </div>
        </div>

        {error && (
          <div className="mt-4 p-3 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-700 flex items-center gap-2">
            <XCircle className="w-4 h-4 shrink-0" /> {error}
          </div>
        )}
      </div>
    </AppShell>
  )
}
