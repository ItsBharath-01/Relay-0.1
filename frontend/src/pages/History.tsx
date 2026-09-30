import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { History as HistoryIcon, CheckCircle, XCircle, Clock, ChevronRight, Zap } from 'lucide-react'
import { apiClient } from '../services/api'
import { useTranslation } from '../i18n/i18nContext'
import { AppShell } from '../components/layout/AppShell'

interface HistoryItem {
  id: string
  goal_text: string
  status: string
  progress: number
  started_at: string
  completed_at?: string | null
}

export default function History() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [items, setItems] = useState<HistoryItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiClient.get<HistoryItem[]>('/api/history')
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setIsLoading(false))
  }, [])

  const statusIcon = (status: string) => {
    if (status === 'completed') return <CheckCircle className="w-4 h-4 text-emerald-500" />
    if (status === 'failed' || status === 'cancelled') return <XCircle className="w-4 h-4 text-rose-400" />
    if (status === 'running') return <Zap className="w-4 h-4 text-blue-500 animate-pulse" />
    return <Clock className="w-4 h-4 text-slate-400" />
  }

  const duration = (start: string, end?: string | null) => {
    const s = new Date(start).getTime()
    const e = end ? new Date(end).getTime() : Date.now()
    const secs = Math.round((e - s) / 1000)
    if (secs < 60) return `${secs}s`
    return `${Math.round(secs / 60)}m`
  }

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="flex items-center gap-2 mb-6">
          <HistoryIcon className="w-5 h-5 text-primary-600" />
          <h1 className="text-xl font-bold text-slate-900">{t('nav.history')}</h1>
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-20 bg-slate-100 rounded-xl animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-700">{error}</div>
        ) : items.length === 0 ? (
          <div className="text-center py-16">
            <HistoryIcon className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500 text-sm">{t('dash.empty_recent')}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((item) => (
              <button
                key={item.id}
                onClick={() => navigate(`/execution/${item.id}`)}
                className="w-full text-left bg-white border border-slate-200 rounded-xl p-4 hover:border-primary-200 hover:bg-primary-50/30 transition-colors group"
              >
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 shrink-0">{statusIcon(item.status)}</div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">{item.goal_text}</p>
                    <div className="flex items-center gap-3 mt-1">
                      <span className={`text-xs font-medium capitalize ${
                        item.status === 'completed' ? 'text-emerald-600'
                        : item.status === 'failed' ? 'text-rose-600'
                        : item.status === 'running' ? 'text-blue-600'
                        : 'text-slate-500'
                      }`}>{item.status}</span>
                      <span className="text-xs text-slate-400">
                        {new Date(item.started_at).toLocaleDateString()} · {duration(item.started_at, item.completed_at)}
                      </span>
                      {item.status === 'running' && (
                        <span className="text-xs text-blue-600">{Math.round(item.progress * 100)}%</span>
                      )}
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-primary-500 transition-colors mt-1 shrink-0" />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  )
}
