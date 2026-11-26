/* Browser checks for the hosted owner sign-in gate. Uses only mocked APIs.
 * Same Playwright/CHROMIUM_PATH/CHROMIUM_ARGS setup as ui-review.cjs. */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')

async function main() {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: JSON.parse(process.env.CHROMIUM_ARGS || '[]') })
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  let signedIn = false, privateReads = 0, offline = false
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace('/api', '')
    if (path === '/auth/session') {
      if (offline) return route.fulfill({ status: 503, json: { detail: 'Offline' } })
      return route.fulfill({ json: { required: true, authenticated: signedIn } })
    }
    if (path === '/auth/login') {
      if (route.request().postDataJSON().password !== 'test-only-password') return route.fulfill({ status: 401, json: { detail: 'Incorrect password. Try again.' } })
      signedIn = true
      return route.fulfill({ json: { authenticated: true } })
    }
    if (path === '/auth/logout') {
      signedIn = false
      return route.fulfill({ status: 204 })
    }
    privateReads++
    assert(signedIn, 'Private API read before authentication')
    const fixtures = { '/health': { ok: true }, '/settings': { language: 'en' }, '/auth/ws-ticket': { ticket: null } }
    return route.fulfill({ json: fixtures[path] || [] })
  })
  if (page.routeWebSocket) await page.routeWebSocket('**/ws', (ws) => ws.close())
  await page.goto(process.env.UI_URL || 'http://localhost:5173')
  await page.getByRole('heading', { name: 'Welcome back' }).waitFor()
  assert.equal(privateReads, 0)
  assert(await page.getByRole('button', { name: 'Sign in', exact: true }).isDisabled())
  await page.getByLabel('Workspace password').fill('wrong')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('alert').filter({ hasText: 'Incorrect password' }).waitFor()
  await page.getByLabel('Workspace password').fill('test-only-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.locator('.workspace').waitFor()
  await page.getByText('Loading your workspace…').waitFor({ state: 'hidden' })
  if (await page.getByRole('dialog').count()) await page.keyboard.press('Escape')
  assert(privateReads > 0)
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))
  assert(!stored.includes('test-only-password'))
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.getByRole('button', { name: 'Log out', exact: true }).click()
  await page.getByRole('heading', { name: 'Welcome back' }).waitFor()
  assert.equal(signedIn, false)
  offline = true
  await page.reload()
  await page.getByRole('heading', { name: 'Backend not connected' }).waitFor()
  offline = false
  await page.getByRole('button', { name: 'Retry connection' }).click()
  await page.getByRole('heading', { name: 'Welcome back' }).waitFor()
  assert.deepEqual(errors, [])
  await browser.close()
  console.log('PASS: sign-in required before private requests, wrong/correct password, no password in storage, logout, unavailable backend and retry')
}
main().catch((error) => { console.error(error); process.exit(1) })
