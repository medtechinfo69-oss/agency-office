/* Deterministic, non-destructive UI regression checks. No real API writes or AI calls.
 * Run with a Vite server on :5173 and Playwright installed:
 *   node frontend/tests/ui-review.cjs
 * Optional: UI_URL, CHROMIUM_PATH, CHROMIUM_ARGS (JSON), UI_SCREENSHOTS (directory).
 * Set UI_AXE=1 with axe-core installed to assert light/dark WCAG A/AA scans.
 */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')

const agents = [
  { id: 'nora', name: 'Nora', role: 'Manager / Director', color: '#4f46e5', status: 'thinking', skills: ['planning', 'strategy'], personality: 'Plans the work and keeps everyone aligned.', level: 4, xp: 345, memory: [], tokens_in: 1200, tokens_out: 400, custom: {} },
  { id: 'karim', name: 'Karim', role: 'Copywriter', color: '#0d9488', status: 'working', skills: ['copywriting', 'social'], personality: 'Writes clear, effective campaigns.', level: 2, xp: 120, memory: [], custom: {} },
]
const tasks = ['todo', 'progress', 'review', 'done', 'blocked'].map((status, i) => ({ id: `t${i}`, title: ['Plan the launch', 'Draft campaign copy', 'Review visual direction', 'Research the audience', 'Resolve missing assets'][i], status, assignee: i % 2 ? 'karim' : 'nora', updated_at: 1795680000, depends: '[]' }))
const project = { id: 'p1', name: 'Summer campaign', status: 'running', progress: 42, tasks, brief: 'Build a campaign', cost_usd: .24 }
const provider = { key: 'openrouter', label: 'OpenRouter', base_url: 'https://openrouter.ai/api/v1', active: true, token_set: false, model: 'example-model', free: true }
const site = { id: 's1', name: 'Studio website', brief: 'An accessible agency website', files: { 'index.html': '<html><head><title>Studio</title></head><body><h1>Studio website</h1></body></html>', 'styles.css': '', 'script.js': '' }, messages: [], updated: 1795680000 }

