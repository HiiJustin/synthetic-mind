"""Minecraft boundary for generic embodied cognition. Only POV observations enter."""
import math
import time
from collections import Counter
from .schemas import CognitiveEvent
from .embodied import fingerprint, action_key


def normalize(sensed):
    blocks=sensed.get('visibleBlocks',[]);entities=sensed.get('visibleEntities',[])
    p=sensed.get('position',{});orient=sensed.get('orientation',{})
    cell=tuple(math.floor(p.get(k,0)/3) for k in ('x','y','z'))
    view=(round(math.atan2(math.sin(orient.get('yaw',0)),math.cos(orient.get('yaw',0)))/.5),round(orient.get('pitch',0)/.3))
    counts=dict(Counter(b['name'] for b in blocks));resources={i['name']:i['count'] for i in sensed.get('inventory',[])}
    objects=[{'type':b['name'],'position':b['position'],'distance':b.get('distance'),'observed':True} for b in blocks[:24]]
    return {'resources':resources,'held':sensed.get('heldItem'),'target_type':(sensed.get('crosshair') or {}).get('name'),
        'contact':sensed.get('contact',{}),'nearby_types':sorted({e['type'] for e in entities}),
        'vitals':{'integrity':sensed.get('health',20)/20,'energy':sensed.get('food',20)/20},
        'needs':{'energy':round(sensed.get('hunger',0),1),'integrity':round(1-sensed.get('health',20)/20,1)},
        'features':[f'view:{cell}:{view}',*[f'object:{k}' for k in counts]],'objects':objects,
        'uncertainty':['Outside field of view and occluded surfaces are unknown; remembered objects may have moved.'],
        'signature':fingerprint([cell,view,counts,resources,sensed.get('heldItem')]),'world_id':sensed.get('world_id')}


