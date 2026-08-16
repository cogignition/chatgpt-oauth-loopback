# ChatGPT OAuth loopback

A Grok plugin that lets **Grok orchestrate ChatGPT OAuth children**.

The parent stays Grok. The child is `gpt-5.6-luna`, authenticated as a ChatGPT subscriber, not as an OpenAI platform customer. There is no `OPENAI_API_KEY`. There is no call to `api.openai.com`.

If ChatGPT OAuth is missing, this project **tells you to log in**. It will not steal the MCP stdio pipe to run `codex login`. You run that in a terminal: `codex login`.

Tracked as [HUB-186](https://linear.app/hublar/issue/HUB-186/align-chatgpt-oauth-loopback-with-grok-plugin-standards-praxis).

## Why this exists

Most “multi-model Grok” setups drop a platform key in `config.toml` and point at `api.openai.com`. That is a second bill and a second identity.

This loopback reuses `codex login` (ChatGPT). Grok’s custom-model client talks HTTP to `127.0.0.1:8743`. A tiny MCP server is the session channel so that HTTP process is not a command sitting in your TUI.

```
  Grok 4.6  ──spawn_subagent──►  child (catalog slug luna)
       │                                │
       │ MCP chatgpt-oauth              │ POST /v1/responses
       │ (plugin .mcp.json)             ▼
       │                         127.0.0.1:8743  loopback.py
       │                                │
       │                                ▼
       │                         chatgpt.com Codex backend
       │                         model = gpt-5.6-luna
       ▼                         auth  = ~/.codex/auth.json
  /mcps  plugin: chatgpt-oauth
```

Drive `python3 loopback.py` and `grok`. There is no `just` catalog.

## Agent opinions

Canonical text is `skills/chatgpt-oauth/SKILL.md` (also `AGENTS.md` in this checkout). Agents should load that skill when spawning luna children.

1. **Orchestrate here.** Planning, review, merge, and praxis stay on the Grok parent. Luna is a child identity, not a second orchestrator.
2. **Route to luna.** Spawn `openai-auth`, or `general-purpose` with `model=luna`. Wire model is `gpt-5.6-luna`.
3. **Trust the child's self-report.** It must say `gpt-5.6-luna`. If it says `grok-4.x`, the route failed.
4. **Login is a human TTY.** `codex login`. MCP `login` only prints the instruction.
5. **One host light.** `:8743` is a singleton. `python3 loopback.py --daemon` on. `--stop` or last holder out off.

## What it is not

| This | Not this |
|---|---|
| ChatGPT OAuth (`codex login` → ChatGPT) | Platform API key / `auth_mode=apikey` |
| `127.0.0.1:8743` | `api.openai.com` |
| Upstream **gpt-5.6-luna** | Calling the child “Codex” |
| Plugin MCP + detached HTTP | A Grok TUI background command |
| One listener per host | One port per Grok session |
| Plugin `.mcp.json` | A second `[mcp_servers.chatgpt-oauth]` in config.toml |

## Prerequisites

- Grok Build TUI
- Codex CLI (`codex` on `PATH`)
- Python 3 (stdlib only; no npm)
## First run

```bash
git clone https://github.com/cogignition/chatgpt-oauth-loopback.git
cd chatgpt-oauth-loopback
codex login                      # choose ChatGPT, not API key
python3 loopback.py --check      # must print "chatgpt"; exit 1 if refused
python3 loopback.py --daemon     # detach :8743
grok plugin install . --trust
grok plugin enable chatgpt-oauth
```

In `~/.grok/config.toml` you still need the **custom model** (plugins cannot ship `[model.*]`) and the plugin enabled. **Do not** add `[mcp_servers.chatgpt-oauth]` — the plugin `.mcp.json` owns that server.

```toml
[model.luna]
model = "gpt-5.6-luna"
name = "luna"
base_url = "http://127.0.0.1:8743/v1"
api_backend = "responses"
api_key = "chatgpt-oauth"
context_window = 272000
# Official model spec is 1.05M context / 128k output. ChatGPT OAuth
# (Codex backend) advertises 272k and 2x-prices input above that.
# Do not set max_completion_tokens — Grok sends max_output_tokens and
# the Codex backend returns 400 Unsupported parameter.

[plugins]
enabled = ["chatgpt-oauth"]

[subagents]
enabled = true

[subagents.models]
openai-auth = "luna"
```

Restart Grok after adding `[model.luna]`. Confirm `grok models` lists `luna`. In `/mcps`, expect **plugin** `chatgpt-oauth`, not a Local duplicate.

## Main-window identity (luna still says Grok)

Picking `luna` in the model picker **does** send turns to `gpt-5.6-luna` on `:8743`. Session metadata will show `current_model_id = gpt-5.6-luna` and the footer `16K / 272K`. That is not the same as the **system prompt**.

Grok always starts the prompt with `You are Grok 4.6 released by xAI.` There is **no** `[model.luna]` field for a per-model system prompt. `[agent]` is global (every model), not per catalog slug.

So a main window on luna will self-report Grok unless that clause is rewritten. Proof of routing is the session file / `:8743` POST log, not the model's answer. The adapter rewrites only the identity sentence; tool policy stays.

Ways to change what it believes:

| How | Effect |
|---|---|
| Adapter rewrite (this repo) | Replaces incoming `You are Grok 4.6…` in system/developer text. Leaves the rest of the Grok harness prompt. |
| `grok --model luna --rules 'You are gpt-5.6-luna via ChatGPT OAuth…'` | Appends to Grok's prompt (`<human_rules>`). Launch-time only. |
| `grok --model luna --system-prompt-override '…'` | Replaces the entire Grok prompt. Drops tool policy. Do not use for a normal TUI. |
| Plugin agent `openai-auth` | Identity for **spawned children**, not the main window. |

This checkout's `AGENTS.md` talks about luna as a *child route*. That text is loaded into a luna **main** session too, which is why the herdr tab labeled `luna` argued it was Grok.

## Set up a subagent

If this TUI's spawn `model` enum does not list `luna`, route by **agent type** (`openai-auth`) or pass `model=luna` after a restart.

The plugin ships **one** child: `agents/openai-auth.md`. The skill `chatgpt-oauth` is parent guidance, not a second child type.

```
subagent_type = "openai-auth"
capability_mode = "read-only"
```

If this TUI only lists the qualified form, use `chatgpt-oauth:openai-auth`. If the type enum is only built-ins, spawn `general-purpose` with `model=luna`.

Fast / researcher / implementer are **examples** (`examples/agents/`). Copy into `agents/` or `~/.grok/agents/` to register. Do not expect plugin install to add a squad.

The child must report `gpt-5.6-luna`. If it reports `grok-4.x`, the route failed (live config missing `[model.luna]`, or this TUI session started before that block existed).

`agents_md: false` on the shipped name-test agent. A researcher can set `agents_md: true`. Do not load a rulebook that says “work stops when Linear is Done” into a three-line identity test.

High-effort luna keeps going unless the prompt says: one final message, then stop. The adapter must fill empty `response.completed.output` or Grok retries `no_visible_content`.

`isolation=worktree` is a request, not a fact. Only call it isolated when `child_cwd` differs from the parent. `read-only` also strips shell; if the child needs `git status` or `just --list`, do not use `capability_mode=read-only`.

```bash
python3 loopback.py --daemon
python3 loopback.py --check   # auth=chatgpt
# spawn openai-auth with a three-line identity prompt
```

Expect one turn, zero tools, then stop. Catalog slug is `luna`. Upstream is `gpt-5.6-luna`.

## Commands

| Command | What it does |
|---|---|
| `codex login` | Interactive ChatGPT OAuth (your TTY) |
| `python3 loopback.py --check` | Auth JSON; exit 1 if missing or API key |
| `python3 loopback.py --daemon` | One HTTP listener on `127.0.0.1:8743` |
| `python3 loopback.py --stop` | Kill **our** listener only |
| `python3 loopback.py --self-test` | Canned SSE / holder / transform checks |
| `curl -sS -m 2 http://127.0.0.1:8743/health` | Listener health |
| `grok plugin install . --trust` | Install this checkout |
| `python3 scripts/check-version` | Semver homes + CHANGELOG |
| `python3 scripts/check-version --release && grok plugin tag .` | Tag `vMAJOR.MINOR.PATCH` (no push) |

The MCP `login` tool only **prints** the same instruction. It does not exec `codex login`.

## If OAuth is not initialized

`python3 loopback.py --check`, `GET /health`, and MCP `health` / `login` return `auth` other than `chatgpt` and a `login` field:

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

Stdio MCP (Grok 1.0.4 / rmcp) is **one JSON line per message**. Replies match the request framing. The plugin `.mcp.json` starts `bin/run-mcp` (`bin/mcp_server.py`: `health`, `login`). `loopback.py --mcp` is debug-only and is not what the plugin launches.

`/plugins` **r** reloads plugins. `/mcps` **r** reloads config. After `grok plugin install . --trust`, enable `chatgpt-oauth` if it is off.

## Many Grok sessions, one light

`[model.luna] base_url` is one URL. The host has **one** `:8743`. You can run as many Grok TUIs as you want. They do not each get a port.

```
  Grok session A ──MCP──┐
                        ├──►  127.0.0.1:8743  (one loopback.py)
  Grok session B ──MCP──┘         │
                                  ▼
                         luna POSTs multiplex
```

**Holders.** Each live MCP process is a holder (pid in `~/.cache/sysop/codex-loopback/holders.json`). `GET /health` reports `holders`.

| Event | Lights |
|---|---|
| `--daemon` | On. Zero holders. Stays up so you can spawn before any TUI attaches. |
| First Grok session MCP starts | Holder = 1. Attaches if already up; starts the listener if not. |
| Second session | Holder = 2. Does **not** reclaim a healthy listener. |
| Concurrent luna children | Fine. `ThreadingHTTPServer`. |
| One session quits | Holder drops. Lights stay on if anyone remains. |
| Last session quits | Holder = 0. **Lights out.** The HTTP process is killed. |
| `--stop` | Lights out now, even if holders remain. |
| `--daemon` after that | Lights on again, zero holders. |

Do not give each session its own port. Grok’s model config cannot follow it.

Token refresh to `~/.codex/auth.json` is locked so two sessions do not clobber the file.

If you open Grok, spawn luna, quit Grok, then `/health` is refused: that is last-out, not a crash. `python3 loopback.py --daemon` or the next session’s MCP turns the light back on.

## Troubleshooting

| Symptom | What to do |
|---|---|
| `--check` exit 1 | `codex login`, choose ChatGPT |
| `/health` connection refused | Last session quit (lights out) or never started. `--daemon` |
| Two TUIs, one dies, children fail | You gave them different ports. Don’t. One `:8743`. |
| `/mcps` shows Local **and** plugin `chatgpt-oauth` | Remove `[mcp_servers.chatgpt-oauth]` from config.toml. Plugin owns MCP. |
| Plugin missing from `grok plugin list` | `grok plugin install . --trust` (not a hand copy into `~/.grok/plugins/`) |
| Child reports then Grok retries | You are not running this adapter’s completed.output fill |
| Child is grok-4.x | `[model.luna]` missing or Grok not restarted after adding it |

## Layout

```
chatgpt-oauth-loopback/
  AGENTS.md                 checkout rules + opinions pointer
  loopback.py               HTTP singleton :8743
  bin/mcp_server.py         stdio MCP (health, login)
  bin/run-mcp               exec the MCP server
  .grok-plugin/plugin.json  Grok manifest (semver home)
  .mcp.json                 plugin MCP (${CLAUDE_PLUGIN_ROOT})
  agents/openai-auth.md     shipped child (medium)
  examples/agents/          extra efforts, not installed
  skills/chatgpt-oauth/     parent spawn guidance
  CHANGELOG.md              Keep a Changelog
  scripts/check-version     semver homes + changelog + tag floor
  hooks/                    pre-commit / pre-push / commit-msg
```

Python 3 stdlib only. No npm.

## License

MIT
