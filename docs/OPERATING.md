# Controls, observation and streaming

[Back to project](../README.md) · [Installation and LLM setup](SETUP.md)

## Launchers

| File | Purpose |
| --- | --- |
| `MINECRAFT_SETUP.cmd` | Prepare dependencies and server |
| `MINECRAFT_START.cmd` | Start with autonomy initially off |
| `STREAM_START.cmd` | Start with autonomy on in a visible console |
| `MIND_DASHBOARD.cmd` | Start the read-only local dashboard |

Start at normal game speed. Fast mode is not a repair for slow reasoning or navigation loops.

## Clickable controls

Open `http://127.0.0.1:8765/` after starting the launcher and dashboard. Start/Pause, goal editing, assisted-routine and learning toggles are available without typing console commands. Start resumes an already running bot; it does not launch a stopped server. Commands expire after 15 seconds and report when the bot applies them. The schematic flashes on real module-event changes, not inferred consciousness.

## Project console

These commands belong in the project console, **not Minecraft chat**.

| Command | Use |
| --- | --- |
| `/help` | Available controls |
| `/status`, `/sense` | Runtime and current observations |
| `/goal TEXT` | Persistent goal; does not itself enable movement |
| `/auto on`, `/auto off` | Enable or disable autonomy |
| `/stop` | Stop current motor activity |
| `/brain`, `/mind` | Model status and competing motivations |
| `/muscles`, `/learning`, `/skills` | Measured effects and outcomes |
| `/learn on`, `/development on` | Enable experiments / require learned muscle effects |
| `/assist on`, `/assist off` | Select or disable supplied survival routines |
| `/survival`, `/inventory` | Survival state / inventory inspection |
| `/events`, `/inspect EVENT_ID` | Trace events and their causes |
| `/quit` | Stop and persist; launcher stops its owned server |

A goal such as “gather wood and build a shelter” is an intention, not a capability guarantee.

## Minecraft chat and camera

`!mind hello` is nearby speech. `!start`, `!stop`, `!shutdown` and camera controls are operator commands.

The prototype recognizes `firmlygrasp1t` as operator. For another account, review the checks in `minecraft/bridge.js`, `src/synthetic_mind/minecraft.py`, and `tools/observer_camera.py`. Camera code also contains exact player-name spelling.

`!camera` enables the spectator camera; `!camera 8` sets its distance; `!camera off` disables it. Camera control requires the launcher-owned server console. It checks intervening geometry, but teleport-based movement can still jitter or clip. Its extra world information is operator telemetry, separate from agent perception.

## Dashboard and OBS overlay

Run `MIND_DASHBOARD.cmd` and open `http://127.0.0.1:8765/`.

In OBS add a **Browser Source** using `http://127.0.0.1:8765/overlay`, set dimensions to **1920 × 1080**, and place it above your Minecraft capture source. Prefer the served URL over a local HTML file, which can encounter browser-fetch restrictions. These loopback addresses assume OBS and the dashboard run on the same PC.

The overlay reflects existing state. It is not a Twitch chat connector. The proposed Twitch `!mind` integration is not implemented; Minecraft chat is a separate channel.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Model missing | `ollama list`; pull the exact configured tag |
| Ollama connection error | Start Ollama; run `python tools/brain_check.py` |
| Input budget exceeded | Check `/brain`, use current code and bounded settings; do not simply raise all limits |
| Connected but stationary | Regular startup is paused; use `/auto on`, then inspect health, sleep and `/mind` |
| Moving in circles | Known unresolved destination-selection problem; responsive software can still make poor decisions |
| Busy indefinitely | v0.14.1 fixes one cause; preserve events and status before diagnosing another |
| No hostile mobs | Check `spawn-monsters=true`, Normal difficulty and `doMobSpawning=true` |
| Cannot connect | Java Edition 1.21.4, correct local port, and server startup log |
| Camera does not attach | Correct operator name, reconnect, `!camera 8`, launcher-owned server |
| Overlay disconnected | Dashboard must remain running; use the served `/overlay` URL |
| Game performance drops | Stop extra test servers; reduce concurrent GPU workloads |

Server output is in `minecraft/server/launcher-server.log`; persistent events are in `data/state.db`. Record version, goal, position over time and latest action errors. Avoid sharing complete databases publicly: they can contain chat and goals.

## Stop and resume

Use `/quit` or authorized `!shutdown`; wait for the owned server to save. Close the dashboard separately. Restarting preserves the world and memory. Stop the bot before unloading its Ollama model to free GPU memory for another game.
