# Synthetic Mind

Experimental modular embodied cognition in Minecraft Java 1.21.4. Current version: 0.14.1.

Separate perception, memory, motivation, workspace, self-model, critic, executive, and learning modules share a local model backend. Opaque muscle channels are sampled and their observed effects retained. Supplied navigation and survival routines are scaffolding, distinct from learned effects. This project does not establish consciousness or general autonomous competence.

## Setup

Requires Windows, Python 3.12+, Node.js 22+, Java 21+ and Ollama for local model deliberation. The configured model is `qwen3-vl:8b-instruct-q4_K_M`.

Run `MINECRAFT_SETUP.cmd` and follow its prompts, including reviewing Minecraft's EULA. Run `STREAM_START.cmd` to start the server and bot with autonomy enabled, or `MINECRAFT_START.cmd` for the regular console. Run `MIND_DASHBOARD.cmd` for the dashboard at http://127.0.0.1:8765/; `/overlay` is the stream overlay.

The existing prototype recognizes `firmlygrasp1t` as its operator; change the operator checks in `src/synthetic_mind/minecraft.py`, `minecraft/bridge.js`, and `tools/observer_camera.py` if using another account. Operator chat: `!start`, `!stop`, `!shutdown`, `!camera`. Review the architecture and source before exposing the offline-authentication server to a network.

This repository excludes Minecraft server binaries/world saves, installed dependencies, runtime logs, learning databases, and machine-specific deployment reports. They remain in the original installation.

## Current limitations

The bot can still loop within a small area and repeatedly select unreachable destinations. It is NOT validated for overnight unattended operation or reliable house completion. See `HANDOFF.md` for the exact known failure and repairs.

## Tests

```powershell
$env:PYTHONPATH = "src"
python -B -m unittest discover -s tests -q
cd minecraft
npm install
npm test
```

Latest validation: 93 Python tests passed on v0.14.1; 25 Node tests passed on the unchanged v0.14 body code. No 12-hour validation claim.

Third-party dependency notices are in `THIRD_PARTY_NOTICES.txt`. No project-wide open-source license has been selected.