async function main() {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || undefined, args: JSON.parse(process.env.CHROMIUM_ARGS || '[]') })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  let failShop = false, failWorkflows = false, deleted = 0
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace('/api', '')
    let data = []
    if (failShop && path.startsWith('/agents/') && route.request().method() === 'PUT') return route.fulfill({ status: 500, json: { detail: 'Test save failure' } })
    if (failWorkflows && path.endsWith('/schedules')) return route.fulfill({ status: 500, json: { detail: 'Test workflow failure' } })
    if (path === '/auth/session') data = { required: false, authenticated: true }
    else if (path === '/auth/ws-ticket') data = { ticket: null }
    else if (path === '/settings') data = { language: 'en', day_night: 'day', sound: 'off', speed: 1 }
    else if (path === '/health') data = { ok: true, demo: false, provider_label: 'OpenRouter', model: 'example-model' }
    else if (path === '/projects') data = [project]
    else if (path === '/projects/p1') data = project
    else if (path === '/agents') data = agents
    else if (path.startsWith('/agents/')) data = agents[0]
    else if (path === '/providers') data = [provider]
    else if (path.endsWith('/schedules')) data = [{ id: 'w1', name: 'Weekly campaign report', enabled: true, kind: 'report', interval_hours: 168, created_at: 1795680000 }]
    else if (path.endsWith('/activity')) data = [{ level: 'success', text: 'Campaign brief approved. The team is working.', created_at: 1795680000 }]
    else if (path.endsWith('/messages')) data = [{ id: 'm1', channel: 'agent', agent_id: 'nora', text: 'The campaign plan is ready. I will coordinate the team.', created_at: 1795680000 }]
    else if (path.endsWith('/brand')) data = { name: 'Studio', colors: ['#4f46e5'], fonts: [], rules: [] }
    else if (path.endsWith('/meta/drafts')) data = { drafts: [], configured: false }
    else if (path === '/prompts') data = [{ id: 'prompt1', name: 'Campaign prompt', category: 'custom', content: 'Write a campaign brief.' }]
    else if (path === '/prompts/prompt1' && route.request().method() === 'DELETE') { deleted++; data = { ok: true } }
    else if (path === '/templates') data = [{ id: 'campaign', name: 'Campaign' }]
    else if (path === '/sitebuilder/projects') data = [site]
    else if (path === '/sitebuilder/projects/s1') data = site
    else if (path === '/sitebuilder/ollama/models') data = { online: false, models: [], active: '' }
    else if (path === '/sitebuilder/settings') data = { provider: 'ollama', model: '', providers: [] }
    await route.fulfill({ json: data })
  })
  if (page.routeWebSocket) await page.routeWebSocket('**/ws', (ws) => ws.close())
  await page.goto(process.env.UI_URL || 'http://localhost:5173')
  await page.getByRole('heading', { name: project.name, exact: true }).waitFor()
  await page.getByText('Loading your workspace…').waitFor({ state: 'hidden' })

  async function navigate(name) {
    const menu = page.getByRole('button', { name: 'Menu', exact: true })
    if (await menu.isVisible()) await menu.click()
    await page.locator('.side-nav').getByRole('button', { name, exact: true }).click()
    await page.waitForTimeout(100)
  }
  async function noOverflow(label) {
    const sizes = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, viewport: innerWidth }))
    assert(sizes.content <= sizes.viewport + 1, `${label}: page overflows ${sizes.content} > ${sizes.viewport}`)
  }
  const accessibility = []
  const nav = ['Office', 'Site Builder', 'Chat', 'Workflows', 'Projects', 'Permissions', 'Logs', 'Skills', 'System health', 'Shop', 'Settings']
  for (const width of [1440, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const name of nav) {
      await navigate(name)
      await noOverflow(`${width}px ${name}`)
      if (process.env.UI_AXE && width === 1440) {
        await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
        const result = await page.evaluate(async () => (await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations.map(({ id, impact, nodes }) => ({ id, impact, nodes: nodes.map(({ target, failureSummary }) => ({ target, failureSummary })) })))
        if (result.length) accessibility.push({ page: name, violations: result })
      }
      if (name === 'Settings') {
        for (const tab of ['Diagnostics', 'Runtimes & agents', 'Access', 'Instance', 'Appearance', 'Account', 'Users', 'Roles & permissions', 'Connections']) {
          await page.getByRole('tab', { name: tab, exact: true }).click()
          await noOverflow(`${width}px Settings / ${tab}`)
        }
        for (const tab of ['Brand kit', 'Agent editor', 'Prompt library', 'Scheduled tasks', 'UI', 'Providers']) {
          const button = page.locator('.settings-tabs button').filter({ hasText: tab })
          if (await button.count()) { await button.click(); await noOverflow(`${width}px Connections / ${tab}`) }
        }
      }
      if (process.env.UI_SCREENSHOTS && ['Office', 'Projects', 'Site Builder', 'Settings'].includes(name)) {
        fs.mkdirSync(process.env.UI_SCREENSHOTS, { recursive: true })
        await page.screenshot({ path: `${process.env.UI_SCREENSHOTS}/${width}-${name.replaceAll(' ', '-')}.png`, fullPage: true })
      }
    }
    console.log(`PASS: all 11 pages and settings sections at ${width}px`)
  }
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    await navigate('Site Builder')
    const trigger = page.getByRole('button', { name: 'Builder model settings' })
    await trigger.click()
    await page.getByRole('dialog', { name: 'Studio settings' }).waitFor()
    await page.waitForTimeout(350) // Let the studio's entry animation finish before contrast checks.
    await noOverflow(`${width}px Studio settings dialog`)
    if (process.env.UI_AXE) {
      const result = await page.evaluate(async () => (await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations.map(({ id, impact, nodes }) => ({ id, impact, nodes: nodes.map(({ target, failureSummary }) => ({ target, failureSummary })) })))
      if (result.length) accessibility.push({ page: `Studio settings (${width}px)`, violations: result })
    }
    await page.keyboard.press('Escape')
    assert.equal(await page.getByRole('dialog').count(), 0)
    assert(await trigger.evaluate((el) => document.activeElement === el))
  }
  console.log('PASS: studio dialog responsiveness, Escape and focus return')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await navigate('Projects')
  const newButton = page.getByRole('button', { name: 'New project', exact: true })
  await newButton.click()
  const dialog = page.getByRole('dialog')
  await dialog.waitFor()
  await page.getByPlaceholder('e.g. Summer campaign').fill('New campaign')
  const close = dialog.getByRole('button', { name: 'Close', exact: true })
  await close.focus()
  await page.keyboard.press('Tab')
  assert(await page.evaluate(() => !!document.activeElement.closest('[role=dialog]')), 'Focus must stay inside modal')
  await page.keyboard.press('Escape')
  assert.equal(await page.getByRole('dialog').count(), 0)
  assert(await newButton.evaluate((el) => document.activeElement === el), 'Focus returns to trigger')
  await page.getByRole('textbox', { name: 'Search tasks' }).fill('no matching task')
  assert.equal(await page.locator('.kanban-card').count(), 0)
  await page.getByRole('textbox', { name: 'Search tasks' }).fill('')
  await page.locator('.kanban-card[role=button]').first().focus()
  await page.keyboard.press('Enter')
  await page.getByRole('dialog', { name: /details/ }).waitFor()
  await page.keyboard.press('Escape')
  console.log('PASS: keyboard task activation, dialog focus containment, Escape, focus return, search')

  await navigate('Chat')
  await page.getByRole('button', { name: /Analytics/ }).click()
  await page.getByRole('dialog').waitFor()
  assert(await page.getByLabel('Campaign name', { exact: false }).count())
  await page.getByLabel('Campaign name', { exact: false }).fill('Campaign')
  const reach = page.getByLabel('Reach', { exact: true })
  await reach.fill('-1')
  assert.equal(await reach.evaluate((el) => el.validity.valid), false)
  await page.keyboard.press('Escape')
  console.log('PASS: persistent analytics labels and negative-number validation')

  await navigate('Shop')
  failShop = true
  await page.locator('.shop-item').nth(1).click()
  await page.getByRole('button', { name: 'Apply', exact: true }).click()
  await page.getByRole('alert').filter({ hasText: 'Could not save' }).waitFor()
  assert(await page.getByRole('button', { name: 'Undo', exact: true }).isDisabled(), 'Failed save must not enter undo history')
  console.log('PASS: failed shop save is visible and does not corrupt undo history')

  failWorkflows = true
  await navigate('Workflows')
  await page.getByRole('alert').filter({ hasText: 'Could not load workflows' }).waitFor()
  failWorkflows = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await page.getByRole('heading', { name: 'Weekly campaign report' }).waitFor()
  console.log('PASS: workflow failure and retry')

  await navigate('Settings')
  await page.locator('.settings-tabs button').filter({ hasText: 'Prompt' }).click()
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: 'Delete prompt Campaign prompt' }).click()
  assert.equal(deleted, 0)
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Delete prompt Campaign prompt' }).click()
  await page.waitForTimeout(100)
  assert.equal(deleted, 1)
  await page.locator('.theme-seg button[title=Night]').click()
  assert(await page.locator('html.theme-dark').count())
  await noOverflow('Dark theme')
  if (process.env.UI_AXE) {
    for (const name of nav) {
      await navigate(name)
      const result = await page.evaluate(async () => (await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations.map(({ id, impact, nodes }) => ({ id, impact, nodes: nodes.map(({ target, failureSummary }) => ({ target, failureSummary })) })))
      if (result.length) accessibility.push({ page: `${name} (dark)`, violations: result })
    }
  }
  await page.locator('.theme-seg button[title=Day]').click()
  console.log('PASS: delete confirmation and light/dark theme')
  if (process.env.UI_AXE) {
    fs.writeFileSync(process.env.UI_AXE_REPORT || '/tmp/agency-accessibility.json', JSON.stringify(accessibility, null, 2))
    console.log(`Accessibility scan: ${accessibility.length} pages with findings; see UI_AXE_REPORT`)
    assert.deepEqual(accessibility, [], 'Automated accessibility findings; see UI_AXE_REPORT')
  }
  assert.deepEqual(errors, [], `JavaScript errors: ${errors.join('; ')}`)
  await browser.close()
  console.log('PASS: no browser JavaScript errors')
}
main().catch((error) => { console.error(error); process.exit(1) })
