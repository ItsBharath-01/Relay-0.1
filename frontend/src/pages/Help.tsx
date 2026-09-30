import React from 'react'
import { HelpCircle, Zap, Shield, RefreshCw, CheckCircle, Globe, Cpu } from 'lucide-react'
import { AppShell } from '../components/layout/AppShell'

interface FlowStep { icon: React.FC<{ className?: string }>; title: string; desc: string }

const FLOW: FlowStep[] = [
  { icon: Zap, title: 'Goal Understanding', desc: 'You describe what you want. Relay uses qwen3:4b (local Ollama) to analyze your goal and identify required capabilities.' },
  { icon: CheckCircle, title: 'Plan Generation', desc: 'Relay decomposes the goal into an ordered task graph with risk classification and tool selection for each step.' },
  { icon: Globe, title: 'Real Tool Execution', desc: 'Relay calls real tools (web search, browser, calendar, email) and observes real results. No scripted demos.' },
  { icon: Shield, title: 'Independent Verification', desc: 'After each task, Relay re-reads system state to confirm the intended outcome actually happened.' },
  { icon: RefreshCw, title: 'Automatic Recovery', desc: 'If a tool fails, Relay tries alternatives and re-plans rather than stopping silently.' },
  { icon: Shield, title: 'Human Approval Gates', desc: 'High-risk actions (sending emails, deleting data, payments) pause and require your explicit approval before proceeding.' },
]

const FAQ = [
  { q: 'Why does goal analysis take so long?', a: 'Relay uses qwen3:4b running locally on your CPU via Ollama. CPU inference takes 90–150 seconds. On a GPU or with a faster model, it completes in seconds.' },
  { q: 'Is my data sent to any cloud AI provider?', a: 'No. Relay is Ollama-first. All LLM inference runs locally. If you configure a hosted provider (Gemini, Anthropic), data would be sent there — but that is entirely optional and disabled by default.' },
  { q: 'What happens if a tool fails?', a: 'Relay detects real tool errors, records them honestly, attempts recovery with alternative tools, and re-plans if necessary. Failures are never hidden.' },
  { q: 'How do I connect Google Calendar or Gmail?', a: 'Go to Connections, click the app, and provide your OAuth token. Relay encrypts credentials at rest. OAuth callback setup requires configuring GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env.' },
  { q: 'What is the payload hash shown in approval requests?', a: "It's a SHA-256 hash of the exact action payload. The server verifies this hash before executing the approved action to prevent tampering." },
]

export default function Help() {
  const [openIdx, setOpenIdx] = React.useState<number | null>(null)

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="flex items-center gap-2 mb-6">
          <HelpCircle className="w-5 h-5 text-primary-600" />
          <h1 className="text-xl font-bold text-slate-900">Help</h1>
        </div>

        {/* How Relay works */}
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-4">How Relay works</h2>
          <div className="space-y-3">
            {FLOW.map(({ title, desc }, i) => (
              <div key={title} className="flex gap-4 bg-white border border-slate-200 rounded-xl p-4">
                <div className="w-8 h-8 rounded-full bg-primary-50 flex items-center justify-center shrink-0 mt-0.5">
                  <span className="text-xs font-bold text-primary-600">{i + 1}</span>
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-900 mb-0.5">{title}</h3>
                  <p className="text-xs text-slate-500 leading-relaxed">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* LLM requirement */}
        <div className="mb-8 p-4 bg-amber-50 border border-amber-200 rounded-xl">
          <div className="flex items-center gap-2 mb-2">
            <Cpu className="w-4 h-4 text-amber-600" />
            <p className="text-sm font-semibold text-amber-900">Requires Ollama + qwen3:4b</p>
          </div>
          <p className="text-xs text-amber-800">
            Relay requires <code className="font-mono">ollama run qwen3:4b</code> running at <code className="font-mono">http://localhost:11434</code>.
            If unavailable, goal analysis will be disabled and the LLM status indicator will show the exact error.
          </p>
        </div>

        {/* FAQ */}
        <div>
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-4">FAQ</h2>
          <div className="space-y-2">
            {FAQ.map(({ q, a }, i) => (
              <div key={i} className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                <button
                  className="w-full text-left px-4 py-3 text-sm font-medium text-slate-800 hover:bg-slate-50 transition-colors flex items-center justify-between gap-2"
                  onClick={() => setOpenIdx(openIdx === i ? null : i)}
                >
                  {q}
                  <span className="text-slate-400 shrink-0">{openIdx === i ? '−' : '+'}</span>
                </button>
                {openIdx === i && (
                  <div className="px-4 pb-4 text-xs text-slate-600 leading-relaxed border-t border-slate-100 pt-3">
                    {a}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  )
}
