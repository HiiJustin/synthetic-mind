"""Small local GUI command mailbox; effects still run through the live session."""
import json
import time
from uuid import uuid4
from .schemas import CognitiveEvent


def validate_control(value):
    if not isinstance(value,dict):raise ValueError('Expected a command object')
    action=value.get('action')
    if action not in {'start','pause','eat','goal','assist','learning'}:raise ValueError('Unsupported control')
    clean={'action':action}
    if action=='goal':
        goal=value.get('value')
        if not isinstance(goal,str) or not 1<=len(goal.strip())<=500 or any(ord(c)<32 for c in goal):raise ValueError('Goal must be 1–500 printable characters')
        clean['value']=goal.strip()
    if action in {'assist','learning'}:
        if type(value.get('value')) is not bool:raise ValueError('Expected true or false')
        clean['value']=value['value']
    return clean


def enqueue(directory,value):
    value=validate_control(value);directory.mkdir(parents=True,exist_ok=True)
    if len(list(directory.glob('*.json')))>=16:raise ValueError('Control queue full; check the bot is running')
    item={**value,'id':str(uuid4()),'expires':time.time()+15}
    temp=directory/(item['id']+'.tmp');temp.write_text(json.dumps(item),encoding='utf-8')
    temp.replace(directory/(item['id']+'.json'));return item['id']


async def drain_controls(session,directory):
    if not directory.exists():return
    for path in sorted(directory.glob('*.json'),key=lambda p:p.stat().st_mtime)[:8]:
        claimed=path.with_suffix('.processing')
        try:path.rename(claimed)
        except FileNotFoundError:continue
        item={};status='applied'
        try:
            item=json.loads(claimed.read_text(encoding='utf-8'));command=validate_control(item)
            if item.get('expires',0)<time.time():raise ValueError('Control expired; submit again')
            action=command['action'];engine=session.engine;s=engine.state
            if action=='eat':
                if s.get('minecraft.motor_busy'):raise ValueError('Body busy; try again after the current action')
                await session.propose({'action':'eat'})
            else:
                async with engine.lock:
                    if action in {'start','pause'}:s.set('minecraft.autonomous',action=='start')
                    elif action=='goal':s.set('brain.goal',command['value'])
                    else:s.set('survival.enabled' if action=='assist' else 'learning.enabled',command['value'])
                    s.set('brain.control_epoch',s.get('brain.control_epoch',0)+1)
                    s.set('council.bids',{});s.set('council.winner',None);s.set('council.next_motor',0)
                    engine.bus.publish(CognitiveEvent('operator_gui','operator.control',command));await engine.bus.drain()
                if action in {'pause','assist'}:await session.propose({'action':'stop'})
        except Exception as exc:status=str(exc)
        finally:
            session.engine.state.set('operator.last_control',{'id':item.get('id'),'action':item.get('action'),'status':status,'time':time.time()})
            claimed.unlink(missing_ok=True)
