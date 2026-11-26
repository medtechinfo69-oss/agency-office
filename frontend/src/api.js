import { authFetch } from './auth'
/* Minimal API client — all requests go through the Vite proxy (/api). */
const BASE = '/api'

async function req(method, path, body) {
  const opts = { method, headers: {} }
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  let res
  try {
    res = await authFetch(BASE + path, opts)
  } catch (e) {
    throw new Error('Cannot reach the agency backend. Check the connection and backend deployment, then retry.')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = j.detail || JSON.stringify(j)
    } catch { /* keep statusText */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return res.json()
  return res
}

export const api = {
  get: (p) => req('GET', p),
  post: (p, b) => req('POST', p, b ?? {}),
  put: (p, b) => req('PUT', p, b ?? {}),
  patch: (p, b) => req('PATCH', p, b ?? {}),
  del: (p) => req('DELETE', p),

  health: () => req('GET', '/health'),
  settings: () => req('GET', '/settings'),
  saveSettings: (b) => req('PUT', '/settings', b),

  providers: () => req('GET', '/providers'),
  saveProvider: (b) => req('PUT', '/providers', b),
  activateProvider: (key) => req('POST', '/providers/activate', { provider: key }),
  providerModels: (key, body) => req('POST', `/providers/${key}/models`, body || {}),

  projects: () => req('GET', '/projects'),
  createProject: (b) => req('POST', '/projects', b),
  project: (id) => req('GET', `/projects/${id}`),
  chat: (id, text) => req('POST', `/projects/${id}/chat`, { text }),
  messages: (id) => req('GET', `/projects/${id}/messages`),
  activity: (id) => req('GET', `/projects/${id}/activity`),
  control: (id, action) => req('POST', `/projects/${id}/control`, { action }),
  approve: (id, kind, approved, comment = '') =>
    req('POST', `/projects/${id}/approve`, { kind, approved, comment }),

  agents: () => req('GET', '/agents'),
  saveAgent: (b, id) => (id ? req('PUT', `/agents/${id}`, b) : req('POST', '/agents', b)),
  deleteAgent: (id) => req('DELETE', `/agents/${id}`),

  brand: (id) => req('GET', `/projects/${id}/brand`),
  saveBrand: (id, b) => req('PUT', `/projects/${id}/brand`, b),

  deliverables: (id) => req('GET', `/projects/${id}/deliverables`),
  versions: (did) => req('GET', `/deliverables/${did}/versions`),
  rollback: (did, version) => req('POST', `/deliverables/${did}/rollback`, { version }),
  exportZip: (id) => `${BASE}/projects/${id}/export`,

  campaign: (id, brief = '') => req('POST', `/projects/${id}/campaign`, { brief_override: brief }),
  calendar: (id, days = 30) => req('POST', `/projects/${id}/calendar`, { days }),
  metaDrafts: (id) => req('GET', `/projects/${id}/meta/drafts`),
  publishDraft: (id, draftId) => req('POST', `/projects/${id}/meta/publish`, { draft_id: draftId, approve: true }),

  meeting: (id, topic) => req('POST', `/projects/${id}/meeting`, { topic }),
  meetings: (id) => req('GET', `/projects/${id}/meetings`),
  standup: (id) => req('POST', `/projects/${id}/standup`),
  standups: (id) => req('GET', `/projects/${id}/standups`),

  trends: (id, query = '') => req('POST', `/projects/${id}/trends`, { query }),
  analytics: (id) => req('GET', `/projects/${id}/analytics`),
  addAnalytics: (id, b) => req('POST', `/projects/${id}/analytics`, b),
  insight: (id) => req('POST', `/projects/${id}/analytics/insight`),

  schedules: (id) => req('GET', `/projects/${id}/schedules`),
  addSchedule: (id, b) => req('POST', `/projects/${id}/schedules`, b),
  patchSchedule: (sid, b) => req('PATCH', `/schedules/${sid}`, b),

  templates: () => req('GET', '/templates'),
  prompts: () => req('GET', '/prompts'),
  savePrompt: (b) => req('POST', '/prompts', b),
  deletePrompt: (id) => req('DELETE', `/prompts/${id}`),

  memory: (id) => req('GET', `/projects/${id}/memory`),
  makeImage: (id, b) => req('POST', `/projects/${id}/images`, b),

  async uploadLogo(pid, file) {
    const fd = new FormData()
    fd.append('file', file)
    const res = await authFetch(`${BASE}/projects/${pid}/brand/logo`, { method: 'POST', body: fd })
    if (!res.ok) throw new Error('logo upload failed')
    return res.json()
  },
}
