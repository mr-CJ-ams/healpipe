import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  Clock3,
  Copy,
  Database,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  X,
  XCircle,
} from 'lucide-react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const FILTERS = ['all', 'validated', 'healed', 'rejected', 'uncertain', 'delivery_failed', 'dropped', 'idempotency_blocked']

const statusMeta = {
  validated: {
    label: 'Validated',
    icon: CheckCircle2,
    badge: 'border-emerald-300/20 bg-emerald-400/10 text-emerald-300',
    iconColor: 'text-emerald-300',
  },
  healed: {
    label: 'Healed',
    icon: Sparkles,
    badge: 'border-amber-300/20 bg-amber-400/10 text-amber-300',
    iconColor: 'text-amber-300',
  },
  rejected: {
    label: 'Rejected',
    icon: XCircle,
    badge: 'border-rose-300/20 bg-rose-400/10 text-rose-300',
    iconColor: 'text-rose-300',
  },
  uncertain: {
    label: 'Uncertain',
    icon: AlertTriangle,
    badge: 'border-purple-300/20 bg-purple-400/10 text-purple-300',
    iconColor: 'text-purple-300',
  },
  delivery_failed: {
    label: 'Delivery failed',
    icon: AlertTriangle,
    badge: 'border-orange-300/20 bg-orange-400/10 text-orange-300',
    iconColor: 'text-orange-300',
  },
  dropped: {
    label: 'Dropped',
    icon: XCircle,
    badge: 'border-slate-300/20 bg-slate-400/10 text-slate-300',
    iconColor: 'text-slate-300',
  },
  idempotency_blocked: {
    label: 'Duplicate blocked',
    icon: XCircle,
    badge: 'border-slate-300/20 bg-slate-400/10 text-slate-300',
    iconColor: 'text-slate-300',
  },
}

function formatDate(value) {
  if (!value) return 'Unknown time'
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function getBusinessDescription(event) {
  if (event.status === 'validated') {
    return 'System Health Optimal: Transaction data matched perfectly and was safely delivered.'
  }
  if (event.status === 'healed') {
    return 'Auto-Healed: Automatically corrected format variations from your app update on the fly to prevent an integration crash.'
  }
  if (event.status === 'rejected') {
    return 'Order Safety Block: Blocked an invalid data stream missing critical customer identity attributes to safeguard your store database.'
  }
  if (event.status === 'uncertain' && event.reason?.startsWith('AI triage failed:')) {
    return 'AI Safety Hold: Our AI detected a highly ambiguous format. Parked securely for your quick manual confirmation to guarantee 100% inventory accuracy.'
  }
  return "Review Required: Detected an unrecognized data field. Please manually link it using the 'Map Field' button on the right."
}

function getInlineStatusLabel(status) {
  return {
    validated: '🟢 System Health Optimal',
    healed: '🟡 Schema Auto-Healed',
    rejected: '🔴 Order Safety Blocked',
    uncertain: '🟣 Human Review Required',
    delivery_failed: '🟠 Delivery Failed',
    dropped: '⚪ Archived by Operator',
    idempotency_blocked: '⚪ Duplicate Suppressed',
  }[status] || '🟣 Human Review Required'
}

function formatPreciseDate(value) {
  if (!value) return 'Unknown timestamp'
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
  }).format(new Date(value))
}

function getBridgeOriginTag(event, bridges) {
  const bridge = bridges.find((item) => item.bridge_id === event.bridge_id)
  if (!bridge) return 'Unscoped / Legacy'
  return bridge.bridge_name || `${bridge.source_platform} Bridge`
}

function getBridgeName(event, bridges) {
  return bridges.find((item) => item.bridge_id === event.bridge_id)?.bridge_name || null
}

function getUncertainField(event) {
  const expectedKeys = new Set(['customer_id', 'email_address', 'stock_count'])
  const payload = event.raw_payload || event.healed_payload || {}
  const entry = Object.entries(payload).find(([key]) => !expectedKeys.has(key))
  return entry || ['unknown_field', 'Unavailable']
}

