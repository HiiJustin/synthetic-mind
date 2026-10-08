'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const { observe, heardSound, validateCommand, configValid, direction } = require('../senses')
const defaults = require('../config.json')

test('crosshair accepts zero angles and uses eye height', () => {
  const { cursorBlock } = require('../senses')
  const bot = fixture()
  bot.entity.eyeHeight = 1.62
  bot.world = { raycast: (eye, direction, range) => {
    assert.equal(eye.y, 1.62)
    assert.equal(direction.z, -1)
    assert.equal(range, 4)
    return { name: 'dirt' }
  } }
  assert.equal(cursorBlock(bot).name, 'dirt')
})

class Position {
  constructor (x, y, z) { this.x = x; this.y = y; this.z = z }
  offset (x, y, z) { return new Position(this.x + x, this.y + y, this.z + z) }
}

function fixture () {
  const blocks = new Map([
    ['0,1,-2', 'stone'], ['0,1,-4', 'gold_block'], ['0,1,2', 'diamond_block']
  ])
  return {
    entity: { id: 1, position: new Position(0.5, 0, 0.5), yaw: 0, pitch: 0, height: 1.62, onGround: true, velocity: new Position(0, 0, 0) },
    health: 20, food: 16, oxygenLevel: 300, entities: {}, time: { timeOfDay: 100 },
    inventory: { items: () => [{ name: 'bread', count: 3 }] },
    blockAt (position) {
      const p = new Position(Math.floor(position.x), Math.floor(position.y), Math.floor(position.z))
      const name = blocks.get(`${p.x},${p.y},${p.z}`) || (p.y < 0 ? 'grass_block' : 'air')
      return { name, position: p, boundingBox: name === 'air' ? 'empty' : 'block' }
    }
  }
}

test('vision filters blocks behind the body and behind solid occluders', () => {
  const snapshot = observe(fixture(), { ...defaults, visionRange: 5 }, 1)
  const names = snapshot.visibleBlocks.map(block => block.name)
  assert.ok(names.includes('stone'))
  assert.ok(!names.includes('gold_block'))
  assert.ok(!names.includes('diamond_block'))
  assert.equal(snapshot.hunger, 0.2)
  assert.deepEqual(snapshot.inventory, [{ name: 'bread', count: 3 }])
})

test('vision count is bounded', () => {
  assert.ok(observe(fixture(), { ...defaults, maxVisibleBlocks: 2 }, 2).visibleBlocks.length <= 2)
})

test('ground surfaces remain visible at oblique angles', () => {
  const snapshot = observe(fixture(), { ...defaults, visionRange: 5 }, 3)
  assert.ok(snapshot.visibleBlocks.some(block => block.name === 'grass_block' && block.distance > 2))
})

test('sound is local and exposes bearing/range rather than precise source coordinates', () => {
  const near = heardSound(fixture(), defaults, { x: 8, y: 0, z: -16, soundId: 2, volume: 1 })
  assert.equal(near.rangeBand, 'near')
  assert.equal(near.position, undefined)
  assert.equal(heardSound(fixture(), defaults, { x: 8000, y: 0, z: 0 }), null)
})

test('directions match Minecraft yaw conventions', () => {
  assert.equal(direction(0, 0).z, -1)
  assert.ok(Math.abs(direction(Math.PI / 2, 0).x + 1) < 1e-9)
})

test('only bounded plain speech and known movements pass validation', () => {
  assert.throws(() => validateCommand({ id: 'x', action: 'say', text: '/op someone' }))
  assert.throws(() => validateCommand({ id: 'x', action: 'say', text: 'hello\n/stop' }))
  assert.throws(() => validateCommand({ id: 'x', action: 'look', yaw: NaN, pitch: 0 }))
  assert.throws(() => validateCommand({ id: 'x', action: 'move', control: 'teleport' }))
  assert.equal(validateCommand({ id: 'x', action: 'move', control: 'forward' }).control, 'forward')
})

test('bridge connects only to a local endpoint', () => {
  assert.throws(() => configValid({ ...defaults, host: 'example.com' }))
  assert.throws(() => configValid({ ...defaults, visionRange: 100 }))
  assert.equal(configValid(defaults).host, '127.0.0.1')
})

test('motor probes use horizontal heading even when looking vertically', () => {
  const bot = fixture()
  bot.entity.pitch = Math.PI / 2
  const snapshot = observe(bot, defaults, 4)
  assert.equal(snapshot.proximity.supportedAhead, true)
})

test('head-height obstruction is detected separately from foot clearance', () => {
  const bot = fixture()
  const original = bot.blockAt.bind(bot)
  bot.blockAt = position => {
    const block = original(position)
    if (block.position.z === -1 && block.position.y === 1) return { ...block, name: 'stone', boundingBox: 'block' }
    return block
  }
  assert.equal(observe(bot, defaults, 5).proximity.obstructedAhead, true)
})

test('one-block step is distinguished from a two-block wall', () => {
  const bot = fixture()
  const original = bot.blockAt.bind(bot)
  bot.blockAt = position => {
    const block = original(position)
    if (block.position.z === -1 && block.position.y === 0) return { ...block, name: 'stone', boundingBox: 'block' }
    return block
  }
  assert.equal(observe(bot, defaults, 6).proximity.canStepUp, true)
  assert.throws(() => validateCommand({id:'x',action:'move',control:'forward',jump:'yes'}))
  assert.equal(validateCommand({id:'x',action:'move',control:'forward',jump:true}).jump, true)
})
