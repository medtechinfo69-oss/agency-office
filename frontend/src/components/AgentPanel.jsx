import useDialog from './useDialog'
import { useEffect, useState } from 'react'
import { api } from '../api'

/* Side panel when clicking an agent: task, conversation, memory, skills, tokens */
export default function AgentPanel({ t, agent, tasks, messages, memory, onClose }) {
  const dialogRef = useDialog(onClose)
  const [mem, setMem] = useState(memory || [])
  const [tab, setTab] = useState('task')

  useEffect(() => {
    if (!agent) return
    api.memory('-').catch(() => {}) // no-op; memory passed via props mostly
    setMem(memory || [])
  }, [agent, memory])

  if (!agent) return null

  const mine = tasks.filter((x) => x.assignee === agent.id)
  const active = mine.find((x) => ['progress', 'review', 'rejected'].includes(x.status))
  const convo = messages.filter((m) => m.agent_id === agent.id || m.to_agent === agent.id)
  const xpInto = agent.xp % 100

  return (
    <div className="agent-backdrop" onClick={onClose}><div ref={dialogRef} role="dialog" aria-modal="true" aria-label={`${agent.name} details`} tabIndex={-1} className="agent-panel" onClick={(e) => e.stopPropagation()}>
      <div className="ap-head" style={{ borderColor: agent.color }}>
        <div className="ap-avatar" style={{ background: agent.color }}>
          {(agent.name || '?')[0]}
        </div>
        <div>
          <div className="ap-name">{agent.name}</div>
          <div className="ap-role">{agent.role}</div>
        </div>
        <button className="ap-close" aria-label="Close agent details" onClick={onClose}>✕</button>
      </div>

      <div className="ap-stats">
        <span className="chip" style={{ background: agent.color, color: '#041018' }}>
          {t('level')} {agent.level}
        </span>
        <span className="chip">XP {agent.xp}</span>
        <span className="chip">{((agent.tokens_in || 0) + (agent.tokens_out || 0)).toLocaleString()} tok</span>
        <span className={`chip ${agent.status}`}>{agent.status}</span>
      </div>
      <div className="xp-track"><div className="xp-fill" style={{ width: xpInto + '%' }} /></div>

      <div className="ap-tabs">
        <button className={tab === 'task' ? 'active' : ''} onClick={() => setTab('task')}>🛠 {t('currentTask')}</button>
        <button className={tab === 'chat' ? 'active' : ''} aria-label="Conversation" onClick={() => setTab('chat')}>💬</button>
        <button className={tab === 'mem' ? 'active' : ''} onClick={() => setTab('mem')}>🧠 {t('memory')}</button>
        <button className={tab === 'skills' ? 'active' : ''} onClick={() => setTab('skills')}>⚡ {t('skills')}</button>
      </div>

      <div className="ap-body">
        {tab === 'task' && (
          <div>
            {active ? (
              <div className="ap-task">
                <div className="ap-task-title">{active.title}</div>
                <div className="ap-task-desc">{active.description}</div>
                <div className="ap-task-acc">
                  {(active.acceptance || []).map((a) => <div key={a}>✓ {a}</div>)}
                </div>
                {active.qa_notes?.length > 0 && (
                  <div className="ap-qa">
                    <b>QA rounds:</b>
                    {active.qa_notes.map((q, i) => (
                      <div key={i} className={q.approved ? 'good' : 'bad'}>
                        {q.approved ? '✔ approved' : `✘ ${ (q.issues||[]).join('; ')}`}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="empty-hint">{t('noTask')}</div>
            )}
            <div className="ap-all-tasks">
              <b>All tasks ({mine.length})</b>
              {mine.map((x) => (
                <div key={x.id} className={`mini-task st-${x.status}`}>
                  <span className={`dot ${x.status}`} /> {x.title}
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === 'chat' && (
          <div>
            {convo.length === 0 && <div className="empty-hint">{t('nothingHere')}</div>}
            {convo.map((m) => (
              <div key={m.id} className={`msg ${m.channel}`}>
                <div className="msg-who">{m.channel === 'boss' ? 'BOSS' : (m.agent_id || '').toUpperCase()}</div>
                <div className="msg-body">{m.text}</div>
              </div>
            ))}
          </div>
        )}

        {tab === 'mem' && (
          <div>
            {mem.length === 0 && <div className="empty-hint">{t('nothingHere')}</div>}
            {mem.map((m) => (
              <div key={m.id} className="mem-item">
                <span className="chip">{m.kind}</span>
                <div>{m.content}</div>
              </div>
            ))}
          </div>
        )}

        {tab === 'skills' && (
          <div className="skills-wrap">
            {(agent.skills || []).map((s) => (
              <span key={s} className="skill-chip">{s.replace(/_/g, ' ')}</span>
            ))}
            <div className="personality"><b>Personality:</b> {agent.personality}</div>
            <div className="personality"><b>Strictness:</b> {'●'.repeat(agent.strictness || 3)}{'○'.repeat(5 - (agent.strictness || 3))}</div>
          </div>
        )}
      </div>
    </div></div>
  )
}
