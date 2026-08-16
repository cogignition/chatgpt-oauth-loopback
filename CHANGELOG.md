# Changelog

All notable changes to this project are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: `MAJOR.MINOR.PATCH` in `.grok-plugin/plugin.json`. Tags: `vMAJOR.MINOR.PATCH`.

Park notes under `[Unreleased]`. A release requires `## [X.Y.Z] - YYYY-MM-DD` then `python3 scripts/check-version --release && grok plugin tag .`.

## [Unreleased]

## [0.4.0] - 2026-08-16

### Changed

- Catalog slug is `luna`, not `openai-codex`. `context_window = 272000` (Codex ChatGPT product window; API spec is 1.05M / 128k out)

## [0.3.0] - 2026-08-16

### Added

- Shipped child agent `openai-auth` (medium). Extra efforts in `examples/agents/` (not installed)
- Skill `chatgpt-oauth` documents spawn; it is not the child type
- `python3 loopback.py --stop` (kill our listener only)

### Changed

- Loopback honors requested reasoning effort instead of forcing `high` (still defaults to high)
- Upstream model stays `gpt-5.6-luna` on every request

### Removed

- Auto-installed `openai-fast` / `openai-researcher` / `openai-implementer` (now examples)
- `justfile`. Drive `loopback.py` and `grok` directly.

## [0.2.0] - 2026-08-16

### Added

- Official Grok plugin layout (`.grok-plugin/`, portable `.mcp.json`)
- Plugin agent `openai-oauth` and skill `chatgpt-oauth` (spawn opinions)
- `AGENTS.md`
- Semver + changelog (`just version-check`, `just release`, `CHANGELOG.md`)

### Changed

- `just plugin-install` uses `grok plugin install` / `update`, not a side-copy
- Install docs: plugin owns MCP; do not add `[mcp_servers.chatgpt-oauth]`

### Removed

- Root `plugin.json` (manifest is `.grok-plugin/plugin.json`)

## [0.1.0] - 2026-08-16

### Added

- First public plugin: HTTP loopback on `127.0.0.1:8743`, stdio MCP `health` / `login`
