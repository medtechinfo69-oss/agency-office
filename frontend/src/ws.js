/* WebSocket client with auto-reconnect + event history replay handling. */
export function connectWS(onEvent, onOpen, onClose) {
  let ws = null
  let closed = false
  let retry = 0

  function url() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    return `${proto}://${location.host}/ws`
  }

  function open() {
    if (closed) return
    try {
      ws = new WebSocket(url())
    } catch {
      schedule()
      return
    }
    ws.onopen = () => { retry = 0; onOpen && onOpen() }
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'history' && msg.event) onEvent(msg.event)
        else onEvent(msg)
      } catch { /* ignore malformed */ }
    }
    ws.onclose = () => { onClose && onClose(); if (!closed) schedule() }
    ws.onerror = () => { try { ws.close() } catch { /* ignore */ } }
  }

  function schedule() {
    const delay = Math.min(500 * 2 ** retry, 8000)
    retry += 1
    setTimeout(open, delay)
  }

  open()
  return () => {
    closed = true
    try { ws && ws.close() } catch { /* ignore */ }
  }
}
