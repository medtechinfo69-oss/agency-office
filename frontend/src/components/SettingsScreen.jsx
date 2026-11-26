import { useEffect, useState } from 'react'
import { api } from '../api'

/* Settings: AI provider (token never displayed), brand kit, agent editor,
 * prompt library, auto-schedules, language/theme/sound/speed. */
export default function SettingsScreen({ t, lang, setLang, settings, onSaveSettings,
  projectId, onClose, onSaved }) {
  const [tab, setTab] = useState('providers')
  const [s, setS] = useState(settings || {})
  const [brand, setBrand] = useState({ name: '', colors: [], fonts: [], tone: '', rules: [] })
  const [agents, setAgents] = useState([])
  const [prompts, setPrompts] = useState([])
  const [schedules, setSchedules] = useState([])
  const [editing, setEditing] = useState(null)
  const [toast, setToast] = useState('')
  const [providers, setProviders] = useState([])
  const [pforms, setPforms] = useState({})  // per-provider edit fields
  const [mstate, setMstate] = useState({})  // per-provider model-list status

  useEffect(() => { setS(settings || {}) }, [settings])
  useEffect(() => {
    api.agents().then(setAgents).catch(() => {})
    api.prompts().then(setPrompts).catch(() => {})
    api.providers().then((list) => {
      setProviders(list)
      const forms = {}
      for (const p of list) {
        forms[p.key] = {
          model: p.model, token: '', base_url: p.base_url,
          image_model: p.image_model || 'pollinations-free',
        }
      }
      setPforms(forms)
      // stored keys → verify + populate dropdowns automatically
      for (const p of list) {
        if (p.token_set || p.key === 'ollama') {
          checkModels(p.key, { silent: true })
        }
      }
    }).catch(() => {})
    if (projectId) {
      api.brand(projectId).then(setBrand).catch(() => {})
      api.schedules(projectId).then(setSchedules).catch(() => {})
    }
  }, [projectId]) // eslint-disable-line

  /* Validate a key (typed or stored) and auto-fill the model dropdowns. */
  const checkModels = async (key, opts = {}) => {
    setMstate((m) => ({ ...m, [key]: { ...(m[key] || {}), status: 'checking' } }))
    try {
      const body = {}
      if (opts.token) body.token = opts.token
      const f = pforms[key] || {}
      if (f.base_url) body.base_url = f.base_url
      const r = await api.providerModels(key, body)
      setMstate((m) => ({ ...m, [key]: { status: r.valid ? 'ok' : 'error', ...r } }))
      if (r.valid && r.models && r.models.length) {
        setPforms((p) => {
          const cur = (p[key] || {}).model
          const ids = r.models.map((x) => x.id)
          const freeIds = r.models.filter((x) => x.free).map((x) => x.id)
          // dropdown shows free models only when the provider has any
          const pool = freeIds.length ? freeIds : ids
          const model = (cur && pool.includes(cur)) ? cur : (pool[0] || cur || '')
          const imgCur = (p[key] || {}).image_model
          const image = (imgCur && (imgCur === 'pollinations-free' || ids.includes(imgCur)))
            ? imgCur
            : (r.image_default || 'pollinations-free')
          return { ...p, [key]: { ...(p[key] || {}), model, image_model: image } }
        })
        if (!opts.silent) {
          flash(`✓ key valid — ${r.free_count || r.models.length} free model(s) ready`)
        }
      } else if (!opts.silent) {
        flash(`✗ ${r.error || 'key check failed'}`)
      }
      return r
    } catch (e) {
      setMstate((m) => ({ ...m, [key]: { status: 'error', error: e.message, models: [] } }))
      if (!opts.silent) flash('⚠ ' + e.message)
      return null
    }
  }

  const refreshProviders = async () => {
    try {
      const list = await api.providers()
      setProviders(list)
      setPforms((prev) => {
        const next = { ...prev }
        for (const p of list) {
          next[p.key] = {
            model: p.model,
            token: next[p.key]?.token || '',
            base_url: next[p.key]?.base_url || p.base_url,
            image_model: next[p.key]?.image_model || p.image_model || 'pollinations-free',
          }
        }
        return next
      })
    } catch (e) { flash('⚠ ' + e.message) }
  }

  const saveProviderCred = async (key) => {
    try {
      const f = pforms[key] || {}
      await api.saveProvider({
        provider: key,
        model: f.model,
        base_url: f.base_url,
        token: f.token && f.token.trim() ? f.token.trim() : undefined,
        image_model: f.image_model || 'pollinations-free',
      })
      setPforms((p) => ({ ...p, [key]: { ...p[key], token: '' } }))
      await refreshProviders()
      flash('✔ Saved — token stays on the server')
      // key now stored → re-verify silently so the dropdown stays fresh
      checkModels(key, { silent: true })
    } catch (e) { flash('⚠ ' + e.message) }
  }

  const activateProvider = async (key) => {
    try {
      await api.activateProvider(key)
      await refreshProviders()
      const p = providers.find((x) => x.key === key)
      flash(`✔ ${p?.label || key} is now the active provider`)
    } catch (e) { flash('⚠ ' + e.message) }
  }

  const flash = (m) => { setToast(m); setTimeout(() => setToast(''), 3500) }

  const saveProvider = async () => {
    try {
      const out = await api.saveSettings({
        api_base_url: s.api_base_url, api_token: s.api_token || undefined,
        text_model: s.text_model,
        auto_approve: s.auto_approve,
        language: s.language, sound: s.sound, speed: s.speed, day_night: s.day_night,
      })
      onSaveSettings(out)
      flash('✔ Saved')
    } catch (e) { flash('⚠ ' + e.message) }
  }

  const saveBrand = async () => {
    try {
      await api.saveBrand(projectId, brand)
      flash('✔ Brand kit saved — all agents will obey it')
    } catch (e) { flash('⚠ ' + e.message) }
  }

  const uploadLogo = async (file) => {
    try {
      const r = await api.uploadLogo(projectId, file)
      flash('✔ Logo uploaded')
      setBrand((b) => ({ ...b, logo_url: r.logo_url }))
    } catch (e) { flash('⚠ ' + e.message) }
  }

  const saveAgent = async () => {
    try {
      await api.saveAgent(editing, editing.id)
      setAgents(await api.agents())
      setEditing(null)
      flash('✔ Agent saved')
    } catch (e) { flash('⚠ ' + e.message) }
  }

  const fireAgent = async (id) => {
    if (!confirm('Remove this custom agent?')) return
    try {
      await api.deleteAgent(id)
      setAgents(await api.agents())
    } catch (e) { flash('⚠ ' + e.message) }
  }

  const savePrompt = async () => {
    const name = prompt('Prompt name?')
    if (!name) return
    const content = prompt('Prompt content?')
    if (!content) return
    try {
      await api.savePrompt({ name, category: 'custom', content })
      setPrompts(await api.prompts())
    } catch (e) { flash('⚠ ' + e.message) }
  }

  const toggleSchedule = async (sch) => {
    try {
      await api.patchSchedule(sch.id, { enabled: !sch.enabled })
      setSchedules(await api.schedules(projectId))
    } catch (e) { flash('⚠ ' + e.message) }
  }

  return (
    <div className="settings-screen">
      <div className="modal wide static" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span>⚙️ {t('settings')}</span>
          {onClose && <button className="ap-close" onClick={onClose}>✕</button>}
        </div>

        <div className="settings-tabs">
          {[
            ['providers', '🔌 Providers'],
            ['brand', '🎨 ' + t('brandKit')],
            ['agents', '🤖 ' + t('agentEditor')],
            ['prompts', '📜 ' + t('promptLibrary')],
            ['sched', '⏰ ' + t('scheduled')],
            ['ui', '🎛 UI'],
          ].map(([k, label]) => (
            <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>
              {label}
            </button>
          ))}
        </div>

        <div className="modal-body">
          {toast && <div className="toast">{toast}</div>}

          {tab === 'providers' && (
            <div>
              <div className="dim" style={{ marginBottom: 12 }}>
                Switch AI backends with one click — any OpenAI-compatible API.
                Tokens are stored server-side only and never displayed.
                On billing/rate-limit errors the app automatically fails over
                to the next configured provider.
              </div>

              <div className="provider-list">
                {providers.map((p) => (
                  <div key={p.key} className={`provider-card ${p.active ? 'active' : ''}`}>
                    <div className="provider-head">
                      <b>{p.label}</b>
                      {p.active && <span className="chip good">● ACTIVE</span>}
                      {!p.active && p.token_set && <span className="chip">ready</span>}
                      {!p.token_set && p.key !== 'ollama' && <span className="chip warn">no key</span>}
                      {p.free && <span className="chip">free</span>}
                      <span className="spacer" />
                      {p.site && (
                        <a className="dim" href={p.site} target="_blank" rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}>
                          get key ↗
                        </a>
                      )}
                    </div>
                    <div className="provider-form">
                      <input
                        type="text"
                        className="p-url"
                        title="base URL"
                        placeholder="base URL (e.g. http://localhost:11434/v1)"
                        value={pforms[p.key]?.base_url ?? p.base_url}
                        onChange={(e) => setPforms((f) => ({
                          ...f, [p.key]: { ...(f[p.key] || {}), base_url: e.target.value },
                        }))}
                        onBlur={() => {
                          const v = (pforms[p.key]?.base_url || '').trim()
                          if (v) checkModels(p.key, { silent: true })
                        }}
                      />
                      <select
                        className="p-select"
                        value={pforms[p.key]?.model ?? p.model}
                        onChange={(e) => setPforms((f) => ({
                          ...f, [p.key]: { ...(f[p.key] || {}), model: e.target.value },
                        }))}
                        title="model"
                      >
                        {(() => {
                          const ms = mstate[p.key] || {}
                          const cur = pforms[p.key]?.model ?? p.model
                          const list = (ms.status === 'ok' && ms.models) ? ms.models : []
                          const free = list.filter((m) => m.free)
                          const show = free.length ? free : list
                          const opts = []
                          if (!show.some((m) => m.id === cur)) {
                            opts.push(<option key="__cur" value={cur}>{cur}</option>)
                          }
                          for (const m of show) {
                            opts.push(<option key={m.id} value={m.id}>{m.id}</option>)
                          }
                          if (!opts.length) opts.push(<option key="__cur" value={cur}>{cur}</option>)
                          return opts
                        })()}
                      </select>
                      <input
                        type="password"
                        placeholder={p.token_set ? '•••••• stored (leave empty to keep)' : 'API key…'}
                        value={pforms[p.key]?.token ?? ''}
                        onChange={(e) => setPforms((f) => ({
                          ...f, [p.key]: { ...(f[p.key] || {}), token: e.target.value },
                        }))}
                        onBlur={(e) => {
                          const v = e.target.value.trim()
                          if (v.length >= 12) checkModels(p.key, { token: v })
                        }}
                      />
                      <button className="btn" onClick={() => saveProviderCred(p.key)}>
                        💾 {t('save')}
                      </button>
                      {!p.active && (
                        <button className="btn primary" onClick={() => activateProvider(p.key)}>
                          ⚡ {p.token_set || p.key === 'ollama' ? 'Activate' : 'Activate anyway'}
                        </button>
                      )}
                    </div>
                    <div className="provider-sub">
                      <select
                        className="p-select img"
                        title="image model"
                        value={pforms[p.key]?.image_model || 'pollinations-free'}
                        onChange={(e) => setPforms((f) => ({
                          ...f, [p.key]: { ...(f[p.key] || {}), image_model: e.target.value },
                        }))}
                      >
                        <option value="pollinations-free">🖼 pollinations-free · auto (free, no key)</option>
                        {(mstate[p.key]?.images_api ? (mstate[p.key]?.models || []) : [])
                          .filter((m) => m.image && m.id !== 'pollinations-free')
                          .map((m) => <option key={m.id} value={m.id}>🖼 {m.id}</option>)}
                      </select>
                      <span className={`p-status ${
                        mstate[p.key]?.status === 'checking' ? 'busy'
                          : mstate[p.key]?.status === 'ok' ? 'good'
                          : mstate[p.key]?.status === 'error' ? 'bad' : ''}`}>
                        {mstate[p.key]?.status === 'checking' && '⏳ checking key…'}
                        {mstate[p.key]?.status === 'ok' &&
                          `✓ key valid · ${mstate[p.key].free_count || mstate[p.key].models?.length || 0} free model(s)`}
                        {mstate[p.key]?.status === 'error' &&
                          `✗ ${mstate[p.key].error || 'key check failed'}`}
                        {!mstate[p.key]?.status &&
                          (p.token_set || p.key === 'ollama'
                            ? 'stored key — verifying…'
                            : 'enter API key → models load automatically')}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="form-grid" style={{ marginTop: 16 }}>
                <label className="check">
                  <input type="checkbox" checked={s.auto_approve === '1'}
                    onChange={(e) => setS({ ...s, auto_approve: e.target.checked ? '1' : '0' })} />
                  {t('autoApprove')}
                </label>
                <div className="btn-row">
                  <button className="btn primary" onClick={saveProvider}>{t('save')}</button>
                </div>
                <div className="dim" style={{ gridColumn: '1 / -1' }}>
                  Models and the image model are selected automatically the moment
                  a key validates — switching providers re-selects both.
                </div>
              </div>
            </div>
          )}

          {tab === 'brand' && (
            <div className="form-grid">
              <label>Brand name
                <input value={brand.name || ''} onChange={(e) => setBrand({ ...brand, name: e.target.value })} />
              </label>
              <label>{t('logo')}
                <input type="file" accept="image/*" onChange={(e) => e.target.files[0] && uploadLogo(e.target.files[0])} />
                {brand.logo_url && <img className="logo-preview" src={brand.logo_url} alt="" />}
              </label>
              <label>{t('colors')} (comma separated hex)
                <input value={(brand.colors || []).join(', ')}
                  onChange={(e) => setBrand({ ...brand, colors: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} />
              </label>
              <div className="swatches">
                {(brand.colors || []).map((c) => (
                  <span key={c} className="swatch" style={{ background: c }} title={c} />
                ))}
              </div>
              <label>{t('fonts')}
                <input value={(brand.fonts || []).join(', ')}
                  onChange={(e) => setBrand({ ...brand, fonts: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} />
              </label>
              <label>{t('tone')}
                <input value={brand.tone || ''} onChange={(e) => setBrand({ ...brand, tone: e.target.value })} />
              </label>
              <label>{t('rules')} (one per line)
                <textarea rows={4} value={(brand.rules || []).join('\n')}
                  onChange={(e) => setBrand({ ...brand, rules: e.target.value.split('\n').filter(Boolean) })} />
              </label>
              <div className="btn-row"><button className="btn primary" onClick={saveBrand}>{t('save')}</button></div>
            </div>
          )}

          {tab === 'agents' && (
            <div>
              <div className="btn-row">
                <button className="btn primary" onClick={() => setEditing({
                  name: '', role: '', personality: '', system_prompt: '', skills: [],
                  color: '#2dd4bf', strictness: 3, avatar: { hair: '#333', shirt: '#2dd4bf', skin: '#e8b88a', acc: '#fff' },
                })}>+ {t('addAgent')}</button>
              </div>
              <div className="agent-list">
                {agents.map((a) => (
                  <div key={a.id} className="agent-row">
                    <span className="dot" style={{ background: a.color }} />
                    <b>{a.name}</b> <span className="dim">{a.role}</span>
                    <span className="chip">L{a.level}</span>
                    <span className="spacer" />
                    <button className="btn ghost" onClick={() => setEditing(a)}>✏️</button>
                    {a.custom === 1 && <button className="btn bad" onClick={() => fireAgent(a.id)}>🗑</button>}
                  </div>
                ))}
              </div>

              {editing && (
                <div className="agent-editor">
                  <h3>{editing.id ? 'Edit' : t('addAgent')}</h3>
                  <div className="form-grid">
                    <label>Name <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></label>
                    <label>Role <input value={editing.role} onChange={(e) => setEditing({ ...editing, role: e.target.value })} /></label>
                    <label>Color <input type="color" value={editing.color} onChange={(e) => setEditing({ ...editing, color: e.target.value })} /></label>
                    <label>Strictness 1–5
                      <input type="range" min="1" max="5" value={editing.strictness}
                        onChange={(e) => setEditing({ ...editing, strictness: Number(e.target.value) })} />
                    </label>
                    <label>Personality
                      <input value={editing.personality} onChange={(e) => setEditing({ ...editing, personality: e.target.value })} />
                    </label>
                    <label>Skills (comma separated)
                      <input value={(editing.skills || []).join(', ')}
                        onChange={(e) => setEditing({ ...editing, skills: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} />
                    </label>
                    <label className="full">System prompt
                      <textarea rows={7} value={editing.system_prompt}
                        onChange={(e) => setEditing({ ...editing, system_prompt: e.target.value })} />
                    </label>
                  </div>
                  <div className="btn-row">
                    <button className="btn primary" onClick={saveAgent}>{t('save')}</button>
                    <button className="btn" onClick={() => setEditing(null)}>{t('close')}</button>
                  </div>
                </div>
              )}
            </div>
          )}

          {tab === 'prompts' && (
            <div>
              <div className="btn-row"><button className="btn primary" onClick={savePrompt}>+ New prompt</button></div>
              {prompts.map((p) => (
                <div key={p.id} className="prompt-row">
                  <span className="chip">{p.category}</span>
                  <b>{p.name}</b>
                  <div className="dim">{p.content.slice(0, 140)}…</div>
                  <button className="btn bad" onClick={async () => {
                    await api.deletePrompt(p.id); setPrompts(await api.prompts())
                  }}>🗑</button>
                </div>
              ))}
            </div>
          )}

          {tab === 'sched' && (
            <div>
              {schedules.map((sch) => (
                <div key={sch.id} className="agent-row">
                  <b>{sch.name}</b>
                  <span className="chip">every {Math.round(sch.interval_hours / 24)}d</span>
                  <span className={`chip ${sch.enabled ? 'good' : ''}`}>{sch.enabled ? 'ON' : 'off'}</span>
                  <span className="spacer" />
                  <label className="check">
                    <input type="checkbox" checked={sch.enabled} onChange={() => toggleSchedule(sch)} />
                    enabled
                  </label>
                </div>
              ))}
              <div className="dim">Recurring jobs fire in the background and message Nora.</div>
            </div>
          )}

          {tab === 'ui' && (
            <div className="form-grid">
              <label>{t('language')}
                <select value={s.language || lang} onChange={(e) => { setLang(e.target.value); setS({ ...s, language: e.target.value }) }}>
                  <option value="en">English</option>
                  <option value="fr">Français</option>
                  <option value="ar">العربية</option>
                </select>
              </label>
              <label>Theme
                <select value={s.day_night || 'day'} onChange={(e) => setS({ ...s, day_night: e.target.value })}>
                  <option value="day">{t('day')}</option>
                  <option value="night">{t('night')}</option>
                </select>
              </label>
              <label>Sound
                <select value={s.sound || 'on'} onChange={(e) => setS({ ...s, sound: e.target.value })}>
                  <option value="on">on</option><option value="off">off</option>
                </select>
              </label>
              <label>Animation speed ×{s.speed || 1}
                <input type="range" min="0.25" max="3" step="0.25" value={s.speed || 1}
                  onChange={(e) => setS({ ...s, speed: Number(e.target.value) })} />
              </label>
              <div className="btn-row"><button className="btn primary" onClick={saveProvider}>{t('save')}</button></div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
