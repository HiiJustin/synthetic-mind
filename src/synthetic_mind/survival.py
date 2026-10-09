"""Independent survival needs, supplied routines, and evidence-based outcome memory."""
from __future__ import annotations
import math
import time
from .schemas import CognitiveEvent

ROUTINES = {'navigate','harvest','craft','place_at','sleep','strike'}
FOOD = {'bread','apple','carrot','baked_potato','cooked_beef','cooked_porkchop','potato','sweet_berries'}
HOSTILE = {'zombie','husk','drowned','skeleton','stray','spider','cave_spider','creeper','witch','pillager','zombie_villager'}


def command_key(c):
    return '|'.join((c['action'], c.get('item',''), str(c.get('target','')),str(c.get('entity_id',''))))


def valid_routine(c, sensed, state):
    if not state.get('survival.enabled') or c.get('action') not in ROUTINES: return False
    action = c['action']
    if action == 'craft': return c.get('item') in {'oak_planks','birch_planks','spruce_planks','crafting_table','stick','wooden_sword','bread'} and type(c.get('count')) is int and 1 <= c['count'] <= 8
    if action == 'strike':
        return any(e.get('id') == c.get('entity_id') and e.get('type') in HOSTILE and e.get('distance',999)<3.3 for e in sensed.get('visibleEntities',[]))
    target=c.get('target')
    if not isinstance(target,dict) or not all(type(target.get(k)) in (int,float) and math.isfinite(target[k]) for k in ('x','y','z')): return False
    if math.dist([target[k] for k in ('x','y','z')],[sensed.get('position',{}).get(k,1e9) for k in ('x','y','z')])>40: return False
    if action=='navigate': return True  # Destination chosen from remembered observations; body checks every path step.
    if not all(type(target[k]) is int for k in ('x','y','z')): return False
    if action=='place_at': return c.get('item') in {'dirt','cobblestone','oak_planks','birch_planks','spruce_planks','crafting_table'}
    return any(b['position']==target and (b['name'].endswith('_bed') if action=='sleep' else b['name']==c.get('block')) for b in sensed.get('visibleBlocks',[]))


def blueprint(center):
    """Three-by-three interior, five-by-five footprint; two-high walls and roof."""
    x,y,z=(center[k] for k in ('x','y','z'))
    walls=[{'x':x+dx,'y':y+h,'z':z+dz} for h in (0,1) for dx in range(-2,3) for dz in range(-2,3)
           if (abs(dx)==2 or abs(dz)==2) and not(dx==0 and dz==-2)]
    roof=[{'x':x+dx,'y':y+2,'z':z+dz} for dx in range(-2,3) for dz in range(-2,3)]
    return walls+roof


