"""Outcome-based forward and inverse models for opaque body channels.

The learner never imports the adapter wiring. Predictions precede activation;
actual observations, uncertainty and context determine later channel selection.
"""
from __future__ import annotations

import math
import time
from .schemas import CognitiveEvent

EFFECTS = ('forward', 'sideways', 'vertical', 'yaw', 'pitch', 'slot_delta', 'food', 'inventory_delta', 'block_changed', 'health')


def context_key(sensed):
    return '|'.join((str(sensed.get('heldItem') or 'empty'), str((sensed.get('crosshair') or {}).get('name') or 'none'),
                     'hungry' if sensed.get('hunger', 0) > 0 else 'full', str(sensed.get('worldTickRate', 20))))


def observed_context(before):
    return '|'.join((str(before.get('held') or 'empty'), str((before.get('target') or {}).get('name') or 'none'),
                     'hungry' if before.get('food', 20) < 20 else 'full', str(before.get('worldTickRate', 20))))


def model_for(record, context=None, duration=350):
    return record.get('contexts', {}).get(f'{context}@{duration}', {}) if context else record


def lower_bound(model, effect, sign=1):
    count = model.get('samples', 0)
    if count < 2:
        return 0.0
    variance = model.get('m2', {}).get(effect, 0) / max(1, count - 1)
    return sign * model.get('mean', {}).get(effect, 0) - 1.5 * math.sqrt(variance / count)


def choose_channel(state, effect, sign=1, minimum=0.1, contextual=False):
    context = context_key(state.get('minecraft.sensed', {}))
    best = None
    for channel, record in state.get('sensorimotor.models', {}).items():
        if record.get('retry_after', 0) > time.time():
            continue
        options = [(350, record)] if not contextual else [(duration, model_for(record, context, duration)) for duration in (350, 1800, 3500)]
        for duration, model in options:
            value = lower_bound(model, effect, sign)
            if effect == 'forward' and (abs(model.get('mean', {}).get('sideways', 0)) > 0.2 or abs(model.get('mean', {}).get('vertical', 0)) > 0.2):
                continue
            if value > minimum and (best is None or value > best[0]):
                best = (value, channel, duration)
    return {'action': 'muscle', 'channel': best[1], 'duration_ms': best[2], 'desired_effect': effect, 'desired_sign': sign} if best else None


def learned_forward(state):
    chosen = choose_channel(state, 'forward')
    return chosen['channel'] if chosen else None


def update_estimate(model, effects):
    count = model.get('samples', 0) + 1
    mean, m2 = model.get('mean', {}), model.get('m2', {})
    for name, observed in effects.items():
        delta = observed - mean.get(name, 0)
        mean[name] = mean.get(name, 0) + delta / count
        m2[name] = m2.get(name, 0) + delta * (observed - mean[name])
    return {'samples': count, 'mean': mean, 'm2': m2}


class MotorBabblingAgent:
    name, priority, subscriptions = 'motor_babbling', 25, {'perception.scene'}

    def __init__(self, state): self.state = state

    async def on_event(self, event):
        if not self.state.get('learning.enabled', True):
            return []
        models = self.state.get('sensorimotor.models', {})
        channels = self.state.get('minecraft.connection', {}).get('muscle_channels', [f'm{i}' for i in range(7)])
        context = context_key(self.state.get('minecraft.sensed', {}))
        choices = []
        for channel in channels:
            record = models.get(channel, {})
            if record.get('retry_after', 0) > time.time():
                continue
            samples = record.get('samples', 0)
            if samples < 2:
                choices.append((samples, channel, 350))
                continue
            means = record.get('mean', {})
            # Two samples are not calibration when uncertainty still prevents reuse.
            uncertain = any(abs(means.get(effect,0))>.1 and lower_bound(record,effect,1 if means.get(effect,0)>0 else -1)<=.1 for effect in ('forward','sideways','yaw','pitch'))
            if 2 <= samples < 12 and uncertain:
                choices.append((2 + samples/100,channel,350))
                continue
            # No-effect channels get longer trials in new contexts, not invented meanings.
            contextual_effect = abs(means.get('food', 0)) > 0 or abs(means.get('block_changed', 0)) > 0
            if contextual_effect or max((abs(means.get(k, 0)) for k in EFFECTS), default=0) < 0.08:
                for duration in (1800, 3500):
                    count = model_for(record, context, duration).get('samples', 0)
                    if count < 2:
                        choices.append((3 + count + duration / 10000, channel, duration))
                        break
        if not choices:
            self.state.set('sensorimotor.discovery', 'Basic effects sampled; awaiting a new context or prediction error')
            return []
        _, channel, duration = min(choices)
        self.state.set('sensorimotor.discovery', f'Testing {channel} for {duration} ms in {context}')
        return [CognitiveEvent(self.name, 'motivation.proposal', {'role': 'muscle_discovery', 'skill': 'muscle_experiment',
            'channel': channel, 'duration_ms': duration, 'score': 1.0 if self.state.get('adaptation.progress',{}).get('looping') else 0.86, 'reason': 'Reduce uncertainty about a body channel through observation',
            'sensory_id': event.content['source_id'], 'target': None})]


