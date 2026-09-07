import re

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _nav(client, pages):
    assert client("nav", {"url": pages + "/form.html"})["success"]


def test_snapshot_lists_roles_names_values(client):
    r = client("snapshot")
    assert r["success"], r
    t = r["text"]
    assert t.startswith('page "Form fixture" url=')
    assert re.search(r'^- textbox "Username" \[e\d+\] value=""', t, re.M), t
    assert re.search(r'^- textbox "Password" \[e\d+\] type=password value=""', t, re.M), t
    assert re.search(r'^- checkbox "Remember me" \[e\d+\] checked', t, re.M), t
    assert re.search(r'^- combobox "Language" \[e\d+\] value="English" options=3', t, re.M), t
    assert re.search(r'^- file "Choose file" \[e\d+\] hidden', t, re.M), t
    assert re.search(r'^- heading "Sign in" level=1', t, re.M), t
    assert re.search(r'^- link "Forgot password\?" \[e\d+\] href=/reset', t, re.M), t
    assert "Hidden button" not in t and "Aria hidden" not in t
    assert r["refs"] >= 10


def test_table_rows_with_buttons_get_refs(client):
    t = client("snapshot")["text"]
    assert re.search(r'^- table "', t, re.M), t
    assert re.search(r'^  - row "12080 spec.pdf Open" \[e\d+\]', t, re.M), t
    assert re.search(r'^    - button "Open" \[e\d+\]', t, re.M), t


def test_full_mode_adds_text(client):
    assert "Static paragraph" not in client("snapshot")["text"]
    assert 'text "Static paragraph' in client("snapshot", {"mode": "full"})["text"]


def test_refs_restart_per_snapshot_and_go_stale_on_nav(client, pages):
    a = client("snapshot")["text"]
    b = client("snapshot")["text"]
    assert a == b
    client("nav", {"url": pages + "/blank.html"})
    r = client("click", {"ref": "e1", "timeout": 500})
    assert r["success"] is False and r["code"] == "stale_snapshot", r


def test_elements_returns_coordinates_and_refs(client):
    r = client("elements")
    assert r["success"], r
    els = r["elements"]
    assert any(e["ref"] and e["x"] > 0 and e["w"] > 0 for e in els)
    filtered = client("elements", {"filter": "open"})["elements"]
    assert filtered and all("open" in (e["name"] or "").lower() or "open" in (e["id"] or "").lower() for e in filtered)
