'use strict'
const {lineVisible,distance} = require('./senses')
async function orient(bot, command) {
 const p=command.target
 if (!p || !['x','y','z'].every(k=>Number.isFinite(p[k])) || !Number.isFinite(command.yaw)) throw Error('Invalid directed step')
 const eye=bot.entity.position.offset(0,bot.entity.eyeHeight||1.62,0)
 const entity=command.entity_id===undefined?null:bot.entities[command.entity_id]
 if(command.entity_id!==undefined&&!entity)throw Error('Pickup target disappeared')
 const point=entity?entity.position.offset(0,(entity.height||1)/2,0):eye.offset(p.x+.5-eye.x,p.y+.5-eye.y,p.z+.5-eye.z)
 if(distance(eye,point)>16 || !lineVisible(bot,eye,point,!entity))throw Error('Directed step target is no longer visible')
 await bot.look(command.yaw,bot.entity.pitch,false)
}
module.exports={orient}
