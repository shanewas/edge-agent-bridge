#!/usr/bin/env python3
"""
Edge Agent Bridge daemon.
Runs locally on 127.0.0.1:18999 (or configured port).
Bridges commands between local agents and the Microsoft Edge extension over WebSocket.
"""
import argparse
import base64
import collections
import hashlib
import hmac
import http.server
import json
import logging
import logging.handlers
import os
import socket
import struct
import sys
import threading
import time
import uuid
from pathlib import Path

from . import __version__, config

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_BODY_BYTES = 16 * 1024 * 1024  # 16 MB
MAX_FRAME_PAYLOAD = 16 * 1024 * 1024  # 16 MB

logger = logging.getLogger("edge_bridge")


def setup_logging(home_dir: Path):
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    log_file = home_dir / "bridge.log"
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    formatter = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class WebSocketConnection:
    def __init__(self, sock: socket.socket):
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

    def close_with_code(self, code: int = 1000, reason: str = ""):
        if not self.closed:
            try:
                payload = struct.pack("!H", code) + reason.encode("utf-8")
                self.send_frame(8, payload)
            except Exception:
                pass
            self.closed = True
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass

    def close(self):
        self.close_with_code(1000)


class HeldCommand:
    def __init__(self, cmd_id: str, payload: dict, event: threading.Event, deadline: float):
        self.id = cmd_id
        self.payload = payload
        self.event = event
        self.deadline = deadline


class BridgeState:
    def __init__(self, port: int, home: Path, token: str, pairing_required: bool = False,
                 heartbeat_sec: float = 20.0, pong_timeout_sec: float = 45.0):
        self.port = port
        self.home = home
        self.token = token
        self.pairing_required = pairing_required
        self.heartbeat_sec = heartbeat_sec
        self.pong_timeout_sec = pong_timeout_sec

        self.lock = threading.RLock()
        self.ext: WebSocketConnection | None = None
        self.ext_version: str | None = None
        self.ext_accepted: bool = False
        self.extension_outdated: bool = False

        self.held: collections.deque[HeldCommand] = collections.deque()
        self.pending: dict[str, threading.Event] = {}
        self.results: dict[str, dict] = {}

        self.last_seen: float = 0.0
        self.last_pong: float = 0.0
        self.last_ping_sent: float = 0.0
        self._grace_timer: threading.Timer | None = None

    def mark_seen(self):
        self.last_seen = time.time()

    def mark_pong(self):
        self.last_pong = time.monotonic()
        self.mark_seen()

    def accept_extension_locked(self):
        self.ext_accepted = True
        if self._grace_timer:
            self._grace_timer.cancel()
            self._grace_timer = None
        self._drain_held_locked()

    def accept_extension(self):
        with self.lock:
            self.accept_extension_locked()

    def _drain_held_locked(self):
        now = time.time()
        while self.held:
            item = self.held.popleft()
            if now < item.deadline and self.ext and not self.ext.closed:
                self.pending[item.id] = item.event
                self.ext.send_text(json.dumps(item.payload))

    def on_ws_closed(self, ws: WebSocketConnection):
        with self.lock:
            if self.ext is ws:
                self.ext = None
                self.ext_accepted = False
                if self._grace_timer:
                    self._grace_timer.cancel()
                    self._grace_timer = None


def _heartbeat_worker(state: BridgeState, stop_event: threading.Event):
    while not stop_event.is_set():
        time.sleep(0.1)
        to_close = None
        with state.lock:
            ws = state.ext
            if ws and not ws.closed:
                now = time.monotonic()
                if state.last_ping_sent > 0 and (now - state.last_pong > state.pong_timeout_sec):
                    logger.warning("Extension pong timeout (%.1fs); closing socket", now - state.last_pong)
                    to_close = ws
                elif now - state.last_ping_sent >= state.heartbeat_sec:
                    state.last_ping_sent = now
                    ws.send_text('{"ping": true}')

        if to_close:
            to_close.close()
            state.on_ws_closed(to_close)


class BridgeRequestHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 30

    def log_message(self, format, *args):
        logger.info("%s %s", self.address_string(), format % args)

    def _respond(self, status: int, data: dict | list | None = None):
        body = json.dumps(data).encode("utf-8") if data is not None else b""
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            if body:
                self.wfile.write(body)
                self.wfile.flush()
        except OSError:
            pass

    def _check_host(self) -> bool:
        host_header = self.headers.get("Host", "")
        port = self.server.state.port
        allowed = {
            f"127.0.0.1:{port}",
            f"localhost:{port}",
            f"[::1]:{port}",
            "127.0.0.1",
            "localhost",
            "[::1]",
        }
        return host_header.lower() in allowed

    def _is_browser_request(self) -> bool:
        if self.headers.get("Origin"):
            return True
        for h in self.headers:
            if h.lower().startswith("sec-fetch-"):
                return True
        return False

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

    def _read_exact(self, n: int) -> bytes | None:
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = self.connection.recv(n - len(buf))
            except (socket.timeout, OSError):
                return None
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    def do_GET(self):
        if not self._check_host():
            self._respond(421, {"success": False, "code": "bad_host", "error": "Invalid host"})
            return

        state = self.server.state

        if self.path.startswith("/status"):
            state.mark_seen()
            with state.lock:
                ext_connected = bool(state.ext and not state.ext.closed)
                ws_active = bool(state.ext and not state.ext.closed and state.ext_accepted)
                ext_ver = state.ext_version
                ext_outdated = state.extension_outdated
                pending_count = len(state.pending) + len(state.held)
                last_seen = state.last_seen

            self._respond(200, {
                "bridge_running": True,
                "daemon_version": __version__,
                "extension_version": ext_ver,
                "extension_outdated": ext_outdated,
                "extension_connected": ext_connected,
                "websocket_active": ws_active,
                "last_seen_seconds_ago": round(time.time() - last_seen, 1) if last_seen > 0 else None,
                "pending": pending_count,
                "pairing_required": state.pairing_required,
            })
            return

        if self.path.startswith("/ws"):
            upgrade = self.headers.get("Upgrade", "").lower()
            conn_hdr = self.headers.get("Connection", "").lower()
            if upgrade != "websocket" or "upgrade" not in conn_hdr:
                self._respond(400, {"success": False, "code": "bad_request", "error": "Expected WebSocket Upgrade"})
                return

            origin = self.headers.get("Origin", "")
            if not origin or not (origin.startswith("chrome-extension://") or origin.startswith("extension://")):
                self._respond(403, {"success": False, "code": "forbidden", "error": "Origin not allowed"})
                return

            key = self.headers.get("Sec-WebSocket-Key")
            if not key:
                self._respond(400, {"success": False, "code": "bad_request", "error": "Missing Sec-WebSocket-Key"})
                return

            accept_str = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()

            self.send_response(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept_str)
            self.end_headers()

            ws_conn = WebSocketConnection(self.connection)
            with state.lock:
                if state.ext:
                    try:
                        state.ext.close()
                    except Exception:
                        pass
                state.ext = ws_conn
                state.ext_version = None
                state.ext_accepted = False
                state.last_pong = time.monotonic()
                state.last_ping_sent = time.monotonic()
                state.mark_seen()

                if not state.pairing_required:
                    def grace_timeout():
                        with state.lock:
                            if state.ext is ws_conn and not state.ext_accepted:
                                state.accept_extension_locked()
                    state._grace_timer = threading.Timer(1.0, grace_timeout)
                    state._grace_timer.daemon = True
                    state._grace_timer.start()

            self.close_connection = True
            self.connection.settimeout(60.0)
            self._run_ws_loop(ws_conn)
            return

        if self.path.startswith("/poll") or self.path.startswith("/result"):
            self._respond(404, {"success": False, "code": "not_found", "error": "/poll and /result are removed in v2; use WebSocket /ws"})
            return

        self._respond(404, {"success": False, "code": "not_found", "error": "Unknown path"})

    def _run_ws_loop(self, ws_conn: WebSocketConnection):
        msg_buffer = bytearray()
        msg_opcode = None
        state = self.server.state

        try:
            while not ws_conn.closed:
                hdr = self._read_exact(2)
                if not hdr:
                    break
                fin = (hdr[0] >> 7) & 1
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

                if length > MAX_FRAME_PAYLOAD:
                    logger.warning("Frame payload %d exceeds 16MB cap; closing 1009", length)
                    ws_conn.close_with_code(1009, "Message too big")
                    break

                payload = self._read_exact(length) if length > 0 else b""
                if payload is None:
                    break

                if has_mask and mask and payload:
                    m = mask * (len(payload) // 4) + mask[:len(payload) % 4]
                    payload = (int.from_bytes(payload, "big") ^ int.from_bytes(m, "big")).to_bytes(len(payload), "big")

                state.mark_seen()

                if opcode == 9:  # Ping
                    ws_conn.send_pong(payload)
                elif opcode == 10:  # Pong
                    state.mark_pong()
                elif opcode == 8:  # Close
                    break
                else:
                    if opcode != 0:
                        msg_opcode = opcode
                        msg_buffer = bytearray(payload)
                    else:
                        msg_buffer.extend(payload)

                    if fin:
                        if msg_opcode == 1:
                            try:
                                data = json.loads(msg_buffer.decode("utf-8"))
                                self._handle_ws_json(data, ws_conn)
                            except Exception as e:
                                logger.debug("Failed to handle WS text: %s", e)
                        msg_buffer = bytearray()
                        msg_opcode = None
        finally:
            ws_conn.close()
            state.on_ws_closed(ws_conn)

    def _handle_ws_json(self, data: dict, ws_conn: WebSocketConnection):
        state = self.server.state
        if not isinstance(data, dict):
            return

        if data.get("pong") is True:
            state.mark_pong()

        if "hello" in data and isinstance(data["hello"], dict):
            hello = data["hello"]
            state.ext_version = hello.get("version")
            if state.pairing_required:
                token = hello.get("token") or ""
                if hmac.compare_digest(token, state.token):
                    state.accept_extension()
                else:
                    logger.warning("Pairing token mismatch from extension hello; closing 4001")
                    ws_conn.close_with_code(4001, "pairing_failed")
                    return
            else:
                state.accept_extension()

        if "id" in data and "result" in data:
            cmd_id = data["id"]
            result = data["result"]
            with state.lock:
                if cmd_id in state.pending:
                    is_v1 = False
                    if state.ext_version is None:
                        is_v1 = True
                    else:
                        try:
                            major = int(state.ext_version.split(".")[0])
                            if major < 2:
                                is_v1 = True
                        except (ValueError, IndexError):
                            is_v1 = True
                    err = result.get("error") if isinstance(result, dict) else ""
                    code = result.get("code") if isinstance(result, dict) else ""
                    if is_v1 and ((isinstance(err, str) and err.startswith("Unknown action")) or code == "unknown_action"):
                        state.extension_outdated = True
                        result = {
                            "success": False,
                            "code": "extension_outdated",
                            "error": f"Extension {state.ext_version or 'older than 2.0.0'} is connected; daemon {__version__} needs extension 2.0.0 or newer. Update it from the Edge Add-ons store, or reload the unpacked extension from {config.extension_dir()}."
                        }
                    state.results[cmd_id] = result
                    ev = state.pending.pop(cmd_id)
                    ev.set()

    def do_POST(self):
        if not self._check_host():
            self._respond(421, {"success": False, "code": "bad_host", "error": "Invalid host"})
            return

        state = self.server.state

        if self.path.startswith("/exec"):
            if self._is_browser_request():
                self._respond(403, {"success": False, "code": "browser_context", "error": "/exec is not reachable from browser context"})
                return

            token_hdr = self.headers.get(config.TOKEN_HEADER)
            if not token_hdr:
                self._respond(401, {"success": False, "code": "missing_token", "error": "X-Bridge-Token header required"})
                return
            if not hmac.compare_digest(token_hdr, state.token):
                self._respond(401, {"success": False, "code": "bad_token", "error": "Invalid token"})
                return

            req, err = self._read_body()
            if err is not None or not isinstance(req, dict):
                self._respond(400, {"success": False, "code": "bad_body", "error": err or "Invalid JSON object"})
                return

            action = req.get("action")
            if not action:
                self._respond(400, {"success": False, "code": "bad_body", "error": "Missing action field"})
                return

            params = req.get("params") or {}
            try:
                timeout = float(req.get("timeout", 20))
            except (TypeError, ValueError):
                timeout = 20.0
            timeout = max(1.0, min(timeout, 120.0))

            cmd_id = str(uuid.uuid4())
            event = threading.Event()
            deadline = time.time() + timeout
            cmd_payload = {
                "id": cmd_id,
                "action": action,
                "params": params
            }

            with state.lock:
                if state.ext and not state.ext.closed and state.ext_accepted:
                    state.pending[cmd_id] = event
                    sent = state.ext.send_text(json.dumps(cmd_payload))
                    if not sent:
                        state.pending.pop(cmd_id, None)
                        held_cmd = HeldCommand(cmd_id, cmd_payload, event, deadline)
                        state.held.append(held_cmd)
                else:
                    held_cmd = HeldCommand(cmd_id, cmd_payload, event, deadline)
                    state.held.append(held_cmd)

            rem = max(0.01, deadline - time.time())
            finished = event.wait(timeout=rem)

            with state.lock:
                if finished:
                    res = state.results.pop(cmd_id, None)
                    if res is not None:
                        self._respond(200, res)
                        return

                for h in list(state.held):
                    if h.id == cmd_id:
                        state.held.remove(h)
                        self._respond(504, {
                            "success": False,
                            "code": "extension_offline",
                            "error": "Edge extension is not connected. Open Edge and check the Edge Agent Bridge popup shows Connected."
                        })
                        return

                state.pending.pop(cmd_id, None)
                self._respond(504, {
                    "success": False,
                    "code": "timeout",
                    "error": "Command timed out waiting for Edge extension response"
                })
            return

        if self.path.startswith("/poll") or self.path.startswith("/result"):
            self._respond(404, {"success": False, "code": "not_found", "error": "/poll and /result are removed in v2; use WebSocket /ws"})
            return

        self._respond(404, {"success": False, "code": "not_found", "error": "Unknown path"})



class BridgeServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, server_address, RequestHandlerClass, state: BridgeState):
        self.state = state
        super().__init__(server_address, RequestHandlerClass)


