'use strict'
const test=require('node:test'),assert=require('node:assert/strict')
const {orient}=require('../directed-step')
class P {constructor(x,y,z){Object.assign(this,{x,y,z})} offset(x,y,z){return new P(this.x+x,this.y+y,this.z+z)}}
function bot(blocked=false){return {entity:{position:new P(0,0,0),pitch:0},entities:{},blockAt:p=>({boundingBox:blocked?'block':'empty',position:p}),look:async()=>{}}}
test('directed step rejects occluded and vanished targets',async()=>{
 await assert.rejects(orient(bot(true),{target:{x:0,y:0,z:-5},yaw:0}),/visible/)
 await assert.rejects(orient(bot(),{target:{x:0,y:0,z:-2},entity_id:5,yaw:0}),/disappeared/)
})
test('visible directed step points toward target',async()=>{
 const b=bot();let yaw=null;b.look=async y=>{yaw=y}
 await orient(b,{target:{x:0,y:0,z:-5},yaw:.2});assert.equal(yaw,.2)
})
