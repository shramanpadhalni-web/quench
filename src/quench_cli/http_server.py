"""HTTP surface: the REST API and the dashboard.

Standard library only. This runs inside a Gateway process when deployed as a
Kiro Crew App, and a dependency here becomes a dependency there.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .wiring import build

DASHBOARD = Path(__file__).resolve().parent / "dashboard.html"


def _append_otlp(payload: dict) -> int:
    """Append one OTLP export to the span log and report how many spans it held.

    Append-only JSONL for the same reason the trace hook is: an observer that
    can lose or reorder what it saw is not an observer.
    """
    from cast.adapters.otel_trace_adapter import DEFAULT_SPAN_FILE

    count = sum(
        len(scope.get("spans", []))
        for resource in payload.get("resourceSpans", [])
        for scope in resource.get("scopeSpans", [])
    )
    DEFAULT_SPAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_SPAN_FILE.open("a") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")) + "\n")
    return count


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # quiet under a supervisor
        pass

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, indent=2, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str) -> None:
        body = text.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _path(self) -> str:
        # Tolerate the Gateway's reverse-proxy prefix.
        return (
            self.path.split("?")[0].rstrip("/").replace("/apps/quench", "") or "/"
        )

    def do_GET(self) -> None:
        path = self._path()
        app = build()
        try:
            if path in ("/", "/ui"):
                return self._html(DASHBOARD.read_text())
            if path == "/health":
                return self._json({"status": "ok", "app": "quench"})
            if path == "/api/candidates":
                return self._json(app.candidates())
            if path == "/api/ingots":
                return self._json(app.ingots())
            if path == "/api/overview":
                return self._json(app.overview())
            if path == "/api/state":
                return self._json(app.state())
        except Exception as exc:  # never take the host process down
            return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
        self._json({"error": f"no route {path}"}, 404)

    def do_POST(self) -> None:
        path = self._path()
        app = build()
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"

        # OTLP/HTTP receiver. Any OTel-instrumented agent can point
        # OTEL_EXPORTER_OTLP_ENDPOINT here and Quench observes it — no plugin,
        # no framework knowledge, no code change in the agent.
        if path == "/v1/traces":
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                # Protobuf OTLP is the other wire format; we accept JSON only,
                # and say so rather than failing opaquely.
                return self._json(
                    {"error": "expected OTLP/JSON; set OTEL_EXPORTER_OTLP_PROTOCOL"
                              "=http/json"},
                    415,
                )
            spans = _append_otlp(payload)
            # OTLP expects an empty success body; extra fields are ignorable.
            return self._json({"partialSuccess": {}, "quench": {"spans": spans}})

        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "invalid JSON"}, 400)
        try:
            if path == "/api/seal":
                return self._json(app.seal(int(body.get("index", -1))))
            if path == "/api/shadow":
                return self._json(
                    app.shadow_result(body["skill_id"], bool(body.get("matched")))
                )
            if path == "/api/drift":
                return self._json(app.drift(body["skill_id"], body.get("reason", "")))
            if path == "/api/revoke":
                return self._json(app.revoke(body["skill_id"]))
        except Exception as exc:
            return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
        self._json({"error": f"no route {path}"}, 404)


def serve_http(port: int = 8471, host: str = "127.0.0.1") -> int:
    server = HTTPServer((host, port), Handler)
    print(f"Quench dashboard  http://{host}:{port}", flush=True)
    print(f"Quench API        http://{host}:{port}/api/candidates", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    return 0
