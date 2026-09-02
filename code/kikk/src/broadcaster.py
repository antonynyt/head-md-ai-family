"""WebSocket broadcaster — pushes JSON events to all connected clients (iPad, browser).

Message shapes sent to clients:
  { "type": "session:start" }
  { "type": "session:end" }
  { "type": "session:error", "message": str }
  { "type": "transcript", "text": str, "turn": "user"|"model", "delay_ms": int }
  { "type": "word:saved", "word": { term, definition, example, added_by, saved_at } }
  { "type": "interrupted" }
  { "type": "dictionary:init", "words": [...] }
"""
from __future__ import annotations

import json
from typing import Any

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError as e:
    raise ImportError("pip install websockets") from e

import src.dictionary as dictionary

_clients: set[WebSocketServerProtocol] = set()


async def handler(ws: WebSocketServerProtocol) -> None:
    """Called for each new WebSocket connection."""
    _clients.add(ws)
    print(f"[ws] client connected: {ws.remote_address}  (total: {len(_clients)})")

    # Bootstrap the client with the current dictionary
    words = dictionary.load()
    try:
        await ws.send(json.dumps({"type": "dictionary:init", "words": words}))
    except Exception:
        pass

    try:
        # Keep the connection open; we don't expect messages from clients
        await ws.wait_closed()
    finally:
        _clients.discard(ws)
        print(f"[ws] client disconnected: {ws.remote_address}  (total: {len(_clients)})")


async def broadcast(msg: dict[str, Any]) -> None:
    """Send a JSON message to all connected clients."""
    if not _clients:
        return
    payload = json.dumps(msg)
    # websockets.broadcast is efficient (sends to all without awaiting each)
    websockets.broadcast(_clients, payload)