function StatusBadge({ status }) {
  const meta = statusMeta[status] || statusMeta.uncertain
  const Icon = meta.icon
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${meta.badge}`}>
      <Icon size={13} />
      {meta.label}
    </span>
  )
}

function StatCard({ label, value, note, icon: Icon, accent }) {
  return (
    <article className="panel relative overflow-hidden p-5">
      <div className={`absolute right-4 top-4 rounded-xl border border-white/10 bg-white/4 p-2 ${accent}`}>
        <Icon size={18} />
      </div>
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</p>
      <p className="mt-5 font-display text-4xl font-semibold tracking-tight text-white">{value}</p>
      <p className="mt-2 text-sm text-slate-500">{note}</p>
    </article>
  )
}

function Modal({ title, eyebrow, onClose, children, wide = false }) {
  useEffect(() => {
    const handleKeyDown = (event) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-[#020807]/80 p-4 backdrop-blur-md" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className={`panel my-auto w-full ${wide ? 'max-w-5xl' : 'max-w-xl'} border-white/15 bg-[#10221e] shadow-2xl`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="flex items-start justify-between border-b border-white/10 p-5 sm:p-6">
          <div><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-300">{eyebrow}</p><h2 className="mt-2 font-display text-xl font-semibold text-white">{title}</h2></div>
          <button className="icon-button" onClick={onClose} aria-label="Close dialog" title="Close dialog"><X size={17} /></button>
        </div>
        {children}
      </section>
    </div>
  )
}

function payloadDiff(before, after, prefix = '') {
  const keys = new Set([...Object.keys(before || {}), ...Object.keys(after || {})])
  return [...keys].flatMap((key) => {
    const path = prefix ? `${prefix}.${key}` : key
    const beforeValue = before?.[key]
    const afterValue = after?.[key]
    if (JSON.stringify(beforeValue) === JSON.stringify(afterValue)) return []
    if (beforeValue && afterValue && typeof beforeValue === 'object' && typeof afterValue === 'object' && !Array.isArray(beforeValue) && !Array.isArray(afterValue)) {
      return payloadDiff(beforeValue, afterValue, path)
    }
    return [{ path, before: beforeValue, after: afterValue }]
  })
}

