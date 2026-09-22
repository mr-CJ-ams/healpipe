import { useEffect, useState } from 'react'
import { Activity, ChevronLeft, ChevronRight, LogOut, Menu, Moon, ShieldCheck, Sun, UserRound, X } from 'lucide-react'
import Dashboard from './components/Dashboard'
import BridgesManager from './components/BridgesManager'
import LoginPage from './components/LoginPage'
import OnboardingPage from './components/OnboardingPage'
import api, { SESSION_KEY } from './api'

const USER_KEY = 'healpipe_user'

export default function App() {
  const [activeView, setActiveView] = useState('telemetry')
  const [user, setUser] = useState(null)
  const [onboardingRequired, setOnboardingRequired] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
  const [signOutOpen, setSignOutOpen] = useState(false)
  const [theme, setTheme] = useState(() => window.localStorage.getItem('healpipe_theme') || 'dark')

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem('healpipe_theme', theme)
  }, [theme])

  useEffect(() => {
    const storedUser = window.localStorage.getItem(USER_KEY)
    if (window.localStorage.getItem(SESSION_KEY)) {
      setUser(storedUser ? JSON.parse(storedUser) : {})
    }
  }, [])

  const toggleTheme = () => setTheme((value) => value === 'light' ? 'dark' : 'light')

  if (!user) return <LoginPage theme={theme} onToggleTheme={toggleTheme} onAuthenticated={(result) => {
    window.localStorage.setItem(USER_KEY, JSON.stringify(result.user))
    setUser(result.user)
    setOnboardingRequired(result.onboarding_required)
  }} />
  if (onboardingRequired) return <OnboardingPage user={user} theme={theme} onToggleTheme={toggleTheme} onComplete={() => setOnboardingRequired(false)} />

  function logout() {
    window.localStorage.removeItem(SESSION_KEY)
    window.localStorage.removeItem(USER_KEY)
    api.defaults.headers.common.Authorization = undefined
    setSignOutOpen(false)
    setAccountOpen(false)
    setUser(null)
  }

  return (
    <div className="min-h-screen bg-[#091312]">
      <aside className={`app-sidebar ${sidebarCollapsed ? 'app-sidebar-collapsed' : ''}`}>
        <div className="app-sidebar-top">
          <button className="brand-mark" onClick={() => setActiveView('telemetry')} aria-label="Open dashboard">
            <span className="brand-icon"><ShieldCheck size={15} /></span>
            {!sidebarCollapsed && <><span>HealPipe</span><span className="brand-context">Operations</span></>}
          </button>
          <button className="sidebar-toggle" onClick={() => setSidebarCollapsed((value) => !value)} aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'} title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>
        <nav className="sidebar-nav" aria-label="Main navigation">
          <button onClick={() => setActiveView('telemetry')} className={`sidebar-link ${activeView === 'telemetry' ? 'sidebar-link-active' : ''}`} title="Dashboard"><Activity size={16} />{!sidebarCollapsed && <span>Dashboard</span>}</button>
          <button onClick={() => setActiveView('bridges')} className={`sidebar-link ${activeView === 'bridges' ? 'sidebar-link-active' : ''}`} title="Data bridges"><ShieldCheck size={16} />{!sidebarCollapsed && <span>Data bridges</span>}</button>
        </nav>
        {!sidebarCollapsed && <div className="sidebar-footer"><span className="sidebar-status-dot" />Workspace secure</div>}
      </aside>
      <div className={`app-content ${sidebarCollapsed ? 'app-content-collapsed' : ''}`}>
        <header className="app-topbar">
          <div className="flex items-center gap-3">
            <button className="mobile-menu-button" onClick={() => setSidebarCollapsed((value) => !value)} aria-label="Toggle navigation" title="Toggle navigation"><Menu size={18} /></button>
            <p className="topbar-label">{activeView === 'telemetry' ? 'Dashboard' : 'Data bridges'}</p>
          </div>
          <div className="relative">
            <button className="theme-button" onClick={toggleTheme} aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`} title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}>{theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}</button>
            <button className={`account-button ${accountOpen ? 'account-button-active' : ''}`} onClick={() => setAccountOpen((value) => !value)} aria-label="Open account menu" title="Account"><UserRound size={18} /></button>
            {accountOpen && <div className="account-menu"><p className="account-menu-label">Signed in as</p><p className="account-email">{user?.email || 'Email unavailable'}</p><button className="account-signout" onClick={() => setSignOutOpen(true)}><LogOut size={15} />Sign out</button></div>}
          </div>
        </header>
        {activeView === 'telemetry' ? <Dashboard onOpenBridges={() => setActiveView('bridges')} /> : <BridgesManager />}
      </div>
      {signOutOpen && <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setSignOutOpen(false)}><section className="signout-modal" role="dialog" aria-modal="true" aria-labelledby="signout-title"><button className="modal-close" onClick={() => setSignOutOpen(false)} aria-label="Close sign out confirmation"><X size={16} /></button><div className="modal-icon"><LogOut size={20} /></div><h2 id="signout-title">Are you sure you want to Sign out?</h2><p>Your current HealPipe session will be closed on this device.</p><div className="modal-actions"><button className="modal-button modal-button-secondary" onClick={() => setSignOutOpen(false)}>No</button><button className="modal-button modal-button-danger" onClick={logout}>Yes, sign out</button></div></section></div>}
    </div>
  )
}
