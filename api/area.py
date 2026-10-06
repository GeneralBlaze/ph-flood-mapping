"""Vercel Python function: POST /api/area runs one step of the full drawn-area analysis."""

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root: the analysis package

from analysis.area_server import MAX_BODY_BYTES, handle, status  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def client_address(headers, fallback: str) -> str:
    """Vercel sets x-real-ip to the caller's address; x-forwarded-for's first entry otherwise."""
    forwarded = headers.get("x-real-ip") or headers.get("x-forwarded-for", "").split(",")[0]
    return forwarded.strip() or fallback


class handler(BaseHTTPRequestHandler):  # noqa: N801 — the name Vercel's Python runtime looks for
    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send(413 if length > MAX_BODY_BYTES else 400, {"error": "Could not read the request."})
            return
        status, payload = handle(self.rfile.read(length), client_address(self.headers, self.client_address[0]))
        self._send(status, payload)

    def do_GET(self) -> None:  # noqa: N802
        self._send(200, status())
