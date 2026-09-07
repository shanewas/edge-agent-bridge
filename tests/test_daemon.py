import http.client
import struct
import threading
import time
import pytest
from tests.fake_extension import FakeExtension


def test_status_reports_running(daemon):
    st = daemon.status()
    assert st["bridge_running"] is True


def test_ping_roundtrip_via_fake_extension(daemon, fake_ext):
    code, body = daemon.exec("ping")
    assert code == 200 and body["success"] is True and body["message"] == "pong"


def test_exec_requires_token(daemon, fake_ext):
    assert daemon.exec("ping", token=None)[0] == 401
    code, body = daemon.exec("ping", token="0" * 64)
    assert code == 401 and body["code"] == "bad_token"


def test_exec_rejects_browser_context(daemon, fake_ext):
    code, body = daemon.exec("ping", headers={"Origin": "http://evil.example"})
    assert code == 403 and body["code"] == "browser_context"
    code, body = daemon.exec("ping", headers={"Sec-Fetch-Mode": "cors"})
    assert code == 403 and body["code"] == "browser_context"


def test_bad_host_rejected(daemon):
    code, body = daemon._request("GET", "/status", headers={"Host": "evil.example:80"})
    assert code == 421 and body["code"] == "bad_host"


def test_ws_requires_extension_origin(daemon):
    with pytest.raises(ConnectionError):
        FakeExtension(daemon.port, origin=None).connect()
    with pytest.raises(ConnectionError):
        FakeExtension(daemon.port, origin="https://page.example").connect()


def test_status_fields(daemon, fake_ext):
    st = daemon.status()
    for k in ("bridge_running", "daemon_version", "extension_version", "extension_outdated",
              "extension_connected", "websocket_active", "last_seen_seconds_ago", "pending", "pairing_required"):
        assert k in st
    assert st["extension_version"] == "2.0.0" and st["extension_outdated"] is False and st["websocket_active"] is True


def test_poll_and_result_gone(daemon):
    assert daemon._request("GET", "/poll?client=sw")[0] == 404
    assert daemon._request("POST", "/result", {"id": "x"})[0] == 404


def test_no_cors_headers(daemon):
    c = http.client.HTTPConnection("127.0.0.1", daemon.port, timeout=5)
    c.request("GET", "/status")
    r = c.getresponse()
    r.read()
    c.close()
    assert r.getheader("Access-Control-Allow-Origin") is None


def test_hello_records_version_and_pong_answers_ping(daemon):
    ext = FakeExtension(daemon.port, version="2.3.4").connect().run()
    time.sleep(0.3)
    assert daemon.status()["extension_version"] == "2.3.4"
    ext.close()


def test_heartbeat_ping_sent(daemon, fake_ext, monkeypatch):
    time.sleep(2.5)
    assert any(m.get("ping") for m in fake_ext.received)


def test_no_pong_closes_socket(daemon):
    ext = FakeExtension(daemon.port).connect()          # not run(): never answers pings
    ext.sock.settimeout(8)
    deadline = time.time() + 8
    closed = False
    while time.time() < deadline:
        op, payload = ext._read_frame()
        if op == 8 or op is None:
            closed = True
            break
    assert closed
    assert daemon.status()["websocket_active"] is False


def test_oversized_frame_closes_1009(daemon):
    ext = FakeExtension(daemon.port).connect()
    hdr = bytes([0x81, 0x80 | 127]) + struct.pack("!Q", 17 * 1024 * 1024) + b"\x00\x00\x00\x00"
    ext.sock.sendall(hdr)
    ext.sock.settimeout(5)
    op, payload = ext._read_frame()
    assert op == 8 and struct.unpack("!H", payload[:2])[0] == 1009


def test_held_commands_drain_in_order_after_hello(daemon):
    order = []

    def handler(action, params):
        order.append(params.get("n"))
        return {"success": True}

    results = []

    def call(n):
        results.append(daemon.exec("noop", {"n": n}, timeout=6))

    threads = [threading.Thread(target=call, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
        time.sleep(0.15)   # arrival order 0,1,2 while offline
    time.sleep(0.3)
    ext = FakeExtension(daemon.port, handler=handler).connect().run()
    for t in threads:
        t.join(timeout=10)
    assert order == [0, 1, 2]
    assert all(code == 200 for code, _ in results)
    ext.close()


def test_offline_command_times_out_with_extension_offline(daemon):
    code, body = daemon.exec("ping", timeout=1)
    assert code == 504 and body["code"] == "extension_offline"
    assert daemon.status()["pending"] == 0


def test_grace_drain_without_hello_when_pairing_off(daemon):
    got = []

    def call():
        got.append(daemon.exec("ping", timeout=6))

    t = threading.Thread(target=call)
    t.start()
    time.sleep(0.2)
    ext = FakeExtension(daemon.port, send_hello=False, version="1.1.2").connect().run()
    t.join(timeout=10)
    assert got and got[0][0] == 200
    ext.close()


def test_inflight_timeout_and_late_result_dropped(daemon):
    ext = FakeExtension(daemon.port).connect().run()
    code, body = daemon.exec("sleep", {"ms": 2500}, timeout=1)
    assert code == 504 and body["code"] == "timeout"
    time.sleep(2)                       # late result arrives, nobody waits
    assert daemon.status()["pending"] == 0
    ext.close()


def test_extension_outdated_rewrite(daemon):
    ext = FakeExtension(daemon.port, send_hello=False).connect().run()   # behaves like 1.x
    time.sleep(1.2)
    code, body = daemon.exec("snapshot", timeout=3)
    assert code == 200 and body["code"] == "extension_outdated" and "2.0.0" in body["error"]
    assert daemon.status()["extension_outdated"] is True
    ext.close()
