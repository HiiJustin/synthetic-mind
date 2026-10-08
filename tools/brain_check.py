"""Check the local shared inference backend, optionally test both cognitive roles."""
from pathlib import Path
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from synthetic_mind.models import ollama_request, OllamaModelBackend
from synthetic_mind.minecraft_brain import SCHEMA, SYSTEM, CognitiveCriticAgent, MinecraftBrain


async def check():
    config = json.loads((ROOT / "config/brain.json").read_text())
    if not config.get("enabled"):
        print("Local cognition disabled in config/brain.json.")
        return
    try:
        tags = await ollama_request("/api/tags", timeout=3)
    except (OSError, TimeoutError):
        executable = shutil.which("ollama") or str(Path.home() / "AppData/Local/Programs/Ollama/ollama.exe")
        if not Path(executable).exists():
            raise RuntimeError("Install/start Ollama, then run: ollama pull " + config["model"])
        log_dir = ROOT / "work"
        log_dir.mkdir(exist_ok=True)
        with (log_dir / "ollama-start.log").open("ab") as log:
            subprocess.Popen([executable, "serve"], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        for _ in range(20):
            await asyncio.sleep(0.5)
            try:
                tags = await ollama_request("/api/tags", timeout=2)
                break
            except (OSError, TimeoutError):
                continue
        else:
            raise RuntimeError("Ollama did not start. Read work/ollama-start.log")
    names = {item["name"] for item in tags["models"]}
    if config["model"] not in names:
        raise RuntimeError("Model missing. Run: ollama pull " + config["model"])
    print(f"Ready: {config['model']} on local Ollama. One shared backend; planner and critic are separate agents.")
    if "--smoke" in sys.argv:
        # Synthetic observation fixture, not evidence of a live Minecraft session.
        context = {"human_message": "Hello! What can you actually see?", "goal": "Observe cautiously",
            "scene": {"blocks": {"grass_block": 12}, "new_block_types": ["grass_block"], "entities": []},
            "body": {"position": {"x": 0, "y": 4, "z": 0}, "orientation": {"yaw": 0, "pitch": 0},
                "health": 20, "hunger": 0.1, "onGround": True,
                "proximity": {"obstructedAhead": False, "supportedAhead": True, "hazardAhead": False}, "inventory": []},
            "memories": [], "outcome": None, "attention": [], "autobiography": []}
        backend = OllamaModelBackend(config["model"], SCHEMA)
        start = time.monotonic()
        decision = MinecraftBrain.validate(await backend.generate(system=SYSTEM, input_text=json.dumps(context), max_tokens=384))
        metrics = dict(backend.metrics)
        reviewed = await CognitiveCriticAgent().review(backend, context, decision)
        print(json.dumps({"fixture": "synthetic grass scene", "decision": decision, "review": reviewed,
            "planner_metrics": metrics, "critic_metrics": backend.metrics, "elapsed_seconds": round(time.monotonic() - start, 2),
            "loaded_models": await ollama_request("/api/ps")}, indent=2))
        if not reviewed["approved"]:
            raise RuntimeError("Model returned a valid plan, but the independent critic rejected it")


if __name__ == "__main__":
    try:
        asyncio.run(check())
    except (RuntimeError, OSError, ValueError, KeyError, TimeoutError) as exc:
        print("Brain setup stopped: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
