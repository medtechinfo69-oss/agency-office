import { authFetch } from './auth'

// Vercel cannot host the existing WebSocket server. Events and orchestration
// checkpoints live in Postgres; this client advances one bounded job per tab.
export function connectPoll(onEvent, onOpen, onClose) {
  let closed = false, cursor = 0, connected = false, timer = null, advancing = false
  const controller = new AbortController()

  async function poll() {
    try {
      const response = await authFetch(`/api/events?after=${cursor}`, { cache: 'no-store', signal: controller.signal })
      if (!response.ok) throw new Error('Events unavailable')
      const data = await response.json()
      if (closed) return
      if (!connected) { connected = true; onOpen?.() }
      for (const event of data.events || []) onEvent(event)
      cursor = data.cursor ?? cursor
      if (!advancing && data.work?.length) {
        advancing = true
        // Keep polling live events while the bounded step request is in flight.
        authFetch('/api/jobs/advance', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_id: data.work[0] }), signal: controller.signal,
        }).catch(() => { if (!closed) { connected = false; onClose?.() } })
          .finally(() => { advancing = false })
      }
    } catch {
      if (!closed && connected) { connected = false; onClose?.() }
    } finally {
      if (!closed) timer = setTimeout(poll, connected ? 2500 : 5000)
    }
  }
  poll()
  return () => { closed = true; clearTimeout(timer); controller.abort() }
}
