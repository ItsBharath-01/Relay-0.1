import { MCPRegistrationModal, Button } from '../components/ui'
import { useEffect, useState } from 'react'
import { Plug, Lock, Unlock, ExternalLink } from 'lucide-react'
import { useConnectionStore } from '../stores/connectionStore'
import { useUIStore } from '../stores/uiStore'
import { useTranslation } from '../i18n/i18nContext'
import { AppShell } from '../components/layout/AppShell'
import type { Connection } from '../types'

const APP_ICONS: Record<string, string> = {
  google_calendar: '📅', gmail: '📧', browser: '🌐',
  slack: '💬', github: '🐙', mcp: '🤖', rest_connector: '🔌',
}

function ConnectionCard({ conn }: { conn: Connection }) {
  const { t } = useTranslation()
  const { togglePermission, disconnectApp } = useConnectionStore()
  const { addToast } = useUIStore()
  const [expanded, setExpanded] = useState(false)

  const isSoon = conn.status === 'coming_soon'
  const isConnected = conn.status === 'connected'

  const statusConfig: Record<string, { cls: string; dot: string; label: string }> = {
    connected: { cls: 'text-emerald-700 bg-emerald-50 border-emerald-200', dot: 'bg-emerald-500', label: 'Connected' },
    not_connected: { cls: 'text-slate-600 bg-slate-50 border-slate-200', dot: 'bg-slate-400', label: 'Not connected' },
    coming_soon: { cls: 'text-purple-700 bg-purple-50 border-purple-200', dot: 'bg-purple-400', label: 'Coming soon' },
    error: { cls: 'text-rose-700 bg-rose-50 border-rose-200', dot: 'bg-rose-500', label: 'Error' },
    needs_reconnection: { cls: 'text-amber-700 bg-amber-50 border-amber-200', dot: 'bg-amber-400 animate-pulse', label: 'Needs reconnection' },
  }
  const sc = statusConfig[conn.status] || statusConfig.not_connected

  const handleTogglePerm = async (key: string, granted: boolean) => {
    try {
      await togglePermission(conn.id, key, granted)
      addToast({ type: 'success', message: `Permission ${granted ? 'granted' : 'revoked'}.` })
    } catch (e: any) {
      addToast({ type: 'error', message: e.message || 'Failed to update permission.' })
    }
  }

  const handleDisconnect = async () => {
    try {
      await disconnectApp(conn.id)
      addToast({ type: 'success', message: `${conn.name} disconnected.` })
    } catch (e: any) {
      addToast({ type: 'error', message: e.message || 'Failed to disconnect.' })
    }
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="flex items-center gap-4 p-4">
        <span className="text-2xl shrink-0">{APP_ICONS[conn.app_id] || '🔌'}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-900">{conn.name}</h3>
            <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border font-medium ${sc.cls}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
              {sc.label}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">Auth: {conn.auth_type}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {isSoon && (
            <span className="text-xs text-purple-600 font-medium">Coming soon</span>
          )}
          {!isSoon && !isConnected && (
            <a
              href="/connections"
              className="text-xs text-primary-600 font-medium hover:underline flex items-center gap-1"
              onClick={(e) => { e.preventDefault(); alert('OAuth flow requires server-side callback setup. Add your Google OAuth credentials to backend/.env') }}
            >
              Connect <ExternalLink className="w-3 h-3" />
            </a>
          )}
          {isConnected && conn.app_id !== 'browser' && (
            <button onClick={handleDisconnect} className="text-xs text-rose-600 hover:underline">
              {t('common.disconnect')}
            </button>
          )}
          {conn.permissions.length > 0 && !isSoon && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-xs text-slate-500 hover:text-slate-700 px-2 py-1 rounded border border-slate-200 hover:bg-slate-50"
            >
              {expanded ? 'Hide' : 'Permissions'}
            </button>
          )}
        </div>
      </div>

      {/* Permissions panel */}
      {expanded && conn.permissions.length > 0 && (
        <div className="border-t border-slate-100 px-4 py-3 bg-slate-50">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Granular Permissions</p>
          <div className="space-y-2">
            {conn.permissions.map((perm) => (
              <label key={perm.key} className="flex items-center justify-between gap-3 cursor-pointer">
                <div className="flex items-center gap-2">
                  {perm.is_sensitive ? (
                    <Lock className="w-3 h-3 text-amber-500 shrink-0" />
                  ) : (
                    <Unlock className="w-3 h-3 text-slate-400 shrink-0" />
                  )}
                  <span className="text-xs text-slate-700">{perm.label}</span>
                  {perm.is_sensitive && (
                    <span className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">sensitive</span>
                  )}
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={perm.is_granted}
                  onClick={() => handleTogglePerm(perm.key, !perm.is_granted)}
                  className={`relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 ${
                    perm.is_granted ? 'bg-primary-600' : 'bg-slate-300'
                  }`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${perm.is_granted ? 'translate-x-4' : 'translate-x-0'}`} />
                </button>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}


export default function Connections() {
  const { t } = useTranslation()
  const { connections, isLoading, fetchConnections } = useConnectionStore()
  const [isMCPModalOpen, setIsMCPModalOpen] = useState(false)

  useEffect(() => {
    fetchConnections()
  }, [fetchConnections])

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Plug className="w-5 h-5 text-primary-600" />
            <h1 className="text-xl font-bold text-slate-900">{t('nav.connections')}</h1>
          </div>
          <Button variant="outline" size="sm" onClick={() => setIsMCPModalOpen(true)}>
            + Add MCP Server
          </Button>
        </div>
        <p className="text-sm text-slate-500 mb-6">
          Relay uses only the applications you connect, with granular permission control. All credentials are encrypted at rest.
        </p>

        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-20 bg-slate-100 rounded-xl animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {connections.map(conn => (
              <ConnectionCard key={conn.id} conn={conn} />
            ))}
            {connections.length === 0 && (
              <div className="text-center py-12 text-slate-400 text-sm">No connections found.</div>
            )}
          </div>
        )}
      </div>
      
      <MCPRegistrationModal 
        isOpen={isMCPModalOpen} 
        onClose={() => setIsMCPModalOpen(false)} 
      />
    </AppShell>
  )
}