class OutcomeMemoryAgent:
    name, priority, subscriptions = 'survival_outcome_memory',59,{'minecraft.command','minecraft.action_result','minecraft.command_error','minecraft.damage','minecraft.death','minecraft.respawned','minecraft.sleep'}
    def __init__(self,state): self.state=state
    async def on_event(self,event):
        s=self.state;c=event.content;now=time.time()
        if event.kind=='minecraft.damage':
            s.set('survival.last_damage',{**c,'time':now,'event_id':event.id})
            dangers=s.get('survival.dangers',{})
            kind=c.get('source_type') if c.get('attribution')=='server' else 'unknown'
            kind=kind or 'unknown';entry=dangers.get(kind,{'hits':0})
            entry.update(hits=entry['hits']+1,last_evidence=event.id,attribution=c.get('attribution','unknown'))
            dangers[kind]=entry;s.set('survival.dangers',dangers)
            lesson=CognitiveEvent(self.name,'survival.lesson',{'lesson':f'Damage associated with {kind}', 'attribution':entry['attribution'],'evidence_id':event.id},(event.id,))
            return [lesson,CognitiveEvent(self.name,'attention.candidate',{'key':'survival.pain','origin_id':event.id,'kind':'survival.lesson','payload':lesson.content,'features':{'salience':1,'novelty':.9,'goal_relevance':1,'urgency':1,'confidence':1 if kind!='unknown' else .4}},(lesson.id,))]
        if event.kind=='minecraft.death':
            deaths=[t for t in s.get('survival.recent_deaths',[]) if now-t<300]+[now]
            s.set('survival.recent_deaths',deaths);s.set('survival.deaths',s.get('survival.deaths',0)+1)
            prior=s.get('survival.last_damage',{});cause=prior if now-prior.get('time',0)<10 else {'attribution':'unknown'}
            s.set('survival.last_death',{'time':now,'position':c.get('position'),'last_damage':cause,'evidence_id':event.id})
            s.set('survival.pending',{});s.set('council.last_motor',None)
            if len(deaths)>=3:
                s.set('minecraft.autonomous',False);s.set('survival.status','Paused after three deaths in five minutes; !start resumes')
            return [CognitiveEvent(self.name,'survival.lesson',{'lesson':'Death followed recent damage; exact final cause may be unknown','last_damage':cause,'evidence_id':event.id},(event.id,))]
        if event.kind=='minecraft.respawned':
            s.set('survival.status','Respawned; retained memory, reassessing inventory and surroundings')
            s.set('navigation.progress',None);s.set('council.bids',{});s.set('council.winner',None)
            return []
        if event.kind=='minecraft.sleep':
            s.set('survival.sleeping',c.get('sleeping',False))
            if c.get('sleeping'):s.set('survival.sleep_count',s.get('survival.sleep_count',0)+1)
            return []
        pending=s.get('survival.pending',{})
        if event.kind=='minecraft.command':
            if c.get('skill')=='routine':
                pending[c['id']]={'command':c,'time':now,'event_id':event.id};s.set('survival.pending',dict(list(pending.items())[-8:]))
            return []
        prior=pending.pop(c.get('command_id'),None)
        if not prior:return []
        s.set('survival.pending',pending);command=prior['command'];key=command_key(command)
        records=s.get('survival.routines',{});r=records.get(key,{'successes':0,'failures':0})
        success=event.kind=='minecraft.action_result' and c.get('verified') is True
        r['successes' if success else 'failures']+=1
        r.update(retry_after=now+(3 if success else min(600,30*r['failures'])),evidence_id=event.id,origin='supplied routine; measured reliability')
        records[key]=r;s.set('survival.routines',dict(list(records.items())[-256:]))
        summary={'action':command['action'],'success':success,'evidence_id':event.id,'detail':c.get('message'), 'origin':'supplied routine; measured outcome'}
        s.set('survival.latest',summary)
        if command['action']=='strike' and success:
            weapons=s.get('survival.weapon_trials',{});weapon=c.get('held','empty');w=weapons.get(weapon,{'confirmed_hits':0});w['confirmed_hits']+=1;w['damage_amount']='unobserved';weapons[weapon]=w;s.set('survival.weapon_trials',weapons)
        if command['action']=='place_at' and success:
            plan=s.get('survival.build',{})
            completed=plan.get('completed',[])
            if command.get('target') in plan.get('blocks',[]) and command['target'] not in completed:
                completed.append(command['target']);plan['completed']=completed;s.set('survival.build',plan)
        if command['action']=='navigate':
            visited=s.get('survival.destinations',{});visited[str(command.get('target'))]=now;s.set('survival.destinations',dict(list(visited.items())[-128:]))
        return [CognitiveEvent(self.name,'survival.lesson',summary,(event.id,prior['event_id']))]


