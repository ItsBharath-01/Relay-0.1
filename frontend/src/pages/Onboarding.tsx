import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, ChevronRight, ChevronLeft } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useTranslation } from '../i18n/i18nContext'

const STEPS = 3

const WORK_AREAS = [
  'Research & Analysis', 'Calendar & Scheduling', 'Email & Comms',
  'Task Management', 'Content Creation', 'Data & Reporting',
  'Engineering & Code', 'Customer Support',
]

export default function Onboarding() {
  const { t } = useTranslation()
  const { updatePreferences } = useAuthStore()
  const navigate = useNavigate()

  const [step, setStep] = useState(1)
  const [selectedAreas, setSelectedAreas] = useState<string[]>([])
  const [prefs, setPrefs] = useState({
    ask_external_messages: true,
    ask_payments: true,
    ask_deleting: true,
    ask_sensitive_info: true,
  })

  const toggleArea = (area: string) => {
    setSelectedAreas((prev) =>
      prev.includes(area) ? prev.filter((a) => a !== area) : [...prev, area]
    )
  }

  const handleFinish = async () => {
    try {
      await updatePreferences(prefs)
    } catch {
      // Non-critical; proceed anyway
    }
    navigate('/dashboard', { replace: true })
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-lg">
        {/* Brand */}
        <div className="text-center mb-8">
          <span className="font-bold text-xl text-primary-600 tracking-tight">Relay</span>
          {/* Stepper */}
          <div className="flex items-center justify-center gap-2 mt-4">
            {Array.from({ length: STEPS }, (_, i) => (
              <React.Fragment key={i}>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-colors ${
                  i + 1 < step ? 'bg-emerald-600 border-emerald-600 text-white'
                  : i + 1 === step ? 'bg-primary-600 border-primary-600 text-white'
                  : 'bg-white border-slate-300 text-slate-400'
                }`}>
                  {i + 1 < step ? <Check className="w-3.5 h-3.5" /> : i + 1}
                </div>
                {i < STEPS - 1 && (
                  <div className={`flex-1 h-0.5 max-w-[60px] ${i + 1 < step ? 'bg-emerald-400' : 'bg-slate-200'}`} />
                )}
              </React.Fragment>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-subtle p-8">
          {/* Step 1 – Work areas */}
          {step === 1 && (
            <div>
              <h2 className="text-lg font-bold text-slate-900 mb-1">{t('onboarding.step1_title')}</h2>
              <p className="text-sm text-slate-500 mb-5">{t('onboarding.step1_desc')}</p>
              <div className="grid grid-cols-2 gap-2">
                {WORK_AREAS.map((area) => {
                  const selected = selectedAreas.includes(area)
                  return (
                    <button
                      key={area}
                      onClick={() => toggleArea(area)}
                      className={`text-sm px-3 py-2.5 rounded-lg border text-left transition-colors font-medium ${
                        selected
                          ? 'border-primary-500 bg-primary-50 text-primary-700'
                          : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        {selected && <Check className="w-3.5 h-3.5 shrink-0" />}
                        {area}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Step 2 – Connections */}
          {step === 2 && (
            <div>
              <h2 className="text-lg font-bold text-slate-900 mb-1">{t('onboarding.step2_title')}</h2>
              <p className="text-sm text-slate-500 mb-5">{t('onboarding.step2_desc')}</p>
              <div className="space-y-2">
                {['Google Calendar', 'Gmail', 'Playwright Browser (Built-in)', 'Slack (Coming soon)', 'GitHub (Coming soon)'].map((app) => {
                  const builtIn = app.includes('Built-in')
                  const soon = app.includes('Coming soon')
                  return (
                    <div key={app} className="flex items-center justify-between px-4 py-3 rounded-lg border border-slate-200">
                      <span className="text-sm font-medium text-slate-700">{app.split(' (')[0]}</span>
                      {builtIn ? (
                        <span className="text-xs text-emerald-600 font-medium">Connected</span>
                      ) : soon ? (
                        <span className="text-xs text-purple-600 font-medium">Coming soon</span>
                      ) : (
                        <button
                          onClick={() => navigate('/connections')}
                          className="text-xs text-primary-600 font-medium hover:underline"
                        >
                          Connect in settings →
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
              <p className="mt-3 text-xs text-slate-400">
                You can connect applications anytime from <strong>Connections</strong> in the sidebar.
              </p>
            </div>
          )}

          {/* Step 3 – Approval preferences */}
          {step === 3 && (
            <div>
              <h2 className="text-lg font-bold text-slate-900 mb-1">{t('onboarding.step3_title')}</h2>
              <p className="text-sm text-slate-500 mb-5">{t('onboarding.step3_desc')}</p>
              <div className="space-y-3">
                {(
                  [
                    ['ask_external_messages', t('onboarding.toggle_external_messages')],
                    ['ask_payments', t('onboarding.toggle_payments')],
                    ['ask_deleting', t('onboarding.toggle_deleting')],
                    ['ask_sensitive_info', t('onboarding.toggle_sensitive')],
                  ] as [keyof typeof prefs, string][]
                ).map(([key, label]) => (
                  <label key={key} className="flex items-start justify-between gap-4 cursor-pointer">
                    <span className="text-sm text-slate-700">{label}</span>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={prefs[key]}
                      onClick={() => setPrefs((p) => ({ ...p, [key]: !p[key] }))}
                      className={`relative inline-flex h-6 w-11 shrink-0 rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 ${prefs[key] ? 'bg-primary-600' : 'bg-slate-300'}`}
                    >
                      <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 ${prefs[key] ? 'translate-x-5' : 'translate-x-0'}`} />
                    </button>
                  </label>
                ))}
              </div>
              <p className="mt-4 text-xs text-slate-400">
                Critical and high-risk actions always require your approval regardless of these settings.
              </p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between mt-5">
          {step > 1 ? (
            <button onClick={() => setStep(s => s - 1)} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700">
              <ChevronLeft className="w-4 h-4" /> Back
            </button>
          ) : (
            <button onClick={() => navigate('/dashboard')} className="text-sm text-slate-400 hover:text-slate-600">
              {t('onboarding.skip')}
            </button>
          )}

          {step < STEPS ? (
            <button
              onClick={() => setStep(s => s + 1)}
              className="flex items-center gap-1.5 bg-primary-600 text-white text-sm font-semibold px-5 py-2.5 rounded-lg hover:bg-primary-700 transition-colors"
            >
              {t('onboarding.next')} <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={handleFinish}
              className="flex items-center gap-1.5 bg-emerald-600 text-white text-sm font-semibold px-5 py-2.5 rounded-lg hover:bg-emerald-700 transition-colors"
            >
              {t('onboarding.finish')} <ChevronRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
