"""Tests for history_search / history_delete (param building + CLI parsing)."""
import json
import os
import subprocess
import sys
from pathlib import Path

from edge_agent_bridge.client import Edge
from tests.fake_extension import FakeExtension

ROOT = Path(__file__).resolve().parents[1]


def run_cli(args, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    cmd = [sys.executable, "-u", "-m", "edge_agent_bridge.cli"] + args
    res = subprocess.run(cmd, cwd=ROOT, env=e, capture_output=True, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def _recording_edge():
    seen = {}
    edge = Edge(pin=False, auto_start=False)

    def fake_send(action, params=None, timeout=None):
        seen["action"] = action
        seen["params"] = params
        return {"success": True}

    edge.send = fake_send
    return edge, seen


def test_history_search_param_building():
    edge, seen = _recording_edge()
    edge.history_search("example", max_results=5)
    assert seen["action"] == "history_search"
    assert seen["params"] == {"text": "example", "maxResults": 5}


def test_history_search_defaults():
    edge, seen = _recording_edge()
    edge.history_search()
    assert seen["action"] == "history_search"
    assert seen["params"] == {"text": "", "maxResults": 20}


def test_history_search_time_bounds():
    edge, seen = _recording_edge()
    edge.history_search("x", start_time=1000.0, end_time=2000.0)
    assert seen["params"] == {"text": "x", "maxResults": 20, "startTime": 1000.0, "endTime": 2000.0}


def test_history_delete_param_building():
    edge, seen = _recording_edge()
    edge.history_delete("http://example.com/")
    assert seen["action"] == "history_delete"
    assert seen["params"] == {"url": "http://example.com/"}


def test_cli_history_search_sends_params(daemon):
    seen = []

    def handler(action, params):
        seen.append((action, dict(params)))
        return {"success": True, "count": 0, "items": []}

    ext = FakeExtension(daemon.port, handler=handler).connect().run()
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["--json", "history", "search", "example", "--max-results", "5"], env=env)
    assert code == 0, err
    assert json.loads(out)["success"] is True
    searches = [p for a, p in seen if a == "history_search"]
    assert searches, seen
    assert searches[-1].get("text") == "example"
    assert searches[-1].get("maxResults") == 5
    ext.close()


def test_cli_history_search_time_bounds(daemon):
    seen = []

    def handler(action, params):
        seen.append((action, dict(params)))
        return {"success": True, "count": 0, "items": []}

    ext = FakeExtension(daemon.port, handler=handler).connect().run()
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["--json", "history", "search", "x", "--start-time", "1000", "--end-time", "2000"], env=env)
    assert code == 0, err
    searches = [p for a, p in seen if a == "history_search"]
    assert searches, seen
    assert searches[-1].get("startTime") == 1000.0
    assert searches[-1].get("endTime") == 2000.0
    ext.close()


def test_cli_history_delete_sends_url(daemon):
    seen = []

    def handler(action, params):
        seen.append((action, dict(params)))
        return {"success": True, "url": params.get("url")}

    ext = FakeExtension(daemon.port, handler=handler).connect().run()
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["--json", "history", "delete", "http://example.com/"], env=env)
    assert code == 0, err
    assert json.loads(out)["success"] is True
    deletes = [p for a, p in seen if a == "history_delete"]
    assert deletes, seen
    assert deletes[-1].get("url") == "http://example.com/"
    ext.close()


def test_cli_history_delete_without_url_exits_3(daemon):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["history", "delete"], env=env)
    assert code == 3
