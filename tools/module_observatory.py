"""Bounded, read-only evidence for the module observatory."""
import json
from collections import Counter

# Descriptions are explanatory metadata. Activation always comes from runtime evidence.
CATALOG = {
 'autonomous_goals':('Self-generated goals','workspace','Chooses an observed resource opportunity when operator goal is auto; holds it for up to two minutes, records outcome, and prefers untried goals.'),
 'selective_attention':('Selective attention','workspace','Ranks observed objects by current goal relevance, distance and novelty; admits eight into working attention.'),
 'subconscious_progress':('Trial review','learning','Tracks failed or ineffective action attempts at specific targets. Temporarily lowers their selection scores so alternatives can compete.'),
 'minecraft_embodiment':('Body interface','senses','Translates Minecraft observations into the common sensory format and sends selected actions back to the body.'),
 'minecraft_body':('Body state','senses','Keeps the latest position, health, inventory and connection state. Remembers only observed blocks.'),
 'minecraft_perception':('Language input','senses','Turns nearby chat and operator messages into attributed language observations.'),
 'sensory_interpretation':('Scene interpretation','senses','Summarizes visible objects and sounds. This is structured game data, not pixel vision.'),
 'input_scene_memory':('Scene changes','senses','Compares observations with remembered features to track change, novelty and uncertainty.'),
 'salience':('Attention signals','senses','Proposes observations that may deserve attention because of urgency, novelty or relevance.'),
 'memory':('Episode storage','memory','Stores experienced events so they can be recalled later.'),
 'episodic_recall':('Recall','memory','Retrieves previous episodes relevant to the current goal and observations.'),
 'episodic_consolidation':('Consolidation','memory','Builds compact summaries from accumulated experience.'),
 'spatial_memory':('Places','memory','Remembers visited areas and landmarks observed from the body.'),
 'semantic_memory':('Observed facts','memory','Records encountered block types and measured action statistics.'),
 'self_model':('Identity','memory','Maintains persistent identity, capability estimates and autobiographical information.'),
 'minecraft_homeostasis':('Body needs','needs','Tracks functional needs from health and hunger. These variables do not establish feelings.'),
 'subconscious_reward':('Outcome value','needs','Evaluates harm, death, need relief and measured outcomes; assigns uncertain temporal credit to recent actions.'),
 'subconscious_goal_memory':('Goal prerequisites','workspace','Connects resource goals to supplied recipe dependencies. This is a limited prerequisite model, not a complete planner.'),
 'subconscious_workspace':('Background integration','workspace','Brings needs, recent feedback, uncertainty and selected observations together for decisions.'),
 'workspace':('Attention workspace','workspace','Maintains a small set of competing important observations for other modules to read.'),
 'planner':('Legacy planner','workspace','Fallback deterministic planner. It yields when the local-model architecture is enabled.'),
 'deliberation_planner':('Deliberation','workspace','Schedules shared-model reasoning. A candidate suggestion is a hypothesis, not a completed action.'),
 'cognitive_critic':('Model review','workspace','Uses the shared model to review a proposed interpretation against sensory evidence.'),
 'subconscious_world_model':('Learned outcomes','learning','Updates persistent contextual values, observed effects and procedural records from results.'),
 'subconscious_prediction':('Expectations','learning','Predicts measurable effects using past trials, then compares the prediction with the actual outcome.'),
 'muscle_learning':('Motor learning','learning','Learns what opaque muscle channels do from measured before-and-after body changes.'),
 'sensorimotor_reflection':('Motor reflection','learning','Summarizes muscle learning and estimates reliability from observed outcomes.'),
 'minecraft_prediction':('Legacy comparison','learning','Records model predictions and available action evidence; it cannot infer unseen task completion.'),
 'action_selection':('Choose an action','action','Compares learned value, uncertainty, needs, goal relevance, repetition and model advice to select an experiment.'),
 'critic':('Body validation','action','Checks command structure, inventory ownership, reach and viewpoint. It does not decide which goal to pursue.'),
 'executive':('Execute decision','action','Turns an approved proposal into an action or speech event.'),
 'minecraft_outbox':('Motor output','action','Packages the approved action for transport to Minecraft.'),
}


