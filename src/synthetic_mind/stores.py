from __future__ import annotations

import json
import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterator

from .schemas import CognitiveEvent, Goal, SelfModel


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def state_patch(before: Any, after: Any, path: tuple = ()) -> list[dict]:
    """Lossless path operations for nested state, avoiding repeated workspace payloads."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        changes = [{"path": list(path + (key,)), "remove": True} for key in sorted(before.keys() - after.keys())]
        for key, value in after.items():
            changes.extend(state_patch(before[key], value, path + (key,)) if key in before else [{"path": list(path + (key,)), "value": value}])
        return changes
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after) and len(after) <= 128:
        return [change for index, value in enumerate(after) for change in state_patch(before[index], value, path + (index,))]
    return [{"path": list(path), "value": after}]


class Database:
    """One writer; transactions couple state changes to durable event deliveries."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.trace: dict[str, Any] | None = None
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 2:
            self.connection.close()
            raise ValueError(f"Database version {version} is newer than this program")
        if version == 0:
            self.connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE state(namespace TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT UNIQUE NOT NULL, root_id TEXT NOT NULL, source TEXT NOT NULL,
                    kind TEXT NOT NULL, timestamp TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    body TEXT NOT NULL, UNIQUE(root_id, fingerprint));
                CREATE TABLE edges(parent_id TEXT REFERENCES events(id),
                    child_id TEXT REFERENCES events(id), PRIMARY KEY(parent_id, child_id));
                CREATE TABLE deliveries(event_id TEXT REFERENCES events(id), module TEXT,
                    status TEXT NOT NULL DEFAULT 'pending', error TEXT,
                    PRIMARY KEY(event_id,module));
                CREATE INDEX pending_delivery ON deliveries(status);
                CREATE INDEX events_kind ON events(kind,seq);
                CREATE TABLE episodes(event_id TEXT PRIMARY KEY REFERENCES events(id),
                    text TEXT NOT NULL);
                CREATE TABLE goals(id TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TRIGGER events_no_update BEFORE UPDATE ON events
                    BEGIN SELECT RAISE(ABORT,'Event history is immutable'); END;
                CREATE TRIGGER events_no_delete BEFORE DELETE ON events
                    BEGIN SELECT RAISE(ABORT,'Event history is immutable'); END;
                CREATE TRIGGER edges_no_update BEFORE UPDATE ON edges
                    BEGIN SELECT RAISE(ABORT,'Causal edges are immutable'); END;
                CREATE TRIGGER edges_no_delete BEFORE DELETE ON edges
                    BEGIN SELECT RAISE(ABORT,'Causal edges are immutable'); END;
                PRAGMA user_version=1;
                COMMIT;
            """)

        if version < 2:
            self.connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE module_traces(event_id TEXT REFERENCES events(id), module TEXT,
                    body TEXT NOT NULL, PRIMARY KEY(event_id,module));
                CREATE TRIGGER traces_no_update BEFORE UPDATE ON module_traces
                    BEGIN SELECT RAISE(ABORT,'Module traces are immutable'); END;
                CREATE TRIGGER traces_no_delete BEFORE DELETE ON module_traces
                    BEGIN SELECT RAISE(ABORT,'Module traces are immutable'); END;
                PRAGMA user_version=2;
                COMMIT;
            """)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self.connection.in_transaction:
            yield
            return
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    def close(self) -> None:
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.connection.close()


