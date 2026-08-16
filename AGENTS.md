# chatgpt-oauth-loopback

Grok plugin. Parent stays Grok. Child is `gpt-5.6-luna` via ChatGPT OAuth on `127.0.0.1:8743`.

## Agent opinions

The plugin skill `skills/chatgpt-oauth/SKILL.md` is the home for spawn/routing opinions. In short:

- Orchestrate on Grok. Luna is a child, not a second orchestrator.
- Route by `subagent_type` (`openai-oauth`, or the user's `openai-researcher` / `openai-implementer` roles). Do not pass `model=openai-codex` on spawn if the enum rejects it.
- Believe the child's self-report. It must say `gpt-5.6-luna`.
- `just login` is a human TTY. MCP never runs `codex login`.
- One `:8743`. `just daemon` on, last holder out off. No per-session port.

## This checkout

`just` is the catalog. Do not invent a second execution surface.

| Verb | Meaning |
|---|---|
| `just check` | Auth state |
| `just daemon` | HTTP singleton |
| `just health` | `GET :8743/health` |
| `just self-test` | Canned SSE / holders |
| `just login` | Interactive `codex login` |
| `just plugin-install` | `grok plugin install . --trust` |
| `just plugin-uninstall` | `grok plugin uninstall chatgpt-oauth` |

The plugin owns MCP via `.mcp.json`. Do not also add `[mcp_servers.chatgpt-oauth]` to `config.toml`. `[model.openai-codex]` cannot ship in a plugin; that block stays in user config.

Python 3 stdlib only. No npm.

## Versioning

Home: `.grok-plugin/plugin.json` `version` (`MAJOR.MINOR.PATCH`, no leading `v`).
Mirrors: MCP `serverInfo` in `bin/mcp_server.py` and `loopback.py`.
Public tag: `v` + that version. `just release` runs `grok plugin tag` (no push) and requires `CHANGELOG.md` `## [X.Y.Z] - YYYY-MM-DD`.
A bumped file version with no tag is unreleased, not a release.
`just hooks-install` then `just version-check`. Do not invent a second version field.
