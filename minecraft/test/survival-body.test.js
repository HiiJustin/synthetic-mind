'use strict'
const test=require('node:test'),assert=require('node:assert/strict')
class Vec3 {constructor(x,y,z){Object.assign(this,{x,y,z})} clone(){return new Vec3(this.x,this.y,this.z)}}
const {execute}=require('../survival-body')
test('navigation cancels a path that makes no physical progress',async()=>{
 let cancelled=false
 const bot={inventory:{items:()=>[]},food:20,health:20,entity:{position:new Vec3(0,64,0)},pathfinder:{goto:()=>new Promise(()=>{}),setGoal:g=>{cancelled=g===null}}}
 const start=Date.now()
 await assert.rejects(execute(bot,{action:'navigate',target:{x:5,y:64,z:0}},()=>{}),/no spatial progress/)
 assert.equal(cancelled,true);assert.ok(Date.now()-start<6000)
})
test('navigation rejects false completion without displacement',async()=>{
 const bot={inventory:{items:()=>[]},food:20,health:20,entity:{position:new Vec3(0,64,0)},pathfinder:{goto:async()=>{},setGoal:()=>{}}}
 await assert.rejects(execute(bot,{action:'navigate',target:{x:5,y:64,z:0}},()=>{}),/before reaching target/)
})