class StateStore:
    def __init__(self, db: Database):
        self.db = db

    def get(self, namespace: str, default: Any = None) -> Any:
        if self.db.trace is not None:
            self.db.trace["state_reads"].append(namespace)
        row = self.db.connection.execute("SELECT value FROM state WHERE namespace=?", (namespace,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, namespace: str, value: Any) -> None:
        encoded = canonical(value)
        previous = self.db.connection.execute("SELECT value FROM state WHERE namespace=?", (namespace,)).fetchone()
        if previous and previous[0] == encoded:
            if self.db.trace is not None:
                self.db.trace["state_writes"].append({"namespace": namespace, "unchanged": True})
            return
        if self.db.trace is not None:
            record: dict[str, Any] = {"namespace": namespace}
            if len(encoded) <= 2048:
                record["value"] = value
            else:
                before = json.loads(previous[0]) if previous else {}
                record.update({"bytes": len(encoded.encode()), "sha256": hashlib.sha256(encoded.encode()).hexdigest()})
                if isinstance(value, dict) and isinstance(before, dict):
                    record["changed"] = {key: item for key, item in value.items() if key not in before or before[key] != item}
                    record["removed"] = list(before.keys() - value.keys())
                    patch = state_patch(before, value)
                    if len(canonical(patch)) < len(canonical(record["changed"])):
                        del record["changed"], record["removed"]
                        record["patch"] = patch
                else:
                    record["patch"] = state_patch(before, value)
            # Large explored maps are traced by delta so idle sensing does not copy
            # the entire accumulated map into history every second.
            self.db.trace["state_writes"].append(record)
        self.db.connection.execute("INSERT INTO state VALUES(?,?) ON CONFLICT(namespace) DO UPDATE SET value=excluded.value",
                                   (namespace, encoded))

    def patch(self, namespace: str, patch: dict[str, Any]) -> None:
        self.set(namespace, {**self.get(namespace, {}), **patch})


class SelfModelStore:
    def __init__(self, state: StateStore):
        self.state = state
        if state.get("self_model") is None:
            self.save(SelfModel())

    def load(self) -> SelfModel:
        return SelfModel(**self.state.get("self_model"))

    def save(self, model: SelfModel) -> None:
        self.state.set("self_model", asdict(model))


class GoalStore:
    def __init__(self, db: Database):
        self.db = db

    def save(self, goal: Goal) -> None:
        self.db.connection.execute("INSERT INTO goals VALUES(?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                                   (goal.id, canonical(asdict(goal))))

    def all(self) -> list[Goal]:
        return [Goal(**json.loads(row[0])) for row in self.db.connection.execute("SELECT value FROM goals ORDER BY rowid")]


class MemoryStore:
    """Deterministic lexical retrieval stub, keeping raw history immutable."""

    def __init__(self, db: Database):
        self.db = db

    def write(self, event: CognitiveEvent) -> None:
        if self.db.trace is not None:
            self.db.trace["memory_writes"].append(event.id)
        self.db.connection.execute("INSERT OR IGNORE INTO episodes VALUES(?,?)", (event.id, canonical(event.content)))

    def retrieve(self, query: str, limit: int = 5, exclude: str | None = None) -> list[CognitiveEvent]:
        words = set(query.casefold().split())
        if not words or limit < 1:
            return []
        rows = self.db.connection.execute("SELECT e.body,m.text,e.seq FROM episodes m JOIN events e ON e.id=m.event_id WHERE e.id != ? ORDER BY e.seq DESC LIMIT 1000", (exclude or "",))
        scored = [(sum(word in row["text"].casefold() for word in words), row["seq"], row["body"]) for row in rows]
        hits = [CognitiveEvent.from_dict(json.loads(body)) for score, _, body in sorted(scored, reverse=True)[:limit] if score > 0]
        if self.db.trace is not None:
            self.db.trace["memory_reads"].append({"query": query, "hits": [event.id for event in hits]})
        return hits


class EventLog:
    def __init__(self, db: Database):
        self.db = db

    def get(self, event_id: str) -> CognitiveEvent:
        row = self.db.connection.execute("SELECT body FROM events WHERE id=?", (event_id,)).fetchone()
        if not row:
            raise KeyError(event_id)
        return CognitiveEvent.from_dict(json.loads(row[0]))

    def recent(self, limit: int = 20) -> list[CognitiveEvent]:
        return [CognitiveEvent.from_dict(json.loads(row[0])) for row in self.db.connection.execute("SELECT body FROM events ORDER BY seq DESC LIMIT ?", (limit,))]

    def inspect(self, event_id: str) -> dict[str, Any]:
        event = self.get(event_id)
        return {"event": event.to_dict(),
                "children": [row[0] for row in self.db.connection.execute("SELECT child_id FROM edges WHERE parent_id=?", (event_id,))],
                "deliveries": [dict(row) for row in self.db.connection.execute("SELECT module,status,error FROM deliveries WHERE event_id=?", (event_id,))],
                "module_traces": [json.loads(row[0]) for row in self.db.connection.execute("SELECT body FROM module_traces WHERE event_id=?", (event_id,))]}

    def export(self, path: Path, limit: int | None = None) -> None:
        """Regenerate a diagnostic export from the authoritative SQLite history."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            query = "SELECT body FROM events ORDER BY seq" if limit is None else "SELECT body FROM (SELECT seq,body FROM events ORDER BY seq DESC LIMIT ?) ORDER BY seq"
            for row in self.db.connection.execute(query, () if limit is None else (limit,)):
                stream.write(row[0] + "\n")
        temporary.replace(path)
