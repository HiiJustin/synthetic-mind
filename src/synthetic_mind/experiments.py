"""Grounded affordances, independent experiment bids, and persistent consequence learning.

Primitives are supplied by the body. Whether they worked is learned from evidence,
never from a model's description of what it intended to do.
"""
from __future__ import annotations

import math
import re
import time

from .schemas import CognitiveEvent

HANDS = {"inventory", "equip", "dig", "place", "inspect_container", "take"}
NAME = re.compile(r"[a-z0-9_]{1,64}\Z")
MATERIALS = {"dirt", "cobblestone", "oak_planks", "oak_log", "birch_log", "spruce_log"}


def valid_hand_action(content, sensed):
    action = content.get("action")
    if action not in HANDS:
        return False
    item = content.get("item")
    if action in {"equip", "place", "take"} and (not isinstance(item, str) or not NAME.fullmatch(item)):
        return False
    if action in {"equip", "place"} and not any(i["name"] == item and i["count"] > 0 for i in sensed.get("inventory", [])):
        return False
    if action == "place" and item not in MATERIALS:
        return False
    if action == "take" and (type(content.get("count")) is not int or not 1 <= content["count"] <= 8):
        return False
    if action in {"dig", "place", "inspect_container", "take"}:
        target = content.get("target")
        if not isinstance(target, dict) or not all(type(target.get(k)) is int for k in ("x", "y", "z")):
            return False
        match = next((b for b in sensed.get("visibleBlocks", []) if b["position"] == target and b["name"] == content.get("block") and b.get("distance", 999) <= 4), None)
        if not match:
            return False
        if action in {"inspect_container", "take"} and match["name"] not in {"chest", "barrel"}:
            return False
        if action == "dig" and (match["name"] not in MATERIALS or target["y"] < math.floor(sensed["position"]["y"])):
            return False
    return True


def key_for(action):
    return action["action"] + ":" + action.get("item", action.get("block", "body"))


class AffordanceAgent:
    name, priority, subscriptions = "affordance", 22, {"perception.scene"}

    def __init__(self, state):
        self.state = state

    async def on_event(self, event):
        sensed = self.state.get("minecraft.sensed", {})
        goal = self.state.get("brain.goal", "").casefold().split()
        candidates = [{"action": "inventory", "expected": "Inventory observation arrives"}]
        for item in sensed.get("inventory", [])[:12]:
            if item["name"] != sensed.get("heldItem"):
                candidates.append({"action": "equip", "item": item["name"], "expected": "Held item becomes " + item["name"]})
        containers = self.state.get("learning.containers", {})
        for block in sensed.get("visibleBlocks", []):
            if block.get("distance", 999) > 4:
                continue
            target = {"target": block["position"], "block": block["name"]}
            if block["name"] in {"chest", "barrel"}:
                candidates.append({"action": "inspect_container", **target, "expected": "Container contents become observable"})
                remembered = containers.get(str(block["position"]), {})
                if sensed.get("hunger", 0) > 0.15 and not any(i["name"] == "bread" for i in sensed.get("inventory", [])):
                    if any(i["name"] == "bread" and i["count"] > 0 for i in remembered.get("contents", [])):
                        candidates.append({"action": "take", "item": "bread", "count": 1, **target, "expected": "Inventory bread count increases", "need": True})
            if any(w in goal for w in ("harvest", "gather", "collect", "dig")) and block["name"].endswith("_log"):
                candidate = {"action": "dig", **target, "expected": "Target block changes; item pickup is a separate observation", "need": True}
                if valid_hand_action(candidate, sensed):
                    candidates.append(candidate)
        self.state.set("learning.affordances", candidates[:24])
        return [CognitiveEvent(self.name, "affordance.available", {"candidates": candidates[:24], "sensory_id": event.content["source_id"]})]


