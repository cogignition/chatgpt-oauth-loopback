# ChatGPT OAuth loopback

Grok plugin that lets a Grok session spawn **ChatGPT OAuth** children (upstream `gpt-5.6-luna`) without a platform API key.

This is **not** `api.openai.com`. Auth is `~/.codex/auth.json` after `codex login`. Choose **ChatGPT**, not an API key. `auth_mode=apikey` is refused.

## What it is

| Piece | Role |
|---|---|
| Plugin MCP `chatgpt-oauth` | Session channel. Tools: `health`, `login`. |
| `loopback.py` | HTTP singleton on `127.0.0.1:8743` for Grok's custom-model client. |

Grok config:

```toml
[model.openai-codex]
model = "gpt-5.6-luna"
base_url = "http://127.0.0.1:8743/v1"
api_backend = "responses"
api_key = "chatgpt-oauth"

[mcp_servers.chatgpt-oauth]
command = "${HOME}/.grok/plugins/chatgpt-oauth/bin/run-mcp"
env = { PYTHONUNBUFFERED = "1" }
enabled = true
```

## Install

```bash
grok plugin install cogignition/chatgpt-oauth-loopback --trust
python3 loopback.py --daemon   # detach :8743
```

Or copy `plugin.json`, `.mcp.json`, and `bin/` into `~/.grok/plugins/chatgpt-oauth/`.

## First-time OAuth

If tokens are missing or the file is an API key, `health` / `login` tell you to run:

```bash
codex login
```

Pick ChatGPT. Do not pick API key. The MCP process will not run `codex login` itself (stdio is not a TTY).

## HTTP adapter

```bash
python3 loopback.py --check      # auth state; exit 1 if refused
python3 loopback.py --self-test
python3 loopback.py --daemon     # one listener on 127.0.0.1:8743
```

Do not run the adapter as a Grok TUI command. The plugin MCP is the session channel.

## License

MIT
