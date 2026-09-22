import { useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowRight, CheckCircle2, Chrome, CircleAlert, Database, GitBranch, LoaderCircle, RotateCcw, Waypoints } from 'lucide-react'
import api, { SESSION_KEY } from '../api'

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID

export default function LoginPage({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [showAuth, setShowAuth] = useState(false)
  const buttonRef = useRef(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    document.documentElement.dataset.theme = showAuth ? 'dark' : 'light'
  }, [showAuth])

  useEffect(() => {
    setError('')
    setLoading(false)
    if (!GOOGLE_CLIENT_ID) {
      setError('Google login is not configured. Add VITE_GOOGLE_CLIENT_ID to the frontend environment.')
      return undefined
    }

    const handleCredential = async (response) => {
      setLoading(true)
      setError('')
      try {
        const result = await api.post('/auth/google', { credential: response.credential, mode })
        window.localStorage.setItem(SESSION_KEY, result.data.session_token)
        onAuthenticated(result.data)
      } catch (requestError) {
        setError(requestError.response?.data?.detail || 'Google sign-in failed. Please try again.')
      } finally {
        setLoading(false)
      }
    }

    const renderGoogleButton = () => {
      if (!window.google || !buttonRef.current) return
      window.google.accounts.id.initialize({ client_id: GOOGLE_CLIENT_ID, callback: handleCredential })
      buttonRef.current.innerHTML = ''
      window.google.accounts.id.renderButton(buttonRef.current, { theme: 'outline', size: 'large', text: mode === 'signup' ? 'signup_with' : 'signin_with', shape: 'rectangular', width: 320 })
    }

    if (window.google) renderGoogleButton()
    else {
      const script = document.createElement('script')
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.defer = true
      script.onload = renderGoogleButton
      document.head.appendChild(script)
      return () => script.remove()
    }
    return undefined
  }, [mode, onAuthenticated])

  function chooseMode(nextMode) {
    if (loading || nextMode === mode) return
    setMode(nextMode)
    setShowAuth(true)
  }

  function openAuth(nextMode) {
    setMode(nextMode)
    setShowAuth(true)
    window.requestAnimationFrame(() => document.getElementById('auth-panel')?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  }

  if (!showAuth) {
    return (
      <main className="landing-page text-slate-100">
        <nav className="landing-nav"><div className="landing-brand"><img className="landing-logo" src="/brand/logo-lightmode.png" alt="HealPipe" /><span className="landing-brand-sub">Webhook reliability infrastructure</span></div><div className="landing-nav-actions"><button className="landing-login-link" onClick={() => openAuth('login')}>Log in</button><button className="landing-nav-cta" onClick={() => openAuth('signup')}>Get started <ArrowRight size={15} /></button></div></nav>
        <section className="landing-hero"><div className="landing-hero-copy"><p className="landing-kicker">THE CONTROL PLANE FOR MESSY WEBHOOKS</p><h1>Keep every data handoff moving.</h1><p className="landing-hero-lede">HealPipe catches broken payloads, resolves schema drift, and gives your team a durable delivery trail before integrations become incidents.</p><div className="landing-hero-actions"><button className="landing-primary-cta" onClick={() => openAuth('signup')}>Start with Google <ArrowRight size={16} /></button><button className="landing-text-cta" onClick={() => document.getElementById('architecture')?.scrollIntoView({ behavior: 'smooth' })}>See how it works <ArrowDown size={16} /></button></div><div className="landing-proof-row"><span><CheckCircle2 size={15} /> Signed ingress</span><span><CheckCircle2 size={15} /> Durable retries</span><span><CheckCircle2 size={15} /> Audit-ready evidence</span></div></div><div className="landing-hero-visual"><div className="signal-grid" /><div className="hero-orbit hero-orbit-one" /><div className="hero-orbit hero-orbit-two" /><div className="hero-node hero-node-source"><span className="node-pulse" /><Database size={19} /><small>Source event</small></div><div className="hero-node hero-node-heal"><Waypoints size={21} /><small>HealPipe</small></div><div className="hero-node hero-node-destination"><CheckCircle2 size={19} /><small>Delivered</small></div><div className="hero-connection connection-one" /><div className="hero-connection connection-two" /><p className="hero-visual-label">LIVE EVENT PATH</p></div></section>
        <section className="landing-section landing-section-dark" id="architecture"><div className="landing-section-heading"><p className="landing-kicker">ONE RELIABLE PATH</p><h2>From source chaos to trusted delivery.</h2><p>Every event moves through an observable control plane that preserves what arrived, what changed, and what finally left.</p></div><div className="architecture-flow"><div className="architecture-step"><span className="architecture-number">01</span><Database size={22} /><h3>Receive</h3><p>Verify the sender and preserve the exact inbound payload.</p></div><div className="architecture-line" /><div className="architecture-step architecture-step-highlight"><span className="architecture-number">02</span><Waypoints size={22} /><h3>Normalize</h3><p>Map drift, hold uncertainty, and heal safe variations.</p></div><div className="architecture-line" /><div className="architecture-step"><span className="architecture-number">03</span><CheckCircle2 size={22} /><h3>Deliver</h3><p>Retry safely and leave a complete evidence trail.</p></div></div></section>
        <section className="landing-section landing-problem-section"><div className="landing-section-heading"><p className="landing-kicker">THE COST OF FRAGILE HANDOFFS</p><h2>Integrations fail quietly, then expensively.</h2></div><div className="pain-grid"><article><CircleAlert size={20} /><span>01</span><h3>Schema drift</h3><p>A harmless source-side rename becomes a broken CRM or inventory record.</p></article><article><RotateCcw size={20} /><span>02</span><h3>Retry blind spots</h3><p>Teams cannot tell whether a delivery failed, duplicated, or disappeared.</p></article><article><GitBranch size={20} /><span>03</span><h3>Unowned exceptions</h3><p>Ambiguous fields land in inboxes instead of a controlled review queue.</p></article></div></section>
        <section className="landing-section landing-solution-section"><div className="landing-solution-panel"><div><p className="landing-kicker">THE HEALPIPE APPROACH</p><h2>Reliability becomes a system, not a rescue mission.</h2><p>Give every bridge its own signed ingress, mapping history, retry policy, and operational view. Your team sees the decision behind every delivery.</p><button className="landing-primary-cta" onClick={() => openAuth('signup')}>Create your workspace <ArrowRight size={16} /></button></div><div className="solution-list"><div><span>01</span><strong>Detect</strong><p>Find missing, malformed, or unfamiliar fields.</p></div><div><span>02</span><strong>Decide</strong><p>Apply approved mappings or safely hold for review.</p></div><div><span>03</span><strong>Prove</strong><p>Trace the payload from inbound to outbound.</p></div></div></div></section>
        <footer className="landing-footer"><span>HealPipe</span><span>Webhook reliability infrastructure for modern operations</span><button onClick={() => openAuth('login')}>Open workspace <ArrowRight size={14} /></button></footer>
      </main>
    )
  }

  return (
    <main className="auth-page flex min-h-screen items-center justify-center bg-[#091312] px-5 py-12 text-slate-100">
      <section className="panel auth-card w-full max-w-md p-8 text-center sm:p-10" id="auth-panel">
        <img className="auth-logo" src="/brand/logo-darkmode.png" alt="HealPipe" />
        <div className="auth-header-row"><button className="auth-back-link" onClick={() => setShowAuth(false)}><ArrowDown size={14} className="rotate-90" />Back to overview</button></div>
        <p className="eyebrow mt-7">HealPipe / Operations</p>
        <h1 className="mt-3 font-display text-3xl font-semibold text-white">Your data, in order.</h1>
        <p className="mt-3 text-sm leading-6 text-slate-400">Connect your workflows, repair payloads, and keep delivery evidence in one place.</p>
        <div className="auth-mode-switch mx-auto mt-7 flex max-w-xs gap-1 rounded-xl border border-white/10 bg-black/10 p-1" role="tablist" aria-label="Authentication mode">
          <button role="tab" aria-selected={mode === 'login'} className={`auth-mode-tab ${mode === 'login' ? 'auth-mode-tab-active' : ''}`} onClick={() => chooseMode('login')}>Login</button>
          <button role="tab" aria-selected={mode === 'signup'} className={`auth-mode-tab ${mode === 'signup' ? 'auth-mode-tab-active' : ''}`} onClick={() => chooseMode('signup')}>Sign up</button>
        </div>
        <div className="auth-intent mt-5"><span className="auth-intent-dot" />{mode === 'signup' ? 'New workspace setup' : 'Existing workspace login'}<ArrowRight size={13} /></div>
        <p className="mt-2 text-xs text-slate-500">{mode === 'signup' ? 'Create your private HealPipe workspace.' : 'Open your existing HealPipe workspace.'}</p>
        <div className={`google-action mt-7 ${loading ? 'google-action-loading' : ''}`}>
          <div className="google-action-label">{mode === 'signup' ? 'Continue to create your workspace' : 'Continue to your workspace'}</div>
          <div className="flex min-h-11 justify-center" ref={buttonRef} />
          {loading && <div className="google-loading"><LoaderCircle size={18} className="animate-spin" /><span>Checking your Google account...</span></div>}
        </div>
        {error && <div className="auth-error mt-5" role="alert"><p>{error}</p>{error.includes('already exists') && <button onClick={() => chooseMode('login')}>Switch to Login</button>}{error.includes('No HealPipe account') && <button onClick={() => chooseMode('signup')}>Switch to Sign up</button>}</div>}
        <div className="mt-8 flex items-center justify-center gap-2 text-[11px] text-slate-500"><Chrome size={13} />Google-only authentication</div>
      </section>
    </main>
  )
}