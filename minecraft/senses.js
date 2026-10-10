'use strict'

function finite (value) { return typeof value === 'number' && Number.isFinite(value) }
function xyz (position) { return { x: position.x, y: position.y, z: position.z } }
function distance (a, b) { return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z) }
function direction (yaw, pitch) {
  return { x: -Math.sin(yaw) * Math.cos(pitch), y: Math.sin(pitch), z: -Math.cos(yaw) * Math.cos(pitch) }
}

function cursorBlock (bot, range = 4) {
  const body = bot.entity
  if (!body || !finite(body.yaw) || !finite(body.pitch)) return null
  // Mineflayer 4.39's helper rejects zero yaw/pitch as falsy. Trace the actual
  // eye ray directly, preserving valid straight-ahead views and true eye height.
  if (!bot.world?.raycast) return bot.blockAtCursor?.(range) || null
  const eye = body.position.offset(0, body.eyeHeight || 1.62, 0)
  const d = direction(body.yaw, body.pitch)
  const vector = body.position.offset(d.x - body.position.x, d.y - body.position.y, d.z - body.position.z)
  return bot.world.raycast(eye, vector, range)
}

function configValid (config) {
  if (!['127.0.0.1', 'localhost', '::1'].includes(config.host)) throw new Error('v0.02 connects to a local server only')
  if (!Number.isInteger(config.port) || config.port < 1 || config.port > 65535) throw new Error('Invalid port')
  if (typeof config.username !== 'string' || !/^[a-zA-Z0-9_]{3,16}$/.test(config.username)) throw new Error('Username must be 3-16 letters, numbers, or underscores')
  for (const key of ['visionRange', 'fieldOfView', 'senseIntervalMs', 'maxVisibleBlocks', 'hearingRange', 'movementDurationMs', 'leaseMs']) {
    if (!finite(config[key]) || config[key] <= 0) throw new Error(`Invalid ${key}`)
  }
  if (config.visionRange > 16 || config.fieldOfView > 180 || config.maxVisibleBlocks > 512 ||
      config.senseIntervalMs < 250 || config.movementDurationMs > 1000 || config.leaseMs > 10000) throw new Error('Sensor/control limits exceeded')
  return config
}

function lineVisible (bot, eye, target, targetIsBlock = false) {
  const length = distance(eye, target)
  // Unknown chunks are not transparent. Stop at the surface; hidden blocks never pass.
  for (let t = 0.25; t < length - 0.45; t += 0.25) {
    const point = eye.offset((target.x - eye.x) * t / length, (target.y - eye.y) * t / length, (target.z - eye.z) * t / length)
    const block = bot.blockAt(point)
    if (!block) return false
    if (block.boundingBox === 'block') {
      // A ray hitting the observed surface is success, even at an oblique angle.
      // A solid block encountered before that surface is an occluder.
      return targetIsBlock && block.position.x === Math.floor(target.x) &&
        block.position.y === Math.floor(target.y) && block.position.z === Math.floor(target.z)
    }
  }
  return true
}

function motorProximity (bot, range = 1.2) {
  const horizontal = direction(bot.entity.yaw, 0)
  const ahead = bot.entity.position.offset(horizontal.x * range, 0.1, horizontal.z * range)
  const foot = bot.blockAt(ahead)
  const head = bot.blockAt(ahead.offset(0, 1.5, 0))
  const ground = bot.blockAt(ahead.offset(0, -0.5, 0))
  const stepSpace = bot.blockAt(ahead.offset(0, 1.1, 0))
  const stepHead = bot.blockAt(ahead.offset(0, 2.5, 0))
  return { obstructedAhead: !foot || !head || foot.boundingBox === 'block' || head.boundingBox === 'block',
    supportedAhead: Boolean(ground && ground.boundingBox === 'block'),
    canStepUp: Boolean(foot && foot.boundingBox === 'block' && stepSpace && stepSpace.boundingBox !== 'block' && stepHead && stepHead.boundingBox !== 'block'),
    hazardAhead: [foot, head, ground].some(block => block && /lava|fire|cactus|magma|powder_snow/.test(block.name)) }
}

