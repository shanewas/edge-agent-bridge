#!/usr/bin/env python3
"""
Antigravity Edge Bridge Daemon.
Runs locally on 127.0.0.1:18999.
Bridges commands between Antigravity agent and Microsoft Edge extension.
"""
import base64
import hashlib
import http.server
import json
import queue
import struct
import threading
import time
import traceback
import uuid
from pathlib import Path

PORT = 18999
HOST = "127.0.0.1"

MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_EXEC_TIMEOUT = 120
POLL_WAIT_SECONDS = 15.0

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# In-memory command & response queues
command_queue = queue.Queue()
pending_responses = {}      # cmd_id -> threading.Event
response_data = {}          # cmd_id -> response_json
abandoned_commands = set()  # cmd_ids whose /exec caller already gave up
state_lock = threading.Lock()
last_extension_ping = 0

class WebSocketConnection:
    def __init__(self, sock):
        self.sock = sock
        self.closed = False
        self._write_lock = threading.Lock()

    def send_frame(self, opcode: int, data: bytes) -> bool:
        if self.closed:
            return False
        length = len(data)
        header = bytearray([0x80 | (opcode & 0x0F)])
        if length < 126:
            header.append(length)
        elif length <= 0xFFFF:
            header.append(126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", length))
        payload = bytes(header) + data
        with self._write_lock:
            try:
                self.sock.sendall(payload)
                return True
            except Exception:
                self.closed = True
                return False

    def send_text(self, text: str) -> bool:
        return self.send_frame(1, text.encode("utf-8"))

    def send_ping(self, data: bytes = b"") -> bool:
        return self.send_frame(9, data)

    def send_pong(self, data: bytes = b"") -> bool:
        return self.send_frame(10, data)

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.send_frame(8, b"")
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass

active_extension_ws = None
ws_lock = threading.Lock()

class BridgeRequestHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # Without this a half-sent request parks a worker thread on rfile forever.
    timeout = 30

    def log_message(self, format, *args):
        log_file = Path(__file__).parent / "bridge.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}\n")

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _respond(self, code, obj=None, cors=True):
        """Single exit point for every response.

        HTTP/1.1 keep-alive gives the client no way to find the end of a body
        that has no Content-Length, so it blocks until the socket closes and
        the worker thread is never released. Every path must set one.
        """
        body = b"" if obj is None else json.dumps(obj).encode("utf-8")
        self.send_response(code)
        if cors:
            self._send_cors_headers()
        if code != 204:
            if obj is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _is_browser_request(self):
        """A browser always stamps Origin/Sec-Fetch-* on a fetch; urllib never
        does. /exec is the agent's control channel and must stay unreachable
        from page script — otherwise any site the user visits can drive the
        browser through this daemon."""
        return "Origin" in self.headers or any(
            h.lower().startswith("sec-fetch-") for h in self.headers.keys()
        )

    def _mark_seen(self):
        global last_extension_ping
        last_extension_ping = time.time()

    def do_OPTIONS(self):
        self._respond(200)

    def _handle_result_payload(self, data):
        """Process a result dict from either GET ?d=, POST body, or WebSocket frame."""
        if not isinstance(data, dict):
            return
        cmd_id = data.get("id")
        with state_lock:
            event = pending_responses.get(cmd_id)
            if event is not None:
                response_data[cmd_id] = data.get("result", {})
                event.set()

    def _read_exact(self, n: int):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.connection.recv(n - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    def _run_ws_loop(self, ws_conn: WebSocketConnection):
        global active_extension_ws
        try:
            while not ws_conn.closed:
                hdr = self._read_exact(2)
                if not hdr:
                    break
                opcode = hdr[0] & 0x0F
                has_mask = (hdr[1] >> 7) & 1
                length = hdr[1] & 0x7F
                if length == 126:
                    ext = self._read_exact(2)
                    if not ext:
                        break
                    length = struct.unpack("!H", ext)[0]
                elif length == 127:
                    ext = self._read_exact(8)
                    if not ext:
                        break
                    length = struct.unpack("!Q", ext)[0]

                mask = None
                if has_mask:
                    mask = self._read_exact(4)
                    if not mask:
                        break

                payload = self._read_exact(length) if length > 0 else b""
                if payload is None:
                    break

                if has_mask and mask:
                    payload = bytes([b ^ mask[i % 4] for i, b in enumerate(payload)])

                self._mark_seen()

                if opcode == 1:  # Text frame
                    try:
                        data = json.loads(payload.decode("utf-8"))
                        self._handle_result_payload(data)
                    except Exception:
                        pass
                elif opcode == 9:  # Ping
                    ws_conn.send_pong(payload)
                elif opcode == 10:  # Pong
                    pass
                elif opcode == 8:  # Close
                    break
        finally:
            ws_conn.close()
            with ws_lock:
                if active_extension_ws is ws_conn:
                    active_extension_ws = None

    def do_GET(self):
        if self.path.startswith("/ws"):
            upgrade = self.headers.get("Upgrade", "").lower()
            if upgrade != "websocket":
                self._respond(400, {"error": "Expected WebSocket Upgrade"})
                return

            origin = self.headers.get("Origin")
            if origin and not (origin.startswith("chrome-extension://") or origin.startswith("extension://")):
                self.send_response(403)
                self.end_headers()
                return

            key = self.headers.get("Sec-WebSocket-Key")
            if not key:
                self._respond(400, {"error": "Missing Sec-WebSocket-Key"})
                return

            accept_str = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()

            self.send_response(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept_str)
            self.end_headers()

            ws_conn = WebSocketConnection(self.connection)
            global active_extension_ws
            with ws_lock:
                if active_extension_ws:
                    try:
                        active_extension_ws.close()
                    except Exception:
                        pass
                active_extension_ws = ws_conn

            self._mark_seen()
            self.close_connection = True
            self._run_ws_loop(ws_conn)
            return

        elif self.path.startswith("/poll"):
            # Only background service worker is allowed to poll commands
            if "client=sw" not in self.path:
                self._respond(410, {"error": "Content script polling deprecated; client=sw only"})
                return

            # Extension polling for commands
            self._mark_seen()
            deadline = time.monotonic() + POLL_WAIT_SECONDS
            cmd = None
            while cmd is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    candidate = command_queue.get(timeout=remaining)
                except queue.Empty:
                    break
                with state_lock:
                    abandoned = candidate["id"] in abandoned_commands
                    abandoned_commands.discard(candidate["id"])
                # Caller already gave up and was told so; running it now would
                # act on the browser minutes after the CLI reported failure.
                if not abandoned:
                    cmd = candidate

            self._mark_seen()
            if cmd is None:
                self._respond(204)
                return

            try:
                self._respond(200, cmd)
            except OSError:
                # Poller vanished between dequeue and write (tab navigated or
                # closed). The command was never delivered, so put it back
                # instead of silently destroying it.
                command_queue.put(cmd)
                raise

        elif self.path.startswith("/status"):
            # Status check — connected if pinged in last 30s or WebSocket active
            connected = (time.time() - last_extension_ping) < 30
            with ws_lock:
                ws_active = bool(active_extension_ws and not active_extension_ws.closed)
            self._respond(200, {
                "bridge_running": True,
                "extension_connected": connected or ws_active,
                "websocket_active": ws_active,
                "last_seen_seconds_ago": round(time.time() - last_extension_ping, 1) if last_extension_ping > 0 else None,
                "queue_size": command_queue.qsize()
            })

        elif self.path.startswith("/ping"):
            self._mark_seen()
            self._respond(200, {"ok": True, "time": time.time()})

        elif self.path.startswith("/result"):
            # no-cors result delivery via GET ?d=<url-encoded-json>
            self._mark_seen()
            from urllib.parse import urlparse, parse_qs, unquote
            qs = parse_qs(urlparse(self.path).query)
            d = qs.get("d", [None])[0]
            if d:
                try:
                    data = json.loads(unquote(d))
                    self._handle_result_payload(data)
                except Exception:
                    pass
            self._respond(200)

        else:
            self._respond(404, {"success": False, "error": "Unknown path"})


    def _read_body(self):
        raw = self.headers.get("Content-Length", "0")
        try:
            length = int(raw)
        except (TypeError, ValueError):
            return None, "Malformed Content-Length"
        if length < 0 or length > MAX_BODY_BYTES:
            return None, f"Body too large (max {MAX_BODY_BYTES} bytes)"
        if length == 0:
            return {}, None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8")), None
        except Exception as e:
            return None, f"Malformed JSON body: {e}"

    def do_POST(self):
        if self.path.startswith("/result"):
            # Extension posting command execution result
            self._mark_seen()
            data, err = self._read_body()
            if err is None:
                self._handle_result_payload(data)
            self._respond(200, {"ok": True})

        elif self.path.startswith("/exec"):
            # Agent sending command to be executed in Edge. Local processes
            # only — never page script.
            if self._is_browser_request():
                self._respond(403, {"success": False, "error": "/exec is not reachable from browser context"}, cors=False)
                return

            req, err = self._read_body()
            if err is not None:
                self._respond(400, {"success": False, "error": err}, cors=False)
                return

            try:
                timeout = float(req.get("timeout", 15))
            except (TypeError, ValueError):
                timeout = 15
            timeout = max(1.0, min(timeout, MAX_EXEC_TIMEOUT))

            cmd_id = str(uuid.uuid4())
            event = threading.Event()
            with state_lock:
                pending_responses[cmd_id] = event

            cmd_payload = {
                "id": cmd_id,
                "action": req.get("action"),
                "params": req.get("params", {})
            }

            # Attempt instant dispatch via WebSocket if connected
            dispatched_ws = False
            with ws_lock:
                ws = active_extension_ws if (active_extension_ws and not active_extension_ws.closed) else None
                if ws:
                    dispatched_ws = ws.send_text(json.dumps(cmd_payload))

            if not dispatched_ws:
                command_queue.put(cmd_payload)

            finished = event.wait(timeout=timeout)

            with state_lock:
                pending_responses.pop(cmd_id, None)
                res = response_data.pop(cmd_id, None)
                if res is None:
                    # Nothing came back. The command may still be sitting in the
                    # queue; tag it so a later poll discards rather than replays it.
                    abandoned_commands.add(cmd_id)

            if finished and res is not None:
                self._respond(200, res, cors=False)
            else:
                self._respond(504, {
                    "success": False,
                    "error": "Command timed out waiting for Edge extension response"
                }, cors=False)

        else:
            self._respond(404, {"success": False, "error": "Unknown path"})

class BridgeServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # Default True lets a second daemon bind the same live port on Windows and
    # silently split the queue in two. Fail loudly instead.
    allow_reuse_address = False

def run_server():
    log_file = Path(__file__).parent / "bridge.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%X')}] Starting server on {HOST}:{PORT}\n")
    try:
        server = BridgeServer((HOST, PORT), BridgeRequestHandler)
        server.serve_forever()
    except Exception as e:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%X')}] Server crashed: {e}\n")
            traceback.print_exc(file=f)

if __name__ == "__main__":
    run_server()
