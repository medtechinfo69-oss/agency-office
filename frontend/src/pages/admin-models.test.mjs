import { test } from 'node:test'
import assert from 'node:assert/strict'
import { recommendModel } from './admin-models.js'
const models = [
  { id: 'reasoner-32b', free: true, size: 20e9 },
  { id: 'coder-3b', free: true, size: 2e9 },
  { id: 'vision-pro', free: false, size: 10e9 },
  { id: 'fast-mini', free: true, size: 1e9 },
]
test('recommend by task without inventing model names', () => {
  assert.equal(recommendModel(models, 'reasoning').id, 'reasoner-32b')
  assert.equal(recommendModel(models, 'code').id, 'coder-3b')
  assert.equal(recommendModel(models, 'design').id, 'vision-pro')
  assert.equal(recommendModel(models, 'speed').id, 'coder-3b')
})
test('filter known RAM requirements and return null if none fit', () => {
  assert.equal(recommendModel(models, 'reasoning', 4).id, 'coder-3b')
  assert.equal(recommendModel(models, 'reasoning', 1), null)
  assert.equal(recommendModel([], 'code'), null)
})
