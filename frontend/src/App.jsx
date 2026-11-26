import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { connectWS } from './ws'
import { t as translate, dir } from './i18n'
import PlatformPage, { PLATFORM_PAGES } from './pages/PlatformPage'
import Sidebar, { NAV } from './components/Sidebar'
import TopBar from './components/TopBar'
import CommandCenter from './components/CommandCenter'
import { loadModels } from './model-store'
import AgentPanel from './components/AgentPanel'
import PreviewScreen from './components/PreviewScreen'
import AnalyticsScreen from './components/AnalyticsScreen'
import NewProjectModal from './components/NewProjectModal'
import { officeAction } from './components/IsometricOffice'
import OfficePage from './pages/OfficePage'
import ChatPage from './pages/ChatPage'
import ProjectsPage from './pages/ProjectsPage'
import WorkflowsPage from './pages/WorkflowsPage'
import SkillsPage from './pages/SkillsPage'
import LogsPage from './pages/LogsPage'
import PermissionsPage from './pages/PermissionsPage'
import SystemHealthPage from './pages/SystemHealthPage'
import ShopPage from './pages/ShopPage'
import SettingsPage, { ADMIN_PAGES } from './pages/SettingsPage'
const SiteBuilderPage = lazy(() => import('./sitebuilder/main'))
const BuilderPage = lazy(() => import('./pages/BuilderPage'))

/* Simple WebAudio blips (no assets needed) */
const audio = {
  ctx: null,
  play(kind) {
    if (localStorage.getItem('ao_sound') === 'off') return
    try {
      if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)()
      const o = this.ctx.createOscillator()
      const g = this.ctx.createGain()
      o.connect(g); g.connect(this.ctx.destination)
      const now = this.ctx.currentTime
      const freq = { good: 880, bad: 220, tick: 520, hire: 660 }[kind] || 440
      o.frequency.setValueAtTime(freq, now)
      if (kind === 'good') o.frequency.exponentialRampToValueAtTime(1320, now + 0.12)
      g.gain.setValueAtTime(0.06, now)
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.25)
      o.start(now); o.stop(now + 0.26)
    } catch { /* audio unavailable */ }
  },
}

let toastSeq = 0

