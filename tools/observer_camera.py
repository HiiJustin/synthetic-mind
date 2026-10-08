"""Operator-only trailing camera, controlled through the owned server console."""
import json
import time
from pathlib import Path
import re
import threading

PLAYER = 'Firmlygrasp1t'
TARGET = 'SyntheticMind'
TAG = 'sm_stream_camera'
MARKER = 'sm_stream_return'


def restore_commands():
    player = f'@a[name={PLAYER},tag={TAG}]'
    commands = [f'execute as {player} at @e[type=minecraft:marker,tag={MARKER},limit=1] run tp @s ~ ~ ~',
        *[f'gamemode {mode} @a[name={PLAYER},tag={TAG},scores={{sm_camera={n}}}]'
          for n, mode in enumerate(('survival', 'creative', 'adventure', 'spectator'))],
        f'kill @e[type=minecraft:marker,tag={MARKER}]', f'tag {player} remove {TAG}']
    return [f'execute if entity {player} run '+command for command in commands]


def follow_commands(distance=8, position=None):
    new = f'@a[name={PLAYER},tag=!{TAG}]'
    teleport = (f'tp @a[name={PLAYER},tag={TAG}] {position["x"]:.3f} {position["y"]:.3f} {position["z"]:.3f} facing entity {TARGET} eyes' if position else f'execute at {TARGET} rotated ~ 0 run tp @a[name={PLAYER},tag={TAG}] ^ ^3 ^-{distance} facing entity {TARGET} eyes')
    return [*[f'execute as @a[name={PLAYER},tag=!{TAG},gamemode={mode}] run scoreboard players set @s sm_camera {n}'
               for n, mode in enumerate(('survival', 'creative', 'adventure', 'spectator'))],
        f'execute as {new} at @s run summon minecraft:marker ~ ~ ~ {{Tags:["{MARKER}"]}}',
        f'tag {new} add {TAG}',
        f'gamemode spectator @a[name={PLAYER},tag={TAG},gamemode=!spectator]',
        teleport]


class ObserverCamera:
    def __init__(self, process, log):
        self.process, self.log = process, log
        self.camera_dir = Path(__file__).resolve().parents[1] / "work"
        self.camera_dir.mkdir(exist_ok=True)
        self.end = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def send(self, commands):
        self.process.stdin.write('\n'.join(commands) + '\n')
        self.process.stdin.flush()

    def start(self):
        self.thread.start()

    def close(self):
        self.end.set()
        self.thread.join(timeout=3)

    def run(self):
        enabled, distance = False, 8
        try:
            saved=json.loads((self.camera_dir/'camera-settings.json').read_text())
            enabled=bool(saved.get('enabled'));distance=max(4,min(20,int(saved.get('distance',8))))
        except (OSError,ValueError,TypeError): pass
        last_settings = None
        last_setup = 0
        try:
            self.send(['scoreboard objectives add sm_camera dummy'])
            with self.log.open(encoding='utf-8', errors='replace') as stream:
                stream.seek(0, 2)
                while not self.end.wait(.05):
                    for line in stream.readlines():
                        match = re.search(r'<'+PLAYER+r'> (![^\r\n]+)$', line, re.IGNORECASE)
                        if not match:
                            continue
                        command = match.group(1).strip().lower()
                        if command in ('!camera off', '!camera stop', '!stop'):
                            enabled = False
                            self.send(restore_commands())
                        elif re.fullmatch(r'!camera(?: on)?(?: (\d+))?', command):
                            digits = re.search(r'\d+$', command)
                            distance = max(4, min(20, int(digits.group()) if digits else 8))
                            enabled = True
                    settings = (enabled, distance)
                    if settings != last_settings:
                        (self.camera_dir / "camera-settings.json").write_text(json.dumps({"enabled": enabled, "distance": distance}))
                        last_settings = settings
                    if not enabled and time.monotonic()-last_setup > 1:
                        self.send(restore_commands())
                        last_setup = time.monotonic()
                    if enabled:
                        try:
                            view = json.loads((self.camera_dir / "camera-view.json").read_text())
                            pos = view.get("position")
                            if view.get("clear") and time.time()*1000-view["timestamp"] < 1500 and isinstance(pos, dict) and all(isinstance(pos.get(k), (float,int)) and abs(pos[k]) < 30000000 for k in ("x","y","z")):
                                commands = follow_commands(distance, pos)
                                if time.monotonic()-last_setup < 1:
                                    commands = commands[-1:]
                                else:
                                    last_setup = time.monotonic()
                                self.send(['execute if entity '+TARGET+' run '+cmd for cmd in commands])
                        except (OSError, ValueError, KeyError):
                            pass
        except (OSError, ValueError):
            pass
        finally:
            try:
                self.send(restore_commands())
            except (OSError, ValueError):
                pass
