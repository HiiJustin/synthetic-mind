'use strict'
// Body/protocol validity only; friendly mobs and players remain valid targets.
const INVALID = new Set(['item', 'item_stack', 'experience_orb', 'xp_orb', 'arrow', 'spectral_arrow', 'trident', 'marker', 'block_display', 'item_display', 'text_display', 'interaction'])
function attackTarget(bot, entity) {
  if (!entity || entity.id === bot.entity?.id || bot.entities?.[entity.id] !== entity || entity.isValid === false) {
    throw new Error('Attack target is no longer available or is self')
  }
  const name = String(entity.name || bot.registry?.entities?.[entity.entityType]?.name || '').replace(/^minecraft:/, '')
  if (!name || name === 'unknown' || INVALID.has(name)) throw new Error(`Entity cannot be attacked: ${name || 'unknown'}`)
  bot.attack(entity)
}
module.exports = { attackTarget }
