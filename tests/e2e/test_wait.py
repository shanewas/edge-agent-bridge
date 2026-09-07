import pytest

pytestmark = pytest.mark.e2e


def test_idle_waits_for_fetch_but_ignores_websocket(client, pages):
    client("console")  # attaches the debugger so the next navigation's requests are tracked
    assert client("nav", {"url": pages + "/slow.html"})["success"]
    early = client("wait", {"idle": True, "timeout": 300})
    assert early["success"] is False and early["code"] == "timeout", early
    assert any("/slow" in u for u in early["inflight"]), early
    r = client("wait", {"idle": True, "timeout": 8000})
    assert r["success"] and r["waited"] >= 900, r
    assert client("eval", {"code": "[document.title, window.__wsOpen === true]"})["result"] == ["Done", True]


def test_wait_selector_url_and_load(client, pages):
    assert client("nav", {"url": pages + "/slow.html"})["success"]
    r = client("wait", {"selector": "[data-done]", "timeout": 8000})
    assert r["success"], r
    r = client("wait", {"url": "/slow\\.html$/"})
    assert r["success"] and r["url"].endswith("/slow.html"), r
    r = client("wait", {"url": "blank.html", "timeout": 300})
    assert r["success"] is False and r["code"] == "timeout", r
    r = client("wait", {"load": True})
    assert r["success"], r


def test_wait_missing_selector_reports_waited(client, pages):
    assert client("nav", {"url": pages + "/blank.html"})["success"]
    r = client("wait", {"selector": "#never", "timeout": 500})
    assert r["success"] is False and r["code"] == "target_not_found" and r["waited"] >= 500, r
