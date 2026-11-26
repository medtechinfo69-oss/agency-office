/* Office (home): stats strip · isometric scene · floor cards ·
   roster tree · Journal / Scheduled tabs · approval gates. */
import { useEffect, useMemo, useState } from 'react'
import { Clock, Play, Pause, CheckCircle2, XCircle } from 'lucide-react'
import { api } from '../api'
import IsometricOffice, { officeAction } from '../components/IsometricOffice'
import { Kpi, StatusPill, Tabs, Empty } from '../components/ui'
import { AgentBot } from '../components/Characters'

const FLOORS = [
  { id: 'ground', label: 'Ground floor', emoji: '🏢' },
  { id: 'floor1', label: 'Floor 1', emoji: '🪜' },
  { id: 'gym', label: 'Gym', emoji: '🏋️' },
]

export default function OfficePage({
  t, agents, tasks, log, projects, project, projectId, connected, speed,
  approval, escalation, onApprove, picked, onPickAgent, onNewProject,
  onStandup, onMeeting, onTrends, control, onControl, canvasApi, refreshKey,
  onCustomize,
}) {
  const [floor, setFloor] = useState('ground')
  const [tab, setTab] = useState('journal')
  const [schedules, setSchedules] = useState([])

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const lists = await Promise.all(projects.map((p) => api.schedules(p.id).catch(() => [])))
        if (alive) setSchedules(lists.flat())
      } catch { /* ignore */ }
    })()
    return () => { alive = false }
  }, [projects])

  const activeAgents = agents.filter((a) => ['working', 'thinking', 'reviewing'].includes(a.status)).length
  const activeRuns = projects.filter((p) => ['running', 'awaiting_approval', 'review'].includes(p.status)).length
  const totalTokens = agents.reduce((s, a) => s + (a.tokens_in || 0) + (a.tokens_out || 0), 0)
  const tok = totalTokens > 9999 ? (totalTokens / 1000).toFixed(1) + 'k' : String(totalTokens)

  const resting = agents.length - activeAgents
  const manager = agents.find((a) => a.id === 'nora')
  const crew = agents.filter((a) => a.id !== 'nora')

  const journal = useMemo(() => [...log].slice(-60).reverse(), [log])

  return (
    <div className="page office-page">
      {/* stats strip */}
      <div className="stats-strip">
        <Kpi label="Active agents" value={activeAgents} sub={`of ${agents.length}`} />
        <Kpi label="Active runs" value={activeRuns} sub={activeRuns ? 'in flight' : 'all quiet'} />
        <Kpi label="Sub-agents" value={agents.length} sub="on payroll" />
        <Kpi label="Scheduled tasks" value={schedules.filter((s) => s.enabled).length} sub={`${schedules.length} total`} />
        <Kpi label="Total tokens" value={tok} mono sub="this office" />
        <Kpi label="CPU" value="—" mono sub="server metric unavailable" />
      </div>

      <div className="office-grid">
        {/* centre: scene + floors */}
        <section className="office-main">
          {approval && (
            <div className="approval-card" role="alert">
              <div className="approval-body">
                <strong>
                  {approval.kind === 'plan' ? '📋 ' + t('planApproval') : '📦 ' + t('deliverableApproval')}
                </strong>
                {approval.kind === 'plan' && approval.plan && (
                  <p className="approval-plan">
                    {approval.plan.summary}
                    <span className="mono approval-count">
                      {approval.plan.tasks?.length || 0} tasks
                    </span>
                  </p>
                )}
              </div>
              <div className="approval-actions">
                <button className="btn ghost" onClick={() => onApprove(approval.kind, false)}>
                  <XCircle size={14} /> {t('reject')}
                </button>
                <button className="btn good" onClick={() => onApprove(approval.kind, true)}>
                  <CheckCircle2 size={14} /> {t('approve')}
                </button>
              </div>
            </div>
          )}

          {escalation && (
            <div className="approval-card warn" role="alert">
              <div className="approval-body">
                <strong>⚠️ {t('escalate')}</strong>
                <p>{String(escalation.question || escalation.reason || '').slice(0, 240)}</p>
              </div>
            </div>
          )}

          <div className="scene-card card">
            <IsometricOffice
              agents={agents} speed={speed} picked={picked}
              onPickAgent={onPickAgent} apiRef={canvasApi}
              floor={floor} connected={connected}
              status={project?.status || 'idle'}
              onCustomize={onCustomize}
            />
          </div>

          {/* floor selector */}
          <div className="floor-row">
            {FLOORS.map((f) => (
              <button key={f.id}
                className={`floor-card ${floor === f.id ? 'on' : ''}`}
                onClick={() => setFloor(f.id)}>
                <span className="floor-emoji">{f.emoji}</span>
                <span className="floor-meta">
                  <strong>{f.label}</strong>
                  <span className="mono">
                    {f.id === 'ground'
                      ? `${activeAgents} active · ${resting} resting`
                      : '0 active · 0 resting'}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </section>

        {/* right: roster tree */}
        <aside className="roster-pane card">
          <div className="pane-head">
            <span className="eyebrow">Roster</span>
            <StatusPill status={connected ? 'working' : 'idle'}
              label={connected ? 'Live' : 'Offline'} />
          </div>
          <div className="roster-tree">
            {manager && (
              <div className="roster-node root">
                <RosterCard agent={manager} onPick={onPickAgent} t={t} />
              </div>
            )}
            <div className="roster-children">
              {crew.map((a) => (
                <div key={a.id} className="roster-node child">
                  <RosterCard agent={a} onPick={onPickAgent} t={t} />
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>

      {/* bottom: Journal / Scheduled */}
      <div className="office-bottom card">
        <div className="office-bottom-bar">
          <Tabs
            tabs={[
              { id: 'journal', label: t('journal') || 'Journal', count: journal.length },
              { id: 'scheduled', label: t('scheduled') || 'Scheduled tasks', count: schedules.length },
            ]}
            value={tab} onChange={setTab}
          />
          <div className="bb-actions">
            <button className="btn sm" onClick={() => onControl(control === 'paused' ? 'resume' : 'pause')}>
              {control === 'paused' ? <Play size={13} /> : <Pause size={13} />}
              {control === 'paused' ? t('resume') : t('pause')}
            </button>
            <button className="btn sm" onClick={onStandup}>🌅 {t('standup')}</button>
            <button className="btn sm" onClick={() => onMeeting('Brainstorm: next best move')}>🧠 {t('meeting')}</button>
            <button className="btn sm" onClick={onTrends}>🕵️ {t('trends')}</button>
          </div>
        </div>

        {tab === 'journal' ? (
          <div className="journal-list">
            {journal.length === 0 && <Empty icon="📜" title="No events yet" hint="Activity from your crew shows up here live." />}
            {journal.map((l, i) => (
              <div key={i} className={`journal-line lvl-${l.level || 'info'}`}>
                <span className="journal-dot" />
                <span className="journal-text">{l.text}</span>
                {l.created_at && (
                  <time className="mono journal-time">
                    {new Date(l.created_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </time>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="sched-list">
            {schedules.length === 0 && (
              <Empty icon="⏰" title="Nothing scheduled" hint="Auto-schedules you create appear here." />
            )}
            {schedules.map((s) => (
              <div key={s.id} className="sched-line">
                <Clock size={14} className="sched-icon" />
                <span className="sched-name">{s.name}</span>
                <span className="mono sched-cadence">every {s.interval_hours}h</span>
                <StatusPill status={s.enabled ? 'active' : 'disabled'}
                  label={s.enabled ? 'Active' : 'Disabled'} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function RosterCard({ agent, onPick, t }) {
  const isManager = agent.id === 'nora'
  return (
    <button className="roster-card" onClick={() => onPick(agent.id)}>
      <span className="roster-avatar" style={{ '--ring': agent.color || '#4f46e5' }}>
        <AgentBot agentId={agent.id} size={34} color={agent.color} />
      </span>
      <span className="roster-info">
        <span className="roster-name">
          {agent.name} {isManager && <span className="chip chip-indigo">Manager</span>}
        </span>
        <span className="roster-role">{agent.role}</span>
        {!isManager && <span className="roster-by">Launched by Manager</span>}
      </span>
      <StatusPill status={agent.status} />
    </button>
  )
}
