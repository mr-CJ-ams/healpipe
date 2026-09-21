import { useState } from 'react'
import { Activity, ShieldCheck } from 'lucide-react'
import Dashboard from './components/Dashboard'
import BridgesManager from './components/BridgesManager'

export default function App() {
  const [activeView, setActiveView] = useState('telemetry')

  return (
    <div className="min-h-screen bg-[#091312]">
      <nav className="app-nav">
        <div className="app-nav-inner">
          <button className="brand-mark" onClick={() => setActiveView('telemetry')} aria-label="Open dashboard"><span className="brand-icon"><ShieldCheck size={15} /></span><span>HealPipe</span><span className="brand-context">Operations</span></button>
          <div className="flex gap-1 rounded-xl border border-white/10 bg-black/10 p-1">
            <button onClick={() => setActiveView('telemetry')} className={`nav-tab ${activeView === 'telemetry' ? 'nav-tab-active' : ''}`}><Activity size={13} />Dashboard</button>
            <button onClick={() => setActiveView('bridges')} className={`nav-tab ${activeView === 'bridges' ? 'nav-tab-active' : ''}`}>Data bridges</button>
          </div>
        </div>
      </nav>
      {activeView === 'telemetry' ? <Dashboard /> : <BridgesManager />}
    </div>
  )
}
