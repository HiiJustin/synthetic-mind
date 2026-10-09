"""Local operator channel; deliberately outside cognitive events and model tools."""
import json
import os
import secrets
import threading
import time
import uuid
from pathlib import Path


def enqueue(command):
    token = os.environ.get('SYNTHETIC_SERVER_TOKEN')
    folder = os.environ.get('SYNTHETIC_SERVER_MAILBOX')
    if not token or not folder:
        raise ValueError('Server console unavailable: start through MINECRAFT_START or STREAM_START.')
    command = command.strip().lstrip('/')
    if not command or len(command) > 2000 or any(ord(c) < 32 for c in command):
        raise ValueError('Enter one server command, without line breaks.')
    path = Path(folder) / (uuid.uuid4().hex + '.json')
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps({'token': token, 'command': command, 'time': time.time()}), encoding='utf-8')
    temp.replace(path)


class ServerControl:
    def __init__(self, process, folder, lock):
        self.process, self.folder, self.lock = process, Path(folder), lock
        self.folder.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_hex(24)
        self.end = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    @property
    def env(self):
        return {'SYNTHETIC_SERVER_TOKEN': self.token, 'SYNTHETIC_SERVER_MAILBOX': str(self.folder)}

    def run(self):
        while not self.end.wait(.15):
            for path in sorted(self.folder.glob('*.json'))[:16]:
                try:
                    value = json.loads(path.read_text(encoding='utf-8'))
                    path.unlink()
                    command = value.get('command', '')
                    if value.get('token') != self.token or not 0 <= time.time()-value.get('time', 0) < 15:
                        continue
                    if not isinstance(command, str) or not command or len(command)>2000 or any(ord(c)<32 for c in command):
                        continue
                    with self.lock:
                        self.process.stdin.write(command+'\n')
                        self.process.stdin.flush()
                    print('[server] Sent: '+command, flush=True)
                except (OSError, ValueError, TypeError):
                    continue

    def start(self): self.thread.start()
    def close(self):
        self.end.set()
        self.thread.join(timeout=2)
