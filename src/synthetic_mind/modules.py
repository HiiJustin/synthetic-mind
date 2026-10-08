from __future__ import annotations

from collections import deque
from dataclasses import asdict
from typing import Any

from .models import ModelBackend
from .schemas import CognitiveEvent, Drives, Goal
from .scheduler import ComputeGovernor
from .stores import GoalStore, MemoryStore, SelfModelStore, StateStore
from .world import ACTIONS, GridWorld


class PerceptionModule:
    name, priority = "perception", 10
    subscriptions = {"user.text", "user.action", "user.goal"}

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        if event.kind == "user.text":
            text = str(event.content["text"]).strip()
            return [CognitiveEvent(self.name, "perception.text", {"text": text, "words": len(text.split()), "attribution": "user"})]
        if event.kind == "user.goal":
            return [CognitiveEvent(self.name, "goal.requested", {"description": str(event.content["description"])})]
        return [CognitiveEvent(self.name, "action.proposed", {"action": event.content["action"], "reason": "user request", "manual": True})]


class SalienceModule:
    name, priority = "salience", 20
    subscriptions = {"perception.text", "body.observation", "body.result", "prediction.error", "goal.created"}

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        body = event.kind == "body.observation"
        urgency = float(event.content.get("hunger", 0.0)) if body else 0.5 if event.kind == "prediction.error" else 0.3
        features = {"salience": 0.8, "novelty": 0.7, "goal_relevance": 0.9 if body else 0.7,
                    "urgency": urgency, "confidence": 1.0}
        return [CognitiveEvent(self.name, "attention.candidate", {
            "key": "body.observation" if body else event.id, "origin_id": event.id,
            "kind": event.kind, "payload": event.content, "features": features})]


class EpisodicMemoryModule:
    name, priority = "memory", 25
    subscriptions = {"perception.text", "body.observation", "body.result", "attention.candidate", "workspace.broadcast"}

    def __init__(self, memory: MemoryStore, state: StateStore):
        self.memory, self.state = memory, state

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        if event.kind == "attention.candidate" and event.content["kind"] == "perception.text":
            origin = event.content["origin_id"]
            hits = self.memory.retrieve(event.content["payload"]["text"], exclude=origin)
            self.state.set("memory.last_retrieval", {"query_event": origin, "hits": [hit.id for hit in hits]})
            if hits:
                return [CognitiveEvent(self.name, "attention.support", {"key": event.content["key"], "memories": [hit.id for hit in hits]}, (event.id, *[hit.id for hit in hits]))]
        elif event.kind != "attention.candidate":
            self.memory.write(event)
        return []


class BodyModelModule:
    name, priority = "body_model", 15
    subscriptions = {"body.observation", "body.result"}

    def __init__(self, state: StateStore):
        self.state = state

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        if event.kind == "body.observation":
            self.state.set("body.sensed", {**event.content, "event_id": event.id})
            known = self.state.get("body.map", {})
            for cell in event.content["visible"]:
                known[",".join(map(str, cell["position"]))] = cell["kind"]
            self.state.set("body.map", known)
            visited = self.state.get("body.visited", [])
            position = ",".join(map(str, event.content["position"]))
            if position not in visited:
                visited.append(position)
            self.state.set("body.visited", visited)
        else:
            sensed = {**event.content["observation"], "event_id": event.id}
            self.state.set("body.sensed", sensed)
            known = self.state.get("body.map", {})
            for cell in sensed["visible"]:
                known[",".join(map(str, cell["position"]))] = cell["kind"]
            if event.content["blocked"]:
                known[",".join(map(str, event.content["target"]))] = "wall"
            if event.content["ate"]:
                known[",".join(map(str, event.content["position"]))] = "empty"
            self.state.set("body.map", known)
        return []


class PredictionModule:
    name, priority = "prediction", 5
    subscriptions = {"executive.action", "body.result"}

    def __init__(self, state: StateStore):
        self.state = state

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        if event.kind == "executive.action":
            sensed = self.state.get("body.sensed", {})
            before = sensed.get("position", [1, 2])
            action = event.content["action"]
            delta = ACTIONS[action]
            target = [before[0] + delta[0], before[1] + delta[1]]
            transitions = self.state.get("learning.transitions", {})
            key = f"{before[0]},{before[1]}:{action}"
            learned = transitions.get(key)
            known_wall = self.state.get("body.map", {}).get(",".join(map(str, target))) == "wall"
            expected = learned["position"] if learned else before if known_wall else target
            prediction = {"action_event": event.id, "transition_key": key,
                          "expected_position": expected, "learned": learned is not None}
            self.state.set("prediction.pending", prediction)
            return [CognitiveEvent(self.name, "prediction.created", prediction)]
        prediction = self.state.get("prediction.pending")
        if not prediction:
            return []
        correct = prediction["expected_position"] == event.content["position"]
        transitions = self.state.get("learning.transitions", {})
        previous = transitions.get(prediction["transition_key"], {})
        transitions[prediction["transition_key"]] = {"position": event.content["position"],
            "samples": previous.get("samples", 0) + 1, "blocked": event.content["blocked"]}
        self.state.set("learning.transitions", transitions)
        metrics = self.state.get("learning.metrics", {"predictions": 0, "errors": 0})
        metrics["predictions"] += 1
        metrics["errors"] += int(not correct)
        self.state.set("learning.metrics", metrics)
        self.state.set("prediction.pending", None)
        return [CognitiveEvent(self.name, "prediction.confirmed" if correct else "prediction.error",
                               {**prediction, "actual_position": event.content["position"]},
                               (event.id, prediction["action_event"]))]


