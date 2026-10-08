from __future__ import annotations

import math
from dataclasses import asdict

from .survival import valid_routine, ROUTINES
from .schemas import CognitiveEvent
from .experiments import HANDS, valid_hand_action
from .stores import SelfModelStore, StateStore


CONTROLS = {"forward", "back", "left", "right", "jump"}


class MinecraftPerception:
    name, priority = "minecraft_perception", 10
    subscriptions = {"user.text", "minecraft.chat"}

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        content = event.content
        return [CognitiveEvent(self.name, "perception.text", {
            "text": str(content["text"])[:1000], "attribution": content.get("username", "operator"),
            "environment": "minecraft", "world_id": content.get("world_id"), "words": len(str(content["text"]).split())})]


class MinecraftBodyModel:
    name, priority = "minecraft_body", 15
    subscriptions = {"minecraft.senses", "minecraft.sound", "minecraft.connected", "minecraft.disconnected", "minecraft.death", "minecraft.action_result", "minecraft.command_error"}

    def __init__(self, state: StateStore, model: SelfModelStore):
        self.state, self.model = state, model

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        if event.kind == "minecraft.senses":
            self.state.set("minecraft.sensed", {**event.content, "event_id": event.id})
            known = self.state.get("minecraft.map", {})
            for block in event.content.get("visibleBlocks", []):
                pos = block["position"]
                known[f"{pos['x']},{pos['y']},{pos['z']}"] = {"name": block["name"], "seen_at": event.timestamp}
            # Map growth is bounded; episodes retain the older observations.
            self.state.set("minecraft.map", dict(list(known.items())[-10000:]))
            self.state.set("minecraft.drives", {"hunger": event.content["hunger"],
                "health": event.content["health"] / 20, "uncertainty": 1 / (1 + len(known))})
        elif event.kind == "minecraft.sound":
            self.state.set("minecraft.last_sound", event.content)
        elif event.kind == "minecraft.connected":
            self.state.set("minecraft.connection", {**event.content, "connected": True})
            model = self.model.load()
            model.capabilities["minecraft_body"] = 1.0
            model.limitations["minecraft_cognition"] = "Local model deliberation over structured senses; no pixel/audio inference" if self.state.get("brain.enabled") else "Reactive deterministic controller; no language model or pixel/audio inference"
            self.model.save(model)
        elif event.kind == "minecraft.death" and self.state.get("survival.enabled"):
            self.state.set("minecraft.motor_busy", False)
            self.state.set("brain.control_epoch",self.state.get("brain.control_epoch",0)+1)
            self.state.set("council.program", None)
        elif event.kind in {"minecraft.disconnected", "minecraft.death"}:
            self.state.set("minecraft.connection", {"connected": False, "reason": event.kind})
            self.state.set("minecraft.autonomous", False)
        elif event.kind == "minecraft.action_result":
            if event.content.get("action") != "say":
                self.state.set("minecraft.motor_busy", bool(event.content.get("motor_busy", False)))
            self.state.set("minecraft.last_action", event.content)
            if "before" in event.content and "position" in event.content:
                before, after = event.content["before"], event.content["position"]
                moved = math.dist([before[k] for k in ("x", "y", "z")], [after[k] for k in ("x", "y", "z")])
                control = event.content.get("control", "unknown")
                learned = self.state.get("minecraft.motor_learning", {})
                previous = learned.get(control, {"samples": 0, "mean_distance": 0, "blocked": 0})
                count = previous["samples"] + 1
                learned[control] = {"samples": count,
                    "mean_distance": previous["mean_distance"] + (moved - previous["mean_distance"]) / count,
                    "blocked": previous["blocked"] + int(event.content.get("contact", False))}
                self.state.set("minecraft.motor_learning", learned)
        else:
            if event.content.get("action") != "say":
                self.state.set("minecraft.motor_busy", False)
            self.state.set("minecraft.last_error", event.content)
        return []


class MinecraftSalience:
    name, priority = "salience", 20
    subscriptions = {"minecraft.senses", "minecraft.sound", "perception.text", "minecraft.command_error", "goal.created", "prediction.outcome", "drive.changed", "minecraft.reflex"}

    def __init__(self, state=None):
        self.state = state

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        sensory = event.kind == "minecraft.senses"
        urgency = max(event.content.get("hunger", 0.0), 1 - event.content.get("health", 20) / 20) if sensory else 0.4
        if event.kind == "drive.changed":
            urgency = event.content["urgency"]
        if event.kind == "minecraft.reflex":
            urgency = 1.0
        novelty = 0.65
        if sensory and self.state and self.state.get("brain.enabled"):
            novelty = 1.0 if self.state.get("cognition.scene", {}).get("new_block_types") else 0.15
        if event.kind == "prediction.outcome":
            urgency = 0.9 if event.content.get("prediction_error") else 0.2
            novelty = 0.9 if event.content.get("prediction_error") else 0.1
        return [CognitiveEvent(self.name, "attention.candidate", {
            "key": "minecraft.senses" if sensory else "minecraft.sound" if event.kind == "minecraft.sound" else event.id,
            "origin_id": event.id, "kind": event.kind, "payload": event.content,
            "features": {"salience": 0.8, "novelty": novelty, "goal_relevance": 0.9 if sensory else 0.7,
                         "urgency": urgency, "confidence": 1.0}})]


