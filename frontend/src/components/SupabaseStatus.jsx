import { useEffect, useState } from 'react'
import { checkSupabaseConnection, getSupabase } from '../supabase'

// Read-only diagnostic. A healthy database must not bypass the legacy API gate.
export default function SupabaseStatus() {
  const [status, setStatus] = useState(null)
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 10000)
    async function check() {
      try {
        const connection = getSupabase()
        if (!connection) return
        setStatus({ message: 'Checking the Supabase connection…' })
        await checkSupabaseConnection(connection, controller.signal)
        if (active) setStatus({ ready: true })
      } catch (error) {
        if (active) setStatus({ message: controller.signal.aborted
          ? 'Supabase connection check timed out. Retry to check again.'
          : error.message })
      } finally {
        clearTimeout(timeout)
      }
    }
    check()
    return () => { active = false; clearTimeout(timeout); controller.abort() }
  }, [])
  if (!status) return null
  return <div className="feedback-banner" role="status">
    {status.ready
      ? 'Supabase connection verified. The workspace API migration is still pending; Supabase is not yet replacing the Python backend.'
      : status.message}
  </div>
}
