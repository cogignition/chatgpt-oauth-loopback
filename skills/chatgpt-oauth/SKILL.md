---
name: chatgpt-oauth
description: >
  Route Grok children through ChatGPT OAuth (gpt-5.6-luna) on 127.0.0.1:8743.
  Use when spawning openai-auth, checking loopback health, or when the user
  mentions luna, ChatGPT OAuth, openai-codex, or a Codex child.
  Not a platform API key. Not the child agent (that type is openai-auth).
when-to-use: spawn openai-auth, ChatGPT OAuth child, gpt-5.6-luna, openai-codex, loopback health, codex login
allowed-tools: search_tool, use_tool, spawn_subagent
license: MIT
---

# ChatGPT OAuth children

This skill is **parent guidance**. The child type is `openai-auth`. Do not name them the same: `/chatgpt-oauth` loads this playbook; `subagent_type=openai-auth` is the luna session.

Parent stays Grok. The child is `gpt-5.6-luna` authenticated as a ChatGPT subscriber. There is no `OPENAI_API_KEY`. There is no `api.openai.com`.

## Opinions

1. **Orchestrate here.** Planning, review, merge, and praxis stay on the Grok parent. Luna is a child identity, not a second orchestrator.
2. **Ship one child, not a squad.** Install registers `openai-auth` (medium). Fast / researcher / implementer live in `examples/agents/` — copy them only if you want those types.
3. **Route to luna.** Catalog slug `openai-codex` sends `model=gpt-5.6-luna` through `:8743`. If `openai-auth` is not in this TUI's type enum, spawn `general-purpose` with `model=openai-codex`.
4. **Trust the child's self-report.** It must say `gpt-5.6-luna`. If it says `grok-4.x`, the live session is missing `[model.openai-codex]` or started before that block existed.
5. **Login is a human TTY.** `codex login` (choose ChatGPT). MCP `login` only prints that instruction.
6. **One host light.** `:8743` is a singleton. `python3 loopback.py --daemon` on. `--stop` or last MCP holder out off.

## Before you spawn

Call MCP `chatgpt-oauth__health`.

| `auth` / bind | What you do |
|---|---|
| `chatgpt` and `:8743` up | Spawn |
| not `chatgpt` | Tell the user to run `codex login`. Stop. |
| connection refused | Tell the user to run `python3 loopback.py --daemon`. Stop. |
| `auth_mode=apikey` | Same as missing OAuth. Refuse. |

## Spawn

```
subagent_type = "openai-auth"
# qualified if needed: chatgpt-oauth:openai-auth
# if the type enum rejects that:
subagent_type = "general-purpose"
model = "openai-codex"
```

| Type | Effort | Where |
|---|---|---|
| `openai-auth` | medium | shipped |
| `openai-auth-fast` | low | `examples/agents/` |
| `openai-auth-researcher` | high | `examples/agents/` |
| `openai-auth-implementer` | xhigh | `examples/agents/` |

The loopback forwards effort. It does not overwrite to `high`.

Capability: `read-only` unless the child needs a shell. Isolation `worktree` is a request — only call it isolated when `child_cwd` differs from the parent.

`agents_md: false` on the shipped `openai-auth` agent (name tests). Researcher/implementer examples set `agents_md: true`. High-effort luna keeps going unless the prompt says: one final message, then stop.
