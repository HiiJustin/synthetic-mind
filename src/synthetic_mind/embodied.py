"""Environment-independent background cognition and action selection.

Inputs are normalized observations, action candidates and taught transformations.
No Minecraft names, key mappings, entity policies or material whitelists live here.
This is online contextual outcome learning, not neural weight training.
"""
import hashlib
import json
import math
import re
import time
from .schemas import CognitiveEvent


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:20]


def inventory(observation): return observation.get('resources',{})


def context(observation):
    return fingerprint({k:observation.get(k) for k in ('held','target_type','contact','nearby_types')})


def action_key(candidate, observation):
    # Locations are not action identities: learned effects generalize across instances.
    return fingerprint([candidate['family'],candidate.get('parameters',{}),context(observation)])


class Module:
    def __init__(self,state): self.state=state


class PerceptualMemory(Module):
    name,priority,subscriptions='input_scene_memory',20,{'embodied.observation'}
    async def on_event(self,event):
        s=self.state;o=event.content;now=time.time();previous=s.get('embodied.observation',{})
        old=s.get('embodied.seen',{});features=o.get('features',[])
        novelty=sum(1/(1+old.get(f,0)) for f in features)/max(1,len(features))
        for f in features:old[f]=old.get(f,0)+1
        s.set('embodied.seen',dict(list(old.items())[-4096:]))
        s.set('embodied.observation',{**o,'event_id':event.id,'time':now})
        s.set('embodied.perception',{'novelty':novelty,'changed':o.get('signature')!=previous.get('signature'),
            'objects':o.get('objects',[])[:24],'uncertainty':o.get('uncertainty',[]),'evidence_id':event.id})
        return [CognitiveEvent(self.name,'subconscious.perceived',{'novelty':novelty,'signature':o.get('signature')})]


class OutcomeEvaluator(Module):
    """Homeostatic value and delayed credit. An aversive value is not subjective pain."""
    name,priority,subscriptions='subconscious_reward',25,{'embodied.executed','embodied.result','embodied.terminal','embodied.observation'}
    async def on_event(self,event):
        s=self.state;c=event.content;now=time.time();history=s.get('embodied.eligibility',[])
        if event.kind=='embodied.executed':
            history=[h for h in history if now-h['time']<30]
            history.append({**c,'time':now,'before':{k:s.get('embodied.observation',{}).get(k,{}) for k in ('resources','vitals')}})
            s.set('embodied.eligibility',history[-16:]);return []
        if event.kind=='embodied.observation':
            old=s.get('embodied.vitals')
            vitals=c.get('vitals',{});s.set('embodied.vitals',vitals)
            if old is None:return []
            # Respawn/healing never reward the death that preceded them.
            loss=max(0,old.get('integrity',1)-vitals.get('integrity',1))
            relief=max(0,vitals.get('energy',1)-old.get('energy',1))
            novelty=s.get('embodied.perception',{}).get('novelty',0)
            if loss==0 and relief==0 and novelty<.5:return []
            parts={'harm':-8*loss,'need_relief':2*relief,'novel_observation':.2*novelty if novelty>=.5 else 0}
            entries=[h for h in history if now-h['time']<8]
            observed={'vitals':vitals};kind='body_change'
        elif event.kind=='embodied.terminal':
            parts={'terminal':-12.0};entries=[h for h in history if now-h['time']<20]
            observed=c;kind='terminal'
            s.set('embodied.deaths',s.get('embodied.deaths',0)+1)
            s.set('embodied.vitals',None)
        else:
            entries=[h for h in history if h['id']==c.get('id')]
            if not entries:return []
            # Transport success alone is not reward. Compare measured resources and world effects.
            before=entries[0]['before'];after=c.get('after',{})
            gained=sum(max(0,n-inventory(before).get(k,0)) for k,n in inventory(after).items())
            parts={'failure':-.3 if c.get('failed') else 0,
                   'resource_gain':min(.6,gained*.1),
                   'information':min(.3,c.get('information',0))}
            observed=c;kind='outcome'
        total=sum(parts.values());weights=[math.exp(-(now-h['time'])/8) for h in entries];denom=sum(weights) or 1
        credits=[{'key':h['key'],'family':h['family'],'weight':w/denom,'command_id':h['id']} for h,w in zip(entries,weights)]
        episode={'score':total,'components':parts,'credits':credits,'kind':kind,'observation':observed,
                 'evidence_id':event.id,'time':now,'attribution':'temporal association, not proven causation'}
        s.set('embodied.feedback',episode)
        episodes=s.get('embodied.episodes',[]);episodes.append(episode);s.set('embodied.episodes',episodes[-128:])
        if kind=='terminal':s.set('embodied.eligibility',[])
        return [CognitiveEvent(self.name,'subconscious.evaluated',episode)]


