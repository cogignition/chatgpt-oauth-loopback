# ChatGPT OAuth loopback

A Grok plugin that lets **Grok orchestrate ChatGPT OAuth children**.

The parent stays Grok. The child is `gpt-5.6-luna`, authenticated as a ChatGPT subscriber, not as an OpenAI platform customer. There is no `OPENAI_API_KEY`. There is no call to `api.openai.com`.

If ChatGPT OAuth is missing, this project **tells you to log in**. It will not steal the MCP stdio pipe to run `codex login`. You run that in a terminal: `just login`.

## Why this exists

Most “multi-model Grok” setups drop a platform key in `config.toml` and point at `api.openai.com`. That is a second bill and a second identity.

This loopback reuses `codex login` (ChatGPT). Grok’s custom-model client talks HTTP to `127.0.0.1:8743`. A tiny MCP server is the session channel so that HTTP process is not a command sitting in your TUI.

```
  Grok 4.6  ──spawn_subagent──►  child (catalog slug openai-codex)
       │                                │
       │ MCP chatgpt-oauth              │ POST /v1/responses
       │ (health, login)                ▼
       │                         127.0.0.1:8743  loopback.py
       │                                │
       │                                ▼
       │                         chatgpt.com Codex backend
       │                         model = gpt-5.6-luna
       ▼                         auth  = ~/.codex/auth.json
  /mcps  Local: chatgpt-oauth
```

`just` is the catalog. Do not invent a second execution surface.

## What it is not

| This | Not this |
|---|---|
| ChatGPT OAuth (`codex login` → ChatGPT) | Platform API key / `auth_mode=apikey` |
| `127.0.0.1:8743` | `api.openai.com` |
| Upstream **gpt-5.6-luna** | Calling the child “Codex” |
| Plugin MCP + detached HTTP | A Grok TUI background command |
| One listener per host | One port per Grok session |

## Prerequisites

- Grok Build TUI
- Codex CLI (`codex` on `PATH`)
- Python 3 (stdlib only; no npm)
- `just` (optional but this is how you drive it)

## First run

```bash
git clone https://github.com/cogignition/chatgpt-oauth-loopback.git
cd chatgpt-oauth-loopback
just                 # catalog
just login           # Codex CLI; choose ChatGPT, not API key
just check           # must print "chatgpt"; exit 1 if refused
just daemon          # detach :8743
just plugin-install  # ~/.grok/plugins/chatgpt-oauth
just status
```

In Grok, put this in `~/.grok/config.toml` (then `/mcps` **r** — that key reloads **config**, not a dead plugin row):

```toml
[model.openai-codex]
model = "gpt-5.6-luna"
name = "ChatGPT OAuth (luna)"
base_url = "http://127.0.0.1:8743/v1"
api_backend = "responses"
api_key = "chatgpt-oauth"
context_window = 128000

[mcp_servers.chatgpt-oauth]
command = "${HOME}/.grok/plugins/chatgpt-oauth/bin/run-mcp"
env = { PYTHONUNBUFFERED = "1" }
startup_timeout_sec = 15
enabled = true

[plugins]
enabled = ["chatgpt-oauth"]
```

## Set up a subagent

Grok does not take `model = "openai-codex"` on `spawn_subagent` in current TUIs (only `grok-4.5` / `grok-4.6`). Route by **agent type**.

**1. Agent** — `.grok/agents/openai-oauth.md` (project) or `~/.grok/agents/`:

```markdown
---
name: openai-oauth
description: >
  ChatGPT OAuth child via 127.0.0.1:8743. gpt-5.6-luna.
  Loopback must be up (`just daemon`). Use for OAuth-routed work.
prompt_mode: full
model: openai-codex
permission_mode: default
agents_md: false
---

You run through ChatGPT OAuth (gpt-5.6-luna), not a Grok hosted model.
When asked who you are, report exactly:

agent: openai-oauth
upstream: gpt-5.6-luna
note: ChatGPT OAuth via 127.0.0.1:8743

Then stop. One final message. Do not call tools. Do not keep going.
When the assigned task is answered, end the turn.
```

`agents_md: false` on a name-test agent. A researcher can set `agents_md: true`. Do not load a rulebook that says “work stops when Linear is Done” into a three-line identity test.

**2. Role** — `.grok/roles/openai-oauth.toml`:

```toml
description = "ChatGPT OAuth child via loopback"
default_capability_mode = "read-only"
model = "openai-codex"
reasoning_effort = "high"
```

