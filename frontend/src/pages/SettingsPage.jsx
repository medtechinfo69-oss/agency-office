import { useCallback, useEffect, useState } from 'react'
import { Activity, ArrowRight, Bot, Check, CircleHelp, Clock3, Copy, Cpu, ExternalLink, Gauge, KeyRound, Layers, Moon, Palette, Play, Plus, RefreshCw, Search, Server, Shield, ShieldCheck, Sparkles, Square, Sun, Trash2, Users, Workflow } from 'lucide-react'
import { api } from '../api'
import { Action, Badge, Button, Card, Confirm, Empty, Field, InlineNotice, Modal, PageHeader, Skeleton, Switch } from '../components/admin-ui'
import { recommendModel } from './admin-models'

export const ADMIN_PAGES = [
  { id: 'diagnostics', label: 'Diagnostics', Icon: Activity, description: 'A clear view of your workspace health, performance, and activity.' },
  { id: 'runtimes', label: 'Runtimes & agents', Icon: Cpu, description: 'Manage the agents and runtimes that power your workspace.' },
  { id: 'connections', label: 'Connections', Icon: Workflow, description: 'Connect your AI providers and choose the right model for every task.' },
  { id: 'access', label: 'Access', Icon: KeyRound, description: 'Create and manage scoped API keys for secure workspace access.' },
  { id: 'instance', label: 'Instance', Icon: Server, description: 'Deployment details and operational information for this workspace.' },
  { id: 'appearance', label: 'Appearance', Icon: Palette, description: 'Make your workspace feel right. Preferences apply instantly in this browser.' },
  { id: 'account', label: 'Account', Icon: ShieldCheck, description: 'Manage your profile and protect your account.' },
  { id: 'users', label: 'Users', Icon: Users, description: 'Invite your team and manage access to this shared workspace.' },
  { id: 'roles', label: 'Roles & permissions', Icon: Shield, description: 'Define what each role can see and change. Permissions are enforced by the API.' },
]
const request = (path, method = 'get', body) => api[method]('/admin' + path, body)
const date = (value) => value ? new Date(value * 1000).toLocaleString() : 'Never'
const initials = (name) => name?.split(' ').map((s) => s[0]).slice(0, 2).join('').toUpperCase() || 'AO'
const duration = (seconds = 0) => seconds < 60 ? `${seconds}s` : seconds < 3600 ? `${Math.floor(seconds / 60)}m` : `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m`
const tone = (status) => ['active', 'working', 'connected', 'healthy'].includes(status) ? 'healthy' : ['error', 'failed', 'blocked'].includes(status) ? 'error' : ['invited', 'warning'].includes(status) ? 'warning' : 'neutral'

function SearchBox({ value, onChange, placeholder = 'Search…' }) { return <div className="a-search"><Search size={16} /><input aria-label={placeholder} placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} /></div> }
function Stat({ label, value, foot, Icon }) { return <Card><div className="a-stat-label">{label}<Icon size={16} /></div><div className="a-stat-value">{value}</div><div className="a-stat-foot">{foot}</div></Card> }

