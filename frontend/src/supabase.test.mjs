import test from 'node:test'
import assert from 'node:assert/strict'
import { supabaseConfig, checkSupabaseConnection } from './supabase.js'

const config = {
  VITE_SUPABASE_URL: 'https://example.supabase.co',
  VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_test_only',
}

test('Supabase is opt-in and requires complete public configuration', () => {
  assert.equal(supabaseConfig(), null)
  assert.deepEqual(supabaseConfig(config), { url: config.VITE_SUPABASE_URL, key: config.VITE_SUPABASE_PUBLISHABLE_KEY })
  assert.throws(() => supabaseConfig({ VITE_SUPABASE_URL: config.VITE_SUPABASE_URL }), /both/)
})

test('rejects unsafe origins and non-publishable keys without echoing them', () => {
  for (const url of ['http://example.com', 'https://user:password@example.com', 'https://example.com/path', 'https://example.com/?token=value', 'broken']) {
    assert.throws(() => supabaseConfig({ ...config, VITE_SUPABASE_URL: url }), /HTTPS project origin/)
  }
  for (const key of ['sb_secret_do_not_expose', 'service_role', 'eyJhbGciOiJIUzI1NiJ9']) {
    assert.throws(() => supabaseConfig({ ...config, VITE_SUPABASE_PUBLISHABLE_KEY: key }), error => {
      assert.ok(!error.message.includes(key))
      return /publishable key/.test(error.message)
    })
  }
})

function connection(result) {
  return { rpc(name) {
    assert.equal(name, 'agency_connection_status')
    return { async abortSignal(signal) { assert.ok(signal); return result } }
  } }
}

test('validates readiness version, not merely an HTTP response', async () => {
  const signal = new AbortController().signal
  const data = { service: 'agency-office', schema_version: 1 }
  assert.deepEqual(await checkSupabaseConnection(connection({ data }), signal), data)
  await assert.rejects(checkSupabaseConnection(connection({ data: {} }), signal), /schema is not ready/)
  await assert.rejects(checkSupabaseConnection(connection({ error: { message: 'sensitive upstream details' } }), signal), /could not be verified/)
})
