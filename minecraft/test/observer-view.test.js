const test=require('node:test'),assert=require('node:assert/strict')
const {chooseView,clearRay}=require('../observer-view')
class V { constructor(x,y,z){Object.assign(this,{x,y,z})} offset(x,y,z){return new V(this.x+x,this.y+y,this.z+z)} plus(b){return this.offset(b.x,b.y,b.z)} minus(b){return this.offset(-b.x,-b.y,-b.z)} scaled(n){return new V(this.x*n,this.y*n,this.z*n)} distanceTo(b){return Math.hypot(this.x-b.x,this.y-b.y,this.z-b.z)} }
const make=blocked=>({entity:{position:new V(0,70,0),yaw:0},blockAt:p=>({name:blocked(p)?'stone':'air',boundingBox:blocked(p)?'block':'empty'})})
test('camera chooses an unobstructed angle around a wall',()=>{
 const b=make(p=>p.z>=3&&p.z<=4&&Math.abs(p.x)<3&&p.y<80),v=chooseView(b)
 assert.ok(v.clear);assert.ok(clearRay(b,b.entity.position.offset(0,1.5,0),new V(v.position.x,v.position.y+1.62,v.position.z)))
 assert.ok(Math.abs(v.position.x)>2||v.position.z<3)
})
test('camera ignores head turns and eases translation',()=>{
 const b=make(()=>false),v=chooseView(b);b.entity.yaw=Math.PI
 const same=chooseView(b,8,v.position);assert.ok(new V(...Object.values(v.position)).distanceTo(new V(...Object.values(same.position)))<.001)
 b.entity.position=b.entity.position.offset(1,0,0);const next=chooseView(b,8,v.position)
 assert.ok(new V(...Object.values(next.position)).distanceTo(new V(...Object.values(v.position)))<.5)
})
test('fully enclosed or unloaded views fail closed',()=>{assert.equal(chooseView(make(()=>true)).clear,false);const b=make(()=>false);b.blockAt=()=>null;assert.equal(chooseView(b).clear,false)})