function ProviderCard({ provider, notify, onRefresh, canWrite }) {
  const [models, setModels] = useState([])
  const [model, setModel] = useState(provider.token_set ? provider.model || '' : '')
  const [token, setToken] = useState('')
  const [base, setBase] = useState(provider.base_url)
  const [status, setStatus] = useState(provider.token_set ? 'unchecked' : 'unconfigured')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [task, setTask] = useState('reasoning')
  const [ram, setRam] = useState('')
  const [lastTest, setLastTest] = useState(null)
  const [freeOnly, setFreeOnly] = useState(false)
  const isLocal = provider.key === 'ollama'
  const loadModels = useCallback(async (manual = false) => {
    setBusy(true); setError('')
    try {
      const data = await api.post(`/providers/${provider.key}/models`, { token: token || undefined, base_url: base })
      if (!data.valid) throw new Error(data.error || 'Provider did not accept this connection. Check the endpoint and credentials.')
      setModels(data.models || []); setStatus('connected'); setLastTest(Date.now())
      if (manual) notify(`Connected to ${provider.label}. ${data.models?.length || 0} models available.`, 'success')
      return data.models || []
    } catch (e) { setStatus('error'); setError(e.message); if (manual) notify(e.message, 'error'); return [] }
    finally { setBusy(false) }
  }, [provider.key, provider.label, token, base, notify])
  useEffect(() => { if (provider.token_set) loadModels() }, []) // Stored connections are discovered automatically; edits require an explicit test.
  const choices = freeOnly ? models.filter((m) => m.free) : models
  const recommendation = recommendModel(choices, task, isLocal && ram ? Number(ram) : null)
  const savedModelAvailable = models.some((m) => m.id === model)
  const canSave = !!model && savedModelAvailable && status === 'connected' && canWrite
  return <Card className="a-provider"><div className="a-provider-top"><div className="a-identity"><span className="a-avatar">{isLocal ? <Server size={20} /> : <Workflow size={20} />}</span><div><h2>{provider.label.replace(' (local · unlimited)', '').replace(' (free tier)', '')}</h2><p>{isLocal ? 'Self-hosted runtime' : provider.free ? 'Cloud provider · free-tier options' : 'Cloud provider'}</p></div></div><Badge tone={status === 'connected' ? 'healthy' : status === 'error' ? 'error' : 'neutral'}>{status === 'connected' ? 'Connected' : status === 'error' ? 'Error' : status === 'unconfigured' ? 'Not configured' : 'Checking'}</Badge></div>
    <div className="a-form">
      {isLocal && <InlineNotice>Localhost works only when the backend runs on that machine. A Vercel backend needs a remotely reachable Ollama endpoint.</InlineNotice>}
      <Field label="API endpoint"><input value={base} type="url" onChange={(e) => { setBase(e.target.value); setStatus('unchecked') }} disabled={!canWrite} /></Field>
      {!isLocal && <Field label="API key" hint={provider.token_set ? 'A key is stored securely. Leave blank to keep it.' : 'Stored server-side. Never saved in browser storage.'}><input type="password" autoComplete="new-password" value={token} disabled={!canWrite} placeholder={provider.token_set ? '••••••••••••••••' : 'Enter your provider key'} onChange={(e) => { setToken(e.target.value); setStatus('unchecked') }} /></Field>}
      <div className="a-actions"><Button busy={busy} onClick={() => loadModels(true)} disabled={!canWrite || (!isLocal && !token && !provider.token_set)}><RefreshCw size={15} />Test connection</Button>{lastTest && <span className="a-stat-foot">Checked {new Date(lastTest).toLocaleTimeString()}</span>}</div>
      {error && <InlineNotice tone="error">{error}</InlineNotice>}
      {provider.key === 'openrouter' && <div className="a-toolbar"><span className="a-stat-foot">Show free models only</span><Switch label="Show free models only" checked={freeOnly} onChange={setFreeOnly} /></div>}
      <Field label="Default model" error={!model ? 'Choose a default model before saving.' : models.length && !savedModelAvailable ? 'Choose an available model from the verified provider list.' : ''} hint={status !== 'connected' ? 'Test the connection to discover available models. Save remains blocked until verified.' : `${choices.length} available models`}>
        <select aria-label={`${provider.label} model`} value={model} disabled={busy || !choices.length || !canWrite} onChange={(e) => setModel(e.target.value)}><option value="">Choose a model</option>{model && !savedModelAvailable && <option value={model}>{model} · saved, not verified</option>}{choices.map((m) => <option key={m.id} value={m.id}>{m.id}{m.free ? ' · free tier' : ''}</option>)}</select>
      </Field>
      <div className="a-grid"><Field label="Optimize for"><select value={task} onChange={(e) => setTask(e.target.value)}>{['reasoning', 'code', 'design', 'speed'].map((x) => <option key={x}>{x}</option>)}</select></Field>{isLocal && <Field label="Available RAM (GB)" hint="Your runtime machine; not browser RAM."><input type="number" min="1" max="1024" value={ram} onChange={(e) => setRam(e.target.value)} placeholder="Optional budget" /></Field>}</div>
      <Button variant="ghost" disabled={!recommendation || !canWrite} onClick={() => { setModel(recommendation.id); notify(`Selected ${recommendation.id} for ${task}. Review before saving.`, 'success') }}><Sparkles size={16} />Auto-select best model</Button>
      {recommendation && <div><Badge tone="accent">Recommended</Badge><p className="a-stat-foot">{recommendation.id} · name/capability heuristic{isLocal && ram ? '; known sizes filtered to RAM budget' : ''}. Not a performance benchmark{isLocal ? '; models with unknown sizes need manual RAM verification' : ''}.</p></div>}
      <div className="a-form-footer"><Badge tone={provider.active ? 'accent' : 'neutral'}>{provider.active ? 'Workspace default' : 'Available provider'}</Badge><Action variant="primary" disabled={!canSave} notify={notify} success="Connection and default model saved." onClick={async () => { await api.put('/providers', { provider: provider.key, model, base_url: base, ...(token ? { token } : {}) }); await api.post('/providers/activate', { provider: provider.key }); setToken(''); await onRefresh() }}>Save & use model<ArrowRight size={15} /></Action></div>
    </div></Card>
}