class MinecraftEmbodiment:
    name,priority='minecraft_embodiment',16
    subscriptions={'minecraft.senses','minecraft.command','minecraft.action_result','minecraft.command_error','minecraft.death','minecraft.respawned','cognition.cycle','embodied.selected'}
    def __init__(self,state): self.state=state
    async def on_event(self,event):
        s=self.state;c=event.content
        if event.kind=='minecraft.senses':
            o=normalize(c);s.set('embodied.candidates',self.candidates(c))
            knowledge={r['item']:{'inputs':r.get('inputs',{}),'origin':'supplied Minecraft recipe knowledge'} for r in c.get('recipes',[])}
            prior=s.get('embodied.knowledge',{});prior.update(knowledge);s.set('embodied.knowledge',dict(list(prior.items())[-2048:]))
            return [CognitiveEvent(self.name,'embodied.observation',o)]
        if event.kind=='cognition.cycle':
            ready=s.get('minecraft.autonomous') and s.get('minecraft.connection',{}).get('connected') and not s.get('minecraft.motor_busy') and not s.get('minecraft.sensed',{}).get('sleeping') and s.get('minecraft.sensed',{}).get('health',0)>0
            return [CognitiveEvent(self.name,'embodied.cycle',{'enabled':bool(ready)})]
        if event.kind=='embodied.selected':
            if s.get('minecraft.motor_busy') or not s.get('minecraft.autonomous'):return []
            candidate=c['candidate'];command=candidate['command'];s.set('minecraft.motor_busy',True)
            s.set('council.winner',{'role':'embodied','skill':candidate['family'],'reason':str(c['terms']),'score':c['score']})
            return [CognitiveEvent(self.name,'minecraft.action_proposed',{**command,'skill':'embodied','learning_key':c['key'],'candidate':candidate})]
        if event.kind=='minecraft.command':
            candidate=c.get('candidate')
            if not candidate:return []
            return [CognitiveEvent(self.name,'embodied.executed',{'id':c['id'],'key':c['learning_key'],'family':candidate['family'],'candidate':candidate})]
        if event.kind=='minecraft.death':
            s.set('minecraft.motor_busy',False)
            return [CognitiveEvent(self.name,'embodied.terminal',{'position':c.get('position'),'cause':'unknown unless separately attributed'})]
        if event.kind=='minecraft.respawned':
            s.set('embodied.vitals',None);s.set('embodied.candidates',[]);s.set('embodied.recent_choices',[]);return []
        record=next((h for h in s.get('embodied.eligibility',[]) if h['id']==c.get('command_id')),None)
        if not record:return []
        after=c.get('muscle_after') or c.get('after') or {}
        resources={i['name']:i['count'] for i in after.get('inventory',[])}
        # A missing result snapshot is unknown, never an empty backpack.
        if 'inventory' not in after:resources=record['before'].get('resources',{})
        effects={'resources':resources,'held':after.get('held'),'target':after.get('target'), 'position':after.get('position',c.get('position')),
            'yaw':after.get('yaw'),'pitch':after.get('pitch'),'block_after':c.get('block_after')}
        before=c.get('muscle_before') or c.get('before') or {}
        numeric={f'resource:{k}':resources.get(k,0)-record['before'].get('resources',{}).get(k,0) for k in resources.keys() | record['before'].get('resources',{}).keys()}
        for name,scale in (('food',20),('health',20),('yaw',1),('pitch',1)):
            if name in after and name in before:numeric[name]=(after[name]-before[name])/scale
        effects['measured']=numeric
        changed=resources!=record['before'].get('resources',{}) or any(after.get(k)!=before.get(k) for k in ('held','yaw','pitch','position','target') if k in after)
        failed=event.kind=='minecraft.command_error' or c.get('verified') is False
        return [CognitiveEvent(self.name,'embodied.result',{'id':c['command_id'],'after':{'resources':resources},'effects':effects,'changed':changed,'failed':failed,
            'information':0,'error':c.get('message')})]

    def candidates(self,obs):
        s=self.state;out=[];held=obs.get('heldItem');orientation=obs.get('orientation',{})
        def add(command,parameters=None,prior=None,information=0,cost=.05):
            out.append({'family':command['action'],'parameters':parameters or {k:v for k,v in command.items() if k not in ('action','target','yaw','pitch')},
                'command':command,'prior':prior or {},'information':information,'cost':cost})
        # Opaque channel exploration remains available in every context, for all durations.
        for channel in s.get('minecraft.connection',{}).get('muscle_channels',[f'm{i}' for i in range(13)]):
            for duration in (350,1800,3500):
                add({'action':'muscle','channel':channel,'duration_ms':duration},cost=duration/10000)
        # Named look is a supplied motor skill, clearly separate from opaque muscle learning.
        # It actively samples under-observed viewing directions, including elevation.
        for dy,dp in ((.8,0),(-.8,0),(0,.5),(0,-.5)):
            pitch=max(-1.5,min(1.5,orientation.get('pitch',0)+dp));yaw=orientation.get('yaw',0)+dy
            add({'action':'look','yaw':yaw,'pitch':pitch},{'yaw_delta':dy,'pitch_delta':dp},information=.22)
        for item in obs.get('inventory',[]):
            if item['name']!=held:add({'action':'equip','item':item['name']})
        # Affordances express possibilities. Their selection belongs to the generic learner.
        seen=set()
        for block in obs.get('visibleBlocks',[]):
            if block.get('distance',999)>4 or block['name'] in seen:continue
            seen.add(block['name']);target=block['position']
            add({'action':'dig','target':target,'block':block['name']},{'block':block['name'],'held':held},
                {'resources':{item:1 for item in block.get('knownDrops',[])}})
            add({'action':'use_block','target':target,'block':block['name']},{'block':block['name'],'held':held})
        for entity in obs.get('visibleEntities',[]):
            if entity.get('distance',999)<=3:
                add({'action':'strike','entity_id':entity['id']},{'target_type':entity['type'],'held':held})
        for recipe in obs.get('recipes',[]):
            if recipe.get('craftable'):
                add({'action':'craft','item':recipe['item'],'count':1},{'item':recipe['item']},{'resources':{recipe['item']:recipe.get('count',1)}})
        if obs.get('heldNutrition',0)>0:
            add({'action':'use_item'},{'held':held},{'relief':{'energy':obs['heldNutrition']/4}})
        else:add({'action':'use_item'},{'held':held})
        return out
