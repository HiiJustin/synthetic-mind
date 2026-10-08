"""Independent cognitive agents communicate through events and persistent state.

Agents are logical processors, not separate weight copies. Inference is delegated
to the shared worker; perception, retrieval, prediction, and consolidation are cheap.
"""
from collections import Counter
import math
import time

from .schemas import CognitiveEvent


class SensoryInterpretationAgent:
    name, priority = "sensory_interpretation", 17
    subscriptions = {"minecraft.senses", "minecraft.sound"}

    def __init__(self, state):
        self.state = state

    async def on_event(self, event):
        if event.kind == "minecraft.sound":
            return [CognitiveEvent(self.name, "perception.sound", {"heard": event.content, "uncertainty": "Packet-derived sound direction; not microphone audio"})]
        sensed = event.content
        names = dict(Counter(block["name"] for block in sensed.get("visibleBlocks", [])))
        old = self.state.get("cognition.scene", {})
        scene = {"blocks": names, "new_block_types": sorted(set(names) - set(old.get("blocks", {}))),
            "entities": sensed.get("visibleEntities", [])[:8], "proximity": sensed.get("proximity"),
            "hunger": sensed.get("hunger"), "health": sensed.get("health"), "source_id": event.id}
        scene["summary"] = ("Visible block types: " + ", ".join(sorted(names)[:8]) +
            f". Visible entities: {len(scene['entities'])}. Health: {scene['health']}; hunger: {scene['hunger']}. " +
            f"On ground: {sensed.get('onGround')}. Block underfoot is not identified by these observations.")
        self.state.set("cognition.scene", scene)
        return [CognitiveEvent(self.name, "perception.scene", scene)]


class EpisodicRecallAgent:
    name, priority = "episodic_recall", 36
    subscriptions = {"workspace.broadcast"}

    def __init__(self, state, memory):
        self.state, self.memory = state, memory

    async def on_event(self, event):
        payload = event.content.get("payload", {})
        query = payload.get("text") or self.state.get("brain.goal", "explore")
        scene = self.state.get("cognition.scene", {})
        query += " " + " ".join(scene.get("new_block_types", []))
        world_id = self.state.get("minecraft.world_id")
        episodes = [item for item in self.memory.retrieve(query, limit=8, exclude=event.id)
            if item.id != event.content.get("origin_id") and item.content.get("world_id", world_id) == world_id][:3]
        recalled = [{"event_id": item.id, "kind": item.kind, "content": str(item.content)[:500]} for item in episodes]
        self.state.set("cognition.recalled", recalled)
        return [CognitiveEvent(self.name, "memory.recalled", {"query": query, "episodes": recalled}, tuple(dict.fromkeys((event.id,) + tuple(item.id for item in episodes))))]


class HomeostasisAgent:
    name, priority = "minecraft_homeostasis", 18
    subscriptions = {"minecraft.senses", "clock.tick"}

    def __init__(self, state):
        self.state = state

    async def on_event(self, event):
        previous = self.state.get("cognition.drives", {"curiosity": 0.5, "hunger": 0, "threat": 0})
        scene = self.state.get("cognition.scene", {})
        sensed = self.state.get("minecraft.sensed", {})
        drives = {"hunger": sensed.get("hunger", 0), "threat": max(0, 1 - sensed.get("health", 20) / 20),
            "curiosity": max(0.1, previous["curiosity"] - 0.1) if scene.get("new_block_types") and event.kind == "minecraft.senses" else min(1.0, previous["curiosity"] + (0.02 if event.kind == "clock.tick" else 0))}
        self.state.set("cognition.drives", drives)
        if any(abs(drives[key] - previous.get(key, 0)) >= 0.1 for key in drives):
            return [CognitiveEvent(self.name, "drive.changed", {**drives, "urgency": max(drives["hunger"], drives["threat"]), "note": "Functional drive variables, not simulated feelings"})]
        return []


