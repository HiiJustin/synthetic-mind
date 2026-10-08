from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import WorkspaceConfig
from .schemas import CognitiveEvent
from .stores import StateStore


class GlobalWorkspace:
    name = "workspace"
    subscriptions = {"attention.candidate", "attention.support", "clock.tick"}
    priority = 30

    def __init__(self, state: StateStore, config: WorkspaceConfig, namespace: str = "workspace"):
        self.state, self.config = state, config
        self.namespace = namespace

    @staticmethod
    def score(features: dict[str, float]) -> float:
        weights = {"salience": 0.30, "novelty": 0.20, "goal_relevance": 0.25,
                   "urgency": 0.15, "confidence": 0.10}
        return sum(weights[key] * max(0.0, min(1.0, features.get(key, 0.0))) for key in weights)

    def items(self) -> list[dict[str, Any]]:
        data = self.state.get(self.namespace, {"candidates": {}, "active": []})
        return [data["candidates"][key] for key in data["active"] if key in data["candidates"]]

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        data = self.state.get(self.namespace, {"candidates": {}, "active": [], "revision": 0})
        candidates, old_active = data["candidates"], set(data["active"])
        changed: str | None = None
        if event.kind == "attention.candidate":
            candidate = dict(event.content)
            changed = candidate["key"]
            previous = candidates.get(changed, {})
            candidate["activation"] = min(1.0, self.score(candidate["features"]) + 0.1 * previous.get("activation", 0.0))
            candidate["updated_at"] = event.timestamp
            candidate["supporters"] = []
            candidates[changed] = candidate
        elif event.kind == "attention.support":
            changed = event.content["key"]
            candidate = candidates.get(changed)
            if candidate and event.source not in candidate["supporters"]:
                candidate["supporters"].append(event.source)
                candidate["activation"] = min(1.0, candidate["activation"] + self.config.support_gain)
        else:
            for candidate in candidates.values():
                candidate["activation"] *= self.config.decay
        now = datetime.now(timezone.utc)
        candidates = {key: value for key, value in candidates.items()
                      if (now - datetime.fromisoformat(value["updated_at"])).total_seconds() <= self.config.max_age_seconds
                      and value["activation"] >= 0.01}
        ranked = sorted(candidates, key=lambda key: (candidates[key]["activation"], candidates[key]["updated_at"], key), reverse=True)
        candidates = {key: candidates[key] for key in ranked[:self.config.max_candidates]}
        eligible = [key for key in ranked if key in candidates and candidates[key]["activation"] >=
                    (self.config.retention_threshold if key in old_active else self.config.ignition_threshold)]
        active = eligible[:self.config.capacity]
        # Capacity competition is the initial inhibitory approximation. Losing candidates
        # stay backstage, so subsequent corroboration can bring them back into contention.
        outputs = []
        for key in active:
            if key not in old_active or (key == changed and event.kind == "attention.candidate"):
                data["revision"] += 1
                item = candidates[key]
                outputs.append(CognitiveEvent(self.name, "workspace.broadcast", {
                    "revision": data["revision"], "reason": "ignition" if key not in old_active else "refresh",
                    "key": key, "activation": item["activation"], "origin_id": item["origin_id"],
                    "kind": item["kind"], "payload": item["payload"]},
                    tuple(dict.fromkeys((event.id, item["origin_id"])))))
        self.state.set(self.namespace, {"candidates": candidates, "active": active, "revision": data["revision"]})
        return outputs
