/* Workflows — auto-schedules as cards (real data from /schedules). */
import { useEffect, useState } from 'react'
import { Clock, Zap, CalendarClock } from 'lucide-react'
import { api } from '../api'
import { Card, StatusPill, Empty } from '../components/ui'

function nextIn(hours, seed = 0) {
  const period = Math.max(1, hours) * 3600 * 1000
  const start = seed || Date.now() - period / 2
  const next = start + Math.ceil((Date.now() - start) / period) * period
  const ms = Math.max(0, next - Date.now())
  const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000)
  return h > 0 ? `Next in ${h} h ${m} min` : `Next in ${m} min`
}

export default function WorkflowsPage({ t, projects }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let alive = true
    setRows(null); setError('')
    ;(async () => {
      try {
        const lists = await Promise.all(projects.map((p) =>
          api.schedules(p.id).then((s) => s.map((x) => ({ ...x, project: p.name, pid: p.id })))))
        if (alive) setRows(lists.flat())
      } catch (e) { if (alive) { setRows([]); setError(e.message) } }
    })()
    return () => { alive = false }
  }, [projects, retry])

  if (rows === null) return <div className="page"><Empty icon="⏳" title="Loading workflows…" /></div>

  return (
    <div className="page workflows-page">
      {error && <div className="feedback-banner error" role="alert"><span>Could not load workflows: {error}</span><button className="btn" onClick={() => setRetry((n) => n + 1)}>Retry</button></div>}
      <div className="wf-grid">
        {rows.map((w) => (
          <Card key={w.id} className="wf-card">
            <div className="wf-top">
              <span className="wf-icon"><Zap size={15} /></span>
              <h3>{w.name}</h3>
              <StatusPill status={w.enabled ? 'active' : 'disabled'}
                label={w.enabled ? 'Active' : 'Disabled'} />
            </div>
            <p className="wf-desc">
              {String(w.kind || 'workflow').replace(/_/g, ' ')} · {w.project}
            </p>
            <div className="wf-sched mono">
              <Clock size={13} /> every {w.interval_hours}h
              <span className="wf-last">
                last run {w.created_at
                  ? new Date(w.created_at * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                  : '—'}
              </span>
            </div>
            <div className="wf-next">
              <CalendarClock size={13} />
              {w.enabled ? nextIn(w.interval_hours, w.created_at ? w.created_at * 1000 : 0) : 'Paused'}
            </div>
          </Card>
        ))}
      </div>
      {!error && rows.length === 0 && (
        <Empty icon="⚡" title="No workflows yet"
          hint="Auto-schedules (weekly posts, reports…) appear here once created in Settings." />
      )}
    </div>
  )
}
