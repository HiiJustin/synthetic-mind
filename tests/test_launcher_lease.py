import unittest,sys,socket
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import minecraft_setup
class LauncherLeaseTests(unittest.TestCase):
    def test_duplicate_launcher_rejected_and_lease_released(self):
        with socket.socket() as held:
            held.bind(('127.0.0.1',25566));held.listen(1)
            with self.assertRaisesRegex(RuntimeError,'Another Synthetic Mind'):minecraft_setup.launch()
        with patch.object(minecraft_setup,'launch_owned',return_value=7):
            self.assertEqual(minecraft_setup.launch(),7)
            self.assertEqual(minecraft_setup.launch(),7)
