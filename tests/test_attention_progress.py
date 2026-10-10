import unittest,time
from synthetic_mind.attention import SelectiveAttention,ProgressReview,AutonomousGoals
from synthetic_mind.embodied import ActionSelector,action_key
from synthetic_mind.minecraft_embodiment import MinecraftEmbodiment
from synthetic_mind.schemas import CognitiveEvent
from test_goal_progress import State

class AttentionProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_goal_object_wins_attention_over_near_clutter(self):
        s=State();s.set('embodied.goal_state',{'resource_relevance':{'oak_log':1}})
        objects=[{'id':str(i),'type':'grass','distance':1} for i in range(20)]+[{'id':'log','type':'oak_log','distance':7}]
        s.set('embodied.observation',{'objects':objects})
        await SelectiveAttention(s).on_event(CognitiveEvent('test','subconscious.perceived',{}))
        self.assertEqual(s.get('embodied.attention')['objects'][0]['id'],'log')
        self.assertEqual(len(s.get('embodied.attention')['objects']),8)
    async def test_repeat_failures_change_action_selection(self):
        s=State();o={'time':time.time()};s.set('embodied.observation',o)
        a={'family':'move','parameters':{'toward':'log'},'command':{'target':{'x':1}},'prior':{'resources':{'log':1}}}
        b={'family':'muscle','parameters':{'channel':'m0'},'command':{}}
        s.set('embodied.goal_state',{'resource_relevance':{'log':1}});s.set('embodied.candidates',[a,b])
        first=await ActionSelector(s).on_event(CognitiveEvent('test','embodied.cycle',{'enabled':True}))
        self.assertEqual(first[0].content['candidate'],a)
        s.set('embodied.eligibility',[{'id':'trial','candidate':a}])
        for _ in range(3):await ProgressReview(s).on_event(CognitiveEvent('test','embodied.result',{'id':'trial','changed':False}))
        s.set('embodied.next_action',0);s.set('embodied.recent_choices',[])
        second=await ActionSelector(s).on_event(CognitiveEvent('test','embodied.cycle',{'enabled':True}))
        self.assertEqual(second[0].content['candidate'],b)
    async def test_auto_goal_persists_and_operator_wins(self):
        s=State();s.set('brain.goal','auto');s.set('embodied.candidates',[{'prior':{'resources':{'log':1}}}])
        module=AutonomousGoals(s);await module.on_event(CognitiveEvent('test','embodied.observation',{'resources':{}}))
        first=s.get('embodied.autonomous_goal');s.set('embodied.candidates',[])
        await module.on_event(CognitiveEvent('test','embodied.observation',{'resources':{}}));self.assertEqual(first,s.get('embodied.autonomous_goal'))
        s.set('brain.goal','operator task');self.assertEqual(await module.on_event(CognitiveEvent('test','embodied.observation',{})),[])
    def test_visible_far_resource_has_directed_step(self):
        s=State();obs={'position':{'x':0,'y':0,'z':0},'visibleBlocks':[{'name':'oak_log','distance':7,'position':{'x':0,'y':1,'z':-7},'knownDrops':['oak_log']}]}
        moves=[c for c in MinecraftEmbodiment(s).candidates(obs) if c['family']=='move' and c['command'].get('target')]
        self.assertEqual(len(moves),1);self.assertGreater(moves[0]['prior']['resources']['oak_log'],0)
    def test_dropped_resource_has_pickup_not_attack(self):
        s=State();obs={'position':{'x':0,'y':0,'z':0},'visibleEntities':[{'id':2,'type':'item','distance':2,'position':{'x':0,'y':0,'z':-2},'item':{'name':'oak_log','count':1}}]}
        candidates=MinecraftEmbodiment(s).candidates(obs)
        self.assertTrue(any(c['parameters'].get('pickup')=='oak_log' for c in candidates));self.assertFalse(any(c['family']=='strike' for c in candidates))

    async def test_slot_changes_alone_do_not_reset_trial_penalty(self):
        s=State();candidate={'family':'muscle','parameters':{'channel':'m5'},'command':{}}
        s.set('embodied.eligibility',[{'id':'a','candidate':candidate}])
        for _ in range(3):await ProgressReview(s).on_event(CognitiveEvent('test','embodied.result',{'id':'a','changed':True,'effects':{'measured':{}}}))
        self.assertEqual(s.get('embodied.progress_review')['streak'],3)
