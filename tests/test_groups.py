"""Tests for group_list / group_move / group_ungroup (param building + CLI parsing)."""
import json
from tests.fake_extension import FakeExtension
from tests.support import recording_edge, run_cli


def test_group_list_param_building():
    edge, seen = recording_edge()
    edge.group_list()
    assert seen["action"] == "group_list"
    assert seen["params"] == {}


def test_group_list_window_id():
    edge, seen = recording_edge()
    edge.group_list(window_id=3)
    assert seen["action"] == "group_list"
    assert seen["params"] == {"windowId": 3}


def test_group_move_param_building():
    edge, seen = recording_edge()
    edge.group_move([1, 2], group_id=7, title="Work", color="blue")
    assert seen["action"] == "group_move"
    assert seen["params"] == {"tabIds": [1, 2], "groupId": 7, "title": "Work", "color": "blue"}


def test_group_move_single_tab_id():
    edge, seen = recording_edge()
    edge.group_move(5)
    assert seen["action"] == "group_move"
    assert seen["params"] == {"tabIds": [5]}


def test_group_ungroup_param_building():
    edge, seen = recording_edge()
    edge.group_ungroup([1, 2])
    assert seen["action"] == "group_ungroup"
    assert seen["params"] == {"tabIds": [1, 2]}


def test_cli_group_list_sends_params(daemon):
    seen = []

    def handler(action, params):
        seen.append((action, dict(params)))
        return {"success": True, "count": 0, "groups": []}

    ext = FakeExtension(daemon.port, handler=handler).connect().run()
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["--json", "group", "list"], env=env)
    assert code == 0, err
    assert json.loads(out)["success"] is True
    lists = [p for a, p in seen if a == "group_list"]
    assert lists, seen
    assert "windowId" not in lists[-1]
    ext.close()


def test_cli_group_list_window_id(daemon):
    seen = []

    def handler(action, params):
        seen.append((action, dict(params)))
        return {"success": True, "count": 0, "groups": []}

    ext = FakeExtension(daemon.port, handler=handler).connect().run()
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["--json", "group", "list", "--window-id", "3"], env=env)
    assert code == 0, err
    lists = [p for a, p in seen if a == "group_list"]
    assert lists, seen
    assert lists[-1].get("windowId") == 3
    ext.close()


def test_cli_group_move_sends_params(daemon):
    seen = []

    def handler(action, params):
        seen.append((action, dict(params)))
        return {"success": True, "groupId": 7, "tabIds": params.get("tabIds")}

    ext = FakeExtension(daemon.port, handler=handler).connect().run()
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(
        ["--json", "group", "move", "1", "2", "--group-id", "7", "--title", "Work", "--color", "blue"],
        env=env,
    )
    assert code == 0, err
    assert json.loads(out)["success"] is True
    moves = [p for a, p in seen if a == "group_move"]
    assert moves, seen
    assert moves[-1].get("tabIds") == [1, 2]
    assert moves[-1].get("groupId") == 7
    assert moves[-1].get("title") == "Work"
    assert moves[-1].get("color") == "blue"
    ext.close()


def test_cli_group_ungroup_sends_params(daemon):
    seen = []

    def handler(action, params):
        seen.append((action, dict(params)))
        return {"success": True, "tabIds": params.get("tabIds")}

    ext = FakeExtension(daemon.port, handler=handler).connect().run()
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["--json", "group", "ungroup", "1", "2"], env=env)
    assert code == 0, err
    assert json.loads(out)["success"] is True
    ungroups = [p for a, p in seen if a == "group_ungroup"]
    assert ungroups, seen
    assert ungroups[-1].get("tabIds") == [1, 2]
    ext.close()


def test_cli_group_move_without_tabs_exits_3(daemon):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["group", "move"], env=env)
    assert code == 3


def test_cli_group_ungroup_without_tabs_exits_3(daemon):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["group", "ungroup"], env=env)
    assert code == 3


def test_cli_group_move_noninteger_tabs_exits_3(daemon):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["group", "move", "abc"], env=env)
    assert code == 3
    assert "integers" in err


def test_cli_group_ungroup_noninteger_tabs_exits_3(daemon):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["group", "ungroup", "1", "xyz"], env=env)
    assert code == 3
    assert "integers" in err


def test_cli_group_move_noninteger_tabs_json(daemon):
    env = {"EDGE_BRIDGE_HOME": str(daemon.home), "EDGE_BRIDGE_PORT": str(daemon.port)}
    code, out, err = run_cli(["--json", "group", "move", "abc"], env=env)
    assert code == 3
    body = json.loads(out)
    assert body["success"] is False
    assert body["code"] == "bad_params"
    assert "integers" in body["error"]
