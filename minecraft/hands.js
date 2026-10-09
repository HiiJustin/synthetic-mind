'use strict'

const { distance, lineVisible } = require('./senses')
const ACTIONS = ['inventory', 'equip', 'dig', 'place', 'inspect_container', 'take', 'use_block', 'use_item']
const MATERIALS = /^(dirt|cobblestone|oak_planks|oak_log|birch_log|spruce_log)$/
const items = bot => bot.inventory.items().map(item => ({ name: item.name, count: item.count }))
const snapshot = bot => ({ inventory: items(bot), held: bot.heldItem ? bot.heldItem.name : null, food: bot.food, health: bot.health, position:bot.entity?.position ? {x:bot.entity.position.x,y:bot.entity.position.y,z:bot.entity.position.z}:undefined })

function validateHands (command) {
  if (['equip', 'place', 'take'].includes(command.action) && (typeof command.item !== 'string' || !/^[a-z0-9_]{1,64}$/.test(command.item))) throw new Error('Specify an item name')
  if (['dig', 'place', 'inspect_container', 'take', 'use_block'].includes(command.action)) {
    if (!command.target || !['x', 'y', 'z'].every(k => Number.isInteger(command.target[k]) && Math.abs(command.target[k]) <= 30000000)) throw new Error('Specify integer block coordinates')
    if (typeof command.block !== 'string' || !/^[a-z0-9_]{1,64}$/.test(command.block)) throw new Error('Specify the expected block name')
  }
  if (command.action === 'take' && (!Number.isInteger(command.count) || command.count < 1 || command.count > 8)) throw new Error('Take between 1 and 8 items')
  return command
}

function targetBlock (bot, command) {
  const p = command.target
  const point = bot.entity.position.offset(p.x - bot.entity.position.x, p.y - bot.entity.position.y, p.z - bot.entity.position.z)
  const block = bot.blockAt(point)
  const eye = bot.entity.position.offset(0, 1.62, 0)
  if (!block || block.name !== command.block) throw new Error('Target changed since observation')
  if (distance(eye, point.offset(0.5, 0.5, 0.5)) > 4 || !lineVisible(bot, eye, point.offset(0.5, 0.5, 0.5), true)) throw new Error('Target is out of reach or occluded')
  return block
}

async function executeHands (bot, command, check = () => {}) {
  validateHands(command)
  check()
  const before = snapshot(bot)
  let evidence = {}
  if (command.action === 'use_item') { await executeUse(bot, 2000, check); return { before, after: snapshot(bot), verified: true } }
  if (command.action === 'inventory') return { before, after: snapshot(bot), verified: true }
  if (command.action === 'equip') {
    const item = bot.inventory.items().find(i => i.name === command.item)
    if (!item) throw new Error('Item is not in inventory')
    await bot.equip(item, 'hand')
    check()
    evidence = { verified: bot.heldItem?.name === command.item }
  } else {
    const block = targetBlock(bot, command)
    if (command.action === 'use_block') {
      await bot.activateBlock(block); check()
      if (bot.currentWindow) { evidence.contents=bot.currentWindow.slots.filter(Boolean).map(i=>({name:i.name,count:i.count,slot:i.slot})); bot.closeWindow(bot.currentWindow) }
      evidence.verified=true
    } else if (command.action === 'dig') {
      // No underfoot excavation, falling blocks, fluids, containers or unbounded mining.
      if (block.diggable === false) throw new Error('The game marks this block unbreakable')
      let timer
      try { await Promise.race([bot.dig(block),new Promise((_,reject)=>{timer=setTimeout(()=>{bot.stopDigging();reject(new Error('Dig pulse ended before block broke'))},7500)})]) }
      finally { clearTimeout(timer) }
      check()
      const after = bot.blockAt(block.position)
      evidence = { block_before: block.name, block_after: after?.name, verified: Boolean(after && after.name !== block.name) }
    } else if (command.action === 'place') {
      const dest = block.position.offset(0, 1, 0)
      const space = bot.blockAt(dest)
      if (!space || !['air', 'cave_air'].includes(space.name) || distance(dest.offset(0.5, 0.5, 0.5), bot.entity.position.offset(0, 0.5, 0)) < 1.2) throw new Error('Placement space is occupied or too close to body')
      const item = bot.inventory.items().find(i => i.name === command.item)
      if (!item) throw new Error('Building item is not in inventory')
      await bot.equip(item, 'hand')
      check()
      targetBlock(bot, command)
      await bot.placeBlock(block, block.position.offset(-block.position.x, 1 - block.position.y, -block.position.z))
      check()
      evidence = { block_after: bot.blockAt(dest)?.name, verified: bot.blockAt(dest)?.name === command.item }
    } else {
      if (!['chest', 'barrel'].includes(block.name)) throw new Error('Only chests and barrels are supported')
      const container = await bot.openContainer(block)
      try {
        check()
        evidence = { contents: container.containerItems().map(i => ({ name: i.name, count: i.count })).slice(0, 54), verified: true }
        if (command.action === 'take') {
          const item = container.containerItems().find(i => i.name === command.item)
          if (!item || item.count < command.count) throw new Error('Requested items are unavailable')
          await container.withdraw(item.type, item.metadata, command.count)
          check()
          const count = list => list.filter(i => i.name === command.item).reduce((n, i) => n + i.count, 0)
          await new Promise(resolve => setTimeout(resolve, 150))
          check()
          evidence.verified = count(items(bot)) - count(before.inventory) >= command.count
        }
      } finally { container.close() }
    }
  }
  const after = snapshot(bot)
  if (command.action === 'take') {
    const count = list => list.filter(i => i.name === command.item).reduce((n, i) => n + i.count, 0)
    evidence.verified = count(after.inventory) - count(before.inventory) >= command.count
  }
  return { before, after, ...evidence }
}

async function executeUse(bot, duration, check) {
  const block = require('./senses').cursorBlock(bot)
  const held = bot.heldItem
  if (block && held && bot.registry.blocksByName[held.name]) {
    const hit = block.face
    const faces = [[0,-1,0],[0,1,0],[0,0,-1],[0,0,1],[-1,0,0],[1,0,0]]
    const f = faces[hit] || [0,1,0]
    await bot.placeBlock(block, block.position.offset(-block.position.x+f[0],-block.position.y+f[1],-block.position.z+f[2]))
  } else if (held && bot.registry.foodsByName?.[held.name]) {
    bot.activateItem()
    try { const until=Date.now()+duration; while(Date.now()<until){check();await new Promise(r=>setTimeout(r,25))} }
    finally { bot.deactivateItem() }
  } else if (block) { await bot.activateBlock(block); if(bot.currentWindow)bot.closeWindow(bot.currentWindow) }
  else {
    bot.activateItem()
    try { await new Promise(r=>setTimeout(r,Math.min(duration,350)));check() } finally { bot.deactivateItem() }
  }
  check()
}
module.exports = { ACTIONS, validateHands, executeHands, snapshot, executeUse }
