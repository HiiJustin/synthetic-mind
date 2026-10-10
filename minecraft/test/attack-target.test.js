'use strict'
const test = require('node:test')
const assert = require('node:assert/strict')
const { attackTarget } = require('../attack-target')
function fixture(name) {
  const target = { id: 2, name }; let calls = 0
  const bot = { entity: {id:1}, entities: {2:target}, attack: () => calls++ }
  return { bot, target, calls: () => calls }
}
test('invalid objects cannot send attack packets', () => {
  for (const name of ['item','item_stack','experience_orb','arrow','spectral_arrow','trident','marker','unknown','']) {
    const f = fixture(name); assert.throws(() => attackTarget(f.bot, f.target)); assert.equal(f.calls(),0)
  }
})
test('mobs, players and breakable entities retain attack access', () => {
  for (const name of ['zombie','cow','player','armor_stand','item_frame','boat']) {
    const f = fixture(name); attackTarget(f.bot,f.target); assert.equal(f.calls(),1)
  }
})
test('despawned, replaced and self targets cannot send packets', () => {
  const f = fixture('zombie'); delete f.bot.entities[2]
  assert.throws(() => attackTarget(f.bot,f.target))
  f.bot.entities[2] = {...f.target}; assert.throws(() => attackTarget(f.bot,f.target))
  f.bot.entities[1] = f.bot.entity; assert.throws(() => attackTarget(f.bot,f.bot.entity))
  assert.equal(f.calls(),0)
})
