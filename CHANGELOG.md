# Changelog

## 2.0.0

Drive the user's open Edge from any agent: MCP server, `--json` CLI, and a Python client that
share one daemon, with element targeting by snapshot refs instead of fuzzy text.

### Added
- `edge-bridge mcp`: stdio MCP server (protocol 2025-11-25) exposing 29 `edge_*` tools; `edge-bridge setup` registers it with Claude Code, Cursor, Windsurf, Gemini CLI, Codex CLI and VS Code; `edge-bridge mcp-config` prints the snippet.
- `snapshot`: accessibility-style page tree with `e<n>` refs (and `f<frame>e<n>` inside iframes, cross-origin included); every action accepts `ref`; `stale_snapshot`/`stale_ref` errors instead of misclicks; hidden file inputs listed.
- Sessions pin to the tab they first touch and carry `tab: {id, title, url}` on every result; `tab_new` with tab groups or a separate window; `back`, `forward`, `reload`.
- `select`, `upload` (native file chooser over CDP), `type` (per-key events), `screenshot` with jpeg quality, clip, and element capture without stealing focus.
- `wait` on text, selector, ref, url (regex), load, or network idle (WebSocket/EventSource excluded).
- `console`: recent console output, uncaught exceptions and dialogs per tab; `dialog` policy (accept, dismiss, manual).
- `check_radio` / `edge-bridge check-radio`: check radio buttons and checkboxes by selector, label text, or value; ported from v1.2.0 with full pointer+click event sequence.
- Visual highlight ring on the element about to be acted on; `--no-highlight` / `highlight:false`.
- Daemon: token on `/exec`, Host allowlist, Origin required on `/ws`, heartbeat, held command queue while the extension reconnects, frame-size cap, rotating log and pid file in the user data dir, `extension_outdated` message during store review lag, optional pairing (`--require-pairing`). REST aliases `/api/status`, `/api/tabs`, `/api/eval`.
- Hermetic test suite with a fake extension, real-Edge E2E suite, CI on Windows, Linux and macOS.

### Changed
- Extension renamed to "Edge Agent Bridge"; service worker split into modules.
- Python floor 3.10. Single source tree under `edge_agent_bridge/`; version only in `edge_agent_bridge/__init__.py`.
- `tab_close` requires an explicit `tabId`.

### Removed
- `login` and `open_file` verbs, root-level `edge.py`/`bridge.py` copies, HTTP long-poll fallback.

## 1.1.2
- WebSocket continuation frames and faster unmasking in the daemon.

## 1.1.1
- Verified author email; branding assets.

## 1.1.0
- First public release: WebSocket transport, CDP native input, CLI and Python API.
