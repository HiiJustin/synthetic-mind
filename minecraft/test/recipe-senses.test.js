'use strict'
const test=require('node:test'),assert=require('node:assert/strict')
const {recipeKnowledge}=require('../recipe-senses')
const craft=require('mineflayer/lib/plugins/craft')
const deps=require('node:module').createRequire(require.resolve('mineflayer'))
const registry=deps('minecraft-data')('1.21.4')
function botWith(items){const bot={registry,inventory:{items:()=>items.map(([name,count])=>({name,count,type:registry.itemsByName[name].id})),count:id=>items.filter(([n])=>registry.itemsByName[n].id===id).reduce((n,[,c])=>n+c,0)}};craft(bot);return bot}
test('recipe observations use actual registry, support tools and distinguish missing table',()=>{
 const bot=botWith([['oak_planks',6],['stick',2]])
 const recipes=recipeKnowledge(bot,[])
 assert.equal(recipes.find(r=>r.item==='crafting_table').craftable,true)
 assert.equal(recipes.find(r=>r.item==='wooden_pickaxe').craftable,false)
 assert.equal(recipes.find(r=>r.item==='wooden_pickaxe').requiresTable,true)
 assert.ok(recipes.find(r=>r.item==='wooden_pickaxe').inputs.stick)
})
test('recipe sensing with no visible table never searches hidden world',()=>{
 const bot=botWith([['oak_log',1]]);bot.blockAt=()=>{throw Error('Hidden world access')}
 assert.ok(recipeKnowledge(bot,[]).some(r=>r.item==='oak_planks'&&r.craftable))
})

