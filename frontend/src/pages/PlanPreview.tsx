import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Play, Edit2, AlertTriangle, CheckCircle, Shield, Loader2 } from 'lucide-react'
import { useGoalStore } from '../stores/goalStore'
import { useExecutionStore } from '../stores/executionStore'
import { useTranslation } from '../i18n/i18nContext'
import { AppShell } from '../components/layout/AppShell'
import type { PlanTask } from '../types'

const RISK_COLORS: Record<string, string> = {
  low: 'text-emerald-600 bg-emerald-50 border-emerald-200',
  medium: 'text-amber-700 bg-amber-50 border-amber-200',
  high: 'text-orange-700 bg-orange-50 border-orange-200',
  critical: 'text-rose-700 bg-rose-50 border-rose-200',
}


function TaskCard({ task, index }: { task: PlanTask; index: number }) {
  const { t } = useTranslation()
  const riskClass = RISK_COLORS[task.risk_level] || RISK_COLORS.low

  return (
    <div className={`relative pl-8 ${index > 0 ? 'pt-4' : ''}`}>
      {/* Timeline connector */}
      {index > 0 && (
        <div className="absolute left-3.5 top-0 w-0.5 h-4 bg-slate-200" />
      )}
      {/* Circle */}
      <div className={`absolute left-2 top-4 w-3 h-3 rounded-full border-2 ${
        task.has_connected_tool ? 'border-primary-600 bg-white' : 'border-slate-300 bg-slate-100'
      }`} />

      <div className="bg-white border border-slate-200 rounded-xl p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className="text-xs text-slate-400 font-mono">#{task.order + 1}</span>
              <h3 className="text-sm font-semibold text-slate-900 truncate">{task.title}</h3>
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {/* Capability */}
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary-50 text-primary-700 border border-primary-200">
                {task.capability_id.replace(/_/g, ' ')}
              </span>
              {/* Risk */}
              <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${riskClass}`}>
                {t('plan.risk_level')}: {task.risk_level}
              </span>
              {/* Approval */}
              {task.requires_approval && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-200 flex items-center gap-1">
                  <Shield className="w-3 h-3" /> {t('plan.requires_approval')}
                </span>
              )}
            </div>
            {/* Tool */}
            {task.selected_tool_name && (
              <p className="mt-2 text-xs text-slate-500 flex items-center gap-1">
                <CheckCircle className="w-3 h-3 text-emerald-500" />
                Tool: <span className="font-medium">{task.selected_tool_name}</span>
              </p>
            )}
            {/* No tool warning */}
            {!task.has_connected_tool && (
              <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-700">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                <span>{t('plan.no_tool_warning')}</span>
              </div>
            )}
            {/* Dependencies */}
            {task.depends_on.length > 0 && (
              <p className="mt-1 text-xs text-slate-400">
                Depends on: {task.depends_on.join(', ')}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function PlanPreview() {
  const { t } = useTranslation()
  const { currentPlan, currentGoalText, isGeneratingPlan, error } = useGoalStore()
  const { startExecution } = useExecutionStore()
  const navigate = useNavigate()

  const [isStarting, setIsStarting] = React.useState(false)

  if (!currentPlan && !isGeneratingPlan) {
    return (
      <AppShell>
        <div className="max-w-2xl mx-auto px-4 py-12 text-center">
          <p className="text-slate-500">No plan generated yet.</p>
          <button onClick={() => navigate('/dashboard')} className="mt-4 text-primary-600 font-medium text-sm hover:underline">
            ← Go to Dashboard
          </button>
        </div>
      </AppShell>
    )
  }

  const handleStart = async () => {
    if (!currentPlan) return
    setIsStarting(true)
    try {
      const exec = await startExecution(currentPlan.id)
      navigate(`/execution/${exec.id}`)
    } catch {
      setIsStarting(false)
    }
  }

  const canStart = currentPlan && currentPlan.all_tools_available !== false

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-xl font-bold text-slate-900 mb-1">{t('plan.title')}</h1>
          <p className="text-sm text-slate-500">{t('plan.subtitle')}</p>
        </div>

        {isGeneratingPlan && (
          <div className="flex items-center gap-3 p-6 bg-white border border-slate-200 rounded-2xl mb-4">
            <Loader2 className="w-5 h-5 text-primary-600 animate-spin" />
            <p className="text-sm text-slate-600">Decomposing goal into task graph… (~90–150s on CPU)</p>
          </div>
        )}

        {currentPlan && (
          <div className="space-y-4">
            {/* Goal reminder */}
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Goal</p>
              <p className="text-sm text-slate-700">{currentGoalText}</p>
            </div>

            {/* Missing capabilities warning */}
            {currentPlan.missing_capabilities && currentPlan.missing_capabilities.length > 0 && (
              <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
                <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-amber-900">Some capabilities are not connected</p>
                  <p className="text-xs text-amber-700 mt-0.5">
                    Missing: {currentPlan.missing_capabilities.join(', ')}. Connect the required apps in Connections.
                  </p>
                </div>
              </div>
            )}

            {/* Task timeline */}
            <div className="bg-white border border-slate-200 rounded-xl p-5">
              <h2 className="text-sm font-semibold text-slate-700 mb-4">{t('plan.tasks_list')}</h2>
              <div>
                {currentPlan.tasks.map((task, i) => (
                  <TaskCard key={task.id} task={task} index={i} />
                ))}
              </div>
            </div>

            {error && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-700">
                {error}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-between pt-2">
              <button
                onClick={() => navigate('/goal/current/understand')}
                className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700"
              >
                <Edit2 className="w-4 h-4" /> {t('plan.edit_plan')}
              </button>
              <button
                onClick={handleStart}
                disabled={isStarting || !canStart}
                className="flex items-center gap-2 bg-primary-600 text-white text-sm font-semibold px-6 py-2.5 rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isStarting ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Starting…</>
                ) : (
                  <><Play className="w-4 h-4" /> {t('plan.start_execution')}</>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  )
}
