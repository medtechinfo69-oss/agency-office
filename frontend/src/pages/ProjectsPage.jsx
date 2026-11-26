/* Projects — kanban (Idea · To do · In progress · In review · Done) with
   monogram covers, priority badges, tags, risk pills, avatars, dates. */
import { useMemo, useState } from 'react'
import { Search, Plus, AlertTriangle } from 'lucide-react'
import { AgentBot } from '../components/Characters'
import { Empty, StatusPill } from '../components/ui'

const COLS = [
  { id: 'idea', label: 'Idea', match: (s) => s === 'idea' },
  { id: 'todo', label: 'To do', match: (s) => ['todo', 'pending'].includes(s) },
  { id: 'doing', label: 'In progress', match: (s) => ['doing', 'running', 'progress'].includes(s) },
  { id: 'review', label: 'In review', match: (s) => ['review', 'rejected'].includes(s) },
  { id: 'done', label: 'Done', match: (s) => ['done', 'blocked'].includes(s) },
]

const PRIO = { blocked: 'P0', rejected: 'P1', review: 'P2', doing: 'P3', running: 'P3', todo: 'P4', idea: 'P6', done: 'P7' }

export default function ProjectsPage({
  t, projects, projectId, setProjectId, tasks, agents, onNewProject, onPickAgent,
}) {
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState('all') // all | risk | manager
  const [sort, setSort] = useState('updated')
  const [prio, setPrio] = useState('all')

  const agentOf = (id) => agents.find((a) => a.id === id)

  const filtered = useMemo(() => {
    let list = [...tasks]
    if (q.trim()) {
      const s = q.toLowerCase()
      list = list.filter((x) =>
        (x.title || '').toLowerCase().includes(s) ||
        (x.assignee || '').toLowerCase().includes(s))
    }
    if (filter === 'risk') list = list.filter((x) => ['blocked', 'rejected'].includes(x.status))
    if (filter === 'manager') list = list.filter((x) => x.assignee === 'nora')
    if (prio !== 'all') list = list.filter((x) => (PRIO[x.status] || 'P4') === prio)
    list.sort((a, b) => sort === 'title'
      ? (a.title || '').localeCompare(b.title || '')
      : (b.updated_at || 0) - (a.updated_at || 0))
    return list
  }, [tasks, q, filter, sort, prio])

  const riskCount = tasks.filter((x) => ['blocked', 'rejected'].includes(x.status)).length

  return (
    <div className="page projects-page">
      {/* toolbar */}
      <div className="proj-toolbar">
        <div className="project-pick">
          <select value={projectId || ''} onChange={(e) => setProjectId(e.target.value)}>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <label className="search-box">
          <Search size={14} />
          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder={`${t('search')}…`} />
        </label>
        <div className="seg">
          {[['all', 'All'], ['risk', `At risk${riskCount ? ` (${riskCount})` : ''}`], ['manager', 'With Manager']].map(([id, label]) => (
            <button key={id} className={filter === id ? 'on' : ''} onClick={() => setFilter(id)}>
              {label}
            </button>
          ))}
        </div>
        <select className="mini-select" value={prio} onChange={(e) => setPrio(e.target.value)} aria-label="priority">
          <option value="all">Priority: all</option>
          {['P0', 'P1', 'P2', 'P3', 'P4', 'P6', 'P7'].map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="mini-select" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="sort">
          <option value="updated">Sort: recent</option>
          <option value="title">Sort: A–Z</option>
        </select>
        <span className="spacer" />
        <button className="btn primary" onClick={onNewProject}>
          <Plus size={14} /> {t('newProject')}
        </button>
      </div>

      {/* kanban */}
      <div className="kanban">
        {COLS.map((col) => {
          const items = filtered.filter((x) => col.match(x.status))
          return (
            <section key={col.id} className={`kanban-col col-${col.id}`}>
              <header className="kanban-head">
                <span className="kanban-title">{col.label}</span>
                <span className="kanban-count mono">{items.length}</span>
              </header>
              <div className="kanban-body">
                {items.length === 0 && (
                  <div className="kanban-empty">{col.id === 'idea' ? 'No ideas yet' : '—'}</div>
                )}
                {items.map((task) => {
                  const ag = agentOf(task.assignee)
                  const risky = ['blocked', 'rejected'].includes(task.status)
                  const initial = (task.title || '?').trim()[0].toUpperCase()
                  return (
                    <article key={task.id} className="kanban-card"
                      onClick={() => ag && onPickAgent(ag.id)}>
                      <div className="kc-cover" style={{ background: ag?.color || '#4f46e5' }}>
                        <span className="kc-mono">{initial}</span>
                        <span className="kc-prio mono">{PRIO[task.status] || 'P4'}</span>
                      </div>
                      <div className="kc-body">
                        <h4 className="kc-title">{task.title}</h4>
                        <div className="kc-tags">
                          <span className="tag mono">{task.assignee}</span>
                          {task.depends && task.depends !== '[]' && task.depends !== '[]' &&
                            <span className="tag">deps</span>}
                          {risky && (
                            <span className="pill pill-red">
                              <AlertTriangle size={10} />
                              {task.status === 'blocked' ? 'Blocked' : 'Rejected'}
                            </span>
                          )}
                        </div>
                        <div className="kc-foot">
                          <span className="kc-avatars">
                            <span className="kc-av" style={{ '--ring': ag?.color || '#4f46e5' }}>
                              {ag ? <AgentBot agentId={ag.id} size={22} color={ag.color} /> : '?'}
                            </span>
                            {risky && (
                              <span className="kc-av" style={{ '--ring': '#f59e0b' }}>
                                <AgentBot agentId="rami" size={22} color="#f59e0b" />
                              </span>
                            )}
                          </span>
                          <time className="mono kc-date">
                            {task.updated_at
                              ? new Date(task.updated_at * 1000).toLocaleDateString([], { month: 'short', day: 'numeric' })
                              : ''}
                          </time>
                        </div>
                      </div>
                    </article>
                  )
                })}
              </div>
            </section>
          )
        })}
      </div>

      {tasks.length === 0 && (
        <Empty icon="📁" title="No tasks in this project yet"
          hint="Approve Nora's plan and cards will populate the board." />
      )}
    </div>
  )
}
