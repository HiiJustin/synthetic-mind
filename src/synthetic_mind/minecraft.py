from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import sys
import threading
from pathlib import Path

from .config import Config
from .engine import Engine
from .minecraft_modules import (MinecraftBodyModel, MinecraftCritic, MinecraftExecutive,
                                MinecraftOutbox, MinecraftPerception, MinecraftPlanner, MinecraftSalience)
from .survival import survival_agents
from .schemas import CognitiveEvent, utc_now
from .stores import canonical
from .workspace import GlobalWorkspace
from .minecraft_brain import CognitiveCriticAgent, MinecraftBrain
from .minecraft_cognition import (SensoryInterpretationAgent, EpisodicRecallAgent,
    PredictionAgent, ConsolidationAgent, DeliberationPlannerAgent, HomeostasisAgent)
from .council import council_agents
from .tempo import profile


HELP = """Minecraft controls (operator console):
  /server COMMAND     owned server console (operator only; e.g. /server time set day)
  /status             connection, body, drives, motor outcomes
  /sense              last filtered sensory observation
  /move forward|back|left|right|jump  one short movement pulse
  /turn DEGREES       relative horizontal turn
  /look YAW [PITCH]   absolute angles in degrees
  /stop               cancel movement; disable automatic mode
  /auto on|off        goal-directed local cognition (default off)
  /goal TEXT          persistent goal; does not enable movement
  /think              interpret current senses and choose a next step
  /brain              last decision, model status, and budget
  /mind               motivations, disagreements, skills, reflection
  /skills             learned successes/failures and motor reliability
  /learn on|off       enable/disable curiosity experiments (requires /auto on)
  /development on|off require learned muscle effects for autonomous control
  /muscles            learned channel effects, uncertainty and prediction errors
  /muscle m0..m12      activate one bounded muscle channel
  /learning           learned action effects and latest evidence
  /inventory          actively inspect inventory
  /equip ITEM         equip an inventory item
  /eat                eat available food
  /dig X Y Z          break one visible reachable supported material
  /place ITEM X Y Z   place one block above a visible reference block
  /chest X Y Z        inspect chest/barrel contents
  /take ITEM N X Y Z  withdraw up to 8 items from a visible chest/barrel
  /say TEXT           executive speech in Minecraft chat
  /memory QUERY       retrieve episodes
  /events             recent events
  /inspect EVENT_ID   causal record and module traces
  /help               controls
  /quit               stop bot and persist state
Ordinary console text goes to the local model. In game, say !mind hello nearby.
"""


def find_node() -> str:
    executable = shutil.which("node")
    if executable:
        return executable
    bundled = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"
    if bundled.exists():
        return str(bundled)
    raise RuntimeError("Node.js 22+ is required; run MINECRAFT_SETUP.cmd first")


