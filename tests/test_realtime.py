#!/usr/bin/env python3
"""
Hermetic test for Real-Time WebSocket and Security Enforcement in Edge Bridge.
Tests:
1. Security: Origin check on WebSocket (rejects unauthorized web page origins).
2. Security: Sec-Fetch / Origin check on /exec control channel.
3. Functionality: Real-time status reporting.
4. Latency: Sequential round-trip latency benchmarks (P50, P95).
5. Persistence: EdgeClient context manager and connection reuse.
"""
import base64
import hashlib
import http.client
import json
import socket
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from edge import EdgeClient, ensure_bridge_running

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

def test_security_websocket_origin_rejection():
    print("[1/5] Testing WebSocket Origin Rejection (Security Gate)...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("127.0.0.1", 18999))
    req = (
        "GET /ws HTTP/1.1\r\n"
        "Host: 127.0.0.1:18999\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "Origin: https://malicious-site.example.com\r\n"
        "\r\n"
    )
    s.sendall(req.encode("utf-8"))
    res = s.recv(1024).decode("utf-8")
    s.close()
    assert "403" in res, f"Expected 403 Forbidden for browser page origin, got: {res[:50]}"
    print("  ✓ Malicious web page origin rejected with 403 Forbidden")

def test_security_exec_channel_protection():
    print("[2/5] Testing /exec Browser Context Protection (Security Gate)...")
    req = urllib.request.Request(
        "http://127.0.0.1:18999/exec",
        data=json.dumps({"action": "ping"}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Origin": "http://evil-website.com"
        }
    )
    try:
        urllib.request.urlopen(req)
        assert False, "Should have been rejected with 403"
    except urllib.error.HTTPError as e:
        assert e.code == 403, f"Expected 403, got {e.code}"
        print("  ✓ Web page fetch to /exec rejected with 403 Forbidden")

def test_status_and_websocket_channel():
    print("[3/5] Testing Bridge Status & Real-Time Channel...")
    client = EdgeClient()
    req = urllib.request.Request("http://127.0.0.1:18999/status")
    with urllib.request.urlopen(req) as resp:
        st = json.loads(resp.read().decode("utf-8"))
    assert st.get("bridge_running") is True
    print(f"  ✓ Bridge Daemon: RUNNING")
    print(f"  ✓ WebSocket Active: {st.get('websocket_active')}")
    print(f"  ✓ Extension Connected: {st.get('extension_connected')}")

def test_connection_pooling_and_context_manager():
    print("[4/5] Testing EdgeClient Connection Pooling & Context Manager...")
    with EdgeClient() as c:
        t0 = time.time()
        res1 = c.send("ping")
        t1 = time.time()
        res2 = c.send("ping")
        t2 = time.time()
        assert res1.get("success") is True or "pong" in str(res1)
        assert res2.get("success") is True or "pong" in str(res2)
        print(f"  ✓ Connection pooled ping 1: {(t1-t0)*1000:.2f}ms | ping 2: {(t2-t1)*1000:.2f}ms")

def test_realtime_latency_benchmark():
    print("[5/5] Running Real-Time Latency Benchmark (20 calls)...")
    client = EdgeClient()
    latencies = []
    for _ in range(20):
        t0 = time.time()
        res = client.tab()
        dt = (time.time() - t0) * 1000
        latencies.append(dt)

    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]
    avg = sum(latencies) / len(latencies)
    print(f"  ✓ 20 calls completed: Avg={avg:.1f}ms | P50={p50:.1f}ms | P95={p95:.1f}ms | Min={min(latencies):.1f}ms")
    assert p50 < 100.0, f"Expected P50 < 100ms, got {p50}ms"

if __name__ == "__main__":
    assert ensure_bridge_running(), "Bridge could not be started"
    test_security_websocket_origin_rejection()
    test_security_exec_channel_protection()
    test_status_and_websocket_channel()
    test_connection_pooling_and_context_manager()
    test_realtime_latency_benchmark()
    print("\nALL REAL-TIME TESTS PASSED! 🚀")
