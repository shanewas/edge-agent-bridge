import json
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publish_chrome  # noqa: E402


class StoreStub:
    """Minimal stand-in for chromewebstore.googleapis.com plus the OAuth token endpoint."""

    def __init__(self, states, token_ok=True):
        self.states = list(states)
        self.token_ok = token_ok
        self.calls = []
        self.uploaded = b""
        self.token_form = {}
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                stub.calls.append(("POST", self.path))
                if self.path == "/token":
                    stub.token_form = dict(urllib.parse.parse_qsl(body.decode()))
                    if not stub.token_ok:
                        self._json(400, {"error": "invalid_grant"})
                    else:
                        self._json(200, {"access_token": "at-123", "expires_in": 3599})
                    return
                if self.headers.get("Authorization") != "Bearer at-123":
                    self._json(401, {"error": "unauthorized"})
                    return
                if self.path.endswith(":upload"):
                    stub.uploaded = body
                self._json(200, {"ok": True})

            def do_GET(self):
                stub.calls.append(("GET", self.path))
                if self.headers.get("Authorization") != "Bearer at-123":
                    self._json(401, {"error": "unauthorized"})
                    return
                state = stub.states.pop(0) if stub.states else "SUCCESS"
                self._json(200, {"itemId": "abc", "lastAsyncUploadState": state})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.root = f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def package(tmp_path):
    p = tmp_path / "ext.zip"
    p.write_bytes(b"PK\x05\x06" + b"\0" * 18)
    return p


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("CHROME_CLIENT_ID", "cid")
    monkeypatch.setenv("CHROME_CLIENT_SECRET", "csec")
    monkeypatch.setenv("CHROME_REFRESH_TOKEN", "rtok")
    monkeypatch.setenv("CHROME_PUBLISHER_ID", "pub1")
    monkeypatch.setenv("CHROME_ITEM_ID", "item1")


def run(stub, package, *extra):
    return publish_chrome.main([str(package), "--api-root", stub.root,
                                "--token-url", stub.root + "/token", "--interval", "0", *extra])


def test_upload_then_publish_round_trip(package, creds):
    with StoreStub(["UPLOAD_IN_PROGRESS", "SUCCESS"]) as stub:
        assert run(stub, package) == 0
    assert stub.uploaded == package.read_bytes()
    paths = [p for _, p in stub.calls]
    assert "/upload/v2/publishers/pub1/items/item1:upload" in paths
    assert "/v2/publishers/pub1/items/item1:fetchStatus" in paths
    assert "/v2/publishers/pub1/items/item1:publish" in paths


def test_refresh_token_exchanged_for_bearer(package, creds):
    with StoreStub(["SUCCESS"]) as stub:
        assert run(stub, package) == 0
    assert stub.token_form["grant_type"] == "refresh_token"
    assert stub.token_form["refresh_token"] == "rtok"
    assert stub.token_form["client_id"] == "cid"


def test_upload_only_skips_publish(package, creds):
    with StoreStub(["SUCCESS"]) as stub:
        assert run(stub, package, "--upload-only") == 0
    assert not any(p.endswith(":publish") for _, p in stub.calls)


def test_failed_upload_state_reports_the_body(package, creds, capsys):
    with StoreStub(["FAILURE"]) as stub:
        assert run(stub, package) == 1
    assert "FAILURE" in capsys.readouterr().err


def test_timeout_while_upload_in_progress(package, creds, capsys):
    with StoreStub(["UPLOAD_IN_PROGRESS"] * 5) as stub:
        assert run(stub, package, "--timeout", "0") == 1
    assert "still in progress" in capsys.readouterr().err


def test_bad_refresh_token_surfaces(package, creds, capsys):
    with StoreStub(["SUCCESS"], token_ok=False) as stub:
        assert run(stub, package) == 1
    assert "invalid_grant" in capsys.readouterr().err


def test_missing_credentials_are_named(package, monkeypatch, capsys):
    for n in ("CHROME_CLIENT_ID", "CHROME_CLIENT_SECRET", "CHROME_REFRESH_TOKEN",
              "CHROME_PUBLISHER_ID", "CHROME_ITEM_ID"):
        monkeypatch.delenv(n, raising=False)
    with StoreStub([]) as stub:
        assert run(stub, package) == 1
    err = capsys.readouterr().err
    assert "CHROME_ITEM_ID" in err and "CHROME_REFRESH_TOKEN" in err


def test_missing_package_exits_two(tmp_path, creds, capsys):
    assert publish_chrome.main([str(tmp_path / "nope.zip")]) == 2
    assert "package not found" in capsys.readouterr().err
