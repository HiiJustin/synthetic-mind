import importlib.util
from pathlib import Path
import tempfile
import unittest
from synthetic_mind.stores import Database, StateStore, state_patch
from synthetic_mind.tempo import profile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dashboard', ROOT/'tools/mind_dashboard.py')
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


class ObservabilityTests(unittest.TestCase):
    def test_snapshot_reads_without_changing_state(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            path = Path(folder)/'state.db'
            db = Database(path)
            state = StateStore(db)
            state.set('minecraft.autonomous', False)
            before = db.connection.total_changes
            value = dashboard.read_snapshot(path)
            self.assertFalse(value['state']['minecraft.autonomous'])
            self.assertEqual(db.connection.total_changes, before)
            db.connection.close()

    def test_nested_trace_patch_preserves_small_change_without_copying_payload(self):
        before = {'candidate': {'payload': 'x'*9000, 'activation': .5}}
        after = {'candidate': {'payload': 'x'*9000, 'activation': .6}}
        self.assertEqual(state_patch(before, after), [{'path':['candidate','activation'],'value':.6}])

    def test_optional_tempo_defaults_and_bounds(self):
        self.assertEqual(profile('normal')['world_tps'], 20)
        self.assertEqual(profile('fast')['world_tps'], 40)
        self.assertLess(profile('fast')['sense_ms'], profile('normal')['sense_ms'])
        with self.assertRaises(ValueError): profile('unlimited')

    def test_routes_are_actual_completed_deliveries(self):
        from synthetic_mind.schemas import CognitiveEvent
        from synthetic_mind.stores import canonical
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            path=Path(folder)/'state.db';db=Database(path)
            event=CognitiveEvent('action_selection','embodied.selected',{})
            db.connection.execute('INSERT INTO events(id,root_id,source,kind,timestamp,fingerprint,body) VALUES(?,?,?,?,?,?,?)',(event.id,event.id,event.source,event.kind,event.timestamp,'test',canonical(event.to_dict())))
            db.connection.execute("INSERT INTO deliveries(event_id,module,status) VALUES(?,?,'done')",(event.id,'minecraft_embodiment'))
            db.connection.execute("INSERT INTO deliveries(event_id,module,status) VALUES(?,?,'pending')",(event.id,'subconscious_reward'))
            StateStore(db).set('runtime.active_modules',['action_selection','minecraft_embodiment','subconscious_reward'])
            result=dashboard.read_snapshot(path)
            self.assertEqual(len(result['activity']['routes']),1)
            self.assertEqual(result['activity']['routes'][0]['target'],'minecraft_embodiment')
            self.assertNotIn('subconscious_reward',result['activity']['latest'])
            db.close()

    def test_explanation_does_not_claim_success(self):
        from module_observatory import explanation
        value=explanation({'embodied.selection':{'winner':{'candidate':{'family':'muscle','parameters':{'channel':'m4','duration_ms':350}},'terms':{'uncertainty':1},'score':.7}}})
        self.assertIn('little evidence',value['reason'])
        self.assertIn('separate evidence',value['status'])