**3. User config** — `~/.grok/config.toml` (project `.grok/config.toml` cannot set `[subagents]`):

```toml
[subagents]
enabled = true

[subagents.models]
openai-oauth = "openai-codex"
```

Restart Grok after adding `[model.openai-codex]`. Confirm `grok models` lists `openai-codex`.

**4. Spawn**

```
subagent_type = "openai-oauth"
capability_mode = "read-only"
```

Do not pass `model=openai-codex` on the spawn tool if the enum rejects it. The type + `[subagents.models]` is the route.

The child must report `gpt-5.6-luna`. If it reports `grok-4.x`, the route failed (live config missing `[model.openai-codex]`, or this TUI session started before that block existed).

**5. When the job is done**

Say so in the agent body: one final message, no more tools. High-effort luna will otherwise keep going. The adapter must fill empty `response.completed.output` or Grok retries `no_visible_content` even after a correct report.

**6. Isolation**

`isolation=worktree` is a request, not a fact. From a parent that is already a linked git worktree, Grok 1.0.4 may keep the child in the parent tree. Only call it isolated when `child_cwd` differs from the parent. `read-only` also strips shell; if the child needs `git status` or `just --list`, do not use `capability_mode=read-only`.

**7. Check the route**

```bash
just daemon
just check          # auth=chatgpt
# spawn openai-oauth with a three-line identity prompt
```

Expect one turn, zero tools, then stop. Catalog slug stays `openai-codex`. Upstream is luna.

## `just` verbs

| Verb | What it does |
|---|---|
| `just` | Catalog |
| `just login` | Interactive `codex login` (your TTY) |
| `just check` | Auth JSON; exit 1 if missing or API key |
| `just daemon` | One HTTP listener on `127.0.0.1:8743` |
| `just health` | `GET /health` |
| `just stop` | Kill **our** listener only |
| `just self-test` | Canned SSE / holder checks; no network |
| `just plugin-install` | Copy plugin into `~/.grok/plugins/chatgpt-oauth` |
| `just plugin-uninstall` | Remove that directory |
| `just status` | Auth + plugin path + HTTP |

`just login` is the only interactive verb. The MCP `login` tool only **prints** the same instruction. It does not exec `codex login`.

## If OAuth is not initialized

`just check`, `GET /health`, and MCP `health` / `login` return `auth` other than `chatgpt` and a `login` field:

```
ChatGPT OAuth is not initialized. In a local terminal run:
  codex login
Choose ChatGPT, not an API key.
```

`auth_mode=apikey` is refused the same way. There is no fallback to `api.openai.com`.

## How Grok talks to it

Grok’s custom-model client uses the Responses API (`stream: true`, `store: false`). The adapter:

- Forces `gpt-5.6-luna`, high / standard reasoning
- Maps `role=system` → `developer` (ChatGPT rejects system)
- Drops `item_reference`
- Fills empty `response.completed.output` from `output_item.done` (otherwise Grok retries `no_visible_content`)

Stdio MCP (Grok 1.0.4 / rmcp) is **one JSON line per message**. Replies match the request framing. `/mcps` **r** refreshes after a `config.toml` edit. It does not resurrect a plugin row marked `[unavailable]`. Put the server under **Local** via `[mcp_servers.chatgpt-oauth]`.

`:8743` is a host singleton. Two Grok sessions share it. Concurrent POSTs are fine. Last MCP holder out may tear the listener down; `just daemon` brings it back without a holder.

## Troubleshooting

| Symptom | What to do |
|---|---|
| `just check` exit 1 | `just login`, choose ChatGPT |
| `/health` connection refused | `just daemon` |
| `/mcps` plugin row `[unavailable]` | Ignore the plugin group. Use Local `chatgpt-oauth` after a config `r` |
| `r` does nothing | `r` is a config refresh. Edit `config.toml` or `Space` to toggle enable |
| Child reports then Grok retries | You are not running this adapter’s completed.output fill |
| Child is grok-4.x | `[model.openai-codex]` missing or Grok not restarted after adding it |

## Layout

```
chatgpt-oauth-loopback/
  justfile           operator catalog
  loopback.py        HTTP singleton :8743
  bin/mcp_server.py  stdio MCP (health, login)
  bin/run-mcp        exec the MCP server
  plugin.json        Grok plugin name chatgpt-oauth
  .mcp.json          plugin MCP manifest
```

Python 3 stdlib only. No npm.

## License

MIT
