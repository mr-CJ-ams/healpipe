import { useEffect, useRef, useState } from 'react'
import { Chrome, ShieldCheck } from 'lucide-react'
import api, { SESSION_KEY } from '../api'

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID

export default function LoginPage({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const buttonRef = useRef(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
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

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#091312] px-5 py-12 text-slate-100">
      <section className="panel w-full max-w-md p-8 text-center sm:p-10">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-emerald-300/25 bg-emerald-300/10 text-emerald-300"><ShieldCheck size={28} /></div>
        <p className="eyebrow mt-7">HealPipe / Operations</p>
        <h1 className="mt-3 font-display text-3xl font-semibold text-white">Your data, in order.</h1>
        <p className="mt-3 text-sm leading-6 text-slate-400">Connect your workflows, repair payloads, and keep delivery evidence in one place.</p>
        <div className="mx-auto mt-7 flex max-w-xs gap-1 rounded-xl border border-white/10 bg-black/10 p-1">
          <button className={`nav-tab flex-1 justify-center ${mode === 'login' ? 'nav-tab-active' : ''}`} onClick={() => setMode('login')}>Login</button>
          <button className={`nav-tab flex-1 justify-center ${mode === 'signup' ? 'nav-tab-active' : ''}`} onClick={() => setMode('signup')}>Sign up</button>
        </div>
        <p className="mt-4 text-xs text-slate-500">{mode === 'signup' ? 'Create your private HealPipe workspace.' : 'Open your existing HealPipe workspace.'}</p>
        <div className="mt-8 flex min-h-11 justify-center" ref={buttonRef} />
        {loading && <p className="mt-4 text-xs text-emerald-200">Opening your workspace...</p>}
        {error && <p className="mt-5 rounded-lg border border-rose-300/20 bg-rose-400/10 p-3 text-left text-sm text-rose-200">{error}</p>}
        <div className="mt-8 flex items-center justify-center gap-2 text-[11px] text-slate-500"><Chrome size={13} />Google-only authentication</div>
      </section>
    </main>
  )
}