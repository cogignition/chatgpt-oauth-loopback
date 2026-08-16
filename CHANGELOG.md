# Changelog

All notable changes to this project are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: `MAJOR.MINOR.PATCH` in `.grok-plugin/plugin.json`. Tags: `vMAJOR.MINOR.PATCH`.

Park notes under `[Unreleased]`. `just release` requires `## [X.Y.Z] - YYYY-MM-DD`.

## [Unreleased]

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
