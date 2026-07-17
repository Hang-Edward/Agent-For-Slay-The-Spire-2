from __future__ import annotations

import json
import mimetypes
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class DashboardServer:
    def __init__(self, event_bus, history_store, host: str = "127.0.0.1", port: int = 18889):
        self.event_bus = event_bus
        self.history_store = history_store
        self.host = host
        self.port = port
        self.static_dir = Path(__file__).parent / "static"
        self._httpd = None
        self._thread = None
        self._stopping = threading.Event()

    @property
    def url(self) -> str:
        port = self._httpd.server_address[1] if self._httpd else self.port
        return f"http://{self.host}:{port}"

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                return

            def _json(self, status: int, value) -> None:
                body = json.dumps(value, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _static(self, name: str) -> None:
                path = outer.static_dir / name
                if not path.is_file():
                    self._json(404, {"error": "not found"})
                    return
                body = path.read_bytes()
                mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") else ""))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self): self._json(405, {"error": "read only"})
            def do_PUT(self): self._json(405, {"error": "read only"})
            def do_PATCH(self): self._json(405, {"error": "read only"})
            def do_DELETE(self): self._json(405, {"error": "read only"})

            def do_GET(self):
                parsed = urlparse(self.path)
                path = unquote(parsed.path)
                if path == "/": return self._static("index.html")
                if path in {"/styles.css", "/app.js"}: return self._static(path[1:])
                if path == "/api/snapshot": return self._json(200, outer.event_bus.snapshot())
                if path == "/api/events": return self._events()
                if path == "/api/runs":
                    query = parse_qs(parsed.query)
                    offset = max(0, int(query.get("offset", [0])[0]))
                    limit = min(200, max(1, int(query.get("limit", [50])[0])))
                    return self._json(200, outer.history_store.list_runs(offset=offset, limit=limit))
                match = re.fullmatch(r"/api/runs/([A-Za-z0-9._-]+)", path)
                if match:
                    run = outer.history_store.get_run(match.group(1))
                    return self._json(200 if run else 404, run or {"error": "not found"})
                match = re.fullmatch(r"/api/runs/([A-Za-z0-9._-]+)/decisions/([A-Za-z0-9._-]+)", path)
                if match:
                    item = outer.history_store.get_decision(match.group(1), match.group(2))
                    return self._json(200 if item else 404, item or {"error": "not found"})
                self._json(404, {"error": "not found"})

            def _events(self):
                try:
                    last = int(self.headers.get("Last-Event-ID", "0"))
                except ValueError:
                    last = 0
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                self.wfile.write(b"retry: 1500\n")
                try:
                    while not outer._stopping.is_set():
                        events, _gap = outer.event_bus.events_after(last)
                        if not events:
                            events, _gap = outer.event_bus.wait_for_events(last, 15.0)
                        for event in events:
                            payload = json.dumps(
                                event.to_dict(), ensure_ascii=False, separators=(",", ":")
                            )
                            self.wfile.write(
                                f"id: {event.sequence}\nevent: telemetry\ndata: {payload}\n\n".encode("utf-8")
                            )
                            last = event.sequence
                        if not events:
                            self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return

        self._httpd = _Server((self.host, self.port), Handler)
        self._stopping.clear()
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="dashboard-http", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._httpd:
            return
        self._stopping.set()
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=5)
        self._httpd = None