class PredictionAgent:
    name, priority = "minecraft_prediction", 42
    subscriptions = {"brain.decision", "minecraft.action_result"}

    def __init__(self, state, log):
        self.state, self.log = state, log

    async def on_event(self, event):
        if event.kind == "brain.decision":
            self.state.set("cognition.expected", {"decision_id": event.id, "action": event.content["action"], "expected_outcome": event.content["expected_outcome"]})
            return []
        if event.content.get("action") == "say":
            return []
        # Transport causal parents identify the actual decision, avoiding attribution
        # of a manual action to an unrelated model prediction.
        prediction = None
        pending = list(event.parents)
        visited = set()
        while pending and len(visited) < 24:
            ancestor_id = pending.pop()
            if ancestor_id in visited:
                continue
            visited.add(ancestor_id)
            ancestor = self.log.get(ancestor_id)
            if ancestor.kind == "brain.decision" and event.content.get("action") in {"move", "look", "eat"}:
                prediction = {"decision_id": ancestor.id, "action": ancestor.content["action"], "expected_outcome": ancestor.content["expected_outcome"]}
                break
            pending.extend(ancestor.parents)
        result = event.content
        displacement = None
        if "before" in result and "position" in result:
            displacement = math.dist([result["before"][key] for key in ("x", "y", "z")], [result["position"][key] for key in ("x", "y", "z")])
        outcome = {"observed": result, "prediction": prediction, "distance": displacement,
            "blocked": result.get("contact", False), "prediction_error": "Move produced little displacement" if displacement is not None and displacement < 0.1 else None}
        self.state.set("brain.outcome", outcome)
        return [CognitiveEvent(self.name, "prediction.outcome", outcome)]


class ConsolidationAgent:
    name, priority = "episodic_consolidation", 65
    subscriptions = {"brain.decision", "prediction.outcome"}

    def __init__(self, state, model):
        self.state, self.model = state, model

    async def on_event(self, event):
        # Preserve the distinction between model-generated interpretations and facts.
        content = {"type": "tentative_interpretation", "summary": event.content["memory"]} if event.kind == "brain.decision" else {"type": "observed_outcome", "outcome": event.content}
        recent = self.state.get("cognition.autobiography", [])
        self.state.set("cognition.autobiography", (recent + [{"event_id": event.id, **content}])[-20:])
        if event.kind == "prediction.outcome":
            model = self.model.load()
            observed = event.content["observed"]
            model.autobiographical_summary = f"Last observed Minecraft action: {observed.get('action')}; position: {observed.get('position')}; event: {event.id}."
            if event.content.get("prediction_error"):
                model.known_failures = (model.known_failures + [event.content["prediction_error"] + " at " + event.id])[-20:]
            self.model.save(model)
        return [CognitiveEvent(self.name, "memory.consolidated", {**content, "world_id": self.state.get("minecraft.world_id")})]


class DeliberationPlannerAgent:
    name, priority = "deliberation_planner", 44
    subscriptions = {"workspace.broadcast"}

    def __init__(self, state, interval):
        self.state, self.interval = state, interval

    async def on_event(self, event):
        if event.content["kind"] == "perception.text":
            text = event.content["payload"]["text"]
            if text.casefold().startswith("!mind "):
                return [CognitiveEvent(self.name, "brain.request", {"text": text[6:][:1000]})]
        if event.content["kind"] == "minecraft.senses" and self.state.get("minecraft.autonomous"):
            now = time.time()
            if self.state.get("council.enabled"):
                scene = self.state.get("cognition.scene", {})
                signature = [sorted(scene.get("blocks", {})), [entity.get("type") for entity in scene.get("entities", [])],
                    int(scene.get("hunger", 0) * 4), (self.state.get("council.winner") or {}).get("skill"),
                    sum(item["failures"] for item in self.state.get("council.skills", {}).values()) // 3]
                unchanged = signature == self.state.get("brain.last_auto_signature")
                if unchanged and now - self.state.get("brain.last_auto_request", 0) < self.state.get("runtime.tempo", {}).get("quiet_interval", 120):
                    return []
            if not self.state.get("brain.busy") and not self.state.get("brain.queued") and not self.state.get("minecraft.motor_busy") and now - self.state.get("brain.last_auto_request", 0) >= max(self.interval, self.state.get("brain.last_pair_seconds", 0) * 1.25):
                self.state.set("brain.last_auto_request", now)
                if self.state.get("council.enabled"):
                    self.state.set("brain.last_auto_signature", signature)
                self.state.set("brain.queued", True)
                return [CognitiveEvent(self.name, "brain.request", {"text": "", "automatic": True})]
        return []
