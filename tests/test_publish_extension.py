import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publish_extension  # noqa: E402

UPLOAD_OP = "11111111-1111-1111-1111-111111111111"
PUBLISH_OP = "22222222-2222-2222-2222-222222222222"


class StoreStub:
    """Minimal stand-in for api.addons.microsoftedge.microsoft.com."""

    def __init__(self, upload_states, publish_states, location_style="bare"):
        self.upload_states = list(upload_states)
        self.publish_states = list(publish_states)
        self.location_style = location_style
        self.calls = []
        self.uploaded = b""
        self.notes = None
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _auth_ok(self):
                return (self.headers.get("Authorization") == "ApiKey test-key"
                        and self.headers.get("X-ClientID") == "test-client")

            def _location(self, op):
                if stub.location_style == "url":
                    return f"http://{self.headers['Host']}/v1/products/p1/operations/{op}"
                if stub.location_style == "url_query":
                    return f"http://{self.headers['Host']}/v1/products/p1/operations/{op}?api-version=1.1"
                return op

            def do_POST(self):
                stub.calls.append(("POST", self.path))
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if not self._auth_ok():
                    self.send_response(401)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if self.path.endswith("/submissions/draft/package"):
                    stub.uploaded = body
                    op = UPLOAD_OP
                else:
                    stub.notes = json.loads(body.decode())["notes"]
                    op = PUBLISH_OP
                self.send_response(202)
                self.send_header("Location", self._location(op))
                self.end_headers()

            def do_GET(self):
                stub.calls.append(("GET", self.path))
                queue = stub.upload_states if "/draft/package/operations/" in self.path else stub.publish_states
                state = queue.pop(0) if queue else {"status": "Succeeded"}
                payload = json.dumps(state).encode()
                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

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
    monkeypatch.setenv("EDGE_ADDONS_CLIENT_ID", "test-client")
    monkeypatch.setenv("EDGE_ADDONS_API_KEY", "test-key")
    monkeypatch.setenv("EDGE_ADDONS_PRODUCT_ID", "p1")


def run(stub, package, *extra):
    return publish_extension.main([str(package), "--api-root", stub.root, "--interval", "0", *extra])


def test_upload_then_publish_round_trip(package, creds):
    with StoreStub([{"status": "InProgress"}, {"status": "Succeeded"}], [{"status": "Succeeded"}]) as stub:
        assert run(stub, package, "--notes", "ci") == 0
    assert stub.uploaded == package.read_bytes()
    assert stub.notes == "ci"
    assert ("POST", "/v1/products/p1/submissions/draft/package") in stub.calls
    assert ("POST", "/v1/products/p1/submissions") in stub.calls
    assert (f"/v1/products/p1/submissions/operations/{PUBLISH_OP}") in [p for _, p in stub.calls]


def test_location_header_may_be_a_url(package, creds):
    with StoreStub([{"status": "Succeeded"}], [{"status": "Succeeded"}], location_style="url") as stub:
        assert run(stub, package) == 0
    assert any(p.endswith(f"/operations/{UPLOAD_OP}") for _, p in stub.calls)


def test_location_url_may_carry_a_query(package, creds):
    with StoreStub([{"status": "Succeeded"}], [{"status": "Succeeded"}], location_style="url_query") as stub:
        assert run(stub, package) == 0
    assert any(p.endswith(f"/operations/{UPLOAD_OP}") for _, p in stub.calls)


def test_upload_only_skips_the_submission(package, creds):
    with StoreStub([{"status": "Succeeded"}], []) as stub:
        assert run(stub, package, "--upload-only") == 0
    assert ("POST", "/v1/products/p1/submissions") not in stub.calls


def test_failed_upload_reports_the_store_error(package, creds, capsys):
    states = [{"status": "Failed", "message": "manifest version already published"}]
    with StoreStub(states, []) as stub:
        assert run(stub, package) == 1
    assert "manifest version already published" in capsys.readouterr().err


def test_timeout_while_in_progress(package, creds, capsys):
    with StoreStub([{"status": "InProgress"}] * 5, []) as stub:
        assert run(stub, package, "--timeout", "0") == 1
    assert "still in progress" in capsys.readouterr().err


def test_missing_credentials_are_named(package, monkeypatch, capsys):
    for name in ("EDGE_ADDONS_CLIENT_ID", "EDGE_ADDONS_API_KEY", "EDGE_ADDONS_PRODUCT_ID"):
        monkeypatch.delenv(name, raising=False)
    with StoreStub([], []) as stub:
        assert run(stub, package) == 1
    err = capsys.readouterr().err
    assert "EDGE_ADDONS_API_KEY" in err and "EDGE_ADDONS_PRODUCT_ID" in err


def test_missing_package_exits_two(tmp_path, creds, capsys):
    assert publish_extension.main([str(tmp_path / "nope.zip")]) == 2
    assert "package not found" in capsys.readouterr().err


def test_bad_credentials_surface_the_http_status(package, monkeypatch, capsys):
    monkeypatch.setenv("EDGE_ADDONS_CLIENT_ID", "test-client")
    monkeypatch.setenv("EDGE_ADDONS_API_KEY", "wrong")
    monkeypatch.setenv("EDGE_ADDONS_PRODUCT_ID", "p1")
    with StoreStub([], []) as stub:
        assert run(stub, package) == 1
    assert "401" in capsys.readouterr().err
