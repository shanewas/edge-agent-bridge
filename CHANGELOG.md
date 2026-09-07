# Changelog

## 2.0.1

Fixes an authentication hole in the daemon, and corrects what 2.0.0 shipped around the code.

### Security

- Removed `/api/eval`, `/api/tabs` and the `/api/status` alias. `/api/eval` forwarded arbitrary
  JavaScript to the extension without checking the token, so any local process could run script in
  the browser with the user's session. The documented routes are `/exec`, `/status` and `/ws`, and
  `/exec` has always required the token.
- The token file is now created with mode 0600 instead of written and then chmodded, which left it
  world-readable on POSIX for the window in between.

### Fixed

- The MCP server treated a request with `id: 0` as a notification and never answered it, so a
  client numbering from zero hung on its first call.
- An exception inside a tool call killed the MCP session. It now answers -32603 and keeps
  serving.
- `screenshot(path=...)` wrote no file and `edge_screenshot` returned no image. The extension
  reports the capture as `dataUrl`; both callers read a `data` key that never existed, so the
  Python helper returned silently and the MCP tool handed the agent a base64 JSON dump.
- An explicit `tabId` argument now re-pins the session, matching `tab_switch` and `tab_new`.
- `setup` and `mcp-config --client vscode` wrote the server under `mcpServers`. VS Code reads
  `mcp.json` under `servers`, so it registered nothing. Cursor and Windsurf keep `mcpServers`.
- Client config files are written through a temporary file and renamed, so an interrupted
  `setup` can no longer leave a truncated editor config behind.
- `setup` runs the client registration commands as argument lists instead of through a shell.
- `daemon status` printed `PID None`. The status response carries no pid, so the line now reads
  the pid file the daemon already writes.
- `key +` and `key Ctrl++` sent an empty key. The modifier split now takes the last separator.
- Benchmark wall-clock thresholds no longer fail the run by default. A loaded CI runner missed
  them at random, which would have made the pipeline flap. `EDGE_BRIDGE_BENCH_STRICT=1`
  restores them as gates.

- README describes the 2.x surfaces: the MCP server and `edge-bridge setup`, snapshot refs, the
  token on `/exec`, and the shared-host limit that pairing covers. It had still been documenting
  the 1.x CLI, and claimed a Python 3.8 floor against a package that needs 3.10.
- Store screenshots and promo tiles were regenerated. The published ones carried the extension's
  former name and demonstrated commands that no longer exist.
- Targeting and the snapshot role table no longer carry vendor-specific custom-element tag lists.
  Components are still reached through their `role` attribute or the native control in their
  shadow root.
- Frame discovery and subframe snapshot composition moved into their own extension module.
- `scripts/publish_extension.py` submits the extension zip through the Edge Add-ons Update API
  (v1.1, API key auth). `release.yml` publishes to PyPI, cuts the GitHub release, and submits the
  extension when an extension file changed in the push.
- E2E on Linux and macOS reports without failing the workflow until a run there is green. Only
  Windows has been verified against a real browser.

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
