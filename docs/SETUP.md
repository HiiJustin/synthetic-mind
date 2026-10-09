# Installation and local LLM setup

[Back to project](../README.md) · [Controls and streaming](OPERATING.md)

## 1. Install the prerequisites

This is a Windows-first prototype. Install:

| Software | Required version / purpose |
| --- | --- |
| [Python](https://www.python.org/downloads/windows/) | 3.12 or newer; cognitive modules |
| [Node.js](https://nodejs.org/en/download) | 22 or newer, including npm; Minecraft bridge |
| [Java](https://adoptium.net/temurin/releases/) | 21 or newer, on PATH; Minecraft server |
| Minecraft Java Edition | **1.21.4**; your observer client |
| [Ollama for Windows](https://ollama.com/download/windows) | Local model inference |

No Forge, Fabric or Minecraft client mods are required. Open a new PowerShell window after installation:

```powershell
python --version
node --version
npm.cmd --version
java -version
ollama --version
```

The development PC has a Ryzen 9 7900X, RTX 4070 Super 12 GB and 32 GB RAM. This is a working reference configuration, not a verified minimum. Minecraft, OBS, inference and other games compete for resources.

## 2. Get the project

On GitHub choose **Code → Download ZIP**, then extract it. Run launchers from the extracted folder, not inside the ZIP. The private repository requires an authorized GitHub account.

Alternatively:

```powershell
git.exe clone https://github.com/HiiJustin/synthetic-mind.git
cd synthetic-mind
```

If Windows asks which application should open `git`, use `git.exe` or `& "C:\Program Files\Git\cmd\git.exe"`. On the development PC, an empty extensionless file in System32 shadowed the real executable.

Run the following project commands from the folder containing `pyproject.toml`.

## 3. Download and check the LLM

Start Ollama and download the exact configured model:

```powershell
ollama pull qwen3-vl:8b-instruct-q4_K_M
ollama list
ollama run qwen3-vl:8b-instruct-q4_K_M "Reply with one short greeting."
```

The model tag is listed in the [official Ollama library](https://ollama.com/library/qwen3-vl:8b-instruct-q4_K_M). Other tags do not satisfy the launcher's exact-name check.

Check the project integration:

```powershell
python tools/brain_check.py
python tools/brain_check.py --smoke
```

The first checks availability. The smoke test exercises planner and critic using synthetic observations; it does not prove live Minecraft behavior. Local requests use `http://127.0.0.1:11434`. This backend requires no paid API key.

If Ollama is not running, start its application. `ollama serve` in a separate terminal is an alternative; do not launch a second server if the application already owns the port. See the [official quickstart](https://github.com/ollama/ollama/blob/main/docs/quickstart.mdx).

## 4. Understand the model settings

Edit `config/brain.json` while the bot is stopped, then restart:

```json
{
  "enabled": true,
  "architecture": "council",
  "model": "qwen3-vl:8b-instruct-q4_K_M",
  "interval_seconds": 30,
  "calls_per_minute": 4,
  "tokens_per_minute": 10000,
  "max_output_tokens": 640,
  "developmental": true
}
```

| Setting | Meaning |
| --- | --- |
| `enabled` | Enable language-model deliberation |
| `architecture` | Use the modular council |
| `model` | Exact locally installed model name |
| `interval_seconds` | Base automatic deliberation interval; slow inference can lengthen it |
| `calls_per_minute` | Shared request budget; planner and critic both consume calls |
| `tokens_per_minute` | Internal token budget |
| `max_output_tokens` | Requested response-length limit |
| `developmental` | Initial developmental mode; an existing persisted state can take precedence |

Use `/development on` or `/development off` to change an existing session explicitly. Changing models requires downloading the new tag and rerunning the smoke test; other models are not guaranteed to produce the required structured output.

Most modules are deterministic. Planner and critic share one model backend. Increasing model frequency does not fix navigation, and the model's vision capability does not mean this project sends it screenshots: its input is compact structured game observations and memory.

Use `ollama ps` to inspect loaded models and processor allocation. For a deterministic baseline, set `enabled` to `false` and restart. To free model memory **after stopping the bot**:

```powershell
ollama stop qwen3-vl:8b-instruct-q4_K_M
```

## 5. Prepare and launch Minecraft

Double-click `MINECRAFT_SETUP.cmd`. It installs bridge dependencies and downloads the official server with checksum verification into `minecraft/server/`.

Then run `MINECRAFT_START.cmd`. Review the linked Minecraft EULA and type `I AGREE` only if you accept it. Wait for the server and bot connection messages.

A fresh installation creates a natural world with seed `47849012232314`, plus a small scripted test camp with landmarks and obstacles. The camp is supplied scaffolding. Existing worlds and learning data are not included in Git.

**Fresh-install caveat:** setup currently writes `spawn-monsters=false`, while the survival launcher enables Normal difficulty and `doMobSpawning`. If you want hostile mobs, stop the server, set `spawn-monsters=true` in `minecraft/server/server.properties`, and restart. The original installed world already has this setting.

In Minecraft Launcher create an installation for **release 1.21.4**. Use **Multiplayer → Direct Connection → `127.0.0.1:25565`**. The bot is `SyntheticMind`.

In the **project console**, enable autonomy:

```text
/goal Explore cautiously, observe outcomes, and remember what happens.
/auto on
```

The regular launcher starts paused. `STREAM_START.cmd` starts with autonomy enabled. Do not launch duplicate bots or servers.

## 6. Preserve the experiment

`data/state.db` contains persistent cognitive state. `minecraft/server/` contains the world. Stop the bot and server before making a simple filesystem backup, and preserve both directories. Source code alone does not transfer learned history.

The server uses offline authentication and binds to loopback. Do not port-forward it or expose it publicly. The launcher can reuse a server already on port 25565; avoid doing this with an unrelated valuable world.