function observe (bot, config, sequence) {
  if (!bot.entity) return null
  const body = bot.entity
  const eye = body.position.offset(0, body.eyeHeight || 1.62, 0)
  const forward = direction(body.yaw, body.pitch)
  const halfAngleCos = Math.cos(config.fieldOfView * Math.PI / 360)
  const candidates = []
  for (let x = Math.floor(eye.x - config.visionRange); x <= Math.ceil(eye.x + config.visionRange); x++) {
    for (let y = Math.floor(eye.y - config.visionRange); y <= Math.ceil(eye.y + config.visionRange); y++) {
      for (let z = Math.floor(eye.z - config.visionRange); z <= Math.ceil(eye.z + config.visionRange); z++) {
        const center = eye.offset(x + 0.5 - eye.x, y + 0.5 - eye.y, z + 0.5 - eye.z)
        const range = distance(eye, center)
        if (range < 0.25 || range > config.visionRange) continue
        const alignment = ((center.x - eye.x) * forward.x + (center.y - eye.y) * forward.y + (center.z - eye.z) * forward.z) / range
        if (alignment < halfAngleCos) continue
        const block = bot.blockAt(center)
        if (block && block.name !== 'air' && block.name !== 'cave_air' && block.name !== 'void_air') candidates.push({ block, center, range })
      }
    }
  }
  candidates.sort((a, b) => a.range - b.range)
  const firstTypes = new Set()
  const diverse = []; const repeated = []
  for (const c of candidates) {
    if (!lineVisible(bot, eye, c.center, true)) continue
    if (!firstTypes.has(c.block.name)) { firstTypes.add(c.block.name); diverse.push(c) } else repeated.push(c)
  }
  const visibleBlocks = []
  for (const candidate of [...diverse, ...repeated]) {
    if (visibleBlocks.length >= config.maxVisibleBlocks) break
    visibleBlocks.push({ id: `block:${bot.game?.dimension || 'unknown'}:${candidate.block.position.x},${candidate.block.position.y},${candidate.block.position.z}`, kind: 'block', relative: {x:candidate.center.x-eye.x,y:candidate.center.y-eye.y,z:candidate.center.z-eye.z}, name: candidate.block.name, position: xyz(candidate.block.position), distance: Number(candidate.range.toFixed(2)), knownDrops: (bot.registry?.blocksByName?.[candidate.block.name]?.drops || []).map(id=>bot.registry.items[id]?.name).filter(Boolean), knowledgeOrigin: 'supplied game material knowledge' })
  }
  const visibleEntities = []
  for (const entity of Object.values(bot.entities || {})) {
    if (entity.id === body.id || !entity.position) continue
    const target = entity.position.offset(0, (entity.height || 1) / 2, 0)
    const range = distance(eye, target)
    if (range < 0.1 || range > config.visionRange) continue
    const alignment = ((target.x - eye.x) * forward.x + (target.y - eye.y) * forward.y + (target.z - eye.z) * forward.z) / range
    if (alignment >= halfAngleCos && lineVisible(bot, eye, target)) visibleEntities.push({ id: entity.id, type: entity.name || entity.type || 'entity', position: xyz(entity.position), distance: Number(range.toFixed(2)) })
  }
  const position = body.position
  return {
    sequence,
    position: xyz(position), orientation: { yaw: body.yaw, pitch: body.pitch },
    velocity: body.velocity ? xyz(body.velocity) : { x: 0, y: 0, z: 0 }, onGround: Boolean(body.onGround),
    health: bot.health, hunger: (20 - bot.food) / 20, food: bot.food,
    oxygen: finite(bot.oxygenLevel) ? bot.oxygenLevel : null,
    contact: { horizontal: Boolean(body.isCollidedHorizontally), vertical: Boolean(body.isCollidedVertically) },
    visibleBlocks, visibleEntities: visibleEntities.slice(0, 16),
    // Short-range motor clearance is a tactile/proximity abstraction, independent of vision.
    proximity: motorProximity(bot),
    inventory: bot.inventory.items().map(item => ({ name: item.name, count: item.count })).slice(0, 36),
    heldItem: bot.heldItem ? bot.heldItem.name : null,
    heldNutrition: bot.registry?.foodsByName?.[bot.heldItem?.name]?.foodPoints || 0,
    recipes: require('./recipe-senses').recipeKnowledge(bot, visibleBlocks),
    selectedSlot: bot.quickBarSlot,
    crosshair: (() => { const b = cursorBlock(bot); return b ? { name: b.name, position: xyz(b.position) } : null })(),
    worldTickRate: bot.worldTickRate || 20,
    sleeping: Boolean(bot.isSleeping), dimension: bot.game?.dimension || null,
    timeOfDay: bot.time ? bot.time.timeOfDay : null,
    sensoryModel: 'filtered-structured-v1'
  }
}

function heardSound (bot, config, packet) {
  if (!bot.entity || !finite(packet.x) || !finite(packet.y) || !finite(packet.z)) return null
  const location = { x: packet.x / 8, y: packet.y / 8, z: packet.z / 8 }
  const range = distance(bot.entity.position, location)
  if (range > config.hearingRange) return null
  const relative = { x: location.x - bot.entity.position.x, y: location.y - bot.entity.position.y, z: location.z - bot.entity.position.z }
  return { sound: String(packet.soundName || packet.soundId || 'unknown'),
    bearing: Math.atan2(-relative.x, -relative.z), elevation: Math.atan2(relative.y, Math.hypot(relative.x, relative.z)),
    rangeBand: range < 4 ? 'near' : range < 10 ? 'middle' : 'far',
    volume: finite(packet.volume) ? packet.volume : 1, sensoryModel: 'localized-sound-event-v1' }
}

function validateCommand (command) {
  if (!command || typeof command !== 'object' || typeof command.id !== 'string' || command.id.length > 100) throw new Error('Invalid command envelope')
  if (!['move', 'look', 'stop', 'say', 'eat', 'muscle', 'inventory', 'equip', 'dig', 'place', 'inspect_container', 'take', 'use_item', 'use_block', 'heartbeat', 'disconnect', 'navigate', 'harvest', 'craft', 'place_at', 'sleep', 'strike'].includes(command.action)) throw new Error('Unsupported action')
  if (command.action === 'move' && !['forward', 'back', 'left', 'right', 'jump'].includes(command.control)) throw new Error('Unsupported movement')
  if ('jump' in command && typeof command.jump !== 'boolean') throw new Error('Invalid jump modifier')
  if (command.action === 'look' && (!finite(command.yaw) || !finite(command.pitch) || Math.abs(command.pitch) > Math.PI / 2)) throw new Error('Invalid look angle')
  if (command.action === 'say' && (typeof command.text !== 'string' || !command.text.trim() || command.text.trim().startsWith('/') || command.text.length > 200 || /[\r\n\x00-\x1f]/.test(command.text))) throw new Error('Invalid speech (plain chat only)')
  if (command.action === 'muscle' && !/^m(?:[0-9]|1[0-2])$/.test(command.channel)) throw new Error('Unknown muscle channel')
  return command
}

module.exports = { configValid, observe, heardSound, validateCommand, lineVisible, direction, distance, motorProximity, cursorBlock }
