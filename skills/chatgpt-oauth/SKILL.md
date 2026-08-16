---
name: chatgpt-oauth
description: >
  Route Grok children through ChatGPT OAuth (gpt-5.6-luna) on 127.0.0.1:8743.
  Use when spawning openai-oauth / openai-researcher / openai-implementer,
  checking loopback health, or when the user mentions luna, ChatGPT OAuth,
  openai-codex, or a Codex child. Not a platform API key.
when-to-use: spawn openai-oauth, ChatGPT OAuth child, gpt-5.6-luna, openai-codex, loopback health, codex login
allowed-tools: search_tool, use_tool, spawn_subagent
license: MIT
---

# ChatGPT OAuth children

Parent stays Grok. The child is `gpt-5.6-luna` authenticated as a ChatGPT subscriber. There is no `OPENAI_API_KEY`. There is no `api.openai.com`.

## Opinions

1. **Orchestrate here.** Planning, review, merge, and praxis stay on the Grok parent. Luna is a child identity, not a second orchestrator.
2. **Route by type, not by spawn `model`.** Use `subagent_type` `openai-oauth` (or the user's `openai-researcher` / `openai-implementer` roles). Current TUIs reject `model=openai-codex` on `spawn_subagent`. The type plus `[subagents.models]` / `[model.openai-codex]` is the route.
3. **Trust the child's self-report.** The child must say `gpt-5.6-luna`. If it says `grok-4.x`, the live session is missing `[model.openai-codex]` or started before that block existed. Do not keep going as if the route worked.
4. **Login is a human TTY.** `just login` (Codex CLI; choose ChatGPT). MCP `login` only prints that instruction. Never exec `codex login` over MCP stdio.
5. **One host light.** `:8743` is a singleton. `just daemon` turns it on. Last MCP holder out turns it off. Do not invent a port per session.

## Before you spawn

Call MCP `chatgpt-oauth` / `health` (tools `chatgpt-oauth__health` via `search_tool` then `use_tool`).

| `auth` / bind | What you do |
|---|---|
| `chatgpt` and `:8743` up | Spawn |
| not `chatgpt` | Tell the user to run `just login` in a local terminal. Stop. |
| connection refused | Tell the user to run `just daemon`. Stop. |
| `auth_mode=apikey` | Same as missing OAuth. Refuse. No fallback to the platform API. |

## Spawn

```
subagent_type = "openai-oauth"
```

Capability: `read-only` unless the child needs a shell (`git status`, `just`). Isolation `worktree` is a request, not a fact — only call it isolated when `child_cwd` differs from the parent.

Do not load a praxis/rulebook identity into a three-line name test (`agents_md: false` on this plugin's agent). A researcher can set `agents_md: true`.

High-effort luna keeps going unless the prompt says: one final message, then stop.

## Catalog

`just` is the operator surface. Do not invent a second one.

| Verb | Meaning |
|---|---|
| `just login` | Interactive ChatGPT OAuth |
| `just check` | Auth JSON |
| `just daemon` | Lights on |
| `just health` | `GET /health` |
| `just plugin-install` | `grok plugin install . --trust` |
| `just version-check` | Semver homes + CHANGELOG |
| `just release` | Tag `v` + manifest version (no push) |
