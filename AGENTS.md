# chatgpt-oauth-loopback

Grok plugin. Parent stays Grok. Child is `gpt-5.6-luna` via ChatGPT OAuth on `127.0.0.1:8743`.

## Agent opinions

The plugin skill `skills/chatgpt-oauth/SKILL.md` is parent guidance. The shipped child type is `openai-auth`. They are not the same name.

- Orchestrate on Grok. Luna is a child, not a second orchestrator.
- Route via catalog `openai-codex` (wire `gpt-5.6-luna`). Spawn `openai-auth` (medium). Fast / researcher / implementer are `examples/agents/` — not installed. If the type enum is only the built-ins, spawn `general-purpose` with `model=openai-codex`.
- Believe the child's self-report. It must say `gpt-5.6-luna`.
- Login is `codex login` on a human TTY. MCP never runs it.
- One `:8743`. `python3 loopback.py --daemon` on. Last holder out off. No per-session port.

## This checkout

There is no `just` catalog. Drive the script and `grok` directly.

| Command | Meaning |
|---|---|
| `python3 loopback.py --check` | Auth state |
| `python3 loopback.py --daemon` | HTTP singleton |
| `python3 loopback.py --stop` | Kill our listener only |
| `python3 loopback.py --self-test` | Canned SSE / holders / transform |
| `codex login` | Interactive ChatGPT OAuth |
| `grok plugin install . --trust` | Install this checkout |
| `python3 scripts/check-version` | Semver homes + CHANGELOG |
| `python3 scripts/check-version --release && grok plugin tag .` | Tag `vMAJOR.MINOR.PATCH` |

The plugin owns MCP via `.mcp.json`. Do not also add `[mcp_servers.chatgpt-oauth]` to `config.toml`. `[model.openai-codex]` cannot ship in a plugin; that block stays in user config.

Python 3 stdlib only. No npm. No just.

## Versioning

Home: `.grok-plugin/plugin.json` `version` (`MAJOR.MINOR.PATCH`, no leading `v`).
Mirrors: MCP `serverInfo` in `bin/mcp_server.py` and `loopback.py`.
Public tag: `v` + that version. Requires `CHANGELOG.md` `## [X.Y.Z] - YYYY-MM-DD`.
A bumped file version with no tag is unreleased, not a release.
Once per clone: `git config core.hooksPath hooks`. Do not invent a second version field.
