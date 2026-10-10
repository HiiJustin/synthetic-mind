import json
import tempfile
import time
import unittest
from pathlib import Path
from synthetic_mind.embodied import ActionSelector, OutcomeEvaluator, WorldModel, action_key
from synthetic_mind.stores import Database, StateStore
from synthetic_mind.schemas import CognitiveEvent
from synthetic_mind.config import Config
from synthetic_mind.minecraft import MinecraftEngine, MinecraftSession
from test_minecraft import MinecraftTests, PROJECT


class GenericLearningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'state.db');self.state=StateStore(self.db)
    def tearDown(self):self.db.close();self.temp.cleanup()
    async def test_terminal_experience_changes_later_choice_and_survives_reopen(self):
        s=self.state;o={'time':time.time(),'resources':{},'vitals':{'integrity':1,'energy':1},'held':None}
        s.set('embodied.observation',o)
        a={'family':'lever','parameters':{'handle':'A'},'command':{'handle':'A'}}
        b={'family':'lever','parameters':{'handle':'B'},'command':{'handle':'B'}}
        s.set('embodied.candidates',[a,b]);selector=ActionSelector(s)
        first=(await selector.on_event(CognitiveEvent('test','embodied.cycle',{'enabled':True})))[0].content
        await OutcomeEvaluator(s).on_event(CognitiveEvent('body','embodied.executed',{'id':'trial','key':first['key'],'family':'lever','candidate':first['candidate']}))
        feedback=(await OutcomeEvaluator(s).on_event(CognitiveEvent('body','embodied.terminal',{})))[0]
        await WorldModel(s).on_event(feedback)
        self.assertLess(s.get('embodied.models')[first['key']]['value'],-2)
        self.db.close();self.db=Database(Path(self.temp.name)/'state.db');self.state=s=StateStore(self.db)
        s.set('embodied.next_action',0);s.set('embodied.recent_choices',[])
        next_choice=(await ActionSelector(s).on_event(CognitiveEvent('test','embodied.cycle',{'enabled':True})))[0]
        self.assertNotEqual(next_choice.content['key'],first['key']);self.assertEqual(s.get('embodied.deaths'),1)
    async def test_unrelated_ack_cannot_train_an_action(self):
        result=await WorldModel(self.state).on_event(CognitiveEvent('body','embodied.result',{'id':'unrelated','failed':False}))
        self.assertEqual(result,[]);self.assertIsNone(self.state.get('embodied.models'))
    async def test_old_actions_do_not_receive_death_credit(self):
        self.state.set('embodied.eligibility',[{'id':'old','key':'x','family':'lever','time':time.time()-100}])
        result=(await OutcomeEvaluator(self.state).on_event(CognitiveEvent('body','embodied.terminal',{})))[0]
        self.assertEqual(result.content['credits'],[])
    async def test_respawn_does_not_reward_death(self):
        self.state.set('embodied.vitals',None)
        result=await OutcomeEvaluator(self.state).on_event(CognitiveEvent('body','embodied.observation',{'vitals':{'integrity':1,'energy':1}}))
        self.assertEqual(result,[])


class EmbodiedIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name);(root/'config').mkdir()
        (root/'config/brain.json').write_text((PROJECT/'config/brain.json').read_text())
        (root/'config/survival.json').write_text('{"enabled":true}')
        self.engine=MinecraftEngine(root,Config());await self.engine.start();self.session=MinecraftSession(self.engine,PROJECT/'minecraft/config.json');self.sent=[]
        async def send(c):self.sent.append(c)
        self.session.send=send
        await self.session.ingest('minecraft.connected',{'username':'Test','muscle_channels':['m0','m1']});self.sent.clear()
    async def asyncTearDown(self):await self.engine.close();self.temp.cleanup()
    async def test_continuous_cycles_feedback_and_no_busy_deadlock(self):
        s=self.engine.state;s.set('minecraft.autonomous',True)
        for i in range(30):
            s.set('embodied.next_action',0)
            await self.session.ingest('minecraft.senses',{**MinecraftTests.senses(),'sequence':i})
            c=self.sent[-1]
            await self.session.ingest('minecraft.action_result',{'command_id':c['id'],'action':c['action'],'verified':True,'before':{'inventory':[]},'after':{'inventory':[]}})
            self.assertFalse(s.get('minecraft.motor_busy'))
        self.assertEqual(len([c for c in self.sent if c.get('skill')=='embodied']),30)
        self.assertTrue(s.get('embodied.models'));self.assertEqual(self.engine.status()['deliveries'].get('failed',0),0)
    async def test_paused_observations_do_not_act(self):
        await self.session.ingest('minecraft.senses',MinecraftTests.senses())
        self.assertEqual(self.sent,[]);self.assertTrue(self.engine.state.get('embodied.candidates'))
    async def test_no_material_whitelist_and_no_hidden_targets(self):
        await self.session.ingest('minecraft.senses',{**MinecraftTests.senses(),'visibleBlocks':[{'name':'diamond_ore','position':{'x':1,'y':63,'z':0},'distance':2}]})
        from synthetic_mind.experiments import valid_hand_action
        sensed=self.engine.state.get('minecraft.sensed')
        self.assertTrue(valid_hand_action({'action':'dig','block':'diamond_ore','target':{'x':1,'y':63,'z':0}},sensed))
        self.assertFalse(valid_hand_action({'action':'dig','block':'diamond_ore','target':{'x':8,'y':63,'z':0}},sensed))
        names=set(self.engine.registry.modules)
        self.assertIn('subconscious_reward',names);self.assertNotIn('survival_threat',names);self.assertNotIn('motor_skills',names)

    async def test_resource_goal_closed_loop_with_simulated_body(self):
        # Controlled perception/action fixture, not a claim of live Minecraft success.
        import math
        state=self.engine.state;state.set('minecraft.autonomous',True);state.set('brain.goal','Collect 3 oak logs')
        x=0.0;count=0;blocks=[5,6,7];drops=[];families=[]
        for tick in range(100):
            state.set('embodied.next_action',0)
            position={'x':x,'y':64,'z':0}
            visible=[{'id':str(b),'name':'oak_log','position':{'x':b,'y':64,'z':0},'distance':abs(b+.5-x),'knownDrops':['oak_log']} for b in blocks]
            entities=[{'id':100+b,'type':'item','position':{'x':b+.5,'y':64,'z':0},'distance':abs(b+.5-x),'item':{'name':'oak_log','count':1}} for b in drops]
            items=[{'name':'oak_log','count':count}] if count else []
            sensed={**MinecraftTests.senses(),'position':position,'visibleBlocks':visible,'visibleEntities':entities,'inventory':items,'heldItem':None,'food':20,'hunger':0,'health':20,'sequence':tick}
            await self.session.ingest('minecraft.senses',sensed)
            if state.get('embodied.goal_state',{}).get('complete'):break
            cmd=self.sent[-1];families.append(cmd['action']);before={'position':position,'inventory':items};extra={}
            if cmd['action']=='move' and cmd.get('target'):
                target=cmd['target']['x']+(.5 if 'entity_id' not in cmd else 0)
                x+=max(-1,min(1,target-x))
            if cmd['action']=='dig':
                b=cmd['target']['x']
                if b in blocks and abs(b+.5-x)<=4:
                    blocks.remove(b);drops.append(b);extra={'verified':True,'block_after':'air'}
            picked=[b for b in drops if abs(b+.5-x)<1.4];count+=len(picked);drops=[b for b in drops if b not in picked]
            after={'position':{'x':x,'y':64,'z':0},'inventory':[{'name':'oak_log','count':count}] if count else []}
            await self.session.ingest('minecraft.action_result',{'command_id':cmd['id'],'action':cmd['action'],'before':before,'after':after,**extra})
        self.assertEqual(count,3);self.assertTrue(state.get('embodied.goal_state')['complete'])
        self.assertIn('move',families);self.assertIn('dig',families)
