"""Tests for history_search / history_delete (param building + CLI parsing)."""
import json
from tests.fake_extension import FakeExtension
from tests.support import recording_edge, run_cli


def test_history_search_param_building():
    edge, seen = recording_edge()
    edge.history_search("example", max_results=5)
    assert seen["action"] == "history_search"
    assert seen["params"] == {"text": "example", "maxResults": 5}


def test_history_search_defaults():
    edge, seen = recording_edge()
    edge.history_search()
    assert seen["action"] == "history_search"
    assert seen["params"] == {"text": "", "maxResults": 20}


def test_history_search_time_bounds():
    edge, seen = recording_edge()
    edge.history_search("x", start_time=1000.0, end_time=2000.0)
    assert seen["params"] == {"text": "x", "maxResults": 20, "startTime": 1000.0, "endTime": 2000.0}


def test_history_delete_param_building():
    edge, seen = recording_edge()
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
