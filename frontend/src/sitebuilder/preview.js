export function previewDocument(files, nonce = '') {
  let html = files['index.html'] || '<!doctype html><html><head></head><body></body></html>'
  const css = (files['styles.css'] || files['style.css'] || '').replace(/<\/style/gi, '<\\/style')
  const js = (files['script.js'] || '').replace(/<\/script/gi, '<\\/script')
  if (!/<head[\s>]/i.test(html)) html = html.replace(/<html[^>]*>/i, '$&<head></head>')
  if (!/<head[\s>]/i.test(html)) html = '<!doctype html><html><head></head><body>' + html + '</body></html>'
  const policy = "default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; script-src 'unsafe-inline'; img-src data: blob:; font-src https://fonts.gstatic.com data:; connect-src 'none'; form-action 'none'; base-uri 'none'"
  const monitor = `<script>addEventListener('error',e=>parent.postMessage({type:'agency:preview-error',nonce:${JSON.stringify(nonce)},message:String(e.message).slice(0,300)},'*'));addEventListener('unhandledrejection',()=>parent.postMessage({type:'agency:preview-error',nonce:${JSON.stringify(nonce)},message:'Unhandled promise rejection'},'*'))</script>`
  html = html.replace(/<head[^>]*>/i, (head) => `${head}<meta http-equiv="Content-Security-Policy" content="${policy}">${monitor}`)
  html = html.replace(/<link[^>]*href=["']styles?\.css["'][^>]*>/gi, '')
    .replace(/<script[^>]*src=["']script\.js["'][^>]*>\s*<\/script>/gi, '')
  html = html.replace(/<\/head>/i, () => `<style>${css}</style></head>`)
  if (/<\/body>/i.test(html)) html = html.replace(/<\/body>/i, () => `<script>${js}</script></body>`)
  else html += `<script>${js}</script>`
  return html
}
export function openIsolatedPreview(files) {
  const doc = previewDocument(files).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')
  const wrapper = `<!doctype html><html><head><meta name="viewport" content="width=device-width"><title>Website preview</title><style>body{margin:0}iframe{border:0;width:100%;height:100dvh}</style></head><body><iframe title="Isolated website preview" sandbox="allow-scripts" referrerpolicy="no-referrer" srcdoc="${doc}"></iframe></body></html>`
  const url = URL.createObjectURL(new Blob([wrapper], { type: 'text/html' }))
  window.open(url, '_blank', 'noopener,noreferrer')
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}
