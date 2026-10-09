"""Per-player operator cameras. No camera or server truth enters agent perception."""
import json
import time
from pathlib import Path
import re
import threading

PLAYER = 'Firmlygrasp1t'
TARGET = 'SyntheticMind'
TAG = 'sm_stream_camera'
MODES = ('follow', 'side', 'front', 'overhead', 'first')


def checked(player):
    if not re.fullmatch(r'[A-Za-z0-9_]{1,16}', player): raise ValueError('Invalid player name')
    return player


def marker(player): return 'sm_return_'+checked(player).lower()


def restore_commands(player=PLAYER):
    player=checked(player); selector=f'@a[name={player},tag={TAG}]'; tag=marker(player)
    return [f'execute as {selector} run spectate',
        f'execute as {selector} at @e[type=minecraft:marker,tag={tag},limit=1] run tp @s ~ ~ ~',
        *[f'gamemode {mode} @a[name={player},tag={TAG},scores={{sm_camera={n}}}]' for n,mode in enumerate(('survival','creative','adventure','spectator'))],
        f'execute if entity {selector} run kill @e[type=minecraft:marker,tag={tag}]',
        f'tag {selector} remove {TAG}']


def follow_commands(distance=8, position=None, player=PLAYER, mode='follow'):
    player=checked(player); new=f'@a[name={player},tag=!{TAG}]'; selected=f'@a[name={player},tag={TAG}]'; tag=marker(player)
    setup=[*[f'execute as @a[name={player},tag=!{TAG},gamemode={m}] run scoreboard players set @s sm_camera {n}' for n,m in enumerate(('survival','creative','adventure','spectator'))],
        f'execute as {new} at @s run summon minecraft:marker ~ ~ ~ {{Tags:["{tag}"]}}',
        f'tag {new} add {TAG}', f'gamemode spectator {selected}']
    if mode=='first': return setup+[f'execute as {selected} run spectate {TARGET} @s']
    setup.append(f'execute as {selected} run spectate')
    if position:
        setup.append(f'tp {selected} {position["x"]:.3f} {position["y"]:.3f} {position["z"]:.3f} facing entity {TARGET} eyes')
    return setup


class ObserverCamera:
    def __init__(self, process, log, lock=None):
        self.process,self.log=process,log; self.lock=lock or threading.Lock()
        self.camera_dir=Path(__file__).resolve().parents[1]/'work';self.camera_dir.mkdir(exist_ok=True)
        self.end=threading.Event();self.thread=threading.Thread(target=self.run,daemon=True)
    def send(self, commands):
        with self.lock:
            self.process.stdin.write('\n'.join(commands)+'\n');self.process.stdin.flush()
    def start(self):self.thread.start()
    def close(self):self.end.set();self.thread.join(timeout=3)
    def run(self):
        players={}; setups={}; last_settings=None
        try:
            saved=json.loads((self.camera_dir/'camera-settings.json').read_text())
            players=saved.get('players',{})
            if not players and saved.get('enabled'): players={PLAYER:{'mode':'follow','distance':saved.get('distance',8)}}
            players={checked(k):{'mode':v.get('mode','follow') if v.get('mode') in MODES else 'follow','distance':max(4,min(20,int(v.get('distance',8))))} for k,v in players.items()}
        except (OSError,ValueError,TypeError):players={}
        try:
            self.send(['scoreboard objectives add sm_camera dummy'])
            with self.log.open(encoding='utf-8',errors='replace') as stream:
                stream.seek(0,2)
                while not self.end.wait(.1):
                    for line in stream.readlines():
                        match=re.search(r'\[Server thread/INFO\]: <([A-Za-z0-9_]{1,16})> (!camera[^\r\n]*)$',line)
                        if not match:continue
                        player,command=match.groups();arg=command.lower().split()[1:]
                        if arg and arg[0] in ('off','stop'):
                            players.pop(player,None);self.send(restore_commands(player));setups.pop(player,None);continue
                        old=players.get(player,{'mode':'follow','distance':8})
                        mode=old['mode'];distance=old['distance']
                        if arg and arg[0]=='next':mode=MODES[(MODES.index(mode)+1)%len(MODES)]
                        elif arg and arg[0] in MODES:mode=arg[0]
                        elif arg and arg[0] not in ('on',) and not arg[0].isdigit():continue
                        if arg and arg[-1].isdigit():distance=max(4,min(20,int(arg[-1])))
                        players[player]={'mode':mode,'distance':distance};setups.pop(player,None)
                        self.send([f'tellraw {player} '+json.dumps({'text':f'Camera: {mode}. !camera next / !camera off','color':'aqua'})])
                    settings=json.dumps({'enabled':bool(players),'players':players})
                    if settings!=last_settings:
                        tmp=self.camera_dir/'camera-settings.tmp';tmp.write_text(settings);tmp.replace(self.camera_dir/'camera-settings.json');last_settings=settings
                    try:view=json.loads((self.camera_dir/'camera-view.json').read_text())
                    except (OSError,ValueError):view={}
                    for player,options in list(players.items()):
                        mode=options['mode'];v=view.get('players',{}).get(player,{})
                        pos=v.get('position');fresh=0<=time.time()*1000-v.get('timestamp',0)<1500
                        valid=v.get('clear') and fresh and isinstance(pos,dict) and all(type(pos.get(k)) in (float,int) and abs(pos[k])<30000000 for k in ('x','y','z'))
                        if mode!='first' and not valid:continue
                        full=time.monotonic()-setups.get(player,0)>1
                        commands=follow_commands(options['distance'],pos,player,mode)
                        if not full:commands=commands[-1:]
                        else:setups[player]=time.monotonic()
                        self.send([f'execute if entity {TARGET} run '+c for c in commands])
        except (OSError,ValueError):pass
        finally:
            for player in players:
                try:self.send(restore_commands(player))
                except (OSError,ValueError):pass
