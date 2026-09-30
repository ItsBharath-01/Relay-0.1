import React from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Zap, CheckCircle, Shield, Globe } from 'lucide-react'
import { useTranslation } from '../i18n/i18nContext'
import { useAuthStore } from '../stores/authStore'
import { useUIStore } from '../stores/uiStore'

const FLOW_STEPS = [
  'flow_goal', 'flow_plan', 'flow_execute', 'flow_verify', 'flow_recover', 'flow_complete'
]

const CAPABILITY_ICONS = [
  { icon: Globe, label: 'Web Search & Read' },
  { icon: Zap, label: 'Browser Automation' },
  { icon: CheckCircle, label: 'Calendar & Email' },
  { icon: Shield, label: 'Risk Gating' },
]

export default function Landing() {
  const { t } = useTranslation()
  const { isAuthenticated } = useAuthStore()
  const { llmHealth } = useUIStore()
  const navigate = useNavigate()

  const handleStart = () => {
    if (isAuthenticated) navigate('/dashboard')
    else navigate('/signup')
  }

  return (
    <div className="min-h-screen bg-white flex flex-col">
      {/* Nav */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
        <span className="font-bold text-xl text-primary-600 tracking-tight">Relay</span>
        <div className="flex items-center gap-3">
          {/* LLM status pill */}
          {llmHealth && (
            <span className={`hidden md:flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
              llmHealth.status === 'ready'
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-amber-50 text-amber-700 border-amber-200'
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${llmHealth.status === 'ready' ? 'bg-emerald-500' : 'bg-amber-400 animate-pulse'}`} />
              {llmHealth.status === 'ready' ? `${llmHealth.model} ready` : 'LLM offline'}
            </span>
          )}
          <button
            onClick={() => navigate('/login')}
            className="text-sm text-slate-600 hover:text-slate-900 font-medium px-3 py-1.5"
          >
            {t('landing.sign_in')}
          </button>
          <button
            onClick={handleStart}
            className="inline-flex items-center gap-1.5 text-sm font-medium bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors"
          >
            {t('landing.start_relay')} <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center text-center px-6 py-20 max-w-4xl mx-auto w-full">
        {/* Flow pill */}
        <div className="flex items-center gap-0 mb-10 overflow-x-auto">
          {FLOW_STEPS.map((key, i) => (
            <React.Fragment key={key}>
              <span className={`text-xs font-semibold px-3 py-1.5 rounded-full border shrink-0 ${
                i === 0 ? 'bg-primary-600 text-white border-primary-600'
                : i === FLOW_STEPS.length - 1 ? 'bg-emerald-600 text-white border-emerald-600'
                : 'bg-white text-slate-600 border-slate-200'
              }`}>
                {t(`landing.${key}`)}
              </span>
              {i < FLOW_STEPS.length - 1 && (
                <ArrowRight className="w-3 h-3 text-slate-300 mx-1 shrink-0" />
              )}
            </React.Fragment>
          ))}
        </div>

        <h1 className="text-4xl md:text-5xl font-bold text-slate-900 leading-tight mb-4 tracking-tight">
          {t('landing.hero_title')}
        </h1>
        <p className="text-lg text-slate-500 max-w-2xl mb-10 leading-relaxed">
          {t('landing.hero_subtitle')}
        </p>

        <button
          onClick={handleStart}
          className="inline-flex items-center gap-2 bg-primary-600 text-white text-base font-semibold px-7 py-3.5 rounded-xl hover:bg-primary-700 active:bg-primary-800 transition-colors shadow-lifted"
        >
          {t('landing.start_relay')} <ArrowRight className="w-4 h-4" />
        </button>

        {/* Capabilities */}
        <div className="mt-20 w-full">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-6">
            {t('landing.capabilities_header')}
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {CAPABILITY_ICONS.map(({ icon: Icon, label }) => (
              <div key={label} className="flex flex-col items-center gap-2 p-4 rounded-xl border border-slate-200 bg-slate-50">
                <Icon className="w-5 h-5 text-primary-600" />
                <span className="text-xs text-slate-600 font-medium text-center">{label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Honesty notice */}
        {llmHealth && llmHealth.status !== 'ready' && (
          <div className="mt-10 p-4 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-800 max-w-lg">
            <strong>Notice:</strong> The AI engine is currently {llmHealth.status.replace(/_/g, ' ')}. 
            Goal analysis requires Ollama with qwen3:4b running locally.
          </div>
        )}
      </main>

      <footer className="py-6 text-center text-xs text-slate-400 border-t border-slate-100">
        Relay — Real execution, zero fabrication.
      </footer>
    </div>
  )
}
