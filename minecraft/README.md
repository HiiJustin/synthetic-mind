# Current Minecraft entry point: v0.10

Read `../START_V010.md` for the natural world, cognitive council and new operator controls. `../V010_HANDOFF.md` describes the current architecture. This older v0.03 guide remains useful for vanilla1.21.4 installation and sensor definitions; its model-per-action description is superseded by independent motor skills and competing motivations.

# Historical Minecraft cognition: v0.03

Use **vanilla Minecraft Java Edition 1.21.4**. No Forge, Fabric, client mod, shader, or resource pack is required. The Mineflayer bot joins as another player; all libraries are on the project side.

## Launch

1. In Minecraft Launcher, select Installations > New installation > `release 1.21.4`. Launch that installation.
2. Double-click `MINECRAFT_START.cmd` in the project folder, or run `./MINECRAFT_START.cmd` from PowerShell in that folder.
   It checks the already-installed local Ollama model first. See `../START_V03.md` if updating an existing copy.
3. On first run, the launcher prepares dependencies and the official server. Read the Minecraft EULA linked in the terminal. Type `I AGREE` only if you accept it. The prepared files leave `eula=false`; Codex has not accepted it for you.
4. Wait for the terminal to show that the bot connected. In Minecraft choose Multiplayer > Direct Connection > `127.0.0.1:25565`.
5. You should see another player named `SyntheticMind`. Its initial greeting appears in chat. Move near it and type `!mind hello` in game chat.

If you use the prepared workspace copy, dependencies and the verified server jar are already downloaded. The portable source ZIP installs/downloads these on first launch. Python 3.12+, Node 22+, a package manager (npm or the Codex-bundled pnpm), and Java 21+ are required. This PC has Python 3.12.10, Node 24.19.0, Java 23.0.2, and bundled pnpm.

The launcher starts a separate flat test world. It does not edit Minecraft installations, mod directories, launcher profiles, or existing worlds. Closing this launcher stops the server it started; your test world and cognitive database persist. If a server is already using port 25565, the launcher uses that endpoint and does not stop that existing server. Use a separate local offline-mode test server with matching version if you choose that path.

## Operator controls

The project terminal displays `minecraft>`. Commands here are operator tools, not in-game slash commands:

```text
/status
/sense
/brain
/goal Investigate nearby landmarks and remember what changes
/think
/say Hello from my virtual body
/move forward
/turn 90
/move forward
/auto on
/auto off
/stop
/events
/memory stone
/quit
```

`/move` supports forward, back, left, right, and jump. Each movement is limited to a short 350 ms pulse. `/look YAW [PITCH]` takes absolute degrees; `/turn` is a relative yaw change. Movement begins disabled and requires explicit commands or `/auto on`.

Automatic mode uses separate planning and cognitive critic roles through one shared model. Structured perception/recall agents contribute context, prediction compares actual motor outcomes, and consolidation records episodes. The executive can perform one short forward pulse, a90-degree turn, or eat available food per deliberation. Calls are sparse (default at most4/minute; two calls per plan/review), so this is deliberately slower than the earlier reactive walker. No mining, crafting, combat or navigation skill is implemented. Set `enabled=false` in `config/brain.json` to retain the old deterministic mode.

`/say` passes through the critic and executive before chat transport. Plain console input requests a local-model reply. Nearby game chat is perceived, but the bot replies only to `!mind ...`; its own chat is ignored to prevent feedback loops. Slash-command speech is rejected. `/goal` persists a goal without enabling motion; `/auto on` enables motor proposals. `/stop` invalidates in-flight motor plans. Use `/brain` for last plan/review and errors.

## What its senses contain

- **Vision:** nearby block surfaces and entities, filtered by an eight-block range, 100-degree field of view, and solid-block occlusion; up to 96 block observations and 16 entities. This is structured game perception, not pixels.
- **Hearing:** nearby sound packets abstracted into a sound ID/name, bearing, elevation, coarse range band, and volume. This is localized game-event perception, not waveform recognition. Nearby chat is a communication channel.
- **Touch/proximity:** collision flags, grounded state, and a short-range clearance/support/hazard probe for movement. The probe is an explicit extra sensory abstraction, not unrestricted access to a world map.
- **Proprioception:** position, orientation, and velocity.
- **Internal body state:** health, hunger, oxygen, and a bounded inventory description.

Position and inventory are game-native abstractions. Transparent/partial-block occlusion and chunk-boundary behavior are approximate. Sensor packet compatibility and behavior in the actual game still need the first live check. The bot does not receive unrestricted chunk metadata, global entity lists, or evaluator truth through its cognitive interfaces.

## Persistence and reliability

The bot uses the same `data/state.db` as the tiny prototype and retains identity, goals, and history. Minecraft observations, map, drives, workspace, and motor samples use separate namespaces. The tiny simulator remains a regression fixture. Actions are logged before transport and sent at most once. Prior-session commands are abandoned, and reconnect does not resume automatic movement.

Parent heartbeats maintain a 2.5-second motor lease. Commands stop on lease expiry, EOF, disconnect, or shutdown. Disconnects do not auto-reconnect or resume actions. Restart the launcher after fixing a connection problem. Death disables the session; respawn behavior is not implemented yet.

Full observations and causal traces are stored locally. Large dictionary state writes are traced as deltas rather than repeatedly copying the whole remembered map. The map retains up to 10,000 blocks; history/log retention is not yet implemented. Keep initial experiments short while measuring storage and scheduler latency.

## Troubleshooting

- **Connection refused:** let the local server finish loading; the combined launcher waits for its ready message. Check `minecraft/server/launcher-server.log`.
- **Wrong version / outdated client:** select Java `release 1.21.4` for this experiment, not Latest Release.
- **Authentication / secure profile error:** the prepared server is bound to loopback with offline mode and secure-profile enforcement disabled. A normal public/online server is not this connector's target.
- **No reply to game chat:** stand within16blocks and use `!mind hello`. Check `/brain` for inference errors or a budget wait. First cold model load measured about52seconds; a warm two-role cycle measured about2.6seconds in a synthetic fixture. Replies queue when the budget is exhausted.
- **Movement paused:** try `/auto off`, then a single `/move forward`; inspect `/status` for motor/connection errors.
- **Missing Node/npm:** use a standard Node 22+ install, or the available Codex bundled runtime. `MINECRAFT_SETUP.cmd` checks preparation without starting the game server.

## Verification

47 Python tests and seven Node tests passed on this PC, including concurrency, model critic veto, stop invalidation and persisted budgets. Real Ollama passed both a planner/critic smoke test and the event-driven pipeline using synthetic sensors and captured transport; see `../LOCAL_MODEL_TEST.json`. The official server jar was checksum-verified. The user reported the previous connector working in-game; v0.03 still needs the live-game acceptance check. This workspace's server EULA remains unaccepted.

Primary references: [Mineflayer tested versions](https://github.com/PrismarineJS/mineflayer/blob/master/lib/version.js), [Mineflayer API](https://github.com/PrismarineJS/mineflayer/blob/master/docs/api.md), [Minecraft EULA](https://www.minecraft.net/eula).