class WorldModel(Module):
    name,priority,subscriptions='subconscious_world_model',35,{'subconscious.evaluated','embodied.result'}
    async def on_event(self,event):
        s=self.state;c=event.content;models=s.get('embodied.models',{})
        if event.kind=='subconscious.evaluated':
            for credit in c['credits']:
                key=credit['key'];r=models.get(key,{'samples':0,'value':0,'failures':0,'effects':{}})
                # Keep large adverse outcomes influential; only observed later outcomes can revise them.
                r['value']+=.25*credit['weight']*(c['score']-r['value'])
                r['evidence']=event.id;r['family']=credit['family'];models[key]=r
        else:
            record=next((h for h in s.get('embodied.eligibility',[]) if h['id']==c.get('id')),None)
            if not record:return []
            key=record['key'];r=models.get(key,{'samples':0,'value':0,'failures':0,'effects':{}})
            r['samples']+=1;r['failures']+=int(c.get('failed',False));r['last_trial']=time.time()
            r['no_effect']=r.get('no_effect',0)+1 if not c.get('changed') else 0
            means=r.get('mean_effects',{})
            counts=r.get('effect_counts',{});m2=r.get('effect_m2',{})
            for k,v in c.get('effects',{}).get('measured',{}).items():
                counts[k]=counts.get(k,0)+1
                delta=v-means.get(k,0);means[k]=means.get(k,0)+delta/counts[k]
                m2[k]=m2.get(k,0)+delta*(v-means[k])
            r['effect_counts']=counts;r['effect_m2']=m2
            r['mean_effects']=means
            r['effects']=c.get('effects',{});r['evidence']=event.id;r['family']=record['family'];models[key]=r
            # Procedural records contain actual parameters and measured outcomes, not generated claims.
            skills=s.get('embodied.skills',{});skills[key]={'candidate':record.get('candidate'), 'samples':r['samples'],
                'failures':r['failures'],'last_effects':r['effects'],'evidence_id':event.id,'origin':'observed'}
            s.set('embodied.skills',dict(list(skills.items())[-512:]))
        s.set('embodied.models',dict(list(models.items())[-2048:]));return []


class GoalMemory(Module):
    """Backward resource relevance over taught transformations; never claims execution."""
    name,priority,subscriptions='subconscious_goal_memory',30,{'embodied.observation','goal.requested','brain.decision'}
    async def on_event(self,event):
        s=self.state
        if event.kind=='goal.requested':s.set('embodied.goal',event.content.get('description',''))
        if event.kind=='brain.decision':
            if event.content.get('approved') and event.content.get('control_epoch')==s.get('brain.control_epoch'):
                s.set('embodied.hypothesis',{'text':event.content.get('focus',''),'key':event.content.get('candidate_key'),'confidence':event.content.get('confidence',0),'time':time.time(),'origin':'model hypothesis'})
            return []
        o=s.get('embodied.observation',{});known=s.get('embodied.knowledge',{})
        # The operator control room and console share brain.goal as the authority.
        override=s.get('brain.goal',s.get('embodied.goal','')).strip()
        autonomous=not override or override.lower()=='auto'
        goal=override
        resources=set(known)|set(o.get('resources',{}))
        for recipe in known.values():resources.update(recipe.get('inputs',{}))
        for candidate in s.get('embodied.candidates',[]):resources.update(candidate.get('prior',{}).get('resources',{}))
        if autonomous:
            options=sorted(r for r in resources if o.get('resources',{}).get(r,0)==0 and any(c.get('prior',{}).get('resources',{}).get(r,0)>0 for c in s.get('embodied.candidates',[])))
            goal=s.get('embodied.autonomous_goal',{}).get('text') or (('Collect 1 '+options[0].replace('_',' ')) if options else 'Explore and measure an unfamiliar action')
        words=set(re.findall(r'[a-z0-9]+',goal.lower()))
        words.update(w[:-1] for w in list(words) if w.endswith('s'))
        amount=re.search(r'\b(?:collect|gather|obtain|get)\s+(\d+)\b',goal.lower())
        count=max(1,int(amount.group(1))) if amount else 1
        targets={r:count for r in resources if set(r.split('_'))<=words}
        desired={r:1.0 for r,n in targets.items() if o.get('resources',{}).get(r,0)<n}
        needs=dict(desired);frontier=list(desired.items());visited=set()
        for _ in range(6):
            following=[]
            for item,value in frontier:
                if item in visited:continue
                visited.add(item)
                for ingredient in known.get(item,{}).get('inputs',{}):
                    if o.get('resources',{}).get(ingredient,0)>0:continue
                    needs[ingredient]=max(needs.get(ingredient,0),value*.8);following.append((ingredient,value*.8))
            frontier=following
        s.set('embodied.goal_state',{'text':goal,'desired':desired,'targets':targets,
            'progress':{r:min(n,o.get('resources',{}).get(r,0)) for r,n in targets.items()},
            'complete':bool(targets) and not desired,'mode':'autonomous' if autonomous else 'operator',
            'resource_relevance':needs,'origin':'available affordances' if autonomous else 'operator goal + taught dependencies'})
        return []