export default function App({ onLogout } = {}) {
  /* ---------------- state ---------------- */
  const [lang, setLang] = useState('en')
  const [settings, setSettings] = useState(null)
  const [health, setHealth] = useState(null)
  const [projects, setProjects] = useState([])
  const [projectId, setProjectId] = useState(null)
  const [project, setProject] = useState(null)
  const [agents, setAgents] = useState([])
  const [messages, setMessages] = useState([])
  const [log, setLog] = useState([])
  const [tasks, setTasks] = useState([])
  const [approval, setApproval] = useState(null)
  const [escalation, setEscalation] = useState(null)
  const [picked, setPicked] = useState(null)
  const [modal, setModal] = useState(null) // preview|analytics|new
  const [page, updatePage] = useState(() => location.hash.slice(1) || 'office')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [profile, setProfile] = useState(null)
  const setPage = useCallback((value) => { location.hash = value; updatePage(value) }, [])
  useEffect(() => {
    const sync = () => { const id = location.hash.slice(1) || 'office'; updatePage(id); if (id === 'builder') setBuilderVisited(true) }
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  useEffect(() => {
    const load = () => api.get('/admin/me').then(setProfile).catch(() => {})
    const prefs = () => api.get('/admin/me/preferences').then(p => { localStorage.setItem('ao_profile_language',p.language); localStorage.setItem('ao_activity_notifications',p.activity_notifications?'on':'off'); localStorage.setItem('ao_sound',p.sound?'on':'off'); setLang(p.language) }).catch(() => {})
    prefs(); window.addEventListener('agency:preferences-updated', prefs)
    load(); window.addEventListener('agency-profile-updated', load)
    return () => { window.removeEventListener('agency-profile-updated', load); window.removeEventListener('agency:preferences-updated', prefs) }
  }, [])
  const [builderVisited, setBuilderVisited] = useState(() => location.hash === '#builder')
  const [theme, setTheme] = useState(() => localStorage.getItem('ao_theme') || 'night')
  const [control, setControl] = useState('running')
  const [chatBusy, setChatBusy] = useState(false)
  const [connected, setConnected] = useState(false)
  const [showDemoBanner, setShowDemoBanner] = useState(true)
  const [toasts, setToasts] = useState([])
  const [clock, setClock] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const officeApi = useRef(null)

  const t = useCallback((k) => translate(lang, k), [lang])

  const pushToast = useCallback((text, kind = 'info') => {
    const id = ++toastSeq
    setToasts((list) => [...list.slice(-3), { id, text, kind }])
    setTimeout(() => setToasts((list) => list.filter((x) => x.id !== id)), 5200)
  }, [])

  /* ---------------- data loaders ---------------- */
  const autoNewRef = useRef(false)
  const loadProjects = useCallback(async () => {
    const list = await api.projects()
    setProjects(list)
    if (!projectId && list.length) setProjectId(list[0].id)
    // first open with an empty office → straight into creating a real project
    if (!list.length && !autoNewRef.current && !location.hash.startsWith('#settings') && !location.hash.startsWith('#platform/')) {
      autoNewRef.current = true
      setModal('new')
    }
    return list
  }, [projectId])

  const loadProject = useCallback(async (id) => {
    if (!id) return
    const p = await api.project(id)
    setProject(p)
    setTasks(p.tasks || [])
  }, [])

  const loadAgents = useCallback(async () => setAgents(await api.agents()), [])

  const loadMessages = useCallback(async (id) => {
    if (!id) return
    setMessages(await api.messages(id))
  }, [])

  const loadLog = useCallback(async (id) => {
    if (!id) return
    setLog(await api.activity(id))
  }, [])

  /* ---------------- websocket ---------------- */
  const handleEvent = useCallback((ev) => {
    const activityToast = (...args) => { if (localStorage.getItem('ao_activity_notifications') !== 'off' || args[1] === 'error') pushToast(...args) }
    const { type, data, project_id } = ev
    if (project_id && projectId && project_id !== projectId &&
        !['log', 'settings', 'new_hire', 'agent_created', 'agent_updated', 'agent_removed'].includes(type)) return

    switch (type) {
      case 'message':
        setMessages((m) => (m.some((x) => x.id === data.id) ? m : [...m, data]))
        if (data.channel === 'agent') setChatBusy(false)
        audio.play('tick')
        break
      case 'log':
        setLog((l) => [...l.slice(-400), data])
        if (data.level === 'success') audio.play('good')
        if (data.level === 'error') { audio.play('bad'); activityToast(data.text, 'error') }
        break
      case 'agent_state':
        setAgents((list) => list.map((a) => a.id === data.agent_id
          ? { ...a, status: data.state, message: data.message, current_task: data.task || a.current_task } : a))
        break
      case 'agent_message':
        if (data.persist) {
          setMessages((m) => [...m, {
            id: 'ev' + Date.now() + Math.random(), channel: 'agent',
            agent_id: data.agent_id, to_agent: data.to_agent, text: data.text,
            project_id: projectId, created_at: Date.now() / 1000,
          }])
        }
        break
      case 'task':
        setTasks((list) => {
          const i = list.findIndex((x) => x.id === data.id)
          if (i === -1) return [...list, data]
          const copy = [...list]; copy[i] = data; return copy
        })
        break
      case 'project':
        if (data.id === projectId) setProject(data)
        break
      case 'progress':
        setProject((p) => p ? { ...p, progress: data.progress } : p)
        break
      case 'cost':
        setProject((p) => p ? { ...p, cost_usd: data.cost_usd, tokens_in: data.tokens_in, tokens_out: data.tokens_out } : p)
        break
      case 'plan_ready':
        setApproval({ kind: 'plan', plan: data.plan })
        activityToast('📋 Nora sent a plan — approve to start work', 'warn')
        break
      case 'approval_required':
        if (data.kind === 'plan') {
          setApproval({ kind: 'plan', plan: data.plan })
          activityToast('📋 Plan ready for approval', 'warn')
        } else {
          setApproval({ kind: 'deliverable', package: data.package })
          activityToast('📦 Final package ready — approve to deliver', 'success')
        }
        break
      case 'escalation':
        setEscalation(data)
        activityToast('⚠️ Nora needs your guidance', 'warn')
        break
      case 'delivered':
        setApproval(null)
        audio.play('good')
        activityToast('🎉 Package delivered!', 'success')
        loadProject(projectId)
        break
      case 'control':
        setControl(data.action === 'pause' ? 'paused' : 'running')
        break
      case 'confetti':
        officeAction(officeApi.current, 'confetti', data)
        audio.play('good')
        break
      case 'level_up':
        loadAgents()
        activityToast(`⭐ ${data.name} reached level ${data.level}!`, 'success')
        break
      case 'promotion':
        loadAgents()
        audio.play('hire')
        activityToast(`🎉 PIXEL promoted to ${data.role}!`, 'success')
        break
      case 'new_hire':
        loadAgents()
        audio.play('hire')
        activityToast(`🆕 New hire: ${data.name}`, 'success')
        break
      case 'agent_created':
      case 'agent_updated':
      case 'agent_removed':
        loadAgents()
        break
      case 'settings':
        if (data.language) setLang(data.language)
        break
      case 'meeting_start':
        setLog((l) => [...l, { level: 'info', text: `🧠 Meeting: ${data.topic}` }])
        break
      case 'meeting_end':
        setLog((l) => [...l, { level: 'success', text: `🧠 Meeting ended — best: ${String(data.best).slice(0, 100)}` }])
        activityToast('🧠 Brainstorm complete', 'success')
        break
      case 'agent_stuck':
        activityToast(`⛔ ${data.agent_id} is stuck: ${data.message}`, 'error')
        break
      default:
        break
    }
  }, [projectId, loadAgents, loadProject, pushToast])

  const refreshHealth = useCallback(async () => {
    try { setHealth(await api.health()) } catch { /* ignore */ }
  }, [])

  /* live clock (header) */
  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString([], {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    }))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  /* theme: auto | day | night → root classes (CSS handles media query) */
  useEffect(() => {
    const r = document.documentElement
    r.classList.remove('theme-light', 'theme-dark')
    const media = matchMedia('(prefers-color-scheme: dark)')
    const apply = () => { r.classList.remove('theme-light', 'theme-dark'); r.classList.add(theme === 'day' || theme === 'auto' && !media.matches ? 'theme-light' : 'theme-dark') }
    apply(); media.addEventListener('change', apply)
    localStorage.setItem('ao_theme', theme)
    r.dataset.accent = localStorage.getItem('ao_accent') || 'indigo'
    r.dataset.density = localStorage.getItem('ao_density') || 'comfortable'
    return () => media.removeEventListener('change', apply)
  }, [theme])

  /* ---------------- boot (parallel for fast first paint) ---------------- */
  useEffect(() => {
    ;(async () => {
      try {
        const [h, s] = await Promise.all([api.health(), api.settings()])
        setHealth(h)
        setSettings(s)
        setLang(localStorage.getItem('ao_profile_language') || s.language || 'en')
        if (localStorage.getItem('ao_sound') === null) localStorage.setItem('ao_sound', s.sound || 'on')
        const [list] = await Promise.all([loadProjects(), loadAgents()])
        if (list.length) {
          const id = list[0].id
          setProjectId(id)
          await Promise.all([loadProject(id), loadMessages(id), loadLog(id)])
        }
      } catch (e) {
        setLoadError('Unable to load the office. Check that the backend is running, then retry.')
        setLog([{ level: 'error', text: 'Backend unreachable: ' + e.message }])
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  useEffect(() => {
    if (!projectId) return
    Promise.all([loadProject(projectId), loadMessages(projectId), loadLog(projectId)])
      .catch((e) => pushToast('Could not load project: ' + e.message, 'error'))
    setApproval(null)
    setEscalation(null)
    setPicked(null)
  }, [projectId])

  useEffect(() => {
    const stop = connectWS(
      (ev) => handleEvent(ev),
      () => setConnected(true),
      () => setConnected(false),
    )
    return stop
  }, [handleEvent])

  useEffect(() => {
    document.documentElement.dir = dir(lang)
    document.documentElement.lang = lang
  }, [lang])

  /* ---------------- actions ---------------- */
  const sendChat = async (text, pid) => {
    const target = pid || projectId
    if (!target) return
    setChatBusy(true)
    try {
      const r = await api.chat(target, text)
      if (r?.message) {
        setMessages((m) => (m.some((x) => x.id === r.message.id) ? m : [...m, r.message]))
      }
      loadLog(target)
      setTimeout(() => setChatBusy(false), 1200)
    } catch (e) {
      setMessages((m) => [...m, {
        id: 'err' + Date.now(), channel: 'system',
        text: '⚠ ' + e.message, created_at: Date.now() / 1000,
      }])
      setChatBusy(false)
      pushToast(e.message, 'error')
    }
  }

  const doApprove = async (kind, approved, comment) => {
    try {
      await api.approve(projectId, kind, approved, comment)
      if (approved || kind === 'plan') setApproval(null)
      loadLog(projectId)
      audio.play(approved ? 'good' : 'bad')
      pushToast(approved ? '✔ Approved — the team is on it' : '✘ Rejected — Nora will revise',
        approved ? 'success' : 'warn')
    } catch (e) {
      pushToast(e.message, 'error')
    }
  }

  const doControl = async (action) => {
    try {
      const r = await api.control(projectId, action)
      if (r.ok) setControl(action === 'pause' ? 'paused' : 'running')
      loadLog(projectId)
    } catch (e) {
      pushToast(e.message, 'error')
    }
  }

  const doStandup = async () => {
    setLog((l) => [...l, { level: 'info', text: '🌅 Stand-up requested…' }])
    try {
      const r = await api.standup(projectId)
      setMessages((m) => [...m, {
        id: r.id, channel: 'agent', agent_id: 'nora',
        text: r.content, created_at: Date.now() / 1000,
      }])
      audio.play('good')
      pushToast('🌅 Stand-up ready', 'success')
    } catch (e) {
      pushToast(e.message, 'error')
    }
  }

  const doMeeting = async (topic) => {
    setLog((l) => [...l, { level: 'info', text: '🧠 Meeting started…' }])
    pushToast('🧠 Roundtable started…')
    try {
      await api.meeting(projectId, topic)
      loadLog(projectId)
      loadMessages(projectId)
    } catch (e) {
      pushToast(e.message, 'error')
    }
  }

  const doTrends = async () => {
    pushToast('🕵️ Scanning trends & competitors…')
    try {
      const r = await api.trends(projectId, '')
      setMessages((m) => [...m, {
        id: 'tr' + Date.now(), channel: 'agent', agent_id: 'yara',
        text: `TREND SCAN ${r.live ? '(live web)' : '(offline knowledge)'} — ${r.query}\n\n${r.summary}\n\n`
          + (r.competitors || []).map((c) => `• ${c.name}: ${c.observation}`).join('\n')
          + (r.sources?.length ? `\n\nSources:\n${r.sources.slice(0, 5).join('\n')}` : ''),
        created_at: Date.now() / 1000,
      }])
      pushToast('🕵️ Trend scan ready — see chat', 'success')
    } catch (e) {
      pushToast(e.message, 'error')
    }
  }

  const openNewProject = async ({ name, brief, template }) => {
    const p = await api.createProject({ name, brief, template })
    await loadProjects()
    setProjectId(p.id)
    setModal(null)
    setTimeout(() => sendChat('Please start with this brief.', p.id), 500)
  }

  const exportZip = () => api.exportZip(projectId || '')

  const pickedAgent = useMemo(() => agents.find((a) => a.id === picked) || null, [agents, picked])
  const pickedMemory = useMemo(() => pickedAgent?.memory || [], [pickedAgent])

  const night = (settings?.day_night || 'day') === 'night'
  const speed = Number(settings?.speed || 1)

  const setDayNight = (v) => api.saveSettings({ day_night: v }).then(setSettings).catch((e) => pushToast(e.message, 'error'))

  const onPickAgent = (id) => {
    if (id === '__shop__') { setPage('shop'); return }
    setPicked(id === picked ? null : id)
  }

  /* page → title + question subtitle */
  const adminSection = page === 'platform/providers' ? 'connections' : page === 'settings' ? 'connections' : page.startsWith('settings/') ? page.split('/')[1] : null
  const adminItem = ADMIN_PAGES.find((p) => p.id === adminSection)
  const navItem = NAV.find((n) => n.id === page) || NAV[0]
  const title = page === 'office'
    ? (project?.name || t('title'))
    : page.startsWith('platform/') ? (PLATFORM_PAGES.find(p=>p[0]===page.split('/')[1])?.[1]||'Platform') : adminItem ? adminItem.label : (t('nav.' + page) !== 'nav.' + page ? t('nav.' + page) : navItem.label)
  const question = page.startsWith('platform/')?'Platform management':t('sub.' + page)

  useEffect(() => {
    loadModels().catch(() => {})
    const interval = setInterval(() => loadModels(true).then(async (catalog) => { if (!catalog.selection.model) return; const result = await api.post('/models/fallback', catalog.selection); if (result.changed) { await loadModels(); window.dispatchEvent(new Event('agency:model-changed')); pushToast(`${result.warning} ${result.selection.provider} / ${result.selection.model}`, 'warning') } }).catch(() => {}), 60000)
    const changed = () => { api.health().then(setHealth).catch(() => {}) }
    window.addEventListener('agency:model-changed', changed)
    return () => { clearInterval(interval); window.removeEventListener('agency:model-changed', changed) }
  }, [])

  /* ---------------- render ---------------- */
  return (
    <div className={`app ${night ? 'night' : 'day'}`} dir={dir(lang)}>
      <CommandCenter onNavigate={setPage} />
      <a className="skip-link" href="#main-content">Skip to content</a>
      <Sidebar
        page={page} mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} profile={profile} onNavigate={(p) => { if (p === 'builder') setBuilderVisited(true); setPage(p); setPicked(null) }}
        lang={lang}
        onLang={(v) => { setLang(v); api.saveSettings({ language: v }).then(setSettings).catch((e) => pushToast(e.message, 'error')) }}
        theme={theme} onTheme={setTheme}
        t={t}
        onLogout={onLogout || (() => pushToast('Local mode has no sign-in session', 'info'))}
      />

      <main id="main-content" tabIndex={-1} className={`workspace ${page === 'builder' ? 'builder-workspace' : ''} ${['projects','logs','health','settings/diagnostics','settings/users','settings/roles'].includes(page) ? 'data-workspace' : ''}`}>
        {import.meta.env.VITE_EVENT_TRANSPORT === 'poll' && (
          <div className="feedback-banner a-cloud-notice" role="note">Cloud mode: keep this tab open to advance jobs. Scheduled runs are unavailable on this hosting setup. Add a cloud AI provider key in Settings to generate real content.</div>
        )}
        {health?.demo && showDemoBanner && (
          <div className="demo-banner">
            {health.demo_reason === 'billing'
              ? '💳 APInex billing issue (402) — running DEMO fallback so you can explore. Top up at apinex.bond/billing, then restart to resume real AI.'
              : '🧪 ' + t('demoNote')}
            <button aria-label="Dismiss demo notice" onClick={() => setShowDemoBanner(false)}>✕</button>
          </div>
        )}
        {<TopBar
          title={title} question={question}
          live={connected} clock={clock}
          provider={health?.provider_label} model={health?.model} demo={health?.demo}
          onNavigate={setPage} onLogout={onLogout || (() => pushToast('Local mode has no sign-in session', 'info'))}
          onMenu={() => setMobileOpen(true)} mobileOpen={mobileOpen} profile={profile}
          right={page === 'office' ? (
            <div className="project-pick">
              <select aria-label="Current project" value={projectId || ''} onChange={(e) => setProjectId(e.target.value)}>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          ) : null}
        />}

        {loading && page !== 'builder' && <div className="feedback-banner" role="status"><span className="loading-dot" /> Loading your workspace…</div>}
        {loadError && page !== 'builder' && <div className="feedback-banner error" role="alert"><span>{loadError}</span><button className="btn sm" onClick={() => window.location.reload()}>Retry</button></div>}

        {builderVisited && <div style={{display: page === 'builder' ? 'contents' : 'none'}}><Suspense fallback={<div className="feedback-banner" role="status">Loading Builder…</div>}><BuilderPage active={page === 'builder'} notify={pushToast} onLegacy={() => setPage('builder-legacy')} /></Suspense></div>}
        {page === 'builder-legacy' && <Suspense fallback={<div role="status">Loading runtime tools…</div>}><SiteBuilderPage officeTheme={theme} /></Suspense>}

        {page === 'office' && (
          <OfficePage
            t={t} agents={agents} tasks={tasks} log={log} projects={projects}
            project={project} projectId={projectId} connected={connected} speed={speed}
            approval={approval} escalation={escalation} onApprove={doApprove}
            picked={picked} onPickAgent={onPickAgent}
            onNewProject={() => setModal('new')}
            onStandup={doStandup} onMeeting={doMeeting} onTrends={doTrends}
            control={control} onControl={doControl}
            canvasApi={officeApi} refreshKey={tasks.length + log.length}
            onCustomize={() => setPage('shop')}
          />
        )}

        {page === 'chat' && (
          <ChatPage
            t={t} messages={messages} onSend={sendChat} busy={chatBusy}
            projectId={projectId} log={log} health={health}
            onStandup={doStandup} onMeeting={doMeeting} onTrends={doTrends}
            onPreview={() => setModal('preview')} onAnalytics={() => setModal('analytics')}
            onExport={exportZip}
            approval={approval} onApprove={doApprove}
          />
        )}

        {page === 'projects' && (
          <ProjectsPage
            t={t} projects={projects} projectId={projectId} setProjectId={setProjectId}
            tasks={tasks} agents={agents}
            onNewProject={() => setModal('new')} onPickAgent={onPickAgent}
          />
        )}

        {page === 'workflows' && <WorkflowsPage t={t} projects={projects} />}
        {page === 'skills' && <SkillsPage t={t} agents={agents} />}
        {page === 'logs' && <LogsPage t={t} log={log} onRefresh={() => loadLog(projectId)} />}
        {page.startsWith('platform/') && page!=='platform/providers' && <PlatformPage key={page} section={page.split('/')[1]} notify={pushToast}/>}
        {page === 'permissions' && <PermissionsPage t={t} agents={agents} />}
        {page === 'health' && <SystemHealthPage t={t} health={health} />}
        {page === 'shop' && <ShopPage t={t} agents={agents} onRefresh={loadAgents} />}

        {adminSection && (
          <SettingsPage key={adminSection} section={adminSection} notify={pushToast} reloadAgents={loadAgents}
            t={t} lang={lang} setLang={setLang}
            agents={agents} health={health} connected={connected} onRefresh={refreshHealth}
            onNavigate={setPage}
            theme={theme} setTheme={setTheme}
            dayNight={settings?.day_night || 'day'} setDayNight={setDayNight}
            settings={settings}
            onSaveSettings={(s) => {
              setSettings(s)
              if (s.language) setLang(s.language)
              refreshHealth()
            }}
            projectId={projectId}
          />
        )}
      </main>

      {/* notification toasts */}
      <div className="toast-stack" role="region" aria-label="Notifications" aria-live="polite" aria-relevant="additions">
        {toasts.map((x) => (
          <div key={x.id} className={`toast-item ${x.kind}`}><span>{x.text}</span><button aria-label="Dismiss notification" onClick={() => setToasts((list) => list.filter((item) => item.id !== x.id))}>×</button></div>
        ))}
      </div>

      {pickedAgent && (
        <AgentPanel t={t} agent={pickedAgent} tasks={tasks} messages={messages}
          memory={pickedMemory} onClose={() => setPicked(null)} />
      )}

      {modal === 'preview' && projectId && (
        <PreviewScreen t={t} projectId={projectId} onClose={() => setModal(null)} />
      )}
      {modal === 'analytics' && projectId && (
        <AnalyticsScreen t={t} projectId={projectId} onClose={() => setModal(null)} />
      )}
      {modal === 'new' && (
        <NewProjectModal t={t} onClose={() => setModal(null)} onCreate={openNewProject} />
      )}
    </div>
  )
}
