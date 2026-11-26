import { useState } from 'react'

/* Shared UI primitives: StatusPill, Card, Kpi, Tabs, Segmented */

const TONE = {
  green: 'green', ok: 'green', working: 'green', active: 'green', delivered: 'green',
  amber: 'amber', waiting: 'amber', warning: 'amber', paused: 'amber', review: 'amber',
  purple: 'purple', thinking: 'purple', reviewing: 'purple',
  teal: 'teal', research: 'teal', researching: 'teal',
  red: 'red', error: 'red', failed: 'red', blocked: 'red', rejected: 'red',
  grey: 'grey', idle: 'grey', disabled: 'grey', off: 'grey',
  indigo: 'indigo',
}

/* status → colour tone (fallback grey) */
export function toneOf(status) {
  const s = String(status || '').toLowerCase()
  if (TONE[s]) return TONE[s]
  if (s.includes('work') || s.includes('run') || s.includes('active')) return 'green'
  if (s.includes('wait') || s.includes('approv') || s.includes('pend')) return 'amber'
  if (s.includes('think') || s.includes('review')) return 'purple'
  if (s.includes('error') || s.includes('fail') || s.includes('block')) return 'red'
  if (s.includes('idle') || s.includes('stop')) return 'grey'
  return 'indigo'
}

export function StatusPill({ status, label, tone, dot = true, className = '' }) {
  const tn = tone || toneOf(status)
  return (
    <span className={`pill pill-${tn} ${className}`}>
      {dot && <span className="pill-dot" />}
      {label || String(status || '').replace(/_/g, ' ')}
    </span>
  )
}

export function Card({ children, className = '', ...rest }) {
  return <div className={`card ${className}`} {...rest}>{children}</div>
}

export function Kpi({ label, value, sub, mono, tone }) {
  return (
    <div className={`kpi ${tone ? 'kpi-' + tone : ''}`}>
      <span className="kpi-label">{label}</span>
      <span className={`kpi-value ${mono ? 'mono' : ''}`}>{value}</span>
      {sub && <span className="kpi-sub">{sub}</span>}
    </div>
  )
}

export function Tabs({ tabs, value, onChange, className = '' }) {
  const navigate = (event) => {
    const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
    if (!keys.includes(event.key)) return
    event.preventDefault()
    const buttons = [...event.currentTarget.querySelectorAll('[role=tab]')]
    const index = buttons.indexOf(document.activeElement)
    const step = document.documentElement.dir === 'rtl' ? -1 : 1
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
      : (index + (event.key === 'ArrowRight' ? step : -step) + buttons.length) % buttons.length
    buttons[next]?.focus()
    buttons[next]?.click()
  }
  return (
    <div className={`tabs ${className}`} role="tablist" aria-label="Sections" onKeyDown={navigate}>
      {tabs.map((tb) => (
        <button
          key={tb.id}
          role="tab"
          tabIndex={value === tb.id ? 0 : -1}
          aria-selected={value === tb.id}
          className={`tab ${value === tb.id ? 'active' : ''}`}
          onClick={() => onChange(tb.id)}
        >
          {tb.icon && <tb.icon size={14} />}
          {tb.label}
          {tb.count !== undefined && <span className="tab-count">{tb.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function Segmented({ options, value, onChange, ariaLabel }) {
  return (
    <div className="seg" role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button
          key={o.id}
          className={value === o.id ? 'on' : ''}
          onClick={() => onChange(o.id)}
          aria-label={o.label || o.id}
          aria-pressed={value === o.id}
        >
          {o.icon && <o.icon size={13} />}
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Empty({ icon = '🗂️', title, hint }) {
  return (
    <div className="empty-state">
      <span className="empty-icon" aria-hidden="true">{icon}</span>
      <strong>{title}</strong>
      {hint && <p>{hint}</p>}
    </div>
  )
}

// Wrap promise-returning UI actions without changing their API behavior.
export function ActionButton({ onClick, children, disabled, ...props }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const run = async () => {
    if (busy || disabled) return
    setBusy(true); setError('')
    try { await onClick() }
    catch (e) { setError(e.message || 'Action failed. Please try again.') }
    finally { setBusy(false) }
  }
  return <>
    <button {...props} disabled={disabled || busy} aria-busy={busy} onClick={run}>{children}</button>
    {error && <span className="np-err" role="alert">{error}</span>}
  </>
}
