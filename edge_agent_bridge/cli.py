#!/usr/bin/env python3
"""
Edge Agent Bridge CLI.
Allows the agent or user to drive Microsoft Edge directly via command line.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import __version__, config
from .client import Edge, EdgeClient, send_cmd, ensure_bridge_running

# Force UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _handle_daemon_cmd(args, port: int) -> int:
    sub = args.daemon_action
    pid_p = config.pid_path()

    if sub == "stop":
        if pid_p.exists():
            try:
                pid = int(pid_p.read_text(encoding="utf-8").strip())
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    os.kill(pid, signal.SIGTERM)
                print(f"Stopped daemon (PID {pid})")
            except Exception as e:
                print(f"Error stopping daemon: {e}")
            finally:
                try:
                    pid_p.unlink(missing_ok=True)
                except Exception:
                    pass
        else:
            print("Daemon PID file not found")
        return 0

    elif sub == "start":
        if getattr(args, "require_pairing", False):
            cfg = config.read_config()
            cfg["pairing"] = "1"
            config.write_config(cfg)
        ok = ensure_bridge_running(port=port, wait_for_extension=False, timeout=5.0)
        if ok:
            print(f"Daemon running on port {port}")
            return 0
        else:
            print(f"Failed to start daemon on port {port}", file=sys.stderr)
            return 2

    elif sub == "restart":
        _handle_daemon_cmd(argparse.Namespace(daemon_action="stop"), port)
        time.sleep(0.5)
        return _handle_daemon_cmd(argparse.Namespace(daemon_action="start", require_pairing=False), port)

    elif sub == "status":
        with Edge(port=port, auto_start=False) as client:
            st = client.status()
        if st.get("bridge_running"):
            pid_file = config.pid_path()
            pid = pid_file.read_text(encoding="utf-8").strip() if pid_file.exists() else "?"
            print(f"Daemon: running on 127.0.0.1:{port} (PID {pid})")
            print(f"Extension: {st.get('extension_version', 'none')} ({'connected' if st.get('websocket_active') else 'disconnected'})")
            return 0
        else:
            print(f"Daemon not running on 127.0.0.1:{port}")
            return 2

    return 3


def _handle_extension_cmd(args) -> int:
    ext_dir = config.extension_dir()
    if args.extension_action == "path":
        print(str(ext_dir))
        return 0
    elif args.extension_action == "open":
        if sys.platform == "win32":
            os.startfile(ext_dir)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(ext_dir)])
        else:
            subprocess.run(["xdg-open", str(ext_dir)])
        return 0
    return 3


def _handle_session_cmd(args, edge: Edge, opt_json: bool) -> int:
    sub = args.session_action
    if sub == "start" and not getattr(args, "new", False) and edge.session_token:
        st = edge._send_once("session_status", {})
        if st.get("success"):
            if opt_json:
                print(json.dumps({"success": True, "sessionToken": edge.session_token, **st}))
            else:
                print(f"sessionToken={edge.session_token} (existing, tab {st.get('tabId')})")
            return 0
    if sub == "start":
        res = edge._send_once("session_start", {})
        if not res.get("success"):
            if opt_json:
                print(json.dumps(res))
            else:
                print(f"Error ({res.get('code')}): {res.get('error')}", file=sys.stderr)
            return 1
        if opt_json:
            print(json.dumps({"success": True, "sessionToken": res["sessionToken"]}))
        else:
            print(f"sessionToken={res['sessionToken']}")
            print(f"export EDGE_BRIDGE_SESSION={res['sessionToken']}")
        return 0
    if not edge.session_token:
        msg = "no session: pass --session TOKEN or set EDGE_BRIDGE_SESSION"
        if opt_json:
            print(json.dumps({"success": False, "code": "no_session", "error": msg}))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        return 3
    res = edge._send_once("session_status" if sub == "status" else "session_stop", {})
    if opt_json:
        print(json.dumps(res))
    else:
        if res.get("success"):
            if sub == "status":
                print(f"Session tab: {res.get('tabId')} (closed: {res.get('tabClosed')})")
            else:
                print("Session stopped")
        else:
            print(f"Error ({res.get('code')}): {res.get('error')}", file=sys.stderr)
    return 0 if res.get("success") else 1


def _run_repl(edge: Edge) -> int:
    print(f"Edge Agent Bridge REPL (port {edge.port}). Type 'help' or action commands, 'exit' to quit.")
    while True:
        try:
            line = input("eab> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("exit", "quit"):
            break
        if line == "help":
            print("Actions: ping, status, tabs, tab, nav <url>, snapshot, click <target>, fill <target> <text>, eval <code>")
            continue
        parts = line.split(maxsplit=1)
        action = parts[0]
        params = {}
        if len(parts) > 1:
            try:
                params = json.loads(parts[1])
            except Exception:
                params = {"target": parts[1]}
        res = edge.send(action, params)
        print(json.dumps(res, indent=2))
    return 0


def main(argv=None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Output raw result as single JSON line")
    common.add_argument("--no-highlight", action="store_true", default=argparse.SUPPRESS, help="Disable visual highlight ring and cursor")
    common.add_argument("--tab", type=int, default=argparse.SUPPRESS, help="Target specific tab ID")
    common.add_argument("--port", type=int, default=argparse.SUPPRESS, help="Bridge port override")
    common.add_argument("--session", default=argparse.SUPPRESS, help="Daemon session token (or EDGE_BRIDGE_SESSION)")
    common.add_argument("--no-fallback", action="store_true", default=argparse.SUPPRESS, help="Disable ref→text→scan→coords fallback ladder")

    parser = argparse.ArgumentParser(
        prog="edge-bridge",
        parents=[common],
        description="Edge Agent Bridge CLI for driving Microsoft Edge.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="cmd", help="Command to run")

    def add_cmd(name, **kwargs):
        kwargs.setdefault("parents", [common])
        return subparsers.add_parser(name, **kwargs)

    # ping
    add_cmd("ping", help="Ping daemon/extension")

    # status
    add_cmd("status", help="Get daemon and extension status")

    # daemon
    p_daemon = add_cmd("daemon", help="Manage daemon process")
    p_daemon.add_argument("daemon_action", choices=["start", "stop", "restart", "status"])
    p_daemon.add_argument("--require-pairing", action="store_true", help="Require pairing token")

    # repl
    add_cmd("repl", help="Interactive REPL session")

    # tabs
    add_cmd("tabs", help="List open tabs")

    # tab
    add_cmd("tab", help="Get active or pinned tab")

    # switch
    p_switch = add_cmd("switch", help="Switch to tab ID")
    p_switch.add_argument("tab_id", type=int)

    # new
    p_new = add_cmd("new", help="Open new tab")
    p_new.add_argument("url", nargs="?", default="about:blank")
    p_new.add_argument("--group", default=None)
    p_new.add_argument("--window", action="store_true")
    p_new.add_argument("--background", action="store_true")

    # close
    add_cmd("close", help="Close tab (requires --tab ID)")

    # session
    p_session = add_cmd("session", help="Manage daemon tab sessions")
    p_session.add_argument("session_action", choices=["start", "status", "stop"])
    p_session.add_argument("--new", action="store_true", help="session start: always mint a fresh token")

    # history
    p_history = add_cmd("history", help="Search or delete browsing history")
    p_history.add_argument("history_action", choices=["search", "delete"])
    p_history.add_argument("query", nargs="?", default="", help="Search text or URL to delete")
    p_history.add_argument("--max-results", type=int, default=20, help="history search: max results (default 20)")
    p_history.add_argument("--start-time", type=float, default=None, help="history search: only items after this time (ms since epoch)")
    p_history.add_argument("--end-time", type=float, default=None, help="history search: only items before this time (ms since epoch)")

    # group
    p_group = add_cmd("group", help="List or manage tab groups")
    p_group.add_argument("group_action", choices=["list", "move", "ungroup"])
    p_group.add_argument("tabs", nargs="*", default=[], help="Tab IDs to move or ungroup")
    p_group.add_argument("--group-id", type=int, default=None, help="group move: existing group ID (omit for a new group)")
    p_group.add_argument("--title", default=None, help="group move: title for the group")
    p_group.add_argument("--color", default=None, help="group move: color (grey, blue, red, yellow, green, pink, purple, cyan, orange)")
    p_group.add_argument("--window-id", type=int, default=None, help="group list: only this window")

    # nav
    p_nav = add_cmd("nav", help="Navigate to URL")
    p_nav.add_argument("url")
    p_nav.add_argument("--no-wait", action="store_true")

    # back / forward / reload
    p_back = add_cmd("back", help="History back")
    p_back.add_argument("--no-wait", action="store_true")
    p_fwd = add_cmd("forward", help="History forward")
    p_fwd.add_argument("--no-wait", action="store_true")
    p_rel = add_cmd("reload", help="Reload page")
    p_rel.add_argument("--no-wait", action="store_true")

    # snapshot
    p_snap = add_cmd("snapshot", help="Take semantic accessibility snapshot")
    p_snap.add_argument("--full", action="store_true", help="Include static text")
    p_snap.add_argument("--no-frames", action="store_true", help="Skip subframes")

    # elements
    p_el = add_cmd("elements", help="List interactive elements with coordinates and refs")
    p_el.add_argument("filter", nargs="?", default=None)

    # click / dblclick / rightclick / hover
    for act in ("click", "dblclick", "rightclick", "hover"):
        p_act = add_cmd(act, help=f"{act.capitalize()} on element")
        p_act.add_argument("target", nargs="?", default=None)
        p_act.add_argument("--x", type=float, default=None)
        p_act.add_argument("--y", type=float, default=None)
        p_act.add_argument("--button", default="left")
        p_act.add_argument("--ref", default=None)

    # drag
    p_drag = add_cmd("drag", help="Drag from one target to another")
    p_drag.add_argument("from_target")
    p_drag.add_argument("to_target")
    p_drag.add_argument("--steps", type=int, default=10)

    # fill
    p_fill = add_cmd("fill", help="Fill input or textarea")
    p_fill.add_argument("target")
    p_fill.add_argument("text")
    p_fill.add_argument("--append", action="store_true")
    p_fill.add_argument("--no-clear", action="store_true")

    # type
    p_type = add_cmd("type", help="Type text character by character")
    p_type.add_argument("text")
    p_type.add_argument("--delay", type=int, default=20)
    p_type.add_argument("--ref", default=None)
    p_type.add_argument("--target", default=None)

    # key
    p_key = add_cmd("key", help="Send keyboard key (e.g. Enter, Tab, Ctrl+A)")
    p_key.add_argument("key")

    # check-radio
    p_chk = add_cmd("check-radio", help="Check a radio button or checkbox")
    p_chk.add_argument("target", nargs="?", default=None, help="Label text, selector, or value")
    p_chk.add_argument("--selector", "-s", default=None)
    p_chk.add_argument("--text", default=None)
    p_chk.add_argument("--value", "-v", default=None)

    # select
    p_sel = add_cmd("select", help="Select option in dropdown")
    p_sel.add_argument("target")
    p_sel.add_argument("--value", default=None)
    p_sel.add_argument("--label", default=None)

    # upload
    p_up = add_cmd("upload", help="Upload files to file input")
    p_up.add_argument("target")
    p_up.add_argument("files", nargs="+")

    # scroll
    p_scroll = add_cmd("scroll", help="Scroll viewport or element")
    p_scroll.add_argument("--x", type=float, default=None)
    p_scroll.add_argument("--y", type=float, default=None)
    p_scroll.add_argument("--ref", default=None)
    p_scroll.add_argument("--target", default=None)

    # wait
    p_wait = add_cmd("wait", help="Wait for condition")
    p_wait.add_argument("--text", default=None)
    p_wait.add_argument("--selector", default=None)
    p_wait.add_argument("--ref", default=None)
    p_wait.add_argument("--url", default=None)
    p_wait.add_argument("--load", action="store_true")
    p_wait.add_argument("--idle", action="store_true")
    p_wait.add_argument("--timeout", type=int, default=5000)

    # text
    p_txt = add_cmd("text", help="Get text content of target")
    p_txt.add_argument("target")

    # eval
    p_eval = add_cmd("eval", help="Evaluate JavaScript expression in tab")
    p_eval.add_argument("code")

    # screenshot
    p_ss = add_cmd("screenshot", help="Capture screenshot")
    p_ss.add_argument("path", nargs="?", default=None)
    p_ss.add_argument("--png", action="store_true")
    p_ss.add_argument("--quality", type=int, default=80)
    p_ss.add_argument("--clip", default=None)
    p_ss.add_argument("--of", default=None)

    # console
    p_con = add_cmd("console", help="Read console logs")
    p_con.add_argument("--clear", action="store_true")

    # dialog
    p_diag = add_cmd("dialog", help="Set dialog policy")
    p_diag.add_argument("policy", choices=["accept", "dismiss", "manual"])
    p_diag.add_argument("--prompt", default=None)

    # batch
    p_batch = add_cmd("batch", help="Execute batch steps")
    p_batch.add_argument("steps")

    # extension
    p_ext = add_cmd("extension", help="Extension paths and options")
    p_ext.add_argument("extension_action", choices=["path", "open"])

    # mcp
    add_cmd("mcp", help="Run MCP stdio server")

    # mcp-config
    p_mcp_cfg = add_cmd("mcp-config", help="Print MCP client configuration")
    p_mcp_cfg.add_argument("--client", required=True, choices=["claude", "cursor", "windsurf", "gemini", "codex", "vscode"])

    # setup
    p_setup = add_cmd("setup", help="Auto-configure detected MCP clients")
    p_setup.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 3

    opt_json = getattr(args, "json", False)
    opt_tab = getattr(args, "tab", None)
    opt_no_highlight = getattr(args, "no_highlight", False)
    opt_port = getattr(args, "port", None)
    opt_session = getattr(args, "session", None) or os.environ.get("EDGE_BRIDGE_SESSION")

    # Special handling: history delete without a URL
    if args.cmd == "history" and args.history_action == "delete" and not args.query:
        if opt_json:
            print(json.dumps({"success": False, "code": "bad_params", "error": "history delete requires a URL"}))
        else:
            print("Error: 'history delete' requires a URL", file=sys.stderr)
        return 3

    # Special handling: group move/ungroup without tab IDs
    if args.cmd == "group" and args.group_action in ("move", "ungroup") and not args.tabs:
        if opt_json:
            print(json.dumps({"success": False, "code": "bad_params", "error": f"group {args.group_action} requires tab IDs"}))
        else:
            print(f"Error: 'group {args.group_action}' requires tab IDs", file=sys.stderr)
        return 3

    # Special handling: group move/ungroup with non-integer tab IDs
    if args.cmd == "group" and args.group_action in ("move", "ungroup") and args.tabs:
        try:
            [int(t) for t in args.tabs]
        except ValueError:
            if opt_json:
                print(json.dumps({"success": False, "code": "bad_params", "error": f"group {args.group_action} tab IDs must be integers"}))
            else:
                print(f"Error: 'group {args.group_action}' tab IDs must be integers", file=sys.stderr)
            return 3

    # Special handling: close without --tab
    if args.cmd == "close" and opt_tab is None:
        if opt_json:
            print(json.dumps({"success": False, "code": "tab_required", "error": "close requires --tab ID"}))
        else:
            print("Error: 'close' requires --tab ID", file=sys.stderr)
        return 3

    port = opt_port or config.port()

    # Route special commands that don't need Edge client
    if args.cmd == "daemon":
        return _handle_daemon_cmd(args, port)
    if args.cmd == "extension":
        return _handle_extension_cmd(args)
    if args.cmd == "mcp":
        from .mcp import main as mcp_main
        return mcp_main()
    if args.cmd == "mcp-config":
        from .setup import mcp_config_cli
        return mcp_config_cli(args.client)
    if args.cmd == "setup":
        from .setup import setup_cli
        return setup_cli(yes=getattr(args, "yes", False))

    edge = Edge(
        tab_id=opt_tab,
        port=port,
        highlight=not opt_no_highlight,
        pin=False,
        auto_start=False,
        session_token=opt_session,
    )

    if args.cmd == "session":
        return _handle_session_cmd(args, edge, opt_json)

    if args.cmd == "repl":
        return _run_repl(edge)

    # Route status
    if args.cmd == "status":
        res = edge.status()
        if opt_json:
            print(json.dumps(res))
        else:
            if res.get("success"):
                print(f"Edge Agent Bridge v{res.get('daemon_version') or __version__}")
                print(f"Daemon: running on 127.0.0.1:{port} (PID {res.get('pid')})")
                print(f"Extension: {res.get('extension_version', 'none')} ({'connected' if res.get('websocket_active') else 'disconnected'})")
            else:
                err_code = res.get("code", "error")
                err_msg = res.get("error", "Action failed")
                print(f"Error ({err_code}): {err_msg}", file=sys.stderr)
        if res.get("success"):
            return 0
        return 2 if res.get("code") in ("daemon_unreachable", "missing_token") else 1

    # Map command to action and params
    action = args.cmd
    params = {}
    if opt_tab is not None:
        params["tabId"] = opt_tab
    if getattr(args, "no_fallback", False):
        params["fallback"] = False

    if action == "ping":
        pass
    elif action == "tabs":
        pass
    elif action == "tab":
        pass
    elif action == "switch":
        action = "tab_switch"
        params["tabId"] = args.tab_id
    elif action == "new":
        action = "tab_new"
        params["url"] = args.url
        params["active"] = not args.background
        params["window"] = args.window
        if args.group:
            params["group"] = args.group
    elif action == "close":
        action = "tab_close"
        params["tabId"] = opt_tab
    elif action == "history":
        if args.history_action == "search":
            action = "history_search"
            params["text"] = args.query or ""
            params["maxResults"] = args.max_results
            if args.start_time is not None:
                params["startTime"] = args.start_time
            if args.end_time is not None:
                params["endTime"] = args.end_time
        else:
            action = "history_delete"
            params["url"] = args.query
    elif action == "group":
        if args.group_action == "list":
            action = "group_list"
            if args.window_id is not None:
                params["windowId"] = args.window_id
        elif args.group_action == "move":
            action = "group_move"
            params["tabIds"] = [int(t) for t in args.tabs]
            if args.group_id is not None:
                params["groupId"] = args.group_id
            if args.title is not None:
                params["title"] = args.title
            if args.color is not None:
                params["color"] = args.color
        else:
            action = "group_ungroup"
            params["tabIds"] = [int(t) for t in args.tabs]
    elif action == "nav":
        params["url"] = args.url
        params["wait"] = "none" if args.no_wait else "load"
    elif action in ("back", "forward", "reload"):
        params["wait"] = "none" if args.no_wait else "load"
    elif action == "snapshot":
        params["mode"] = "full" if args.full else "interactive"
        params["frames"] = not args.no_frames
    elif action == "elements":
        if args.filter:
            params["filter"] = args.filter
    elif action in ("click", "dblclick", "rightclick", "hover"):
        if args.ref:
            params["ref"] = args.ref
        elif args.target:
            params["target"] = args.target
        elif args.x is not None and args.y is not None:
            params["x"] = args.x
            params["y"] = args.y
        if hasattr(args, "button"):
            params["button"] = args.button
    elif action == "drag":
        params["from"] = args.from_target
        params["to"] = args.to_target
        params["steps"] = args.steps
    elif action == "fill":
        params["target"] = args.target
        params["text"] = args.text
        params["append"] = args.append
        params["clear"] = not args.no_clear
    elif action == "type":
        params["text"] = args.text
        params["delay"] = args.delay
        if args.ref:
            params["ref"] = args.ref
        elif args.target:
            params["target"] = args.target
    elif action == "key":
        params["key"] = args.key
    elif action == "check-radio":
        action = "check_radio"
        if args.selector:
            params["selector"] = args.selector
        elif args.target:
            params["target"] = args.target
        if args.text:
            params["text"] = args.text
        if args.value is not None:
            params["value"] = args.value
    elif action == "select":
        params["target"] = args.target
        if args.value:
            params["value"] = args.value
        if args.label:
            params["label"] = args.label
    elif action == "upload":
        params["target"] = args.target
        params["files"] = [str(Path(f).resolve()) for f in args.files]
    elif action == "scroll":
        if args.x is not None:
            params["x"] = args.x
        if args.y is not None:
            params["y"] = args.y
        if args.ref:
            params["ref"] = args.ref
        elif args.target:
            params["target"] = args.target
    elif action == "wait":
        params["timeout"] = args.timeout
        if args.text:
            params["text"] = args.text
        elif args.selector:
            params["selector"] = args.selector
        elif args.ref:
            params["ref"] = args.ref
        elif args.url:
            params["url"] = args.url
        elif args.load:
            params["load"] = True
        elif args.idle:
            params["idle"] = True
    elif action == "text":
        params["target"] = args.target
    elif action == "eval":
        params["code"] = args.code
    elif action == "screenshot":
        params["format"] = "png" if args.png else "jpeg"
        params["quality"] = args.quality
        if args.clip:
            try:
                parts = [float(x) for x in args.clip.split(",")]
                params["clip"] = {"x": parts[0], "y": parts[1], "width": parts[2], "height": parts[3]}
            except Exception:
                pass
        if args.of:
            params["of"] = args.of
    elif action == "console":
        params["clear"] = args.clear
    elif action == "dialog":
        params["policy"] = args.policy
        if args.prompt:
            params["promptText"] = args.prompt
    elif action == "batch":
        try:
            params["steps"] = json.loads(args.steps)
        except Exception as e:
            if opt_json:
                print(json.dumps({"success": False, "code": "bad_params", "error": f"Invalid JSON in batch: {e}"}))
            else:
                print(f"Error: Invalid JSON for batch: {e}", file=sys.stderr)
            return 3

    res = edge.send(action, params)
    if opt_session and edge.session_token != opt_session:
        print(f"edge-bridge: session expired; re-minted sessionToken={edge.session_token} "
              f"(export EDGE_BRIDGE_SESSION={edge.session_token})", file=sys.stderr)

    # If screenshot with path, save file
    if action == "screenshot" and getattr(args, "path", None) and res.get("success") and (res.get("dataUrl") or res.get("data")):
        data_str = res.get("dataUrl") or res["data"]
        if "," in data_str:
            data_str = data_str.split(",", 1)[1]
        import base64
        b = base64.b64decode(data_str)
        out_p = Path(args.path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_bytes(b)
        res["path"] = str(out_p.resolve())

    if opt_json:
        print(json.dumps(res))
    else:
        # Human-friendly output
        if res.get("success"):
            if action == "snapshot":
                print(res.get("text", ""))
            elif action == "elements":
                els = res.get("elements", [])
                print(f"Found {len(els)} interactive element(s):")
                for e in els:
                    ref = f"[{e.get('ref')}]" if e.get("ref") else ""
                    print(f"  {ref} {e.get('tag', '')} {e.get('text', '')[:40]} ({e.get('x')},{e.get('y')})")
            elif action == "tabs":
                tabs = res.get("tabs", [])
                print(f"{len(tabs)} tab(s):")
                for t in tabs:
                    act = "*" if t.get("active") else " "
                    print(f"  {act} [{t.get('id')}] {t.get('title', '')[:50]} - {t.get('url')}")
            elif action == "screenshot":
                if res.get("path"):
                    print(f"Saved screenshot: {res['path']}")
                else:
                    print(f"Screenshot taken ({len(res.get('data', ''))} bytes base64)")
            elif action == "history_search":
                items = res.get("items", [])
                print(f"Found {len(items)} history item(s):")
                for it in items:
                    print(f"  {it.get('title', '')[:50]} - {it.get('url')}")
            elif action == "group_list":
                groups = res.get("groups", [])
                print(f"{len(groups)} group(s):")
                for g in groups:
                    print(f"  [{g.get('id')}] {g.get('title', '')} ({g.get('color', '')})")
            elif action == "console":
                entries = res.get("entries", [])
                print(f"{len(entries)} console entry(ies):")
                for item in entries:
                    print(f"  [{item.get('level')}] {item.get('text')}")
            else:
                tab_info = res.get("tab")
                tab_str = f" (tab {tab_info['id']})" if isinstance(tab_info, dict) and "id" in tab_info else ""
                print(f"OK{tab_str}")
        else:
            err_code = res.get("code", "error")
            err_msg = res.get("error", "Action failed")
            print(f"Error ({err_code}): {err_msg}", file=sys.stderr)

    # Determine exit code
    if res.get("success"):
        return 0
    code = res.get("code")
    if code in ("daemon_unreachable", "missing_token"):
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