function Connections({ notify, onRefresh, canWrite }) {
  const [providers, setProviders] = useState(null)
  const [error, setError] = useState('')
  const load = useCallback(async () => { try { setProviders(await api.providers()); setError('') } catch (e) { setError(e.message) } }, [])
  useEffect(() => { load() }, [load])
  return <>{error && <InlineNotice tone="error">{error}<Button onClick={load}>Retry</Button></InlineNotice>}{!providers ? <Skeleton /> : <><div className="a-notice"><ShieldCheck size={18} /><span>Credentials stay on your server. Testing discovers models without generating content. Provider usage and free-tier limits still apply.</span></div><div className="a-grid">{providers.map((provider) => <ProviderCard key={provider.key} provider={provider} notify={notify} canWrite={canWrite} onRefresh={async () => { await load(); await onRefresh() }} />)}</div></>}</>
}

function Diagnostics({ agents, connected, notify, onRefresh }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [history, setHistory] = useState([])
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const run = useCallback(async () => {
    const start = performance.now()
    try { const result = await request('/diagnostics'); setData(result); setHistory((v) => [...v.slice(-23), { ms: Math.round(performance.now() - start), at: Date.now() }]); setError(''); await onRefresh() }
    catch (e) { setError(e.message); throw e }
  }, [onRefresh])
  useEffect(() => { run().catch(() => {}) }, [])
  const logs = (data?.logs || []).filter((l) => (filter === 'all' || l.level === filter) && l.text.toLowerCase().includes(search.toLowerCase()))
  if (!data && !error) return <Skeleton />
  return <>{error && <InlineNotice tone="error">{error}</InlineNotice>}<div className="a-toolbar"><Badge tone={data ? 'healthy' : 'error'}>{data ? 'Database reachable' : 'Check failed'}</Badge><Action notify={notify} success="Diagnostics completed." onClick={run}><RefreshCw size={16} />Run diagnostics</Action></div><div className="a-stats"><Stat label="Workspace status" value={connected ? 'Live' : 'Reconnecting'} foot="Live event transport" Icon={Activity} /><Stat label="Process uptime" value={duration(data?.uptime_seconds)} foot="Resets on function cold start" Icon={Clock3} /><Stat label="Active runtimes" value={data?.active_runtimes ?? '—'} foot={`${agents.length} registered agents`} Icon={Cpu} /><Stat label="API latency" value={history.length ? `${history.at(-1).ms} ms` : '—'} foot={data ? `Last check ${new Date(data.checked_at * 1000).toLocaleTimeString()}` : 'No successful check yet'} Icon={Gauge} /></div>
    <div className="a-grid"><Card title="Response time" description="Measured browser-to-API round trip for each diagnostic run." action={<Badge>ms</Badge>}><div className="a-chart" role="img" aria-label={history.map((x) => `${x.ms} milliseconds`).join(', ')}>{history.map((x, i) => <div className="a-chart-bar" key={i} style={{ height: `${Math.max(5, x.ms / Math.max(1, ...history.map((h) => h.ms)) * 100)}%` }} title={`${x.ms} ms · ${new Date(x.at).toLocaleTimeString()}`} />)}</div><div className="a-chart-label"><span>Session measurements only</span><span>{history.length} sample{history.length === 1 ? '' : 's'}</span></div></Card><Card title="Service health" description="Current transport and persistence checks."><dl className="a-definition"><dt>Database</dt><dd><Badge tone={data ? 'healthy' : 'error'}>{data?.database || 'Unavailable'}</Badge></dd><dt>Database query</dt><dd>{data?.database_ms ?? '—'} ms</dd><dt>Event transport</dt><dd><Badge tone={connected ? 'healthy' : 'warning'}>{data?.event_transport || 'Checking'}</Badge></dd><dt>Last successful check</dt><dd>{date(data?.checked_at)}</dd></dl></Card></div>
    <Card title="Activity logs" description="Latest 100 persisted workspace events."><div className="a-toolbar"><SearchBox value={search} onChange={setSearch} placeholder="Search logs…" /><select aria-label="Filter log level" value={filter} onChange={(e) => setFilter(e.target.value)}>{['all', 'info', 'success', 'warn', 'error'].map((l) => <option key={l} value={l}>{l === 'all' ? 'All levels' : l}</option>)}</select></div>{logs.length ? <div className="a-table-wrap" tabIndex={0} role="region" aria-label="Scrollable data table"><table className="a-table"><thead><tr><th>Time</th><th>Level</th><th>Event</th></tr></thead><tbody>{logs.map((l) => <tr key={l.id}><td>{date(l.created_at)}</td><td><Badge tone={l.level === 'error' ? 'error' : l.level === 'warn' ? 'warning' : 'neutral'}>{l.level}</Badge></td><td>{l.text}</td></tr>)}</tbody></table></div> : <Empty title="No matching events" description="Try a different search or run another diagnostic check." action={<Button onClick={() => { setSearch(''); setFilter('all'); run().catch((e) => notify(e.message, 'error')) }}>Refresh logs</Button>} />}</Card></>
}

