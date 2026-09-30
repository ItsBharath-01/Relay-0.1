import { useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { CheckCircle, XCircle, Shield, RefreshCw, ChevronRight, Home } from 'lucide-react'
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

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto px-4 py-10">
        {/* Status header */}
        <div className="text-center mb-8">
          <div className={`w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 ${
            succeeded ? 'bg-emerald-100' : 'bg-rose-100'
          }`}>
            {succeeded
              ? <CheckCircle className="w-8 h-8 text-emerald-600" />
              : <XCircle className="w-8 h-8 text-rose-600" />
            }
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mb-2">
            {succeeded ? 'Goal Completed' : 'Execution Stopped'}
          </h1>
          <p className="text-sm text-slate-500 max-w-md mx-auto">{execution.goal_text}</p>
        </div>

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
