# Agent Browser Bridge (ABB)

[![PyPI - Version](https://img.shields.io/pypi/v/edge-agent-bridge?color=0078D4&logo=pypi&logoColor=white&label=PyPI)](https://pypi.org/project/edge-agent-bridge/)
[![GitHub Release](https://img.shields.io/github/v/release/shanewas/edge-agent-bridge?color=2ea44f&logo=github&label=Release)](https://github.com/shanewas/edge-agent-bridge/releases/latest)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/edge-agent-bridge?color=3776AB&logo=python&logoColor=white)](https://pypi.org/project/edge-agent-bridge/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/shanewas/edge-agent-bridge/blob/main/LICENSE)
[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/shanewas)
[![Buy Me A Coffee](https://img.shields.io/badge/Donate-Buy%20Me%20A%20Coffee-ffdd00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/shanewas)

Universal real-time AI agent control for Microsoft Edge and Chromium browsers directly from Python scripts and CLI commands.

Standard browser automation frameworks like Playwright, Puppeteer, and Selenium always spin up clean temporary profiles that lack your logged-in cookies, triggering bot checks or breaking on corporate SSO portals. **Agent Browser Bridge** connects any AI coding agent (Claude, Antigravity, OpenAI Codex, OpenCode, AutoGPT, custom agents) straight to your running browser window, preserving active sessions, enterprise VPNs, and saved credentials. It dispatches hardware-level inputs through Chrome DevTools Protocol over a local RFC 6455 WebSocket.

---

## Measured Benchmarks

Hard benchmark and stress test suite executed against live Microsoft Edge tabs (`tests/test_benchmark_hard.py`):

| Gate | Category | Load & Conditions | Result | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BM-01** | **WebSocket Latency** | 200 sequential calls | **P50: 9.09 ms** (Min: 5.89 ms, P95: 14.35 ms) | P50 < 20 ms | **PASS** |
| **BM-02** | **Action Batching** | 50 ops batched vs sequential | **7.9x speedup** (Batched: 140 ms / 356 ops/s vs 1103 ms) | >= 3.0x | **PASS** |
| **BM-03** | **Native Click Burst** | 100 rapid-fire CDP clicks | **100/100 clicks, 100% `isTrusted: true`**, 0 dropped | 100% trusted | **PASS** |
| **BM-04** | **Typing Integrity** | 55 chars Unicode + Symbols + Japanese | **100% byte match** in **216 ms** (`EdgeAgent 日本語...`) | Exact match | **PASS** |
| **BM-05** | **CSS `:hover` Cascade** | Multi-tier pure CSS dropdown | `sub1: block` -> `sub2: block` -> clicked target | Blink `:hover` | **PASS** |
| **BM-06** | **CDP Mouse Drag** | 300px coordinate drag over 15 steps | Dropped successfully in **612 ms** | Valid drop | **PASS** |
| **BM-07** | **Massive DOM Scanner** | 3,000 synthetic DOM elements | **2,253 interactive elements scanned in 134.8 ms** | < 350 ms | **PASS** |
| **BM-08** | **Screenshot Capture** | Viewport PNG capture + Base64 decode | **111.2 ms avg per screenshot** (99.8 KB PNG) | < 300 ms | **PASS** |
| **BM-09** | **Tab Query Lifecycle** | Query open tabs & active tab ID | **12 Edge tabs queried in 11.9 ms** | Active tab ok | **PASS** |

### Run the Benchmark Suite Locally

```bash
python tests/test_benchmark_hard.py
```

---

## Installation

```bash
pip install edge-agent-bridge
```

Runs on Python 3.8+ without installing external packages.

---

## Fast Setup

### 1. Install the Microsoft Edge Extension
You can install the extension via either method:

- **Method A (Microsoft Edge Add-ons Store)**:
  Install the official **Antigravity Edge Bridge** extension from the [Microsoft Edge Add-ons Store](https://microsoftedge.microsoft.com/addons).
- **Method B (Developer Mode / Unpacked)**:
  1. Open `edge://extensions` in Edge and toggle **Developer mode** on.
  2. Run in terminal:
     ```bash
     edge-bridge extension open
     ```
  3. Click **Load unpacked** and select that directory.

### 2. Verify Connection
Run in terminal:
```bash
edge-bridge status
```
When Microsoft Edge is open, the bridge daemon connects instantly over `127.0.0.1:18999` with sub-15ms WebSocket latency.

---

## Python API

```python
from edge_agent_bridge import Edge

with Edge() as browser:
    tab = browser.tab()
    print("Active:", tab["tab"]["title"])

    browser.nav("https://news.ycombinator.com")
    browser.hover("past")
    browser.click("comments")
    browser.fill("Search:", "AI agents")

    elements = browser.elements()
    print(f"Found {len(elements)} targets")

    browser.screenshot("hn.png")
```

---

## Command Line Interface

```bash
# Check daemon and socket state
edge-bridge status

# Query active tab
edge-bridge tab

# List open tabs or jump to specific ID
edge-bridge tabs
edge-bridge switch 1234

# Hover by visible text label or coordinates
edge-bridge hover "Settings"
edge-bridge hover --x 450 --y 320

# Hardware click with trusted events
edge-bridge click "Sign In"
edge-bridge click "#submit-button"

# Double click, right click, or drag and drop
edge-bridge dblclick "File_01.pdf"
edge-bridge rightclick "Folder A"
edge-bridge drag "Task 1" "Done Column"

# Fill inputs and dispatch keyboard keys
edge-bridge fill "Search query" "LangChain vs AutoGPT"
edge-bridge key Enter
edge-bridge key Ctrl+A

# Extract element text or take viewport snapshots
edge-bridge text "#results-count"
edge-bridge screenshot output.png

# In-memory action batching (single round-trip multi-step execution)
edge-bridge batch '[{"action":"click","x":450,"y":320},{"action":"sleep","ms":50},{"action":"fill","target":"Search","text":"AI Agents"}]'
```

---

## Interactive REPL

If you're running repeated actions and want to skip Python startup overhead, launch the interactive shell:

```bash
edge-bridge repl
```

```text
=== Edge Bridge Real-Time Interactive REPL ===
edge> tab
[11.8ms] {"success": true, "tab": {"id": 1459, "title": "GitHub"}}
edge> click "Pull requests"
[14.2ms] {"success": true, "x": 380, "y": 96, "native": true}
edge> fill "Type / to search" "bugfix"
[18.9ms] {"success": true, "text": "bugfix", "native": true}
```

---

## Architecture & Security Model

- **RFC 6455 Streaming & Frame Reassembly**: Full support for multi-frame continuation sequences (`opcode=0`) when Chromium fragments payloads >64KB (full-page DOM dumps, multi-megabyte screenshots).
- **Fast Integer-XOR Unmasking**: Standard-library integer XOR unmasks multi-megabyte WebSocket payloads in <1ms without C-extensions or external dependencies.
- **Localhost only**: The daemon binds strictly to `127.0.0.1:18999` and refuses remote network traffic.
- **Origin check**: Any browser page attempting to open `ws://127.0.0.1:18999/ws` gets rejected with 403 Forbidden, meaning web pages you browse cannot hijack the bridge.
- **Zero telemetry**: Nothing leaves your computer. Zero external network calls.

---

## Support & Sponsorship

Edge Agent Bridge is built by **Shanewas Ahmed**.

If this project saves you engineering hours or simplifies your agent workflows, consider supporting its development:

- **GitHub Sponsors**: [github.com/sponsors/shanewas](https://github.com/sponsors/shanewas)
- **Buy Me a Coffee**: [buymeacoffee.com/shanewas](https://buymeacoffee.com/shanewas)
- **Ko-fi**: [ko-fi.com/shanewas](https://ko-fi.com/shanewas)

Sponsorship helps fund keeping CDP handlers aligned with rapid Chromium engine updates and maintaining zero-dependency Python packages.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
