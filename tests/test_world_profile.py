import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('world_profile', PROJECT / 'tools/world_profile.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WorldProfileTests(unittest.TestCase):
    def test_new_profile_preserves_old_world_and_can_restore_properties(self):
        with tempfile.TemporaryDirectory(dir=PROJECT / 'work') as scratch:
            root = Path(scratch)
            (root / 'config').mkdir()
            (root / 'config/world.json').write_text((PROJECT / 'config/world.json').read_text())
            server = root / 'minecraft/server'
            old = server / 'laboratory-world'
            old.mkdir(parents=True)
            (old / 'evidence.txt').write_text('old world remains')
            original = 'level-name=laboratory-world\nlevel-type=minecraft\\:flat\nlevel-seed=12345\n'
            (server / 'server.properties').write_text(original)
            backup = module.apply_profile(root, check_running=False)
            self.assertEqual((backup / 'server.properties').read_text(), original)
            self.assertEqual((old / 'evidence.txt').read_text(), 'old world remains')
            new = (server / 'server.properties').read_text()
            self.assertIn('level-type=minecraft:normal', new)
            self.assertIn('generate-structures=true', new)
            self.assertIsNone(module.apply_profile(root, check_running=False))

    def test_world_name_cannot_escape_server_directory(self):
        with tempfile.TemporaryDirectory(dir=PROJECT / 'work') as scratch:
            root = Path(scratch)
            (root / 'config').mkdir()
            (root / 'config/world.json').write_text(json.dumps({'level_name':'../../outside'}))
            with self.assertRaises(ValueError):
                module.apply_profile(root, check_running=False)