function PayloadInspector({ event, bridges, onClose }) {
  const [copied, setCopied] = useState('')
  const [replayingJobId, setReplayingJobId] = useState('')
  const [replayMessage, setReplayMessage] = useState('')
  const [audit, setAudit] = useState(null)
  const [auditError, setAuditError] = useState('')
  const bridgeName = getBridgeName(event, bridges) || 'your active bridge'

  useEffect(() => {
    let active = true
    async function loadAudit() {
      if (!event.bridge_id) return
      try {
        const response = await axios.get(`${API_BASE_URL}/v1/webhooks/events/${event.event_id}/audit`, { params: { bridge_id: event.bridge_id } })
        if (active) setAudit(response.data)
      } catch (requestError) {
        if (active) setAuditError(requestError.response?.data?.detail || 'Unable to load the complete audit record.')
      }
    }
    loadAudit()
    return () => { active = false }
  }, [event.event_id, event.bridge_id])

  const copyPayload = async (label, payload) => {
    await navigator.clipboard?.writeText(JSON.stringify(payload || {}, null, 2))
    setCopied(label)
    window.setTimeout(() => setCopied(''), 1600)
  }

  const source = audit || event
  const latestJob = audit?.delivery_jobs?.[audit.delivery_jobs.length - 1]
  const outboundPayload = latestJob?.payload || source.healed_payload
  const stages = [
    ['Inbound', source.raw_payload, 'border-rose-300/20 bg-rose-400/[0.05] text-rose-100', 'raw'],
    ['Normalized', source.normalized_payload || source.raw_payload, 'border-sky-300/20 bg-sky-400/[0.05] text-sky-100', 'normalized'],
    ['Healed / mapped', source.healed_payload, 'border-amber-300/20 bg-amber-400/[0.05] text-amber-100', 'healed'],
    ['Outbound', outboundPayload, 'border-emerald-300/20 bg-emerald-400/[0.05] text-emerald-100', 'outbound'],
  ]
  const changes = payloadDiff(source.raw_payload, outboundPayload)

  async function replayJob(jobId) {
    setReplayingJobId(jobId)
    setReplayMessage('')
    try {
      await axios.post(`${API_BASE_URL}/v1/delivery-jobs/${jobId}/replay`)
      setReplayMessage('Replay queued. Refresh the audit record to see the new delivery attempts.')
    } catch (requestError) {
      setReplayMessage(requestError.response?.data?.detail || 'Unable to queue replay.')
    } finally {
      setReplayingJobId('')
    }
  }

  return (
    <Modal title="Payload inspector" eyebrow={`${event.status} event / ${event.event_id}`} onClose={onClose} wide>
      <div className="space-y-5 p-5 sm:p-6">
        <div className="grid gap-4 rounded-xl border border-white/10 bg-black/10 p-4 text-sm sm:grid-cols-3">
          <div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">Event UUID</p><p className="mt-2 break-all font-mono text-xs text-slate-200">{event.event_id}</p></div>
          <div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">Created</p><p className="mt-2 text-xs text-slate-200">{formatPreciseDate(event.created_at)}</p></div>
          <div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">Bridge Name</p><p className="mt-2 text-xs font-semibold text-emerald-200">{getBridgeName(event, bridges) || 'Unscoped / Legacy'}</p></div>
          {event.ai_telemetry && <div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">AI Confidence</p><p className="mt-2 text-xs text-slate-200">{Number(event.ai_telemetry.confidence_score).toFixed(2)} <span className="text-slate-500">/ {event.ai_telemetry.algorithm}</span></p></div>}
        </div>
        {auditError && <div className="rounded-xl border border-rose-300/20 bg-rose-400/10 p-3 text-sm text-rose-200">{auditError}</div>}
        <div className="rounded-xl border border-white/10 bg-black/10 p-4"><StatusBadge status={event.status} /><p className="mt-3 text-sm leading-6 text-slate-300">{getBusinessDescription(event)}</p></div>
        {source.validation_errors?.length > 0 && <div className="rounded-xl border border-rose-300/20 bg-rose-400/5 p-4"><p className="text-xs font-bold uppercase tracking-[0.16em] text-rose-200">Validation findings</p><ul className="mt-3 space-y-2 text-sm text-slate-300">{source.validation_errors.map((finding, index) => <li key={`${finding.field}-${index}`}><span className="font-mono text-rose-100">{finding.field}</span> {finding.message}</li>)}</ul></div>}
        {event.status === 'rejected' && <div className="rounded-xl border border-amber-300/20 bg-amber-400/5 p-4 text-sm text-slate-300"><h3 className="font-display text-base font-semibold text-amber-200">🔧 Recommended Action Steps</h3><ol className="mt-3 space-y-2 leading-6"><li>1. Log into your source platform admin panel for: <span className="font-semibold text-white">{bridgeName}</span>.</li><li>2. Navigate to your checkout or webhook logs matching the exact timestamp: <span className="font-semibold text-white">{formatPreciseDate(event.created_at)}</span>.</li><li>3. Verify that your frontend customer forms are strictly requiring <span className="font-mono text-amber-100">'Email Address'</span> or <span className="font-mono text-amber-100">'Customer ID'</span> input parameters before allowing a payload payload submission to prevent blank records.</li></ol></div>}
        <div className="grid gap-4 sm:grid-cols-2">
        {stages.map(([label, payload, tone, key]) => (
          <div key={key} className={`overflow-hidden rounded-xl border ${tone}`}>
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3"><p className="text-xs font-bold uppercase tracking-[0.16em]">{label}</p><button className="icon-button h-8 w-8" onClick={() => copyPayload(key, payload)} aria-label={`Copy ${label}`} title={`Copy ${label}`}><Copy size={14} /></button></div>
            <pre className="max-h-105 overflow-auto p-4 font-mono text-xs leading-6"><code>{JSON.stringify(payload || {}, null, 2)}</code></pre>
          </div>
        ))}
        </div>
        <div className="rounded-xl border border-white/10 bg-black/10 p-4"><div className="flex items-center justify-between"><p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-300">Inbound to outbound diff</p><span className="text-xs text-slate-500">{changes.length} changed path(s)</span></div>{changes.length > 0 ? <div className="mt-3 divide-y divide-white/5">{changes.map((change) => <div key={change.path} className="grid gap-2 py-3 text-xs sm:grid-cols-[minmax(120px,.6fr)_1fr_1fr]"><span className="font-mono text-slate-300">{change.path}</span><code className="break-all text-rose-200">{JSON.stringify(change.before)}</code><code className="break-all text-emerald-200">{JSON.stringify(change.after)}</code></div>)}</div> : <p className="mt-3 text-sm text-slate-500">No payload changes recorded.</p>}</div>
        {audit?.delivery_jobs?.length > 0 && <div className="rounded-xl border border-white/10 bg-black/10 p-4"><p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-300">Delivery ledger</p>{replayMessage && <p className="mt-2 text-xs text-amber-200">{replayMessage}</p>}<div className="mt-3 space-y-3">{audit.delivery_jobs.map((job) => <div key={job.job_id} className="rounded-lg border border-white/8 bg-white/2 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-mono text-xs text-slate-400">{job.job_id}</span><div className="flex items-center gap-2"><StatusBadge status={job.status === 'dead_lettered' ? 'delivery_failed' : job.status} />{['dead_lettered', 'delivery_failed'].includes(job.status) && <button className="icon-button h-7 w-7" onClick={() => replayJob(job.job_id)} disabled={replayingJobId === job.job_id} aria-label="Replay delivery job" title="Replay delivery job"><RotateCcw size={13} className={replayingJobId === job.job_id ? 'animate-spin' : ''} /></button>}</div></div>{job.attempts?.map((attempt) => <div key={attempt.attempt_id} className="mt-2 text-xs text-slate-400"><p>Attempt {attempt.attempt_number}: <span className="text-slate-200">{attempt.status}</span>{attempt.http_status ? ` · HTTP ${attempt.http_status}` : ''}{attempt.error_message ? ` · ${attempt.error_message}` : ''}</p>{attempt.response_body && <pre className="mt-1 max-h-20 overflow-auto whitespace-pre-wrap text-slate-500">{attempt.response_body}</pre>}</div>)}</div>)}</div></div>}
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-white/10 px-5 py-4 text-xs text-slate-400 sm:px-6">
        {event.key_mappings && Object.keys(event.key_mappings).length > 0 && <span>{Object.keys(event.key_mappings).length} field mapping(s)</span>}
        {audit ? <span>Audit record loaded</span> : <span>Loading audit record...</span>}
        {copied && <span className="ml-auto inline-flex items-center gap-1 text-emerald-300"><Check size={13} />Copied</span>}
      </div>
    </Modal>
  )
}

function NewBridgeModal({ onClose }) {
  const [source, setSource] = useState('Shopify')
  const [target, setTarget] = useState('https://api.gohighlevel.com/webhooks/healpipe')
  const [savedBridge, setSavedBridge] = useState(null)
  const [saving, setSaving] = useState(false)
  const [bridgeError, setBridgeError] = useState('')
  const [copied, setCopied] = useState(false)

  async function saveBridge() {
    setSaving(true)
    setBridgeError('')
    try {
      const response = await axios.post(`${API_BASE_URL}/v1/bridges`, {
        source_platform: source,
        target_endpoint_url: target,
      })
      setSavedBridge(response.data)
    } catch (requestError) {
      setBridgeError(requestError.response?.data?.detail || 'Unable to save this data bridge.')
    } finally {
      setSaving(false)
    }
  }

  async function copyIngestionUrl() {
    await navigator.clipboard?.writeText(savedBridge.ingestion_url)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  return (
    <Modal title="Create a data bridge" eyebrow="New connection" onClose={onClose}>
      <div className="space-y-6 p-5 sm:p-6">
        {savedBridge ? (
          <div className="space-y-5">
            <div className="rounded-xl border border-emerald-300/20 bg-emerald-400/6 p-4"><div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.16em] text-emerald-300"><Check size={14} />Bridge saved</div><p className="mt-2 text-sm text-slate-300">{savedBridge.source_platform} is now connected to the configured destination.</p></div>
            <div className="rounded-xl border border-white/10 bg-black/10 p-4"><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">Your ingestion URL</p><p className="mt-3 break-all font-mono text-xs leading-6 text-emerald-100">{savedBridge.ingestion_url}</p><button className="mt-4 inline-flex items-center gap-2 rounded-lg border border-emerald-300/25 px-3 py-2 text-xs font-bold text-emerald-200 hover:bg-emerald-400/10" onClick={copyIngestionUrl}><Copy size={14} />{copied ? 'Copied to clipboard' : 'Copy to clipboard'}</button></div>
          </div>
        ) : <>
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-300 text-[#092019]">1</span>Choose your source <ArrowRight size={14} /><span className="flex h-6 w-6 items-center justify-center rounded-full border border-white/10">2</span>Choose destination</div>
        <label className="block"><span className="mb-2 block text-sm font-medium text-slate-300">Source application</span><select value={source} onChange={(event) => setSource(event.target.value)} className="field"><option>Shopify</option><option>WooCommerce</option><option>Supplier warehouse</option><option>Custom webhook</option></select></label>
        <label className="block"><span className="mb-2 block text-sm font-medium text-slate-300">Target destination</span><select value={target} onChange={(event) => setTarget(event.target.value)} className="field"><option value="https://api.gohighlevel.com/webhooks/healpipe">GoHighLevel CRM</option><option value="https://api.shopify.com/webhooks/healpipe">Shopify</option><option value="https://inventory.example.com/webhooks/healpipe">Inventory system</option><option value="https://api.example.com/webhooks/healpipe">Custom API</option></select></label>
        {bridgeError && <p className="rounded-lg border border-rose-300/20 bg-rose-400/10 p-3 text-sm text-rose-200">{bridgeError}</p>}
        <button className="w-full rounded-xl bg-emerald-300 px-4 py-3 text-sm font-bold text-[#092019] transition hover:bg-emerald-200 disabled:cursor-wait disabled:opacity-60" onClick={saveBridge} disabled={saving}>{saving ? 'Saving bridge...' : 'Save bridge'}</button>
        </>}
      </div>
    </Modal>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState({ validated: 0, healed: 0, rejected: 0, uncertain: 0, delivery_failed: 0, dropped: 0, idempotency_blocked: 0 })
  const [events, setEvents] = useState([])
  const [bridges, setBridges] = useState([])
  const [selectedBridgeId, setSelectedBridgeId] = useState('')
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lastUpdated, setLastUpdated] = useState(null)
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [triageEventId, setTriageEventId] = useState(null)
  const [triageField, setTriageField] = useState('customer_id')
  const [triageMessage, setTriageMessage] = useState('')

  async function loadDashboard() {
    setLoading(true)
    setError('')
    try {
      const bridgesResponse = await axios.get(`${API_BASE_URL}/v1/bridges?include_inactive=false`)
      setBridges(bridgesResponse.data)
      if (!selectedBridgeId) {
        setStats({ validated: 0, healed: 0, rejected: 0, uncertain: 0, delivery_failed: 0, dropped: 0, idempotency_blocked: 0 })
        setEvents([])
        setLastUpdated(new Date())
        return
      }
      const params = { bridge_id: selectedBridgeId }
      const [statsResponse, eventsResponse] = await Promise.all([
        axios.get(`${API_BASE_URL}/v1/webhooks/stats`, { params }),
        axios.get(`${API_BASE_URL}/v1/webhooks/events`, { params: { ...params, limit: 100 } }),
      ])
      setStats({ validated: 0, healed: 0, rejected: 0, uncertain: 0, delivery_failed: 0, dropped: 0, idempotency_blocked: 0, ...statsResponse.data })
      setEvents(eventsResponse.data)
      setLastUpdated(new Date())
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Backend unavailable. Start FastAPI on port 8000.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDashboard()
    const interval = window.setInterval(loadDashboard, 15000)
    return () => window.clearInterval(interval)
  }, [selectedBridgeId])

  const filteredEvents = useMemo(
    () => filter === 'all' ? events : events.filter((event) => event.status === filter),
    [events, filter],
  )
  const activeBridges = bridges.filter((bridge) => bridge.is_active)
  const total = Object.values(stats).reduce((sum, count) => sum + count, 0)

  async function handleMapField(eventId) {
    try {
      await axios.post(`${API_BASE_URL}/v1/webhooks/resolve-triage`, {
        event_id: eventId,
        target_key: triageField,
        action: 'map',
      })
      setTriageMessage(`Mapping saved for ${eventId.slice(0, 12)}... → ${triageField}`)
      setTriageEventId(null)
      await loadDashboard()
    } catch (requestError) {
      setTriageMessage(requestError.response?.data?.detail || 'Unable to save this mapping.')
    }
  }

  async function handleDrop(eventId) {
    try {
      await axios.post(`${API_BASE_URL}/v1/webhooks/resolve-triage`, {
        event_id: eventId,
        action: 'drop',
      })
      setTriageMessage(`Event ${eventId.slice(0, 12)}... was archived from triage.`)
      await loadDashboard()
    } catch (requestError) {
      setTriageMessage(requestError.response?.data?.detail || 'Unable to archive this event.')
    }
  }

  return (
    <main className="min-h-screen bg-[#091312] text-slate-100">
      <div className="page-wrap">
        <header className="page-heading">
          <div>
            <div className="eyebrow">HealPipe / Control room</div>
            <h1 className="page-title">Pipeline telemetry</h1>
            <p className="page-subtitle">Monitor every payload that passed through the self-healing gateway for one data bridge at a time.</p>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-500">
            <span className="flex items-center gap-2"><span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />Live</span>
            {lastUpdated && <span className="hidden text-slate-600 sm:inline">Updated {formatDate(lastUpdated)}</span>}
            <button className="icon-button" onClick={loadDashboard} aria-label="Refresh dashboard" title="Refresh dashboard">
              <RefreshCw size={17} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </header>

        <section className="grid gap-3 py-6 sm:grid-cols-2 xl:grid-cols-7">
          <StatCard label="Validated" value={stats.validated} note="Clean on first pass" icon={CheckCircle2} accent="text-emerald-300" />
          <StatCard label="Healed" value={stats.healed} note="Recovered automatically" icon={Sparkles} accent="text-amber-300" />
          <StatCard label="Rejected" value={stats.rejected} note="Missing core fields" icon={XCircle} accent="text-rose-300" />
          <StatCard label="Uncertain" value={stats.uncertain} note="Waiting for triage" icon={AlertTriangle} accent="text-purple-300" />
          <StatCard label="Delivery failed" value={stats.delivery_failed} note="Destination errors" icon={AlertTriangle} accent="text-orange-300" />
          <StatCard label="Dropped" value={stats.dropped} note="Archived by operator" icon={XCircle} accent="text-slate-300" />
          <StatCard label="Duplicate blocked" value={stats.idempotency_blocked} note="Idempotency protection" icon={XCircle} accent="text-slate-300" />
        </section>

        <section className="panel overflow-hidden">
          {!selectedBridgeId && <div className="mx-5 mt-5 rounded-xl border border-amber-300/20 bg-amber-400/10 p-4 text-sm text-amber-100 sm:mx-6"><p className="font-semibold">Select a data bridge to view operational metrics.</p><p className="mt-1 text-amber-100/70">Global and unscoped activity is intentionally hidden to preserve tenant isolation.</p></div>}
          <div className="flex flex-col gap-4 border-b border-white/10 p-4 sm:p-5">
            <div>
              <div className="flex items-center gap-2"><Activity size={16} className="text-emerald-300" /><h2 className="font-display text-base font-semibold text-white">Event stream</h2></div>
              <p className="mt-1 text-xs text-slate-500">Scoped to {selectedBridgeId ? getBridgeOriginTag({ bridge_id: selectedBridgeId }, bridges) : 'no bridge selected'} · {total} events</p>
            </div>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <label className="flex w-full items-center gap-3 sm:w-auto">
                <span className="shrink-0 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">Scope</span>
                <select value={selectedBridgeId} onChange={(event) => setSelectedBridgeId(event.target.value)} className="field h-9 min-w-0 flex-1 py-1 text-xs sm:w-64 sm:flex-none" aria-label="Filter events by data bridge">
                  <option value="">All data bridges</option>
                  {activeBridges.map((bridge) => <option key={bridge.bridge_id} value={bridge.bridge_id}>{bridge.bridge_name || `${bridge.source_platform} Bridge`}</option>)}
                </select>
              </label>
              <div className="flex max-w-full gap-1 overflow-x-auto rounded-lg border border-white/10 bg-black/10 p-1">
                {FILTERS.map((item) => (
                  <button key={item} onClick={() => setFilter(item)} className={`whitespace-nowrap rounded-md px-2.5 py-1.5 text-[11px] font-semibold transition ${filter === item ? 'bg-emerald-300 text-[#0c1b18]' : 'text-slate-400 hover:bg-white/5 hover:text-white'}`}>
                    {item.replace('_', ' ')}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {error && <div className="m-5 flex items-start gap-3 rounded-xl border border-rose-300/20 bg-rose-400/10 p-4 text-sm text-rose-200"><AlertTriangle size={17} className="mt-0.5 shrink-0" /><p>{error}</p></div>}
          {triageMessage && <div className="mx-5 mt-5 flex items-center gap-2 rounded-xl border border-amber-300/20 bg-amber-400/10 p-3 text-sm text-amber-200"><Check size={16} /><p>{triageMessage}</p><button className="ml-auto text-amber-200/60 hover:text-amber-100" onClick={() => setTriageMessage('')} aria-label="Dismiss message"><X size={15} /></button></div>}
          <div className="divide-y divide-white/[0.07]">
            {loading && events.length === 0 && <div className="p-12 text-center text-sm text-slate-500">Loading event telemetry...</div>}
            {!loading && filteredEvents.length === 0 && <div className="p-12 text-center"><Clock3 className="mx-auto text-slate-600" size={24} /><p className="mt-3 text-sm text-slate-500">No events match this filter.</p></div>}
            {filteredEvents.map((event) => (
              <article key={event.event_id} className="grid cursor-pointer gap-4 p-5 transition hover:bg-white/2.5 sm:grid-cols-[minmax(150px,0.8fr)_minmax(180px,1fr)_auto] sm:items-center lg:grid-cols-[minmax(190px,1fr)_minmax(240px,1.4fr)_minmax(170px,0.7fr)_auto]" onClick={() => setSelectedEvent(event)} onKeyDown={(keyboardEvent) => keyboardEvent.key === 'Enter' && setSelectedEvent(event)} tabIndex="0" role="button">
                <div className="flex items-center gap-3"><div className={`h-2 w-2 rounded-full ${event.status === 'validated' ? 'bg-emerald-300' : event.status === 'healed' ? 'bg-amber-300' : event.status === 'rejected' ? 'bg-rose-300' : 'bg-purple-300'}`} /><div><p className="font-mono text-xs text-slate-300">{event.event_id.slice(0, 14)}...</p><p className="mt-1 text-xs text-slate-600">{formatDate(event.created_at)}</p>{getBridgeOriginTag(event, bridges) && <p className="mt-1 text-xs font-medium text-slate-500">{getBridgeOriginTag(event, bridges)}</p>}</div></div>
                <div><StatusBadge status={event.status} /><p className="mt-2 text-sm font-medium text-slate-300">{getInlineStatusLabel(event.status)}</p></div>
                <div className="hidden lg:block">{triageEventId !== event.event_id && <><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-600">Payload keys</p><p className="mt-1 truncate font-mono text-xs text-slate-400">{Object.keys(event.healed_payload || {}).join(', ') || '—'}</p></>}</div>
                {event.status === 'uncertain' ? (
                  <div className="flex flex-wrap items-center gap-2 justify-self-start sm:justify-self-end" onClick={(clickEvent) => clickEvent.stopPropagation()}>
                    {triageEventId === event.event_id && <div className="w-full rounded-lg border border-amber-300/20 bg-amber-400/5 p-3"><p className="text-xs font-semibold text-amber-200">👉 Map Field: <span className="font-mono">'{getUncertainField(event)[0]}'</span></p><p className="mt-1 text-xs text-slate-400">Value Received: <span className="font-mono text-slate-200">{String(getUncertainField(event)[1])}</span></p><select value={triageField} onChange={(changeEvent) => setTriageField(changeEvent.target.value)} className="field mt-2 h-9 w-full py-1 text-xs" aria-label="Expected schema field"><option>customer_id</option><option>email_address</option><option>stock_count</option></select></div>}
                    <button className="rounded-lg border border-amber-300/25 bg-amber-400/10 px-3 py-2 text-xs font-bold text-amber-200 transition hover:bg-amber-400/20" onClick={() => triageEventId === event.event_id ? handleMapField(event.event_id) : setTriageEventId(event.event_id)}>{triageEventId === event.event_id ? 'Apply map' : 'Map Field'}</button>
                    <button className="rounded-lg border border-rose-300/25 bg-rose-400/10 px-3 py-2 text-xs font-bold text-rose-200 transition hover:bg-rose-400/20" onClick={() => handleDrop(event.event_id)}>Drop</button>
                  </div>
                ) : <button className="icon-button justify-self-start sm:justify-self-end" onClick={(clickEvent) => { clickEvent.stopPropagation(); setSelectedEvent(event) }} aria-label="Inspect event" title="Inspect event"><Database size={16} /></button>}
              </article>
            ))}
          </div>
        </section>
      </div>
      {selectedEvent && <PayloadInspector event={selectedEvent} bridges={bridges} onClose={() => setSelectedEvent(null)} />}
    </main>
  )
}
