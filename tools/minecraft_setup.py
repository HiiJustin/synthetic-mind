"""Prepare and launch an isolated loopback-only Minecraft Java laboratory."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "minecraft" / "server"
VERSION = "1.21.4"
MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
EULA = "https://www.minecraft.net/eula"


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def node_executable() -> str:
    node = shutil.which("node")
    if not node:
        path = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
        node = str(path) if path.exists() else None
    if not node:
        raise RuntimeError("Install Node.js 22 or newer, then run this launcher again")
    major = int(subprocess.check_output([node, "--version"], text=True).strip().lstrip("v").split(".")[0])
    if major < 22:
        raise RuntimeError("Node.js 22 or newer is required")
    return node


def install_bridge() -> None:
    node = node_executable()
    bridge = ROOT / "minecraft"
    if (bridge / "node_modules" / "mineflayer").exists() and (bridge / "node_modules" / "mineflayer-pathfinder").exists():
        subprocess.run([node, "-e", "require('mineflayer')"], cwd=bridge, check=True)
        return
    pnpm = shutil.which("pnpm")
    fallback = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm.cmd"
    if not pnpm and fallback.exists():
        pnpm = str(fallback)
    npm = shutil.which("npm")
    if pnpm:
        subprocess.run([pnpm, "install", "--frozen-lockfile", "--ignore-scripts", "--store-dir", str(ROOT / "work" / "pnpm-store")], cwd=bridge, check=True)
    elif npm:
        subprocess.run([npm, "install", "--ignore-scripts", "--no-fund", "--no-audit"], cwd=bridge, check=True)
    else:
        raise RuntimeError("A package manager is needed. Install standard Node.js (includes npm), then retry")


def prepare() -> None:
    install_bridge()
    SERVER.mkdir(parents=True, exist_ok=True)
    jar = SERVER / "server.jar"
    metadata_path = SERVER / "download.json"
    if jar.exists() and metadata_path.exists():
        download = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        print(f"Preparing official Minecraft Java {VERSION} server...", flush=True)
        entry = next(item for item in fetch_json(MANIFEST)["versions"] if item["id"] == VERSION)
        download = fetch_json(entry["url"])["downloads"]["server"]
        partial = jar.with_suffix(".download")
        urllib.request.urlretrieve(download["url"], partial)
        if hashlib.sha1(partial.read_bytes()).hexdigest() != download["sha1"]:
            raise RuntimeError("Official server checksum verification failed")
        partial.replace(jar)
        metadata_path.write_text(json.dumps({**download, "version": VERSION}, indent=2), encoding="utf-8")
    if hashlib.sha1(jar.read_bytes()).hexdigest() != download["sha1"]:
        raise RuntimeError("Server jar checksum does not match the official download")
    properties = SERVER / "server.properties"
    if not properties.exists():
        properties.write_text("\n".join([
            "# Isolated local Synthetic Mind experiment; do not expose this server publicly.",
            "server-ip=127.0.0.1", "server-port=25565", "online-mode=false", "enforce-secure-profile=false",
            "enable-rcon=false", "enable-query=false", "max-players=4", "view-distance=6", "simulation-distance=4",
            "level-name=laboratory-natural-v010", "level-type=minecraft:normal", "level-seed=47849012232314", "generate-structures=true",
            "difficulty=normal", "spawn-monsters=false", "spawn-animals=true", "spawn-protection=0",
            "gamemode=survival", "force-gamemode=false", "motd=Synthetic Mind Local Laboratory", "enable-command-block=false", ""
        ]), encoding="utf-8")
    if not (SERVER / "eula.txt").exists():
        (SERVER / "eula.txt").write_text(f"# Read {EULA} before accepting.\neula=false\n", encoding="utf-8")
    print(f"Ready: Java {VERSION}, Mineflayer 4.39.0, verified official server jar.", flush=True)
    print("Use MINECRAFT_START.cmd. Join from Java 1.21.4: Multiplayer > Direct Connection > 127.0.0.1:25565.", flush=True)


def accept_eula() -> None:
    content = (SERVER / "eula.txt").read_text(encoding="utf-8")
    if any(line.strip().lower() == "eula=true" for line in content.splitlines()):
        return
    print(f"Minecraft requires you to read and accept its EULA before running the server:\n{EULA}")
    answer = input('After reading it, type "I AGREE" to accept, or press Enter to stop: ')
    if answer.strip() != "I AGREE":
        raise RuntimeError("Server was not started; EULA remains unaccepted")
    (SERVER / "eula.txt").write_text(f"# Accepted interactively by the user; {EULA}\neula=true\n", encoding="utf-8")


def java_command() -> list[str]:
    java = shutil.which("java")
    if not java:
        raise RuntimeError("Java 21 or newer is required on PATH for the server")
    version = subprocess.run([java, "-version"], capture_output=True, text=True, check=True)
    import re
    match = re.search(r'version "(\d+)', version.stderr + version.stdout)
    if not match or int(match.group(1)) < 21:
        raise RuntimeError("Java 21 or newer is required")
    return [java, "-Xms512M", "-Xmx3G", "-jar", "server.jar", "nogui"]


def listening() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 25565), timeout=0.2):
            return True
    except OSError:
        return False


def initialize_camp(process) -> None:
    """Operator-owned one-time setup; commands are never exposed to the cognitive agent."""
    properties = (SERVER / "server.properties").read_text()
    if "level-name=laboratory-natural-v010" not in properties:
        return
    marker = SERVER / "laboratory-natural-v010" / "synthetic-camp.json"
    if marker.exists():
        return
    commands = ["gamerule doInsomnia false", "gamerule mobGriefing false", "time set day",
        "fill -6 69 -6 6 69 6 oak_planks", "fill -6 70 -6 6 74 6 air",
        "fill -5 70 -5 -5 72 -5 red_wool", "fill 5 70 -5 5 72 -5 blue_wool",
        "fill -2 70 -4 1 71 -4 stone_bricks", "setblock 4 70 4 chest",
        "setblock -4 70 4 lantern", "summon cow 3 70 2", "summon sheep -3 70 2", "setworldspawn 0 70 0"]
    for command in commands:
        process.stdin.write(command + "\n")
    process.stdin.flush()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"center": {"x": 0, "y": 70, "z": 0}, "description": "Small test camp in natural plains; surrounding terrain remains natural"}, indent=2))
    print("Initialized the natural-world test camp: colored landmarks, obstacle, animals, chest and lantern.", flush=True)


def launch(tempo="normal") -> int:
    prepare()
    command = java_command()
    process = None
    log = None
    camera = None
    try:
        if listening():
            if tempo != "normal":
                raise RuntimeError("Fast mode requires a stopped server so the launcher can own and restore its tick rate")
            print("A server is already listening locally; connecting without starting another one.", flush=True)
        else:
            accept_eula()
            log = (SERVER / "launcher-server.log").open("w", encoding="utf-8")
            process = subprocess.Popen(command, cwd=SERVER, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            print("Starting the laboratory server; first world generation may take a minute...", flush=True)
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Server exited; read minecraft/server/launcher-server.log")
                if listening() and "Done (" in (SERVER / "launcher-server.log").read_text(encoding="utf-8", errors="replace"):
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Server startup timed out; read minecraft/server/launcher-server.log")
            initialize_camp(process)
            process.stdin.write("tick rate " + ("40" if tempo == "fast" else "20") + "\n")
            survival_file=ROOT / "config" / "survival.json"
            if survival_file.exists() and json.loads(survival_file.read_text()).get("enabled"):
                process.stdin.write("difficulty normal\ngamerule doMobSpawning true\ngamerule playersSleepingPercentage 50\n")
            process.stdin.write("tick query\n")
            process.stdin.flush()
        print("\nOpen Minecraft Java 1.21.4 and join 127.0.0.1:25565.\nThe bot will join as SyntheticMind. Console sessions start stopped; STREAM_START enables autonomous learning.\n", flush=True)
        if process:
            from observer_camera import ObserverCamera
            camera = ObserverCamera(process, SERVER / "launcher-server.log")
            camera.start()
        env = {**os.environ, "SYNTHETIC_MIND_TEMPO": tempo, "PYTHONPATH": str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")}
        return subprocess.call([sys.executable, "-B", "-m", "synthetic_mind", "minecraft"], cwd=ROOT, env=env)
    finally:
        if camera:
            camera.close()
        if process and process.poll() is None:
            try:
                assert process.stdin
                process.stdin.write("tick rate 20\nstop\n")
                process.stdin.flush()
                process.wait(timeout=20)
            except (OSError, subprocess.TimeoutExpired):
                process.terminate()
                process.wait(timeout=10)
        if process and process.stdin:
            process.stdin.close()
        if log:
            log.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "start", "server"))
    parser.add_argument("--tempo", choices=("normal", "fast"), default="normal")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare()
        elif args.command == "server":
            prepare()
            command = java_command()
            accept_eula()
            raise SystemExit(subprocess.call(command, cwd=SERVER))
        else:
            raise SystemExit(launch(args.tempo))
    except (RuntimeError, OSError, subprocess.CalledProcessError, StopIteration) as exc:
        print(f"Setup stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
