import time
import test_council
from synthetic_mind.experiments import valid_hand_action


class ExperimentTests(test_council.CouncilTests):
    # Use the same engine fixture, without inheriting the movement-only tests.
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.engine.state.set('learning.enabled', True)
        self.engine.state.set('sensorimotor.models', {f'm{i}': {'samples': 2, 'mean': {'yaw': 0.4}} for i in range(7)})

    async def test_experiment_effect_is_measured_then_changes_future_choice(self):
        self.engine.state.set('minecraft.autonomous', True)
        await self.sense(hunger=0, inventory=[{'name': 'bread', 'count': 2}])
        command = self.sent[-1]
        self.assertEqual(command['action'], 'inventory')
        self.assertEqual(self.engine.log.get(command['id']).source, 'executive')
        await self.session.ingest('minecraft.action_result', {'command_id': command['id'], 'action': 'inventory', 'verified': True, 'after': {'inventory': [{'name': 'bread', 'count': 2}]}})
        self.engine.state.set('council.next_motor', 0)
        await self.sense(sequence=2, hunger=0, inventory=[{'name': 'bread', 'count': 2}])
        self.assertEqual(self.sent[-1]['action'], 'equip')
        self.assertEqual(self.engine.state.get('learning.actions')['inventory:body']['successes'], 1)
        self.assertEqual(self.engine.status()['deliveries'].get('failed', 0), 0)

    async def test_ack_without_effect_is_not_success(self):
        await self.sense(hunger=0, inventory=[{'name': 'bread', 'count': 2}])
        await self.session.propose({'action': 'equip', 'item': 'bread'})
        command = self.sent[-1]
        await self.session.ingest('minecraft.action_result', {'command_id': command['id'], 'action': 'equip', 'ok': True})
        self.assertEqual(self.engine.state.get('learning.actions')['equip:bread']['failures'], 1)
        self.assertFalse(self.engine.state.get('learning.last_lesson')['success'])

    async def test_failed_action_cools_down_and_unrelated_ack_is_ignored(self):
        await self.sense(hunger=0, inventory=[{'name': 'bread', 'count': 2}])
        await self.session.propose({'action': 'equip', 'item': 'bread'})
        command = self.sent[-1]
        await self.session.ingest('minecraft.action_result', {'command_id': 'unrelated', 'action': 'equip', 'verified': True})
        self.assertEqual(self.engine.state.get('learning.actions', {}), {})
        await self.session.ingest('minecraft.command_error', {'command_id': command['id'], 'message': 'cancelled'})
        self.assertGreater(self.engine.state.get('learning.actions')['equip:bread']['retry_after'], time.time())

    async def test_auto_off_still_senses_affordances_without_acting(self):
        await self.sense(hunger=0, inventory=[{'name': 'bread', 'count': 2}])
        self.assertTrue(self.engine.state.get('learning.affordances'))
        self.assertEqual(self.sent, [])

    async def test_restart_keeps_evidence_abandons_pending_action(self):
        from synthetic_mind.minecraft import MinecraftEngine
        from synthetic_mind.config import Config
        from pathlib import Path
        await self.sense()
        await self.session.propose({'action': 'inventory'})
        await self.session.ingest('minecraft.action_result', {'command_id': self.sent[-1]['id'], 'action': 'inventory', 'verified': True})
        identity = self.engine.self_model.load().identity_id
        await self.engine.close()
        self.engine = MinecraftEngine(Path(self.temp.name), Config())
        self.assertEqual(self.engine.state.get('learning.actions')['inventory:body']['successes'], 1)
        self.assertEqual(self.engine.state.get('learning.pending'), {})
        self.assertEqual(self.engine.self_model.load().identity_id, identity)

    async def test_critic_rejects_hidden_and_underfoot_dig(self):
        sensed = await self.sense()
        self.assertFalse(valid_hand_action({'action':'dig','target':{'x':1,'y':3,'z':2},'block':'dirt'}, sensed))
        self.assertFalse(valid_hand_action({'action':'equip','item':'diamond_sword'}, sensed))


# Keep the shared fixture, not inherited movement-specific tests.
for name in dir(test_council.CouncilTests):
    if name.startswith('test_') and name not in ExperimentTests.__dict__:
        setattr(ExperimentTests, name, None)
