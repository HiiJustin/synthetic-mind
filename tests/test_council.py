import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest

from synthetic_mind.config import Config
from synthetic_mind.minecraft import MinecraftEngine, MinecraftSession
from synthetic_mind.schemas import CognitiveEvent
import test_minecraft

PROJECT = test_minecraft.PROJECT


class CouncilTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=PROJECT / 'work')
        root = Path(self.temp.name)
        (root / 'config').mkdir()
        (root / 'config/brain.json').write_text(json.dumps({**json.loads((PROJECT / 'config/brain.json').read_text()), "architecture":"council"}))
        self.engine = MinecraftEngine(root, Config())
        self.engine.state.set("learning.enabled", False)
        self.engine.state.set("sensorimotor.developmental", False)
        await self.engine.start()
        self.session = MinecraftSession(self.engine, PROJECT / 'minecraft/config.json')
        self.sent = []
        async def send(content):
            self.sent.append(content)
        self.session.send = send
        await self.session.ingest('minecraft.connected', {'username': 'Test'})
        self.sent.clear()

    async def asyncTearDown(self):
        await self.engine.close()
        self.temp.cleanup()

    async def sense(self, **changes):
        sensed = {**test_minecraft.MinecraftTests.senses(), **changes}
        await self.session.ingest('minecraft.senses', sensed)
        return sensed

    async def test_generic_goal_does_not_match_farmland_substring(self):
        self.engine.state.set('brain.goal', 'explore and learn')
        await self.sense(visibleBlocks=[{'name':'farmland','position':{'x':0,'y':64,'z':4},'distance':4}])
        self.assertEqual(self.engine.state.get('council.bids')['goal']['skill'], 'explore')

    async def test_reached_landmark_does_not_keep_winning(self):
        self.engine.state.set('brain.goal', 'find oak log')
        await self.sense(position={'x':0,'y':64,'z':0},visibleBlocks=[{'name':'oak_log','position':{'x':0,'y':64,'z':1},'distance':1}])
        self.assertEqual(self.engine.state.get('council.bids')['goal']['skill'], 'explore')

    async def test_prolonged_standstill_gets_recovery_bid(self):
        self.engine.state.set('minecraft.autonomous', True)
        self.engine.state.set('navigation.progress', {'x':0,'z':0,'since':time.time()-40})
        await self.sense(position={'x':0,'y':64,'z':0})
        self.assertEqual(self.engine.state.get('council.winner')['role'], 'recovery')
        self.assertEqual(self.sent[-1]['action'], 'move')

    async def test_recovery_yields_to_discovery_when_forward_not_learned(self):
        self.engine.state.set('minecraft.autonomous', True)
        self.engine.state.set('learning.enabled', True)
        self.engine.state.set('sensorimotor.developmental', True)
        self.engine.state.set('sensorimotor.models', {'m2': {'samples':1, 'mean':{'forward':0}, 'failures':35}})
        self.engine.state.set('navigation.progress', {'x':0,'z':0,'since':time.time()-3600})
        await self.sense(position={'x':0,'y':64,'z':0})
        self.assertEqual(self.engine.state.get('council.winner')['role'], 'muscle_discovery')
        self.assertEqual(self.sent[-1]['action'], 'muscle')
        self.assertNotIn('recovery', self.engine.state.get('council.bids'))

    async def test_repeated_outcomes_do_not_leave_orphaned_busy_reservation(self):
        await self.sense()
        self.engine.state.set('minecraft.autonomous', True)
        self.engine.bus.publish(CognitiveEvent('motor_loop', 'cognition.cycle', {}))
        await self.engine.bus.drain()
        await self.session._flush()
        for _ in range(50):
            command = self.sent[-1]
            self.engine.state.set('council.next_motor', 0)
            await self.session.ingest('minecraft.action_result', {'command_id':command['id'], 'action':command['action'], 'verified':True})
            self.assertFalse(self.engine.state.get('minecraft.motor_busy'), 'Completed action must release its motor reservation')
            count = len(self.sent)
            self.engine.bus.publish(CognitiveEvent('runtime', 'cognition.cycle', {}))
            await self.engine.bus.drain()
            await self.session._flush()
            self.assertEqual(len(self.sent), count+1)
            self.assertIsNotNone(self.engine.state.get('council.last_motor'))

    async def test_competing_specialists_produce_safe_motor_without_model_call(self):
        self.engine.state.set('minecraft.autonomous', True)
        await self.sense()
        self.assertEqual(self.sent[-1]['action'], 'move')
        self.assertEqual(len(self.engine.state.get('council.bids')), 3)
        self.assertEqual(len(self.engine.state.get('council.disagreements')), 2)
        self.assertEqual(self.engine.governor.total_calls, 0)
        self.assertEqual(self.engine.log.get(self.sent[-1]['id']).source, 'executive')

    async def test_hazard_preempts_curiosity(self):
        self.engine.state.set('minecraft.autonomous', True)
        await self.sense(proximity={'obstructedAhead':False,'supportedAhead':True,'hazardAhead':True})
        self.assertEqual(self.sent[-1]['action'], 'look')
        self.assertEqual(self.engine.state.get('council.winner')['role'], 'preservation')

    async def test_rest_goal_beats_exploration(self):
        self.engine.state.set('minecraft.autonomous', True)
        self.engine.state.set('brain.goal', 'stay still and rest')
        await self.sense()
        self.assertEqual(self.sent, [])
        self.assertEqual(self.engine.state.get('council.winner')['skill'], 'rest')

    async def test_hunger_competes_and_selects_available_food(self):
        self.engine.state.set('minecraft.autonomous', True)
        await self.sense(hunger=0.6, inventory=[{'name':'bread','count':2}])
        self.assertEqual(self.sent[-1]['action'], 'eat')

    async def test_measured_outcomes_change_skill_confidence_and_persist(self):
        self.engine.state.set('minecraft.autonomous', True)
        await self.sense()
        command = self.sent[-1]
        await self.session.ingest('minecraft.action_result', {'command_id':command['id'],'action':'move','before':{'x':1,'y':4,'z':2},'position':{'x':1,'y':4,'z':1},'contact':False})
        record = self.engine.state.get('council.skills')['explore']
        self.assertEqual(record['successes'], 1)
        self.assertGreater(record['confidence'], 0.5)
        identity = self.engine.self_model.load().identity_id
        await self.engine.close()
        self.engine = MinecraftEngine(Path(self.temp.name), Config())
        self.assertEqual(self.engine.state.get('council.skills')['explore']['successes'], 1)
        self.assertEqual(self.engine.self_model.load().identity_id, identity)
        self.assertFalse(self.engine.state.get('minecraft.autonomous'))

    async def test_failed_move_causes_reorientation_instead_of_repeating(self):
        self.engine.state.set('minecraft.autonomous', True)
        await self.sense()
        command = self.sent[-1]
        await self.session.ingest('minecraft.action_result', {'command_id':command['id'],'action':'move','before':{'x':1,'y':4,'z':2},'position':{'x':1,'y':4,'z':2},'contact':True})
        self.engine.state.set('council.next_motor', 0)
        await self.sense(sequence=2)
        self.assertEqual(self.sent[-1]['action'], 'look')
        self.assertEqual(self.engine.state.get('council.skills')['explore']['failures'], 1)

    async def test_stale_senses_prevent_skill_execution(self):
        await self.sense()
        self.engine.state.set('minecraft.autonomous', True)
        self.engine.state.set('minecraft.sensed_at', time.time()-10)
        self.engine.bus.publish(CognitiveEvent('test','cognition.cycle',{}))
        await self.engine.bus.drain()
        await self.session._flush()
        self.assertEqual(self.sent, [])

    async def test_one_block_step_uses_bounded_jump_modifier(self):
        self.engine.state.set('minecraft.autonomous', True)
        await self.sense(proximity={'obstructedAhead':True,'supportedAhead':True,'hazardAhead':False,'canStepUp':True})
        self.assertEqual(self.sent[-1]['action'], 'move')
        self.assertTrue(self.sent[-1]['jump'])

    async def test_background_reflection_updates_self_model_from_measured_outcomes(self):
        self.engine.state.set('council.skills', {'explore': {'successes':3,'failures':1}})
        await self.engine.housekeeping()
        reflection = self.engine.state.get('council.reflection')
        self.assertEqual(reflection['successes'], 3)
        self.assertEqual(reflection['failures'], 1)
        self.assertAlmostEqual(self.engine.self_model.load().capabilities['minecraft_motor_reliability'], 4/6)

    async def test_world_change_invalidates_spatial_map_preserves_identity_and_skills(self):
        await self.sense()
        identity = self.engine.self_model.load().identity_id
        self.engine.state.set('council.skills', {'explore': {'successes':3,'failures':1}})
        await self.engine.close()
        root = Path(self.temp.name)
        (root / 'config/world.json').write_text(json.dumps({'id':'another-world'}))
        self.engine = MinecraftEngine(root, Config())
        self.assertEqual(self.engine.self_model.load().identity_id, identity)
        self.assertEqual(self.engine.state.get('minecraft.map'), {})
        self.assertEqual(self.engine.state.get('council.skills')['explore']['successes'], 3)
