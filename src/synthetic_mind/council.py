"""Sparse recurrent cognitive council and learned bounded motor programs.

Specialists make bids; the arbiter selects an intention; skills are checked against
fresh senses on every step and still pass through critic/executive/outbox.
"""
from __future__ import annotations

import re
import math
import time
from collections import Counter

from .survival import ROUTINES
from .schemas import CognitiveEvent
from .experiments import HANDS, experiment_agents
from .muscles import MuscleLearningAgent, MotorBabblingAgent, SensorimotorReflectionAgent, learned_forward, choose_channel


FOODS = {"bread", "apple", "carrot", "baked_potato", "cooked_beef", "cooked_porkchop"}


class SpatialMemoryAgent:
    name, priority, subscriptions = "spatial_memory", 19, {"minecraft.senses"}

    def __init__(self, state):
        self.state = state

    async def on_event(self, event):
        pos = event.content["position"]
        sector = f"{math.floor(pos['x']/4)},{math.floor(pos['z']/4)}"
        spatial = self.state.get("council.spatial", {"visits": {}, "landmarks": {}, "sector": None})
        entered = sector != spatial["sector"]
        if entered:
            spatial["visits"][sector] = spatial["visits"].get(sector, 0) + 1
            spatial["visits"] = dict(list(spatial["visits"].items())[-2048:])
        spatial["sector"] = sector
        for block in event.content.get("visibleBlocks", []):
            if any(word in block["name"] for word in ("log", "lantern", "wool", "chest", "water", "flower", "door", "crops", "bed")):
                p = block["position"]
                key = f"{p['x']},{p['y']},{p['z']}"
                spatial["landmarks"][key] = {"name": block["name"], "position": p, "event_id": event.id}
        spatial["landmarks"] = dict(list(spatial["landmarks"].items())[-512:])
        self.state.set("council.spatial", spatial)
        if entered:
            return [CognitiveEvent(self.name, "spatial.entered", {"sector": sector, "visits": spatial["visits"][sector], "world_id": event.content.get("world_id")})]
        return []


class SemanticMemoryAgent:
    name, priority, subscriptions = "semantic_memory", 43, {"prediction.outcome", "perception.scene"}

    def __init__(self, state):
        self.state = state

    async def on_event(self, event):
        semantic = self.state.get("council.semantic", {"block_types": {}, "action_stats": {}})
        if event.kind == "perception.scene":
            for name in event.content["blocks"]:
                semantic["block_types"][name] = {"last_evidence": event.id}
            semantic["block_types"] = dict(list(semantic["block_types"].items())[-128:])
        else:
            observed = event.content["observed"]
            action = observed.get("action", "unknown")
            record = semantic["action_stats"].get(action, {"samples": 0, "blocked": 0, "mean_distance": 0})
            count = record["samples"] + 1
            distance = event.content.get("distance")
            semantic["action_stats"][action] = {"samples": count, "blocked": record["blocked"] + int(event.content.get("blocked", False)),
                "mean_distance": record["mean_distance"] if distance is None else record["mean_distance"] + (distance - record["mean_distance"]) / count,
                "evidence_id": event.id}
        self.state.set("council.semantic", semantic)
        return []


