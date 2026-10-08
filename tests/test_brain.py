import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from synthetic_mind.config import Config
from synthetic_mind.minecraft import MinecraftEngine, MinecraftSession
from synthetic_mind.minecraft_brain import MinecraftBrain, SCHEMA, REVIEW_SCHEMA
from synthetic_mind.schemas import CognitiveEvent
import test_minecraft
PROJECT = test_minecraft.PROJECT


DECISION = {"observation": "Stone is visible.", "focus": "Explore safely", "action": "forward",
    "expected_outcome": "Move a short distance", "speech": "I see stone.", "memory": "Stone was seen nearby.", "confidence": 0.8}


class GatedBackend:
    schema = SCHEMA
    metrics = {}

    def __init__(self, approved=True):
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.approved = approved
        self.calls = 0

    async def generate(self, **kwargs):
        self.calls += 1
        if self.schema == REVIEW_SCHEMA:
            return json.dumps({"approved": self.approved, "reason": "Reviewed independently"})
        self.entered.set()
        await self.release.wait()
        decision = dict(DECISION)
        decision["observation"] = self.schema["properties"]["observation"].get("const", decision["observation"])
        if self.schema["properties"]["action"]["enum"] == ["wait"]:
            decision["action"] = "wait"
        return json.dumps(decision)


class BrainTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=PROJECT / "work")
        root = Path(self.temp.name)
        (root / "config").mkdir()
        config = json.loads((PROJECT / "config/brain.json").read_text())
        config["architecture"] = "legacy"
        (root / "config/brain.json").write_text(json.dumps(config))
        self.engine = MinecraftEngine(root, Config())
        await self.engine.start()
        self.session = MinecraftSession(self.engine, PROJECT / "minecraft/config.json")
        self.sent = []

        async def send(content):
            self.sent.append(content)

        self.session.send = send
        self.backend = GatedBackend()
        self.brain = MinecraftBrain(self.session, self.engine.brain_config, self.backend)
        await self.session.ingest("minecraft.connected", {"username": "SyntheticMind"})
        await self.session.ingest("minecraft.senses", test_minecraft.MinecraftTests.senses())
        self.sent.clear()

    async def asyncTearDown(self):
        await self.engine.close()
        self.temp.cleanup()

    async def request(self):
        self.engine.bus.publish(CognitiveEvent("operator", "brain.request", {"text": "What do you notice?"}))
        await self.engine.bus.drain()

    async def test_large_learned_state_is_compacted_without_blocking_inference(self):
        self.engine.state.set("council.skills", {"history": "learned outcome " * 4000})
        await self.request()
        self.backend.release.set()
        await self.brain.tick()
        sizes = self.engine.state.get("brain.context_size")
        self.assertTrue(sizes["compacted"])
        self.assertLessEqual(sizes["sent"], 3800)
        self.assertEqual(self.backend.calls, 2)
        self.assertFalse(self.brain.pending)

    async def test_only_named_operator_can_start_and_stop_from_chat(self):
        await self.session.ingest("minecraft.chat", {"username": "stranger", "text": "!start"})
        self.assertFalse(self.engine.state.get("minecraft.autonomous"))
        await self.session.ingest("minecraft.chat", {"username": "Firmlygrasp1t", "text": "!start"})
        self.assertTrue(self.engine.state.get("minecraft.autonomous"))
        await self.session.ingest("minecraft.chat", {"username": "firmlygrasp1t", "text": "!stop"})
        self.assertFalse(self.engine.state.get("minecraft.autonomous"))
        self.assertEqual(self.sent[-1]["action"], "stop")

    async def test_shared_backend_distinct_roles_and_executive_gate(self):
        await self.request()
        self.backend.release.set()
        await self.brain.tick()
        self.assertEqual(self.backend.calls, 2)
        self.assertEqual([command["action"] for command in self.sent], ["say"])
        self.assertEqual(self.engine.log.get(self.sent[0]["id"]).source, "executive")
        recent = self.engine.log.recent(50)
        self.assertTrue(any(event.source == "cognitive_critic" and event.kind == "brain.review" for event in recent))
        self.assertTrue(self.engine.state.get("cognition.autobiography"))
        self.assertEqual(self.engine.status()["deliveries"].get("failed", 0), 0, self.engine.status()["modules"])

    async def test_senses_continue_during_inference_stop_invalidates_motor(self):
        self.engine.state.set("minecraft.autonomous", True)
        await self.request()
        task = asyncio.create_task(self.brain.tick())
        await asyncio.wait_for(self.backend.entered.wait(), 1)
        await asyncio.wait_for(self.session.ingest("minecraft.senses", {**test_minecraft.MinecraftTests.senses(), "sequence": 20}), 1)
        self.assertEqual(self.engine.state.get("minecraft.sensed")["sequence"], 20)
        self.engine.state.set("minecraft.autonomous", False)
        await self.session.propose({"action": "stop"})
        self.backend.release.set()
        await task
        self.assertFalse(any(command["action"] == "move" for command in self.sent))

    async def test_critic_veto_blocks_speech_and_movement(self):
        self.engine.state.set("minecraft.autonomous", True)
        self.backend.approved = False
        await self.request()
        self.backend.release.set()
        await self.brain.tick()
        self.assertEqual(self.sent, [])
        self.assertFalse(self.engine.state.get("brain.last_review")["approved"])

    async def test_budget_survives_restart_and_defers_new_requests(self):
        self.engine.state.set("brain.budget", [{"time": __import__("time").time(), "tokens": 100} for _ in range(4)])
        await self.request()
        await self.brain.tick()
        self.assertEqual(self.backend.calls, 0)
        await self.engine.close()
        self.engine = MinecraftEngine(Path(self.temp.name), Config())
        self.assertEqual(len(self.engine.state.get("brain.budget")), 4)

    async def test_hazard_prevents_forward_action(self):
        sensed = test_minecraft.MinecraftTests.senses()
        sensed["proximity"]["hazardAhead"] = True
        self.assertIsNone(MinecraftBrain.motor("forward", sensed))

    async def test_actual_outcome_is_linked_to_its_decision(self):
        self.engine.state.set("minecraft.autonomous", True)
        await self.request()
        self.backend.release.set()
        await self.brain.tick()
        move = next(command for command in self.sent if command["action"] == "move")
        await self.session.ingest("minecraft.action_result", {"command_id": move["id"], "action": "move", "before": {"x": 0, "y": 4, "z": 0}, "position": {"x": 0, "y": 4, "z": 0}, "contact": True})
        outcome = self.engine.state.get("brain.outcome")
        self.assertEqual(outcome["prediction"]["action"], "forward")
        self.assertEqual(outcome["distance"], 0)
        self.assertTrue(outcome["prediction_error"])
        self.assertEqual(self.engine.status()["deliveries"].get("failed", 0), 0)

    async def test_speech_ack_does_not_release_motor_busy(self):
        self.engine.state.set("minecraft.motor_busy", True)
        await self.session.ingest("minecraft.action_result", {"action": "say", "ok": True})
        self.assertTrue(self.engine.state.get("minecraft.motor_busy"))
