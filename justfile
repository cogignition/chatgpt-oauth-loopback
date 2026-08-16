# ChatGPT OAuth loopback for Grok.
# `just` with no args is the catalog. Run a verb; do not invent a second surface.

set dotenv-load := false

plugin_dest := env_var_or_default("HOME", "") / ".grok/plugins/chatgpt-oauth"
python := "python3"

# List verbs.
default:
    @just --list

# Auth state. Exit 1 if missing or API key.
check:
    {{ python }} loopback.py --check

# GET :8743/health. Fails if the singleton is down.
health:
    curl -sS -m 2 http://127.0.0.1:8743/health
    @echo

# Lights on: one HTTP listener. Shared by every Grok session. Zero holders.
daemon:
    {{ python }} loopback.py --daemon

# Lights out now. Kills our listener even if Grok sessions still hold.
stop:
    #!/usr/bin/env bash
    set -euo pipefail
    pids="$(lsof -nP -t -iTCP:8743 -sTCP:LISTEN 2>/dev/null || true)"
    if [ -z "${pids}" ]; then
      echo "nothing on :8743"
      exit 0
    fi
    for pid in ${pids}; do
      cmd="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
      if echo "${cmd}" | grep -q 'loopback.py'; then
        echo "stop ${pid}"
        kill "${pid}" || true
      else
        echo "leave ${pid} (${cmd})"
      fi
    done

# Canned SSE + holder checks. No network.
self-test:
    {{ python }} loopback.py --self-test

# Interactive `codex login` (ChatGPT, not API key). Your TTY, not MCP.
login:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v codex >/dev/null 2>&1; then
      echo "codex not on PATH. Install Codex CLI, then: just login"
      exit 1
    fi
    echo "Choose ChatGPT. Do not choose API key."
    exec codex login

# Copy plugin files into ~/.grok/plugins/chatgpt-oauth (user, auto-trusted).
plugin-install:
    #!/usr/bin/env bash
    set -euo pipefail
    dest="{{ plugin_dest }}"
    mkdir -p "${dest}/bin"
    install -m 0755 bin/run-mcp "${dest}/bin/run-mcp"
    install -m 0755 bin/mcp_server.py "${dest}/bin/mcp_server.py"
    install -m 0644 plugin.json "${dest}/plugin.json"
    python3 -c 'import json; from pathlib import Path; dest=Path("'"${dest}"'"); dest.joinpath(".mcp.json").write_text(json.dumps({"mcpServers":{"chatgpt-oauth":{"command": str(dest / "bin" / "run-mcp"), "env": {"PYTHONUNBUFFERED": "1"}}}}, indent=2)+"\n")'
    echo "installed ${dest}"
    echo "Grok config: [mcp_servers.chatgpt-oauth] and [plugins] enabled = [\"chatgpt-oauth\"]"
    echo "Then /mcps r  (config refresh, not plugin r)"

# Remove the installed user plugin.
plugin-uninstall:
    #!/usr/bin/env bash
    set -euo pipefail
    dest="{{ plugin_dest }}"
    if [ -d "${dest}" ]; then
      rm -rf "${dest}"
      echo "removed ${dest}"
    else
      echo "not installed"
    fi

# Auth file, plugin dir, and :8743 in one shot.
status:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "auth:"
    {{ python }} loopback.py --check || true
    echo "plugin:"
    if [ -d "{{ plugin_dest }}" ]; then echo "  {{ plugin_dest }}"; else echo "  not installed"; fi
    echo "http:"
    if curl -sS -m 1 http://127.0.0.1:8743/health; then echo; else echo "  down"; fi