class PlannerModule:
    name, priority = "planner", 45
    subscriptions = {"workspace.broadcast"}

    def __init__(self, state: StateStore):
        self.state = state

    @staticmethod
    def choose(observation: dict[str, Any], known: dict[str, str], visited: list[str]) -> tuple[str, str]:
        start = tuple(observation["position"])
        if observation["hunger"] < 0.35:
            return "wait", "No current food need"
        if known.get(",".join(map(str, start))) == "food":
            return "eat", "Food is at the current position"
        queue = deque([(start, [])])
        seen = {start}
        frontiers: list[tuple[int, bool, tuple[int, int], list[str]]] = []
        while queue:
            position, path = queue.popleft()
            if known.get(",".join(map(str, position))) == "food" and path:
                return path[0], "Navigate to remembered food"
            unknown_neighbor = False
            for action in ("east", "north", "south", "west"):
                dx, dy = ACTIONS[action]
                neighbor = (position[0] + dx, position[1] + dy)
                kind = known.get(",".join(map(str, neighbor)))
                if kind is None:
                    unknown_neighbor = True
                elif kind != "wall" and neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, path + [action]))
            if unknown_neighbor and path:
                frontiers.append((len(path), ",".join(map(str, position)) in visited, position, path))
        if frontiers:
            # Only sensed cells are navigable. The map and remembered outcomes change
            # the next decision; exploration itself is a hand-written bootstrap policy.
            best = min(frontiers, key=lambda item: (item[1], item[0], item[2]))
            return best[3][0], "Explore an observed route toward unknown space"
        return "wait", "No observed route to food or unexplored space"

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        if event.content["kind"] != "body.observation" or not self.state.get("runtime.autonomous", False):
            return []
        origin = event.content["origin_id"]
        if self.state.get("planner.last_origin") == origin:
            return []
        self.state.set("planner.last_origin", origin)
        action, reason = self.choose(event.content["payload"], self.state.get("body.map", {}), self.state.get("body.visited", []))
        return [CognitiveEvent(self.name, "action.proposed", {"action": action, "reason": reason, "manual": False})]


class CriticModule:
    name, priority = "critic", 50
    subscriptions = {"action.proposed"}

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        allowed = event.content.get("action") in ACTIONS
        return [CognitiveEvent(self.name, "action.approved" if allowed else "action.rejected", event.content)]


class ExecutiveModule:
    name, priority = "executive", 60
    subscriptions = {"action.approved", "workspace.broadcast", "user.reflect"}

    def __init__(self, state: StateStore, backend: ModelBackend, governor: ComputeGovernor):
        self.state, self.backend, self.governor = state, backend, governor

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        if event.kind == "action.approved":
            return [CognitiveEvent(self.name, "executive.action", event.content)]
        if event.kind == "workspace.broadcast" and event.content["kind"] == "perception.text":
            text = event.content["payload"]["text"]
            return [CognitiveEvent(self.name, "executive.speech", {"text": f"[deterministic] Recorded your message: {text}", "origin_id": event.content["origin_id"]})]
        if event.kind == "user.reflect":
            summary = "I retain an identity, explored map, memories, and action outcomes. This response is a mock."
            result = await self.governor.execute(lambda: self.backend.generate(system="Mock reflection", input_text=summary), input_tokens=len(summary.split()), output_tokens=128)
            return [CognitiveEvent(self.name, "model.call", {"backend": "mock", "input_tokens_estimate": len(summary.split()), "output_tokens_estimate": len(result.split()), "template_version": "mock-v1", "external_cost": 0}),
                    CognitiveEvent(self.name, "executive.speech", {"text": result})]
        return []


class SelfModelModule:
    name, priority = "self_model", 70
    subscriptions = {"workspace.broadcast", "user.text", "goal.requested", "body.result", "prediction.error"}

    def __init__(self, model: SelfModelStore, goals: GoalStore):
        self.model, self.goals = model, goals

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        model = self.model.load()
        outputs = []
        if event.kind == "workspace.broadcast":
            model.broadcasts_observed += 1
        elif event.kind == "user.text":
            model.last_external_interaction = event.timestamp
        elif event.kind == "goal.requested":
            goal = Goal(event.content["description"])
            self.goals.save(goal)
            model.active_goals.append(goal.id)
            outputs.append(CognitiveEvent(self.name, "goal.created", asdict(goal)))
        elif event.kind == "prediction.error":
            model.known_failures = (model.known_failures + [f"Movement prediction failed at {event.content['transition_key']}"])[-20:]
        elif event.kind == "body.result" and event.content["ate"]:
            model.autobiographical_summary = f"I reached and ate food at {event.content['position']} on body step {event.content['step']}."
        self.model.save(model)
        return outputs


class HomeostasisModule:
    name, priority = "homeostasis", 18
    subscriptions = {"body.observation", "body.result", "clock.tick"}

    def __init__(self, state: StateStore):
        self.state = state

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        drives = Drives(**self.state.get("drives", {}))
        if event.kind.startswith("body."):
            drives.hunger = event.content["hunger"]
        else:
            drives.novelty_need = min(1.0, drives.novelty_need + 0.002)
        known = self.state.get("body.map", {})
        drives.uncertainty = 1.0 / (1.0 + len(known))
        drives.cognitive_load = min(1.0, len(self.state.get("workspace", {}).get("active", [])) / 7)
        self.state.set("drives", asdict(drives))
        return []


class ActuatorModule:
    name, priority = "actuator", 80
    subscriptions = {"executive.action"}

    def __init__(self, world: GridWorld):
        self.world = world

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        return [CognitiveEvent(self.name, "body.result", self.world.act(event.content["action"]))]
