'use strict'
const test = require('node:test')
const assert = require('node:assert/strict')
const { validateHands, executeHands } = require('../hands')

test('hands reject malformed targets and excessive transfers', () => {
  assert.throws(() => validateHands({ action: 'dig', target: { x: NaN, y: 1, z: 2 }, block: 'dirt' }))
  assert.throws(() => validateHands({ action: 'take', item: 'bread', count: 64, target: { x: 0, y: 1, z: 2 }, block: 'chest' }))
  assert.doesNotThrow(() => validateHands({ action: 'place', item: 'tnt', target: { x: 0, y: 1, z: 2 }, block: 'stone' }))
})

test('equipment learns an observed held-item change, not just a resolved promise', async () => {
  const bot = { inventory: { items: () => [{ name: 'bread', count: 2 }] }, food: 20,
    equip: async () => {} }
  assert.equal((await executeHands(bot, { action: 'equip', item: 'bread' })).verified, false)
  bot.equip = async item => { bot.heldItem = item }
  assert.equal((await executeHands(bot, { action: 'equip', item: 'bread' })).verified, true)
})

test('cancelled action cannot start an effect', async () => {
  let calls = 0
  const bot = { equip: async () => { calls++ } }
  await assert.rejects(executeHands(bot, { action: 'equip', item: 'bread' }, () => { throw new Error('cancelled') }), /cancelled/)
  assert.equal(calls, 0)
})

test('missing inventory items fail without equipping', async () => {
  const bot = { inventory: { items: () => [] }, food: 20 }
  await assert.rejects(executeHands(bot, { action: 'equip', item: 'bread' }), /not in inventory/)
})