function Runtimes({ agents, health, notify, reload, canWrite }) {
  const [search, setSearch] = useState('')
  const [confirm, setConfirm] = useState(null)
  const list = agents.filter((a) => `${a.name} ${a.role}`.toLowerCase().includes(search.toLowerCase()))
  const change = async (agent, enabled) => { await request('/agent-control/' + agent.id, 'post', { enabled }); await reload(); notify(`${agent.name} ${enabled ? 'enabled for new tasks' : 'stopped from accepting new tasks'}.`, 'success') }
  return <><InlineNotice><CircleHelp size={18} />Start enables an agent for assigned tasks; it does not launch an autonomous process. Stop blocks new task execution. In-flight provider calls cannot be terminated safely.</InlineNotice><div className="a-toolbar"><SearchBox value={search} onChange={setSearch} placeholder="Search agents…" /><Badge>{agents.length} registered agents</Badge></div>{list.length ? <div className="a-grid">{list.map((agent) => <Card key={agent.id}><div className="a-provider-top"><div className="a-identity"><span className="a-avatar"><Bot size={20} /></span><div><h2>{agent.name}</h2><p>{agent.role}</p></div></div><Badge tone={agent.enabled === false ? 'neutral' : tone(agent.status)}>{agent.enabled === false ? 'Stopped' : agent.status || 'idle'}</Badge></div><dl className="a-definition"><dt>Current task</dt><dd>{agent.current_task || 'Waiting for assignment'}</dd><dt>Workspace model</dt><dd>{health?.model && health.model !== '-' ? health.model : 'No model configured'}</dd></dl><div className="a-form-footer">{agent.enabled === false ? <Action notify={notify} disabled={!canWrite} onClick={() => change(agent, true)}><Play size={15} />Start agent</Action> : <Button disabled={!canWrite} onClick={() => setConfirm(agent)}><Square size={15} />Stop agent</Button>}</div></Card>)}</div> : <Card><Empty title="No agents found" description="Adjust your search to find an agent in this workspace." action={<Button onClick={() => setSearch('')}>Clear search</Button>} /></Card>}{confirm && <Confirm title={`Stop ${confirm.name}?`} description="The agent will not accept new work. Existing in-flight calls are not force-cancelled." label="Stop agent" notify={notify} onClose={() => setConfirm(null)} onConfirm={() => change(confirm, false)} />}</>
}

function SecretModal({ secret, onClose, notify }) {
  return <Modal title={secret.title} onClose={onClose}><InlineNotice tone="warning">{secret.description}</InlineNotice><code className="a-secret">{secret.value}</code><div className="a-dialog-actions"><Action notify={notify} success="Copied to clipboard." onClick={() => navigator.clipboard.writeText(secret.value)}><Copy size={16} />Copy {secret.kind}</Action><Button variant="primary" onClick={onClose}>Done</Button></div></Modal>
}

function Access({ notify, roles, canWrite }) {
  const [keys, setKeys] = useState(null)
  const [create, setCreate] = useState(false)
  const [name, setName] = useState('')
  const [role, setRole] = useState('Viewer')
  const [secret, setSecret] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const load = useCallback(async () => setKeys(await request('/keys')), [])
  useEffect(() => { load().catch((e) => notify(e.message, 'error')) }, [load, notify])
  const reveal = (result) => setSecret({ title: 'Your API key', description: result.message, value: result.token, kind: 'key' })
  return <><InlineNotice><KeyRound size={18} />Keys authenticate API requests using an Authorization: Bearer header. Full keys are shown once; stored keys are hashed and cannot be copied again. Regenerate to replace a lost key.</InlineNotice><Card title="Workspace API keys" description="Scoped access, with immediate revocation." action={<Button variant="primary" disabled={!canWrite} onClick={() => setCreate(true)}><Plus size={16} />Create key</Button>}>{!keys ? <Skeleton /> : !keys.length ? <Empty Icon={KeyRound} title="No API keys yet" description="Create a scoped key only when an integration needs access to your workspace." action={<Button disabled={!canWrite} onClick={() => setCreate(true)}><Plus size={16} />Create your first key</Button>} /> : <div className="a-table-wrap" tabIndex={0} role="region" aria-label="Scrollable data table"><table className="a-table"><thead><tr><th>Name / key</th><th>Role</th><th>Last used</th><th>Status</th><th>Actions</th></tr></thead><tbody>{keys.map((key) => <tr key={key.id}><td><strong>{key.name}</strong><small>{key.prefix}••••••••••••</small></td><td><Badge>{key.role}</Badge></td><td>{date(key.last_used)}</td><td><Badge tone={key.revoked ? 'neutral' : 'healthy'}>{key.revoked ? 'Revoked' : 'Active'}</Badge></td><td><div className="a-actions"><Button disabled={!canWrite || !!key.revoked} variant="ghost" onClick={() => setConfirm({ key, action: 'regenerate' })} aria-label={`Regenerate ${key.name}`}><RefreshCw size={16} /></Button><Button disabled={!canWrite || !!key.revoked} variant="ghost" onClick={() => setConfirm({ key, action: 'revoke' })} aria-label={`Revoke ${key.name}`}><Trash2 size={16} /></Button></div></td></tr>)}</tbody></table></div>}</Card>
    {create && <Modal title="Create API key" onClose={() => setCreate(false)}><form className="a-form" onSubmit={(e) => e.preventDefault()}><Field label="Key name"><input autoFocus value={name} maxLength={100} onChange={(e) => setName(e.target.value)} placeholder="e.g. Reporting integration" required /></Field><Field label="Role"><select value={role} onChange={(e) => setRole(e.target.value)}>{roles.map((r) => <option key={r.id}>{r.id}</option>)}</select></Field><div className="a-dialog-actions"><Button onClick={() => setCreate(false)}>Cancel</Button><Action variant="primary" disabled={!name.trim()} notify={notify} onClick={async () => { const result = await request('/keys', 'post', { name, role }); setCreate(false); setName(''); reveal(result); await load() }}>Create key</Action></div></form></Modal>}
    {secret && <SecretModal secret={secret} notify={notify} onClose={() => setSecret(null)} />}{confirm && <Confirm title={`${confirm.action === 'revoke' ? 'Revoke' : 'Regenerate'} ${confirm.key.name}?`} description="The current key will stop working immediately. Update any integration that uses it." label={confirm.action === 'revoke' ? 'Revoke access' : 'Regenerate key'} notify={notify} onClose={() => setConfirm(null)} onConfirm={async () => { if (confirm.action === 'revoke') { await request('/keys/' + confirm.key.id, 'del'); notify('API key revoked.', 'success') } else reveal(await request('/keys/' + confirm.key.id + '/regenerate', 'post', {})); await load() }} />}</>
}

