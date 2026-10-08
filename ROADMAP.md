# v0.03 progress

Minecraft connection and shared local inference are now implemented. Separate planner and cognitive critic roles, deterministic sensory interpretation/homeostasis/recall/prediction/consolidation agents, persistent working goals and interrupted-plan invalidation are available. See `NEXT_MODEL_HANDOFF.md` for the current priorities; older planned steps below are historical. Next acceptance check: run the new modular cognition in the user's working Minecraft world and inspect actual sensory/action feedback.

# Next stages after v0.01

Priority update: proceed to the Minecraft adapter next, once the user's edition and version are confirmed. The simulator improvements below are optional follow-up experiments, not prerequisites for connecting Minecraft. The tiny world remains a regression fixture.

## 0.02: strengthen the embodied laboratory

Preserve this release's tests and add controlled worlds with renewable food, changing barriers, localized sound events, limited directional vision, and delayed/noisy sensations. Keep hidden truth available only to evaluators. Add uncertainty to transitions rather than treating the latest outcome as universally correct.

Compare the recurrent workspace with simple feed-forward routing under matched observations and action budgets. Measure task success, exploration efficiency, prediction error, recovery after world changes, memory usefulness, attention saturation, and event cost. Add lesion/recovery trials and causal graphs. Self-monitoring should infer capability problems from consequences; simply telling the self-model which module was disabled does not test that.

Acceptance: identify a previously successful route becoming blocked, remember the change across restart, and find a viable alternative. Quantify the differences with recurrence or memory removed. Do not label a hard-coded repair branch as emergent self-awareness.

## Minecraft adapter

Implement a narrow bridge to a controlled local Minecraft Java server, likely using Mineflayer. Bridge messages carry typed, versioned observations/actions. Sensors filter occlusion, range, and permissible game metadata before forwarding observations. Hearing begins as localized game sound events. The executive's speech maps to Minecraft chat; internal module events never leak into chat. Motor feedback and action cancellation must work independently of slow deliberation.

The user will need to confirm their Minecraft edition/version and handle account login if needed. No credentials belong in prompts or traces. Server setup and version compatibility must be checked before installation. A private experimental world is the initial environment.

Acceptance: the same memory, body-model, and executive interfaces operate against both the tiny simulator and Minecraft. Losing a connection pauses motor commands and records the interruption. Game data unavailable to the configured senses remains unavailable to cognition.

## Shared local inference

Integrate one configured local ModelBackend after deterministic acceptance tests pass. Start with a 4B Q4 GGUF and serialized inference, then compare an 8B model only if the benchmark and behavior justify it. Use typed outputs with validation, bounded retries, cancellation, and durable call reservations before API spending.

Benchmark model/idle VRAM, RAM, prompt processing and generation speed, latency at 128/256/512 output tokens, context sizes 2K/4K/8K/12K, utilization, and interactive queue delay. Record hardware, driver, runtime build, model hash, prompt/template version, and both input/output tokens. The budget must be based on these results.

## Richer perception and cognition

Add rendered first-person vision through a visual backend that fits measured hardware capacity. Actual audio waveform perception is a separate component. Introduce learned salience, more robust memory consolidation, goals grounded in consequences, cross-modal prediction, and reliable self/other attribution incrementally.

Keep hypotheses explicit: recurrent access, multisensory coherence, internal regulation, and adaptive self-modeling are candidate mechanisms. Functional success and descriptions of inner experience do not establish subjective experience. The physical-substrate claims of IIT are not verified by software event loops.

## Usage discipline during development

Use discrete implementation checkpoints. Run relevant tests after meaningful changes, and broaden checks only for new concerns. Keep runtime inference local by default, absent while idle, and prioritized for interaction. Reserve higher development reasoning effort for difficult design or debugging decisions. No autonomous API spending is included in this release.
