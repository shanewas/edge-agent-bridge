"""
Edge Agent Bridge
Real-time AI agent control for Microsoft Edge using active browser sessions,
CDP hardware events, and WebSockets.
"""
from .cli import Edge, EdgeClient, send_cmd, ensure_bridge_running
from .bridge import run_server

__version__ = "1.1.0"
__all__ = ["Edge", "EdgeClient", "send_cmd", "ensure_bridge_running", "run_server"]