class MinecraftEngine(Engine):
    def __init__(self, directory: Path, config: Config | None = None, database: Path | None = None):
        super().__init__(directory, config, database)
        survival_path=directory / "config" / "survival.json"
        self.survival_config=json.loads(survival_path.read_text()) if survival_path.exists() else {"enabled":False}
        self.state.set("survival.enabled", self.survival_config.get("enabled",False))
        self.state.set("survival.pending", {})
        self.state.set("survival.sleeping", False)
        self.tempo = profile()
        self.state.set("runtime.tempo", self.tempo)
        brain_path = directory / "config" / "brain.json"
        self.brain_config = json.loads(brain_path.read_text(encoding="utf-8")) if brain_path.exists() else {"enabled": False}
        if self.tempo['name'] == 'fast':
            self.brain_config.update(interval_seconds=self.tempo['model_interval'], calls_per_minute=self.tempo['calls_per_minute'], tokens_per_minute=self.tempo['tokens_per_minute'])
        if self.state.get("sensorimotor.developmental") is None:
            self.state.set("sensorimotor.developmental", self.brain_config.get("developmental", False))
        self.state.set("embodied.enabled", False)
        self.state.set("brain.enabled", self.brain_config.get("enabled", False))
        self.state.set("brain.busy", False)
        self.state.set("brain.queued", False)
        self.state.set("brain.control_epoch", self.state.get("brain.control_epoch", 0) + 1)
        self.state.set("council.enabled", self.brain_config.get("architecture") in {"council", "embodied"})
        self.state.set("learning.pending", {})
        self.state.set("muscles.pending", {})
        self.state.set("council.program", None)
        self.state.set("adaptation.window", [])
        self.state.set("adaptation.pending", {})
        self.state.set("council.last_motor", None)
        self.state.set("council.pending_motor", None)
        self.state.set("council.guidance", {})
        self.state.set("council.bids", {})
        self.state.set("council.winner", None)
        self.state.set("minecraft.sensed_at", 0)
        world_path = directory / "config" / "world.json"
        world = json.loads(world_path.read_text()) if world_path.exists() else {"id": "legacy-flat"}
        if self.state.get("minecraft.world_id", "legacy-flat") != world["id"]:
            for key, value in {"learning.containers": {}, "minecraft.map": {}, "minecraft.workspace": {"candidates": {}, "active": [], "revision": 0},
                "council.spatial": {"visits": {}, "landmarks": {}, "sector": None}, "cognition.scene": {}, "cognition.recalled": [], "minecraft.sensed": {}, "survival.build":{}, "survival.destinations":{}, "survival.routines":{}, "adaptation.visits":{}, "adaptation.rewarded_cells":[], "adaptation.window":[]}.items():
                self.state.set(key, value)
        self.state.set("minecraft.world_id", world["id"])
        # The tiny world stays as a regression fixture. These modules and namespaces
        # operate only on Minecraft observations and never read its truth/map.
        for name in ("perception", "salience", "workspace", "body_model", "prediction", "planner", "critic", "executive", "homeostasis", "actuator"):
            self.registry.modules.pop(name, None)
        self.workspace = GlobalWorkspace(self.state, self.config.workspace, "minecraft.workspace")
        aliases = {"minecraft_perception": "perception", "minecraft_body": "body_model", "minecraft_outbox": "actuator"}
        for module in (MinecraftPerception(), MinecraftSalience(self.state), self.workspace,
                       MinecraftBodyModel(self.state, self.self_model), MinecraftPlanner(self.state),
                       MinecraftCritic(self.state), MinecraftExecutive(self.state), MinecraftOutbox()):
            if self.config.enabled_modules is None or aliases.get(module.name, module.name) in self.config.enabled_modules:
                self.registry.register(module)
        if self.brain_config.get("enabled"):
            for agent in (SensoryInterpretationAgent(self.state), HomeostasisAgent(self.state), EpisodicRecallAgent(self.state, self.memory),
                          PredictionAgent(self.state, self.log), ConsolidationAgent(self.state, self.self_model),
                          DeliberationPlannerAgent(self.state, self.brain_config["interval_seconds"]), CognitiveCriticAgent()):
                self.registry.register(agent)
            if self.state.get("council.enabled"):
                for agent in council_agents(self.state, self.self_model):
                    self.registry.register(agent)
                from .adaptation import AdaptiveFeedbackAgent
                self.registry.register(AdaptiveFeedbackAgent(self.state))
                for agent in survival_agents(self.state):
                    self.registry.register(agent)
        if self.brain_config.get("architecture") == "embodied":
            # Keep measured muscle learning and memory; replace fixed bids and motor policies.
            keep = {"spatial_memory", "semantic_memory", "muscle_learning", "sensorimotor_reflection"}
            for agent in council_agents(self.state, self.self_model):
                if agent.name not in keep: self.registry.modules.pop(agent.name, None)
            for agent in survival_agents(self.state): self.registry.modules.pop(agent.name, None)
            self.registry.modules.pop("adaptive_feedback", None)
            from .embodied import modules
            from .minecraft_embodiment import MinecraftEmbodiment
            for agent in [MinecraftEmbodiment(self.state), *modules(self.state)]: self.registry.register(agent)
            self.state.set("embodied.eligibility", [])
            self.state.set("embodied.candidates", [])
            self.state.set("embodied.vitals", None)
            self.state.set("embodied.next_action", 0)
            self.state.set("embodied.enabled", True)
            if self.state.get("embodied.deaths") is None: self.state.set("embodied.deaths", self.state.get("survival.deaths",0))
            self.state.set("sensorimotor.discovery", "Opaque channels and supplied inventory skills; outcomes feed contextual selection")
            self.state.set("council.blocked_reason", None)
        self.state.set("runtime.active_modules", list(self.registry.modules))
        memory = self.registry.modules.get("memory")
        if memory:
            memory.subscriptions = memory.subscriptions | {"minecraft.senses", "minecraft.sound", "minecraft.action_result", "minecraft.chat", "memory.consolidated", "learning.outcome", "muscle.learned", "survival.lesson", "minecraft.damage", "minecraft.death", "minecraft.respawned"}
        self.state.set("minecraft.autonomous", False)
        self.state.set("minecraft.motor_busy", False)
        self.state.set("minecraft.connection", {"connected": False})
        # External effects are not transactionally replayable. Previous-session
        # commands are abandoned; reconnect begins with motor control stopped.
        self.state.set("minecraft.transport_cursor", self.db.connection.execute("SELECT coalesce(max(seq),0) FROM events").fetchone()[0])

    async def start(self) -> None:
        async with self.lock:
            self.bus.publish(CognitiveEvent("runtime", "runtime.boot", {"identity_id": self.self_model.load().identity_id,
                "previous_seen_at": self.start_previous_seen, "environment": "minecraft", "version": "0.16.0", "backend": self.brain_config.get("model", "mock-unused"), "world_id": self.state.get("minecraft.world_id")}))
            await self.bus.drain()

    def status(self) -> dict:
        status = super().status()
        status.update({"version": "0.16.0-minecraft", "environment": "minecraft", "tempo": self.tempo, "connection": self.state.get("minecraft.connection", {}),
                       "council": {"winner": self.state.get("council.winner"), "alternatives": self.state.get("council.disagreements", []),
                           "skills": self.state.get("council.skills", {}), "reflection": self.state.get("council.reflection"),
                           "blocked_reason": self.state.get("council.blocked_reason"), "spatial_sectors": len(self.state.get("council.spatial", {}).get("visits", {}))},
                       "sensorimotor": {"developmental": self.state.get("sensorimotor.developmental"), "discovery": self.state.get("sensorimotor.discovery"), "models": self.state.get("sensorimotor.models", {}), "latest": self.state.get("sensorimotor.latest")},
                       "learning": {"enabled": self.state.get("learning.enabled", True), "actions": self.state.get("learning.actions", {}), "last_lesson": self.state.get("learning.last_lesson"), "affordances": self.state.get("learning.affordances", [])},
                       "brain": {"enabled": self.state.get("brain.enabled"), "model": self.brain_config.get("model"), "busy": self.state.get("brain.busy"), "budget_wait": self.state.get("brain.budget_wait"), "last_error": self.state.get("brain.last_error"), "goal": self.state.get("brain.goal"), "last_decision": self.state.get("brain.last_decision"), "last_review": self.state.get("brain.last_review"), "agents": list(self.registry.modules)},
                       "body": self.state.get("minecraft.sensed", {}), "drives": self.state.get("minecraft.drives", {}),
                       "autonomous": self.state.get("minecraft.autonomous", False),
                       "remembered_blocks": len(self.state.get("minecraft.map", {})),
                       "motor_learning": self.state.get("minecraft.motor_learning", {}),
                       "last_sound": self.state.get("minecraft.last_sound"), "last_error": self.state.get("minecraft.last_error"),
                       "workspace": [{"key": item["key"], "kind": item["kind"], "activation": item["activation"]} for item in self.workspace.items()]})
        status['embodied']={key:self.state.get('embodied.'+key) for key in ('enabled','workspace','selection','feedback','goal_state','deaths')}
        return status