class MotivationAgent:
    priority, subscriptions = 24, {"perception.scene"}

    def __init__(self, state, role):
        self.state, self.role = state, role
        self.name = "motivation_" + role

    async def on_event(self, event):
        sensed = self.state.get("minecraft.sensed", {})
        drives = self.state.get("cognition.drives", {})
        proximity = sensed.get("proximity", {})
        blocked = (proximity.get("obstructedAhead", True) or not proximity.get("supportedAhead", False)) and not proximity.get("canStepUp", False) or proximity.get("hazardAhead", True)
        skill, score, reason = "observe", 0.2, "Gather another observation"
        if self.role == "preservation":
            edible = any(item["name"] in FOODS for item in sensed.get("inventory", []))
            if edible and sensed.get("hunger", 0) > 0.15 and (not self.state.get("sensorimotor.developmental") or choose_channel(self.state, "food", minimum=0.5, contextual=True)):
                skill, score, reason = "eat", 0.9 + 0.1 * sensed["hunger"], "Available food can reduce hunger"
            elif blocked:
                skill, score, reason = "orient", (0.80 if self.state.get("sensorimotor.developmental") and not (choose_channel(self.state, "yaw", 1) or choose_channel(self.state, "yaw", -1)) else 0.95), "Path blocked, unsupported or hazardous; reorient before moving"
        elif self.role == "curiosity":
            visits = self.state.get("council.spatial", {}).get("visits", {})
            sector = self.state.get("council.spatial", {}).get("sector")
            skill, score, reason = "explore", 0.58 + 0.15 * drives.get("curiosity", 0.5), "Explore a safe direction and sample consequences"
            if visits.get(sector, 0) > 3 and self.state.get("council.reoriented_sector") != sector:
                skill, score, reason = "orient", 0.78, "Repeatedly visited sector; seek a different heading"
        elif self.role == "goal":
            goal = self.state.get("brain.goal", "explore cautiously").casefold()
            if goal.split()[:1] and goal.split()[0] in {"stay", "wait", "rest", "stop"}:
                skill, score, reason = "rest", 0.98, "The persistent operator goal asks for stillness"
            else:
                words = set(re.findall(r"[a-z_]+", goal)) - {"and", "the", "for", "with", "from", "your", "when", "into", "toward", "different", "visible"}
                reached = self.state.get("council.reached_landmarks", {})
                pos = sensed.get("position", {})
                def eligible(block):
                    key = str(block["position"])
                    b = block["position"]
                    nearby = math.hypot(b["x"]+.5-pos.get("x",0), b["z"]+.5-pos.get("z",0)) < 2
                    matches = bool(words & (set(block["name"].split("_")) | {block["name"]}))
                    return matches and not nearby and reached.get(key, 0) < time.time()
                hits = [block for block in sensed.get("visibleBlocks", []) if eligible(block)]
                if hits:
                    target = min(hits, key=lambda block: block.get("distance", 999))
                    skill, score, reason = "approach", 0.82, "A currently visible landmark matches the working goal"
                else:
                    target = None
                    skill, score, reason = "explore", 0.62, "Exploration supports the working goal"
                guidance = self.state.get("council.guidance", {})
                if guidance.get("until", 0) > time.time() and guidance.get("action") == "forward" and skill == "explore":
                    score += 0.08
                    reason += "; deliberation corroborates exploration"
                return [CognitiveEvent(self.name, "motivation.proposal", {"role": self.role, "skill": skill, "score": score,
                    "reason": reason, "target": target, "sensory_id": event.content["source_id"]})]
        return [CognitiveEvent(self.name, "motivation.proposal", {"role": self.role, "skill": skill, "score": score,
            "reason": reason, "target": None, "sensory_id": event.content["source_id"]})]


class ExplorationRecoveryAgent:
    """Measured lack of spatial progress contributes a competing recovery bid."""
    name, priority, subscriptions = "exploration_recovery", 26, {"perception.scene"}

    def __init__(self, state): self.state = state

    async def on_event(self, event):
        sensed = self.state.get("minecraft.sensed", {})
        pos = sensed.get("position")
        now = time.time()
        if not pos or not self.state.get("minecraft.autonomous"):
            self.state.set("navigation.progress", None)
            return []
        progress = self.state.get("navigation.progress")
        if not progress or math.hypot(pos["x"]-progress["x"],pos["z"]-progress["z"]) > 1.5:
            self.state.set("navigation.progress", {"x":pos["x"],"z":pos["z"],"since":now})
            return []
        goal = self.state.get("brain.goal", "").lower().split()
        if now-progress["since"] < 30 or goal[:1] and goal[0] in {"stay","wait","rest","stop"}:
            return []
        proximity = sensed.get("proximity", {})
        safe = not proximity.get("obstructedAhead", True) and proximity.get("supportedAhead", False) and not proximity.get("hazardAhead", True)
        skill = "explore" if safe else "orient"
        if self.state.get("sensorimotor.developmental"):
            available = choose_channel(self.state, "forward") if safe else (choose_channel(self.state, "yaw", 1) or choose_channel(self.state, "yaw", -1))
            if available is None:
                # Do not outbid discovery with an intention the body cannot execute.
                self.state.set("navigation.recovery", {"reason":"Recovery needs measured muscle effects; yielding to discovery", "since":progress["since"]})
                return []
        self.state.set("navigation.recovery", {"reason":"No spatial progress for 30 seconds", "skill":skill,"since":progress["since"]})
        return [CognitiveEvent(self.name,"motivation.proposal",{"role":"recovery","skill":skill,"score":.89,
            "reason":"No spatial progress; test a safe direction through learned motor channels", "target":None,
            "sensory_id":event.content["source_id"]})]


