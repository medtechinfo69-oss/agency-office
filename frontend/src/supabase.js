import { createClient } from '@supabase/supabase-js'

// Only public configuration belongs here. Never supply a service-role/secret key.
export function supabaseConfig(env = {}) {
  const url = (env.VITE_SUPABASE_URL || '').trim()
  const key = (env.VITE_SUPABASE_PUBLISHABLE_KEY || '').trim()
  if (!url && !key) return null
  if (!url || !key) throw new Error('Supabase needs both its project URL and publishable key.')
  let parsed
  try { parsed = new URL(url) } catch { throw new Error('Supabase needs a valid HTTPS project origin.') }
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password ||
      parsed.pathname !== '/' || parsed.search || parsed.hash) {
    throw new Error('Supabase needs a valid HTTPS project origin.')
  }
  if (!/^sb_publishable_[A-Za-z0-9_-]+$/.test(key)) {
    throw new Error('Use a Supabase publishable key, never a secret or service-role key.')
  }
  return { url: parsed.origin, key }
}

let client
export function getSupabase() {
  if (client) return client
  const config = supabaseConfig(import.meta.env || {})
  if (!config) return null
  client = createClient(config.url, config.key, {
    // Staged integration: no browser token persistence or implicit URL login.
    // A tested auth flow must be implemented before switching the app to Supabase.
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
  })
  return client
}

export async function checkSupabaseConnection(connection, signal) {
  const { data, error } = await connection.rpc('agency_connection_status').abortSignal(signal)
  if (error) throw new Error('Supabase connection could not be verified. Check its public settings or project status.')
  if (data?.service !== 'agency-office' || data?.schema_version !== 1) {
    throw new Error('The Agency Office Supabase schema is not ready.')
  }
  return data
}
