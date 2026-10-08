from __future__ import annotations

import tomllib
import math
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    database: str = "data/state.db"
    log_file: str = "data/events.jsonl"
    housekeeping_seconds: float = 5.0
    max_pending: int = 2048
    max_hops: int = 24
    max_events_per_drain: int = 4096


@dataclass(frozen=True)
class WorkspaceConfig:
    capacity: int = 7
    ignition_threshold: float = 0.56
    retention_threshold: float = 0.30
    support_gain: float = 0.15
    decay: float = 0.88
    max_candidates: int = 64
    max_age_seconds: float = 300.0


@dataclass(frozen=True)
class GovernorConfig:
    calls_per_minute: int = 6
    tokens_per_minute: int = 4096
    max_concurrent: int = 1
    max_seconds_per_call: float = 10.0


@dataclass(frozen=True)
class BodyConfig:
    vision_radius: int = 2
    hunger_per_action: float = 0.025


@dataclass(frozen=True)
class Config:
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    governor: GovernorConfig = field(default_factory=GovernorConfig)
    body: BodyConfig = field(default_factory=BodyConfig)
    enabled_modules: tuple[str, ...] | None = None

    @classmethod
    def load(cls, path: Path) -> Config:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        unknown = set(data) - {"runtime", "workspace", "governor", "body", "modules"}
        if unknown:
            raise ValueError(f"Unknown config sections: {sorted(unknown)}")
        for section, schema in (("runtime", RuntimeConfig), ("workspace", WorkspaceConfig),
                                ("governor", GovernorConfig), ("body", BodyConfig)):
            extra = set(data.get(section, {})) - {f.name for f in fields(schema)}
            if extra:
                raise ValueError(f"Unknown {section} settings: {sorted(extra)}")
        if set(data.get("modules", {})) - {"enabled"}:
            raise ValueError("modules accepts only enabled")
        result = cls(RuntimeConfig(**data.get("runtime", {})),
                     WorkspaceConfig(**data.get("workspace", {})),
                     GovernorConfig(**data.get("governor", {})),
                     BodyConfig(**data.get("body", {})),
                     tuple(data["modules"]["enabled"]) if "enabled" in data.get("modules", {}) else None)
        result.validate()
        return result

    def validate(self) -> None:
        r, w, g, b = self.runtime, self.workspace, self.governor, self.body
        counts = (r.max_pending, r.max_hops, r.max_events_per_drain, w.capacity,
                  w.max_candidates, g.calls_per_minute, g.tokens_per_minute, g.max_concurrent,
                  b.vision_radius)
        if any(type(value) is not int for value in counts):
            raise ValueError("Counts and limits must be integers")
        numbers = (r.housekeeping_seconds, w.ignition_threshold, w.retention_threshold,
                   w.support_gain, w.decay, w.max_age_seconds, g.max_seconds_per_call,
                   b.hunger_per_action)
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in numbers):
            raise ValueError("Numeric settings must be finite numbers")
        if min(r.max_pending, r.max_hops, r.max_events_per_drain, w.capacity,
               w.max_candidates, g.calls_per_minute, g.tokens_per_minute, g.max_concurrent,
               b.vision_radius) < 1:
            raise ValueError("Counts and limits must be positive")
        if not 0 <= w.retention_threshold < w.ignition_threshold <= 1:
            raise ValueError("Require 0 <= retention < ignition <= 1")
        if not 0 < w.decay < 1 or not 0 <= w.support_gain <= 1:
            raise ValueError("Invalid workspace decay/support")
        if w.max_candidates < w.capacity:
            raise ValueError("Candidate limit must accommodate workspace capacity")
        if min(r.housekeeping_seconds, w.max_age_seconds, g.max_seconds_per_call) <= 0:
            raise ValueError("Time intervals must be positive")
        if not 0 <= b.hunger_per_action <= 1:
            raise ValueError("Invalid hunger rate")
