import unittest
from synthetic_mind.muscles import MuscleLearningAgent, learned_forward, choose_channel, update_estimate
from synthetic_mind.schemas import CognitiveEvent


class State:
    def __init__(self): self.data = {}
    def get(self, key, default=None): return self.data.get(key, default)
    def set(self, key, value): self.data[key] = value


class MuscleTests(unittest.IsolatedAsyncioTestCase):
    async def test_effects_determine_mapping_even_when_channel_is_permuted(self):
        state = State()
        agent = MuscleLearningAgent(state)
        self.assertIsNone(learned_forward(state))
        for i in range(2):
            await agent.on_event(CognitiveEvent('executive', 'minecraft.command', {'id': str(i), 'action': 'muscle', 'channel': 'm6'}))
            await agent.on_event(CognitiveEvent('body', 'minecraft.action_result', {'command_id': str(i), 'verified': True,
                'muscle_before': {'position': {'x':0,'y':0,'z':0}, 'yaw':0, 'slot':0},
                'muscle_after': {'position': {'x':0,'y':0,'z':-0.8}, 'yaw':0, 'slot':0}}))
        self.assertEqual(learned_forward(state), 'm6')
        self.assertAlmostEqual(state.get('muscles.learned')['m6']['forward'], 0.8)

    async def test_inhibited_channel_is_not_learned_as_motion(self):
        state = State()
        agent = MuscleLearningAgent(state)
        await agent.on_event(CognitiveEvent('executive','minecraft.command', {'id':'a','action':'muscle','channel':'m0'}))
        await agent.on_event(CognitiveEvent('body','minecraft.command_error', {'command_id':'a'}))
        self.assertIsNone(learned_forward(state))
        self.assertEqual(state.get('muscles.learned')['m0']['samples'], 0)

    async def test_external_teleport_is_not_learned_as_an_action(self):
        state = State()
        agent = MuscleLearningAgent(state)
        await agent.on_event(CognitiveEvent('executive', 'minecraft.command', {'id':'a','action':'muscle','channel':'m0'}))
        await agent.on_event(CognitiveEvent('body','minecraft.action_result', {'command_id':'a','verified':True,
            'muscle_before': {'position':{'x':0,'y':0,'z':0},'yaw':0,'slot':0},
            'muscle_after': {'position':{'x':0,'y':0,'z':-100},'yaw':0,'slot':0}}))
        self.assertIsNone(learned_forward(state))
        self.assertFalse(state.get('sensorimotor.latest')['valid'])

    async def test_variable_effect_is_not_confidently_selected(self):
        state = State()
        record = update_estimate({}, {'forward': 1.0})
        record = update_estimate(record, {'forward': -0.8})
        state.set('sensorimotor.models', {'m8': record})
        self.assertIsNone(choose_channel(state, 'forward'))

    async def test_food_effect_requires_matching_held_item_context(self):
        state = State()
        state.set('sensorimotor.models', {'m3': {'contexts': {'bread|none|hungry|20@1800': {'samples': 2, 'mean': {'food': 5}, 'm2': {}}}}})
        state.set('minecraft.sensed', {'heldItem':'dirt','hunger':.5})
        self.assertIsNone(choose_channel(state, 'food', contextual=True))
        state.set('minecraft.sensed', {'heldItem':'bread','hunger':.5})
        selected = choose_channel(state, 'food', contextual=True)
        self.assertEqual(selected['channel'], 'm3')
        self.assertEqual(selected['duration_ms'], 1800)
