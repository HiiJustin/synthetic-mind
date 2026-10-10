import unittest
from synthetic_mind.embodied import GoalMemory
from synthetic_mind.minecraft_embodiment import normalize
from synthetic_mind.schemas import CognitiveEvent

class State:
    def __init__(self): self.data={}
    def get(self,k,d=None): return self.data.get(k,d)
    def set(self,k,v): self.data[k]=v

class GoalTests(unittest.IsolatedAsyncioTestCase):
    async def test_plural_quantity_and_completion(self):
        s=State();s.set('brain.goal','Collect 3 oak logs')
        s.set('embodied.candidates',[{'prior':{'resources':{'oak_log':1}}}])
        for count, complete in [(0,False),(2,False),(3,True)]:
            s.set('embodied.observation',{'resources':{'oak_log':count}})
            await GoalMemory(s).on_event(CognitiveEvent('test','embodied.observation',{}))
            self.assertEqual(s.get('embodied.goal_state')['targets'],{'oak_log':3})
            self.assertEqual(s.get('embodied.goal_state')['complete'],complete)
    async def test_operator_overrides_old_goal_and_auto_is_explicit(self):
        s=State();s.set('embodied.goal','old goal');s.set('brain.goal','auto')
        s.set('embodied.candidates',[{'prior':{'resources':{'oak_log':1}}}])
        await GoalMemory(s).on_event(CognitiveEvent('test','embodied.observation',{}))
        self.assertEqual(s.get('embodied.goal_state')['mode'],'autonomous')
        s.set('brain.goal','Collect 3 oak logs')
        await GoalMemory(s).on_event(CognitiveEvent('test','embodied.observation',{}))
        self.assertEqual(s.get('embodied.goal_state')['mode'],'operator')
    def test_inventory_stacks_are_summed(self):
        self.assertEqual(normalize({'inventory':[{'name':'oak_log','count':2},{'name':'oak_log','count':1}]})['resources']['oak_log'],3)