function Instance({ notify }) {
  const [data, setData] = useState(null)
  const [confirm, setConfirm] = useState(false)
  const load = useCallback(async () => setData(await request('/instance')), [])
  useEffect(() => { load().catch((e) => notify(e.message, 'error')) }, [load, notify])
  return !data ? <Skeleton /> : <><Card title="Instance overview" description="Live metadata reported by your API." action={<Action notify={notify} success="Instance details refreshed." onClick={load}><RefreshCw size={16} />Refresh</Action>}><dl className="a-definition">{[['Platform', data.platform], ['Application version', data.version], ['Commit', data.commit], ['Environment', data.environment], ['Region', data.region], ['Persistence', data.database], ['Event transport', data.event_transport], ['Process uptime', duration(data.uptime_seconds)]].map(([label, value]) => <div className="a-definition-row" key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></Card><Card title="Deployment lifecycle" description="Your instance is managed by the hosting platform."><InlineNotice tone="warning">Vercel has no persistent instance to restart. Redeployment creates new functions; current requests may be interrupted. This app does not hold a Vercel deployment token.</InlineNotice><div className="a-form-footer"><Button onClick={() => setConfirm(true)}><ExternalLink size={16} />Manage deployment</Button></div></Card>{confirm && <Confirm title="Open deployment controls?" description="Continue to your Vercel dashboard to redeploy the backend. Nothing will be restarted automatically, and workspace data will not be reset." label="Open Vercel" notify={notify} onClose={() => setConfirm(false)} onConfirm={async () => { window.open(data.restart_url, '_blank', 'noopener,noreferrer') }} />}</>
}

function Appearance({ theme, setTheme, dayNight, setDayNight, notify }) {
  const [accent, setAccent] = useState(() => localStorage.getItem('ao_accent') || 'indigo')
  const [density, setDensity] = useState(() => localStorage.getItem('ao_density') || 'comfortable')
  const set = (key, value, update) => { try { localStorage.setItem('ao_' + key, value); document.documentElement.dataset[key] = value; update(value); notify('Appearance updated.', 'success') } catch { notify('Browser storage is unavailable.', 'error') } }
  return <div className="a-grid"><div className="a-form"><Card title="Interface theme" description="A focused workspace, in light or dark."><div className="a-grid">{[{ id: 'night', label: 'Dark', Icon: Moon }, { id: 'day', label: 'Light', Icon: Sun }].map(({ id, label, Icon }) => <button key={id} className="a-choice" aria-label={label} aria-pressed={theme === id} onClick={() => { setTheme(id); notify(`${label} theme enabled.`, 'success') }}><Icon size={20} /><strong>{label}</strong><small>{id === 'night' ? 'Low-glare surfaces' : 'Clear, bright surfaces'}</small></button>)}</div></Card><Card title="Accent color" description="One accent across navigation and actions."><div className="a-actions">{['indigo', 'blue'].map((color) => <Button key={color} variant={accent === color ? 'primary' : 'secondary'} aria-pressed={accent === color} onClick={() => set('accent', color, setAccent)}>{accent === color && <Check size={16} />}{color === 'indigo' ? 'Indigo' : 'Blue'}</Button>)}</div></Card><Card title="Content density" description="Adjust the spacing of tables and panels."><div className="a-actions">{['comfortable', 'compact'].map((v) => <Button key={v} aria-pressed={density === v} variant={density === v ? 'primary' : 'secondary'} onClick={() => set('density', v, setDensity)}>{v === 'compact' ? 'Compact' : 'Comfortable'}</Button>)}</div></Card><Card title="Office lighting" description="Independent of the interface theme; saved to your workspace."><div className="a-actions">{['day', 'night', 'auto'].map((v) => <Action notify={notify} success="Office lighting updated." key={v} variant={dayNight === v ? 'primary' : 'secondary'} onClick={() => setDayNight(v)}>{v}</Action>)}</div></Card></div><Card title="Live preview" description="A sample panel using your current preferences."><div className="a-preview"><div className="a-toolbar"><div className="a-identity"><span className="a-avatar"><Layers size={20} /></span><div><h3>Project overview</h3><p className="a-stat-foot">Appearance preview only</p></div></div><Badge tone="healthy">Healthy</Badge></div><div className="a-stats"><div><div className="a-stat-label">Tasks</div><div className="a-stat-value">12</div></div><div><div className="a-stat-label">Agents</div><div className="a-stat-value">4</div></div></div><div className="a-table-wrap" tabIndex={0} role="region" aria-label="Scrollable data table"><table className="a-table"><thead><tr><th>Task</th><th>Status</th></tr></thead><tbody><tr><td>Review landing page</td><td><Badge tone="accent">In review</Badge></td></tr><tr><td>Draft campaign brief</td><td><Badge>Queued</Badge></td></tr></tbody></table></div><p className="a-stat-foot">Changes apply immediately. Preview figures are illustrative, not workspace metrics.</p></div></Card></div>
}

function Account({ me, setMe, notify }) {
  const [name, setName] = useState(me.name)
  const [email, setEmail] = useState(me.email)
  const [password, setPassword] = useState('')
  const [nextPassword, setNextPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState('')
  return <div className="a-grid"><Card title="Profile" description="Your identity in this shared workspace."><form className="a-form" onSubmit={(e) => e.preventDefault()}><div className="a-identity"><span className="a-avatar">{initials(name)}</span><div><h3>{name || 'Your profile'}</h3><Badge tone="accent">{me.role}</Badge></div></div><Field label="Full name"><input value={name} autoComplete="name" required maxLength={100} onChange={(e) => setName(e.target.value)} /></Field><Field label="Email address" hint={me.id === 'owner' ? 'Owner sign-in still uses the owner password with the email field left blank.' : 'Use this email to sign in.'}><input type="email" value={email} autoComplete="email" onChange={(e) => setEmail(e.target.value)} /></Field><div className="a-form-footer"><Action variant="primary" notify={notify} disabled={!name.trim() || (!!email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))} success="Profile updated." onClick={async () => { const profile = await request('/me', 'put', { name, email }); setMe({ ...me, ...profile }); window.dispatchEvent(new Event('agency-profile-updated')) }}>Save profile</Action></div></form></Card><Card title="Change password" description="Updating your password signs out existing sessions."><form className="a-form" onSubmit={(e) => e.preventDefault()}><Field label="Current password"><input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field><Field label="New password" error={nextPassword && nextPassword.length < 16 ? 'Use at least 16 characters.' : ''}><input type="password" autoComplete="new-password" value={nextPassword} minLength={16} onChange={(e) => setNextPassword(e.target.value)} /></Field><Field label="Confirm new password" error={repeat && repeat !== nextPassword ? 'Passwords do not match.' : error}><input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} /></Field><div className="a-form-footer"><Action variant="primary" notify={notify} onError={setError} disabled={!password || nextPassword.length < 16 || repeat !== nextPassword} onClick={async () => { await request('/me/password', 'post', { current_password: password, new_password: nextPassword }); setPassword(''); setNextPassword(''); setRepeat(''); notify('Password changed. Sign in again with your new password.', 'success'); window.dispatchEvent(new Event('agency-auth-expired')) }}>Update password</Action></div></form></Card></div>
}

function UsersPage({ me, roles, notify, canWrite }) {
  const [users, setUsers] = useState(null)
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('Viewer')
  const [secret, setSecret] = useState(null)
  const [remove, setRemove] = useState(null)
  const [edit, setEdit] = useState(null)
  const load = useCallback(async () => setUsers(await request('/users')), [])
  useEffect(() => { load().catch((e) => notify(e.message, 'error')) }, [load, notify])
  const list = (users || []).filter((u) => `${u.name} ${u.email} ${u.role}`.toLowerCase().includes(search.toLowerCase()))
  return <><InlineNotice><Users size={18} />This is a shared workspace, not separate tenant accounts. Invitations expire after 24 hours and must be shared securely; no email delivery service is configured.</InlineNotice><Card title="Workspace members" description="The owner always retains full access." action={<Button variant="primary" disabled={!canWrite} onClick={() => setModal(true)}><Plus size={16} />Invite member</Button>}><div className="a-toolbar"><SearchBox value={search} onChange={setSearch} placeholder="Search members…" /><Badge>{users?.length || 0} members</Badge></div>{!users ? <Skeleton /> : list.length ? <div className="a-table-wrap" tabIndex={0} role="region" aria-label="Scrollable data table"><table className="a-table"><thead><tr><th>Member</th><th>Role</th><th>Status</th><th>Joined / invited</th><th>Actions</th></tr></thead><tbody>{list.map((u) => <tr key={u.id}><td><div className="a-identity"><span className="a-avatar">{initials(u.name)}</span><div><strong>{u.name}{me.id === u.id ? ' (you)' : ''}</strong><small>{u.email || 'Owner password sign-in'}</small></div></div></td><td><Badge tone={u.role === 'Owner' ? 'accent' : 'neutral'}>{u.role}</Badge></td><td><Badge tone={tone(u.status)}>{u.status}</Badge></td><td>{date(u.created_at)}</td><td><div className="a-actions"><Button variant="ghost" disabled={!canWrite || u.id === 'owner'} onClick={() => { setEdit(u); setRole(u.role) }} aria-label={`Change role for ${u.name}`}><Shield size={16} /></Button><Button variant="ghost" disabled={!canWrite || u.id === 'owner' || u.id === me.id} onClick={() => setRemove(u)} aria-label={`Delete ${u.name}`}><Trash2 size={16} /></Button></div></td></tr>)}</tbody></table></div> : <Empty title="No matching members" description="Try a different name, email, or role." action={<Button onClick={() => setSearch('')}>Clear search</Button>} />}</Card>
    {modal && <Modal title="Invite a team member" onClose={() => setModal(false)}><form className="a-form" onSubmit={(e) => e.preventDefault()}><Field label="Full name"><input autoFocus required value={name} maxLength={100} onChange={(e) => setName(e.target.value)} /></Field><Field label="Email address"><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field><Field label="Role"><select value={role} onChange={(e) => setRole(e.target.value)}>{roles.map((r) => <option key={r.id}>{r.id}</option>)}</select></Field><div className="a-dialog-actions"><Button onClick={() => setModal(false)}>Cancel</Button><Action variant="primary" notify={notify} disabled={!name.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)} onClick={async () => { const result = await request('/users', 'post', { name, email, role }); setModal(false); setName(''); setEmail(''); setSecret({ title: 'Invitation ready', description: result.delivery, value: `${location.origin}/#invite=${result.invite_token}`, kind: 'invitation link' }); await load(); notify('Invitation created. Copy and share the link securely.', 'success') }}>Create invitation</Action></div></form></Modal>}
    {secret && <SecretModal secret={secret} notify={notify} onClose={() => setSecret(null)} />}{remove && <Confirm title={`Remove ${remove.name}?`} description="Their sessions and any unused invitation will stop working immediately. Workspace projects and agent outputs will not be deleted." label="Delete user" notify={notify} onClose={() => setRemove(null)} onConfirm={async () => { await request('/users/' + remove.id, 'del'); await load(); notify('User removed.', 'success') }} />}
    {edit && <Modal title={`Change ${edit.name}’s role`} onClose={() => setEdit(null)}><div className="a-form"><Field label="Role"><select value={role} onChange={(e) => setRole(e.target.value)}>{roles.map((r) => <option key={r.id}>{r.id}</option>)}</select></Field><InlineNotice>Existing sessions will be invalidated. The member must sign in again.</InlineNotice><div className="a-dialog-actions"><Button onClick={() => setEdit(null)}>Cancel</Button><Action variant="primary" notify={notify} onClick={async () => { await request('/users/' + edit.id, 'patch', { role }); await load(); setEdit(null); notify('Role updated.', 'success') }}>Save role</Action></div></div></Modal>}
  </>
}

