import {test} from 'node:test';import assert from 'node:assert/strict';import {mask,compactLink} from './handoff.mjs';
test('encode accents, Arabic and line breaks',()=>{const p='Café\nمرحبا بالعالم';assert.equal(new URL(compactLink(p).url).searchParams.get('prompt'),p)});
test('limit very long Unicode links safely',()=>{const r=compactLink('🌸مرحبا '.repeat(500));assert.ok(r.short);assert.ok(r.url.length<=1950);assert.ok(new URL(r.url).searchParams.get('prompt').length>0)});
test('mask secrets and contact details',()=>{const r=mask('password=hunter2 sk-abcdefghijklmnop jane@example.com +216 55 123 456');assert.doesNotMatch(r,/hunter2|sk-abcdefghijklmnop|jane@example.com|55 123 456/);assert.match(r,/REDACTED/)});
