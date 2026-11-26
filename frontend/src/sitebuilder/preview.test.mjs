import { test } from 'node:test'
import assert from 'node:assert/strict'
import { previewDocument } from './preview.js'
import { completedFiles } from './partial.js'
test('preview preserves dollar replacement syntax and installs strict CSP before scripts',()=>{
 const doc=previewDocument({'index.html':'<html><head></head><body><h1>Test</h1></body></html>','styles.css':'a::after{content:"$&"}','script.js':'const replacement="$&";'},'known-test-id')
 assert(doc.includes('const replacement="$&";'))
 assert(doc.includes('content:"$&"'))
 assert(doc.includes("connect-src 'none'"))
 assert(doc.indexOf('Content-Security-Policy')<doc.indexOf('<script>'))
 assert(!doc.includes('allow-same-origin'))
})
test('partial preview only reads complete supported JSON strings without eval',()=>{
 assert.deepEqual(completedFiles('{"files":{"index.html":"<h1>Done</h1>","styles.css":"unfinished'),{'index.html':'<h1>Done</h1>'})
 assert.deepEqual(completedFiles('{"../.env":"no"}'),{})
})
