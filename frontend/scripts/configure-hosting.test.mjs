import test from 'node:test'
import assert from 'node:assert/strict'
import { hostingConfig } from './configure-hosting.mjs'

test('routes HTTP/media through Vercel but uses direct WSS for live events', () => {
  const result = hostingConfig('https://backend.example.com')
  assert.equal(result.websocket, 'wss://backend.example.com/ws')
  assert.deepEqual(result.config.rewrites, [
    { source: '/api/:path*', destination: 'https://backend.example.com/api/:path*' },
    { source: '/media/:path*', destination: 'https://backend.example.com/media/:path*' },
  ])
  assert(!JSON.stringify(result.config).includes('password'))
})

test('rejects insecure, credential-bearing and temporary backend addresses', () => {
  for (const url of ['http://backend.example.com', 'https://user:pass@backend.example.com', 'https://backend.example.com/api', 'https://backend.example.com/?token=secret', 'https://localhost', 'https://5173-sandbox.e2b.app']) {
    assert.throws(() => hostingConfig(url))
  }
})
