"""
Agent Browser Bridge
Universal AI agent control for Microsoft Edge and Chromium browsers using active sessions,
CDP hardware events, and WebSockets.
"""
from .cli import Edge, EdgeClient, send_cmd, ensure_bridge_running
from .bridge import run_server

__version__ = "1.2.1"
__all__ = ["Edge", "EdgeClient", "send_cmd", "ensure_bridge_running", "run_server"]
