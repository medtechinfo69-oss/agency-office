import { lazy, Suspense, useEffect, useState } from 'react'
import { Building2, LockKeyhole, RefreshCw } from 'lucide-react'
import App from '../App'

const SupabaseStatus = lazy(() => import('./SupabaseStatus'))

export default function AuthGate() {
  const [session, setSession] = useState(null)
  const [error, setError] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let active = true
    setSession(null); setError('')
    fetch('/api/auth/session', { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw new Error('Backend unavailable')
        const data = await response.json()
        if (typeof data.required !== 'boolean') throw new Error('Backend setup is incomplete')
        if (active) setSession(data)
      })
      .catch(() => { if (active) setError('Cannot connect to the agency backend. Check the hosting configuration and try again.') })
    const expired = () => { setSession((previous) => previous?.required ? { required: true, authenticated: false } : previous); setError('Your session expired. Please sign in again.') }
    window.addEventListener('agency-auth-expired', expired)
    return () => { active = false; window.removeEventListener('agency-auth-expired', expired) }
  }, [retry])

  const login = async (event) => {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError('')
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Sign-in failed. Try again.')
      setPassword(''); setSession({ required: true, authenticated: true })
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const logout = async () => {
    const response = await fetch('/api/auth/logout', { method: 'POST' })
    if (response.ok || response.status === 401) {
      setSession({ required: true, authenticated: false }); setPassword(''); setError('')
    } else { window.alert('Could not sign out. Please try again.') }
  }

  if (session?.authenticated) return <App onLogout={session.required ? logout : undefined} />

  return <main className="auth-screen">
    <section className="auth-card card" aria-labelledby="auth-title">
      <span className="side-logo-mark" aria-hidden="true"><Building2 size={24} /></span>
      <span className="eyebrow">Agency Office</span>
      <h1 id="auth-title">{session ? 'Welcome back' : error ? 'Backend not connected' : 'Opening your agency…'}</h1>
      <p className="muted">{session ? 'Sign in to your private workspace to manage projects, agents, and AI providers.' : 'Your workspace needs a connection to its persistent backend.'}</p>
      {error && <div className="feedback-banner error" role="alert">{error}</div>}
      {!session && error && <Suspense fallback={null}><SupabaseStatus key={retry} /></Suspense>}
      {session ? <form onSubmit={login} className="auth-form" aria-busy={busy}>
        <label className="field" htmlFor="owner-password">Workspace password
          <input id="owner-password" type="password" autoComplete="current-password" required autoFocus value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        <button className="btn primary" type="submit" disabled={busy || !password} aria-busy={busy}><LockKeyhole size={16} />{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="field-help">Use the ACCESS_PASSWORD configured in your backend host. Never share it in chat.</p>
      </form> : error ? <button className="btn" onClick={() => setRetry((n) => n + 1)}><RefreshCw size={16} /> Retry connection</button>
        : <div className="feedback-banner" role="status"><span className="loading-dot" /> Connecting securely…</div>}
    </section>
  </main>
}
