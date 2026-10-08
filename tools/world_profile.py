"""Switch to a new natural test world without deleting the existing world."""
from __future__ import annotations
from pathlib import Path
import argparse
import json
import re
import shutil
import socket
import time


ROOT = Path(__file__).resolve().parents[1]


def apply_profile(root: Path, *, check_running=True):
    server = (root / "minecraft/server").resolve()
    if check_running:
        try:
            with socket.create_connection(("127.0.0.1", 25565), timeout=0.3):
                raise RuntimeError("Close the bot and old server before switching world profiles")
        except OSError:
            pass
    profile = json.loads((root / "config/world.json").read_text())
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", profile["level_name"]):
        raise ValueError("Invalid world directory name")
    target = (server / profile["level_name"]).resolve()
    if target.parent != server:
        raise ValueError("World path escaped the server directory")
    properties = server / "server.properties"
    if not properties.exists():
        raise RuntimeError("Run MINECRAFT_SETUP.cmd first")
    original = properties.read_text(encoding="utf-8")
    values = {}
    for line in original.splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    if values.get("level-name") == profile["level_name"] and values.get("level-type", "").replace('\\:', ':') == profile["generator"]:
        print("Natural test world already selected; it will not be regenerated.")
        return None
    backup = server / "backups" / time.strftime("profile-%Y%m%d-%H%M%S")
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(properties, backup / "server.properties")
    previous = values.get("level-name", "world")
    values.update({"level-name": profile["level_name"], "level-type": profile["generator"], "level-seed": profile["seed"],
        "generate-structures": "true", "difficulty": "easy", "spawn-monsters": "false", "spawn-animals": "true",
        "server-ip": "127.0.0.1", "server-port": "25565", "online-mode": "false", "enforce-secure-profile": "false",
        "motd": "Synthetic Mind v0.10 Natural Cognitive Laboratory"})
    (backup / "recovery.json").write_text(json.dumps({"previous_level_name": previous, "preserved_world": str(server / previous),
        "new_world": str(target), "restore": "Stop the server and restore this saved server.properties to switch back; no world directory was deleted."}, indent=2))
    temporary = properties.with_suffix(".tmp")
    temporary.write_text("# Synthetic Mind natural laboratory; previous profile saved under backups\n" + "\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    temporary.replace(properties)
    print(f"Natural world selected: {profile['level_name']} (seed {profile['seed']}). Previous world preserved: {previous}. Profile backup: {backup}")
    return backup


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        apply_profile(args.root.resolve())
    except (RuntimeError, ValueError, OSError) as exc:
        print("World switch stopped: " + str(exc))
        raise SystemExit(1)
