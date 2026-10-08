# Current handoff — v0.14.1

Keep the original experiment: separate cognitive modules, recurrent feedback, persistent memory, and learned opaque motor effects. Do not replace it with one LLM controlling Minecraft or present supplied routines as discoveries.

## Fixed failures

1. At an oak-plank corner, mineflayer-pathfinder repeatedly planned diagonal paths its motion simulation could not execute. `survival-body.js` now uses cardinal movement edges and rejects navigation after four seconds without 0.6 blocks of progress. An outer 20-second routine deadline remains.
2. Recovery could outbid muscle discovery while requiring an unavailable forward model. `ExplorationRecoveryAgent` now yields when that measured effect is unavailable.
3. An immediate action-result cognition cycle could reserve motor_busy and then have its identical proposal suppressed by per-root event deduplication. `MinecraftSession.ingest` no longer schedules a successor immediately from action_result. Fresh senses and the independent motor clock schedule subsequent actions. A regression reproduces the old failure and tests 50 repeated completion/cycle pairs.

## Still unresolved

Live observation after these changes showed about 56 blocks of sampled travel in five minutes, confined to a roughly 6-by-8-block area at elevation 73. The controller was responsive and not busy-locked; the model had no error. This is repetitive exploration and unreachable-destination selection, not the earlier frozen controller. Investigate progress beyond local oscillation, reachable destination selection, alternatives to repeatedly facing ledges, and starvation of discovery. Preserve memory and avoid teleportation masquerading as learned recovery.

Previous short curated tests missed extended-run failures. Reproduce in a copy of the user's actual terrain and learned state, then observe sustained autonomous behavior. Do not run an extra server while the user is gaming without considering resource use. Current stream installation remains separate from this repository snapshot.

House completion is experimental. Damage attribution can be unknown; do not invent causes or damage amounts. The local model is shared across logical modules. No claim of consciousness, weight training, or general reinforcement learning.
