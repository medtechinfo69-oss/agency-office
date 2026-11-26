/* Read-only layout/a11y sweep against the local isolated test workspace.
 * npm install --prefix /tmp/agency-browser playwright @axe-core/playwright
 * NODE_PATH=/tmp/agency-browser/node_modules LD_LIBRARY_PATH=/tmp/al2023/lib node tests/control-layout.cjs
 */
const {chromium}=require('playwright')
const AxeBuilder=require('@axe-core/playwright').default
const assert=require('node:assert/strict'),fs=require('node:fs')
const BASE=process.env.UI_URL||'http://localhost:5175'
assert.equal(new URL(BASE).hostname,'localhost')
;(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/tmp/chromium',args:['--no-sandbox']})
 const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'})
 const page=await context.newPage(),errors=[],findings=[],checks=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.goto(BASE+'/#settings/diagnostics');await page.getByLabel('Workspace password',{exact:true}).fill('test-owner-password-for-ui-only');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.locator('.a-admin').waitFor()
 for(const theme of ['night','day']){
  await page.evaluate(theme=>{localStorage.setItem('ao_theme',theme);localStorage.removeItem('ao_custom_accent');localStorage.setItem('ao_sidebar_collapsed','false')},theme)
  await page.reload();await page.locator('.a-admin').waitFor()
  for(const width of [1440,1024,768,390]){
   await page.setViewportSize({width,height:1000})
   for(const route of ['builder','settings/diagnostics','settings/runtimes','settings/connections','settings/access','settings/instance','settings/appearance','settings/account','settings/users','settings/roles']){
    await page.goto(BASE+'/#'+route);await page.getByRole('heading',{level:1}).first().waitFor();await page.locator('[aria-label="Loading settings"]').first().waitFor({state:'hidden'});await page.waitForTimeout(150)
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)
    if(overflow)findings.push({theme,width,route,type:'overflow',size:await page.evaluate(()=>document.documentElement.scrollWidth)})
    const scan=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()
    if(scan.violations.length)findings.push({theme,width,route,type:'axe',violations:scan.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))})
    checks.push({theme,width,route})
   }
  }
 }
 // Legacy workspace pages retain their existing handlers and can still render.
 await page.setViewportSize({width:1440,height:1000})
 for(const route of ['office','chat','projects','workflows','permissions','logs','skills','health','shop']){
  await page.goto(BASE+'/#'+route);await page.waitForTimeout(250)
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)
  if(overflow)findings.push({theme:'day',width:1440,route,type:'legacy-overflow'})
 }
 fs.writeFileSync('/tmp/control-layout-results.json',JSON.stringify({checks,findings,errors},null,2))
 console.log(JSON.stringify({checks:checks.length,findings,errors},null,2))
 await browser.close();assert.deepEqual(findings,[]);assert.deepEqual(errors,[])
})().catch(e=>{console.error(e);process.exit(1)})
