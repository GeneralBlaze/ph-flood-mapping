"""Local preview of the site with the full-area analysis, using this computer's Earth Engine login.

Usage:
    python -m analysis.dev_server --port 8792
"""

import argparse
import json
import logging
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class DevHandler(SimpleHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/api/area":
            self.send_error(404)
            return
        from analysis.area_server import handle

        length = int(self.headers.get("content-length") or 0)
        status, payload = handle(self.rfile.read(length), self.client_address[0])
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/api/area":
            super().do_GET()
            return
        from analysis.area_server import status

        data = json.dumps(status()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8792)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    os.environ.setdefault("AREA_LOCAL_DEV", "1")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(DevHandler, directory=str(WEB_DIR)))
    logging.info("Serving %s with /api/area on http://127.0.0.1:%d", WEB_DIR, args.port)
    server.serve_forever()


if __name__ == "__main__":
    main()
