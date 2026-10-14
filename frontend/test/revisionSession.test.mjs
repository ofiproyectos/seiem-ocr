import { test } from 'node:test'
import assert from 'node:assert/strict'

test('a duplicated tab gets a different identity despite copied storage', async (t) => {
  let stored = 'original-tab'
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: {
    getItem: () => stored, setItem: (_key, value) => { stored = value },
  } })
  t.mock.method(performance, 'getEntriesByType', () => [{ type: 'navigate' }])
  const { revisionBrowserSession } = await import('../src/revisionSession.ts?duplicated')
  const value = revisionBrowserSession()
  assert.notEqual(value, 'original-tab')
  assert.equal(revisionBrowserSession(), value)
  assert.equal(stored, value)
})

test('reloading retains the tab identity to resume its reservation', async (t) => {
  let stored = 'same-tab'
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: {
    getItem: () => stored, setItem: (_key, value) => { stored = value },
  } })
  t.mock.method(performance, 'getEntriesByType', () => [{ type: 'reload' }])
  const { revisionBrowserSession } = await import('../src/revisionSession.ts?reload')
  assert.equal(revisionBrowserSession(), 'same-tab')
})
