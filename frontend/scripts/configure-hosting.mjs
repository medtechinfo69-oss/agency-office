import { writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

export function hostingConfig(input) {
  const backend = new URL(input)
  if (backend.protocol !== 'https:' || backend.username || backend.password || backend.pathname !== '/' || backend.search || backend.hash) {
    throw new Error('Supply only the backend HTTPS origin, without credentials, a path, query or fragment.')
  }
  if (['localhost', '127.0.0.1', '[::1]'].includes(backend.hostname) || backend.hostname.endsWith('.e2b.app')) {
    throw new Error('Use a persistent hosted backend, not localhost or the temporary Arena preview.')
  }
  return {
    backend: backend.origin,
    websocket: backend.origin.replace(/^https:/, 'wss:') + '/ws',
    config: {
      $schema: 'https://openapi.vercel.sh/vercel.json',
      framework: 'vite',
      buildCommand: 'npm run build',
      installCommand: 'npm ci',
      outputDirectory: 'dist',
      rewrites: [
        { source: '/api/:path*', destination: `${backend.origin}/api/:path*` },
        { source: '/media/:path*', destination: `${backend.origin}/media/:path*` },
      ],
      headers: [
        { source: '/api/:path*', headers: [{ key: 'Cache-Control', value: 'no-store' }] },
        { source: '/media/:path*', headers: [{ key: 'Cache-Control', value: 'no-store' }] },
        { source: '/(.*)', headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ] },
      ],
    },
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    const result = hostingConfig(process.argv[2])
    const output = process.argv[3] || fileURLToPath(new URL('../vercel.json', import.meta.url))
    await writeFile(output, JSON.stringify(result.config, null, 2) + '\n')
    console.log(`Wrote ${output}\nSet Vercel VITE_WS_URL=${result.websocket}\nThen rebuild/redeploy Vercel and allow the exact frontend origin on the backend.`)
  } catch (error) {
    console.error(error.message + '\nUsage: node frontend/scripts/configure-hosting.mjs https://YOUR-BACKEND-HOST')
    process.exitCode = 1
  }
}
