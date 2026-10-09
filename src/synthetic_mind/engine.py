from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import Config
from .event_bus import EventBus, ModuleRegistry
from .models import MockModelBackend
from .modules import (ActuatorModule, BodyModelModule, CriticModule, EpisodicMemoryModule,
                      ExecutiveModule, HomeostasisModule, PerceptionModule, PlannerModule,
                      PredictionModule, SalienceModule, SelfModelModule)
from .schemas import CognitiveEvent, utc_now
from .scheduler import ComputeGovernor, Scheduler
from .stores import Database, EventLog, GoalStore, MemoryStore, SelfModelStore, StateStore
from .workspace import GlobalWorkspace
from .world import GridWorld


class Engine:
    """Composition root. Runtime sequencing lives here; cognition lives in modules."""

    def __init__(self, directory: Path, config: Config | None = None, database: Path | None = None):
        self.directory = directory.resolve()
        self.config = config or Config.load(directory / "config" / "default.toml")
        self.config.validate()
        self.db = Database(database or directory / self.config.runtime.database)
        self.log_path = database.with_suffix(".events.jsonl") if database else directory / self.config.runtime.log_file
        self.state = StateStore(self.db)
        self.memory, self.goals = MemoryStore(self.db), GoalStore(self.db)
        self.self_model = SelfModelStore(self.state)
        self.world = GridWorld(self.state, self.config.body)
        self.workspace = GlobalWorkspace(self.state, self.config.workspace)
        self.backend, self.governor = MockModelBackend(), ComputeGovernor(self.config.governor)
        self.scheduler = Scheduler(self.config.runtime.max_pending)
        self.registry = ModuleRegistry()
        modules = [PerceptionModule(), SalienceModule(), self.workspace,
                   EpisodicMemoryModule(self.memory, self.state), BodyModelModule(self.state),
                   PredictionModule(self.state), PlannerModule(self.state), CriticModule(),
                   ExecutiveModule(self.state, self.backend, self.governor),
                   SelfModelModule(self.self_model, self.goals), HomeostasisModule(self.state),
                   ActuatorModule(self.world)]
        available = {module.name for module in modules}
        if self.config.enabled_modules is not None:
            unknown = set(self.config.enabled_modules) - available
            if unknown:
                self.db.close()
                raise ValueError(f"Unknown modules: {sorted(unknown)}")
        for module in modules:
            if self.config.enabled_modules is None or module.name in self.config.enabled_modules:
                self.registry.register(module)
        self.bus = EventBus(self.db, self.registry, self.scheduler, self.config.runtime)
        self.log = EventLog(self.db)
        self.lock = asyncio.Lock()
        self.closed = False
        self.last_clock = time.monotonic()
        self.start_previous_seen = self.self_model.load().last_seen_at
        self.state.set("runtime.autonomous", False)

    def _account_time(self) -> None:
        now = time.monotonic()
        model = self.self_model.load()
        model.active_seconds += max(0.0, now - self.last_clock)
        model.last_seen_at = utc_now()
        self.self_model.save(model)
        self.last_clock = now

    async def start(self) -> None:
        async with self.lock:
            self.bus.publish(CognitiveEvent("runtime", "runtime.boot", {
                "identity_id": self.self_model.load().identity_id, "previous_seen_at": self.start_previous_seen,
                "config": asdict(self.config), "backend": "mock", "version": "0.0.1"}))
            await self.bus.drain()
            self.bus.publish(CognitiveEvent("body", "body.observation", self.world.observe()))
            await self.bus.drain()

    async def submit(self, text: str) -> str:
        async with self.lock:
            if self.closed:
                raise RuntimeError("Engine is closed")
            if len(text) > 10000:
                raise ValueError("Text limit is 10,000 characters")
            event = CognitiveEvent("user", "user.text", {"text": text})
            self.bus.publish(event)
            await self.bus.drain()
            return event.id

    async def request_goal(self, description: str) -> str:
        async with self.lock:
            event = CognitiveEvent("user", "user.goal", {"description": description[:1000]})
            self.bus.publish(event)
            await self.bus.drain()
            return event.id

    async def reflect(self) -> None:
        async with self.lock:
            self.bus.publish(CognitiveEvent("user", "user.reflect", {}))
            await self.bus.drain()

    async def step(self, action: str | None = None) -> list[CognitiveEvent]:
        async with self.lock:
            before = self.db.connection.execute("SELECT coalesce(max(seq),0) FROM events").fetchone()[0]
            self.state.set("runtime.autonomous", action is None)
            try:
                observed = CognitiveEvent("body", "body.observation", self.world.observe())
                self.bus.publish(observed)
                await self.bus.drain()
                if action is not None:
                    self.bus.publish(CognitiveEvent("user", "user.action", {"action": action}, (observed.id,)))
                    await self.bus.drain()
            finally:
                self.state.set("runtime.autonomous", False)
            import json
            return [CognitiveEvent.from_dict(json.loads(row[0])) for row in self.db.connection.execute("SELECT body FROM events WHERE seq>? AND kind IN ('body.result','action.rejected','runtime.module_error') ORDER BY seq", (before,))]

    async def housekeeping(self) -> None:
        async with self.lock:
            if self.closed:
                return
            self._account_time()
            self.bus.publish(CognitiveEvent("clock", "clock.tick", {"at": utc_now()}))
            await self.bus.drain()

    def status(self) -> dict[str, Any]:
        counts = dict(self.db.connection.execute("SELECT status,count(*) FROM deliveries GROUP BY status"))
        return {"version": "0.0.1", "self_model": asdict(self.self_model.load()),
                "body": self.state.get("body.sensed", {}), "drives": self.state.get("drives", {}),
                "workspace": [{"key": item["key"], "kind": item["kind"], "activation": item["activation"]} for item in self.workspace.items()],
                "goals": [asdict(goal) for goal in self.goals.all()],
                "events": self.db.connection.execute("SELECT count(*) FROM events").fetchone()[0],
                "deliveries": counts, "suppressed_this_session": self.bus.suppressed,
                "model_calls_this_session": self.governor.total_calls,
                "learning": self.state.get("learning.metrics", {}),
                "modules": {name: self.state.get("health." + name, {}) for name in self.registry.modules}}

    async def close(self) -> None:
        async with self.lock:
            if self.closed:
                return
            try:
                await self.bus.drain()
                self._account_time()
                self.bus.publish(CognitiveEvent("runtime", "runtime.shutdown", {"clean": True}))
                await self.scheduler.close()
                self.log.export(self.log_path, limit=10000)  # SQLite retains complete history; shutdown exports a bounded diagnostic tail.
            finally:
                self.db.close()
                self.closed = True
