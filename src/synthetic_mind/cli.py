from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import unittest
from pathlib import Path

from .engine import Engine


HELP = """Text without / submits a message. Only executive.speech is the agent's speech.
Inspection output is labeled [inspect]. Body outcomes are labeled [body].
  /status                 identity, body, drives, workspace, health
  /map                    explored map (@ body, F food, # wall, ? unknown)
  /step [count]           autonomous body steps (1-200)
  /move east|west|north|south|eat|wait
  /goal description      persist an explicit goal (informational in v0.01)
  /memory query          lexical recall of up to five episodes
  /events [count]        recent canonical events
  /inspect EVENT_ID      event, direct parents, children, deliveries
  /reflect               explicitly exercise mock inference and governor
  /help                  this help
  /quit                  persist and exit cleanly
The REPL runs housekeeping while waiting for input; the body moves only on /step or /move.
"""


def pretty(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=True))


def show_results(events: list) -> None:
    for event in events:
        summary = {key: value for key, value in event.content.items() if key != "observation"}
        print(f"[body] {event.kind}: {json.dumps(summary)}")


def show_speech(engine: Engine, after: int) -> None:
    for row in engine.db.connection.execute("SELECT body FROM events WHERE seq>? AND kind='executive.speech' ORDER BY seq", (after,)):
        print("[speech] " + json.loads(row[0])["content"]["text"])


async def command(engine: Engine, line: str) -> bool:
    before = engine.db.connection.execute("SELECT coalesce(max(seq),0) FROM events").fetchone()[0]
    if not line.startswith("/"):
        event_id = await engine.submit(line)
        print(f"[inspect] input event {event_id}")
    else:
        verb, _, argument = line.partition(" ")
        argument = argument.strip()
        if verb in {"/quit", "/exit"}:
            return False
        if verb == "/help":
            print(HELP)
        elif verb == "/status":
            print("[inspect] status")
            pretty(engine.status())
        elif verb == "/map":
            print("[inspect] explored map\n" + engine.world.render())
        elif verb == "/step":
            count = int(argument or "1")
            if not 1 <= count <= 200:
                raise ValueError("Step count must be 1-200")
            for _ in range(count):
                show_results(await engine.step())
        elif verb == "/move":
            show_results(await engine.step(argument))
        elif verb == "/goal":
            if not argument:
                raise ValueError("Provide a goal description")
            print("[inspect] goal input " + await engine.request_goal(argument))
        elif verb == "/memory":
            print("[inspect] recalled episodes")
            pretty([event.to_dict() for event in engine.memory.retrieve(argument)])
        elif verb == "/events":
            print("[inspect] canonical events")
            for event in reversed(engine.log.recent(max(1, min(200, int(argument or "10"))))):
                print(f"{event.id} {event.source:12} {event.kind}")
        elif verb == "/inspect":
            print("[inspect] causal record")
            pretty(engine.log.inspect(argument))
        elif verb == "/reflect":
            await engine.reflect()
        else:
            raise ValueError("Unknown command. Use /help")
    show_speech(engine, before)
    return True


async def repl(engine: Engine) -> None:
    print("Synthetic Mind v0.01 | deterministic embodied laboratory | no external inference")
    print("Identity: " + engine.self_model.load().identity_id)
    print(HELP)
    loop = asyncio.get_running_loop()
    lines: asyncio.Queue[str | None] = asyncio.Queue()

    def read_input() -> None:
        # A daemon stdin reader avoids an executor thread keeping Windows alive
        # after a quit or Ctrl+C. All engine mutations stay on the event loop.
        while True:
            line = sys.stdin.readline()
            try:
                loop.call_soon_threadsafe(lines.put_nowait, line.rstrip("\r\n") if line else None)
            except RuntimeError:
                return
            if not line:
                return

    threading.Thread(target=read_input, daemon=True).start()

    async def clock_loop() -> None:
        while True:
            await asyncio.sleep(engine.config.runtime.housekeeping_seconds)
            await engine.housekeeping()

    clock_task = asyncio.create_task(clock_loop())
    try:
        while True:
            print("mind> ", end="", flush=True)
            line = await lines.get()
            if line is None:
                break
            if not line.strip():
                continue
            try:
                if not await command(engine, line.strip()):
                    break
            except (ValueError, KeyError, RuntimeError, OverflowError) as exc:
                print(f"[inspect] error: {exc}")
    finally:
        clock_task.cancel()
        try:
            await clock_task
        except asyncio.CancelledError:
            pass


async def run(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[2]
    if args.command == "minecraft":
        from .minecraft import run_minecraft
        await run_minecraft(root, args.db, args.bridge_config)
        return
    from .config import Config
    config = Config.load(args.config or root / "config" / "default.toml")
    engine = Engine(root, config, args.db)
    try:
        await engine.start()
        if args.command == "repl":
            await repl(engine)
        elif args.command == "demo":
            print("[inspect] identity " + engine.self_model.load().identity_id)
            for _ in range(args.steps):
                results = await engine.step()
                show_results(results)
                if any(event.kind == "body.result" and event.content["ate"] for event in results):
                    print("[inspect] Food reached and eaten. Memory and body state will persist.")
                    break
            print("[inspect] explored map\n" + engine.world.render())
            pretty(engine.status())
            if not args.exit_after_demo:
                print("\nDemo finished successfully. Entering interactive mode; try /map or /status.")
                await repl(engine)
            else:
                print("[inspect] Demo finished successfully. Start run.cmd repl to enter commands.")
        elif args.command == "status":
            pretty(engine.status())
        elif args.command == "inspect-event":
            pretty(engine.log.inspect(args.event_id))
    finally:
        await engine.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic Mind v0.01")
    parser.add_argument("--db", type=Path, help="Alternate database; use a fresh path for a new body/identity")
    parser.add_argument("--config", type=Path, help="Alternate TOML configuration")
    subs = parser.add_subparsers(dest="command")
    subs.add_parser("repl")
    subs.add_parser("status")
    minecraft = subs.add_parser("minecraft", help="Connect to the prepared local Minecraft Java server")
    minecraft.add_argument("--bridge-config", type=Path)
    demo = subs.add_parser("demo")
    demo.add_argument("--steps", type=int, default=30)
    demo.add_argument("--exit", dest="exit_after_demo", action="store_true",
                      help="Exit after the demo instead of entering interactive mode")
    inspect = subs.add_parser("inspect-event")
    inspect.add_argument("event_id")
    subs.add_parser("test")
    args = parser.parse_args()
    args.command = args.command or "repl"
    if args.command == "test":
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[2] / "tests"))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
    if args.command == "demo" and not 1 <= args.steps <= 200:
        parser.error("--steps must be 1-200")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nStopped; shutdown was requested.")
    except (ValueError, KeyError, RuntimeError, OverflowError) as exc:
        parser.exit(1, f"Error: {exc}\n")
