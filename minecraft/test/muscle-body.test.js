'use strict'
const test = require('node:test')
const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const { CHANNELS, validateMuscle, activateMuscle } = require('../muscle-body')

class Position {
  constructor (x, y, z) { this.x = x; this.y = y; this.z = z }
  offset (x, y, z) { return new Position(this.x + x, this.y + y, this.z + z) }
}
function fixture () {
  const bot = new EventEmitter()
  Object.assign(bot, { entity: { position: new Position(0.5, 1, 0.5), yaw: 0, pitch: 0, onGround: true },
    inventory: { items: () => [] }, quickBarSlot: 0, food: 20, health: 20, registry: {},
    blockAtCursor: () => null,
    blockAt: p => ({ name: p.y < 1 ? 'stone' : 'air', position: p, boundingBox: p.y < 1 ? 'block' : 'empty' }),
    setQuickBarSlot: slot => { bot.quickBarSlot = slot },
    look: async (yaw, pitch) => { bot.entity.yaw = yaw; bot.entity.pitch = pitch },
    setControlState: (control, value) => { bot.control = value ? control : null },
    clearControlStates: () => { bot.control = null }
  })
  return bot
}
const guard = { check: () => {} }

test('body catalog exposes only neutral channels', () => {
  assert.equal(CHANNELS.length, 13)
  assert.ok(CHANNELS.every(c => /^m\d+$/.test(c)))
  assert.throws(() => validateMuscle({ channel: 'forward' }))
  assert.throws(() => validateMuscle({ channel: 'm0', duration_ms: 100000 }))
})

test('wiring can be permuted without changing channel names or result schema', async () => {
  const bot = fixture()
  const result = await activateMuscle(bot, { channel: 'm0' }, guard, ['slot_next'])
  assert.equal(result.muscle_after.slot - result.muscle_before.slot, 1)
  assert.equal(result.control, undefined)
  assert.equal(result.verified, true)
})

test('cancellation releases controls and physics listeners', async () => {
  const bot = fixture()
  let checks = 0
  await assert.rejects(activateMuscle(bot, { channel: 'm2' }, { check: () => { if (++checks > 2) throw new Error('cancelled') } }), /cancelled/)
  assert.equal(bot.control, null)
  assert.equal(bot.listenerCount('physicsTick'), 0)
})

test('unsafe ground inhibits before control is pressed', async () => {
  const bot = fixture()
  bot.blockAt = p => ({ name: 'air', position: p, boundingBox: 'empty' })
  await assert.rejects(activateMuscle(bot, { channel: 'm2' }, guard), /inhibited/)
  assert.equal(bot.control, undefined)
})

test('looking is measured rather than described by a key label', async () => {
  const bot = fixture()
  const result = await activateMuscle(bot, { channel: 'm7' }, guard)
  assert.ok(result.muscle_after.yaw > result.muscle_before.yaw)
  assert.equal(result.muscle_after.position.x, result.muscle_before.position.x)
})
