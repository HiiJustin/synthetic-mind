import unittest
from synthetic_mind.expectations import OutcomePrediction
from synthetic_mind.embodied import ActionSelector,action_key
from synthetic_mind.schemas import CognitiveEvent
from test_embodied import GenericLearningTests


class PredictionTests(GenericLearningTests):
    async def test_prediction_uses_pre_action_values(self):
        s=self.state;s.set('embodied.models',{'trial':{'samples':3,'mean_effects':{'food':.5},'effect_counts':{'food':3},'effect_m2':{'food':.08}}})
        module=OutcomePrediction(s)
        await module.on_event(CognitiveEvent('body','embodied.executed',{'id':'cmd','key':'trial'}))
        # A later learner update cannot retroactively change the saved expectation.
        s.set('embodied.models',{'trial':{'mean_effects':{'food':0}}})
        result=(await module.on_event(CognitiveEvent('body','embodied.result',{'id':'cmd','effects':{'measured':{'food':0}},'failed':False})))[0]
        self.assertEqual(result.content['expected']['food'],.5)
        self.assertEqual(result.content['errors']['food'],-.5)
        self.assertTrue(result.content['comparable'])
        self.assertGreater(s.get('embodied.prediction_quality')['trial']['error'],0)
    async def test_unknown_effect_is_not_an_invented_prediction(self):
        m=OutcomePrediction(self.state)
        await m.on_event(CognitiveEvent('body','embodied.executed',{'id':'a','key':'unknown'}))
        result=(await m.on_event(CognitiveEvent('body','embodied.result',{'id':'a','effects':{'measured':{'food':1}}})))[0]
        self.assertFalse(result.content['comparable']);self.assertIsNone(result.content['normalized_error'])
    async def test_terminal_clears_pending_expectation(self):
        self.state.set('embodied.prediction_pending',{'a':{'key':'x'}})
        await OutcomePrediction(self.state).on_event(CognitiveEvent('body','embodied.terminal',{}))
        self.assertEqual(self.state.get('embodied.prediction_pending'),{})
    async def test_inaccurate_positive_prediction_changes_selection(self):
        import time
        s=self.state;o={'time':time.time()};s.set('embodied.observation',o);s.set('learning.enabled',False)
        a={'family':'switch','parameters':{'id':'A'}};b={'family':'switch','parameters':{'id':'B'}}
        ka,kb=action_key(a,o),action_key(b,o);s.set('embodied.candidates',[a,b]);s.set('embodied.models',{ka:{'value':1,'samples':5},kb:{'value':.8,'samples':5}})
        s.set('embodied.prediction_quality',{ka:{'error':4}})
        chosen=(await ActionSelector(s).on_event(CognitiveEvent('clock','embodied.cycle',{'enabled':True})))[0]
        self.assertEqual(chosen.content['key'],kb)

# The base tests are run in their own file, not repeated here.
for name in GenericLearningTests.__dict__:
    if name.startswith('test_'):setattr(PredictionTests,name,None)
