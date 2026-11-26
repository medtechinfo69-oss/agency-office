/* Chat with the Manager — date separators, indigo user bubbles right,
   white agent bubbles left with mono meta, composer + tools + trace. */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Send, Activity, X } from 'lucide-react'
import { StatusPill, Empty } from '../components/ui'

const QUICK = [
  { id: 'campaign', label: '🚀 Launch a full campaign' },
  { id: 'calendar', label: '🗓️ 30-day content calendar' },
  { id: 'trends', label: '🕵️ Competitor & trend scan' },
]

export default function ChatPage({
  t, messages, onSend, busy, projectId, log,
  onStandup, onMeeting, onTrends, onPreview, onAnalytics, onExport,
  approval, onApprove, health,
}) {
  const [text, setText] = useState('')
  const [trace, setTrace] = useState(false)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, busy])

  const groups = useMemo(() => {
    const out = []
    for (const m of messages) {
      const d = new Date((m.created_at || 0) * 1000)
      const key = d.toLocaleDateString()
      const last = out[out.length - 1]
      if (!last || last.key !== key) out.push({ key, label: d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' }), items: [m] })
      else last.items.push(m)
    }
    return out
  }, [messages])

  const submit = (e) => {
    e?.preventDefault()
    const v = text.trim()
    if (!v || !projectId) return
    onSend(v)
    setText('')
  }

  const quick = (id) => {
    if (!projectId) return
    if (id === 'campaign') onSend('Build the full campaign package now.')
    if (id === 'calendar') onSend('Build the 30-day content calendar now.')
    if (id === 'trends') onTrends()
  }

  return (
    <div className="page chat-page">
      <div className="chat-col">
        {approval && (
          <div className="approval-card" role="alert">
            <div className="approval-body">
              <strong>{approval.kind === 'plan' ? '📋 ' + t('planApproval') : '📦 ' + t('deliverableApproval')}</strong>
              {approval.kind === 'plan' && approval.plan && (
                <p className="approval-plan">{approval.plan.summary}</p>
              )}
            </div>
            <div className="approval-actions">
              <button className="btn ghost" onClick={() => onApprove(approval.kind, false)}>{t('reject')}</button>
              <button className="btn good" onClick={() => onApprove(approval.kind, true)}>{t('approve')}</button>
            </div>
          </div>
        )}

        <div className="chat-scroll">
          {messages.length === 0 && (
            <Empty icon="💬" title="No messages yet"
              hint="Tell Nora what to build — she plans, assigns and delivers." />
          )}
          {groups.map((g) => (
            <div key={g.key}>
              <div className="date-sep"><span>{g.label}</span></div>
              {g.items.map((m) => <Bubble key={m.id} m={m} health={health} />)}
            </div>
          ))}
          {busy && (
            <div className="msg agent">
              <div className="bubble-agent typing">
                <span /><span /><span />
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* quick actions */}
        <div className="chat-quick">
          {QUICK.map((q) => (
            <button key={q.id} className="quick-chip" onClick={() => quick(q.id)}>{q.label}</button>
          ))}
        </div>

        <form className="composer" onSubmit={submit}>
          <textarea
            className="composer-input"
            rows={2}
            value={text}
            placeholder={t('placeholder')}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit()
            }}
          />
          <div className="composer-side">
            <span className="composer-hint mono">⌘↵ to send</span>
            <button className="btn primary" disabled={busy || !text.trim()} type="submit">
              <Send size={14} /> {t('send')}
            </button>
          </div>
        </form>

        <div className="chat-tools">
          <button className="btn sm" onClick={onStandup}>🌅 {t('standup')}</button>
          <button className="btn sm" onClick={() => onMeeting('Brainstorm: next best move')}>🧠 {t('meeting')}</button>
          <button className="btn sm" onClick={onTrends}>🕵️ {t('trends')}</button>
          <span className="spacer" />
          <button className="btn sm" onClick={onPreview}>👁 {t('preview')}</button>
          <button className="btn sm" onClick={onAnalytics}>📈 {t('analytics')}</button>
          <button className="btn sm" onClick={onExport}>⤓ {t('export')}</button>
          <button className={`btn sm ${trace ? 'active' : ''}`} onClick={() => setTrace((v) => !v)}>
            <Activity size={13} /> Open trace
          </button>
        </div>
      </div>

      {/* trace drawer */}
      {trace && (
        <aside className="trace-drawer card">
          <div className="pane-head">
            <span className="eyebrow">Trace · activity</span>
            <button className="ap-close" onClick={() => setTrace(false)}><X size={13} /></button>
          </div>
          <div className="trace-list">
            {[...log].slice(-80).reverse().map((l, i) => (
              <div key={i} className={`trace-line lvl-${l.level || 'info'}`}>
                <span className="journal-dot" />
                <span>{l.text}</span>
                {l.created_at && (
                  <time className="mono">
                    {new Date(l.created_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </time>
                )}
              </div>
            ))}
          </div>
        </aside>
      )}
    </div>
  )
}

function Bubble({ m, health }) {
  if (m.channel === 'system') {
    return <div className="msg system mono">{m.text}</div>
  }
  const isUser = m.channel === 'boss'
  const d = new Date((m.created_at || 0) * 1000)
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const agent = (m.agent_id || 'nora').toUpperCase()

  if (isUser) {
    return (
      <div className="msg user">
        <div className="bubble-user">{m.text}</div>
        <div className="bubble-meta mono">{time}</div>
      </div>
    )
  }
  return (
    <div className="msg agent">
      <div className="bubble-agent-head">
        <strong>{agent}</strong>
        <span className="mono bubble-meta">
          {time} · {m.to_agent ? `→ ${m.to_agent}` : (health?.model || 'model')} · {(m.text || '').length}c
        </span>
        {m.channel === 'agent' && <StatusPill status="working" label="replied" tone="green" />}
      </div>
      <div className="bubble-agent">
        <pre className="bubble-text">{m.text}</pre>
      </div>
    </div>
  )
}
