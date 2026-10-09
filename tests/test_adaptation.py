import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from synthetic_mind.adaptation import AdaptiveFeedbackAgent
from synthetic_mind.operator_control import enqueue,validate_control
from synthetic_mind.schemas import CognitiveEvent
from synthetic_mind.survival import SurvivalNeedAgent
from synthetic_mind.muscles import MotorBabblingAgent

class State(dict):
    def set(self,k,v):self[k]=v

class AdaptationTests(unittest.IsolatedAsyncioTestCase):
    async def test_uncertain_forward_channel_is_resampled(self):
        s=State({'minecraft.connection':{'muscle_channels':['m2']},'sensorimotor.models':{'m2':{'samples':2,'mean':{'forward':.63},'m2':{'forward':.7938}}}})
        events=await MotorBabblingAgent(s).on_event(CognitiveEvent('sense','perception.scene',{'source_id':'a'}))
        self.assertEqual(events[0].content['channel'],'m2')
        self.assertEqual(events[0].content['duration_ms'],350)

    async def test_repeated_local_motion_is_detected(self):
        s=State({'minecraft.autonomous':True});a=AdaptiveFeedbackAgent(s)
        for t in range(0,124,2):
            with patch('synthetic_mind.adaptation.time.time',return_value=1000+t):
                await a.on_event(CognitiveEvent('body','minecraft.senses',{'position':{'x':t%8,'y':73,'z':t%6}}))
        self.assertTrue(s['adaptation.progress']['looping'])
        self.assertLessEqual(len(s['adaptation.window']),61)

    async def test_travel_and_productive_work_not_marked_as_loop(self):
        for moving in (True,False):
            s=State({'minecraft.autonomous':True,'adaptation.productive_at':1100});a=AdaptiveFeedbackAgent(s)
            for t in range(0,124,2):
                with patch('synthetic_mind.adaptation.time.time',return_value=1000+t):
                    await a.on_event(CognitiveEvent('body','minecraft.senses',{'position':{'x':t if moving else 0,'y':73,'z':0}}))
            self.assertFalse(s['adaptation.progress']['looping'])

    async def test_revisiting_a_cell_cannot_farm_novelty_reward(self):
        s=State();a=AdaptiveFeedbackAgent(s)
        for n in range(2):
            await a.on_event(CognitiveEvent('executive','minecraft.command',{'id':str(n),'action':'navigate'}))
            await a.on_event(CognitiveEvent('body','minecraft.action_result',{'command_id':str(n),'verified':True,'after':{'position':{'x':3,'y':70,'z':3}}}))
            self.assertEqual(s['adaptation.feedback']['score'],.25 if n==0 else 0)

    async def test_inhibited_action_is_not_rewarded(self):
        s=State();a=AdaptiveFeedbackAgent(s)
        await a.on_event(CognitiveEvent('executive','minecraft.command',{'id':'a','action':'muscle'}))
        await a.on_event(CognitiveEvent('body','minecraft.action_result',{'command_id':'a','verified':False,'intervention':'cliff'}))
        self.assertLess(s['adaptation.feedback']['score'],0)

    async def test_feedback_changes_routine_priority(self):
        obs={'position':{'x':0,'y':70,'z':0}}
        s=State({'survival.enabled':True,'minecraft.sensed':obs})
        a=SurvivalNeedAgent(s,'exploration');e=CognitiveEvent('sense','perception.scene',{'source_id':'a'})
        c={'action':'navigate','target':{'x':3,'y':70,'z':0}}
        before=a.offer(e,c,.96,'test')[0].content['score']
        s['adaptation.actions']={'navigate':{'mean_feedback':-.5}}
        self.assertLess(a.offer(e,c,.96,'test')[0].content['score'],before)

    def test_controls_are_bounded_and_do_not_accept_shell_actions(self):
        for value in [{'action':'shell','value':'anything'},{'action':'goal','value':'x'*501},{'action':'assist','value':'yes'}]:
            with self.assertRaises(ValueError):validate_control(value)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);identifier=enqueue(p,{'action':'pause'})
            self.assertTrue((p/(identifier+'.json')).exists())
            for _ in range(15):enqueue(p,{'action':'start'})
            with self.assertRaises(ValueError):enqueue(p,{'action':'start'})
