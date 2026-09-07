"""Setup and configuration helpers for registering Edge Agent Bridge with agent clients.

Detects local agent clients (Claude Code, Gemini, Codex, Cursor, Windsurf, VS Code),
manages mcpServers JSON configuration with automatic backups, and runs CLI registration.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

JSON_TEMPLATE = {
    "mcpServers": {
        "edge": {
            "command": "edge-bridge",
            "args": ["mcp"],
        }
    }
}


def get_mcp_config(client: str) -> str:
    """Return the exact command line or JSON configuration snippet for a client."""
    client = client.lower().strip()
    if client == "claude":
        return "claude mcp add edge -- edge-bridge mcp"
    elif client == "gemini":
        return "gemini mcp add edge edge-bridge mcp"
    elif client == "codex":
        return "codex mcp add edge -- edge-bridge mcp"
    elif client in ("cursor", "windsurf", "vscode"):
        return json.dumps(JSON_TEMPLATE, indent=2)
    return f"# Unknown client '{client}'. Use one of: claude, gemini, codex, cursor, windsurf, vscode"


def merge_json_config(path: Path) -> tuple[bool, str]:
    """Safely merge edge MCP server into a client's JSON configuration file.

    Creates a .bak.<timestamp> backup. If the file is unparsable, it is left untouched.
    """
    p = Path(path)
    if p.exists():
        raw = p.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except Exception as e:
            return False, f"Failed to parse {p}: invalid JSON ({e})"

        # Create backup
        ts = int(time.time())
        bak_path = p.with_name(f"{p.name}.bak.{ts}")
        bak_path.write_text(raw, encoding="utf-8")

        if not isinstance(data, dict):
            data = {}
        if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
            data["mcpServers"] = {}

        data["mcpServers"]["edge"] = {
            "command": "edge-bridge",
            "args": ["mcp"],
        }
        p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return True, f"Updated {p} (backup saved to {bak_path.name})"
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(JSON_TEMPLATE, indent=2) + "\n", encoding="utf-8")
        return True, f"Created {p}"


def _get_vscode_mcp_path(env: dict) -> Path:
    if sys.platform == "win32":
        base = Path(env.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "Code" / "User" / "mcp.json"


def detect_clients(env: dict | None = None, path_which: Callable[[str], str | None] | None = None) -> dict[str, Any]:
    """Detect available agent clients on the system."""
    e = env if env is not None else os.environ
    which = path_which or shutil.which

    cli_clients = {
        "claude": which("claude"),
        "gemini": which("gemini"),
        "codex": which("codex"),
    }

    home = Path.home()
    cursor_path = home / ".cursor" / "mcp.json"
    windsurf_path = home / ".codeium" / "windsurf" / "mcp_config.json"
    vscode_path = _get_vscode_mcp_path(e)

    json_clients = {
        "cursor": {
            "path": cursor_path,
            "found": cursor_path.exists() or cursor_path.parent.exists(),
        },
        "windsurf": {
            "path": windsurf_path,
            "found": windsurf_path.exists() or windsurf_path.parent.exists(),
        },
        "vscode": {
            "path": vscode_path,
            "found": vscode_path.exists() or vscode_path.parent.exists(),
        },
    }

    return {"cli": cli_clients, "json": json_clients}


def mcp_config_cli(client: str) -> int:
    """CLI handler for `edge-bridge mcp-config --client <name>`."""
    print(get_mcp_config(client))
    return 0


def setup_cli(yes: bool = False) -> int:
    """CLI handler for `edge-bridge setup`."""
    print("Edge Agent Bridge Setup — Client Auto-Detection")
    detected = detect_clients()

    targets_cli = []
    for name, path in detected["cli"].items():
        if path:
            targets_cli.append(name)

    targets_json = []
    for name, info in detected["json"].items():
        if info["found"]:
            targets_json.append((name, info["path"]))

    if not targets_cli and not targets_json:
        print("\nNo supported agent clients detected automatically.")
        print("To configure manually, run:")
        for client in ("claude", "cursor", "windsurf", "gemini", "codex", "vscode"):
            print(f"\n  edge-bridge mcp-config --client {client}")
        return 0

    print("\nDetected clients:")
    for c in targets_cli:
        print(f"  - CLI: {c} ({detected['cli'][c]})")
    for name, path in targets_json:
        print(f"  - App: {name} ({path})")

    if not yes:
        try:
            resp = input("\nConfigure detected clients with Edge Agent Bridge MCP server? [y/N]: ").strip().lower()
            if resp not in ("y", "yes"):
                print("Aborted.")
                return 0
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return 0

    # Configure CLI clients
    for c in targets_cli:
        cmd_str = get_mcp_config(c)
        print(f"\nConfiguring {c}...")
        try:
            subprocess.run(cmd_str, shell=True, check=True)
            print(f"  Successfully added edge MCP to {c}")
        except Exception as err:
            print(f"  Failed to configure {c}: {err}")

    # Configure JSON clients
    for name, path in targets_json:
        print(f"\nConfiguring {name} ({path})...")
        ok, msg = merge_json_config(path)
        if ok:
            print(f"  {msg}")
        else:
            print(f"  Error: {msg}")

    print("\nSetup complete! You can verify daemon status with: edge-bridge status")
    return 0
