"""Minimal async HTTP server — serves /public for the iPad UI."""
from __future__ import annotations

import asyncio
from pathlib import Path

from src.config import PUBLIC_DIR, PORT

MIME = {
    ".html": "text/html",
    ".css":  "text/css",
    ".js":   "application/javascript",
    ".json": "application/json",
    ".ico":  "image/x-icon",
    ".png":  "image/png",
    ".svg":  "image/svg+xml",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".woff":  "font/woff",
    ".woff2": "font/woff2",
}


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        request_line = await reader.readline()
        if not request_line:
            return
        parts = request_line.decode().split()
        if len(parts) < 2 or parts[0] != "GET":
            writer.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return

        path = parts[1].split("?")[0]
        if path == "/":
            path = "/index.html"

        # Prevent path traversal
        full = Path(PUBLIC_DIR) / path.lstrip("/")
        full = full.resolve()
        if not str(full).startswith(str(Path(PUBLIC_DIR).resolve())):
            writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            return

        if not full.exists():
            writer.write(b"HTTP/1.1 404 Not Found\r\n\r\n")
            return

        mime = MIME.get(full.suffix, "application/octet-stream")
        data = full.read_bytes()
        response = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: {mime}\r\n"
            f"Content-Length: {len(data)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode() + data
        writer.write(response)
    except Exception as e:
        print(f"[http] error: {e}")
    finally:
        await writer.drain()
        writer.close()


async def start_http_server() -> asyncio.Server:
    server = await asyncio.start_server(_handle, "0.0.0.0", PORT)
    print(f"[http] serving /public on http://0.0.0.0:{PORT}")
    return server
