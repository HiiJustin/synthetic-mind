"""Read-only, loopback-only observability for the canonical SQLite state."""
from __future__ import annotations
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import time
from pathlib import Path
import sqlite3
import sys
import threading
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from synthetic_mind.operator_control import enqueue
CONTROL_LOCK = threading.Lock()
STREAM_COUNTS = {}

NAMESPACES = ('adaptation.progress','adaptation.feedback','adaptation.actions','operator.last_control','learning.enabled','survival.food_status','survival.enabled', 'survival.status', 'survival.latest', 'survival.dangers', 'survival.deaths', 'survival.build', 'survival.sleeping', 'survival.weapon_trials', 'self_model', 'minecraft.sensed', 'minecraft.connection', 'minecraft.autonomous',
              'minecraft.sensed_at', 'minecraft.world_id', 'cognition.drives', 'council.winner',
              'council.disagreements', 'council.blocked_reason', 'sensorimotor.models', 'sensorimotor.latest',
              'sensorimotor.discovery', 'sensorimotor.developmental', 'learning.last_lesson',
              'brain.last_decision', 'brain.last_review', 'brain.context_size', 'brain.busy', 'brain.last_error', 'brain.goal', 'brain.budget', 'minecraft.workspace')


def read_snapshot(database):
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
        db.execute('PRAGMA query_only=ON')
        placeholders = ','.join('?' for _ in NAMESPACES)
        state = {name: json.loads(value) for name, value in db.execute(f'SELECT namespace,value FROM state WHERE namespace IN ({placeholders})', NAMESPACES)}
        events = [json.loads(row[0]) for row in db.execute("SELECT body FROM events WHERE kind IN ('survival.lesson','minecraft.death','minecraft.respawned','muscle.learned','learning.outcome','runtime.module_error','minecraft.command_error','brain.review','goal.created') ORDER BY seq DESC LIMIT 20")]
        health = {name[7:]: json.loads(value) for name, value in db.execute("SELECT namespace,value FROM state WHERE namespace LIKE 'health.%'")}
        return {'state': state, 'events': events, 'health': health, 'database_bytes': database.stat().st_size}


def read_stream(database):
    snapshot = read_snapshot(database)
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
        boot = db.execute("SELECT timestamp FROM events WHERE kind='runtime.boot' ORDER BY seq DESC LIMIT 1").fetchone()
        cache=STREAM_COUNTS.get(str(database),{})
        if time.time()-cache.get('time',0)>30:
            cache={'time':time.time(),'count':db.execute("SELECT COUNT(*) FROM events WHERE kind='minecraft.action_result'").fetchone()[0]}
            STREAM_COUNTS[str(database)]=cache
        results=cache['count']
    snapshot['session_started'] = boot[0] if boot else None
    snapshot['action_results'] = results
    snapshot['server_time'] = time.time()
    try:
        snapshot['camera'] = json.loads((ROOT/'work/camera-view.json').read_text())
    except (OSError, ValueError):
        snapshot['camera'] = None
    return snapshot


def read_event(database, event_id):
    if len(event_id) > 100: raise ValueError('Invalid event id')
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
        row = db.execute('SELECT body FROM events WHERE id=?', (event_id,)).fetchone()
        if not row: raise KeyError(event_id)
        return {'event': json.loads(row[0]), 'traces': [json.loads(row[0]) for row in db.execute('SELECT body FROM module_traces WHERE event_id=? LIMIT 16', (event_id,))],
                'children': [row[0] for row in db.execute('SELECT child_id FROM edges WHERE parent_id=? LIMIT 40', (event_id,))]}


def serve(database, port):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                expected=f'127.0.0.1:{port}'
                # Same-origin JSON + custom header: external pages cannot submit controls.
                if self.path!='/api/control' or self.headers.get('Host') not in {expected,f'localhost:{port}'}:raise ValueError('Invalid control endpoint')
                origin=self.headers.get('Origin')
                if origin not in {f'http://{expected}',f'http://localhost:{port}'}:raise ValueError('Same-origin controls only')
                if self.headers.get('X-Mind-Control')!='1' or self.headers.get('Content-Type')!='application/json':raise ValueError('Invalid control request')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=2048:raise ValueError('Invalid request size')
                value=json.loads(self.rfile.read(size))
                with CONTROL_LOCK: command_id=enqueue(ROOT/'work/controls',value)
                body=json.dumps({'id':command_id,'status':'queued; waiting for running bot'}).encode();code=202
            except (ValueError,OSError) as exc:
                body=json.dumps({'error':str(exc)}).encode();code=400
            self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

        def do_GET(self):
            route = urlsplit(self.path)
            try:
                if route.path == '/':
                    body, kind = (ROOT/'tools/dashboard.html').read_bytes(), 'text/html; charset=utf-8'
                elif route.path == '/brain-map.js':
                    body, kind = (ROOT/'tools/brain-map.js').read_bytes(), 'application/javascript; charset=utf-8'
                elif route.path in ('/overlay', '/overlay.html'):
                    body, kind = (ROOT/'tools/stream_overlay.html').read_bytes(), 'text/html; charset=utf-8'
                elif route.path == '/api/stream':
                    body, kind = json.dumps(read_stream(database)).encode(), 'application/json'
                elif route.path == '/api/state':
                    body, kind = json.dumps(read_snapshot(database)).encode(), 'application/json'
                elif route.path == '/api/event':
                    body, kind = json.dumps(read_event(database, parse_qs(route.query).get('id', [''])[0])).encode(), 'application/json'
                else:
                    self.send_error(404); return
                self.send_response(200)
            except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
                body, kind = json.dumps({'error': str(exc)}).encode(), 'application/json'
                self.send_response(503)
            if self.headers.get('Origin') == 'null':
                self.send_header('Access-Control-Allow-Origin', 'null')
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_): pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'Synthetic Mind observatory: http://127.0.0.1:{port}\nLocal controls; Ctrl+C closes this window.', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, default=ROOT/'data/state.db')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    serve(args.database, args.port)
