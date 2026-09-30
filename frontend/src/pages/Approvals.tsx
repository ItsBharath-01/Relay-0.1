import React, { useEffect } from 'react'
import { CheckCircle, XCircle, Shield, Clock } from 'lucide-react'
import { useApprovalStore } from '../stores/approvalStore'
import { useTranslation } from '../i18n/i18nContext'
import { AppShell } from '../components/layout/AppShell'
import type { Approval } from '../types'

function ApprovalCard({ approval, onDecide }: {
  approval: Approval
  onDecide: (id: string, d: 'approved' | 'rejected') => void
}) {
  const { t } = useTranslation()
  const [deciding, setDeciding] = React.useState(false)

  const riskColors: Record<string, string> = {
    low: 'border-l-emerald-400', medium: 'border-l-amber-400',
    high: 'border-l-orange-500', critical: 'border-l-rose-500',
  }

  const statusBadge: Record<string, string> = {
    pending: 'bg-violet-50 text-violet-700 border-violet-200',
    approved: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    rejected: 'bg-rose-50 text-rose-700 border-rose-200',
    expired: 'bg-slate-50 text-slate-500 border-slate-200',
  }

  const handle = async (d: 'approved' | 'rejected') => {
    setDeciding(true)
    await onDecide(approval.id, d)
    setDeciding(false)
  }

  return (
    <div className={`bg-white border border-slate-200 rounded-xl overflow-hidden border-l-4 ${riskColors[approval.risk] || riskColors.high}`}>
      <div className="p-5">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <Shield className="w-4 h-4 text-violet-600" />
              <h3 className="text-sm font-semibold text-slate-900">{approval.action}</h3>
              <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${statusBadge[approval.status]}`}>
                {approval.status}
              </span>
            </div>
            {approval.target && <p className="text-xs text-slate-500 ml-6">{approval.target}</p>}
          </div>
          <span className="text-xs text-slate-400 shrink-0 flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {new Date(approval.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>

        <div className="space-y-2 text-xs text-slate-600">
          <div>
            <span className="font-semibold text-slate-400 uppercase tracking-wider">Reason: </span>
            {approval.reason}
          </div>
          {approval.consequences && (
            <div>
              <span className="font-semibold text-slate-400 uppercase tracking-wider">If approved: </span>
              {approval.consequences}
            </div>
          )}
          <div className="font-mono text-slate-400 truncate">
            SHA-256: {approval.payload_hash.substring(0, 32)}…
          </div>
        </div>

        {approval.status === 'pending' && (
          <div className="flex gap-2 mt-4">
            <button
              onClick={() => handle('rejected')}
              disabled={deciding}
              className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg border border-rose-200 text-rose-700 text-xs font-semibold hover:bg-rose-50 transition-colors disabled:opacity-50"
            >
              <XCircle className="w-3.5 h-3.5" /> {t('approval.reject_button')}
            </button>
            <button
              onClick={() => handle('approved')}
              disabled={deciding}
              className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-50"
            >
              <CheckCircle className="w-3.5 h-3.5" /> {t('approval.approve_button')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Approvals() {
  const { t } = useTranslation()
  const { approvals, isLoading, fetchApprovals, decide } = useApprovalStore()

  useEffect(() => {
    fetchApprovals()
  }, [fetchApprovals])

  const pending = approvals.filter(a => a.status === 'pending')
  const past = approvals.filter(a => a.status !== 'pending')

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto px-4 py-8">
        <h1 className="text-xl font-bold text-slate-900 mb-6">{t('nav.approvals')}</h1>

        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-28 bg-slate-100 rounded-xl animate-pulse" />
            ))}
          </div>
        ) : (
          <>
            {pending.length > 0 && (
              <div className="mb-6">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-violet-600 mb-3">
                  Pending ({pending.length})
                </h2>
                <div className="space-y-3">
                  {pending.map(a => (
                    <ApprovalCard key={a.id} approval={a} onDecide={decide} />
                  ))}
                </div>
              </div>
            )}

            {past.length > 0 && (
              <div>
                <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
                  Past decisions ({past.length})
                </h2>
                <div className="space-y-3">
                  {past.map(a => (
                    <ApprovalCard key={a.id} approval={a} onDecide={decide} />
                  ))}
                </div>
              </div>
            )}

            {approvals.length === 0 && (
              <div className="text-center py-16">
                <CheckCircle className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                <p className="text-slate-500 text-sm">{t('dash.empty_approvals')}</p>
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  )
}
