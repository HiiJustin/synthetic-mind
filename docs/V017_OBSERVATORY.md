# v0.17: module observatory and measured expectations

Individual runtime modules now have plain-English descriptions, hover/focus explanations, clickable telemetry, and connections based on completed event deliveries. Green means output, gold state changes, blue input. Offline state does not simulate activity. Narrow windows stack regions for readability. Raw data remains available in expandable sections, alongside readable action reasoning and alternatives.

The activity endpoint reads at most 96 recent events and their indexed deliveries. Links demonstrate delivery, not proven influence. The brain-shaped layout is a software schematic, not a biological scan.

A new subconscious_prediction module records expectations before actions, compares matching results, and tracks prediction quality. Unknown effects remain unknown. Inaccurate positive expectations reduce positive learned-value contributions in selection; negative values are not discounted. Effect statistics use per-dimension counts and variance; resource consumption is now measured too.

Validation: 128 Python test executions passed (legacy imported fixture classes include repeats), JavaScript syntax checked, browser selection and readable module descriptions verified. Tests cover pre-action capture, unknown expectations, terminal cleanup, prediction quality changing choices, and completed-delivery links. No extra Minecraft server or overnight test was run.

Dashboard: http://127.0.0.1:8765/ ; overlay: http://127.0.0.1:8765/overlay . Refresh the browser/OBS source. The prediction module appears after the next mind startup. Use STREAM_START.cmd for autonomy or MINECRAFT_START.cmd to begin paused.

Remaining limitations: temporal credit is associative; prerequisite planning remains basic; some Minecraft interfaces and multi-step learned skill composition remain unfinished. The existing database is roughly 10.6 GiB. This release bounds observatory reads without deleting historical evidence. No claim of consciousness or improved long-horizon performance.
