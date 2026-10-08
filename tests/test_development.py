import test_council


class DevelopmentTests(test_council.CouncilTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.engine.state.set('sensorimotor.developmental', True)

    async def test_no_named_fallback_when_mapping_is_unknown(self):
        self.engine.state.set('minecraft.autonomous', True)
        await self.sense(hunger=0)
        self.assertEqual(self.sent, [])
        self.assertIn('no named-action fallback', self.engine.state.get('council.blocked_reason'))

    async def test_permuted_learned_channel_is_used_for_actual_executive_action(self):
        self.engine.state.set('sensorimotor.models', {'m6': {'samples': 3, 'mean': {'forward': .8}, 'm2': {}}})
        self.engine.state.set('minecraft.autonomous', True)
        await self.sense(hunger=0)
        self.assertEqual(self.sent[-1]['action'], 'muscle')
        self.assertEqual(self.sent[-1]['channel'], 'm6')
        self.assertEqual(self.sent[-1]['desired_effect'], 'forward')
        self.assertEqual(self.engine.log.get(self.sent[-1]['id']).source, 'executive')

    async def test_babbling_starts_without_a_learned_mapping(self):
        self.engine.state.set('learning.enabled', True)
        self.engine.state.set('minecraft.autonomous', True)
        await self.sense(hunger=0)
        self.assertEqual(self.sent[-1]['action'], 'muscle')
        self.assertEqual(self.sent[-1]['skill'], 'muscle_experiment')

    async def test_inhibition_does_not_deadlock_discovery(self):
        self.engine.state.set('learning.enabled', True)
        self.engine.state.set('minecraft.autonomous', True)
        await self.sense(hunger=0)
        failed = self.sent[-1]
        await self.session.ingest('minecraft.command_error', {'command_id':failed['id'],'action':'muscle','message':'Body reflex inhibited activation'})
        self.engine.state.set('council.next_motor', 0)
        await self.sense(hunger=0, sequence=2)
        self.assertEqual(self.sent[-1]['skill'], 'muscle_experiment')
        self.assertNotEqual(self.sent[-1]['channel'], failed['channel'])
        self.assertEqual(self.engine.status()['deliveries'].get('failed',0), 0)


for name in dir(test_council.CouncilTests):
    if name.startswith('test_') and name not in DevelopmentTests.__dict__:
        setattr(DevelopmentTests, name, None)
