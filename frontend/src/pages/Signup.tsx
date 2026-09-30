import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Mail, Lock, User, Eye, EyeOff, ArrowLeft, Check, X } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useTranslation } from '../i18n/i18nContext'

function PasswordRule({ met, label }: { met: boolean; label: string }) {
  return (
    <div className={`flex items-center gap-1.5 text-xs ${met ? 'text-emerald-600' : 'text-slate-400'}`}>
      {met ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
      {label}
    </div>
  )
}

export default function Signup() {
  const { t } = useTranslation()
  const { signup, isLoading, error, clearError } = useAuthStore()
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPw, setShowPw] = useState(false)

  const hasMin = password.length >= 8
  const hasNum = /\d/.test(password)
  const matches = password === confirm && confirm.length > 0

  const valid = hasMin && hasNum && matches && name.trim().length > 0 && email.includes('@')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    clearError()
    try {
      await signup(name.trim(), email, password)
      navigate('/onboarding', { replace: true })
    } catch {
      // error shown from store
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <span className="font-bold text-2xl text-primary-600 tracking-tight">Relay</span>
          <h1 className="mt-2 text-xl font-bold text-slate-900">{t('auth.sign_up_title')}</h1>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-subtle p-8">
          {error && (
            <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded-lg text-sm text-rose-700">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Name */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                {t('auth.name')}
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text" value={name} onChange={(e) => setName(e.target.value)}
                  required autoComplete="name" placeholder="Jane Smith"
                  className="w-full pl-9 pr-3.5 py-2.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
            </div>

            {/* Email */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                {t('auth.email')}
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  required autoComplete="email" placeholder="you@example.com"
                  className="w-full pl-9 pr-3.5 py-2.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                {t('auth.password')}
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type={showPw ? 'text' : 'password'} value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required autoComplete="new-password" placeholder="••••••••"
                  className="w-full pl-9 pr-10 py-2.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
                <button type="button" onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <div className="mt-2 flex flex-col gap-1 pl-1">
                <PasswordRule met={hasMin} label={t('auth.rule_min_length')} />
                <PasswordRule met={hasNum} label={t('auth.rule_number')} />
              </div>
            </div>

            {/* Confirm */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                {t('auth.confirm_password')}
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type={showPw ? 'text' : 'password'} value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required autoComplete="new-password" placeholder="••••••••"
                  className={`w-full pl-9 pr-3.5 py-2.5 text-sm border rounded-lg focus:outline-none focus:ring-2 ${
                    confirm && !matches
                      ? 'border-rose-400 focus:ring-rose-400'
                      : 'border-slate-300 focus:ring-primary-500 focus:border-primary-500'
                  }`}
                />
              </div>
              {confirm && !matches && (
                <p className="mt-1 text-xs text-rose-600">{t('auth.password_mismatch')}</p>
              )}
            </div>

            <button
              type="submit" disabled={!valid || isLoading}
              className="w-full flex items-center justify-center gap-2 bg-primary-600 text-white font-semibold py-2.5 rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed mt-2"
            >
              {isLoading && <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />}
              {t('auth.sign_up_title')}
            </button>
          </form>
        </div>

        <p className="mt-4 text-center text-sm text-slate-500">
          <Link to="/login" className="text-primary-600 hover:text-primary-700 font-medium">
            {t('auth.already_have_account')}
          </Link>
        </p>
        <p className="mt-2 text-center">
          <Link to="/" className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600">
            <ArrowLeft className="w-3 h-3" /> Back to home
          </Link>
        </p>
      </div>
    </div>
  )
}
