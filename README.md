# Edge Agent Bridge

[![PyPI version](https://img.shields.io/pypi/v/edge-agent-bridge.svg?color=blue)](https://pypi.org/project/edge-agent-bridge/)
[![Python versions](https://img.shields.io/pypi/pyversions/edge-agent-bridge.svg)](https://pypi.org/project/edge-agent-bridge/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Sponsor](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-ff69b4.svg)](https://github.com/sponsors/shanewas)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Donate-yellow.svg)](https://buymeacoffee.com/shanewas)

Control your real, active Microsoft Edge tabs directly from Python scripts and CLI commands.

Standard browser automation frameworks like Playwright, Puppeteer, and Selenium always spin up clean temporary profiles that don't have your logged-in cookies, which ends up triggering bot checks or breaking on company SSO portals. Edge Agent Bridge skips that headache by attaching straight to your running browser window, so you don't lose your active session, enterprise VPN, or saved logins. It dispatches hardware-level inputs through Chrome DevTools Protocol over a local RFC 6455 WebSocket.

---

## Measured Benchmarks

Ran 50 sequential tab queries on Windows 11 to compare round-trip response times:

| Setup | P50 Latency | Minimum | Extra Dependencies | Session State |
| :--- | :--- | :--- | :--- | :--- |
| **Edge Agent Bridge (WebSocket)** | **12.4 ms** | **8.1 ms** | **None (Standard Library)** | Live Edge Tabs |
| **HTTP Long Polling** | 860 ms | 125 ms | None | Live Edge Tabs |
| **Playwright Browser Launch** | ~1,800 ms | ~1,200 ms | 5+ packages & binaries | Blank Incognito |

---

## Installation

```bash
pip install edge-agent-bridge
```

Runs on Python 3.8+ without installing external packages.

---

## Fast Setup

1. Open `edge://extensions` in Microsoft Edge and toggle Developer mode on.
2. Run `edge-bridge extension open` in your terminal to reveal the extension folder.
3. In Edge, select "Load unpacked" and pick that folder.
4. Verify the connection by running:
   ```bash
   edge-bridge status
   ```

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

## Security Model

- **Localhost only**: The daemon binds strictly to `127.0.0.1:18999` and refuses remote network traffic.
- **Origin check**: Any browser page attempting to open `ws://127.0.0.1:18999/ws` gets rejected with 403 Forbidden, meaning web pages you browse cannot hijack the bridge.
- **Zero telemetry**: Nothing leaves your computer.

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
