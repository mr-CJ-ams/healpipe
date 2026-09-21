import { useEffect, useState } from 'react'
import axios from 'axios'
import { Ban, Check, Clipboard, Database, ExternalLink, FlaskConical, GitBranch, Plus, RefreshCw, RotateCcw, Server } from 'lucide-react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const targetLabels = {
  'https://api.gohighlevel.com/webhooks/healpipe': 'GoHighLevel CRM',
  'https://api.shopify.com/webhooks/healpipe': 'Shopify',
  'https://inventory.example.com/webhooks/healpipe': 'Inventory system',
  'https://api.example.com/webhooks/healpipe': 'Custom API',
}

function formatBridgeDate(value) {
  if (!value) return 'Unknown date'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(value))
}

function BridgeForm({ onSaved }) {
  const [bridgeName, setBridgeName] = useState('')
  const [source, setSource] = useState('Shopify')
  const [target, setTarget] = useState('https://api.gohighlevel.com/webhooks/healpipe')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [savedBridge, setSavedBridge] = useState(null)

  async function createBridge(event) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const response = await axios.post(`${API_BASE_URL}/v1/bridges`, {
        bridge_name: bridgeName,
        source_platform: source,
        target_endpoint_url: target,
      })
      setSavedBridge(response.data)
      onSaved(response.data)
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Unable to create this bridge.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={createBridge} className="panel space-y-4 p-4 lg:w-80">
      {savedBridge && <div className="rounded-xl border border-emerald-300/25 bg-emerald-400/10 p-4"><div className="flex items-center gap-2 text-sm font-bold text-emerald-200"><Check size={16} />Bridge created successfully</div><p className="mt-2 text-xs leading-5 text-slate-300">Copy this webhook URL into your source platform:</p><p className="mt-2 break-all rounded-lg bg-black/20 p-2 font-mono text-[11px] text-emerald-100">{savedBridge.ingestion_url}</p><button type="button" className="mt-3 inline-flex items-center gap-2 rounded-lg border border-emerald-300/25 px-3 py-2 text-xs font-bold text-emerald-200 hover:bg-emerald-400/10" onClick={() => navigator.clipboard?.writeText(savedBridge.ingestion_url)}><Clipboard size={14} />Copy webhook URL</button></div>}
      <div><p className="eyebrow">New connection</p><h2 className="mt-2 font-display text-base font-semibold text-white">Create data bridge</h2><p className="mt-1 text-xs leading-5 text-slate-500">Each bridge gets its own ingestion URL and isolated event stream.</p></div>
      <label className="block"><span className="mb-2 block text-sm text-slate-400">Bridge Reference Name</span><input className="field" required value={bridgeName} onChange={(event) => setBridgeName(event.target.value)} placeholder="Somi Apparel - US Store" /></label>
      <label className="block"><span className="mb-2 block text-sm text-slate-400">Source platform</span><select className="field" value={source} onChange={(event) => setSource(event.target.value)}><option>Shopify</option><option>TikTok Shop</option><option>WooCommerce</option><option>Supplier warehouse</option></select></label>
      <label className="block"><span className="mb-2 block text-sm text-slate-400">Target destination</span><select className="field" value={target} onChange={(event) => setTarget(event.target.value)}><option value="https://api.gohighlevel.com/webhooks/healpipe">GoHighLevel CRM</option><option value="https://api.shopify.com/webhooks/healpipe">Shopify</option><option value="https://inventory.example.com/webhooks/healpipe">Inventory system</option><option value="https://api.example.com/webhooks/healpipe">Custom API</option></select></label>
      {error && <p className="rounded-lg border border-rose-300/20 bg-rose-400/10 p-3 text-sm text-rose-200">{error}</p>}
      <button className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-300/35 bg-emerald-300/10 px-4 py-2.5 text-xs font-bold text-emerald-200 transition hover:bg-emerald-300/20 disabled:opacity-60" disabled={saving}><Plus size={15} />{saving ? 'Saving...' : 'Create data bridge'}</button>
    </form>
  )
}

