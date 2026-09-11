"""Tests for edge_agent_bridge.cli."""
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from edge_agent_bridge import config
from tests.fake_extension import FakeExtension
from tests.support import DaemonHandle, free_port

ROOT = Path(__file__).resolve().parents[1]


def run_cli(args, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    cmd = [sys.executable, "-u", "-m", "edge_agent_bridge.cli"] + args
    res = subprocess.run(cmd, cwd=ROOT, env=e, capture_output=True, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def test_cli_json_ping_exits_0(daemon, fake_ext):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["--json", "ping"], env=env)
    assert code == 0
    data = json.loads(out)
    assert data["success"] is True
    assert data["message"] == "pong"


def test_cli_json_tab_not_found_exits_1(daemon):
    def handler(action, params):
        return {"success": False, "code": "tab_not_found", "error": "Tab 999 no longer exists"}

    ext = FakeExtension(daemon.port, handler=handler).connect().run()
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["--json", "tab", "--tab", "999"], env=env)
    assert code == 1
    data = json.loads(out)
    assert data["success"] is False
    assert data["code"] == "tab_not_found"
    ext.close()


def test_cli_unreachable_port_exits_2(monkeypatch, tmp_path):
    port = free_port()
    env = {"EDGE_BRIDGE_HOME": str(tmp_path), "EDGE_BRIDGE_PORT": str(port)}
    code, out, err = run_cli(["--json", "ping"], env=env)
    assert code == 2
    data = json.loads(out)
    assert data["success"] is False
    assert data["code"] in ("daemon_unreachable", "missing_token")


def test_cli_close_without_tab_exits_3(daemon):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["close"], env=env)
    assert code == 3


def test_cli_status_human_contains_extension_and_version(daemon, fake_ext):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["status"], env=env)
    assert code == 0
    assert "Extension:" in out
    assert fake_ext.version in out


def test_cli_screenshot_writes_the_file(daemon, fake_ext, tmp_path):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    out_file = tmp_path / "shot.jpg"
    code, out, err = run_cli(["--json", "screenshot", str(out_file)], env=env)
    assert code == 0, err
    data = json.loads(out)
    assert data["path"] == str(out_file.resolve())
    assert out_file.exists() and out_file.stat().st_size > 0


def test_cli_session_start_status_stop(daemon):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["--json", "session", "start"], env=env)
    assert code == 0
    token = json.loads(out)["sessionToken"]
    code, out, err = run_cli(["--json", "session", "status", "--session", token], env=env)
    assert code == 0 and json.loads(out)["tabClosed"] is False
    code, out, err = run_cli(["--json", "session", "stop", "--session", token], env=env)
    assert code == 0 and json.loads(out)["success"] is True
    code, out, err = run_cli(["--json", "session", "status", "--session", token], env=env)
    assert code == 1 and json.loads(out)["code"] == "unknown_session"


def test_cli_session_env_resolution_and_pin_routing(daemon):
    seen = []

    def handler(action, params):
        seen.append((action, dict(params)))
        tid = params.get("tabId", 5)
        return {"success": True, "tab": {"id": tid, "title": "t", "url": "http://t"}}

    ext = FakeExtension(daemon.port, handler=handler).connect().run()
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    _, out, _ = run_cli(["--json", "session", "start"], env=env)
    token = json.loads(out)["sessionToken"]
    env["EDGE_BRIDGE_SESSION"] = token
    code, out, err = run_cli(["--json", "switch", "5"], env=env)
    assert code == 0
    code, out, err = run_cli(["--json", "click", "Save"], env=env)
    assert code == 0
    clicks = [p for a, p in seen if a == "click"]
    assert clicks and clicks[-1].get("tabId") == 5
    ext.close()


def test_cli_no_fallback_flag_accepted(daemon):
    def handler(action, params):
        return {"success": True, "tab": {"id": 1, "title": "t", "url": "http://t"}}

    ext = FakeExtension(daemon.port, handler=handler).connect().run()
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["--json", "click", "Save", "--no-fallback"], env=env)
    assert code == 0, err
    ext.close()