def describe(names):
    return {name:{'label':CATALOG.get(name,(name.replace('_',' ').title(),'other','Runtime module; inspect its events for details.'))[0],
                  'group':CATALOG.get(name,('', 'other',''))[1],
                  'description':CATALOG.get(name,('','','Runtime module; inspect its events for details.'))[2]} for name in names}


def activity(db,names):
    """Read at most 96 recent events, then their indexed deliveries. No full-history scan."""
    names=set(names);routes={};latest={};recent=[]
    events=list(db.execute('SELECT id,source,kind,timestamp FROM events ORDER BY seq DESC LIMIT 96'))
    for event_id,source,kind,timestamp in events:
        for module,status in db.execute('SELECT module,status FROM deliveries WHERE event_id=?',(event_id,)):
            if module not in names or status!='done':continue
            if module not in latest:latest[module]={'event_id':event_id,'kind':kind,'timestamp':timestamp,'source':source}
            if source in names and source!=module:
                key=(source,module);edge=routes.setdefault(key,{'source':source,'target':module,'count':0,'timestamp':timestamp,'kind':kind,'event_id':event_id})
                edge['count']+=1
        if source in names:recent.append({'source':source,'kind':kind,'timestamp':timestamp,'event_id':event_id})
    return {'modules':describe(names),'latest':latest,'routes':list(routes.values()),'recent':recent[:24],
            'window_events':len(events),'meaning':'Observed event deliveries; links do not prove decision influence.'}


def explanation(state):
    selection=state.get('embodied.selection') or {};winner=selection.get('winner') or {};candidate=winner.get('candidate') or {};terms=winner.get('terms') or {}
    family=candidate.get('family');parameters=candidate.get('parameters') or {}
    if not family:return {'headline':'Waiting for an action selection','reason':'No selection has been recorded for this architecture yet.'}
    label=family.replace('_',' ')
    if family=='muscle':label=f"Try muscle {parameters.get('channel','?')} for {parameters.get('duration_ms',350)} ms"
    elif parameters.get('item'):label+=f" {parameters['item']}"
    elif parameters.get('block'):label+=f" {parameters['block']}"
    reasons=[]
    if terms.get('goal',0)>0:reasons.append('its expected result supports a resource prerequisite')
    if terms.get('need',0)>0:reasons.append('its expected effect may reduce a current need')
    if terms.get('learned',0)>0:reasons.append('similar trials had positive outcomes')
    if terms.get('uncertainty',0)>.5:reasons.append('there is little evidence about this experiment')
    if terms.get('information',0)>0:reasons.append('it may reveal additional information')
    if terms.get('deliberation',0)>0:reasons.append('the reviewed model suggestion supports it')
    if terms.get('learned',0)<0:reasons.append('past outcomes count against it, but other score terms outweighed them')
    feedback=state.get('embodied.feedback') or {}
    return {'headline':label,'reason':'Selected because '+('; '.join(reasons) or 'it had the highest score among the available candidates')+'.',
        'time':selection.get('time'),'score':winner.get('score'),'terms':terms,'key':winner.get('key'),
        'origin':'Opaque muscle trial' if family=='muscle' else 'Supplied body operation; outcomes are learned',
        'status':'Selection is an intention; execution and success require separate evidence.',
        'feedback':{k:feedback.get(k) for k in ('score','components','kind','attribution','evidence_id')},
        'alternatives':[{'action':v.get('candidate',{}).get('family'),'parameters':v.get('candidate',{}).get('parameters'),'score':v.get('score'),'terms':v.get('terms')} for v in selection.get('alternatives',[])[:4]]}
