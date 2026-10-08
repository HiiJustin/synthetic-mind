from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Protocol

from .config import RuntimeConfig
from .schemas import CognitiveEvent, ModuleHealth
from .scheduler import Scheduler
from .stores import Database, EventLog, StateStore, canonical


class CognitiveModule(Protocol):
    name: str
    subscriptions: set[str]
    priority: int

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]: ...


class ModuleRegistry:
    def __init__(self):
        self.modules: dict[str, CognitiveModule] = {}

    def register(self, module: CognitiveModule) -> None:
        if module.name in self.modules:
            raise ValueError(f"Duplicate module: {module.name}")
        self.modules[module.name] = module

    def subscribers(self, kind: str) -> list[CognitiveModule]:
        return [m for m in self.modules.values() if kind in m.subscriptions]


class EventBus:
    def __init__(self, db: Database, registry: ModuleRegistry, scheduler: Scheduler, config: RuntimeConfig):
        self.db, self.registry, self.scheduler, self.config = db, registry, scheduler, config
        self.log, self.state = EventLog(db), StateStore(db)
        self.suppressed = 0
        self.draining = False

    def publish(self, event: CognitiveEvent) -> str | None:
        with self.db.transaction():
            if self.db.connection.execute("SELECT 1 FROM events WHERE id=?", (event.id,)).fetchone():
                self.suppressed += 1
                return None
            parents = [self.log.get(parent) for parent in event.parents]
            root = parents[0].root_id if parents else event.id
            event = replace(event, root_id=root, hops=max((p.hops for p in parents), default=-1) + 1)
            fingerprint = hashlib.sha256(canonical([event.source, event.kind, event.content]).encode()).hexdigest()
            if event.hops > self.config.max_hops or self.db.connection.execute(
                "SELECT 1 FROM events WHERE root_id=? AND fingerprint=?", (root, fingerprint)
            ).fetchone():
                self.suppressed += 1
                return None
            subscribers = self.registry.subscribers(event.kind)
            pending = self.db.connection.execute("SELECT count(*) FROM deliveries WHERE status='pending'").fetchone()[0]
            if pending + len(subscribers) > self.config.max_pending:
                raise OverflowError("Durable event queue is full")
            self.db.connection.execute("INSERT INTO events(id,root_id,source,kind,timestamp,fingerprint,body) VALUES(?,?,?,?,?,?,?)",
                                       (event.id, root, event.source, event.kind, event.timestamp, fingerprint, canonical(event.to_dict())))
            self.db.connection.executemany("INSERT INTO edges VALUES(?,?)", [(p, event.id) for p in event.parents])
            self.db.connection.executemany("INSERT INTO deliveries(event_id,module) VALUES(?,?)", [(event.id, m.name) for m in subscribers])
            return event.id

    async def _deliver(self, event_id: str, name: str) -> None:
        event = self.log.get(event_id)
        health = ModuleHealth(**self.state.get("health." + name, {}))
        if name not in self.registry.modules:
            self.db.connection.execute("UPDATE deliveries SET status='failed',error='Module disabled on restart' WHERE event_id=? AND module=?", (event_id, name))
            return
        if event.ttl_seconds is not None and (datetime.now(timezone.utc) - datetime.fromisoformat(event.timestamp)).total_seconds() > event.ttl_seconds:
            self.db.connection.execute("UPDATE deliveries SET status='expired' WHERE event_id=? AND module=?", (event_id, name))
            return
        try:
            started = time.perf_counter()
            trace = {"event_id": event.id, "module": name, "state_reads": [], "state_writes": [],
                     "memory_reads": [], "memory_writes": [], "output_event_ids": []}
            # Delivery + state writes + child events commit together; no external actions here.
            with self.db.transaction():
                self.db.trace = trace
                children = await self.registry.modules[name].on_event(event)
                for child in children:
                    child_id = self.publish(replace(child, parents=child.parents or (event.id,)))
                    if child_id:
                        trace["output_event_ids"].append(child_id)
                health.processed += 1
                health.last_event = event.id
                self.state.set("health." + name, asdict(health))
                self.db.connection.execute("UPDATE deliveries SET status='done' WHERE event_id=? AND module=?", (event.id, name))
                trace["latency_ms"] = (time.perf_counter() - started) * 1000
                self.db.connection.execute("INSERT INTO module_traces VALUES(?,?,?)", (event.id, name, canonical(trace)))
        except Exception as exc:
            self.db.trace = None
            health.failures += 1
            health.last_error = f"{type(exc).__name__}: {exc}"
            self.state.set("health." + name, asdict(health))
            self.db.connection.execute("UPDATE deliveries SET status='failed',error=? WHERE event_id=? AND module=?", (health.last_error, event.id, name))
            self.publish(CognitiveEvent("runtime", "runtime.module_error", {"module": name, "error": health.last_error}, (event.id,)))
        finally:
            self.db.trace = None

    async def drain(self) -> None:
        if self.draining:
            raise RuntimeError("Concurrent drain is unsupported")
        self.draining = True
        processed = 0
        try:
            while True:
                rows = list(self.db.connection.execute("SELECT d.event_id,d.module FROM deliveries d JOIN events e ON e.id=d.event_id WHERE d.status='pending' ORDER BY e.seq,d.module LIMIT ?", (self.scheduler.capacity,)))
                if not rows:
                    return
                if processed + len(rows) > self.config.max_events_per_drain:
                    raise RuntimeError("Drain work budget reached; pending deliveries remain durable")
                for row in rows:
                    event_id, name = row
                    priority = getattr(self.registry.modules.get(name), "priority", 50)
                    self.scheduler.schedule(name, lambda e=event_id, n=name: self._deliver(e, n), priority)
                await self.scheduler.run()
                processed += len(rows)
        finally:
            self.draining = False
