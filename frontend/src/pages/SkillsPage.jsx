/* Skills — filter column with counts + card grid of agent skills. */
import { useMemo, useState } from 'react'
import { LayoutGrid, List, Search } from 'lucide-react'
import { AgentBot } from '../components/Characters'
import { StatusPill, Empty, Segmented } from '../components/ui'

const ROLE_EMOJI = {
  'Manager / Director': '🎧', Designer: '🎨', Developer: '🛠️', Copywriter: '✍️',
  'SEO Specialist': '🔎', 'Ads Specialist': '📢', 'Social Media': '📱',
  'Image Artist': '🖼️', 'QA / Compliance': '✅', Intern: '🌱',
}

export default function SkillsPage({ t, agents }) {
  const [q, setQ] = useState('')
  const [view, setView] = useState('grid')
  const [scope, setScope] = useState('all')

  const groups = useMemo(() => {
    const g = { all: agents.length, active: 0, creative: 0, growth: 0, ops: 0 }
    agents.forEach((a) => {
      if (['working', 'thinking', 'reviewing'].includes(a.status)) g.active++
      const r = (a.role || '').toLowerCase()
      if (r.includes('design') || r.includes('image') || r.includes('copy')) g.creative++
      else if (r.includes('seo') || r.includes('ads') || r.includes('social')) g.growth++
      else g.ops++
    })
    return g
  }, [agents])

  const rows = useMemo(() => {
    let list = agents
    if (scope === 'active') list = list.filter((a) => ['working', 'thinking', 'reviewing'].includes(a.status))
    if (scope === 'creative') list = list.filter((a) => /design|image|copy/.test((a.role || '').toLowerCase()))
    if (scope === 'growth') list = list.filter((a) => /seo|ads|social/.test((a.role || '').toLowerCase()))
    if (scope === 'ops') list = list.filter((a) => !/design|image|copy|seo|ads|social/.test((a.role || '').toLowerCase()))
    if (q.trim()) {
      const s = q.toLowerCase()
      list = list.filter((a) =>
        (a.name || '').toLowerCase().includes(s) ||
        (a.id || '').includes(s) ||
        (a.skills || []).some((k) => k.includes(s)))
    }
    return list
  }, [agents, scope, q])

  const filters = [
    { id: 'all', label: 'All skills', n: groups.all },
    { id: 'active', label: 'Active now', n: groups.active },
    { id: 'creative', label: 'Creative', n: groups.creative },
    { id: 'growth', label: 'Growth', n: groups.growth },
    { id: 'ops', label: 'Operations', n: groups.ops },
  ]

  return (
    <div className="page skills-page">
      <aside className="skills-filter card">
        <span className="eyebrow">Filters</span>
        {filters.map((f) => (
          <button key={f.id}
            className={`filter-row ${scope === f.id ? 'on' : ''}`}
            onClick={() => setScope(f.id)}>
            <span>{f.label}</span>
            <span className="mono filter-count">{f.n}</span>
          </button>
        ))}
      </aside>

      <section className="skills-main">
        <div className="skills-bar">
          <label className="search-box">
            <Search size={14} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search skills…" />
          </label>
          <Segmented ariaLabel="view"
            options={[{ id: 'grid', label: '', icon: LayoutGrid }, { id: 'list', label: '', icon: List }]}
            value={view} onChange={setView} />
        </div>

        <div className={view === 'grid' ? 'skill-grid' : 'skill-list'}>
          {rows.map((a) => (
            <article key={a.id} className={`skill-card card ${view}`}>
              <div className="skill-top">
                <span className="skill-emoji">{ROLE_EMOJI[a.role] || '🤖'}</span>
                <span className="mono skill-id">{a.id}</span>
                <StatusPill status={a.status} />
              </div>
              <p className="skill-desc">{(a.personality || a.role || '').split('.')[0]}</p>
              <div className="skill-tags">
                {(a.skills || []).slice(0, view === 'list' ? 6 : 4).map((s) => (
                  <span key={s} className="tag mono">{s}</span>
                ))}
                {(a.skills || []).length > 4 && view !== 'list' && (
                  <span className="tag">+{a.skills.length - 4}</span>
                )}
              </div>
              <footer className="skill-foot">
                <span className="skill-agent">
                  <AgentBot agentId={a.id} size={20} color={a.color} />
                  {a.name}
                </span>
                <span className="mono skill-scope">{a.role} · L{a.level || 1}</span>
              </footer>
            </article>
          ))}
        </div>
        {rows.length === 0 && <Empty icon="🧩" title="No skills match" hint="Try another filter or search." />}
      </section>
    </div>
  )
}
