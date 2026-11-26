/* Run against Vite with dummy VITE_SUPABASE_URL=https://example.supabase.co
 * and VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_test_only. All APIs mocked. */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')

async function main() {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: JSON.parse(process.env.CHROMIUM_ARGS || '[]') })
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    let outcome = 'ready', rpcCalls = 0, privateReads = 0
    await page.route('**/api/**', route => {
      if (new URL(route.request().url()).pathname !== '/api/auth/session') privateReads++
      return route.fulfill({ status: 503, json: { detail: 'Backend offline' } })
    })
    await page.route('https://example.supabase.co/**', route => {
      assert.equal(new URL(route.request().url()).pathname, '/rest/v1/rpc/agency_connection_status')
      assert.equal(route.request().headers().apikey, 'sb_publishable_test_only')
      rpcCalls++
      return outcome === 'ready'
        ? route.fulfill({ json: { service: 'agency-office', schema_version: 1 } })
        : route.fulfill({ status: 401, json: { message: 'Invalid API key' } })
    })
    await page.goto(process.env.UI_URL || 'http://localhost:5174')
    await page.getByText('The public Supabase connection is available,', { exact: false }).waitFor()
    assert.equal(await page.locator('.workspace').count(), 0, 'Readiness must not bypass authentication/API gate')
    assert.equal(privateReads, 0)
    assert.ok(rpcCalls > 0)
    const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))
    assert.ok(!storage.includes('sb-') && !storage.includes('test_only'))
    outcome = 'invalid'
    await page.getByRole('button', { name: 'Retry connection' }).click()
    await page.getByText('Supabase connection could not be verified.', { exact: false }).waitFor()
    assert.equal(await page.locator('.workspace').count(), 0)
    assert.deepEqual(errors, [])
    console.log('PASS: Supabase readiness, public key header, rejected key, no auth bypass/private reads/browser credentials')
  } finally { await browser.close() }
}
main().catch(error => { console.error(error); process.exit(1) })
