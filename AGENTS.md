# AGENTS.md

Entry point for Codex, Cursor, Opencode and other agents. Inherits every rule in `CLAUDE.md`.

- Single source tree `edge_agent_bridge/`; nothing to mirror.
- Version in `edge_agent_bridge/__init__.py` only.
- Tests: `python -m pytest -m "not e2e"` (hermetic), `python -m pytest -m e2e` (needs Edge).
- Author email shanewasahmed@gmail.com, never the work address.
