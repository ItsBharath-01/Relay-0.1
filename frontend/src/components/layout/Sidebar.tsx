import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  Home, Plus, Zap, History, CheckSquare, Plug, Settings, HelpCircle,
  ChevronLeft, ChevronRight, LogOut, X
} from 'lucide-react'
import { useAuthStore } from '../../stores/authStore'
import { useApprovalStore } from '../../stores/approvalStore'
import { useTranslation } from '../../i18n/i18nContext'

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
  mobileOpen: boolean
  onMobileClose: () => void
}

interface NavItem {
  to: string
  icon: React.FC<{ className?: string }>
  labelKey: string
  badge?: number
}

export const Sidebar: React.FC<SidebarProps> = ({ collapsed, onToggle, mobileOpen, onMobileClose }) => {
  const { t } = useTranslation()
  const { logout, user } = useAuthStore()
  const { pendingCount } = useApprovalStore()
  const navigate = useNavigate()

  const navItems: NavItem[] = [
    { to: '/dashboard', icon: Home, labelKey: 'nav.home' },
    { to: '/goal/new', icon: Plus, labelKey: 'nav.new' },
    { to: '/history', icon: Zap, labelKey: 'nav.active' },
    { to: '/history', icon: History, labelKey: 'nav.history' },
    { to: '/approvals', icon: CheckSquare, labelKey: 'nav.approvals', badge: pendingCount },
    { to: '/connections', icon: Plug, labelKey: 'nav.connections' },
    { to: '/settings', icon: Settings, labelKey: 'nav.settings' },
    { to: '/help', icon: HelpCircle, labelKey: 'nav.help' },
  ]

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  const sidebarContent = (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className={`flex items-center px-4 py-4 border-b border-slate-200 ${collapsed ? 'justify-center' : 'justify-between'}`}>
        {!collapsed && (
          <span className="font-bold text-lg text-primary-600 tracking-tight select-none">Relay</span>
        )}
        <button
          onClick={onToggle}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors hidden lg:flex"
          aria-label="Toggle sidebar"
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
        <button onClick={onMobileClose} className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:bg-slate-100">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.labelKey}
            to={item.to}
            onClick={onMobileClose}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors relative ${
                isActive
                  ? 'bg-primary-50 text-primary-700'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              } ${collapsed ? 'justify-center' : ''}`
            }
          >
            <item.icon className="w-4 h-4 shrink-0" />
            {!collapsed && <span>{t(item.labelKey)}</span>}
            {item.badge !== undefined && item.badge > 0 && (
              <span className={`${collapsed ? 'absolute -top-1 -right-1' : 'ml-auto'} bg-violet-600 text-white text-xs font-bold rounded-full px-1.5 py-0.5 min-w-[18px] text-center leading-none`}>
                {item.badge}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-3 py-3 border-t border-slate-200">
        {!collapsed && user && (
          <div className="px-3 py-2 mb-1">
            <p className="text-xs font-semibold text-slate-700 truncate">{user.name}</p>
            <p className="text-xs text-slate-400 truncate">{user.email}</p>
          </div>
        )}
        <button
          onClick={handleLogout}
          className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm text-slate-500 hover:bg-rose-50 hover:text-rose-600 transition-colors ${collapsed ? 'justify-center' : ''}`}
        >
          <LogOut className="w-4 h-4 shrink-0" />
          {!collapsed && <span>Sign out</span>}
        </button>
      </div>
    </div>
  )

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className={`hidden lg:flex flex-col bg-white border-r border-slate-200 transition-all duration-200 shrink-0 ${
          collapsed ? 'w-16' : 'w-56'
        }`}
      >
        {sidebarContent}
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" onClick={onMobileClose} />
          <aside className="relative flex flex-col w-56 bg-white shadow-xl z-50">
            {sidebarContent}
          </aside>
        </div>
      )}
    </>
  )
}
