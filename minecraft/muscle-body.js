'use strict'

const { motorProximity, cursorBlock } = require('./senses')
const DEFAULT_WIRING = ['left', 'jump', 'forward', 'back', 'right', 'slot_next', 'slot_previous', 'yaw_left', 'yaw_right', 'pitch_up', 'pitch_down', 'use', 'attack']
const CHANNELS = DEFAULT_WIRING.map((_, i) => `m${i}`)
const xyz = p => ({ x: p.x, y: p.y, z: p.z })

function validateMuscle (command) {
  if (!CHANNELS.includes(command.channel)) throw new Error('Unknown muscle channel')
  if (command.duration_ms !== undefined && ![350, 1800, 3500].includes(command.duration_ms)) throw new Error('Unsupported activation duration')
}

function proprioception (bot, trackedTarget) {
  const target = trackedTarget ? bot.blockAt(trackedTarget) : cursorBlock(bot)
  return { position: xyz(bot.entity.position), yaw: bot.entity.yaw, pitch: bot.entity.pitch,
    worldTickRate: bot.worldTickRate || 20, slot: bot.quickBarSlot, held: bot.heldItem?.name || null, food: bot.food, health: bot.health,
    inventory: bot.inventory.items().map(i => ({ name: i.name, count: i.count })),
    target: target ? { name: target.name, position: xyz(target.position) } : null }
}

// Wiring is confined to the body; perception exposes channel IDs, never key labels.
// Optional permutation is used by adapter-level lesion/rewiring tests.
async function activateMuscle (bot, command, guard, wiring = DEFAULT_WIRING) {
  validateMuscle(command)
  const control = wiring[CHANNELS.indexOf(command.channel)]
  const requested = command.duration_ms || 350
  const before = proprioception(bot)
  const target = cursorBlock(bot)
  let intervention = null
  let peakHeight = bot.entity.position.y
  const started = Date.now()
  const check = () => { guard.check(); peakHeight = Math.max(peakHeight, bot.entity.position.y) }
  const wait = async ms => {
    const until = Date.now() + ms
    while (Date.now() < until) { check(); await new Promise(resolve => setTimeout(resolve, Math.min(25, until - Date.now()))) }
    check()
  }
  check()
  if (['forward', 'back', 'left', 'right', 'jump'].includes(control)) {
    const offset = { forward: 0, back: Math.PI, left: Math.PI / 2, right: -Math.PI / 2, jump: 0 }[control]
    if (!bot.entity.onGround) throw new Error('Body reflex: wait until grounded')
    const probe = () => motorProximity({ ...bot, entity: { ...bot.entity, yaw: bot.entity.yaw + offset } }, 0.85)
    const unsafe = () => { const p = probe(); return p.hazardAhead || !p.supportedAhead || p.obstructedAhead }
    if (unsafe()) throw new Error('Body reflex inhibited activation')
    const reflex = () => {
      peakHeight = Math.max(peakHeight, bot.entity.position.y)
      if (control !== 'jump' && bot.entity.onGround && unsafe()) {
        intervention = 'proximity'; bot.clearControlStates()
      }
    }
    bot.on('physicsTick', reflex)
    try {
      bot.setControlState(control, true)
      await wait(Math.min(requested, 350))
    } finally { bot.clearControlStates(); bot.removeListener('physicsTick', reflex) }
  } else if (control.startsWith('slot_')) {
    bot.setQuickBarSlot((bot.quickBarSlot + (control === 'slot_next' ? 1 : 8)) % 9)
    await wait(100)
  } else if (control.startsWith('yaw_') || control.startsWith('pitch_')) {
    const yaw = bot.entity.yaw + (control === 'yaw_left' ? 0.45 : control === 'yaw_right' ? -0.45 : 0)
    const pitch = Math.max(-1.3, Math.min(1.3, bot.entity.pitch + (control === 'pitch_up' ? 0.3 : control === 'pitch_down' ? -0.3 : 0)))
    await bot.look(yaw, pitch, true)
    await wait(100)
  } else if (control === 'use') {
    // Early body supports using held food; it never chooses/equips a food item here.
    if (bot.heldItem && bot.registry.foodsByName?.[bot.heldItem.name] && bot.food < 20) {
      bot.activateItem()
      try { await wait(Math.min(requested, 2500)) } finally { bot.deactivateItem() }
      await wait(150)
    } else await wait(100)
  } else if (control === 'attack') {
    if (target && /^(dirt|oak_log|birch_log|spruce_log)$/.test(target.name) && target.position.y >= Math.floor(bot.entity.position.y)) {
      // A held pulse can be too short to break a block: that is an observable non-effect.
      let settled = false
      let failure
      const digging = bot.dig(target, 'ignore').then(() => { settled = true }, error => { failure = error; settled = true })
      try { await wait(requested) } finally { if (!settled) bot.stopDigging(); await digging }
      check()
      if (failure && !/abort/i.test(failure.message)) throw failure
      await wait(150)
    } else await wait(100)
  } else throw new Error('Invalid body wiring')
  check()
  const after = proprioception(bot, target?.position)
  return { muscle_before: before, muscle_after: after, peak_rise: peakHeight - before.position.y,
    duration_ms: requested, elapsed_ms: Date.now() - started, intervention, verified: !intervention }
}

module.exports = { CHANNELS, validateMuscle, activateMuscle, proprioception }