function Roles({ roles, reload, notify, canWrite }) {
  const [selected, setSelected] = useState(roles[0]?.id || 'Admin')
  const [draft, setDraft] = useState(null)
  const [confirm, setConfirm] = useState(false)
  const role = roles.find((r) => r.id === selected)
  const permissions = draft || role?.permissions || {}
  const resources = Object.keys(permissions)
  return <><InlineNotice><ShieldCheck size={18} />Read permits viewing a resource. Manage permits changes and implies Read. The Owner role is protected and cannot be reduced. The legacy agent planning matrix does not control these permissions.</InlineNotice><Card title="Role policies" description="Changes take effect on the next API request."><div className="a-tabs" role="tablist" aria-label="Workspace roles" onKeyDown={(event) => {
    const buttons = [...event.currentTarget.querySelectorAll('[role=tab]')]
    const index = buttons.indexOf(document.activeElement)
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length
    buttons[next]?.focus(); buttons[next]?.click()
  }}>{roles.map((r) => <button key={r.id} role="tab" tabIndex={selected === r.id ? 0 : -1} aria-selected={selected === r.id} onClick={() => { setSelected(r.id); setDraft(null) }}>{r.id}</button>)}</div><div className="a-table-wrap" tabIndex={0} role="region" aria-label="Scrollable data table"><table className="a-table"><thead><tr><th>Resource</th><th>Read</th><th>Manage</th></tr></thead><tbody>{resources.map((resource) => <tr key={resource}><td><strong>{resource[0].toUpperCase() + resource.slice(1)}</strong><small>{['access', 'roles', 'users', 'connections'].includes(resource) ? 'Security-sensitive resource' : 'Workspace resource'}</small></td>{['read', 'write'].map((action) => <td key={action}><input className="a-permission" type="checkbox" aria-label={`${selected} ${resource} ${action}`} checked={!!permissions[resource][action]} disabled={!canWrite} onChange={(e) => { const next = { ...permissions, [resource]: { ...permissions[resource], [action]: e.target.checked } }; if (action === 'write' && e.target.checked) next[resource].read = true; if (action === 'read' && !e.target.checked) next[resource].write = false; setDraft(next) }} /></td>)}</tr>)}</tbody></table></div><div className="a-form-footer"><Button disabled={!draft} onClick={() => setDraft(null)}>Discard changes</Button><Button variant="primary" disabled={!draft || !canWrite} onClick={() => setConfirm(true)}>Save permissions</Button></div></Card>{confirm && <Confirm title={`Update ${selected} permissions?`} description="This changes access for every member and API key assigned to this role. Review security-sensitive permissions carefully." label="Save permissions" notify={notify} onClose={() => setConfirm(false)} onConfirm={async () => { await request('/roles/' + selected, 'put', { permissions }); await reload(); setDraft(null); notify('Role permissions saved and enforced.', 'success') }} />}</>
}

