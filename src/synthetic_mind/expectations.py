"""Environment-independent expectations, captured before action outcomes arrive."""
import math
from .schemas import CognitiveEvent


class OutcomePrediction:
    name,priority,subscriptions='subconscious_prediction',28,{'embodied.executed','embodied.result','embodied.terminal'}
    def __init__(self,state):self.state=state
    async def on_event(self,event):
        s=self.state;c=event.content;pending=s.get('embodied.prediction_pending',{})
        if event.kind=='embodied.terminal':
            s.set('embodied.prediction_pending',{});return []
        if event.kind=='embodied.executed':
            learned=s.get('embodied.models',{}).get(c['key'],{});means=dict(learned.get('mean_effects',{}));counts=learned.get('effect_counts',{})
            prediction={'command_id':c['id'],'key':c['key'],'expected':means,'samples':learned.get('samples',0),
                'standard_errors':{k:math.sqrt(max(0,learned.get('effect_m2',{}).get(k,0))/max(1,counts.get(k,0)-1)/max(1,counts.get(k,0))) if counts.get(k,0)>=2 else None for k in means},
                'origin':'Measured contextual effects' if means else 'No measured expectation yet', 'evidence_id':event.id}
            pending[c['id']]=prediction;s.set('embodied.prediction_pending',dict(list(pending.items())[-16:]));s.set('embodied.prediction',prediction)
            return [CognitiveEvent(self.name,'subconscious.expected',prediction)]
        prediction=pending.pop(c.get('id'),None)
        if prediction is None:return []
        s.set('embodied.prediction_pending',pending)
        measured=c.get('effects',{}).get('measured',{})
        errors={k:v-prediction['expected'][k] for k,v in measured.items() if k in prediction['expected']}
        normalized=sum(abs(v)/(1+abs(prediction['expected'][k])) for k,v in errors.items())/max(1,len(errors))
        result={'command_id':c['id'],'key':prediction['key'],'expected':prediction['expected'],'observed':measured,'errors':errors,
            'comparable':bool(errors) and not c.get('failed',False),'normalized_error':normalized if errors else None,
            'prediction_evidence':prediction['evidence_id'],'outcome_evidence':event.id,
            'meaning':'Prediction error measures mismatch; it is not proof of causal responsibility.'}
        if result['comparable']:
            quality=s.get('embodied.prediction_quality',{});entry=quality.get(prediction['key'],{'comparisons':0,'error':0})
            entry['comparisons']+=1;entry['error']+=.25*(normalized-entry['error']);entry['evidence_id']=event.id
            quality[prediction['key']]=entry;s.set('embodied.prediction_quality',dict(list(quality.items())[-2048:]))
        s.set('embodied.prediction_error',result)
        return [CognitiveEvent(self.name,'subconscious.compared',result)]
