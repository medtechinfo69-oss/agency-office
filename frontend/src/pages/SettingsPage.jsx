/* Settings — top tabs; Connections renders the migrated SettingsScreen
   (Providers default tab, .p-status / .p-select selectors preserved). */
import { useEffect, useState } from 'react'
import { Server, Users, Shield, User, Palette, Activity, Boxes, KeyRound } from 'lucide-react'
import SettingsScreen from '../components/SettingsScreen'
import { api } from '../api'
import { Card, StatusPill, Segmented, Empty, Tabs } from '../components/ui'

const TABS = [
  { id: 'diagnostics', label: 'Diagnostics', icon: Activity },
  { id: 'runtimes', label: 'Runtimes & agents', icon: Boxes },
  { id: 'connections', label: 'Connections', icon: KeyRound },
  { id: 'access', label: 'Access', icon: Shield },
  { id: 'instance', label: 'Instance', icon: Server },
  { id: 'appearance', label: 'Appearance', icon: Palette },
  { id: 'account', label: 'Account', icon: User },
  { id: 'users', label: 'Users', icon: Users },
  { id: 'roles', label: 'Roles & permissions', icon: Shield },
]

export default function SettingsPage({
  t, lang, setLang, agents, health, onRefresh, onNavigate,
  theme, setTheme, dayNight, setDayNight,
  settings, onSaveSettings, projectId,
}) {
  const [tab, setTab] = useState('connections')
  const [latency, setLatency] = useState(null)
  const [user, setUser] = useState(0)
  const users = [
    { name: 'Boss', role: 'Admin', email: 'boss@agency.local', init: 'BO' },
    { name: 'Nora', role: 'Editor', email: 'nora@agency.local', init: 'NO' },
    { name: 'Karim', role: 'Writer', email: 'karim@agency.local', init: 'KA' },
  ]
  const [role, setRole] = useState('Editor')
  const [perms, setPerms] = useState('Write')

  useEffect(() => {
    const t0 = performance.now()
    api.health().then(() => setLatency(Math.round(performance.now() - t0))).catch(() => setLatency(null))
  }, [])

  return (
    <div className="page settings-page">
      <div className="settings-topbar card">
        <Tabs tabs={TABS.map((x) => ({ id: x.id, label: x.label }))} value={tab} onChange={setTab} />
      </div>

      <div className="settings-body">
        {tab === 'connections' && (
          <SettingsScreen t={t} lang={lang} setLang={setLang} settings={settings}
            onSaveSettings={onSaveSettings} projectId={projectId} onRefresh={onRefresh} />
        )}

        {tab === 'diagnostics' && (
          <div className="settings-panel">
            <Card className="diag-card">
              <span className="eyebrow">Backend</span>
              <div className="diag-row"><StatusPill status={health?.ok ? 'ok' : 'error'} label={health?.ok ? 'Reachable' : 'Down'} />
                <span className="mono">GET /api/health</span>
                <span className="mono">{latency !== null ? `${latency} ms` : '—'}</span></div>
              <div className="diag-row"><StatusPill status="ok" label="WebSocket" /><span className="mono">/ws · event stream</span></div>
              <div className="diag-row"><StatusPill status="ok" label="Ollama" /><span className="mono">localhost:11434</span></div>
            </Card>
            <Card className="diag-card">
              <span className="eyebrow">Crew</span>
              <div className="diag-row"><span>Agents registered</span><span className="mono">{agents.length}</span></div>
              <div className="diag-row"><span>Working now</span>
                <span className="mono">{agents.filter((a) => ['working', 'thinking'].includes(a.status)).length}</span></div>
              <div className="diag-row"><span>Tokens spent</span>
                <span className="mono">{agents.reduce((s, a) => s + (a.tokens_in || 0) + (a.tokens_out || 0), 0)}</span></div>
            </Card>
          </div>
        )}

        {tab === 'runtimes' && (
          <div className="settings-panel">
            <Card>
              <span className="eyebrow">LLM runtimes</span>
              <div className="rt-row"><strong>Ollama</strong><span className="mono">11434</span>
                <StatusPill status="ok" label="Local · free" /></div>
              <div className="rt-row"><strong>OpenRouter</strong><span className="mono">openrouter.ai</span>
                <StatusPill status="idle" label="Cloud fallback" /></div>
              <div className="rt-row"><strong>Custom</strong><span className="mono">any OpenAI-compatible</span>
                <StatusPill status="idle" label="Configurable" /></div>
            </Card>
            <Card>
              <span className="eyebrow">Agents</span>
              {agents.map((a) => (
                <div key={a.id} className="rt-agent">
                  <span>{a.name}</span>
                  <span className="mono">{a.role}</span>
                  <StatusPill status={a.status} />
                </div>
              ))}
            </Card>
          </div>
        )}

        {tab === 'access' && (
          <Card className="settings-panel">
            <span className="eyebrow">Access</span>
            <p className="muted">The Permissions page is a local planning matrix only. It does not enforce access restrictions.</p>
            <button className="btn primary" onClick={() => onNavigate?.('permissions')}>Open Permissions matrix</button>
          </Card>
        )}

        {tab === 'instance' && (
          <Card className="settings-panel">
            <span className="eyebrow">Instance</span>
            <div className="diag-row"><span>Frontend</span><span className="mono">:5173 · vite preview</span></div>
            <div className="diag-row"><span>API</span><span className="mono">:8000 · uvicorn</span></div>
            <div className="diag-row"><span>Database</span><span className="mono">agency.db (sqlite)</span></div>
            <div className="diag-row"><span>Region</span><span className="mono">local sandbox</span></div>
          </Card>
        )}

        {tab === 'appearance' && (
          <Card className="settings-panel">
            <span className="eyebrow">Theme</span>
            <Segmented ariaLabel="theme"
              options={[{ id: 'auto', label: 'System' }, { id: 'day', label: 'Light' }, { id: 'night', label: 'Dark' }]}
              value={theme} onChange={setTheme} />
            <span className="eyebrow" style={{ marginTop: 16 }}>Office</span>
            <Segmented ariaLabel="office theme"
              options={[{ id: 'auto', label: 'Auto' }, { id: 'day', label: 'Day' }, { id: 'night', label: 'Night' }]}
              value={dayNight} onChange={setDayNight} />
            <p className="muted">Saved to your profile and reflected in the isometric office.</p>
          </Card>
        )}

        {tab === 'account' && (
          <Card className="settings-panel">
            <span className="eyebrow">Account</span>
            <div className="diag-row"><span>Name</span><strong>Boss</strong></div>
            <div className="diag-row"><span>Role</span><strong>Admin</strong></div>
            <div className="diag-row"><span>Email</span><span className="mono">boss@agency.local</span></div>
            <p className="muted">API keys stay server-side — they are never sent to the browser.</p>
          </Card>
        )}

        {tab === 'users' && (
          <div className="users-wrap">
            <Card className="users-list">
              <span className="eyebrow">Users</span>
              {users.map((u, i) => (
                <button key={u.email} className={`user-row ${i === user ? 'on' : ''}`} onClick={() => setUser(i)}>
                  <span className="user-init">{u.init}</span>
                  <span className="user-meta"><strong>{u.name}</strong><em>{u.email}</em></span>
                  <span className="tag mono">{u.role}</span>
                </button>
              ))}
            </Card>
            <Card className="users-detail">
              <span className="eyebrow">Detail</span>
              <div className="user-big">
                <span className="user-init lg">{users[user].init}</span>
                <div><strong>{users[user].name}</strong><em>{users[user].email}</em></div>
              </div>
              <label className="field">
                <span>Role</span>
                <select value={role} onChange={(e) => setRole(e.target.value)}>
                  {['Admin', 'Editor', 'Writer', 'Viewer'].map((r) => <option key={r}>{r}</option>)}
                </select>
              </label>
              <div className="field">
                <span>Default permission</span>
                <div className="seg">
                  {['None', 'Read', 'Write'].map((p) => (
                    <button key={p} className={perms === p ? 'on' : ''} onClick={() => setPerms(p)}>{p}</button>
                  ))}
                </div>
              </div>
              <div className="save-bar">
                <span className={`save-flash ${role === users[user].role ? '' : ''}`}>unsaved changes apply instantly</span>
                <span className="spacer" />
                <button className="btn primary">Save</button>
              </div>
            </Card>
          </div>
        )}

        {tab === 'roles' && (
          <div className="roles-grid">
            {[
              { name: 'Admin', n: 1, desc: 'Full control: keys, users, delete.' },
              { name: 'Editor', n: 1, desc: 'Run projects, approve plans, chat.' },
              { name: 'Writer', n: 1, desc: 'Draft tasks and comments only.' },
              { name: 'Viewer', n: 0, desc: 'Read-only dashboards.' },
            ].map((r) => (
              <Card key={r.name} className="role-card">
                <div className="role-top"><strong>{r.name}</strong><span className="mono">{r.n} user{r.n === 1 ? '' : 's'}</span></div>
                <p>{r.desc}</p>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
