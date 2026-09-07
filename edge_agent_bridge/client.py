"""Client library for Edge Agent Bridge.

Provides the Edge class (and EdgeClient alias), session pinning, connection pooling,
and convenience methods for all browser actions.
"""
import base64
import http.client
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import config


def _probe_status(port: int) -> dict | None:
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
        conn.request("GET", "/status")
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return data
    except Exception:
        return None


def ensure_bridge_running(port=None, wait_for_extension=True, timeout=12.0) -> bool:
    """Ensure the bridge daemon is running, spawning it if necessary."""
    p = port or config.port()
    status = _probe_status(p)
    if status and status.get("bridge_running"):
        if not wait_for_extension or status.get("websocket_active"):
            return True

    if status is None:
        cmd = [sys.executable, "-u", "-m", "edge_agent_bridge.bridge", "--port", str(p)]
        env = dict(os.environ)
        if sys.platform == "win32":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP
            if hasattr(subprocess, "DETACHED_PROCESS"):
                flags |= subprocess.DETACHED_PROCESS
            try:
                subprocess.Popen(cmd, env=env, creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            try:
                subprocess.Popen(cmd, env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _probe_status(p)
        if status and status.get("bridge_running"):
            if not wait_for_extension or status.get("websocket_active"):
                return True
        time.sleep(0.1)
    return False


class Edge:
    """Persistent client for Edge Agent Bridge with connection pooling and session pinning."""

    def __init__(
        self,
        tab_id=None,
        port=None,
        timeout=20,
        highlight=True,
        pin=True,
        auto_start=True,
        token=None,
    ):
        self.tab_id = tab_id
        self.port = port or config.port()
        self.timeout = timeout
        self.highlight = highlight
        self.pin = pin
        self.auto_start = auto_start
        self.token = token
        self._conn: http.client.HTTPConnection | None = None

    def _get_connection(self) -> http.client.HTTPConnection:
        if self._conn is None:
            self._conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.timeout)
        return self._conn

    def send(self, action: str, params: dict | None = None, timeout: int | None = None) -> dict:
        """Send an action to the daemon over loopback HTTP POST /exec."""
        if self.auto_start:
            status = _probe_status(self.port)
            if status is None or not status.get("bridge_running"):
                ensure_bridge_running(port=self.port, wait_for_extension=False, timeout=6.0)

        token = self.token or config.read_token()
        if token is None:
            status = _probe_status(self.port)
            if status is None or not status.get("bridge_running"):
                return {
                    "success": False,
                    "code": "daemon_unreachable",
                    "error": f"Cannot reach bridge daemon on 127.0.0.1:{self.port}",
                }
            return {
                "success": False,
                "code": "missing_token",
                "error": f"Missing bridge token at {config.token_path()}",
            }

        p = dict(params or {})
        if self.pin and self.tab_id is not None and "tabId" not in p:
            p["tabId"] = self.tab_id
        if not self.highlight and "highlight" not in p:
            p["highlight"] = False

        t = timeout or self.timeout
        payload = json.dumps({"action": action, "params": p, "timeout": t}).encode("utf-8")
        headers = {
            "Host": f"127.0.0.1:{self.port}",
            "Content-Type": "application/json",
            "Connection": "keep-alive",
            config.TOKEN_HEADER: token,
        }

        data = None
        for attempt in range(2):
            try:
                conn = self._get_connection()
                conn.request("POST", "/exec", body=payload, headers=headers)
                resp = conn.getresponse()
                raw = resp.read().decode("utf-8")
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {"success": False, "code": "bad_response", "error": raw}
                break
            except Exception as e:
                if self._conn:
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                    self._conn = None
                if attempt == 1:
                    return {
                        "success": False,
                        "code": "daemon_unreachable",
                        "error": f"Cannot reach bridge daemon on 127.0.0.1:{self.port}: {e}",
                    }

        if data is None:
            return {
                "success": False,
                "code": "daemon_unreachable",
                "error": f"Cannot reach bridge daemon on 127.0.0.1:{self.port}",
            }

        # Session pinning maintenance
        if self.pin:
            if action in ("tab_close", "close_tab") and p.get("tabId") == self.tab_id:
                self.tab_id = None
            if data.get("code") == "tab_not_found":
                self.tab_id = None
            tab_info = data.get("tab")
            if isinstance(tab_info, dict) and tab_info.get("id") is not None:
                if action in ("tab_switch", "switch_tab", "tab_new") or self.tab_id is None:
                    self.tab_id = tab_info["id"]

        return data

    def tab(self) -> dict:
        return self.send("tab")

    def tabs(self) -> dict:
        return self.send("tabs")

    def tab_switch(self, tab_id=None) -> dict:
        p = {}
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("tab_switch", p)

    def tab_new(self, url="about:blank", group=None, window=False, active=True) -> dict:
        p = {"url": url, "window": window, "active": active}
        if group is not None:
            p["group"] = group
        return self.send("tab_new", p)

    def tab_close(self, tab_id=None) -> dict:
        p = {}
        target_id = tab_id if tab_id is not None else self.tab_id
        if target_id is not None:
            p["tabId"] = target_id
        return self.send("tab_close", p)

    def nav(self, url: str, wait: str = "load", tab_id=None) -> dict:
        p = {"url": url, "wait": wait}
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("nav", p)

    def back(self, wait: str = "load", tab_id=None) -> dict:
        p = {"wait": wait}
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("back", p)

    def forward(self, wait: str = "load", tab_id=None) -> dict:
        p = {"wait": wait}
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("forward", p)

    def reload(self, wait: str = "load", tab_id=None) -> dict:
        p = {"wait": wait}
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("reload", p)

    def snapshot(self, mode: str = "interactive", frames: bool = True, tab_id=None) -> dict:
        p = {"mode": mode, "frames": frames}
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("snapshot", p)

    def elements(self, filter: str | None = None, tab_id=None) -> dict:
        p = {}
        if filter:
            p["filter"] = filter
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("elements", p)

    def _resolve_target_params(self, target, selector, text, ref, x, y, button, modifiers, tab_id):
        p = {"button": button}
        if ref is not None:
            p["ref"] = ref
        elif selector is not None:
            p["selector"] = selector
        elif text is not None:
            p["text"] = text
        elif target is not None:
            p["target"] = target
        elif x is not None and y is not None:
            p["x"] = x
            p["y"] = y
        if modifiers:
            p["modifiers"] = modifiers
        if tab_id is not None:
            p["tabId"] = tab_id
        return p

    def click(self, target=None, selector=None, text=None, ref=None, x=None, y=None, button="left", modifiers=None, tab_id=None) -> dict:
        p = self._resolve_target_params(target, selector, text, ref, x, y, button, modifiers, tab_id)
        return self.send("click", p)

    def dblclick(self, target=None, selector=None, text=None, ref=None, x=None, y=None, button="left", modifiers=None, tab_id=None) -> dict:
        p = self._resolve_target_params(target, selector, text, ref, x, y, button, modifiers, tab_id)
        return self.send("dblclick", p)

    def rightclick(self, target=None, selector=None, text=None, ref=None, x=None, y=None, tab_id=None) -> dict:
        p = self._resolve_target_params(target, selector, text, ref, x, y, "right", None, tab_id)
        return self.send("rightclick", p)

    def hover(self, target=None, selector=None, text=None, ref=None, x=None, y=None, tab_id=None) -> dict:
        p = self._resolve_target_params(target, selector, text, ref, x, y, "left", None, tab_id)
        return self.send("hover", p)

    def drag(self, from_target, to_target, steps: int = 10, tab_id=None) -> dict:
        p = {"from": from_target, "to": to_target, "steps": steps}
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("drag", p)

    def fill(self, target=None, text: str = "", ref=None, append: bool = False, clear: bool = True, tab_id=None) -> dict:
        p = {"text": text, "append": append, "clear": clear}
        if ref is not None:
            p["ref"] = ref
        elif target is not None:
            p["target"] = target
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("fill", p)

    def type(self, text: str, delay: int = 20, ref=None, target=None, tab_id=None) -> dict:
        p = {"text": text, "delay": delay}
        if ref is not None:
            p["ref"] = ref
        elif target is not None:
            p["target"] = target
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("type", p)

    def key(self, key: str, tab_id=None) -> dict:
        p = {"key": key}
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("key", p)

    def check_radio(self, target=None, selector: str = None, text: str = None, value: str = None, tab_id=None) -> dict:
        """Check a radio button or checkbox by selector, label text, or value attribute."""
        p = {}
        if selector is not None:
            p["selector"] = selector
        elif target is not None:
            p["target"] = target
        if text is not None:
            p["text"] = text
        if value is not None:
            p["value"] = str(value)
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("check_radio", p)

    def select(self, target=None, ref=None, value=None, label=None, tab_id=None) -> dict:
        p = {}
        if ref is not None:
            p["ref"] = ref
        elif target is not None:
            p["target"] = target
        if value is not None:
            p["value"] = value
        if label is not None:
            p["label"] = label
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("select", p)

    def upload(self, target=None, ref=None, files=None, tab_id=None) -> dict:
        file_list = []
        if files:
            if isinstance(files, (list, tuple)):
                file_list = [str(Path(f).resolve()) for f in files]
            else:
                file_list = [str(Path(files).resolve())]
        p = {"files": file_list}
        if ref is not None:
            p["ref"] = ref
        elif target is not None:
            p["target"] = target
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("upload", p)

    def scroll(self, x=None, y=None, ref=None, target=None, tab_id=None) -> dict:
        p = {}
        if x is not None:
            p["x"] = x
        if y is not None:
            p["y"] = y
        if ref is not None:
            p["ref"] = ref
        elif target is not None:
            p["target"] = target
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("scroll", p)

    def wait(self, text=None, selector=None, ref=None, url=None, load=False, idle=False, timeout=5000, tab_id=None) -> dict:
        p = {"timeout": timeout}
        if text:
            p["text"] = text
        elif selector:
            p["selector"] = selector
        elif ref:
            p["ref"] = ref
        elif url:
            p["url"] = url
        elif load:
            p["load"] = True
        elif idle:
            p["idle"] = True
        if tab_id is not None:
            p["tabId"] = tab_id
        call_timeout = (timeout // 1000) + 5 if timeout else None
        return self.send("wait", p, timeout=call_timeout)

    def text(self, target=None, ref=None, tab_id=None) -> dict:
        p = {}
        if ref is not None:
            p["ref"] = ref
        elif target is not None:
            p["target"] = target
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("text", p)

    def eval(self, code: str, tab_id=None) -> dict:
        p = {"code": code}
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("eval", p)

    def screenshot(self, path=None, format: str = "jpeg", quality: int = 80, clip=None, of=None, tab_id=None) -> dict:
        p = {"format": format, "quality": quality}
        if clip is not None:
            p["clip"] = clip
        if of is not None:
            p["of"] = of
        if tab_id is not None:
            p["tabId"] = tab_id
        res = self.send("screenshot", p)
        if path and res.get("success") and res.get("data"):
            data_str = res["data"]
            if "," in data_str:
                data_str = data_str.split(",", 1)[1]
            img_bytes = base64.b64decode(data_str)
            out_p = Path(path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_bytes(img_bytes)
            res["path"] = str(out_p.resolve())
        return res

    def console(self, clear: bool = False, tab_id=None) -> dict:
        p = {"clear": clear}
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("console", p)

    def dialog(self, policy: str = "accept", prompt_text=None, tab_id=None) -> dict:
        p = {"policy": policy}
        if prompt_text is not None:
            p["promptText"] = prompt_text
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("dialog", p)

    def batch(self, steps: list, tab_id=None) -> dict:
        p = {"steps": steps}
        if tab_id is not None:
            p["tabId"] = tab_id
        return self.send("batch", p)

    def status(self) -> dict:
        for attempt in range(2):
            try:
                conn = self._get_connection()
                conn.request("GET", "/status")
                resp = conn.getresponse()
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                data["success"] = bool(data.get("bridge_running"))
                return data
            except Exception as e:
                if self._conn:
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                    self._conn = None
                if attempt == 1:
                    return {
                        "success": False,
                        "code": "daemon_unreachable",
                        "error": f"Cannot reach bridge daemon on 127.0.0.1:{self.port}: {e}",
                    }
        return {
            "success": False,
            "code": "daemon_unreachable",
            "error": f"Cannot reach bridge daemon on 127.0.0.1:{self.port}",
        }

    def close(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


EdgeClient = Edge


def send_cmd(action: str, params: dict | None = None, timeout: int = 20) -> dict:
    with Edge(pin=False, timeout=timeout) as client:
        return client.send(action, params, timeout=timeout)
