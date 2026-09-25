"""Tests for edge-bridge doctor, logs, and MCP registration status."""
import json
import time
from tests.fake_extension import FakeExtension
from tests.support import free_port
from tests.support import run_cli


def _tabs_handler(action, params):
    if action == "tabs":
        return {"success": True, "tabs": [{"id": 1, "title": "T", "url": "http://x/", "active": True}]}
    return {"success": True}


def test_doctor_healthy_tree(daemon):
    ext = FakeExtension(daemon.port, handler=_tabs_handler).connect().run()
    time.sleep(0.3)
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["doctor"], env=env)
    assert code == 0, out
    assert "FAIL" not in out
    for name in ("daemon", "token", "extension", "versions", "tabs", "pairing", "pid", "mcp"):
        assert f"[ok  ] {name}:" in out
    ext.close()


def test_doctor_json_shape_hides_token(daemon):
    ext = FakeExtension(daemon.port, handler=_tabs_handler).connect().run()
    time.sleep(0.3)
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["--json", "doctor"], env=env)
    assert code == 0, out
    body = json.loads(out)
    assert body["success"] is True
    assert [c["name"] for c in body["checks"]] == [
        "daemon", "token", "extension", "versions", "tabs", "pairing", "pid", "mcp"]
    token = (daemon.home / "token").read_text(encoding="utf-8").strip()
    assert token not in out
    ext.close()


def test_doctor_daemon_down(tmp_path):
    port = free_port()
    home = tmp_path / "empty_home"
    home.mkdir()
    env = {"EDGE_BRIDGE_HOME": str(home), "EDGE_BRIDGE_PORT": str(port)}
    code, out, err = run_cli(["--json", "doctor"], env=env)
    assert code == 1
    body = json.loads(out)
    assert body["success"] is False
    by_name = {c["name"]: c for c in body["checks"]}
    assert by_name["daemon"]["ok"] is False
    assert "edge-bridge daemon start" in by_name["daemon"]["fix"]
    assert by_name["token"]["ok"] is False
    code, out, err = run_cli(["doctor"], env=env)
    assert code == 1 and "[FAIL] daemon:" in out


def test_doctor_stale_pid(tmp_path):
    port = free_port()
    home = tmp_path / "stale_home"
    home.mkdir()
    (home / "bridge.pid").write_text("99999999", encoding="utf-8")
    env = {"EDGE_BRIDGE_HOME": str(home), "EDGE_BRIDGE_PORT": str(port)}
    code, out, err = run_cli(["--json", "doctor"], env=env)
    assert code == 1
    by_name = {c["name"]: c for c in json.loads(out)["checks"]}
    assert by_name["pid"]["ok"] is False
    assert "stale pid file" in by_name["pid"]["detail"]
    assert "edge-bridge daemon restart" in by_name["pid"]["fix"]


def test_doctor_outdated_extension(daemon):
    ext = FakeExtension(daemon.port, version="1.0.0", handler=_tabs_handler).connect().run()
    time.sleep(0.3)
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["doctor"], env=env)
    assert code == 1
    assert "[FAIL] versions:" in out
    assert "microsoftedge.microsoft.com" in out
    ext.close()


def test_doctor_no_extension(daemon):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["doctor"], env=env)
    assert code == 1
    assert "[FAIL] extension:" in out


def test_logs_tail_and_json(daemon, fake_ext):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    run_cli(["ping"], env=env)
    code, out, err = run_cli(["logs", "--tail", "5"], env=env)
    assert code == 0, err
    assert len(out.splitlines()) >= 1
    code, out, err = run_cli(["--json", "logs", "--tail", "5"], env=env)
    assert code == 0
    body = json.loads(out)
    assert body["success"] is True and isinstance(body["lines"], list)


def test_logs_missing(tmp_path):
    port = free_port()
    home = tmp_path / "nolog_home"
    home.mkdir()
    env = {"EDGE_BRIDGE_HOME": str(home), "EDGE_BRIDGE_PORT": str(port)}
    code, out, err = run_cli(["--json", "logs"], env=env)
    assert code == 1
    assert json.loads(out)["code"] == "no_log"


def test_registration_status_reads_json_configs(tmp_path):
    from edge_agent_bridge.setup import registration_status
    cursor_cfg = tmp_path / "cursor-mcp.json"
    cursor_cfg.write_text(json.dumps({"mcpServers": {"edge": {"command": "edge-bridge", "args": ["mcp"]}}}),
                          encoding="utf-8")
    broken = tmp_path / "vscode-mcp.json"
    broken.write_text("{oops", encoding="utf-8")
    detected = {
        "cli": {"claude": "/usr/bin/claude", "gemini": None},
        "json": {
            "cursor": {"path": cursor_cfg, "found": True},
            "vscode": {"path": broken, "found": True},
            "windsurf": {"path": tmp_path / "nope.json", "found": False},
        },
    }
    assert registration_status(detected) == {
        "claude": "detected", "gemini": "absent", "cursor": "registered",
        "vscode": "detected", "windsurf": "absent"}