class MinecraftSession:
    def __init__(self, engine: MinecraftEngine, bridge_config: Path):
        self.engine, self.bridge_config = engine, bridge_config
        self.process: asyncio.subprocess.Process | None = None
        self.tasks: list[asyncio.Task] = []
        self.closing = False
        self.disconnected = asyncio.Event()
        self.brain = MinecraftBrain(self, engine.brain_config) if engine.brain_config.get("enabled") else None

    async def start(self) -> None:
        root = self.engine.directory / "minecraft"
        if not (root / "node_modules" / "mineflayer").exists():
            raise RuntimeError("Minecraft dependencies are missing. Run MINECRAFT_SETUP.cmd")
        config = json.loads(self.bridge_config.read_text())
        config['senseIntervalMs'] = self.engine.tempo['sense_ms']
        config['clockProfile'] = self.engine.tempo['name']
        config_file = self.engine.directory / 'work' / ('bridge-session-' + self.engine.tempo['name'] + '.json')
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config["survival"] = self.engine.state.get("survival.enabled", False)
        config_file.write_text(json.dumps(config))
        self.process = await asyncio.create_subprocess_exec(find_node(), str(root / "bridge.js"), str(config_file),
            cwd=root, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        self.tasks = [asyncio.create_task(self._read()), asyncio.create_task(self._stderr()), asyncio.create_task(self._heartbeat())]
        if self.brain:
            self.brain.start()

    async def send(self, content: dict) -> None:
        if not self.process or self.process.returncode is not None or not self.process.stdin:
            raise RuntimeError("Minecraft bridge is not running")
        self.process.stdin.write((canonical(content) + "\n").encode())
        await self.process.stdin.drain()

    async def _flush(self) -> None:
        cursor = self.engine.state.get("minecraft.transport_cursor", 0)
        rows = list(self.engine.db.connection.execute("SELECT seq,body FROM events WHERE seq>? AND kind='minecraft.command' ORDER BY seq", (cursor,)))
        for row in rows:
            event = CognitiveEvent.from_dict(json.loads(row["body"]))
            # Mark before I/O for at-most-once effects. A crash during transport can
            # lose a command, but cannot replay an old movement on reconnect.
            self.engine.state.set("minecraft.transport_cursor", row["seq"])
            try:
                await self.send(event.content)
                self.engine.bus.publish(CognitiveEvent("transport", "minecraft.command_sent", {"command_id": event.content["id"]}, (event.id,)))
            except (RuntimeError, BrokenPipeError, ConnectionError) as exc:
                self.engine.bus.publish(CognitiveEvent("transport", "minecraft.command_error", {"command_id": event.content["id"], "message": str(exc)}, (event.id,)))
            if event.content.get("action") == "say":
                print("[speech] " + event.content["text"], flush=True)
        await self.engine.bus.drain()

    async def ingest(self, kind: str, content: dict) -> None:
        if not kind.startswith("minecraft.") or not isinstance(content, dict):
            raise ValueError("Invalid bridge message")
        if kind == "minecraft.chat" and str(content.get("username", "")).lower() == "firmlygrasp1t":
            command = content.get("text", "").strip().lower()
            if command in {"!start", "!stop", "!shutdown"}:
                async with self.engine.lock:
                    state = self.engine.state
                    state.set("minecraft.autonomous", command == "!start")
                    state.set("brain.control_epoch", state.get("brain.control_epoch", 0) + 1)
                    state.set("brain.last_auto_request", 0)
                    state.set("council.program", None)
                    state.set("council.next_motor", 0)
                if command != "!start":
                    await self.propose({"action": "stop"})
                if command == "!shutdown":
                    self.disconnected.set()
                print("[operator] " + command, flush=True)
                return
            if command.startswith("!camera"):
                return  # The owned server launcher handles the observer camera.
        async with self.engine.lock:
            parents = ()
            if kind in {"minecraft.action_result", "minecraft.command_error"} and content.get("command_id"):
                try:
                    self.engine.log.get(content["command_id"])
                    parents = (content["command_id"],)
                except KeyError:
                    pass
            observed = CognitiveEvent("minecraft", kind, {**content, "world_id": self.engine.state.get("minecraft.world_id")}, parents)
            self.engine.bus.publish(observed)
            if kind == "minecraft.senses":
                self.engine.state.set("minecraft.sensed_at", __import__('time').time())
            await self.engine.bus.drain()
            # Results release the current action. Scheduling its successor inside
            # the same causal root can suppress an identical proposal after it
            # reserves motor_busy. Fresh senses/the independent motor clock
            # schedule the next step without extending the command-result chain.
            if self.engine.state.get("council.enabled") and kind == "minecraft.senses":
                self.engine.bus.publish(CognitiveEvent("runtime", "cognition.cycle", {}, (observed.id,)))
                await self.engine.bus.drain()
            await self._flush()
        if kind in {"minecraft.connected", "minecraft.error", "minecraft.kicked", "minecraft.disconnected", "minecraft.command_error", "minecraft.death"}:
            print(f"[minecraft] {kind}: {canonical(content)}", flush=True)

    async def _read(self) -> None:
        assert self.process and self.process.stdout
        try:
            while line := await self.process.stdout.readline():
                value = json.loads(line)
                if value.get("protocol") != 1:
                    raise ValueError("Unsupported bridge protocol")
                await self.ingest(value["kind"], value["content"])
        except (ValueError, KeyError, RuntimeError, OverflowError) as exc:
            print(f"[minecraft] bridge reader stopped: {exc}", flush=True)
        finally:
            self.engine.state.set("minecraft.autonomous", False)
            self.engine.state.set("minecraft.motor_busy", False)
            self.engine.state.set("minecraft.connection", {"connected": False})
            self.disconnected.set()

    async def _stderr(self) -> None:
        assert self.process and self.process.stderr
        while line := await self.process.stderr.readline():
            print("[bridge] " + line.decode(errors="replace").rstrip(), flush=True)

    async def _heartbeat(self) -> None:
        while not self.closing:
            try:
                await self.send({"id": "heartbeat", "action": "heartbeat"})
            except (RuntimeError, BrokenPipeError, ConnectionError):
                return
            await asyncio.sleep(0.5)

    async def propose(self, content: dict, speech: bool = False) -> None:
        async with self.engine.lock:
            self.engine.state.set("brain.control_epoch", self.engine.state.get("brain.control_epoch", 0) + 1)
            self.engine.state.set("brain.prediction", None)
            self.engine.state.set("council.program", None)
            self.engine.state.set("council.last_motor", None)
            self.engine.state.set("council.next_motor", __import__('time').time() + 3)
            if not self.engine.state.get("minecraft.connection", {}).get("connected", False):
                raise RuntimeError("Bot is not connected/spawned yet")
            if not speech and content.get("action") != "stop" and self.engine.state.get("minecraft.motor_busy", False):
                raise RuntimeError("Wait for the previous motor action to finish")
            if not speech:
                self.engine.state.set("minecraft.motor_busy", content.get("action") != "stop")
            self.engine.bus.publish(CognitiveEvent("operator", "minecraft.speech_proposed" if speech else "minecraft.action_proposed", content))
            await self.engine.bus.drain()
            await self._flush()

    async def close(self) -> None:
        self.closing = True
        if self.brain:
            await self.brain.close()
        if self.process and self.process.returncode is None:
            try:
                await self.send({"id": "shutdown", "action": "disconnect"})
                await asyncio.wait_for(self.process.wait(), 3)
            except (RuntimeError, BrokenPipeError, ConnectionError, TimeoutError):
                if self.process.returncode is None:
                    self.process.kill()
                    await self.process.wait()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


async def minecraft_console(session: MinecraftSession) -> None:
    engine = session.engine
    print("Synthetic Mind Minecraft | identity " + engine.self_model.load().identity_id)
    print(HELP)
    loop = asyncio.get_running_loop()
    lines: asyncio.Queue[str | None] = asyncio.Queue()

    def reader() -> None:
        while True:
            line = sys.stdin.readline()
            try:
                loop.call_soon_threadsafe(lines.put_nowait, line.rstrip() if line else None)
            except RuntimeError:
                return
            if not line:
                return

    threading.Thread(target=reader, daemon=True).start()
    while not session.disconnected.is_set():
        print("minecraft> ", end="", flush=True)
        input_task = asyncio.create_task(lines.get())
        end_task = asyncio.create_task(session.disconnected.wait())
        done, pending = await asyncio.wait((input_task, end_task), return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if end_task in done or input_task.result() is None:
            break
        line = input_task.result().strip()
        if not line:
            continue
        verb, _, argument = line.partition(" ")
        try:
            if verb == "/quit":
                break
            if verb == "/help":
                print(HELP)
            elif verb == "/server":
                import importlib.util
                spec = importlib.util.spec_from_file_location("server_control", engine.directory / "tools" / "server_control.py")
                control = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(control)
                control.enqueue(argument)
                print("[server] Queued; server output is in minecraft/server/launcher-server.log")
            elif verb == "/status":
                print(json.dumps(engine.status(), indent=2))
            elif verb == "/sense":
                print(json.dumps(engine.state.get("minecraft.sensed", {}), indent=2))
            elif verb == "/brain":
                print(json.dumps(engine.status()["brain"], indent=2))
            elif verb == "/mind":
                print(json.dumps(engine.status()["embodied"] if engine.state.get("embodied.enabled") else engine.status()["council"], indent=2))
            elif verb == "/survival":
                print(json.dumps({key:engine.state.get("survival."+key) for key in ("enabled","status","latest","dangers","deaths","build","weapon_trials")},indent=2))
            elif verb == "/assist":
                if argument not in {"on","off"}: raise ValueError("Use /assist on or /assist off")
                engine.state.set("survival.enabled",argument=="on")
                engine.state.set("council.bids",{})
                engine.state.set("council.winner",None)
                await session.propose({"action":"stop"})
                print("[inspect] Supplied survival routine selection "+argument)
            elif verb == "/muscles":
                print(json.dumps(engine.status()["sensorimotor"], indent=2))
            elif verb == "/development":
                if argument not in {"on", "off"}:
                    raise ValueError("Use /development on or /development off")
                engine.state.set("sensorimotor.developmental", argument == "on")
                engine.state.set("council.bids", {})
                engine.state.set("council.winner", None)
                print("[inspect] Developmental control " + argument)
            elif verb == "/muscle":
                args = argument.split()
                if len(args) not in (1, 2):
                    raise ValueError("Use /muscle CHANNEL [350|1800|3500]")
                await session.propose({"action": "muscle", "channel": args[0], "duration_ms": int(args[1]) if len(args) == 2 else 350})
            elif verb == "/learning":
                print(json.dumps(engine.state.get("embodied.models",{}) if engine.state.get("embodied.enabled") else engine.status()["learning"], indent=2))
            elif verb == "/learn":
                if argument not in {"on", "off"}:
                    raise ValueError("Use /learn on or /learn off")
                engine.state.set("learning.enabled", argument == "on")
                engine.state.set("council.bids", {})
                engine.state.set("council.winner", None)
                print("[learning] Curiosity experiments " + argument)
            elif verb in {"/inventory", "/equip", "/eat"}:
                await session.propose({"action": verb[1:], **({"item": argument} if verb == "/equip" else {})})
            elif verb in {"/dig", "/place", "/chest", "/take"}:
                parts = argument.split()
                offset = 1 if verb == "/place" else 2 if verb == "/take" else 0
                if len(parts) != 3 + offset:
                    raise ValueError("Check /help for this action's arguments")
                target = dict(zip(("x", "y", "z"), map(int, parts[offset:])))
                block = next((b for b in engine.state.get("minecraft.sensed", {}).get("visibleBlocks", []) if b["position"] == target), None)
                if not block:
                    raise ValueError("Target must be currently visible; inspect /sense")
                command = {"action": "inspect_container" if verb == "/chest" else verb[1:], "target": target, "block": block["name"]}
                if offset:
                    command["item"] = parts[0]
                if verb == "/take":
                    command["count"] = int(parts[1])
                await session.propose(command)
            elif verb == "/skills":
                print(json.dumps(engine.state.get("embodied.skills",{}) if engine.state.get("embodied.enabled") else engine.state.get("council.skills", {}), indent=2))
            elif verb in {"/goal", "/think"}:
                if not engine.state.get("brain.enabled"):
                    raise ValueError("Local brain disabled; enable config/brain.json")
                if verb == "/goal" and (not argument.strip() or len(argument) > 500):
                    raise ValueError("Use /goal TEXT (1-500 characters)")
                async with engine.lock:
                    if verb == "/goal":
                        engine.state.set("brain.goal", argument)
                        engine.state.set("brain.control_epoch", engine.state.get("brain.control_epoch", 0) + 1)
                        goal = CognitiveEvent("operator", "goal.requested", {"description": argument})
                        engine.bus.publish(goal)
                    engine.bus.publish(CognitiveEvent("operator", "brain.request", {"text": "Consider my new goal: " + argument if verb == "/goal" else "Describe what you notice and a useful next step."}, (goal.id,) if verb == "/goal" else ()))
                    await engine.bus.drain()
                print("[brain] Request queued; /auto on allows motor actions.")
            elif verb == "/memory":
                print(json.dumps([event.to_dict() for event in engine.memory.retrieve(argument)], indent=2))
            elif verb == "/events":
                for event in reversed(engine.log.recent()):
                    print(event.id, event.kind)
            elif verb == "/inspect":
                print(json.dumps(engine.log.inspect(argument), indent=2))
            elif verb == "/move":
                await session.propose({"action": "move", "control": argument})
            elif verb == "/turn":
                sensed = engine.state.get("minecraft.sensed", {})
                if not sensed:
                    raise RuntimeError("Wait for a sensory observation")
                await session.propose({"action": "look", "yaw": sensed["orientation"]["yaw"] + math.radians(float(argument)), "pitch": sensed["orientation"]["pitch"]})
            elif verb == "/look":
                angles = argument.split()
                if len(angles) not in (1, 2):
                    raise ValueError("Use /look YAW [PITCH] in degrees")
                await session.propose({"action": "look", "yaw": math.radians(float(angles[0])), "pitch": math.radians(float(angles[1])) if len(angles) == 2 else 0.0})
            elif verb in {"/stop", "/auto"}:
                if verb == "/auto" and argument not in {"on", "off"}:
                    raise ValueError("Use /auto on or /auto off")
                enabled = verb == "/auto" and argument == "on"
                engine.state.set("minecraft.autonomous", enabled)
                engine.state.set("brain.control_epoch", engine.state.get("brain.control_epoch", 0) + 1)
                engine.state.set("brain.last_auto_request", 0)
                engine.state.set("council.program", None)
                engine.state.set("council.next_motor", 0)
                if not enabled:
                    await session.propose({"action": "stop"})
                print(f"[inspect] automatic movement {'on' if enabled else 'off'}")
            elif verb == "/say":
                await session.propose({"text": argument}, speech=True)
            elif not line.startswith("/"):
                async with engine.lock:
                    engine.bus.publish(CognitiveEvent("operator", "user.text", {"text": "!mind " + line}))
                    await engine.bus.drain()
                    await session._flush()
            else:
                raise ValueError("Unknown command. Use /help")
        except (ValueError, KeyError, RuntimeError) as exc:
            print(f"[inspect] {exc}")


async def run_minecraft(root: Path, database: Path | None = None, bridge_config: Path | None = None) -> None:
    engine = MinecraftEngine(root, Config.load(root / "config" / "default.toml"), database)
    session = MinecraftSession(engine, bridge_config or root / "minecraft" / "config.json")
    clock_task = None
    motor_task = None
    try:
        await engine.start()
        await session.start()

        async def clock_loop() -> None:
            while True:
                await asyncio.sleep(engine.config.runtime.housekeeping_seconds)
                await engine.housekeeping()

        clock_task = asyncio.create_task(clock_loop())
        async def motor_loop():
            while True:
                await asyncio.sleep(engine.tempo["cycle_interval"])
                from .operator_control import drain_controls
                await drain_controls(session, root / "work" / "controls")
                if engine.state.get("council.enabled"):
                    async with engine.lock:
                        engine.bus.publish(CognitiveEvent("runtime", "cognition.cycle", {}))
                        await engine.bus.drain()
                        await session._flush()
        motor_task = asyncio.create_task(motor_loop())
        if os.environ.get("SYNTHETIC_MIND_HEADLESS") == "1":
            engine.state.set("minecraft.autonomous", True)
            print("[operator] Headless stream session; !start, !stop, !shutdown in game chat.", flush=True)
            await session.disconnected.wait()
        else:
            if os.environ.get("SYNTHETIC_MIND_AUTOSTART") == "1":
                engine.state.set("minecraft.autonomous", True)
            await minecraft_console(session)
    finally:
        if clock_task:
            clock_task.cancel()
            await asyncio.gather(clock_task, return_exceptions=True)
        if motor_task:
            motor_task.cancel()
            await asyncio.gather(motor_task, return_exceptions=True)
        await session.close()
        await engine.close()
