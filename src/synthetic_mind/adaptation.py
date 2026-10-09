"""Measured progress and bounded, interpretable outcome feedback (not weight training)."""
import math
import time
from .schemas import CognitiveEvent


def cell(position):
    return f"{math.floor(position['x']/3)},{math.floor(position['z']/3)}"


class AdaptiveFeedbackAgent:
    name, priority = 'adaptive_feedback', 18
    subscriptions = {'minecraft.senses', 'minecraft.command', 'minecraft.action_result', 'minecraft.command_error'}

    def __init__(self, state): self.state = state

    async def on_event(self, event):
        s, c, now = self.state, event.content, time.time()
        if event.kind == 'minecraft.senses':
            p = c['position']; history = s.get('adaptation.window', [])
            if history and now-history[-1]['t'] < 2: return []
            history = [v for v in history if now-v['t'] < 120]
            history.append({'t':now,'x':p['x'],'z':p['z'],'cell':cell(p)})
            s.set('adaptation.window',history[-61:])
            visits = s.get('adaptation.visits', {})
            visits[cell(p)] = min(10000, visits.get(cell(p),0)+1)
            s.set('adaptation.visits',dict(list(visits.items())[-2048:]))
            span = now-history[0]['t']
            extent = math.hypot(max(v['x'] for v in history)-min(v['x'] for v in history), max(v['z'] for v in history)-min(v['z'] for v in history))
            looping = span >= 60 and extent < 12 and now-s.get('adaptation.productive_at',0)>60
            active = bool(s.get('minecraft.autonomous')) and not c.get('sleeping')
            progress = {'looping':looping and active,'window_seconds':round(span),'extent':round(extent,1),
                        'unique_cells':len({v['cell'] for v in history}),
                        'status':'Local repetition: change strategy' if looping and active else 'Observing progress' if active else 'Paused / sleeping'}
            s.set('adaptation.progress',progress)
            return []
        pending = s.get('adaptation.pending', {})
        if event.kind == 'minecraft.command':
            if c.get('action') in {'say','stop'}: return []
            obs=s.get('minecraft.sensed',{})
            pending[c['id']]={'command':c,'food':obs.get('food',20),'health':obs.get('health',20)}
            s.set('adaptation.pending',dict(list(pending.items())[-8:])); return []
        prior = pending.pop(c.get('command_id'),None)
        if not prior:return []
        s.set('adaptation.pending',pending)
        action=prior['command']['action']; parts={}
        success=event.kind=='minecraft.action_result' and c.get('verified',True) and not c.get('intervention')
        if not success:parts['failed_attempt']=-.5
        # Reward only measured changes; acknowledgements and speech are not progress.
        after=c.get('after') or c.get('muscle_after') or {}
        if success and after.get('food',prior['food'])>prior['food']:
            parts['need_reduction']=min(1,(after['food']-prior['food'])/4)
        if success and action in {'harvest','craft','place_at','sleep'} and not c.get('already_present'):
            parts['verified_task_step']=.5
        if success and action=='navigate' and after.get('position'):
            key=cell(after['position']); awarded=s.get('adaptation.rewarded_cells',[])
            if key not in awarded:
                parts['new_area']=.25; s.set('adaptation.rewarded_cells',(awarded+[key])[-4096:])
            elif s.get('adaptation.progress',{}).get('looping'):parts['repeated_area']=-.25
        if parts.get('need_reduction',0)>0 or parts.get('verified_task_step',0)>0:s.set('adaptation.productive_at',now)
        score=sum(parts.values()); stats=s.get('adaptation.actions',{})
        entry=stats.get(action,{'trials':0,'mean_feedback':0})
        entry['trials']+=1;entry['mean_feedback']+=(score-entry['mean_feedback'])/entry['trials'];stats[action]=entry;s.set('adaptation.actions',stats)
        result={'action':action,'score':round(score,3),'components':parts,'evidence_id':event.id,'time':now,
                'meaning':'Engineered feedback, not emotion or model training'}
        s.set('adaptation.feedback',result)
        return [CognitiveEvent(self.name,'adaptation.feedback',result,(event.id,))]
