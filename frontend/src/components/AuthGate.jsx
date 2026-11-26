import { lazy, Suspense, useEffect, useState } from 'react'
import { Building2, LockKeyhole, RefreshCw } from 'lucide-react'
import SaaSEntry from './SaaSEntry'

const SupabaseStatus = lazy(() => import('./SupabaseStatus'))

export default function AuthGate() {
  const [session, setSession] = useState(null)
  const [error, setError] = useState('')
  const [email, setEmail] = useState('')
  const [invitation, setInvitation] = useState(() => {
    if (!location.hash.startsWith('#invite=')) return null
    return location.hash.slice(8)
  })
  const [inviteDone, setInviteDone] = useState(false)
  const [password, setPassword] = useState('')
  const [otp, setOtp] = useState('')
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(0)

  useEffect(() => { if (invitation) history.replaceState(null, '', location.pathname) }, [invitation])

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
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password, email, otp }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Sign-in failed. Try again.')
      setPassword(''); setOtp(''); setSession({ required: true, authenticated: true })
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const logout = async () => {
    const response = await fetch('/api/auth/logout', { method: 'POST' })
    if (response.ok || response.status === 401) {
      setSession({ required: true, authenticated: false }); setPassword(''); setError('')
    } else { window.alert('Could not sign out. Please try again.') }
  }

  if (invitation) return <main className="auth-screen"><section className="auth-card card"><span className="eyebrow">Agency Office</span><h1>Join your workspace</h1><p className="muted">Create a password to accept your single-use invitation.</p><form className="auth-form" onSubmit={async (event) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const response = await fetch('/api/auth/invite/accept', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: invitation, password }) })
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Invitation could not be accepted.')
      setInvitation(null); setInviteDone(true); setPassword('')
    } catch (error) { setError(error.message) } finally { setBusy(false) }
  }}><label className="field">New password<input type="password" autoComplete="new-password" required minLength={16} value={password} onChange={(e) => setPassword(e.target.value)} /></label><p className="field-help">Use at least 16 characters.</p>{error && <div role="alert" className="feedback-banner error">{error}</div>}<button className="btn primary" disabled={busy || password.length < 16}>{busy ? 'Accepting…' : 'Accept invitation'}</button></form></section></main>

  if (session?.authenticated) return <SaaSEntry onLogout={session.required ? logout : undefined} />

  return <main className="auth-screen">
    <section className="auth-card card" aria-labelledby="auth-title">
      <span className="side-logo-mark" aria-hidden="true"><Building2 size={24} /></span>
      <span className="eyebrow">Agency Office</span>
      <h1 id="auth-title">{session ? 'Welcome back' : error ? 'Backend not connected' : 'Opening your agency…'}</h1>
      <p className="muted">{session ? 'Sign in to your private workspace to manage projects, agents, and AI providers.' : 'Your workspace needs a connection to its persistent backend.'}</p>
      {error && <div className="feedback-banner error" role="alert">{error}</div>}
      {!session && error && <Suspense fallback={null}><SupabaseStatus key={retry} /></Suspense>}
      {inviteDone && <p role="status">Invitation accepted. Sign in using your email and new password.</p>}
      {session ? <form onSubmit={login} className="auth-form" aria-busy={busy}>
        <label className="field">Email (invited members only)
          <input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Owner: leave this blank" />
        </label>
        <label className="field" htmlFor="owner-password">Workspace password
          <input id="owner-password" type="password" autoComplete="current-password" required autoFocus value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        <label className="field">Authenticator or recovery code (if enabled)<input autoComplete="one-time-code" value={otp} maxLength={100} onChange={e => setOtp(e.target.value)} /></label>
        <button className="btn primary" type="submit" disabled={busy || !password} aria-busy={busy}><LockKeyhole size={16} />{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="field-help">Owner: use your existing workspace password. Invited members: enter your email and personal password.</p>
      </form> : error ? <button className="btn" onClick={() => setRetry((n) => n + 1)}><RefreshCw size={16} /> Retry connection</button>
        : <div className="feedback-banner" role="status"><span className="loading-dot" /> Connecting securely…</div>}
    </section>
  </main>
}