class SurvivalNeedAgent:
    priority,subscriptions=27,{'perception.scene'}
    def __init__(self,state,role):self.state,self.role=state,role;self.name='survival_'+role
    def offer(self,event,c,score,reason):
        if c['action'] in ROUTINES and not valid_routine(c,self.state.get('minecraft.sensed',{}),self.state):return []
        r=self.state.get('survival.routines',{}).get(command_key(c),{})
        if r.get('retry_after',0)>time.time():return []
        # Repeated failure lowers a routine bid even after cooldown expires.
        score += max(-.04,min(.04,self.state.get('adaptation.actions',{}).get(c['action'],{}).get('mean_feedback',0)*.04))
        score -= min(.12, .025*r.get('failures',0)/max(1,r.get('successes',0)+1))
        self.state.set('survival.intent_'+self.role,reason)
        return [CognitiveEvent(self.name,'motivation.proposal',{'role':'survival_'+self.role,'skill':'routine','score':score,'reason':reason,'target':None,'experiment':c,'sensory_id':event.content['source_id']})]
    async def on_event(self,event):
        s=self.state;obs=s.get('minecraft.sensed',{});pos=obs.get('position');goal=s.get('brain.goal','').lower()
        if not s.get('survival.enabled') or not pos or obs.get('health',0)<=0 or obs.get('sleeping'):return []
        if goal.split()[:1] and goal.split()[0] in {'stay','wait','rest','stop'}:return []
        inv={i['name']:i['count'] for i in obs.get('inventory',[])};blocks=obs.get('visibleBlocks',[]);now=time.time()
        def offer(c,score,reason):return self.offer(event,c,score,reason)
        def nearest(candidates):return min(candidates,key=lambda b:b.get('distance',999),default=None)
        def harvest(block,score,reason):return offer({'action':'harvest','target':block['position'],'block':block['name']},score,reason)
        if self.role=='threat':
            learned=s.get('survival.dangers',{})
            mobs=[e for e in obs.get('visibleEntities',[]) if e.get('type') in HOSTILE or learned.get(e.get('type'),{}).get('hits',0)>0]
            mob=nearest(mobs)
            if not mob:return []
            learned_hits=learned.get(mob.get('type'),{}).get('hits',0)
            if learned_hits>0 and obs.get('health',20)<12:
                safe=[b for b in blocks if b['name'] in {'grass_block','dirt','stone','oak_planks'} and b.get('distance',0)>3 and math.dist([b['position'][k] for k in ('x','y','z')],[mob['position'][k] for k in ('x','y','z')])>mob['distance']+2]
                if safe:return offer({'action':'navigate','target':{**safe[-1]['position'],'y':safe[-1]['position']['y']+1}},1.12,'Prior damage from this entity type and low health: retreat toward observed ground')
            if mob['distance']<=3.2 and mob['type'] in HOSTILE:
                weapons=[i for i in inv if i.endswith('_sword')]
                trials=s.get('survival.weapon_trials',{})
                weapons.sort(key=lambda item:trials.get(item,{}).get('confirmed_hits',0),reverse=True)
                if weapons and obs.get('heldItem')!=weapons[0]:return offer({'action':'equip','item':weapons[0]},1.08,'Equip available defensive tool (supplied affordance)')
                return offer({'action':'strike','entity_id':mob['id']},1.07,'Nearby hostile; measure a defensive strike')
            if mob['distance']<7:
                safe=[b for b in blocks if b['name'] in {'grass_block','dirt','stone','oak_planks'} and b.get('distance',0)>3 and math.dist([b['position'][k] for k in ('x','y','z')],[mob['position'][k] for k in ('x','y','z')])>mob['distance']+2]
                if safe:return offer({'action':'navigate','target':{**safe[-1]['position'],'y':safe[-1]['position']['y']+1}},1.01,'Increase distance from observed hostile')
        if self.role=='food':
            hungry=obs.get('hunger',0)>.1 or obs.get('health',20)<20 and obs.get('food',20)<20
            s.set('survival.food_status', 'Hungry: food available' if hungry and any(i in FOOD for i in inv) else 'Hungry: seeking food' if hungry else 'Food level sufficient; no eating needed')
            if hungry and any(i in FOOD for i in inv):return offer({'action':'eat'},1.04,'Food is available; restore hunger and permit natural regeneration')
            if inv.get('wheat',0)>=3 and any(b['name']=='crafting_table' and b.get('distance',999)<4 for b in blocks):return offer({'action':'craft','item':'bread','count':1},.99,'Test recipe using available wheat')
            if hungry:
                crop=nearest([b for b in blocks if b['name'] in {'wheat','carrots','potatoes','sweet_berry_bush'}])
                if crop:return harvest(crop,.98,'Gather an observed crop; verify the result')
                chest=nearest([b for b in blocks if b['name'] in {'chest','barrel'} and b.get('distance',999)<=4])
                if chest:
                    known=s.get('learning.containers',{}).get(str(chest['position']),{})
                    item=next((i for i in known.get('contents',[]) if i['name'] in FOOD and i['count']>0),None)
                    action={'action':'take','item':item['name'],'count':min(3,item['count'])} if item else {'action':'inspect_container'}
                    return offer({**action,'target':chest['position'],'block':chest['name']},.98,'Inspect or retrieve food from a visible container')
        if self.role=='sleep':
            night=12541<=obs.get('timeOfDay',0)<=23458
            if night:
                bed=nearest([b for b in blocks if b['name'].endswith('_bed')])
                if bed:return offer({'action':'sleep','target':bed['position']},1.02,'Night: try an observed bed and record whether sleep starts')
                remembered=[v for v in s.get('council.spatial',{}).get('landmarks',{}).values() if v['name'].endswith('_bed')]
                if remembered:
                    bed=min(remembered,key=lambda b:math.dist(list(pos.values()),list(b['position'].values())))
                    if math.dist(list(pos.values()),list(bed['position'].values()))<32:return offer({'action':'navigate','target':bed['position']},.96,'Return toward a remembered bed; re-observe before using it')
        if self.role=='construction':
            if not any(word in goal for word in ('house','shelter','build')):return []
            plan=s.get('survival.build',{})
            wood=next((i for i in inv if i in {'oak_log','birch_log','spruce_log'}),None)
            planks=next((i for i in inv if i.endswith('_planks')),None)
            if wood:return offer({'action':'craft','item':wood.replace('_log','_planks'),'count':min(inv[wood],8)},.97,'Convert collected wood into building material')
            if not planks:
                log=nearest([b for b in blocks if b['name'] in {'oak_log','birch_log','spruce_log'} and b['position']['y']>=math.floor(pos['y'])])
                if log:return harvest(log,.97,'Gather visible wood for the shelter curriculum')
            if not plan and planks:
                known=s.get('minecraft.map',{})
                for b in blocks:
                    if b['name'] not in {'grass_block','dirt'}:continue
                    center={**b['position'],'y':b['position']['y']+1}
                    x,y,z=(center[k] for k in ('x','y','z'))
                    if all(known.get(f'{x+dx},{y-1},{z+dz}',{}).get('name') in {'grass_block','dirt','stone'} for dx in range(-2,3) for dz in range(-2,3)):
                        plan={'center':center,'blocks':blueprint(center),'completed':[],'origin':'supplied 3x3-interior blueprint'};s.set('survival.build',plan);break
            if plan and planks:
                home=plan['center']
                if math.dist([home[k] for k in ('x','y','z')],[pos[k] for k in ('x','y','z')])>8:
                    candidate=offer({'action':'navigate','target':home},.98,'Return to remembered construction site with materials')
                    if candidate:return candidate
                todo=[p for p in plan['blocks'] if p not in plan['completed']]
                if todo:
                    for target in todo[:12]:
                        candidate=offer({'action':'place_at','target':target,'item':planks},.97,'Place the next shelter block; verify the world changed')
                        if candidate:return candidate
                else:s.set('survival.status','Shelter blueprint placements completed; continue survival and exploration')
        if self.role=='exploration':
            # Reserve periodic intervals for opaque-muscle experiments.
            if int(now)%60<10:return []
            visited=s.get('survival.destinations',{})
            candidates=[b for b in blocks if b['name'] in {'grass_block','dirt','stone','oak_planks','cobblestone'} and 3<b.get('distance',0)<8]
            from .adaptation import cell
            counts=s.get('adaptation.visits',{})
            candidates.sort(key=lambda b:(counts.get(cell(b['position']),0),visited.get(str({**b['position'],'y':b['position']['y']+1}),0),-b.get('distance',0)))
            for b in candidates:
                target={**b['position'],'y':b['position']['y']+1}
                if now-visited.get(str(target),0)<90:continue
                candidate=offer({'action':'navigate','target':target},.96,'Explore an observed surface using a supplied stepping routine')
                if candidate:return candidate
        return []


def survival_agents(state):
    return [OutcomeMemoryAgent(state),*[SurvivalNeedAgent(state,role) for role in ('threat','food','sleep','construction','exploration')]]
