import assert from 'node:assert/strict'
import { test } from 'node:test'
import { observeHeaderOffset } from '../src/v3/scrollOffset.js'

test('scroll offset follows measured desktop and wrapped mobile header heights', () => {
  const properties = new Map()
  let height = 72.25
  let resize
  let observed
  let disconnected = false
  const header = {
    parentElement: { style: {
      setProperty: (key, value) => properties.set(key, value),
      removeProperty: (key) => properties.delete(key),
    } },
    getBoundingClientRect: () => ({ height }),
  }
  class Observer {
    constructor(callback) { resize = callback }
    observe(element) { observed = element }
    disconnect() { disconnected = true }
  }
  const cleanup = observeHeaderOffset(header, Observer)
  assert.equal(observed, header)
  assert.equal(properties.get('--v3-header-height'), '73px')
  height = 138.5
  resize()
  assert.equal(properties.get('--v3-header-height'), '139px')
  height = 64
  resize()
  assert.equal(properties.get('--v3-header-height'), '64px')
  cleanup()
  assert.ok(disconnected)
  assert.ok(!properties.has('--v3-header-height'))
})
