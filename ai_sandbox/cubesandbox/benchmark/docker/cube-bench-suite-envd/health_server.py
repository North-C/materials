#!/usr/bin/env python3
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("CUBE_PROBE_PORT", "49999"))

CASES = [
    "sysbench-memory",
    "sysbench-memory-all",
    "sysbench-prime",
    "sysbench-prime-matrix",
    "go-benchmark",
    "php-benchmark",
    "python-benchmark",
    "node-octane",
    "java-scimark",
    "formal",
]


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/health"):
            self._send(200, {"status": "ok", "service": "cube-bench-suite"})
            return
        if self.path == "/benchmarks":
            self._send(200, {"benchmarks": CASES})
            return
        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
