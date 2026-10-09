'use strict'
// Operator camera geometry is deliberately excluded from cognitive observations.
function clearPoint(bot, p) {
  const b = bot.blockAt(new p.constructor(Math.floor(p.x), Math.floor(p.y), Math.floor(p.z)))
  return !!b && b.boundingBox === 'empty' && !/water|lava/.test(b.name)
}
function clearRay(bot, a, b) {
  const n = Math.ceil(a.distanceTo(b) / .2)
  for (let i=1;i<=n;i++) if (!clearPoint(bot, a.plus(b.minus(a).scaled(i/n)))) return false
  return true
}
function chooseView(bot, distance=8, previous=null, mode='follow') {
  const p=bot.entity.position, eye=p.offset(0,1.5,0), yaw=previous?Math.atan2(previous.x-p.x,previous.z-p.z):bot.entity.yaw
  const options=[]
  for (const radius of [distance, Math.min(distance,6), Math.min(distance,4),2]) {
    for (const height of [3,5,1]) for (const angle of [0,.65,-.65,1.3,-1.3,Math.PI]) {
      const basis=mode==='follow'?yaw:bot.entity.yaw+(mode==='side'?Math.PI/2:mode==='front'?Math.PI:0)
      const a=basis+angle, foot=p.offset(Math.sin(a)*radius,mode==='overhead'?height+distance:height,Math.cos(a)*radius)
      const view=foot.offset(0,1.62,0)
      const continuity=previous?Math.min(8,foot.distanceTo(new p.constructor(previous.x,previous.y,previous.z)))*.18:0
      options.push({position:foot,score:Math.abs(angle)*.7+Math.abs(distance-radius)*.4+Math.abs(height-3)*.2+continuity})
    }
  }
  options.sort((a,b)=>a.score-b.score)
  const valid = options.find(v => clearRay(bot,eye,v.position.offset(0,1.62,0)) && [v.position,v.position.offset(.3,0,.3),v.position.offset(-.3,0,-.3),v.position.offset(0,1.62,0)].every(q=>clearPoint(bot,q)))
  if (!valid) return {clear:false, reason:'No unobstructed camera position in loaded terrain', timestamp:Date.now()}
  const v=valid
  if(previous){
    const old=new p.constructor(previous.x,previous.y,previous.z), smooth=old.plus(v.position.minus(old).scaled(.18))
    if(clearRay(bot,eye,smooth.offset(0,1.62,0)) && clearRay(bot,old.offset(0,1.62,0),smooth.offset(0,1.62,0)) && [smooth,smooth.offset(.3,0,.3),smooth.offset(-.3,0,-.3)].every(q=>clearPoint(bot,q))) v.position=smooth
  }
  return {clear:true,position:{x:v.position.x,y:v.position.y,z:v.position.z},timestamp:Date.now(),distance:v.position.distanceTo(p)}
}
module.exports={chooseView,clearRay}
