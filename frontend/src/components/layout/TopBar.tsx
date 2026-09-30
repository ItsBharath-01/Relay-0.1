import React from 'react'
import { Menu, Mic, Bell } from 'lucide-react'
import { useTranslation } from '../../i18n/i18nContext'
import { useApprovalStore } from '../../stores/approvalStore'
import { useVoiceStore } from '../../stores/voiceStore'

interface TopBarProps {
  onMenuOpen: () => void
  llmIndicator?: React.ReactNode
}

export const TopBar: React.FC<TopBarProps> = ({ onMenuOpen, llmIndicator }) => {
  const { language, setLanguage, supportedLanguages } = useTranslation()
  const { pendingCount } = useApprovalStore()
  const { setIsOpen, isSupported } = useVoiceStore()

  return (
    <header className="h-14 flex items-center justify-between px-4 bg-white border-b border-slate-200 shrink-0">
      {/* Left */}
      <div className="flex items-center gap-3">
        {/* Mobile hamburger */}
        <button
          onClick={onMenuOpen}
          className="lg:hidden p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 transition-colors"
          aria-label="Open menu"
        >
          <Menu className="w-5 h-5" />
        </button>

        {/* Mobile brand */}
        <span className="lg:hidden font-bold text-primary-600 tracking-tight">Relay</span>
      </div>

      {/* Right */}
      <div className="flex items-center gap-2">
        {/* LLM status */}
        {llmIndicator}

        {/* Language switcher */}
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="text-xs text-slate-600 bg-transparent border border-slate-200 rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-primary-500 cursor-pointer"
          aria-label="Language"
        >
          {supportedLanguages.map((l) => (
            <option key={l.code} value={l.code}>
              {l.nativeName}
            </option>
          ))}
        </select>

        {/* Voice button */}
        {isSupported && (
          <button
            onClick={() => setIsOpen(true)}
            className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 hover:text-primary-600 transition-colors"
            aria-label="Voice commands"
          >
            <Mic className="w-4 h-4" />
          </button>
        )}

        {/* Approvals bell */}
        <button
          className="relative p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 transition-colors"
          aria-label={`${pendingCount} pending approvals`}
        >
          <Bell className="w-4 h-4" />
          {pendingCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 bg-violet-600 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
              {pendingCount}
            </span>
          )}
        </button>
      </div>
    </header>
  )
}