class MinecraftPlanner:
    name, priority = "planner", 45
    subscriptions = {"workspace.broadcast"}

    def __init__(self, state: StateStore):
        self.state = state

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        if self.state.get("brain.enabled", False):
            return []
        if event.content["kind"] != "minecraft.senses" or not self.state.get("minecraft.autonomous", False):
            return []
        if self.state.get("minecraft.motor_busy", False):
            return []
        sensed = event.content["payload"]
        if sensed["health"] <= 0:
            return []
        if sensed["hunger"] > 0.3 and any(item["name"] in {"bread", "apple", "carrot", "baked_potato", "cooked_beef", "cooked_porkchop"} for item in sensed["inventory"]):
            action = {"action": "eat", "reason": "Hunger with food in inventory"}
        elif (sensed["proximity"]["obstructedAhead"] or not sensed["proximity"]["supportedAhead"]
              or sensed["proximity"]["hazardAhead"] or sensed["contact"]["horizontal"]):
            action = {"action": "look", "yaw": sensed["orientation"]["yaw"] + math.pi / 2,
                      "pitch": 0.0, "reason": "Turn away from obstacle, ledge, or hazard"}
        else:
            action = {"action": "move", "control": "forward", "reason": "Explore with a short motor pulse"}
        self.state.set("minecraft.motor_busy", True)
        return [CognitiveEvent(self.name, "minecraft.action_proposed", action)]


class MinecraftCritic:
    name, priority = "critic", 50
    subscriptions = {"minecraft.action_proposed", "minecraft.speech_proposed"}

    def __init__(self, state: StateStore):
        self.state = state

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        content = event.content
        action = content.get("action")
        allowed = action in {"stop", "eat"}
        if action == "muscle":
            allowed = content.get("channel") in self.state.get("minecraft.connection", {}).get("muscle_channels", [f"m{i}" for i in range(13)]) and content.get("duration_ms", 350) in (350, 1800, 3500)
        elif action == "move":
            allowed = content.get("control") in CONTROLS
        elif action == "look":
            allowed = all(type(content.get(key)) in (float, int) and math.isfinite(content[key]) for key in ("yaw", "pitch")) and abs(content["pitch"]) <= math.pi / 2
        elif action in ROUTINES:
            allowed = valid_routine(content, self.state.get("minecraft.sensed", {}), self.state)
        elif action in HANDS:
            allowed = valid_hand_action(content, self.state.get("minecraft.sensed", {}))
        elif event.kind == "minecraft.speech_proposed":
            text = content.get("text", "")
            allowed = isinstance(text, str) and bool(text.strip()) and len(text) <= 200 and not text.strip().startswith("/") and not any(ord(char) < 32 for char in text)
        if not allowed:
            self.state.set("minecraft.motor_busy", False)
        return [CognitiveEvent(self.name, "minecraft.approved" if allowed else "minecraft.rejected", {**content, "speech": event.kind == "minecraft.speech_proposed"})]


class MinecraftExecutive:
    name, priority = "executive", 60
    subscriptions = {"minecraft.approved", "workspace.broadcast", "minecraft.connected"}

    def __init__(self, state=None):
        self.state = state

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        if event.kind == "minecraft.connected":
            if self.state and self.state.get("brain.enabled"):
                return [CognitiveEvent(self.name, "executive.speech", {"text": "Synthetic Mind connected. Local cognition ready. Say !mind hello to talk to me."})]
            return [CognitiveEvent(self.name, "executive.speech", {"text": "Synthetic Mind connected. I am running deterministic cognition. Say !mind hello to talk to me."})]
        if event.kind == "minecraft.approved":
            if event.content["speech"]:
                return [CognitiveEvent(self.name, "executive.speech", {"text": event.content["text"]})]
            return [CognitiveEvent(self.name, "executive.action", event.content)]
        if event.content["kind"] == "perception.text":
            if self.state and self.state.get("brain.enabled"):
                return []
            text = event.content["payload"]["text"]
            # A command prefix makes replies deliberate; nearby casual chat is still perceived.
            if text.casefold().startswith("!mind "):
                reply = "[deterministic] I heard: " + text[6:]
                return [CognitiveEvent(self.name, "executive.speech", {"text": reply[:200]})]
        return []


class MinecraftOutbox:
    name, priority = "minecraft_outbox", 80
    subscriptions = {"executive.action", "executive.speech"}

    async def on_event(self, event: CognitiveEvent) -> list[CognitiveEvent]:
        command = {"id": event.id, **({"action": "say", "text": event.content["text"]} if event.kind == "executive.speech" else event.content)}
        return [CognitiveEvent(self.name, "minecraft.command", command)]
