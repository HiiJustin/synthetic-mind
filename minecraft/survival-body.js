'use strict'
// Supplied, bounded body routines. Selection/reliability is learned by Python modules.
const { lineVisible, distance } = require('./senses')
const ROUTINES = ['navigate','harvest','craft','place_at','sleep','strike']
const BUILD = /^(dirt|cobblestone|[a-z_]+_planks|crafting_table)$/
const HARVEST = /^(dirt|[a-z_]+_log|[a-z_]+_leaves|wheat|carrots|potatoes|sweet_berry_bush)$/
const HOSTILE = /^(zombie|husk|drowned|skeleton|stray|spider|cave_spider|creeper|witch|pillager|zombie_villager)$/
const inventory = bot => bot.inventory.items().map(i=>({name:i.name,count:i.count}))
function validRoutine(c) {
 if (!ROUTINES.includes(c.action)) throw Error('Unsupported routine')
 if (['navigate','harvest','place_at','sleep'].includes(c.action) && (!c.target || !['x','y','z'].every(k=>Number.isFinite(c.target[k])&&Math.abs(c.target[k])<30000000))) throw Error('Invalid routine target')
 if(['craft','place_at'].includes(c.action)&&!(/^[a-z0-9_]{1,64}$/).test(c.item||'')) throw Error('Invalid item')
 if(c.action==='craft'&&(!Number.isInteger(c.count)||c.count<1||c.count>8)) throw Error('Craft count outside 1..8')
 if(c.action==='place_at'&&!BUILD.test(c.item)) throw Error('Unsupported building material')
 if(c.action==='strike'&&!Number.isInteger(c.entity_id)) throw Error('Invalid target entity')
}
function install(bot) {
 const {pathfinder,Movements}=require('mineflayer-pathfinder')
 bot.loadPlugin(pathfinder)
 bot.on('spawn',()=>{
  const m=new Movements(bot);m.canDig=false;m.allow1by1towers=false;m.allowParkour=false;m.allowSprinting=false;m.maxDropDown=1;m.scafoldingBlocks=[]
  // Cardinal routes avoid diagonal corner cutting from off-center starts.
  m.getMoveDiagonal=()=>{}
  for(const name of ['lava','fire','water','sweet_berry_bush','cactus','powder_snow'])if(bot.registry.blocksByName[name])m.blocksToAvoid.add(bot.registry.blocksByName[name].id)
  bot.pathfinder.setMovements(m);bot.pathfinder.thinkTimeout=1000;bot.pathfinder.tickTimeout=20;bot.pathfinder.searchRadius=40
 })
}
async function execute(bot,c,check) {
 validRoutine(c);check();const before={inventory:inventory(bot),food:bot.food,health:bot.health,position:{...bot.entity.position}}
 const {GoalNear}=require('mineflayer-pathfinder').goals
 const vec=p=>new bot.entity.position.constructor(p.x,p.y,p.z)
 const go=async(p,range=2)=>{
  check();if(distance(bot.entity.position,p)>40)throw Error('Navigation target beyond bounded range')
  let anchor=bot.entity.position.clone(),progressAt=Date.now(),timer
  try {
   await Promise.race([bot.pathfinder.goto(new GoalNear(Math.floor(p.x),Math.floor(p.y),Math.floor(p.z),range)),new Promise((_,reject)=>{
    timer=setInterval(()=>{
     try{check()}catch(e){bot.pathfinder.setGoal(null);reject(e);return}
     if(distance(bot.entity.position,anchor)>.6){anchor=bot.entity.position.clone();progressAt=Date.now()}
     if(Date.now()-progressAt>4000){reject(Error('Navigation made no spatial progress for 4 seconds'));bot.pathfinder.setGoal(null)}
    },250)
   })])
  } finally {clearInterval(timer)}
  check();if(distance(bot.entity.position,p)>range+1.5)throw Error('Path ended before reaching target')
 }
 const blockAt=()=>bot.blockAt(vec(c.target))
 const reach=(block)=>{const eye=bot.entity.position.offset(0,1.62,0);if(!block||distance(eye,block.position.offset(.5,.5,.5))>4.5||!lineVisible(bot,eye,block.position.offset(.5,.5,.5),true))throw Error('Target occluded or out of reach')}
 let result={}
 if(c.action==='navigate') {await go(c.target,1);result={verified:distance(bot.entity.position,c.target)<2.5}}
 if(c.action==='harvest') {
  let b=blockAt();if(!b||b.name!==c.block||!HARVEST.test(b.name))throw Error('Harvest target changed or unsupported')
  if(/^(wheat|carrots|potatoes)$/.test(b.name)&&Number(b.getProperties().age)<7)throw Error('Crop is not ripe')
  await go(c.target,2);b=blockAt();reach(b);if(b.name!==c.block||b.position.y<Math.floor(bot.entity.position.y))throw Error('Unsafe harvest target')
  const tools=bot.inventory.items().filter(i=>/_(axe|shovel)$/.test(i.name));if(tools[0]){await bot.equip(tools[0],'hand');check()}
  await bot.dig(b);check();result={verified:blockAt()?.name!==c.block,block_before:c.block,block_after:blockAt()?.name}
  // Move near the drop without treating a successful dig as successful collection.
  try{await go(c.target,1)}catch(e){check()}
 }
 if(c.action==='craft') {
  const item=bot.registry.itemsByName[c.item];if(!item)throw Error('Unknown recipe item')
  const table=bot.findBlock({matching:bot.registry.blocksByName.crafting_table.id,maxDistance:4})
  const recipes=bot.recipesFor(item.id,null,c.count,table)
  if(!recipes.length)throw Error('Ingredients or reachable crafting table missing')
  if(table)reach(table)
  await bot.craft(recipes[0],c.count,table);check()
  const total=list=>list.filter(i=>i.name===c.item).reduce((n,i)=>n+i.count,0)
  result={verified:total(inventory(bot))>total(before.inventory),item:c.item}
 }
 if(c.action==='place_at') {
  const p=vec(c.target),existing=bot.blockAt(p)
  if(existing?.name===c.item)return {before,after:before,verified:true,already_present:true}
  if(!existing||!['air','cave_air','short_grass','tall_grass'].includes(existing.name))throw Error('Building destination occupied')
  await go(c.target,3);check()
  if(distance(p.offset(.5,.5,.5),bot.entity.position.offset(0,.5,0))<1.1) {
    let moved=false
    for(const [dx,dz] of [[2,0],[-2,0],[0,2],[0,-2]]) {
      const stand=p.offset(dx,0,dz),ground=bot.blockAt(stand.offset(0,-1,0)),feet=bot.blockAt(stand),head=bot.blockAt(stand.offset(0,1,0))
      if(ground?.boundingBox==='block'&&feet?.boundingBox==='empty'&&head?.boundingBox==='empty'){await go(stand,0);moved=true;break}
    }
    if(!moved||distance(p.offset(.5,.5,.5),bot.entity.position.offset(0,.5,0))<1.1)throw Error('Placement would intersect body')
  }
  let reference,face
  for(const v of [[0,-1,0],[1,0,0],[-1,0,0],[0,0,1],[0,0,-1],[0,1,0]]) {const b=bot.blockAt(p.offset(...v));if(b&&b.boundingBox==='block'){try{reach(b);reference=b;face=new p.constructor(-v[0],-v[1],-v[2]);break}catch(e){}}}
  if(!reference) {
    const stands=[]
    for(let dx=-3;dx<=3;dx++)for(let dz=-3;dz<=3;dz++) {
      if(Math.abs(dx)+Math.abs(dz)<2)continue
      const q=new p.constructor(p.x+dx,Math.floor(bot.entity.position.y),p.z+dz)
      if(bot.blockAt(q.offset(0,-1,0))?.boundingBox==='block'&&bot.blockAt(q)?.boundingBox==='empty'&&bot.blockAt(q.offset(0,1,0))?.boundingBox==='empty')stands.push(q)
    }
    stands.sort((a,b)=>distance(a,bot.entity.position)-distance(b,bot.entity.position))
    for(const q of stands.slice(0,8)) {
      try{await go(q,0)}catch(e){check();continue}
      for(const v of [[0,-1,0],[1,0,0],[-1,0,0],[0,0,1],[0,0,-1],[0,1,0]]) {
        const b=bot.blockAt(p.offset(...v));if(b&&b.boundingBox==='block'){try{reach(b);reference=b;face=new p.constructor(-v[0],-v[1],-v[2]);break}catch(e){}}
      }
      if(reference)break
    }
  }
  if(!reference)throw Error('No reachable attachment face')
  const held=bot.inventory.items().find(i=>i.name===c.item);if(!held)throw Error('Building material missing')
  await bot.equip(held,'hand');check();await bot.placeBlock(reference,face);check()
  result={verified:bot.blockAt(p)?.name===c.item,block_after:bot.blockAt(p)?.name}
 }
 if(c.action==='sleep') {
  if(!['overworld','minecraft:overworld'].includes(bot.game.dimension))throw Error('Sleep only supported in overworld')
  await go(c.target,2);const bed=blockAt();reach(bed);if(!bed.name.endsWith('_bed'))throw Error('Bed no longer present')
  await bot.sleep(bed);check();result={verified:bot.isSleeping,sleep_started:bot.isSleeping}
 }
 if(c.action==='strike') {
  const e=bot.entities[c.entity_id];if(!e||!HOSTILE.test(e.name)||e.type==='player')throw Error('Only nearby hostile mobs can be defensive targets')
  const eye=bot.entity.position.offset(0,1.62,0),point=e.position.offset(0,(e.height||1)/2,0)
  if(distance(eye,point)>3.2||!lineVisible(bot,eye,point))throw Error('Entity out of reach or occluded')
  let hurt=false;const onHurt=(entity,source)=>{if(entity.id===e.id&&source?.id===bot.entity.id)hurt=true}
  bot.on('entityHurt',onHurt)
  try{await bot.lookAt(point,true);check();bot.attack(e);await new Promise(r=>setTimeout(r,650));check()}finally{bot.removeListener('entityHurt',onHurt)}
  result={verified:hurt,target_type:e.name,held:bot.heldItem?.name||'empty',evidence:'server-attributed hurt event; damage amount unknown'}
 }
 return {before,after:{inventory:inventory(bot),food:bot.food,health:bot.health,position:{...bot.entity.position}},...result}
}
module.exports={ROUTINES,validRoutine,install,execute}
