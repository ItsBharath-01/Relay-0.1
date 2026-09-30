import type { ReactNode } from 'react'
import React, { useEffect } from 'react'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { useUIStore } from '../../stores/uiStore'
import { useApprovalStore } from '../../stores/approvalStore'
import { VoiceModal } from '../ui/VoiceModal'

// LLM status inline dot
const LLMDot: React.FC = () => {
  const { llmHealth } = useUIStore()
  if (!llmHealth) return null

  const colors: Record<string, string> = {
    ready: 'bg-emerald-500',
    unavailable: 'bg-amber-400',
    model_missing: 'bg-amber-400',
    backend_unavailable: 'bg-rose-500',
    error: 'bg-rose-500',
  }
  const color = colors[llmHealth.status] || 'bg-slate-400'
  const label = llmHealth.status === 'ready'
    ? `LLM: ${llmHealth.model}`
    : `LLM: ${llmHealth.status.replace(/_/g, ' ')}`

  return (
    <span className="hidden md:flex items-center gap-1.5 text-xs text-slate-500 px-2 py-1 rounded-lg border border-slate-200">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${color} ${llmHealth.status === 'ready' ? '' : 'animate-pulse'}`} />
      {label}
    </span>
  )
}

interface AppShellProps {
  children?: ReactNode
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const { sidebarCollapsed, toggleSidebar, mobileMenuOpen, setMobileMenuOpen } = useUIStore()
  const { fetchApprovals } = useApprovalStore()

  useEffect(() => {
    fetchApprovals('pending').catch(() => {})
  }, [fetchApprovals])

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={toggleSidebar}
        mobileOpen={mobileMenuOpen}
        onMobileClose={() => setMobileMenuOpen(false)}
      />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <TopBar
          onMenuOpen={() => setMobileMenuOpen(true)}
          llmIndicator={<LLMDot />}
        />
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
      {/* Voice command modal — portal, always rendered when isOpen */}
      <VoiceModal />
    </div>
  )
}
