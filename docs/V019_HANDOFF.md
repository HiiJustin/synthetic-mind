# v0.19: attention, feedback, directed actions

Adds selective_attention (eight ranked observed objects), subconscious_progress (target-specific failures/no-effects lower future scores, fading over two minutes), and autonomous_goals (holds an available-resource goal for up to two minutes, logs completion/timeout, operator override wins).

Body now proposes brief directed steps toward visible resource blocks and dropped items. These are supplied motor primitives, not learned navigation or a hidden map. Opaque muscle trials remain available. Digging a changed block counts as a measured effect even before pickup. Inventory stacks are summed. The protocol attack hotfix remains in place.

Planner and critic model roles are configurable under role_models in config/brain.json. Calls remain sequential. qwen3:1.7b was downloaded and tested as critic; it incorrectly approved two unsupported completion claims, so it is NOT enabled. Defaults retain the existing 8B backend. Evaluated using Ollama /api/chat think:false; see https://ollama.com/blog/thinking .

Launcher holds local port 25566 for its lifetime, preventing a duplicate launcher from kicking the existing identity. Directly launching the Python CLI bypasses this launcher lease.

Rolling-history trace updates use lossless remove/append operations instead of copying whole histories. Eligibility retains resource/vital snapshots rather than every observed object. Existing 20 GB history is preserved; no promise of fixed storage cap.

Dashboard shows attention, trial review, goal history and model roles. Module activity remains actual telemetry, not staged neural animation. This is a modular software experiment, not evidence of consciousness or full reinforcement learning.

Automated checks: 138 Python test executions and 33 JavaScript tests passed. A short installed-world validation is in progress; final results will be appended. No claim yet of completing the three-log goal or unattended reliability.