class CouncilArbiterAgent:
    name, priority, subscriptions = "council_arbiter", 38, {"motivation.proposal", "cognition.cycle"}

    def __init__(self, state):
        self.state = state

    async def on_event(self, event):
        if event.kind == "motivation.proposal":
            bids = self.state.get("council.bids", {})
            bids[event.content["role"]] = {**event.content, "event_id": event.id}
            self.state.set("council.bids", bids)
            return []
        sensory_id = self.state.get("minecraft.sensed", {}).get("event_id")
        bids = [bid for bid in self.state.get("council.bids", {}).values() if bid["sensory_id"] == sensory_id]
        if not bids:
            return []
        winner = max(bids, key=lambda bid: (bid["score"], bid["role"]))
        previous = self.state.get("council.winner") or {}
        self.state.set("council.winner", winner)
        self.state.set("council.disagreements", [{"role": bid["role"], "skill": bid["skill"], "score": bid["score"], "reason": bid["reason"]} for bid in bids if bid != winner])
        if previous.get("skill") == winner["skill"] and previous.get("reason") == winner["reason"]:
            return []
        selected = CognitiveEvent(self.name, "motivation.selected", {"winner": winner, "alternatives": bids}, tuple(bid["event_id"] for bid in bids))
        return [selected]


class MotorSkillAgent:
    name, priority, subscriptions = "motor_skills", 55, {"cognition.cycle", "brain.decision", "minecraft.action_result", "minecraft.command_error"}

    def __init__(self, state):
        self.state = state

    async def on_event(self, event):
        if event.kind == "brain.decision":
            if event.content.get("approved"):
                self.state.set("council.guidance", {"action": event.content["action"], "focus": event.content["focus"], "event_id": event.id, "until": time.time() + 30})
            return []
        if event.kind in {"minecraft.action_result", "minecraft.command_error"}:
            active = self.state.get("council.last_motor")
            # Only the matching command may advance the current skill; speech acks cannot.
            if not active or event.content.get("command_id") != active.get("command_id"):
                return []
            result = event.content
            distance = math.dist([result["before"][key] for key in ("x", "y", "z")], [result["position"][key] for key in ("x", "y", "z")]) if "before" in result and "position" in result and "x" in result["before"] else None
            failed = event.kind == "minecraft.command_error" or result.get("verified") is False or bool(result.get("contact")) or distance is not None and distance < 0.08
            learned = self.state.get("council.skills", {})
            record = learned.get(active["skill"], {"successes": 0, "failures": 0})
            record["failures" if failed else "successes"] += 1
            record["confidence"] = (record["successes"] + 1) / (record["successes"] + record["failures"] + 2)
            learned[active["skill"]] = record
            self.state.set("council.skills", learned)
            self.state.set("council.last_motor", None)
            if failed:
                self.state.set("council.force_orient", active["skill"] not in {"experiment", "muscle_experiment"})
                self.state.set("council.program", None)
            return [CognitiveEvent(self.name, "skill.outcome", {"skill": active["skill"], "failed": failed, "distance": distance, "expected": active["expected"], "evidence_id": event.id})]
        if not self.state.get("minecraft.autonomous") or self.state.get("minecraft.motor_busy"):
            return []
        sensed = self.state.get("minecraft.sensed", {})
        if not sensed or sensed.get("health", 0) <= 0 or not self.state.get("minecraft.connection", {}).get("connected"):
            return []
        if sensed.get("sleeping") or self.state.get("survival.sleeping"):
            self.state.set("council.blocked_reason", "Sleeping; waiting for dawn or wake event")
            return []
        if not sensed.get("onGround"):
            self.state.set("council.blocked_reason", "Waiting to land before the next motor step")
            return []
        if time.time() - self.state.get("minecraft.sensed_at", 0) > 3:
            self.state.set("council.blocked_reason", "Waiting for fresh senses")
            return []
        if time.time() < self.state.get("council.next_motor", 0):
            return []
        winner = self.state.get("council.winner")
        if not winner:
            self.state.set("council.blocked_reason", "Waiting for specialist proposals")
            return []
        skill = winner["skill"]
        guidance = self.state.get("council.guidance", {})
        if guidance.get("until", 0) > time.time() and guidance.get("action") == "eat" and skill not in {"rest", "orient", "routine"}:
            skill = "eat"
        if self.state.get("council.force_orient") and skill not in {"muscle_experiment", "rest", "routine"}:
            skill = "orient"
        if skill in {"rest", "observe"}:
            self.state.set("council.blocked_reason", winner["reason"])
            return []
        proximity = sensed.get("proximity", {})
        path_safe = sensed.get("onGround") and ((not proximity.get("obstructedAhead", True) and proximity.get("supportedAhead", False)) or proximity.get("canStepUp", False)) and not proximity.get("hazardAhead", True)
        yaw = sensed["orientation"]["yaw"]
        action = None
        if skill == "muscle_experiment":
            action = {"action": "muscle", "channel": winner["channel"], "duration_ms": winner.get("duration_ms", 350)}
        elif skill in {"experiment", "routine"}:
            action = dict(winner.get("experiment") or {})
        elif skill == "eat":
            if sensed.get("hunger", 0) > 0.1 and any(item["name"] in FOODS for item in sensed.get("inventory", [])):
                action = {"action": "eat"}
        elif skill == "orient" or not path_safe:
            action = {"action": "look", "yaw": yaw + math.pi / 2, "pitch": 0.0}
            self.state.set("council.force_orient", False)
            self.state.set("council.reoriented_sector", self.state.get("council.spatial", {}).get("sector"))
            skill = "orient"
        elif skill == "approach" and winner.get("target"):
            pos, target = sensed["position"], winner["target"]["position"]
            dx, dz = target["x"] + 0.5 - pos["x"], target["z"] + 0.5 - pos["z"]
            target_yaw = math.atan2(-dx, -dz)
            error = math.atan2(math.sin(target_yaw - yaw), math.cos(target_yaw - yaw))
            if math.hypot(dx, dz) < 2:
                reached = self.state.get("council.reached_landmarks", {})
                reached[str(target)] = time.time()+300
                self.state.set("council.reached_landmarks", dict(list(reached.items())[-128:]))
                self.state.set("council.blocked_reason", "Landmark inspected; selecting a new intention")
                self.state.set("council.bids", {})
                self.state.set("council.winner", None)
                return [CognitiveEvent(self.name, "navigation.landmark_reached", {"position": target}, (event.id,))]
            action = {"action": "look", "yaw": target_yaw, "pitch": 0.0} if abs(error) > 0.25 else {"action": "move", "control": "forward"}
        else:
            program = self.state.get("council.program")
            if not program or program.get("remaining", 0) <= 0 or program["expires"] < time.time():
                successes = self.state.get("council.skills", {}).get("explore", {}).get("successes", 0)
                program = {"remaining": min(6, 2 + successes // 3), "expires": time.time() + 12}
            action = {"action": "move", "control": "forward"}
            program["remaining"] -= 1
            self.state.set("council.program", program)
        if not action:
            self.state.set("council.blocked_reason", "No applicable safe motor skill")
            return []
        if skill != "routine" and self.state.get("sensorimotor.developmental") and action["action"] in {"move", "look", "eat"}:
            if action["action"] == "move":
                selected = choose_channel(self.state, "forward")
            elif action["action"] == "eat":
                selected = choose_channel(self.state, "food", minimum=0.5, contextual=True)
            else:
                delta = math.atan2(math.sin(action["yaw"] - yaw), math.cos(action["yaw"] - yaw))
                selected = choose_channel(self.state, "yaw", 1 if delta >= 0 else -1)
                if selected is None:
                    selected = choose_channel(self.state, "yaw", -1 if delta >= 0 else 1)
            if selected is None:
                self.state.set("council.blocked_reason", "Waiting for measured muscle effects; no named-action fallback in developmental mode")
                return []
            action = selected
        elif action["action"] == "move" and action.get("control") == "forward" and not proximity.get("canStepUp"):
            channel = learned_forward(self.state)
            if channel:
                action = {"action": "muscle", "channel": channel}
        if action["action"] == "move" and proximity.get("canStepUp"):
            action["jump"] = True
        self.state.set("council.blocked_reason", None)
        self.state.set("council.next_motor", time.time() + self.state.get("runtime.tempo", {}).get("motor_interval", 1.5))
        self.state.set("minecraft.motor_busy", True)
        proposal = CognitiveEvent(self.name, "minecraft.action_proposed", {**action, "skill": skill, "reason": winner["reason"]}, (event.id, winner["event_id"]))
        self.state.set("council.pending_motor", {"proposal_id": proposal.id, "skill": skill, "expected": "positive displacement" if action["action"] == "move" else "completed " + action["action"]})
        return [proposal]


class MotorAttributionAgent:
    name, priority, subscriptions = "motor_attribution", 85, {"minecraft.command"}

    def __init__(self, state):
        self.state = state

    async def on_event(self, event):
        if event.content.get("action") not in ({"move", "look", "eat", "muscle"} | HANDS | ROUTINES) or not event.content.get("skill"):
            return []
        pending = self.state.get("council.pending_motor")
        if pending:
            self.state.set("council.last_motor", {**pending, "command_id": event.content["id"]})
        return []


class BackgroundReflectionAgent:
    name, priority, subscriptions = "background_reflection", 72, {"clock.tick", "skill.outcome"}

    def __init__(self, state, model):
        self.state, self.model = state, model

    async def on_event(self, event):
        if event.kind == "skill.outcome" and event.content["failed"]:
            return [CognitiveEvent(self.name, "attention.candidate", {"key": "skill.failure", "origin_id": event.id, "kind": event.kind,
                "payload": event.content, "features": {"salience": 0.9, "novelty": 0.9, "goal_relevance": 0.9, "urgency": 0.8, "confidence": 1}})]
        now = time.time()
        if event.kind != "clock.tick" or now - self.state.get("council.reflected_at", 0) < 20:
            return []
        self.state.set("council.reflected_at", now)
        skills = self.state.get("council.skills", {})
        failures = sum(item["failures"] for item in skills.values())
        successes = sum(item["successes"] for item in skills.values())
        summary = {"successes": successes, "failures": failures, "active_intention": (self.state.get("council.winner") or {}).get("skill"),
            "lesson": "Reorient after blocked moves; retain successful short programs" if failures else "Continue testing safe short actions", "evidence": "Measured skill outcomes; not subjective introspection"}
        self.state.set("council.reflection", summary)
        model = self.model.load()
        model.capabilities["minecraft_motor_reliability"] = (successes + 1) / (successes + failures + 2)
        self.model.save(model)
        return [CognitiveEvent(self.name, "reflection.summary", summary)]


def council_agents(state, model):
    return [SpatialMemoryAgent(state), SemanticMemoryAgent(state), *[MotivationAgent(state, role) for role in ("preservation", "curiosity", "goal")],
        ExplorationRecoveryAgent(state), CouncilArbiterAgent(state), MotorSkillAgent(state), MotorAttributionAgent(state), BackgroundReflectionAgent(state, model), *experiment_agents(state, model), MotorBabblingAgent(state), MuscleLearningAgent(state), SensorimotorReflectionAgent(state, model)]
