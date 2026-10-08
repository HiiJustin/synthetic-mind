from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from synthetic_mind.config import Config, GovernorConfig, RuntimeConfig, WorkspaceConfig
from synthetic_mind.engine import Engine
from synthetic_mind.schemas import CognitiveEvent
from synthetic_mind.scheduler import BudgetExceeded, ComputeGovernor, Scheduler
from synthetic_mind.stores import Database, canonical
from synthetic_mind.workspace import GlobalWorkspace


PROJECT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        scratch = PROJECT / "work"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.directory = Path(self.temporary.name)
        self.engine = Engine(self.directory, Config())
        await self.engine.start()

    async def asyncTearDown(self) -> None:
        if not self.engine.closed:
            await self.engine.close()
        self.temporary.cleanup()

    async def test_database_initialization_and_migrations(self) -> None:
        connection = self.engine.db.connection
        self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"events", "edges", "module_traces", "deliveries", "state", "goals", "episodes"} <= tables)

    async def test_restart_identity_goals_memory_and_body(self) -> None:
        identity = self.engine.self_model.load().identity_id
        message = await self.engine.submit("Remember the violet lantern")
        await self.engine.request_goal("Find food")
        await self.engine.step("east")
        known = self.engine.state.get("body.map")
        await self.engine.close()
        self.engine = Engine(self.directory, Config())
        await self.engine.start()
        model = self.engine.self_model.load()
        self.assertEqual(model.identity_id, identity)
        self.assertGreater(model.active_seconds, 0)
        self.assertEqual(self.engine.goals.all()[0].description, "Find food")
        self.assertEqual(len(model.active_goals), 1)
        self.assertTrue(self.engine.memory.retrieve("violet"))
        self.assertEqual(self.engine.log.get(message).content["text"], "Remember the violet lantern")
        self.assertEqual(self.engine.world.observe()["position"], [2, 2])
        self.assertTrue(set(known) <= set(self.engine.state.get("body.map")))
        self.assertFalse(self.engine.state.get("runtime.autonomous"))

    async def test_upgrade_version_one_preserves_history(self) -> None:
        event_id = await self.engine.submit("preserve during migration")
        identity = self.engine.self_model.load().identity_id
        await self.engine.close()
        connection = sqlite3.connect(self.directory / "data" / "state.db")
        connection.executescript("DROP TABLE module_traces; PRAGMA user_version=1;")
        connection.close()
        self.engine = Engine(self.directory, Config())
        await self.engine.start()
        self.assertEqual(self.engine.db.connection.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(self.engine.self_model.load().identity_id, identity)
        self.assertEqual(self.engine.log.get(event_id).content["text"], "preserve during migration")

    async def test_publish_subscribe_and_causal_edges(self) -> None:
        root = await self.engine.submit("hello world")
        children = self.engine.log.inspect(root)["children"]
        self.assertTrue(children)
        perception = next(self.engine.log.get(child) for child in children if self.engine.log.get(child).kind == "perception.text")
        self.assertEqual(perception.content["words"], 2)
        self.assertEqual(perception.root_id, root)
        traces = self.engine.log.inspect(root)["module_traces"]
        self.assertTrue(any(trace["module"] == "perception" and trace["output_event_ids"] for trace in traces))
        speech = [event for event in self.engine.log.recent(20) if event.kind == "executive.speech"]
        self.assertEqual(len(speech), 1)
        self.assertEqual(speech[0].source, "executive")

    async def test_event_and_edge_history_is_immutable(self) -> None:
        root = await self.engine.submit("immutable history")
        for query in ("UPDATE events SET kind='changed' WHERE id=?", "DELETE FROM events WHERE id=?",
                      "DELETE FROM edges WHERE parent_id=?"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.engine.db.connection.execute(query, (root,))

    async def test_unknown_parent_is_rejected_without_partial_event(self) -> None:
        event = CognitiveEvent("test", "unknown", {}, ("missing",))
        with self.assertRaises(KeyError):
            self.engine.bus.publish(event)
        with self.assertRaises(KeyError):
            self.engine.log.get(event.id)

    async def test_duplicate_ids_and_semantic_loop_suppression(self) -> None:
        event = CognitiveEvent("test", "loop", {"value": 1})
        self.assertEqual(self.engine.bus.publish(event), event.id)
        self.assertIsNone(self.engine.bus.publish(event))
        repeated = CognitiveEvent("test", "loop", {"value": 1}, (event.id,))
        self.assertIsNone(self.engine.bus.publish(repeated))
        # Same content in an independent experience must remain valid.
        separate = CognitiveEvent("test", "loop", {"value": 1})
        self.assertEqual(self.engine.bus.publish(separate), separate.id)
        self.assertEqual(self.engine.bus.suppressed, 2)

    async def test_changing_payload_loop_has_hop_limit(self) -> None:
        class Loop:
            name, priority, subscriptions = "loop_test", 1, {"test.loop"}

            async def on_event(self, event):
                return [CognitiveEvent(self.name, "test.loop", {"n": event.content["n"] + 1})]

        self.engine.registry.register(Loop())
        self.engine.bus.publish(CognitiveEvent("test", "test.loop", {"n": 0}))
        await self.engine.bus.drain()
        count = self.engine.db.connection.execute("SELECT count(*) FROM events WHERE kind='test.loop'").fetchone()[0]
        self.assertEqual(count, self.engine.config.runtime.max_hops + 1)
        self.assertGreater(self.engine.bus.suppressed, 0)

    async def test_pending_delivery_survives_abrupt_close(self) -> None:
        event = CognitiveEvent("user", "user.text", {"text": "durable pending message"})
        self.engine.bus.publish(event)
        self.engine.db.close()
        self.engine.closed = True
        self.engine = Engine(self.directory, Config())
        await self.engine.start()
        statuses = self.engine.log.inspect(event.id)["deliveries"]
        self.assertTrue(all(item["status"] == "done" for item in statuses))
        self.assertTrue(self.engine.memory.retrieve("durable"))

    async def test_handler_failure_rolls_back_state_and_children(self) -> None:
        state = self.engine.state

        class Broken:
            name, priority, subscriptions = "broken", 1, {"test.failure"}

            async def on_event(self, event):
                state.set("should_not_commit", True)
                raise ValueError("intentional test failure")

        self.engine.registry.register(Broken())
        event = CognitiveEvent("test", "test.failure", {})
        self.engine.bus.publish(event)
        await self.engine.bus.drain()
        self.assertIsNone(state.get("should_not_commit"))
        self.assertEqual(self.engine.log.inspect(event.id)["deliveries"][0]["status"], "failed")
        self.assertEqual(state.get("health.broken")["failures"], 1)
        self.assertTrue(any(child.kind == "runtime.module_error" for child in self.engine.log.recent()))

    async def test_queue_backpressure_is_atomic(self) -> None:
        self.engine.bus.config = replace(self.engine.config.runtime, max_pending=1)
        event = CognitiveEvent("user", "user.text", {"text": "too many subscribers"})
        with self.assertRaises(OverflowError):
            self.engine.bus.publish(event)
        with self.assertRaises(KeyError):
            self.engine.log.get(event.id)

    async def test_expired_event_is_not_processed(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        event = CognitiveEvent("user", "user.text", {"text": "expired"}, timestamp=old, ttl_seconds=1)
        self.engine.bus.publish(event)
        await self.engine.bus.drain()
        self.assertTrue(all(row["status"] == "expired" for row in self.engine.log.inspect(event.id)["deliveries"]))
        self.assertEqual(self.engine.log.inspect(event.id)["children"], [])

    async def test_clean_shutdown_and_idempotent_close(self) -> None:
        await self.engine.close()
        await self.engine.close()
        self.assertTrue(self.engine.scheduler.closed)
        records = [json.loads(line) for line in (self.directory / "data" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[-1]["kind"], "runtime.shutdown")
        db = sqlite3.connect(self.directory / "data" / "state.db")
        try:
            self.assertEqual(db.execute("SELECT count(*) FROM deliveries WHERE status='pending'").fetchone()[0], 0)
        finally:
            db.close()

    async def test_idle_has_zero_model_calls_and_no_body_motion(self) -> None:
        before = self.engine.world.observe()["step"]
        for _ in range(4):
            await self.engine.housekeeping()
        self.assertEqual(self.engine.governor.total_calls, 0)
        self.assertEqual(self.engine.world.observe()["step"], before)
        self.assertGreater(self.engine.self_model.load().active_seconds, 0)

    async def test_mock_only_on_explicit_request(self) -> None:
        await self.engine.submit("hello")
        self.assertEqual(self.engine.governor.total_calls, 0)
        await self.engine.reflect()
        self.assertEqual(self.engine.governor.total_calls, 1)
        calls = [event for event in self.engine.log.recent() if event.kind == "model.call"]
        self.assertEqual(calls[0].content["backend"], "mock")

    async def test_limited_vision_and_occlusion(self) -> None:
        self.assertNotIn("5,2", self.engine.state.get("body.map"))
        self.assertFalse(any(cell["kind"] == "food" for cell in self.engine.world.observe()["visible"]))
        await self.engine.step("east")
        # Wall at (3,2) blocks sight to (4,2), within the radius.
        positions = {tuple(cell["position"]) for cell in self.engine.world.observe()["visible"]}
        self.assertNotIn((4, 2), positions)

    async def test_body_reaches_food_around_obstacle(self) -> None:
        results = []
        for _ in range(20):
            results.extend(await self.engine.step())
            if any(event.content.get("ate") for event in results):
                break
        ate = [event for event in results if event.kind == "body.result" and event.content["ate"]]
        self.assertEqual(len(ate), 1)
        self.assertEqual(ate[0].content["position"], [5, 2])
        self.assertLess(self.engine.world.observe()["hunger"], 0.1)
        self.assertIn("ate food", self.engine.self_model.load().autobiographical_summary)
        self.assertEqual(self.engine.governor.total_calls, 0)
        self.assertEqual(self.engine.status()["deliveries"].get("failed", 0), 0)
        self.assertFalse(any(cell["kind"] == "food" for cell in self.engine.state.get("body.sensed")["visible"]))

    async def test_prediction_error_learns_and_survives_restart(self) -> None:
        # Hide a real wall from the agent's map to force a false expectation.
        await self.engine.step("east")
        known = self.engine.state.get("body.map")
        known["3,2"] = "empty"
        self.engine.state.set("body.map", known)
        # Directly dispatch the approved action without a new observation correcting the map.
        self.engine.bus.publish(CognitiveEvent("executive", "executive.action", {"action": "east"}))
        await self.engine.bus.drain()
        first = self.engine.state.get("learning.metrics")["errors"]
        self.assertEqual(first, 1)
        transition = self.engine.state.get("learning.transitions")["2,2:east"]
        self.assertTrue(transition["blocked"])
        await self.engine.close()
        self.engine = Engine(self.directory, Config())
        await self.engine.start()
        await self.engine.step("east")
        self.assertEqual(self.engine.state.get("learning.metrics")["errors"], first)
        self.assertEqual(self.engine.state.get("learning.transitions")["2,2:east"]["samples"], 2)

    async def test_replans_after_new_obstacle_and_retains_it(self) -> None:
        await self.engine.step()
        await self.engine.step()
        self.assertEqual(self.engine.world.observe()["position"], [2, 1])
        truth = self.engine.state.get("world.truth")
        truth["walls"].append([3, 1])
        self.engine.state.set("world.truth", truth)
        await self.engine.close()
        self.engine = Engine(self.directory, Config())
        await self.engine.start()
        ate = False
        for _ in range(25):
            results = await self.engine.step()
            if any(event.content.get("ate") for event in results):
                ate = True
                break
        self.assertTrue(ate)
        self.assertEqual(self.engine.state.get("body.map")["3,1"], "wall")
        self.assertEqual(self.engine.world.observe()["position"], [5, 2])

    async def test_invalid_action_cannot_move_body(self) -> None:
        before = self.engine.world.observe()["step"]
        results = await self.engine.step("teleport")
        self.assertTrue(any(event.kind == "action.rejected" for event in results))
        self.assertEqual(self.engine.world.observe()["step"], before)

    async def test_module_lesion_removes_autonomous_actions(self) -> None:
        del self.engine.registry.modules["planner"]
        results = await self.engine.step()
        self.assertFalse(any(event.kind == "body.result" for event in results))
        self.assertEqual(self.engine.world.observe()["position"], [1, 2])

    async def test_traces_capture_state_and_memory_effects(self) -> None:
        await self.engine.submit("memory trace")
        observed = self.engine.log.recent(100)
        self.assertTrue(any(trace["memory_writes"] for event in observed for trace in self.engine.log.inspect(event.id)["module_traces"]))
        self.assertTrue(any(trace["state_writes"] for event in observed for trace in self.engine.log.inspect(event.id)["module_traces"]))

    async def test_large_map_trace_records_delta_instead_of_full_snapshot(self) -> None:
        state = self.engine.state
        original = {str(index): "x" * 80 for index in range(500)}
        state.set("large_map", original)

        class MapUpdate:
            name, priority, subscriptions = "map_update", 1, {"test.map_update"}

            async def on_event(self, event):
                mapping = state.get("large_map")
                mapping["42"] = "new observation"
                state.set("large_map", mapping)
                return []

        self.engine.registry.register(MapUpdate())
        event = CognitiveEvent("test", "test.map_update", {})
        self.engine.bus.publish(event)
        await self.engine.bus.drain()
        writes = self.engine.log.inspect(event.id)["module_traces"][0]["state_writes"]
        delta = next(write for write in writes if write["namespace"] == "large_map")
        self.assertNotIn("value", delta)
        self.assertEqual(delta["changed"], {"42": "new observation"})
        self.assertEqual(delta["removed"], [])
        self.assertEqual(state.get("large_map")["42"], "new observation")


class WorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        scratch = PROJECT / "work"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.engine = Engine(Path(self.temporary.name), Config())
        self.workspace = GlobalWorkspace(self.engine.state, WorkspaceConfig(capacity=2))

    async def asyncTearDown(self) -> None:
        await self.engine.close()
        self.temporary.cleanup()

    @staticmethod
    def candidate(key: str, strength: float) -> CognitiveEvent:
        return CognitiveEvent("test", "attention.candidate", {"key": key, "origin_id": key,
            "kind": "test", "payload": {}, "features": {name: strength for name in
            ("salience", "novelty", "goal_relevance", "urgency", "confidence")}})

    async def test_workspace_capacity_and_scoring(self) -> None:
        for key, strength in (("a", 0.6), ("b", 0.7), ("c", 0.9), ("d", 0.8)):
            await self.workspace.on_event(self.candidate(key, strength))
        self.assertEqual([item["key"] for item in self.workspace.items()], ["c", "d"])
        self.assertAlmostEqual(GlobalWorkspace.score({name: 1.0 for name in
            ("salience", "novelty", "goal_relevance", "urgency", "confidence")}), 1.0)

    async def test_corroboration_ignition_and_duplicate_support(self) -> None:
        self.assertEqual(await self.workspace.on_event(self.candidate("weak", 0.45)), [])
        support = CognitiveEvent("memory", "attention.support", {"key": "weak"})
        broadcast = await self.workspace.on_event(support)
        self.assertEqual(broadcast[0].kind, "workspace.broadcast")
        self.assertAlmostEqual(self.workspace.items()[0]["activation"], 0.6)
        self.assertEqual(await self.workspace.on_event(support), [])
        self.assertAlmostEqual(self.workspace.items()[0]["activation"], 0.6)

    async def test_retention_decay_and_expiration(self) -> None:
        await self.workspace.on_event(self.candidate("a", 0.6))
        await self.workspace.on_event(CognitiveEvent("clock", "clock.tick", {}))
        self.assertEqual(len(self.workspace.items()), 1)
        for _ in range(8):
            await self.workspace.on_event(CognitiveEvent("clock", "clock.tick", {}))
        self.assertEqual(self.workspace.items(), [])
        candidate = self.candidate("old", 1.0)
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.assertEqual(await self.workspace.on_event(replace(candidate, timestamp=old)), [])


class ComputeTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_priority_and_stable_ties(self) -> None:
        scheduler = Scheduler()
        order = []

        async def record(value):
            order.append(value)

        for name, priority in (("background", 90), ("first", 1), ("second", 1)):
            scheduler.schedule(name, lambda n=name: record(n), priority)
        await scheduler.run()
        self.assertEqual(order, ["first", "second", "background"])
        await scheduler.close()
        with self.assertRaises(RuntimeError):
            scheduler.schedule("late", lambda: record("late"))

    async def test_governor_calls_tokens_and_window(self) -> None:
        clock = [0.0]
        governor = ComputeGovernor(GovernorConfig(calls_per_minute=2, tokens_per_minute=10), lambda: clock[0])

        async def generate():
            return "result"

        self.assertEqual(await governor.execute(generate, input_tokens=3, output_tokens=3), "result")
        with self.assertRaises(BudgetExceeded):
            await governor.execute(generate, input_tokens=3, output_tokens=3)
        await governor.execute(generate, input_tokens=1, output_tokens=1)
        with self.assertRaises(BudgetExceeded):
            await governor.execute(generate, input_tokens=0, output_tokens=0)
        clock[0] = 60.0
        await governor.execute(generate, input_tokens=3, output_tokens=3)
        self.assertEqual(governor.active, 0)

    async def test_governor_concurrency_and_timeout(self) -> None:
        governor = ComputeGovernor(GovernorConfig(max_seconds_per_call=0.03))
        started = asyncio.Event()

        async def blocked():
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(governor.execute(blocked, input_tokens=1, output_tokens=1))
        await started.wait()
        with self.assertRaises(BudgetExceeded):
            await governor.execute(blocked, input_tokens=1, output_tokens=1)
        with self.assertRaises(TimeoutError):
            await task
        self.assertEqual(governor.active, 0)


class ConfigAndProcessTests(unittest.TestCase):
    def test_demo_continues_to_commands_and_keeps_identity(self) -> None:
        scratch = PROJECT / "work"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = Path(directory) / "state.db"
            env = {**os.environ, "PYTHONPATH": str(PROJECT / "src")}
            command = [sys.executable, "-B", "-m", "synthetic_mind", "--db", str(path)]
            result = subprocess.run(command + ["demo"], input="/map\nhello after demo\n/quit\n",
                                    text=True, capture_output=True, cwd=PROJECT, env=env, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Food reached and eaten", result.stdout)
            self.assertIn("Entering interactive mode", result.stdout)
            self.assertIn("mind>", result.stdout)
            self.assertIn("[speech] [deterministic] Recorded your message: hello after demo", result.stdout)
            db = sqlite3.connect(path)
            try:
                first_identity = json.loads(db.execute("SELECT value FROM state WHERE namespace='self_model'").fetchone()[0])["identity_id"]
            finally:
                db.close()
            # Batch mode still supports a successful one-shot exit, preserving the identity.
            second = subprocess.run(command + ["demo", "--steps", "1", "--exit"],
                                    text=True, capture_output=True, cwd=PROJECT, env=env, timeout=15)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertNotIn("mind>", second.stdout)
            self.assertIn(first_identity, second.stdout)

    def test_invalid_configuration_rejected(self) -> None:
        for config in (replace(Config(), workspace=WorkspaceConfig(capacity=0)),
                       replace(Config(), workspace=WorkspaceConfig(ignition_threshold=0.1)),
                       replace(Config(), workspace=WorkspaceConfig(capacity=1.5)),
                       replace(Config(), workspace=WorkspaceConfig(decay=float("nan"))),
                       replace(Config(), runtime=RuntimeConfig(housekeeping_seconds=0))):
            with self.assertRaises(ValueError):
                config.validate()

    def test_cli_separate_process_restart_and_shutdown(self) -> None:
        scratch = PROJECT / "work"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = Path(directory) / "state.db"
            env = {**os.environ, "PYTHONPATH": str(PROJECT / "src")}
            command = [sys.executable, "-B", "-m", "synthetic_mind", "--db", str(path)]
            first = subprocess.run(command + ["repl"], input="remember the blue door\n/goal find shelter\n/move east\n/quit\n",
                                   text=True, capture_output=True, cwd=PROJECT, env=env, timeout=15)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("[speech]", first.stdout)
            second = subprocess.run(command + ["status"], text=True, capture_output=True, cwd=PROJECT, env=env, timeout=15)
            self.assertEqual(second.returncode, 0, second.stderr)
            status = json.loads(second.stdout)
            self.assertEqual(status["body"]["position"], [2, 2])
            self.assertEqual(status["goals"][0]["description"], "find shelter")
            self.assertEqual(status["deliveries"].get("failed", 0), 0)
            self.assertIn(status["self_model"]["identity_id"], first.stdout)
            self.assertTrue(path.with_suffix(".events.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