class ExperimentAgent:
    name, priority, subscriptions = "experiment_planner", 24, {"affordance.available"}

    def __init__(self, state):
        self.state = state

    async def on_event(self, event):
        if self.state.get("sensorimotor.developmental") or not self.state.get("learning.enabled", True):
            return []
        records = self.state.get("learning.actions", {})
        choices = []
        for action in event.content["candidates"]:
            record = records.get(key_for(action), {})
            # Repeated failures are evidence to stop trying, not invitations to spin.
            if record.get("retry_after", 0) > time.time() or record.get("failures", 0) >= 3:
                continue
            samples = record.get("successes", 0) + record.get("failures", 0)
            score = 0.89 if action.get("need") else 0.84 if samples == 0 else 0.35
            choices.append((score, action))
        if not choices:
            return []
        score, action = max(choices, key=lambda pair: pair[0])
        return [CognitiveEvent(self.name, "motivation.proposal", {"role": "experiment", "skill": "experiment", "score": score,
            "reason": "Test an available primitive against measured consequences", "target": None,
            "experiment": action, "sensory_id": event.content["sensory_id"]})]


class ConsequenceLearningAgent:
    name, priority, subscriptions = "consequence_learning", 58, {"minecraft.command", "minecraft.action_result", "minecraft.command_error", "minecraft.rejected"}

    def __init__(self, state, model):
        self.state, self.model = state, model

    async def on_event(self, event):
        pending = self.state.get("learning.pending", {})
        if event.kind == "minecraft.command":
            if event.content.get("action") in HANDS | {"eat"}:
                pending[event.content["id"]] = {"action": event.content, "evidence": event.id}
                self.state.set("learning.pending", dict(list(pending.items())[-16:]))
            return []
        if event.kind == "minecraft.rejected":
            self.state.set("council.pending_motor", None)
            return []
        active = pending.pop(event.content.get("command_id"), None)
        if not active:
            return []
        self.state.set("learning.pending", pending)
        action = active["action"]
        success = event.kind == "minecraft.action_result" and event.content.get("verified") is True
        records = self.state.get("learning.actions", {})
        key = key_for(action)
        record = records.get(key, {"successes": 0, "failures": 0})
        record["successes" if success else "failures"] += 1
        record.update(confidence=(record["successes"] + 1) / (record["successes"] + record["failures"] + 2),
                      evidence_id=event.id, retry_after=time.time() + (5 if success else 30))
        records[key] = record
        self.state.set("learning.actions", dict(list(records.items())[-256:]))
        if success and action["action"] in {"inspect_container", "take"}:
            containers = self.state.get("learning.containers", {})
            contents = event.content.get("contents", [])
            if action["action"] == "take":
                contents = [{**i, "count": max(0, i["count"] - action["count"])} if i["name"] == action["item"] else i for i in contents]
            containers[str(action["target"])] = {"contents": contents, "evidence_id": event.id}
            self.state.set("learning.containers", dict(list(containers.items())[-64:]))
        lesson = {"primitive": key, "success": success, "prediction": action.get("expected", "Measured primitive effect"),
                  "observed": {k: event.content[k] for k in ("before", "after", "block_before", "block_after", "verified", "message") if k in event.content},
                  "evidence_id": event.id, "world_id": self.state.get("minecraft.world_id")}
        self.state.set("learning.last_lesson", lesson)
        model = self.model.load()
        model.capabilities["action:" + key] = record["confidence"]
        self.model.save(model)
        return [CognitiveEvent(self.name, "learning.outcome", lesson, (event.id, active["evidence"])),
                CognitiveEvent(self.name, "attention.candidate", {"key": "learning.outcome", "origin_id": event.id, "kind": "learning.outcome", "payload": lesson,
                    "features": {"salience": 0.9, "novelty": 0.9, "goal_relevance": 0.8, "urgency": 0.3 if success else 0.8, "confidence": 1.0}})]


def experiment_agents(state, model):
    return [AffordanceAgent(state), ExperimentAgent(state), ConsequenceLearningAgent(state, model)]
