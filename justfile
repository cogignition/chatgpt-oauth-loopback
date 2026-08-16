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

# Official install: grok plugin install (trusted). Drops the old side-copy first.
plugin-install:
    #!/usr/bin/env bash
    set -euo pipefail
    dest="{{ plugin_dest }}"
    if [ -d "${dest}" ]; then
      rm -rf "${dest}"
      echo "removed side-copy ${dest}"
    fi
    if grok plugin list --json 2>/dev/null | grep -q '"name": "chatgpt-oauth"'; then
      grok plugin update chatgpt-oauth
    else
      grok plugin install . --trust
    fi
    grok plugin enable chatgpt-oauth
    echo "enable in ~/.grok/config.toml: [plugins] enabled = [\"chatgpt-oauth\"]"
    echo "do not add [mcp_servers.chatgpt-oauth]; .mcp.json owns the server"

# Official uninstall, plus any leftover side-copy.
plugin-uninstall:
    #!/usr/bin/env bash
    set -euo pipefail
    dest="{{ plugin_dest }}"
    grok plugin uninstall chatgpt-oauth --confirm || true
    if [ -d "${dest}" ]; then
      rm -rf "${dest}"
      echo "removed side-copy ${dest}"
    fi

# One semver home (.grok-plugin/plugin.json). Mirrors must match.
version-check:
    python3 scripts/check-version

# Point this clone at hooks/ (core.hooksPath). Needed once per clone.
hooks-install:
    git config core.hooksPath hooks
    chmod +x hooks/pre-commit hooks/pre-push hooks/commit-msg scripts/check-version
    git config --get core.hooksPath

# Tag v + manifest version. Does not push. Tree must be clean.
# Move CHANGELOG [Unreleased] to ## [X.Y.Z] - YYYY-MM-DD first.
release:
    python3 scripts/check-version --release
    grok plugin tag .

# Auth file, plugin install, and :8743 in one shot.
status:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "auth:"
    {{ python }} loopback.py --check || true
    echo "plugin:"
    grok plugin list 2>/dev/null | grep -E 'chatgpt-oauth' || echo "  not in grok plugin list"
    if [ -d "{{ plugin_dest }}" ]; then echo "  leftover side-copy {{ plugin_dest }}"; fi
    echo "http:"
    if curl -sS -m 1 http://127.0.0.1:8743/health; then echo; else echo "  down"; fi
