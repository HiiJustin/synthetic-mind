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
