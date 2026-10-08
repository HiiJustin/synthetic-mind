from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path

from synthetic_mind.config import Config
from synthetic_mind.minecraft import MinecraftEngine, MinecraftSession, find_node
from synthetic_mind.schemas import CognitiveEvent


PROJECT = Path(__file__).resolve().parents[1]


class MinecraftTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        scratch = PROJECT / "work"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.engine = MinecraftEngine(Path(self.temp.name), Config())
        await self.engine.start()
        self.session = MinecraftSession(self.engine, PROJECT / "minecraft/config.json")
        self.sent = []

        async def send(content):
            self.sent.append(content)

        self.session.send = send

    async def asyncTearDown(self):
        await self.engine.close()
        self.temp.cleanup()

    @staticmethod
    def senses():
        return {"sequence": 1, "position": {"x": 1, "y": 4, "z": 2},
            "orientation": {"yaw": 0.0, "pitch": 0.0}, "velocity": {"x": 0, "y": 0, "z": 0},
            "health": 20, "hunger": 0.2, "food": 16, "oxygen": 300, "onGround": True,
            "contact": {"horizontal": False, "vertical": True},
            "visibleBlocks": [{"name": "stone", "position": {"x": 1, "y": 4, "z": 0}, "distance": 2}],
            "visibleEntities": [], "proximity": {"obstructedAhead": False, "supportedAhead": True, "hazardAhead": False},
            "inventory": [], "timeOfDay": 1, "sensoryModel": "filtered-structured-v1"}

    async def connect(self):
        await self.session.ingest("minecraft.connected", {"username": "SyntheticMind", "version": "1.21.4"})

    async def test_senses_persist_without_grid_map_leakage(self):
        await self.connect()
        await self.session.ingest("minecraft.senses", self.senses())
        self.assertEqual(self.engine.state.get("minecraft.map")["1,4,0"]["name"], "stone")
        self.assertIsNone(self.engine.state.get("body.map"))
        self.assertEqual(self.engine.governor.total_calls, 0)
        self.assertTrue(self.engine.memory.retrieve("stone"))
        self.assertEqual(self.engine.status()["deliveries"].get("failed", 0), 0)

    async def test_only_executive_outputs_reach_transport(self):
        await self.connect()
        await self.session.propose({"text": "hello Minecraft"}, speech=True)
        self.assertEqual(self.sent[-1]["action"], "say")
        self.assertEqual(self.sent[-1]["text"], "hello Minecraft")
        command = self.sent[-1]
        self.assertEqual(self.engine.log.get(command["id"]).source, "executive")
        await self.session.propose({"text": "/op someone"}, speech=True)
        self.assertEqual(self.sent[-1], command)

    async def test_chat_feedback_does_not_generate_unprompted_reply(self):
        await self.connect()
        before = len(self.sent)
        await self.session.ingest("minecraft.chat", {"username": "Player", "text": "normal conversation"})
        self.assertEqual(len(self.sent), before)
        await self.session.ingest("minecraft.chat", {"username": "Player", "text": "!mind hello"})
        self.assertEqual(self.sent[-1]["text"], "[deterministic] I heard: hello")

    async def test_auto_off_then_reactive_move_and_outcome_learning(self):
        await self.connect()
        before = len(self.sent)
        await self.session.ingest("minecraft.senses", self.senses())
        self.assertEqual(len(self.sent), before)
        self.engine.state.set("minecraft.autonomous", True)
        await self.session.ingest("minecraft.senses", {**self.senses(), "sequence": 2})
        self.assertEqual(self.sent[-1]["action"], "move")
        self.assertEqual(self.sent[-1]["control"], "forward")
        await self.session.ingest("minecraft.action_result", {"command_id": self.sent[-1]["id"], "action": "move", "control": "forward",
            "before": {"x": 0, "y": 4, "z": 0}, "position": {"x": 0, "y": 4, "z": -1}, "contact": False})
        self.assertFalse(self.engine.state.get("minecraft.motor_busy"))
        self.assertEqual(self.engine.state.get("minecraft.motor_learning")["forward"]["mean_distance"], 1)

    async def test_proximity_turns_away_from_ledge(self):
        await self.connect()
        self.engine.state.set("minecraft.autonomous", True)
        snapshot = self.senses()
        snapshot["proximity"]["supportedAhead"] = False
        await self.session.ingest("minecraft.senses", snapshot)
        self.assertEqual(self.sent[-1]["action"], "look")

    async def test_disconnect_disables_autonomy(self):
        await self.connect()
        self.engine.state.set("minecraft.autonomous", True)
        await self.session.ingest("minecraft.disconnected", {"reason": "test"})
        self.assertFalse(self.engine.state.get("minecraft.autonomous"))
        self.assertFalse(self.engine.state.get("minecraft.connection")["connected"])

    async def test_reconnect_retains_identity_but_does_not_replay_commands(self):
        await self.connect()
        await self.session.propose({"action": "move", "control": "forward"})
        identity = self.engine.self_model.load().identity_id
        await self.engine.close()
        self.engine = MinecraftEngine(Path(self.temp.name), Config())
        await self.engine.start()
        self.assertEqual(self.engine.self_model.load().identity_id, identity)
        self.assertFalse(self.engine.state.get("minecraft.autonomous"))
        session = MinecraftSession(self.engine, PROJECT / "minecraft/config.json")
        calls = []

        async def send(content):
            calls.append(content)

        session.send = send
        await session._flush()
        self.assertEqual(calls, [])


class BridgeProcessTests(unittest.TestCase):
    def test_real_bridge_handles_connection_refused_cleanly(self):
        if not (PROJECT / "minecraft/node_modules/mineflayer").exists():
            self.skipTest("Run MINECRAFT_SETUP.cmd to install the optional bridge")
        scratch = PROJECT / "work"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            with socket.socket() as reserved:
                reserved.bind(("127.0.0.1", 0))
                port = reserved.getsockname()[1]
            config = json.loads((PROJECT / "minecraft/config.json").read_text())
            config["port"] = port
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config))
            process = subprocess.Popen([find_node(), str(PROJECT / "minecraft/bridge.js"), str(path)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=PROJECT / "minecraft")
            try:
                # Keep stdin open so the connection itself, not EOF, exercises shutdown.
                process.wait(timeout=10)
                stdout = process.stdout.read()
                stderr = process.stderr.read()
                self.assertEqual(process.returncode, 0, stderr)
                records = [json.loads(line) for line in stdout.splitlines()]
                self.assertTrue(any(record["kind"] == "minecraft.error" for record in records))
                self.assertTrue(any(record["kind"] == "minecraft.disconnected" for record in records))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream:
                        stream.close()
