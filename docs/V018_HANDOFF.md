# v0.18 focused goal and perception repair

The latest server log ends with SyntheticMind disconnected for duplicate login (09:20:36 Oct 10), followed by clean world saving. No evidence from that tail of the prior invalid-attack kick. Do not launch two bot sessions with the same identity.

Goal handling now recognizes plural resource words, quantities in simple collect/gather/obtain/get requests, sums inventory stacks, and uses the console/dashboard brain.goal consistently. Set the goal to auto to generate a simple available-resource goal; an operator goal supersedes it. Dashboard shows source, counts and completion. This is affordance-based deterministic goal generation, not open-ended LLM planning.

Structured vision keeps nearest visible examples of different block types ahead of repeated surfaces. Visibility and cone limits remain; block IDs and eye-relative coordinates are included. Working perception includes entities and favors less-repeated types. This is not pixel vision or a ground-up vision redesign.

Module input receipt is steady blue; pulses require state changes or outputs. Broad subscribers may still legitimately activate together. No invented staggered activity.

Validation: 128 existing Python test executions passed, 3 new goal tests passed, 31 JavaScript tests passed. No live Minecraft/overnight soak; log collection task completion has not been demonstrated.

Deferred: specialized model routing, full sensory and attention redesign, richer goal arbitration, learned navigation/skill composition, duplicate-session lock, and database retention. Persistent database is about 20 GB; history has not been deleted. Weekly allowance began this pass at only 22% remaining, below the requested reserve.