def run_server(host="127.0.0.1", port=None, home=None, require_pairing=None) -> None:
    if port is None:
        port = config.port()
    if home is None:
        home = config.home()
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)

    if require_pairing is None:
        cfg = config.read_config()
        require_pairing = (cfg.get("pairing") == "1")

    token = config.ensure_token()
    setup_logging(home)

    state = BridgeState(
        port=port,
        home=home,
        token=token,
        pairing_required=require_pairing,
        heartbeat_sec=config.heartbeat_seconds(),
        pong_timeout_sec=config.pong_timeout_seconds(),
    )

    stop_event = threading.Event()
    server = BridgeServer((host, port), BridgeRequestHandler, state=state)

    hb_thread = threading.Thread(target=_heartbeat_worker, args=(state, stop_event), daemon=True)
    hb_thread.start()

    pid_file = config.pid_path()
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    import atexit
    atexit.register(lambda: pid_file.unlink(missing_ok=True))
    logger.info("Starting Edge Agent Bridge daemon v%s on %s:%d (pid %d)", __version__, host, port, os.getpid())

    try:
        server.serve_forever()
    finally:
        stop_event.set()
        try:
            server.server_close()
        except Exception:
            pass
        with state.lock:
            if state.ext:
                try:
                    state.ext.close()
                except Exception:
                    pass
        try:
            pid_file.unlink(missing_ok=True)
        except OSError:
            pass
        logger.info("Daemon stopped")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Edge Agent Bridge daemon")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on")
    parser.add_argument("--require-pairing", action="store_true", help="Require pairing token")
    parser.add_argument("--no-pairing", action="store_true", help="Disable pairing token")
    args = parser.parse_args(argv)

    pairing = None
    if args.require_pairing or args.no_pairing:
        pairing = bool(args.require_pairing)
        cfg = config.read_config()
        cfg["pairing"] = "1" if pairing else "0"
        config.write_config(cfg)

    try:
        run_server(port=args.port, require_pairing=pairing)
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logger.error("Daemon crashed: %s", e, exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
