from tests.test_ladder import ScriptedEdge


def test_match_true_passthrough():
    e = ScriptedEdge([("fill", {"success": True, "written": "a", "readback": "a", "match": True})])
    assert e.send("fill", {"target": "t", "text": "a"})["match"] is True


def test_mismatch_retries_once_then_write_mismatch():
    e = ScriptedEdge([
        ("type", {"success": True, "written": "Hello", "readback": "Hell", "match": False}),
        ("fill", {"success": True, "written": "Hello", "readback": "Hell!", "match": False}),
    ])
    data = e.send("type", {"target": "t", "text": "Hello"})
    assert data["code"] == "write_mismatch"
    assert data["expected"] == "Hello" and data["readback"] == "Hell!" and data["attempts"] == 2
    assert e.calls[1] == ("fill", {"target": "t", "text": "Hello", "clear": True})


def test_mismatch_retry_success_marks_retried():
    e = ScriptedEdge([
        ("fill", {"success": True, "written": "ab", "readback": "a", "match": False}),
        ("fill", {"success": True, "written": "ab", "readback": "ab", "match": True}),
    ])
    data = e.send("fill", {"target": "t", "text": "b", "append": True})
    assert data["success"] is True and data["retried"] is True
    assert e.calls[1][1]["text"] == "ab" and e.calls[1][1]["clear"] is True


def test_unknown_degrade_warns_once_with_notice(capsys):
    e = ScriptedEdge([
        ("fill", {"success": True}),
        ("fill", {"success": True}),
    ])
    d1 = e.send("fill", {"target": "t", "text": "a"})
    d2 = e.send("fill", {"target": "t", "text": "b"})
    assert d1["match"] == "unknown" and "notice" in d1
    assert d2["match"] == "unknown" and "notice" not in d2
    assert capsys.readouterr().err.count("readback") == 1


def test_click_ignores_missing_readback(capsys):
    e = ScriptedEdge([("click", {"success": True})])
    data = e.send("click", {"ref": "e1"})
    assert "match" not in data
    assert capsys.readouterr().err == ""


def test_unknown_session_remints_once_and_retries(daemon, fake_ext, monkeypatch):
    monkeypatch.setenv("EDGE_BRIDGE_HOME", str(daemon.home))
    from edge_agent_bridge.client import Edge
    edge = Edge(port=daemon.port, auto_start=False, session_token="stale-token")
    data = edge.send("ping")
    assert data["success"] is True
    assert edge.session_token != "stale-token"
    _, st = daemon.exec("session_status", session_token=edge.session_token)
    assert st["success"] is True
    edge.close()
