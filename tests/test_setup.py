"""Tests for edge_agent_bridge.setup."""
import json
import os
import shutil
from pathlib import Path
import pytest
from edge_agent_bridge import setup

def test_mcp_config_snippets():
    cursor_snip = setup.get_mcp_config("cursor")
    data = json.loads(cursor_snip)
    assert "edge" in data["mcpServers"]
    assert data["mcpServers"]["edge"]["command"] == "edge-bridge"
    assert data["mcpServers"]["edge"]["args"] == ["mcp"]

    claude_snip = setup.get_mcp_config("claude")
    assert "claude mcp add edge" in claude_snip

    gemini_snip = setup.get_mcp_config("gemini")
    assert "gemini mcp add edge" in gemini_snip

    codex_snip = setup.get_mcp_config("codex")
    assert "codex mcp add edge" in codex_snip


def test_vscode_uses_the_servers_key():
    # VS Code reads mcp.json under "servers"; writing "mcpServers" there registers nothing.
    data = json.loads(setup.get_mcp_config("vscode"))
    assert list(data) == ["servers"]
    assert data["servers"]["edge"] == {"command": "edge-bridge", "args": ["mcp"]}


def test_merge_into_vscode_keeps_its_own_key(tmp_path):
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"servers": {"other": {"command": "x"}}, "inputs": []}), encoding="utf-8")
    ok, _ = setup.merge_json_config(target, "vscode")
    assert ok
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["servers"]["edge"] == {"command": "edge-bridge", "args": ["mcp"]}
    assert data["servers"]["other"] == {"command": "x"}
    assert data["inputs"] == []
    assert "mcpServers" not in data


def test_merge_creates_vscode_file_with_servers_key(tmp_path):
    target = tmp_path / "nested" / "mcp.json"
    ok, _ = setup.merge_json_config(target, "vscode")
    assert ok
    assert list(json.loads(target.read_text(encoding="utf-8"))) == ["servers"]
    assert not list(target.parent.glob("*.tmp"))


def test_merge_json_config_existing_and_backup(tmp_path):
    target = tmp_path / "mcp.json"
    original = {"mcpServers": {"existing": {"command": "other"}}, "theme": "dark"}
    target.write_text(json.dumps(original, indent=2), encoding="utf-8")

    ok, msg = setup.merge_json_config(target)
    assert ok is True

    # Backup file created
    baks = list(tmp_path.glob("mcp.json.bak.*"))
    assert len(baks) == 1
    assert json.loads(baks[0].read_text(encoding="utf-8")) == original

    # Updated content preserves other keys
    updated = json.loads(target.read_text(encoding="utf-8"))
    assert updated["theme"] == "dark"
    assert updated["mcpServers"]["existing"] == {"command": "other"}
    assert updated["mcpServers"]["edge"] == {"command": "edge-bridge", "args": ["mcp"]}


def test_merge_json_config_unparsable_left_untouched(tmp_path):
    target = tmp_path / "corrupt.json"
    corrupt_content = "this is not json {"
    target.write_text(corrupt_content, encoding="utf-8")

    ok, msg = setup.merge_json_config(target)
    assert ok is False
    assert "invalid" in msg.lower() or "error" in msg.lower() or "parse" in msg.lower()

    # Content unchanged
    assert target.read_text(encoding="utf-8") == corrupt_content
    # No backup created
    baks = list(tmp_path.glob("corrupt.json.bak.*"))
    assert len(baks) == 0


def test_detect_clients(monkeypatch, tmp_path):
    # Fake which
    which_map = {"claude": "/bin/claude", "gemini": None, "codex": "/bin/codex"}
    fake_which = lambda cmd: which_map.get(cmd)

    # Fake home dirs
    fake_home = tmp_path / "home"
    cursor_dir = fake_home / ".cursor"
    cursor_dir.mkdir(parents=True)
    (cursor_dir / "mcp.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    detected = setup.detect_clients(env={}, path_which=fake_which)
    assert detected["cli"]["claude"] == "/bin/claude"
    assert detected["cli"]["codex"] == "/bin/codex"
    assert detected["cli"]["gemini"] is None
    assert detected["json"]["cursor"]["found"] is True
    assert detected["json"]["windsurf"]["found"] is False
