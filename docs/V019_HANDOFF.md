# v0.19: attention, feedback, directed actions

Adds selective_attention (eight ranked observed objects), subconscious_progress (target-specific failures/no-effects lower future scores, fading over two minutes), and autonomous_goals (holds an available-resource goal for up to two minutes, logs completion/timeout, operator override wins).

Body now proposes brief directed steps toward visible resource blocks and dropped items. These are supplied motor primitives, not learned navigation or a hidden map. Opaque muscle trials remain available. Digging a changed block counts as a measured effect even before pickup. Inventory stacks are summed. The protocol attack hotfix remains in place.

Planner and critic model roles are configurable under role_models in config/brain.json. Calls remain sequential. qwen3:1.7b was downloaded and tested as critic; it incorrectly approved two unsupported completion claims, so it is NOT enabled. Defaults retain the existing 8B backend. Evaluated using Ollama /api/chat think:false; see https://ollama.com/blog/thinking .

Launcher holds local port 25566 for its lifetime, preventing a duplicate launcher from kicking the existing identity. Directly launching the Python CLI bypasses this launcher lease.

Rolling-history trace updates use lossless remove/append operations instead of copying whole histories. Eligibility retains resource/vital snapshots rather than every observed object. Existing 20 GB history is preserved; no promise of fixed storage cap.

Dashboard shows attention, trial review, goal history and model roles. Module activity remains actual telemetry, not staged neural animation. This is a modular software experiment, not evidence of consciousness or full reinforcement learning.

Validation: full Python suite plus new tests covers resource-goal closed-loop completion in a simulated body, selective attention, failure-driven reselection, inventory stacks, auto-goal persistence, launcher lease, and lossless compact traces. JavaScript tests cover real body helpers and visibility. The simulated three-log test passes; it is NOT live success.

Two two-minute installed-world trials started in an enclosed dirt/stone area at Y=62. No disconnect; clean server save. Bot did not escape or collect oak logs. Persistent field evidence remains in SQLite. Do not advertise overnight autonomy or completed live acceptance.

Further fixes after the first trial: short move+jump combinations, up to three candidate blocks per material, explicit dropped-item pickup affordances, horizontal displacement feedback, and a penalty for repeated changes without useful world/need/resource/novelty effects (slot cycling is no longer automatically treated as useful). These remain utility heuristics, not trained neural control. Repeated identical attention content does not emit another workspace packet.

Small critic retested after stronger factual-review wording; it still approved unsupported claims. Download remains available, but role_models defaults stay on the existing 8B model. No new small model is active.

Remaining: robust escape and longer action-sequence learning, live three-log success, validated specialized model assignments, greater field of view/partial-surface perception, bounded archival storage. Preserve this negative live result for the next reviewer.