function MappingPanel({ bridges }) {
  const [bridgeId, setBridgeId] = useState('')
  const [mappings, setMappings] = useState([])
  const [sourceField, setSourceField] = useState('')
  const [destinationField, setDestinationField] = useState('customer_id')
  const [sample, setSample] = useState('{"client_num":"C-100"}')
  const [preview, setPreview] = useState(null)
  const [message, setMessage] = useState('')

  async function loadMappings(id = bridgeId) {
    if (!id) return
    const response = await axios.get(`${API_BASE_URL}/v1/bridges/${id}/mappings`)
    setMappings(response.data)
  }

  async function propose(event) {
    event.preventDefault()
    try {
      await axios.post(`${API_BASE_URL}/v1/bridges/${bridgeId}/mappings`, { source_field: sourceField, destination_field: destinationField }, { headers: { 'X-Operator-Id': 'dashboard-operator' } })
      setSourceField('')
      setMessage('Mapping proposed. Approval is required before activation.')
      await loadMappings()
    } catch (requestError) { setMessage(requestError.response?.data?.detail || 'Unable to propose mapping.') }
  }

  async function mutate(mappingId, action) {
    try {
      await axios.post(`${API_BASE_URL}/v1/mappings/${mappingId}/${action}`, {}, { headers: { 'X-Operator-Id': 'dashboard-operator' } })
      setMessage(`Mapping ${action} completed.`)
      await loadMappings()
    } catch (requestError) { setMessage(requestError.response?.data?.detail || `Unable to ${action} mapping.`) }
  }

  async function testMapping() {
    try {
      const response = await axios.post(`${API_BASE_URL}/v1/bridges/${bridgeId}/mappings/test`, { payload: JSON.parse(sample) })
      setPreview(response.data)
    } catch (requestError) { setMessage(requestError.response?.data?.detail || 'Sample payload must be valid JSON.') }
  }

  return <section className="panel mt-4 overflow-hidden"><div className="border-b border-white/10 p-5 sm:p-6"><div className="flex items-center gap-2"><GitBranch size={18} className="text-amber-300" /><h2 className="font-display text-xl font-semibold text-white">Mapping revisions</h2></div><p className="mt-1 text-sm text-slate-500">Proposed changes stay inactive until an operator approves them.</p></div><div className="grid gap-5 p-5 lg:grid-cols-[minmax(220px,.8fr)_1fr] sm:p-6"><div className="space-y-4"><label className="block"><span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Bridge</span><select className="field" value={bridgeId} onChange={(event) => { setBridgeId(event.target.value); loadMappings(event.target.value) }}><option value="">Select a bridge</option>{bridges.map((bridge) => <option key={bridge.bridge_id} value={bridge.bridge_id}>{bridge.bridge_name}</option>)}</select></label><form onSubmit={propose} className="space-y-3"><input className="field" required value={sourceField} onChange={(event) => setSourceField(event.target.value)} placeholder="Source field, e.g. client_num" /><select className="field" value={destinationField} onChange={(event) => setDestinationField(event.target.value)}><option>customer_id</option><option>email_address</option><option>stock_count</option><option>phone_number</option></select><button className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-amber-300/35 bg-amber-300/10 px-4 py-2.5 text-xs font-bold text-amber-200" disabled={!bridgeId}><Plus size={14} />Propose mapping</button></form><div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Dry-run sample</p><textarea className="field min-h-24 font-mono text-xs" value={sample} onChange={(event) => setSample(event.target.value)} /><button className="mt-2 inline-flex items-center gap-2 rounded-lg border border-sky-300/25 px-3 py-2 text-xs font-bold text-sky-200" onClick={testMapping} disabled={!bridgeId}><FlaskConical size={14} />Test active mapping</button></div>{message && <p className="rounded-lg border border-white/10 bg-white/5 p-3 text-xs text-slate-300">{message}</p>}</div><div className="space-y-3">{mappings.length === 0 ? <p className="rounded-lg border border-white/10 p-5 text-sm text-slate-500">No versioned mappings for this bridge.</p> : mappings.map((mapping) => <div key={mapping.mapping_id} className="rounded-lg border border-white/10 bg-white/2 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><p className="font-mono text-xs text-slate-200">{mapping.source_field} <span className="text-slate-600">-&gt;</span> {mapping.destination_field}</p><span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] ${mapping.status === 'active' ? 'border-emerald-300/25 text-emerald-200' : mapping.status === 'proposed' ? 'border-amber-300/25 text-amber-200' : 'border-white/10 text-slate-500'}`}>v{mapping.revision} {mapping.status}</span></div><p className="mt-2 text-xs text-slate-500">Created by {mapping.created_by} · {formatBridgeDate(mapping.created_at)}</p><div className="mt-3 flex flex-wrap gap-2">{mapping.status === 'proposed' && <button className="inline-flex items-center gap-1.5 rounded border border-emerald-300/25 px-2 py-1.5 text-[11px] text-emerald-200" onClick={() => mutate(mapping.mapping_id, 'approve')}><Check size={13} />Approve</button>}{mapping.status === 'active' && <button className="inline-flex items-center gap-1.5 rounded border border-rose-300/25 px-2 py-1.5 text-[11px] text-rose-200" onClick={() => mutate(mapping.mapping_id, 'disable')}><Ban size={13} />Disable</button>}{mapping.status === 'inactive' && <button className="inline-flex items-center gap-1.5 rounded border border-sky-300/25 px-2 py-1.5 text-[11px] text-sky-200" onClick={() => mutate(mapping.mapping_id, 'rollback')}><RotateCcw size={13} />Restore</button>}</div></div>)}{preview && <pre className="overflow-auto rounded-lg border border-sky-300/20 bg-sky-400/5 p-4 font-mono text-xs leading-6 text-sky-100">{JSON.stringify(preview, null, 2)}</pre>}</div></div></section>
}

export default function BridgesManager() {
  const [bridges, setBridges] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [copiedId, setCopiedId] = useState('')

  async function loadBridges() {
    setLoading(true)
    try {
      const response = await axios.get(`${API_BASE_URL}/v1/bridges?include_inactive=false`)
      setBridges(response.data)
      setError('')
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Unable to load data bridges.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadBridges() }, [])

  async function toggleBridge(bridge) {
    try {
      await axios.patch(`${API_BASE_URL}/v1/bridges/${bridge.bridge_id}`, { is_active: !bridge.is_active })
      setBridges((current) => current.map((item) => item.bridge_id === bridge.bridge_id ? { ...item, is_active: !item.is_active } : item))
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Unable to update bridge status.')
    }
  }

  async function deleteBridge(bridge) {
    if (!window.confirm(`Deactivate ${bridge.bridge_name || bridge.source_platform}?`)) return
    try {
      await axios.delete(`${API_BASE_URL}/v1/bridges/${bridge.bridge_id}`)
      setBridges((current) => current.filter((item) => item.bridge_id !== bridge.bridge_id))
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Unable to delete bridge.')
    }
  }

  async function copyLink(bridge) {
    const link = `https://healpipe.io/v1/webhooks/receive?bridge_id=${bridge.bridge_id}`
    await navigator.clipboard?.writeText(link)
    setCopiedId(bridge.bridge_id)
    window.setTimeout(() => setCopiedId(''), 1600)
  }

  return (
    <main className="min-h-screen bg-[#091312] text-slate-100">
      <div className="page-wrap">
        <header className="page-heading"><div><div className="eyebrow">HealPipe / Configuration</div><h1 className="page-title">Data bridges</h1><p className="page-subtitle">Configure the connections that route repaired payloads from each source platform to its destination.</p></div><button className="icon-button" onClick={loadBridges} aria-label="Refresh bridges" title="Refresh bridges"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /></button></header>
          <div className="flex flex-col gap-4 py-6 lg:flex-row lg:items-start"><BridgeForm onSaved={(bridge) => setBridges((current) => [...current, bridge])} /><section className="panel min-w-0 flex-1 overflow-hidden"><div className="border-b border-white/10 p-5 sm:p-6"><div className="flex items-center gap-2"><Database size={18} className="text-emerald-300" /><h2 className="font-display text-xl font-semibold text-white">Connection registry</h2></div><p className="mt-1 text-sm text-slate-500">{bridges.length} active bridge record(s)</p></div>{error && <p className="m-5 rounded-lg border border-rose-300/20 bg-rose-400/10 p-3 text-sm text-rose-200">{error}</p>}{loading ? <p className="p-10 text-center text-sm text-slate-500">Loading bridge registry...</p> : <div className="overflow-x-auto"><table className="w-full min-w-175 text-left"><thead className="border-b border-white/10 text-[10px] uppercase tracking-[0.16em] text-slate-600"><tr><th className="px-5 py-4">Bridge Name</th><th className="px-5 py-4">Source Platform</th><th className="px-5 py-4">Destination Target</th><th className="px-5 py-4">Date Created</th><th className="px-5 py-4">Ingestion Link</th><th className="px-5 py-4 text-right">Active Switch</th></tr></thead><tbody className="divide-y divide-white/[0.07]">{bridges.map((bridge) => <tr key={bridge.bridge_id} className="transition hover:bg-white/2.5"><td className="px-5 py-5 text-sm font-semibold text-white">{bridge.bridge_name || 'Unnamed Connection'}</td><td className="px-5 py-5"><span className="inline-flex items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-3 py-1.5 text-xs font-semibold text-emerald-200"><Server size={14} />{bridge.source_platform}</span></td><td className="px-5 py-5"><span className="inline-flex items-center gap-2 text-sm text-slate-300"><ExternalLink size={15} className="text-amber-300" />{targetLabels[bridge.target_endpoint_url] || 'Custom endpoint'}</span></td><td className="px-5 py-5 text-sm text-slate-400">{formatBridgeDate(bridge.created_at)}</td><td className="px-5 py-5"><button className="inline-flex items-center gap-2 font-mono text-xs text-slate-400 hover:text-emerald-200" onClick={() => copyLink(bridge)} title="Copy webhook link"><Clipboard size={15} />{copiedId === bridge.bridge_id ? 'Copied' : 'Copy URL'}{copiedId === bridge.bridge_id && <Check size={14} />}</button></td><td className="px-5 py-5 text-right"><div className="flex items-center justify-end gap-3"><button onClick={() => toggleBridge(bridge)} className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${bridge.is_active ? 'bg-emerald-300' : 'bg-slate-700'}`} aria-label={`${bridge.is_active ? 'Deactivate' : 'Activate'} ${bridge.source_platform} bridge`}><span className={`h-4 w-4 rounded-full bg-[#092019] transition ${bridge.is_active ? 'translate-x-6' : 'translate-x-1'}`} /></button><button className="icon-button h-8 w-8 text-rose-300 hover:text-rose-200" onClick={() => deleteBridge(bridge)} aria-label="Delete bridge" title="Delete bridge"><Trash2 size={15} /></button></div></td></tr>)}</tbody></table>{!loading && bridges.length === 0 && <p className="p-10 text-center text-sm text-slate-500">No bridge connections yet.</p>}</div>}</section></div>
        <MappingPanel bridges={bridges} />
      </div>
    </main>
  )
}
