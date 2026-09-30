import { useState } from 'react'
import { Settings as SettingsIcon, User, Bell, Shield, Cpu } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useUIStore } from '../stores/uiStore'
import { useTranslation } from '../i18n/i18nContext'
import { AppShell } from '../components/layout/AppShell'

export default function Settings() {
  const { t, language, setLanguage, supportedLanguages } = useTranslation()
  const { user, updatePreferences } = useAuthStore()
  const { llmHealth, checkLLMHealth } = useUIStore()
  const prefs = user?.preferences

  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [localPrefs, setLocalPrefs] = useState({
    ask_external_messages: prefs?.ask_external_messages ?? true,
    ask_payments: prefs?.ask_payments ?? true,
    ask_deleting: prefs?.ask_deleting ?? true,
    ask_sensitive_info: prefs?.ask_sensitive_info ?? true,
    auto_recover: prefs?.auto_recover ?? true,
  })

  const handleSave = async () => {
    setSaving(true)
    try {
      await updatePreferences(localPrefs)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } finally {
      setSaving(false)
    }
  }

  const ToggleRow = ({ field, label }: { field: keyof typeof localPrefs; label: string }) => (
    <label className="flex items-center justify-between py-3 border-b border-slate-100 last:border-0 cursor-pointer">
      <span className="text-sm text-slate-700">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={localPrefs[field]}
        onClick={() => setLocalPrefs(p => ({ ...p, [field]: !p[field] }))}
        className={`relative inline-flex h-6 w-11 shrink-0 rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 ${localPrefs[field] ? 'bg-primary-600' : 'bg-slate-300'}`}
      >
        <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${localPrefs[field] ? 'translate-x-5' : 'translate-x-0'}`} />
      </button>
    </label>
  )

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
        <div className="flex items-center gap-2 mb-2">
          <SettingsIcon className="w-5 h-5 text-primary-600" />
          <h1 className="text-xl font-bold text-slate-900">{t('nav.settings')}</h1>
        </div>

        {/* Profile */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <User className="w-4 h-4 text-slate-500" />
            <h2 className="text-sm font-semibold text-slate-800">Profile</h2>
          </div>
          <div className="space-y-2 text-sm text-slate-700">
            <div className="flex gap-2"><span className="text-slate-400 w-16">Name</span><strong>{user?.name}</strong></div>
            <div className="flex gap-2"><span className="text-slate-400 w-16">Email</span><span>{user?.email}</span></div>
          </div>
        </div>

        {/* Language */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Bell className="w-4 h-4 text-slate-500" />
            <h2 className="text-sm font-semibold text-slate-800">Language</h2>
          </div>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="text-sm border border-slate-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 w-full md:w-auto"
          >
            {supportedLanguages.map((l) => (
              <option key={l.code} value={l.code}>{l.nativeName} ({l.name})</option>
            ))}
          </select>
        </div>

        {/* Approval preferences */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Shield className="w-4 h-4 text-slate-500" />
            <h2 className="text-sm font-semibold text-slate-800">Approval & Autonomy</h2>
          </div>
          <ToggleRow field="ask_external_messages" label={t('onboarding.toggle_external_messages')} />
          <ToggleRow field="ask_payments" label={t('onboarding.toggle_payments')} />
          <ToggleRow field="ask_deleting" label={t('onboarding.toggle_deleting')} />
          <ToggleRow field="ask_sensitive_info" label={t('onboarding.toggle_sensitive')} />
          <ToggleRow field="auto_recover" label="Automatically attempt recovery on tool failure" />

          <button
            onClick={handleSave}
            disabled={saving}
            className="mt-4 flex items-center gap-2 bg-primary-600 text-white text-sm font-semibold px-5 py-2 rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-60"
          >
            {saving && <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
            {saved ? '✓ Saved!' : t('common.save')}
          </button>
        </div>

        {/* LLM status */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Cpu className="w-4 h-4 text-slate-500" />
            <h2 className="text-sm font-semibold text-slate-800">AI Engine Status</h2>
          </div>
          {llmHealth ? (
            <div className="space-y-2 text-sm">
              <div className="flex gap-2"><span className="text-slate-400 w-20">Provider</span><span>{llmHealth.provider}</span></div>
              <div className="flex gap-2"><span className="text-slate-400 w-20">Model</span><code className="font-mono text-xs">{llmHealth.model}</code></div>
              <div className="flex items-center gap-2">
                <span className="text-slate-400 w-20">Status</span>
                <span className={`flex items-center gap-1.5 text-xs font-semibold ${
                  llmHealth.status === 'ready' ? 'text-emerald-700' : 'text-rose-700'
                }`}>
                  <span className={`w-2 h-2 rounded-full ${llmHealth.status === 'ready' ? 'bg-emerald-500' : 'bg-rose-500 animate-pulse'}`} />
                  {llmHealth.status}
                </span>
              </div>
              {llmHealth.error && (
                <p className="text-xs text-rose-600 mt-1">{llmHealth.error}</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-500">Checking…</p>
          )}
          <button
            onClick={() => checkLLMHealth()}
            className="mt-3 text-xs text-primary-600 hover:underline font-medium"
          >
            Refresh status
          </button>
        </div>
      </div>
    </AppShell>
  )
}
