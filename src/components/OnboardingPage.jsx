import { useState } from 'react'
import { ArrowRight, CheckCircle2, ShieldCheck } from 'lucide-react'
import api from '../api'

const questions = [
  ['user_type', 'What best describes you?', ['Ecommerce business', 'SaaS company', 'Agency or consultant', 'Operations or IT team', 'Developer', 'Other']],
  ['integration_type', 'What are you trying to connect?', ['Shopify', 'WooCommerce', 'CRM', 'Inventory system', 'Custom API', 'Other']],
  ['primary_problem', 'What problem brought you to HealPipe?', ['Failed webhooks', 'Inconsistent payload formats', 'Duplicate events', 'Missing data', 'Retry and delivery visibility', 'Other']],
  ['monthly_volume', 'How many webhook events do you expect?', ['Less than 1,000 per month', '1,000 to 10,000', '10,000 to 100,000', 'More than 100,000', "I’m not sure"]],
  ['user_role', 'What is your role?', ['Founder or owner', 'Developer', 'Operations', 'IT or security', 'Agency', 'Other']],
]

export default function OnboardingPage({ user, onComplete }) {
  const [answers, setAnswers] = useState({})
  const [step, setStep] = useState(0)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [field, prompt, options] = questions[step]
  const selected = answers[field]

  async function next() {
    if (!selected) return
    if (step < questions.length - 1) {
      setStep((value) => value + 1)
      return
    }
    setSaving(true)
    setError('')
    try {
      await api.post('/auth/onboarding', answers)
      onComplete()
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Unable to save your onboarding answers.')
    } finally {
      setSaving(false)
    }
  }

  return <main className="flex min-h-screen items-center justify-center bg-[#091312] px-5 py-12 text-slate-100"><section className="panel w-full max-w-2xl p-7 sm:p-10"><div className="flex items-center justify-between gap-4"><div className="flex items-center gap-3"><span className="brand-icon"><ShieldCheck size={17} /></span><div><p className="eyebrow">Workspace setup</p><p className="mt-1 text-xs text-slate-500">{user?.name || user?.email}</p></div></div><span className="font-mono text-xs text-emerald-300">{step + 1} / {questions.length}</span></div><div className="mt-8 h-1 rounded-full bg-white/10"><div className="h-1 rounded-full bg-emerald-300 transition-all" style={{ width: `${((step + 1) / questions.length) * 100}%` }} /></div><p className="eyebrow mt-10">Tell us what you need</p><h1 className="mt-3 max-w-xl font-display text-3xl font-semibold text-white">{prompt}</h1><p className="mt-3 text-sm text-slate-400">This helps us tailor HealPipe and understand which workflows matter most.</p><div className="mt-8 grid gap-3 sm:grid-cols-2">{options.map((option) => <button key={option} className={`rounded-xl border px-4 py-4 text-left text-sm transition ${selected === option ? 'border-emerald-300/60 bg-emerald-300/15 text-emerald-100' : 'border-white/10 bg-white/3 text-slate-300 hover:border-emerald-300/30 hover:bg-white/6'}`} onClick={() => setAnswers((current) => ({ ...current, [field]: option }))}>{selected === option && <CheckCircle2 size={16} className="mb-2 text-emerald-300" />}{option}</button>)}</div>{error && <p className="mt-5 rounded-lg border border-rose-300/20 bg-rose-400/10 p-3 text-sm text-rose-200">{error}</p>}<div className="mt-8 flex justify-end"><button className="inline-flex items-center gap-2 rounded-lg border border-emerald-300/35 bg-emerald-300/10 px-5 py-3 text-sm font-bold text-emerald-200 disabled:opacity-40" disabled={!selected || saving} onClick={next}>{saving ? 'Saving...' : step === questions.length - 1 ? 'Finish setup' : 'Continue'}<ArrowRight size={16} /></button></div></section></main>
}