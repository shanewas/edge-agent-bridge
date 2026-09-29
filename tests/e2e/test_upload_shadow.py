import time

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _nav(client, pages):
    assert client("nav", {"url": pages + "/shadow-upload.html"})["success"]


def test_upload_shadow_input_by_label(client, tmp_path):
    f = tmp_path / "shadow.txt"
    f.write_text("hi", encoding="utf-8")
    r = client("upload", {"target": "Shadow choose", "files": [str(f)]})
    assert r["success"], r
    time.sleep(0.3)
    assert client("eval", {"code": "document.getElementById('shadow-name').textContent"})["result"] == "shadow.txt"


def test_upload_plupload_style_hidden_input(client, tmp_path):
    f = tmp_path / "plup.txt"
    f.write_text("hi", encoding="utf-8")
    r = client("upload", {"target": "Plupload style", "files": [str(f)]})
    assert r["success"], r
    time.sleep(0.3)
    assert client("eval", {"code": "document.getElementById('plup-name').textContent"})["result"] == "plup.txt"
