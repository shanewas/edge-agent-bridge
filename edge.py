#!/usr/bin/env python3
"""
Antigravity Edge CLI Client.
Allows the agent or user to drive Microsoft Edge directly via command line.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BRIDGE_URL = "http://127.0.0.1:18999"

import socket

def _probe_bridge():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        err = s.connect_ex(("127.0.0.1", 18999))
        s.close()
        return err == 0
    except Exception:
        return False

import http.client

def ensure_bridge_running():
    if _probe_bridge():
        return True

    bridge_script = Path(__file__).parent / "bridge.py"
    spawned = False
    if sys.platform == "win32":
        # WMI spawn breaks out of any Job Object (IDE, subshell, CI runner)
        try:
            cmd = f'"{sys.executable}" "{bridge_script}"'
            ps_cmd = f"Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine = '{cmd}'}}"
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
            spawned = (res.returncode == 0)
        except Exception:
            spawned = False

        if not spawned:
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            try:
                subprocess.Popen([sys.executable, str(bridge_script)], creationflags=flags | 0x01000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                subprocess.Popen([sys.executable, str(bridge_script)], creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen([sys.executable, str(bridge_script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Report what actually happened instead of assuming the spawn worked.
    for _ in range(20):
        time.sleep(0.1)
        if _probe_bridge():
            return True
    return False

class EdgeClient:
    """Persistent real-time client for Edge Bridge daemon with connection pooling."""
    def __init__(self, host="127.0.0.1", port=18999, timeout=20):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._conn = None

    def _get_connection(self):
        if self._conn is None:
            self._conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        return self._conn

    def send(self, action: str, params: dict = None, timeout: int = None) -> dict:
        ensure_bridge_running()
        t = timeout or self.timeout
        payload = json.dumps({
            "action": action,
            "params": params or {},
            "timeout": t
        }).encode("utf-8")
        for attempt in range(2):
            try:
                conn = self._get_connection()
                conn.request("POST", "/exec", body=payload, headers={
                    "Content-Type": "application/json",
                    "Connection": "keep-alive"
                })
                resp = conn.getresponse()
                raw = resp.read().decode("utf-8")
                try:
                    return json.loads(raw)
                except Exception:
                    return {"success": False, "error": raw}
            except Exception:
                if self._conn:
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                    self._conn = None
                if attempt == 1:
                    return send_cmd(action, params, timeout=t)
        return {"success": False, "error": "Failed to send command"}

    def tab(self):
        return self.send("get_active_tab")

    def tabs(self):
        return self.send("list_tabs")

    def nav(self, url: str, tab_id: int = None):
        p = {"url": url}
        if tab_id: p["tabId"] = tab_id
        return self.send("nav", p)

    def click(self, target=None, selector=None, text=None, x=None, y=None, button="left", tab_id=None):
        p = {"button": button}
        if x is not None and y is not None:
            p["x"] = x
            p["y"] = y
        elif target:
            p["target"] = target
        elif selector:
            p["selector"] = selector
        elif text:
            p["text"] = text
        if tab_id: p["tabId"] = tab_id
        return self.send("click", p)

    def fill(self, target: str, text: str, append=False, tab_id=None):
        p = {"target": target, "text": text, "append": append}
        if tab_id: p["tabId"] = tab_id
        return self.send("fill", p)

    def snapshot(self, tab_id=None):
        p = {}
        if tab_id: p["tabId"] = tab_id
        return self.send("snapshot", p)

    def elements(self, filter_text=None, tab_id=None):
        p = {}
        if filter_text: p["filter"] = filter_text
        if tab_id: p["tabId"] = tab_id
        return self.send("elements", p)

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

Edge = EdgeClient

def send_cmd(action: str, params: dict = None, timeout: int = 20) -> dict:
    if not ensure_bridge_running():
        return {"success": False, "error": f"Bridge daemon did not start on {BRIDGE_URL}"}
    payload = {
        "action": action,
        "params": params or {},
        "timeout": timeout
    }
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                f"{BRIDGE_URL}/exec",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout + 2) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            try:
                return json.loads(err_body)
            except Exception:
                return {"success": False, "error": f"HTTP {e.code}: {err_body}"}
        except Exception as e:
            if ("10048" in str(e) or "Only one usage" in str(e)) and attempt < 3:
                time.sleep(0.15)
                continue
            return {"success": False, "error": str(e)}

def cmd_status():
    ensure_bridge_running()
    try:
        with urllib.request.urlopen(f"{BRIDGE_URL}/status", timeout=3) as resp:
            st = json.loads(resp.read().decode("utf-8"))
            print("=== Edge Bridge Status ===")
            print(f"Bridge Daemon: {'RUNNING' if st.get('bridge_running') else 'STOPPED'}")
            print(f"Edge Extension Connected: {'YES' if st.get('extension_connected') else 'NO (load extension in edge://extensions)'}")
            print(f"WebSocket Real-Time Channel: {'ACTIVE (<2ms)' if st.get('websocket_active') else 'INACTIVE (HTTP poll fallback)'}")
            if st.get("last_seen_seconds_ago") is not None:
                print(f"Last Extension Ping: {st.get('last_seen_seconds_ago')}s ago")
            return
    except Exception as e:
        print(f"Bridge not responding: {e}")

def cmd_nav(url: str, tab_id: int = None):
    params = {"url": url}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("nav", params)
    if res.get("success"):
        print(f"Navigated to: {res.get('url')} - '{res.get('title')}'")
    else:
        print(f"Failed to navigate: {res.get('error')}")

def cmd_tab():
    res = send_cmd("get_active_tab")
    if res.get("success"):
        tab = res.get("tab", {})
        print(f"Active Tab [{tab.get('id')}]: {tab.get('title')}\nURL: {tab.get('url')}")
    else:
        print(f"Error: {res.get('error')}")

def cmd_tabs():
    res = send_cmd("list_tabs")
    if res.get("success"):
        tabs = res.get("tabs", [])
        print(f"=== Open Tabs ({len(tabs)}) ===")
        for t in tabs:
            act = "*" if t.get("active") else " "
            print(f"{act} [{t.get('id')}] {t.get('title')} ({t.get('url')})")
    else:
        print(f"Error: {res.get('error')}")

def cmd_switch(tab_id: int):
    res = send_cmd("switch_tab", {"tabId": tab_id})
    if res.get("success"):
        print(f"Switched to tab {tab_id}")
    else:
        print(f"Error: {res.get('error')}")

def cmd_click(target: str = None, selector: str = None, text: str = None, x: int = None, y: int = None, button: str = "left", tab_id: int = None):
    t0 = time.time()
    params = {"button": button}
    if x is not None and y is not None:
        params["x"] = x
        params["y"] = y
    elif target:
        params["target"] = target
    else:
        if selector:
            params["selector"] = selector
        if text:
            params["text"] = text
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("click", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        desc = f"at ({params.get('x')}, {params.get('y')})" if "x" in params else f"'{res.get('text') or target or selector or text}'"
        native_flag = " [native CDP]" if res.get("native") else ""
        print(f"Clicked {desc}{native_flag} in {elapsed}ms")
    else:
        print(f"Click failed: {res.get('error')} ({elapsed}ms)")

def cmd_dblclick(target: str = None, selector: str = None, text: str = None, x: int = None, y: int = None, tab_id: int = None):
    t0 = time.time()
    params = {}
    if x is not None and y is not None:
        params["x"] = x
        params["y"] = y
    elif target:
        params["target"] = target
    else:
        if selector:
            params["selector"] = selector
        if text:
            params["text"] = text
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("dblclick", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        desc = f"at ({params.get('x')}, {params.get('y')})" if "x" in params else f"'{res.get('text') or target or selector or text}'"
        native_flag = " [native CDP]" if res.get("native") else ""
        print(f"Double-clicked {desc}{native_flag} in {elapsed}ms")
    else:
        print(f"Double-click failed: {res.get('error')} ({elapsed}ms)")

def cmd_rightclick(target: str = None, selector: str = None, text: str = None, x: int = None, y: int = None, tab_id: int = None):
    t0 = time.time()
    params = {}
    if x is not None and y is not None:
        params["x"] = x
        params["y"] = y
    elif target:
        params["target"] = target
    else:
        if selector:
            params["selector"] = selector
        if text:
            params["text"] = text
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("rightclick", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        desc = f"at ({params.get('x')}, {params.get('y')})" if "x" in params else f"'{res.get('text') or target or selector or text}'"
        native_flag = " [native CDP]" if res.get("native") else ""
        print(f"Right-clicked {desc}{native_flag} in {elapsed}ms")
    else:
        print(f"Right-click failed: {res.get('error')} ({elapsed}ms)")

def cmd_hover(target: str = None, x: int = None, y: int = None, duration: int = None, tab_id: int = None):
    t0 = time.time()
    params = {}
    if x is not None and y is not None:
        params["x"] = x
        params["y"] = y
    elif target:
        params["target"] = target
    if duration:
        params["duration"] = duration
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("hover", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        desc = f"at ({res.get('x')}, {res.get('y')})" if res.get("x") is not None else f"'{target}'"
        tag_str = f" <{res.get('tag')}> '{res.get('text')}'" if res.get("tag") else ""
        native_flag = " [native CDP :hover]" if res.get("native") else ""
        print(f"Hovered {desc}{tag_str}{native_flag} in {elapsed}ms")
    else:
        print(f"Hover failed: {res.get('error')} ({elapsed}ms)")

def cmd_drag(from_target: str = None, to_target: str = None, from_x: int = None, from_y: int = None, to_x: int = None, to_y: int = None, steps: int = 12, tab_id: int = None):
    t0 = time.time()
    params = {"steps": steps}
    if from_x is not None and from_y is not None:
        params["fromX"], params["fromY"] = from_x, from_y
    elif from_target:
        params["from"] = from_target
    if to_x is not None and to_y is not None:
        params["toX"], params["toY"] = to_x, to_y
    elif to_target:
        params["to"] = to_target
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("drag", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        print(f"Dragged from ({res.get('fromX')}, {res.get('fromY')}) to ({res.get('toX')}, {res.get('toY')}) [native CDP] in {elapsed}ms")
    else:
        print(f"Drag failed: {res.get('error')} ({elapsed}ms)")

def cmd_fill(target: str, text: str, append: bool = False, tab_id: int = None):
    t0 = time.time()
    params = {"target": target, "text": text, "clear": not append}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("fill", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        native_flag = " [native CDP]" if res.get("native") else ""
        print(f"Filled '{text}' into '{target}'{native_flag} in {elapsed}ms")
    else:
        print(f"Fill failed: {res.get('error')} ({elapsed}ms)")

def cmd_wait(target: str, timeout: int = 5000, tab_id: int = None):
    t0 = time.time()
    params = {"target": target, "timeout": timeout}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("wait_for", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        print(f"Target '{target}' ready at ({res.get('x')}, {res.get('y')}) in {elapsed}ms")
    else:
        print(f"Wait failed: {res.get('error')} ({elapsed}ms)")

def cmd_key(key: str, tab_id: int = None):
    t0 = time.time()
    params = {"key": key}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("key", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        print(f"Pressed key '{key}' in {elapsed}ms (target: <{res.get('target')}>)")
    else:
        print(f"Key press failed: {res.get('error')} ({elapsed}ms)")

def cmd_scroll(x: int = 0, y: int = 300, tab_id: int = None):
    t0 = time.time()
    params = {"x": x, "y": y}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("scroll", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        print(f"Scrolled by ({x}, {y}) in {elapsed}ms (scroll pos: {res.get('scrollX')}, {res.get('scrollY')})")
    else:
        print(f"Scroll failed: {res.get('error')} ({elapsed}ms)")

def cmd_move(x: int, y: int, tab_id: int = None):
    t0 = time.time()
    params = {"x": x, "y": y}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("move", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        desc = f"<{res.get('tag')}> '{res.get('text')}'" if res.get("tag") else ""
        print(f"Moved cursor to ({x}, {y}) {desc} in {elapsed}ms")
    else:
        print(f"Move failed: {res.get('error')} ({elapsed}ms)")

def cmd_elements(filter_text: str = None, tab_id: int = None):
    t0 = time.time()
    params = {}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("interactive", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        els = res.get("elements", [])
        if filter_text:
            low = filter_text.lower()
            els = [e for e in els if low in e.get("text", "").lower() or low in e.get("id", "").lower()]
        print(f"=== Interactive Elements ({len(els)}) in {elapsed}ms ===")
        for e in els:
            id_str = f" #{e.get('id')}" if e.get("id") else ""
            print(f"  ({e.get('x')}, {e.get('y')}) [{e.get('tag')}]{id_str} '{e.get('text')}'")
    else:
        print(f"Failed to scan elements: {res.get('error')} ({elapsed}ms)")

def cmd_type(selector: str, text: str, append: bool = False, tab_id: int = None):
    t0 = time.time()
    params = {"selector": selector, "text": text, "clear": not append}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("type", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        print(f"Typed '{text}' into <{res.get('tag')} name='{res.get('name')}'> in {elapsed}ms")
    else:
        print(f"Type failed: {res.get('error')} ({elapsed}ms)")

def cmd_snapshot(tab_id: int = None):
    params = {}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("snapshot", params)
    if res.get("success"):
        snap = res.get("snapshot", {})
        print(f"=== Page: {snap.get('title')} ===")
        print(f"URL: {snap.get('url')}")
        headings = snap.get("headings", [])
        if headings:
            print("\nHeadings:", " | ".join(headings[:5]))

        inputs = snap.get("inputs", [])
        if inputs:
            print(f"\n--- Form Inputs ({len(inputs)}) ---")
            for inp in inputs:
                lbl = f" (label='{inp.get('label')}')" if inp.get("label") else ""
                val = f" val='{inp.get('value')}'" if inp.get("value") else ""
                ph = f" ph='{inp.get('placeholder')}'" if inp.get("placeholder") else ""
                print(f"  [{inp.get('type') or inp.get('tag')}] #{inp.get('id')} name='{inp.get('name')}'{val}{ph}{lbl}")

        buttons = snap.get("buttons", [])
        if buttons:
            print(f"\n--- Buttons & Actions ({len(buttons)}) ---")
            for b in buttons:
                id_str = f" #{b.get('id')}" if b.get("id") else ""
                print(f"  [button]{id_str} '{b.get('text')}'")
    else:
        print(f"Snapshot failed: {res.get('error')}")

def cmd_close(tab_id: int = None):
    t0 = time.time()
    params = {}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("close_tab", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        print(f"Closed tab {res.get('closedTabId')} in {elapsed}ms")
    else:
        print(f"Close failed: {res.get('error')} ({elapsed}ms)")

def cmd_open_file(file_id: int, tab_id: int = None):
    t0 = time.time()
    params = {"fileId": file_id}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("open_file", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        print(f"Opened file {file_id} in new tab in {elapsed}ms! Row: {res.get('rowText')}")
    else:
        print(f"Open file failed: {res.get('error')} ({elapsed}ms)")


def cmd_eval(code: str, tab_id: int = None):
    params = {"code": code}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("eval", params)
    if res.get("success"):
        print("Result:", json.dumps(res.get("result"), ensure_ascii=False, indent=2))
    else:
        print(f"Eval error: {res.get('error')}")

def cmd_screenshot(output_file: str = "screenshot.png", tab_id: int = None):
    params = {}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("screenshot", params)
    if res.get("success"):
        data_url = res.get("dataUrl") or ""
        if "," not in data_url or not data_url.startswith("data:image/"):
            print(f"Screenshot failed: unexpected image payload from Edge ({data_url[:40]!r})")
            return
        data = base64.b64decode(data_url.split(",", 1)[1])
        out = Path(output_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"Screenshot saved to {output_file} ({len(data)} bytes)")
    else:
        print(f"Screenshot failed: {res.get('error')}")

def cmd_batch(steps_json: str, tab_id: int = None):
    t0 = time.time()
    try:
        steps = json.loads(steps_json)
    except Exception as e:
        print(f"Invalid JSON for batch steps: {e}")
        return
    params = {"steps": steps}
    if tab_id is not None:
        params["tabId"] = tab_id
    res = send_cmd("batch", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        print(f"Batch completed ({res.get('count')} steps) in {elapsed}ms")
    else:
        print(f"Batch failed at step '{res.get('stoppedAt')}': {res.get('error')} ({elapsed}ms)")

def cmd_login(username: str = None, password: str = None, url: str = None, user_selector: str = None, pass_selector: str = None, tab_id: int = None):
    if not username or not password:
        print("Error: --username and --password are required for login")
        return
    t0 = time.time()
    tab_param = {"tabId": tab_id} if tab_id is not None else {}

    if url:
        print(f"Navigating to {url} ...")
        send_cmd("nav", {"url": url, **tab_param})
        time.sleep(0.8)

    user_sel = user_selector or "input[type='text'], input[name*='user'], input[id*='user'], input[name*='login'], input[id*='login']"
    pass_sel = pass_selector or "input[type='password']"

    print(f"Entering credentials for '{username}'...")
    send_cmd("type", {"selector": user_sel, "text": username, "clear": True, **tab_param})
    send_cmd("type", {"selector": pass_sel, "text": password, "clear": True, **tab_param})

    submit_js = """(() => {
        const form = document.querySelector('form');
        if (form && form.requestSubmit) {
            form.requestSubmit();
            return true;
        }
        const btn = document.querySelector('button[type="submit"], input[type="submit"], .btn-login, #login-btn');
        if (btn) { btn.click(); return true; }
        return false;
    })()"""
    send_cmd("eval", {"code": submit_js, **tab_param})
    time.sleep(1.0)

    after_res = send_cmd("snapshot", tab_param)
    after_snap = after_res.get("snapshot", {}) if after_res.get("success") else {}
    after_url = after_snap.get("url", "")
    elapsed = round((time.time() - t0) * 1000, 1)

    if "login" not in after_url.lower() and after_url:
        print(f"Successfully logged in as '{username}' to {after_snap.get('title')} ({after_url}) in {elapsed}ms")
    else:
        print(f"Login attempted in {elapsed}ms (URL: {after_url})")

def cmd_extension(action: str = "path"):
    ext_dir = Path(__file__).parent / "extension"
    if not ext_dir.exists():
        ext_dir = Path(__file__).parent / "edge_agent_bridge" / "extension"
    abs_path = ext_dir.resolve()
    if action == "open":
        if sys.platform == "win32":
            subprocess.run(["explorer", str(abs_path)])
        print(f"Opened extension folder: {abs_path}")
    else:
        print("=== Microsoft Edge Extension Setup ===")
        print("1. Open Microsoft Edge and navigate to: edge://extensions")
        print("2. Turn ON the 'Developer mode' toggle (bottom left)")
        print("3. Click 'Load unpacked' and select this directory:")
        print(f"   {abs_path}")
        print("4. Verify the extension badge shows Connected.")

def cmd_text(target: str, tab_id: int = None):
    ensure_bridge_running()
    params = {"target": target}
    if tab_id is not None:
        params["tabId"] = tab_id
    t0 = time.time()
    res = send_cmd("text", params)
    elapsed = round((time.time() - t0) * 1000, 1)
    if res.get("success"):
        txt = res.get("text", "")
        print(f"{txt} (in {elapsed}ms)")
    else:
        print(f"Error: {res.get('error', 'Failed to get text')} (in {elapsed}ms)")

class Edge:
    """Low-code native browser automation for Microsoft Edge."""
    def __init__(self, tab_id: int = None):
        self.tab_id = tab_id
        ensure_bridge_running()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def nav(self, url: str) -> dict:
        params = {"url": url}
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        return send_cmd("nav", params)

    def hover(self, target: str = None, x: int = None, y: int = None, duration: int = None) -> dict:
        params = {}
        if x is not None and y is not None:
            params["x"], params["y"] = x, y
        elif target:
            params["target"] = target
        if duration:
            params["duration"] = duration
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        return send_cmd("hover", params)

    def click(self, target: str = None, x: int = None, y: int = None, button: str = "left") -> dict:
        params = {"button": button}
        if x is not None and y is not None:
            params["x"], params["y"] = x, y
        elif target:
            params["target"] = target
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        return send_cmd("click", params)

    def dblclick(self, target: str = None, x: int = None, y: int = None) -> dict:
        params = {}
        if x is not None and y is not None:
            params["x"], params["y"] = x, y
        elif target:
            params["target"] = target
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        return send_cmd("dblclick", params)

    def rightclick(self, target: str = None, x: int = None, y: int = None) -> dict:
        params = {}
        if x is not None and y is not None:
            params["x"], params["y"] = x, y
        elif target:
            params["target"] = target
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        return send_cmd("rightclick", params)

    def drag(self, from_target, to_target, steps: int = 12) -> dict:
        params = {"steps": steps}
        if isinstance(from_target, (list, tuple)) and len(from_target) == 2:
            params["fromX"], params["fromY"] = from_target
        else:
            params["from"] = str(from_target)
        if isinstance(to_target, (list, tuple)) and len(to_target) == 2:
            params["toX"], params["toY"] = to_target
        else:
            params["to"] = str(to_target)
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        return send_cmd("drag", params)

    def fill(self, target: str, text: str, clear: bool = True) -> dict:
        params = {"target": target, "text": text, "clear": clear}
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        return send_cmd("fill", params)

    def text(self, target: str) -> str:
        params = {"target": target}
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        res = send_cmd("text", params)
        return res.get("text", "") if res.get("success") else ""

    def key(self, key_name: str) -> dict:
        params = {"key": key_name}
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        return send_cmd("key", params)

    def scroll(self, x: int = 0, y: int = 300) -> dict:
        params = {"x": x, "y": y}
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        return send_cmd("scroll", params)

    def wait_for(self, target: str, timeout: int = 5000) -> dict:
        params = {"target": target, "timeout": timeout}
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        return send_cmd("wait_for", params)

    def snapshot(self) -> dict:
        params = {}
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        return send_cmd("snapshot", params)

    def elements(self, filter_text: str = None) -> list:
        params = {}
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        res = send_cmd("interactive", params)
        els = res.get("elements", [])
        if filter_text:
            low = filter_text.lower()
            els = [e for e in els if low in e.get("text", "").lower() or low in e.get("id", "").lower()]
        return els

    def eval(self, code: str) -> dict:
        params = {"code": code}
        if self.tab_id is not None:
            params["tabId"] = self.tab_id
        return send_cmd("eval", params)

    def screenshot(self, output_file: str = "screenshot.png") -> str:
        cmd_screenshot(output_file, tab_id=self.tab_id)
        return output_file

def cmd_daemon(action: str):
    action = action or "status"
    if action == "status":
        cmd_status()
    elif action == "start":
        if _probe_bridge():
            print("Daemon already running on 127.0.0.1:18999")
        else:
            ok = ensure_bridge_running()
            print("Daemon started successfully" if ok else "Failed to start daemon")
    elif action == "stop":
        if sys.platform == "win32":
            subprocess.run(
                ["powershell", "-Command", "Get-CimInstance Win32_Process -Filter \"CommandLine like '%bridge.py%'\" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        print("Daemon stopped.")
    elif action == "restart":
        cmd_daemon("stop")
        time.sleep(0.5)
        cmd_daemon("start")

def cmd_repl():
    print("=== Edge Bridge Real-Time Interactive REPL ===")
    print("Type commands (e.g. 'tab', 'click <target>', 'fill <target> <text>', 'snapshot', 'exit')")
    client = EdgeClient()
    while True:
        try:
            line = input("edge> ").strip()
            if not line:
                continue
            if line in ("exit", "quit", "q"):
                break
            parts = line.split(maxsplit=2)
            subcmd = parts[0].lower()
            t0 = time.time()
            if subcmd in ("tab", "tabs", "snapshot"):
                res = getattr(client, subcmd)()
                dt = (time.time() - t0) * 1000
                print(f"[{dt:.1f}ms] {json.dumps(res, ensure_ascii=False)}")
            elif subcmd == "status":
                cmd_status()
            elif subcmd == "click":
                target = parts[1] if len(parts) > 1 else None
                res = client.click(target=target)
                dt = (time.time() - t0) * 1000
                print(f"[{dt:.1f}ms] {json.dumps(res, ensure_ascii=False)}")
            elif subcmd == "fill":
                target = parts[1] if len(parts) > 1 else None
                val = parts[2] if len(parts) > 2 else ""
                res = client.fill(target=target, text=val)
                dt = (time.time() - t0) * 1000
                print(f"[{dt:.1f}ms] {json.dumps(res, ensure_ascii=False)}")
            elif subcmd == "nav":
                url = parts[1] if len(parts) > 1 else ""
                res = client.nav(url)
                dt = (time.time() - t0) * 1000
                print(f"[{dt:.1f}ms] {json.dumps(res, ensure_ascii=False)}")
            elif subcmd == "elements":
                filt = parts[1] if len(parts) > 1 else None
                res = client.elements(filter_text=filt)
                dt = (time.time() - t0) * 1000
                print(f"[{dt:.1f}ms] {len(res.get('elements', []))} elements")
            else:
                extra = json.loads(parts[1]) if len(parts) > 1 else {}
                res = client.send(subcmd, extra)
                dt = (time.time() - t0) * 1000
                print(f"[{dt:.1f}ms] {json.dumps(res, ensure_ascii=False)}")
        except (EOFError, KeyboardInterrupt):
            break
        except Exception as e:
            print(f"Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="Antigravity Edge CLI Driver")
    sub = parser.add_subparsers(dest="subcmd")

    p_daemon = sub.add_parser("daemon", help="Manage background bridge daemon")
    p_daemon.add_argument("action", nargs="?", choices=["status", "start", "stop", "restart"], default="status", help="Daemon action")

    sub.add_parser("repl", help="Start real-time interactive REPL prompt (<2ms per action)")

    sub.add_parser("status", help="Check bridge and extension connection status")
    sub.add_parser("tab", help="Show active tab title and URL")
    sub.add_parser("tabs", help="List all open tabs")

    p_snap = sub.add_parser("snapshot", help="Inspect visible DOM elements")
    p_snap.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_nav = sub.add_parser("nav", help="Navigate tab to URL")
    p_nav.add_argument("url", help="URL to navigate to")
    p_nav.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_switch = sub.add_parser("switch", help="Switch to tab by ID")
    p_switch.add_argument("tab_id", type=int, help="Tab ID")

    p_hover = sub.add_parser("hover", help="Hover element or coordinates (triggers native CSS :hover)")
    p_hover.add_argument("target", nargs="?", default=None, help="Target text, label, placeholder, or selector")
    p_hover.add_argument("--x", type=int, help="X viewport pixel")
    p_hover.add_argument("--y", type=int, help="Y viewport pixel")
    p_hover.add_argument("--duration", "-d", type=int, help="Hold hover for duration (ms)")
    p_hover.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_click = sub.add_parser("click", help="Click an element by target, selector, text, or (x, y) coordinates")
    p_click.add_argument("target", nargs="?", default=None, help="Target text, label, or selector")
    p_click.add_argument("--selector", "-s", help="CSS selector")
    p_click.add_argument("--text", help="Visible text on button or link")
    p_click.add_argument("--x", type=int, help="X coordinate in viewport pixels")
    p_click.add_argument("--y", type=int, help="Y coordinate in viewport pixels")
    p_click.add_argument("--button", "-b", default="left", choices=["left", "right", "middle"], help="Mouse button")
    p_click.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_dblclick = sub.add_parser("dblclick", help="Double-click an element by target or coordinates")
    p_dblclick.add_argument("target", nargs="?", default=None, help="Target text or selector")
    p_dblclick.add_argument("--selector", "-s", help="CSS selector")
    p_dblclick.add_argument("--text", help="Visible text on element")
    p_dblclick.add_argument("--x", type=int, help="X coordinate in viewport pixels")
    p_dblclick.add_argument("--y", type=int, help="Y coordinate in viewport pixels")
    p_dblclick.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_rclick = sub.add_parser("rightclick", help="Right-click an element by target or coordinates")
    p_rclick.add_argument("target", nargs="?", default=None, help="Target text or selector")
    p_rclick.add_argument("--selector", "-s", help="CSS selector")
    p_rclick.add_argument("--text", help="Visible text on element")
    p_rclick.add_argument("--x", type=int, help="X coordinate in viewport pixels")
    p_rclick.add_argument("--y", type=int, help="Y coordinate in viewport pixels")
    p_rclick.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_drag = sub.add_parser("drag", help="Drag from source to target")
    p_drag.add_argument("from_target", nargs="?", default=None, help="Source target name or selector")
    p_drag.add_argument("to_target", nargs="?", default=None, help="Destination target name or selector")
    p_drag.add_argument("--from-x", type=int, help="Source X")
    p_drag.add_argument("--from-y", type=int, help="Source Y")
    p_drag.add_argument("--to-x", type=int, help="Target X")
    p_drag.add_argument("--to-y", type=int, help="Target Y")
    p_drag.add_argument("--steps", type=int, default=12, help="Interpolation steps")
    p_drag.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_fill = sub.add_parser("fill", help="Fill text into input with smart locator and native input events")
    p_fill.add_argument("target", help="Input label, placeholder, name, or selector")
    p_fill.add_argument("text", help="Text to fill")
    p_fill.add_argument("--append", action="store_true", help="Append instead of replace")
    p_fill.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_wait = sub.add_parser("wait", help="Wait for target element to appear in DOM and be visible")
    p_wait.add_argument("target", help="Target text, label, or selector")
    p_wait.add_argument("--timeout", type=int, default=5000, help="Timeout in ms (default: 5000)")
    p_wait.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_key = sub.add_parser("key", help="Press a keyboard key (e.g. Enter, Tab, Escape, ArrowDown)")
    p_key.add_argument("key", help="Key name (e.g. Enter, Tab, Escape)")
    p_key.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_scroll = sub.add_parser("scroll", help="Scroll the page by (x, y) pixels")
    p_scroll.add_argument("--x", type=int, default=0, help="Horizontal scroll pixels")
    p_scroll.add_argument("--y", type=int, default=300, help="Vertical scroll pixels")
    p_scroll.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_type = sub.add_parser("type", help="Type text into an input")
    p_type.add_argument("--selector", "-s", default="", help="CSS selector (optional if active)")
    p_type.add_argument("text", help="Text to type")
    p_type.add_argument("--append", action="store_true", help="Append instead of replace")
    p_type.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_eval = sub.add_parser("eval", help="Evaluate JavaScript in tab")
    p_eval.add_argument("code", help="JavaScript code to evaluate")
    p_eval.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_text = sub.add_parser("text", help="Extract text from an element by smart target")
    p_text.add_argument("target", help="Target text, label, placeholder, or selector")
    p_text.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_shot = sub.add_parser("screenshot", help="Take screenshot of tab")
    p_shot.add_argument("output_path", nargs="?", default=None, help="Output file path (positional)")
    p_shot.add_argument("--output", "-o", default=None, help="Output file path")
    p_shot.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_ext = sub.add_parser("extension", help="Show extension directory path or open in explorer")
    p_ext.add_argument("action", nargs="?", choices=["path", "open"], default="path", help="Action (path or open)")

    p_close = sub.add_parser("close", help="Close a tab")
    p_close.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_batch = sub.add_parser("batch", help="Execute JSON array of actions in a single round-trip")
    p_batch.add_argument("steps", help='JSON array of action objects, e.g. \'[{"action":"click","x":1710,"y":18},{"action":"sleep","ms":50},{"action":"click","x":1710,"y":125}]\'')
    p_batch.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_move = sub.add_parser("move", help="Move visual cursor to (x, y) without clicking")
    p_move.add_argument("--x", type=int, required=True, help="X viewport pixel")
    p_move.add_argument("--y", type=int, required=True, help="Y viewport pixel")
    p_move.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_elem = sub.add_parser("elements", help="List all visible interactive elements with exact center coordinates")
    p_elem.add_argument("filter", nargs="?", default=None, help="Filter by text or ID")
    p_elem.add_argument("--tab", "-t", type=int, help="Target tab ID")

    p_login = sub.add_parser("login", help="Automated form login helper")
    p_login.add_argument("--username", "-u", required=True, help="Username or email")
    p_login.add_argument("--password", "-p", required=True, help="Password")
    p_login.add_argument("--url", default=None, help="Optional login page URL")
    p_login.add_argument("--user-selector", default=None, help="Custom CSS selector for username")
    p_login.add_argument("--pass-selector", default=None, help="Custom CSS selector for password")
    p_login.add_argument("--tab", "-t", type=int, help="Target tab ID")

    sub.add_parser("reload", help="Reload the Edge extension")

    args = parser.parse_args()
    if not args.subcmd:
        parser.print_help()
        return

    if args.subcmd == "status":
        cmd_status()
    elif args.subcmd == "daemon":
        cmd_daemon(args.action)
    elif args.subcmd == "repl":
        cmd_repl()
    elif args.subcmd == "extension":
        cmd_extension(args.action)
    elif args.subcmd == "tab":
        cmd_tab()
    elif args.subcmd == "tabs":
        cmd_tabs()
    elif args.subcmd == "snapshot":
        cmd_snapshot(tab_id=args.tab)
    elif args.subcmd == "close":
        cmd_close(tab_id=args.tab)
    elif args.subcmd == "nav":
        cmd_nav(args.url, tab_id=args.tab)
    elif args.subcmd == "switch":
        cmd_switch(args.tab_id)
    elif args.subcmd == "hover":
        cmd_hover(target=args.target, x=args.x, y=args.y, duration=args.duration, tab_id=args.tab)
    elif args.subcmd == "click":
        cmd_click(target=args.target, selector=args.selector, text=args.text, x=args.x, y=args.y, button=args.button, tab_id=args.tab)
    elif args.subcmd == "dblclick":
        cmd_dblclick(target=args.target, selector=args.selector, text=args.text, x=args.x, y=args.y, tab_id=args.tab)
    elif args.subcmd == "rightclick":
        cmd_rightclick(target=args.target, selector=args.selector, text=args.text, x=args.x, y=args.y, tab_id=args.tab)
    elif args.subcmd == "drag":
        cmd_drag(from_target=args.from_target, to_target=args.to_target, from_x=args.from_x, from_y=args.from_y, to_x=args.to_x, to_y=args.to_y, steps=args.steps, tab_id=args.tab)
    elif args.subcmd == "fill":
        cmd_fill(target=args.target, text=args.text, append=args.append, tab_id=args.tab)
    elif args.subcmd == "wait":
        cmd_wait(target=args.target, timeout=args.timeout, tab_id=args.tab)
    elif args.subcmd == "key":
        cmd_key(args.key, tab_id=args.tab)
    elif args.subcmd == "scroll":
        cmd_scroll(args.x, args.y, tab_id=args.tab)
    elif args.subcmd == "type":
        cmd_type(args.selector, args.text, args.append, tab_id=args.tab)
    elif args.subcmd == "eval":
        cmd_eval(args.code, tab_id=args.tab)
    elif args.subcmd == "text":
        cmd_text(args.target, tab_id=args.tab)
    elif args.subcmd == "screenshot":
        out_path = args.output or args.output_path or "screenshot.png"
        cmd_screenshot(out_path, tab_id=args.tab)
    elif args.subcmd == "batch":
        cmd_batch(args.steps, tab_id=args.tab)
    elif args.subcmd == "move":
        cmd_move(args.x, args.y, tab_id=args.tab)
    elif args.subcmd == "elements":
        cmd_elements(args.filter, tab_id=args.tab)
    elif args.subcmd == "login":
        cmd_login(username=args.username, password=args.password, url=args.url, user_selector=args.user_selector, pass_selector=args.pass_selector, tab_id=args.tab)
    elif args.subcmd == "reload":
        res = send_cmd("reload")
        print("Extension reload:", res.get("message", res.get("error", "sent")))


if __name__ == "__main__":
    main()
