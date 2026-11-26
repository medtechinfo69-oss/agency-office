/* System health: report only measurements available to the browser/API. */
import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Cpu, HardDrive, MemoryStick } from 'lucide-react'
import { api } from '../api'
import { Card, StatusPill, Kpi } from '../components/ui'

function Bar({ value }) {
  return <div className="hbar"><div className="hbar-fill" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} /></div>
}
function Spark({ pts }) {
  if (pts.length < 2) return null
  const d = pts.map((v, i) => `${i ? 'L' : 'M'} ${(i / (pts.length - 1)) * 100} ${24 - Math.min(100, v) / 5}`).join(' ')
  return <svg className="spark" viewBox="0 0 100 26" preserveAspectRatio="none" aria-label="Browser memory history"><path d={d} fill="none" stroke="var(--teal)" strokeWidth="2" /></svg>
}
export default function SystemHealthPage({ health }) {
  const [providers, setProviders] = useState(null)
  const [storage, setStorage] = useState(null)
  const [memory, setMemory] = useState([])
  useEffect(() => {
    api.providers().then(setProviders).catch(() => setProviders(null))
    navigator.storage?.estimate?.().then(e => {
      if (typeof e.usage === 'number' && e.quota > 0) setStorage(e)
    }).catch(() => {})
    const sample = () => {
      const m = performance.memory
      if (m?.jsHeapSizeLimit) setMemory(p => [...p.slice(-23), { pct: 100 * m.usedJSHeapSize / m.jsHeapSizeLimit, used: m.usedJSHeapSize }])
    }
    sample()
    const id = setInterval(sample, 2000)
    return () => clearInterval(id)
  }, [])
  const last = memory[memory.length - 1]
  const diskPct = storage ? Math.round(storage.usage / storage.quota * 100) : null
  const issues = useMemo(() => {
    const out = []
    if (health && !health.ok) out.push('Backend unreachable')
    providers?.forEach(p => { if (p.active && !p.token_set && p.key !== 'ollama') out.push(`${p.label} has no key`) })
    return out
  }, [health, providers])
  const size = n => n >= 1073741824 ? `${(n / 1073741824).toFixed(1)} GB` : `${(n / 1048576).toFixed(1)} MB`
  return <div className="page health-page">
    <div className="health-kpis">
      <Card className="health-kpi"><div className="hk-head"><Cpu size={15}/><span>CPU</span><StatusPill status="idle" label="Unavailable" /></div><div className="hk-value mono">—</div><p className="muted">Server CPU metrics are not available.</p></Card>
      <Card className="health-kpi"><div className="hk-head"><MemoryStick size={15}/><span>Memory</span><StatusPill status={last ? 'ok' : 'idle'} label={last ? 'Browser heap' : 'Unavailable'} /></div><div className="hk-value mono">{last ? `${Math.round(last.pct)}%` : '—'}{last && <em className="hk-sub">{size(last.used)} browser heap</em>}</div>{last && <><Bar value={last.pct}/><Spark pts={memory.map(m => m.pct)}/></>}</Card>
      <Card className="health-kpi"><div className="hk-head"><HardDrive size={15}/><span>Disk</span><StatusPill status={storage ? 'ok' : 'idle'} label={storage ? 'Browser storage' : 'Unavailable'} /></div><div className="hk-value mono">{storage ? `${diskPct}%` : '—'}{storage && <em className="hk-sub">{size(storage.usage)} of {size(storage.quota)} browser quota</em>}</div>{storage && <Bar value={diskPct}/>}</Card>
      <Kpi label="Backend" value={!health ? '—' : health.ok ? 'UP' : 'DOWN'} mono sub="API health" />
    </div>
    <Card className="channels-card"><span className="eyebrow">Provider configuration</span><div className="channels-list">{providers === null ? <p className="muted">Provider status unavailable.</p> : providers.map(p => <div key={p.key} className="channel-row"><span className="channel-name">{p.label}</span><span className="mono channel-url">{p.base_url}</span><StatusPill status={p.active ? 'active' : 'idle'} label={p.active ? 'Selected' : (p.token_set ? 'Key configured' : 'Not selected')} /></div>)}</div><p className="muted">Selection and key configuration do not confirm connectivity.</p></Card>
    {issues.length ? <div className="issues-list">{issues.map(i => <div key={i} className="issue-row">⚠ {i}</div>)}</div> : health?.ok && providers !== null ? <div className="no-issues"><CheckCircle2 size={18}/><div><strong>No issues detected in available checks</strong><p>Server resource usage and provider connectivity are not checked here.</p></div></div> : <p className="muted">Health checks unavailable.</p>}
  </div>
}
