import time

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture
def noisy(client, pages):
    client("dialog", {"policy": "accept"})
    client("console", {"clear": True})
    assert client("nav", {"url": pages + "/noisy.html"})["success"]
    time.sleep(0.4)


def test_console_captures_errors_and_clamps(client, noisy):
    entries = client("console")["entries"]
    texts = [(e["level"], e["text"]) for e in entries]
    assert any(l == "error" and "boom" in t for l, t in texts), texts
    assert any(l == "error" and "kaboom" in t for l, t in texts), texts
    long = [t for l, t in texts if t.startswith("long:")]
    assert long and len(long[0]) <= 1001, len(long[0]) if long else None
    assert all("t" in e and "url" in e for e in entries)
    assert client("console", {"clear": True})["entries"]
    assert client("console")["entries"] == []


def test_dialog_accept_dismiss_and_manual(client, noisy):
    r = client("click", {"target": "Confirm"})
    assert r["success"], r
    time.sleep(0.3)
    assert client("eval", {"code": "document.getElementById('confirm-btn').dataset.result"})["result"] == "true"
    assert any(e["level"] == "dialog" and "Sure?" in e["text"] for e in client("console")["entries"])

    assert client("dialog", {"policy": "dismiss"})["policy"] == "dismiss"
    client("click", {"target": "Confirm"})
    time.sleep(0.3)
    assert client("eval", {"code": "document.getElementById('confirm-btn').dataset.result"})["result"] == "false"

    assert client("dialog", {"policy": "manual"})["policy"] == "manual"
    client("click", {"target": "Alert"}, timeout=1)  # the click blocks on the open alert; the daemon times it out
    time.sleep(0.3)
    r = client("eval", {"code": "1"})
    assert r["success"] is False and r["code"] == "dialog_open" and "Hi" in r["error"], r
    r = client("dialog", {"policy": "accept"})
    assert r["success"] and r["open"] is None, r
    time.sleep(0.5)
    assert client("eval", {"code": "document.getElementById('alert-btn').dataset.done"})["result"] == "1"