class MuscleLearningAgent:
    name, priority, subscriptions = 'muscle_learning', 57, {'minecraft.command', 'minecraft.action_result', 'minecraft.command_error'}

    def __init__(self, state): self.state = state

    async def on_event(self, event):
        models = self.state.get('sensorimotor.models', {})
        pending = self.state.get('muscles.pending', {})
        if event.kind == 'minecraft.command':
            action = event.content
            if action.get('action') != 'muscle': return []
            channel, duration = action['channel'], action.get('duration_ms', 350)
            record = models.get(channel, {})
            context = context_key(self.state.get('minecraft.sensed', {}))
            expected = model_for(record, context, duration) or record
            prediction = {'channel': channel, 'duration_ms': duration, 'context': context, 'expected': expected.get('mean', {}),
                          'samples': expected.get('samples', 0), 'command_id': action['id']}
            pending[action['id']] = {**prediction, 'parent': event.id, 'intent': action.get('desired_effect')}
            self.state.set('muscles.pending', dict(list(pending.items())[-16:]))
            return [CognitiveEvent(self.name, 'sensorimotor.prediction', prediction)]
        active = pending.pop(event.content.get('command_id'), None)
        if active is None: return []
        self.state.set('muscles.pending', pending)
        channel = active['channel']
        record = models.get(channel, {'samples': 0, 'failures': 0})
        result = event.content
        before, after = result.get('muscle_before'), result.get('muscle_after')
        valid = bool(before and after and result.get('verified') is True and not result.get('intervention'))
        effects = {}
        if valid:
            dx, dy, dz = [after['position'][k] - before['position'][k] for k in ('x', 'y', 'z')]
            if math.sqrt(dx*dx + dy*dy + dz*dz) > max(3, active['duration_ms']/1000*7):
                valid = False  # Teleport/large external displacement is not a motor lesson.
            else:
                yaw = before['yaw']
                angle = after['yaw'] - yaw
                inventory_count = lambda snap: sum(i['count'] for i in snap.get('inventory', []))
                effects = {'forward': -dx*math.sin(yaw)-dz*math.cos(yaw), 'sideways': -dx*math.cos(yaw)+dz*math.sin(yaw),
                    'vertical': max(dy, result.get('peak_rise', 0)), 'yaw': math.atan2(math.sin(angle), math.cos(angle)),
                    'pitch': after.get('pitch', 0)-before.get('pitch', 0), 'slot_delta': (after['slot']-before['slot']+4)%9-4,
                    'food': after.get('food', 20)-before.get('food', 20), 'health': after.get('health', 20)-before.get('health', 20),
                    'inventory_delta': inventory_count(after)-inventory_count(before),
                    'block_changed': float(bool(before.get('target') and after.get('target') and before['target']['name'] != after['target']['name']))}
                valid = all(math.isfinite(v) for v in effects.values())
        if not valid:
            record['failures'] = record.get('failures', 0)+1
            record['retry_after'] = time.time()+min(60, 5*record['failures'])
            error = None
        else:
            error = max((abs(v-active['expected'].get(k, 0)) for k,v in effects.items()), default=0) if active['samples'] >= 2 else None
            # Repeated contradiction reopens discovery; preserve evidence in immutable episodes.
            surprises = record.get('surprises', 0)+1 if error is not None and error > 0.5 else 0
            if surprises >= 2:
                record.update(samples=0, mean={}, m2={}, contexts={}, surprises=0)
            else: record['surprises'] = surprises
            record.update(update_estimate(record, effects))
            contexts = record.get('contexts', {})
            key = f"{observed_context(before)}@{active['duration_ms']}"
            contexts[key] = update_estimate(contexts.get(key, {}), effects)
            record['contexts'] = dict(list(contexts.items())[-32:])
            record['retry_after'] = 0
            record['evidence_id'] = event.id
        models[channel] = record
        self.state.set('sensorimotor.models', models)
        self.state.set('muscles.learned', {c: {'samples': r.get('samples', 0), 'failures': r.get('failures', 0), **r.get('mean', {}), 'evidence_id': r.get('evidence_id')} for c,r in models.items()})
        lesson = {'channel': channel, 'valid': valid, 'effects': effects, 'prediction_error': error, 'expected': active['expected'],
                  'evidence_id': event.id, 'world_id': self.state.get('minecraft.world_id'), 'intent': active.get('intent')}
        self.state.set('sensorimotor.latest', lesson)
        events = [CognitiveEvent(self.name, 'muscle.learned', lesson, (event.id, active['parent']))]
        if error is not None and error > 0.4 or valid and active['samples'] < 2:
            events.append(CognitiveEvent(self.name, 'attention.candidate', {'key': 'sensorimotor.learning', 'origin_id': event.id,
                'kind': 'muscle.learned', 'payload': lesson, 'features': {'salience': .85,'novelty': .9,'goal_relevance': .8,'urgency': .5,'confidence': 1.0}}))
        return events


class SensorimotorReflectionAgent:
    name, priority, subscriptions = 'sensorimotor_reflection', 70, {'muscle.learned'}

    def __init__(self, state, model):
        self.state, self.model = state, model

    async def on_event(self, event):
        models = self.state.get('sensorimotor.models', {})
        known = {effect: choice['channel'] for effect in ('forward', 'sideways', 'vertical', 'yaw', 'pitch', 'slot_delta')
                 if (choice := choose_channel(self.state, effect))}
        uncertainty = sum(1 for record in models.values() if record.get('samples', 0) < 2)
        summary = {'usable_effects': known, 'uncertain_channels': uncertainty,
                   'valid_samples': sum(r.get('samples', 0) for r in models.values()),
                   'inhibited_or_invalid': sum(r.get('failures', 0) for r in models.values()), 'evidence_id': event.id}
        self.state.set('sensorimotor.reflection', summary)
        model = self.model.load()
        model.capabilities['learned_motor_effects'] = len(known) / 6
        model.limitations['motor_learning'] = 'Empirical, context-dependent effects; unknown channels require trials. No guarantee outside observed conditions.'
        self.model.save(model)
        if event.content.get('prediction_error') is not None and event.content['prediction_error'] > .5:
            return [CognitiveEvent(self.name, 'reflection.sensorimotor', {**summary, 'note': 'Prediction contradicted by a measured consequence; mapping may need revision'})]
        return []
