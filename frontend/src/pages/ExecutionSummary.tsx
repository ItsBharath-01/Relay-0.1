import { useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { CheckCircle, XCircle, AlertTriangle, Shield, RefreshCw, ChevronRight, Home } from 'lucide-react'
import { useExecutionStore } from '../stores/executionStore'
import { AppShell } from '../components/layout/AppShell'

export default function ExecutionSummary() {
  const { executionId } = useParams<{ executionId: string }>()
  const { execution, events, recoveries, verifications, fetchExecution } = useExecutionStore()

  useEffect(() => {
    if (executionId && !execution) {
      fetchExecution(executionId)
    }
  }, [executionId])

  if (!execution) {
    return (
      <AppShell>
        <div className="flex items-center justify-center h-full">
          <div className="w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </AppShell>
    )
  }

  const succeeded = execution.status === 'completed'
  const taskCount = events.filter(e => e.type === 'task_completed').length
  const approvalCount = execution.approvals?.filter(a => a.status === 'approved').length || 0
  const recoveryCount = recoveries.filter(r => r.status === 'succeeded').length
  const verifyPassed = verifications.filter(v => v.result === 'passed').length

  const outcome = execution.outcome || (succeeded ? 'COMPLETED' : 'FAILED')
  const evidenceLevel = execution.evidence_level || (succeeded ? 'GOAL_ACHIEVED' : 'ACTION_REQUESTED')

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto px-4 py-10">
        {/* Status header */}
        <div className="text-center mb-8">
          <div className={`w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 ${
            outcome === 'COMPLETED' ? 'bg-emerald-100'
            : outcome === 'PARTIALLY_COMPLETED' ? 'bg-amber-100'
            : outcome === 'BLOCKED' ? 'bg-orange-100'
            : 'bg-rose-100'
          }`}>
            {outcome === 'COMPLETED'
              ? <CheckCircle className="w-8 h-8 text-emerald-600" />
              : <XCircle className="w-8 h-8 text-rose-600" />
            }
          </div>
          <div className="flex items-center justify-center gap-2 mb-2">
            <span className={`px-2.5 py-0.5 text-xs font-bold rounded-full border ${
              outcome === 'COMPLETED' ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
              : outcome === 'PARTIALLY_COMPLETED' ? 'bg-amber-100 text-amber-800 border-amber-300'
              : outcome === 'BLOCKED' ? 'bg-orange-100 text-orange-800 border-orange-300'
              : 'bg-rose-100 text-rose-800 border-rose-300'
            }`}>
              Outcome: {outcome}
            </span>
            <span className="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-slate-100 text-slate-700 border border-slate-200">
              Evidence: {evidenceLevel}
            </span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mb-2">
            {outcome === 'COMPLETED' ? 'Goal Achieved' : outcome === 'BLOCKED' ? 'Execution Blocked' : outcome === 'PARTIALLY_COMPLETED' ? 'Partially Completed' : 'Goal Not Achieved'}
          </h1>
          <p className="text-sm text-slate-500 max-w-md mx-auto">{execution.goal_text}</p>
        </div>

        {/* Outcome Assessment */}
        {execution.outcome_summary && (
          <div className={`mb-6 p-4 rounded-xl border text-sm ${
            outcome === 'COMPLETED' ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
            : outcome === 'BLOCKED' ? 'bg-amber-50 border-amber-200 text-amber-900'
            : outcome === 'PARTIALLY_COMPLETED' ? 'bg-amber-50 border-amber-200 text-amber-900'
            : 'bg-rose-50 border-rose-200 text-rose-900'
          }`}>
            <p className="font-semibold text-xs uppercase tracking-wider mb-1">Outcome Evaluation</p>
            <p className="text-xs leading-relaxed">{execution.outcome_summary}</p>
          </div>
        )}

        {/* Criteria Evaluations */}
        {execution.criteria_evaluations && execution.criteria_evaluations.length > 0 && (
          <div className="bg-white border border-slate-200 rounded-xl p-5 mb-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <Shield className="w-4 h-4 text-primary-600" /> Goal Success Criteria
            </h2>
            <div className="space-y-2">
              {execution.criteria_evaluations.map((c, idx) => (
                <div key={idx} className={`p-3 rounded-lg border text-xs flex items-start gap-2.5 ${
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

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {[
            { label: 'Tasks Done', value: taskCount, color: 'text-emerald-600' },
            { label: 'Approvals', value: approvalCount, color: 'text-violet-600' },
            { label: 'Recoveries', value: recoveryCount, color: 'text-amber-600' },
            { label: 'Verified', value: verifyPassed, color: 'text-blue-600' },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-white border border-slate-200 rounded-xl p-4 text-center">
              <p className={`text-2xl font-bold ${color}`}>{value}</p>
              <p className="text-xs text-slate-500 mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        {/* Verifications */}
        {verifications.length > 0 && (
          <div className="bg-white border border-slate-200 rounded-xl p-5 mb-4">
            <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <Shield className="w-4 h-4 text-primary-600" /> Verification Evidence
            </h2>
            <div className="space-y-2">
              {verifications.map((v) => (
                <div key={v.id} className={`flex items-start gap-3 p-3 rounded-lg text-xs border ${
                  v.result === 'passed' ? 'bg-emerald-50 border-emerald-200' : 'bg-rose-50 border-rose-200'
                }`}>
                  <Shield className={`w-4 h-4 shrink-0 mt-0.5 ${v.result === 'passed' ? 'text-emerald-600' : 'text-rose-600'}`} />
                  <div>
                    <p className="font-medium text-slate-700">{v.criterion}</p>
                    <p className={`font-semibold ${v.result === 'passed' ? 'text-emerald-700' : 'text-rose-700'}`}>
                      {v.result === 'passed' ? '✓ Passed' : '✗ Failed'}
                    </p>
                    {Object.keys(v.evidence).length > 0 && (
                      <pre className="mt-1 text-slate-500 font-mono text-[10px] overflow-auto max-h-16">
                        {JSON.stringify(v.evidence, null, 2)}
                      </pre>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recoveries */}
        {recoveries.length > 0 && (
          <div className="bg-white border border-slate-200 rounded-xl p-5 mb-4">
            <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <RefreshCw className="w-4 h-4 text-amber-600" /> Automatic Recoveries
            </h2>
            <div className="space-y-2">
              {recoveries.map((r) => (
                <div key={r.id} className="text-xs p-3 bg-amber-50 border border-amber-200 rounded-lg">
                  <p className="font-medium text-slate-700">Problem: {r.problem}</p>
                  {r.alternative_tool_id && (
                    <p className="text-slate-600 mt-0.5">
                      Recovered with <span className="font-mono">{r.alternative_tool_id}</span>
                    </p>
                  )}
                  <p className={`mt-0.5 font-semibold ${r.status === 'succeeded' ? 'text-emerald-700' : 'text-rose-700'}`}>
                    {r.status === 'succeeded' ? '✓ Recovered' : '✗ Failed'}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3 mt-6">
          <Link
            to="/dashboard"
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg border border-slate-200 text-slate-700 text-sm font-medium hover:bg-slate-50 transition-colors"
          >
            <Home className="w-4 h-4" /> New Goal
          </Link>
          <Link
            to="/history"
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg bg-primary-600 text-white text-sm font-semibold hover:bg-primary-700 transition-colors"
          >
            View History <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </AppShell>
  )
}