export default function SettingsPage({ section = 'connections', agents, health, connected, onRefresh, theme, setTheme, dayNight, setDayNight, notify, reloadAgents }) {
  const [me, setMe] = useState(null)
  const [roles, setRoles] = useState([])
  const [error, setError] = useState('')
  const page = ADMIN_PAGES.find((p) => p.id === section) || ADMIN_PAGES[2]
  const loadRoles = useCallback(async () => { setRoles(await request('/roles')) }, [])
  const load = useCallback(async () => {
    try { const identity = await request('/me'); setMe(identity); if (identity.permissions.roles.read) await loadRoles(); setError('') }
    catch (e) { setError(e.message) }
  }, [loadRoles])
  useEffect(() => { load() }, [load])
  const resource = { diagnostics: 'instance', runtimes: 'agents', connections: 'connections', access: 'access', instance: 'instance', users: 'users', roles: 'roles' }[section]
  const allowed = !resource || me?.permissions?.[resource]?.read
  const canWrite = !resource || me?.permissions?.[resource]?.write
  return <div className="a-admin"><PageHeader title={page.label} description={page.description} />{error ? <Card><Empty title="Settings could not be loaded" description={error} action={<Button onClick={load}>Retry connection</Button>} /></Card> : !me ? <Skeleton /> : !allowed ? <Card><Empty Icon={Shield} title="Restricted to your role" description="Your role does not allow viewing this resource. Ask your workspace owner to review your access." action={<Action notify={notify} success="Permissions refreshed." onClick={load}>Check access again</Action>} /></Card> : <>
    {section === 'diagnostics' && <Diagnostics agents={agents} connected={connected} notify={notify} onRefresh={onRefresh} />}
    {section === 'connections' && <Connections notify={notify} onRefresh={onRefresh} canWrite={canWrite} />}
    {section === 'runtimes' && <Runtimes agents={agents} health={health} notify={notify} reload={reloadAgents} canWrite={canWrite} />}
    {section === 'access' && <Access roles={roles} notify={notify} canWrite={canWrite} />}
    {section === 'instance' && <Instance notify={notify} />}
    {section === 'appearance' && <Appearance theme={theme} setTheme={setTheme} dayNight={dayNight} setDayNight={setDayNight} notify={notify} />}
    {section === 'account' && <Account me={me} setMe={setMe} notify={notify} />}
    {section === 'users' && <UsersPage me={me} roles={roles} notify={notify} canWrite={canWrite} />}
    {section === 'roles' && <Roles roles={roles} reload={loadRoles} notify={notify} canWrite={canWrite} />}
  </>}</div>
}
