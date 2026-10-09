'use strict'
// Supplied recipe-book knowledge, not a claim that the agent discovered recipes.
// World access is limited to a table already included in the POV observation.
const cache = new WeakMap()
function recipeKnowledge(bot, visibleBlocks) {
  if (!bot.registry?.items || !bot.recipesAll || !bot.recipesFor) return []
  const tableSeen=visibleBlocks.find(b=>b.name==='crafting_table' && b.distance<=4)
  const signature=JSON.stringify([bot.inventory.items().map(i=>[i.name,i.count]),tableSeen?.position])
  const prior=cache.get(bot)
  if(prior?.signature===signature)return prior.recipes
  const table=tableSeen?bot.blockAt(bot.entity.position.offset(tableSeen.position.x-bot.entity.position.x,tableSeen.position.y-bot.entity.position.y,tableSeen.position.z-bot.entity.position.z)):null
  const owned=new Set(bot.inventory.items().map(i=>i.type));const recipes=[]
  for(const item of Object.values(bot.registry.items)) {
    const all=bot.recipesAll(item.id,null,true)
    for(const r of all) {
      const ingredients=(r.delta||[]).filter(v=>v.count<0)
      if(!ingredients.some(v=>owned.has(v.id)))continue
      const inputs={}
      for(const v of ingredients){const name=bot.registry.items[v.id]?.name;if(name)inputs[name]=(inputs[name]||0)-v.count}
      recipes.push({item:item.name,count:r.result?.count||1,inputs,requiresTable:!!r.requiresTable,
        craftable:bot.recipesFor(item.id,null,1,table).length>0,origin:'supplied recipe-book knowledge'})
      break
    }
  }
  cache.set(bot,{signature,recipes});return recipes
}
module.exports={recipeKnowledge}