class WorkspaceIntegrator(Module):
    name,priority,subscriptions='subconscious_workspace',45,{'attention.selected','subconscious.evaluated','subconscious.progress_reviewed'}
    async def on_event(self,event):
        s=self.state;o=s.get('embodied.observation',{});p=s.get('embodied.perception',{})
        summary={'needs':o.get('needs',{}),'novelty':p.get('novelty',0),'uncertainty':p.get('uncertainty',[]),
            'goal':s.get('embodied.goal_state',{}),'recent_feedback':{k:s.get('embodied.feedback',{}).get(k) for k in ('score','components','kind')},
            'working_objects':s.get('embodied.attention',{}).get('objects',[])[:8],'evidence_id':event.id}
        s.set('embodied.workspace',summary)
        return [CognitiveEvent(self.name,'workspace.embodied',summary)]


class ActionSelector(Module):
    """Contextual utility + information seeking. No environment-specific policies."""
    name,priority,subscriptions='action_selection',50,{'embodied.cycle'}
    async def on_event(self,event):
        s=self.state;o=s.get('embodied.observation',{});now=time.time()
        if not event.content.get('enabled') or now-o.get('time',0)>3 or now<s.get('embodied.next_action',0):return []
        candidates=s.get('embodied.candidates',[]);models=s.get('embodied.models',{});recent=s.get('embodied.recent_choices',[])
        relevant=s.get('embodied.goal_state',{}).get('resource_relevance',{});ranked=[]
        for candidate in candidates:
            key=action_key(candidate,o);r=models.get(key,{});n=r.get('samples',0)
            # Repetition is about the same experiment in the same context, not motion alone.
            repeats=recent.count(key);no_effect=r.get('no_effect',0)
            uncertainty=1/math.sqrt(1+n) if s.get('learning.enabled',True) else 0
            prior=candidate.get('prior',{});need=sum(o.get('needs',{}).get(k,0)*v for k,v in prior.get('relief',{}).items())
            goal=sum(relevant.get(k,0)*max(0,v) for k,v in prior.get('resources',{}).items())
            effects=r.get('mean_effects',{})
            goal+=sum(relevant.get(k[9:],0)*max(0,v) for k,v in effects.items() if k.startswith('resource:'))
            need+=4*o.get('needs',{}).get('energy',0)*effects.get('food',0)
            gain=candidate.get('information',0)/(1+repeats) if s.get('learning.enabled',True) else 0
            reliability=1/(1+s.get('embodied.prediction_quality',{}).get(key,{}).get('error',0))
            calibrated_value=min(0,r.get('value',0))+max(0,r.get('value',0))*reliability
            score=calibrated_value+.7*uncertainty+need+goal+gain-.22*repeats-.12*min(8,no_effect)-.3*r.get('failures',0)/(1+n)
            hypothesis=s.get('embodied.hypothesis',{})
            advice=.5*hypothesis.get('confidence',0) if hypothesis.get('key')==key and now-hypothesis.get('time',0)<30 else 0
            from .attention import ProgressReview
            trial=s.get('embodied.trial_review',{}).get(ProgressReview.site(candidate),{})
            trial_penalty=trial.get('penalty',0)*max(0,1-(now-trial.get('time',0))/120)
            mobility=min(1,s.get('embodied.stalled_trials',0)/10)*min(1,effects.get('horizontal_distance',0))
            score+=advice-trial_penalty+mobility
            score-=candidate.get('cost',.05)
            ranked.append({'candidate':candidate,'key':key,'score':score,'terms':{'mobility':mobility,'trial_penalty':-trial_penalty,'learned':calibrated_value,'prediction_reliability':reliability,'uncertainty':uncertainty,'need':need,'goal':goal,'information':gain,'repeats':repeats,'deliberation':advice,'uncertainty_bonus':.7*uncertainty,'repetition_penalty':-.22*repeats,'no_effect_penalty':-.12*min(8,no_effect),'failure_penalty':-.3*r.get('failures',0)/(1+n),'action_cost':-candidate.get('cost',.05)}})
        if not ranked:return []
        ranked.sort(key=lambda r:(r['score'],r['key']),reverse=True);winner=ranked[0]
        s.set('embodied.selection',{'winner':winner,'alternatives':ranked[1:5],'time':now})
        s.set('embodied.recent_choices',(recent+[winner['key']])[-24:]);s.set('embodied.next_action',now+1.0)
        return [CognitiveEvent(self.name,'embodied.selected',winner)]


def modules(state):
    from .expectations import OutcomePrediction
    from .attention import SelectiveAttention, ProgressReview, AutonomousGoals
    return [PerceptualMemory(state),OutcomeEvaluator(state),OutcomePrediction(state),WorldModel(state),AutonomousGoals(state),GoalMemory(state),SelectiveAttention(state),ProgressReview(state),WorkspaceIntegrator(state),ActionSelector(state)]
