"""Bounded attention and trial review; no environment names or scripted task plans."""
import time
from .schemas import CognitiveEvent
from .embodied import fingerprint

class SelectiveAttention:
    name,priority,subscriptions='selective_attention',42,{'subconscious.perceived'}
    def __init__(self,state): self.state=state
    async def on_event(self,event):
        s=self.state;o=s.get('embodied.observation',{});relevant=s.get('embodied.goal_state',{}).get('resource_relevance',{})
        old=s.get('embodied.attention',{});previous={x.get('id') for x in old.get('objects',[])}
        ranked=[]
        for obj in o.get('objects',[]):
            goal=max([relevant.get(obj['type'],0),*[relevant.get(r,0) for r in obj.get('resources',[])]])
            score=3*goal+1/(1+(obj.get('distance') or 0))+.15*(obj.get('id') not in previous)
            ranked.append({**obj,'attention_score':score,'goal_relevance':goal})
        ranked.sort(key=lambda x:x['attention_score'],reverse=True)
        value={'objects':ranked[:8],'observed_count':len(ranked),'reason':'goal relevance, distance and novelty','evidence_id':event.id}
        s.set('embodied.attention',value)
        return [CognitiveEvent(self.name,'attention.selected',value)]

class ProgressReview:
    name,priority,subscriptions='subconscious_progress',38,{'embodied.result'}
    def __init__(self,state): self.state=state
    @staticmethod
    def site(candidate):
        return fingerprint([candidate.get('family'),candidate.get('command',{}).get('target'),candidate.get('parameters')])
    async def on_event(self,event):
        s=self.state;c=event.content
        record=next((r for r in s.get('embodied.eligibility',[]) if r['id']==c.get('id')),None)
        if not record:return []
        candidate=record.get('candidate') or {};key=self.site(candidate);trials=s.get('embodied.trial_review',{})
        old=trials.get(key,{});fail=c.get('failed') or not c.get('changed')
        streak=old.get('streak',0)+1 if fail else 0
        value={'streak':streak,'penalty':min(4,streak*.8),'time':time.time(),'reason':'failed or no measured change' if fail else 'measured change','evidence_id':event.id}
        trials[key]=value;s.set('embodied.trial_review',dict(list(trials.items())[-256:]))
        s.set('embodied.progress_review',{**value,'family':candidate.get('family'),'target':candidate.get('command',{}).get('target')})
        return [CognitiveEvent(self.name,'subconscious.progress_reviewed',value)]


class AutonomousGoals:
    name,priority,subscriptions='autonomous_goals',29,{'embodied.observation'}
    def __init__(self,state): self.state=state
    async def on_event(self,event):
        s=self.state;override=s.get('brain.goal','').strip()
        if override and override.lower()!='auto':return []
        now=time.time();o=event.content;current=s.get('embodied.autonomous_goal',{})
        item=current.get('resource');complete=bool(item) and o.get('resources',{}).get(item,0)>=current.get('target',1)
        if current and not complete and now-current.get('started',0)<120:return []
        history=s.get('embodied.autonomous_history',[])
        if current:history.append({**current,'result':'inventory target reached' if complete else 'time budget exhausted','ended':now})
        seen={h.get('resource') for h in history[-8:]}
        options={r for c in s.get('embodied.candidates',[]) for r,v in c.get('prior',{}).get('resources',{}).items() if v>0 and not o.get('resources',{}).get(r,0)}
        ranked=sorted(options,key=lambda r:(r in seen,r))
        resource=ranked[0] if ranked else None
        value={'resource':resource,'target':1,'text':'Collect 1 '+resource.replace('_',' ') if resource else 'Explore and measure an unfamiliar action',
            'started':now,'reason':'visible obtainable resource with preference for untried goals' if resource else 'no unmet resource opportunity currently observed'}
        s.set('embodied.autonomous_history',history[-32:]);s.set('embodied.autonomous_goal',value)
        return [CognitiveEvent(self.name,'goal.autonomous',value)]
