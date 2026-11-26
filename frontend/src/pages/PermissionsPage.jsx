/* Permissions — agent × action matrix (local view, client-persisted). */
import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { AgentBot } from '../components/Characters'
import { Card, Empty } from '../components/ui'

const ACTIONS = ['Read', 'Write', 'Approve', 'Publish']
const LEVELS = ['None', 'Read', 'Write']

function loadMatrix(agents) {
  try {
    const raw = JSON.parse(localStorage.getItem('ao_perms') || '{}')
    if (raw && typeof raw === 'object' && Object.keys(raw).length) return raw
  } catch { /* ignore */ }
  /* default: Manager full, others read+write on their own work */
  const m = {}
  agents.forEach((a) => {
    m[a.id] = {}
    ACTIONS.forEach((act) => {
      m[a.id][act] = a.id === 'nora' ? 'Write'
        : act === 'Approve' ? 'None'
          : act === 'Publish' ? (['mona', 'adam'].includes(a.id) ? 'Write' : 'Read')
            : 'Write'
    })
  })
  return m
}

export default function PermissionsPage({ t, agents }) {
  const [matrix, setMatrix] = useState(() => loadMatrix(agents))
  const [saved, setSaved] = useState(false)

  const setCell = (agentId, action, level) => {
    setMatrix((m) => ({ ...m, [agentId]: { ...(m[agentId] || {}), [action]: level } }))
    setSaved(false)
  }
  const save = () => {
    localStorage.setItem('ao_perms', JSON.stringify(matrix))
    setSaved(true)
    setTimeout(() => setSaved(false), 1800)
  }

  if (!agents.length) return <div className="page"><Empty icon="🔐" title="No agents yet" /></div>

  return (
    <div className="page perms-page">
      <div className="perms-note">
        <ShieldCheck size={15} />
        Planning only: this matrix is stored in your browser and is not enforced by the server. It does not restrict agent actions.
      </div>
      <Card className="perms-card">
        <table className="perms-table">
          <thead>
            <tr>
              <th>Agent</th>
              {ACTIONS.map((a) => <th key={a}>{a}</th>)}
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.id}>
                <td>
                  <span className="perms-agent">
                    <AgentBot agentId={a.id} size={26} color={a.color} />
                    <span>
                      <strong>{a.name}</strong>
                      <em>{a.role}</em>
                    </span>
                  </span>
                </td>
                {ACTIONS.map((act) => (
                  <td key={act}>
                    <div className="seg seg-sm" role="radiogroup" aria-label={`${a.id} ${act}`}>
                      {LEVELS.map((lv) => (
                        <button key={lv}
                          className={(matrix[a.id]?.[act] || 'None') === lv ? 'on' : ''}
                          onClick={() => setCell(a.id, act, lv)}>
                          {lv}
                        </button>
                      ))}
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div className="save-bar">
        <span className={`save-flash ${saved ? 'on' : ''}`}>✔ Saved</span>
        <span className="spacer" />
        <button className="btn primary" onClick={save}>Save permissions</button>
      </div>
    </div>
  )
}
