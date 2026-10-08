"""Explicit optional runtime tempo; inference remains single-flight and bounded."""
from copy import deepcopy
import os

PROFILES = {
    'normal': {'world_tps': 20, 'sense_ms': 1000, 'motor_interval': 1.5, 'cycle_interval': .5,
               'model_interval': 30, 'quiet_interval': 120, 'calls_per_minute': 4, 'tokens_per_minute': 10000},
    'fast': {'world_tps': 40, 'sense_ms': 500, 'motor_interval': .75, 'cycle_interval': .25,
             'model_interval': 15, 'quiet_interval': 60, 'calls_per_minute': 8, 'tokens_per_minute': 18000},
}


def profile(name=None):
    name = name or os.environ.get('SYNTHETIC_MIND_TEMPO', 'normal')
    if name not in PROFILES:
        raise ValueError('Tempo must be normal or fast')
    return {'name': name, **deepcopy(PROFILES[name])}
