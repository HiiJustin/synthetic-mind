from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CognitiveEvent:
    source: str
    kind: str
    content: dict[str, Any]
    parents: tuple[str, ...] = ()
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=utc_now)
    root_id: str = ""
    hops: int = 0
    ttl_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CognitiveEvent:
        return cls(**{**value, "parents": tuple(value["parents"])})


@dataclass(order=True)
class ScheduledWork:
    priority: int
    sequence: int
    name: str = field(compare=False)
    callback: Any = field(compare=False, repr=False)


@dataclass
class SelfModel:
    identity_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)
    active_seconds: float = 0.0
    last_seen_at: str = field(default_factory=utc_now)
    last_external_interaction: str | None = None
    capabilities: dict[str, float] = field(default_factory=lambda: {"text_stub": 1.0, "grid_body": 1.0})
    limitations: dict[str, str] = field(default_factory=lambda: {
        "reasoning": "Deterministic policies and a mock backend only",
        "consciousness": "No consciousness assessment is implemented",
        "senses": "Structured, limited grid observations; no pixels or audio",
    })
    active_goals: list[str] = field(default_factory=list)
    known_failures: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    autobiographical_summary: str = "A new embodied laboratory instance."
    broadcasts_observed: int = 0


@dataclass
class Goal:
    description: str
    id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "active"
    created_at: str = field(default_factory=utc_now)


@dataclass
class Drives:
    hunger: float = 0.6
    uncertainty: float = 1.0
    cognitive_load: float = 0.0
    novelty_need: float = 0.0
    memory_conflict: float = 0.0


@dataclass
class ModuleHealth:
    processed: int = 0
    failures: int = 0
    last_event: str | None = None
    last_error: str | None = None
