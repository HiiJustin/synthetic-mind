import unittest,time
from synthetic_mind.survival import SurvivalNeedAgent,OutcomeMemoryAgent,valid_routine,blueprint
from synthetic_mind.schemas import CognitiveEvent
class State(dict):
 def set(self,k,v):self[k]=v
class SurvivalTests(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.state=State({'survival.enabled':True,'minecraft.autonomous':True,'brain.goal':'explore and build a house','minecraft.sensed':{'position':{'x':0,'y':70,'z':0},'health':20,'food':20,'hunger':0,'timeOfDay':13000,'inventory':[],'visibleBlocks':[],'visibleEntities':[]}})
  self.event=CognitiveEvent('perception','perception.scene',{'source_id':'sense'})
 async def test_night_selects_observed_bed_and_sleep_suspends_bids(self):
  self.state['minecraft.sensed']['visibleBlocks']=[{'name':'white_bed','position':{'x':0,'y':70,'z':2},'distance':2}]
  agent=SurvivalNeedAgent(self.state,'sleep');events=await agent.on_event(self.event)
  self.assertEqual(events[0].content['experiment']['action'],'sleep')
  self.state['minecraft.sensed']['sleeping']=True;self.assertEqual(await agent.on_event(self.event),[])
 async def test_unknown_damage_does_not_blame_nearby_zombie(self):
  a=OutcomeMemoryAgent(self.state)
  await a.on_event(CognitiveEvent('body','minecraft.damage',{'attribution':'unknown','source_type':None}))
  self.assertIn('unknown',self.state['survival.dangers']);self.assertNotIn('zombie',self.state['survival.dangers'])
 async def test_server_attribution_and_death_evidence_persist(self):
  a=OutcomeMemoryAgent(self.state);damage=CognitiveEvent('body','minecraft.damage',{'attribution':'server','source_type':'zombie'})
  await a.on_event(damage);await a.on_event(CognitiveEvent('body','minecraft.death',{}))
  self.assertEqual(self.state['survival.last_death']['last_damage']['event_id'],damage.id)
  await a.on_event(CognitiveEvent('body','minecraft.respawned',{}));self.assertEqual(self.state['survival.dangers']['zombie']['hits'],1)
 async def test_repeated_death_pauses_autonomy(self):
  a=OutcomeMemoryAgent(self.state)
  for _ in range(3):await a.on_event(CognitiveEvent('body','minecraft.death',{}))
  self.assertFalse(self.state['minecraft.autonomous'])
 async def test_failed_routine_cools_down_not_success(self):
  a=OutcomeMemoryAgent(self.state);c={'id':'a','action':'navigate','target':{'x':2,'y':70,'z':2},'skill':'routine'}
  await a.on_event(CognitiveEvent('executive','minecraft.command',c))
  await a.on_event(CognitiveEvent('body','minecraft.command_error',{'command_id':'a','message':'no path'}))
  entry=next(iter(self.state['survival.routines'].values()));self.assertEqual(entry['successes'],0);self.assertGreater(entry['retry_after'],time.time())
 async def test_food_routine_available_in_developmental_mode(self):
  self.state['sensorimotor.developmental']=True;self.state['minecraft.sensed'].update(hunger=.4,inventory=[{'name':'bread','count':2}])
  events=await SurvivalNeedAgent(self.state,'food').on_event(self.event)
  self.assertEqual(events[0].content['experiment']['action'],'eat')
 async def test_damage_memory_changes_low_health_response(self):
  obs=self.state['minecraft.sensed'];obs.update(health=8,visibleEntities=[{'id':2,'type':'zombie','distance':2,'position':{'x':0,'y':70,'z':2}}],visibleBlocks=[{'name':'grass_block','distance':6,'position':{'x':0,'y':69,'z':-6}}])
  agent=SurvivalNeedAgent(self.state,'threat')
  first=await agent.on_event(self.event);self.assertEqual(first[0].content['experiment']['action'],'strike')
  await OutcomeMemoryAgent(self.state).on_event(CognitiveEvent('body','minecraft.damage',{'attribution':'server','source_type':'zombie'}))
  second=await agent.on_event(self.event);self.assertEqual(second[0].content['experiment']['action'],'navigate')
  self.assertIn('Prior damage',second[0].content['reason'])
 def test_combat_excludes_players_and_far_targets(self):
  obs=self.state['minecraft.sensed'];obs['visibleEntities']=[{'id':1,'type':'player','distance':2},{'id':2,'type':'zombie','distance':8}]
  self.assertFalse(valid_routine({'action':'strike','entity_id':1},obs,self.state));self.assertFalse(valid_routine({'action':'strike','entity_id':2},obs,self.state))
 def test_blueprint_has_doorway_and_roof(self):
  blocks=blueprint({'x':0,'y':70,'z':0})
  self.assertNotIn({'x':0,'y':70,'z':-2},blocks)
  self.assertEqual(len([p for p in blocks if p['y']==72]),25)
  self.assertEqual(len(blocks),55)
