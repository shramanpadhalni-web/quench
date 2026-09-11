"""Quench App backend — the composition root.

**This is the only file in the repository permitted to import a concrete
adapter and wire it to a port.** Everything else depends on interfaces. A new
contributor should be able to read this one file and see the entire object
graph, which is the whole justification for the ports-and-adapters discipline
elsewhere.

If that stops being true, the discipline has already failed.

Runs as a Kiro Crew App backend: the Gateway starts `backend.entryPoint` and
reverse-proxies it at `/apps/quench/api/*`, authenticating with a
`X-Crew-Proxy: <timestamp>:<hmac-sha256>` header.

Standard library only. A dependency here is a dependency in the Gateway's
environment, and this layer is deliberately thin.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for component in ("cast", "assay", "vault", "mill", "kernel"):
    sys.path.insert(0, str(ROOT / component / "src"))

# --------------------------------------------------------------------------
# The wiring. Concrete adapters appear here and nowhere else.
# --------------------------------------------------------------------------
from assay.hallmark.signer import Signer                                # noqa: E402
from assay.purity import oracle                                         # noqa: E402
from assay.strategies import baseline_controlflow_strategy as baseline  # noqa: E402
from cast.adapters.hook_trace_adapter import HookTraceAdapter           # noqa: E402
from cast.compiler.grouping import group_traces                         # noqa: E402
from cast.compiler.ir_builder import CompilationRejected, build_cast    # noqa: E402
from kernel.kernel import Kernel                                        # noqa: E402
from kernel.ports.promotion_policy import ConservativePolicy, DefaultPolicy  # noqa: E402
from kernel.state_machine import KernelState                            # noqa: E402
from vault.adapters.filesystem_repository import FilesystemRepository   # noqa: E402
from vault.models.ingot_artifact import from_cast                       # noqa: E402

MIN_TRACES = int(os.environ.get("QUENCH_MIN_TRACES", "10"))


def build_kernel() -> Kernel:
    """Per-workflow risk tolerance is configured here, not in the Kernel.

    A workflow whose name suggests it touches credentials or production gets
    the conservative policy. This is a deliberately crude heuristic and exists
    to demonstrate the seam; a deployment should configure explicitly.
    """
    return Kernel(policy=DefaultPolicy(threshold=10))


class Quench:
    """The wired application. Everything the HTTP layer can do lives here."""

    def __init__(self) -> None:
        self.traces = HookTraceAdapter()
        self.vault = FilesystemRepository()
        self.signer = Signer()
        self.kernel = build_kernel()

    # ---------------------------------------------------------------- reads
    def candidates(self) -> list[dict]:
        """Workflows discovered from observed traces, with their lifecycle state."""
        out = []
        for index, group in enumerate(group_traces(self.traces.fetch_traces())):
            eligible = len(group) >= MIN_TRACES
            skill_id = group.key
            record = self.kernel.record(skill_id)
            self.kernel.observe(skill_id, len(group))
            out.append(
                {
                    "index": index,
                    "skill_id": skill_id,
                    "state": record.state.value,
                    "traces": len(group),
                    "steps": group.step_count,
                    "tools": [t.split("/")[-1] for t in group.tool_sequence],
                    "label": group.label,
                    "eligible": eligible,
                    "needs": max(0, MIN_TRACES - len(group)),
                    "ingot_id": record.ingot_id,
                    "consecutive_matches": record.consecutive_matches,
                    "drift_events": record.drift_events,
                }
            )
        return out

    def ingots(self) -> list[dict]:
        return [
            {
                "ingot_id": i.ingot_id,
                "steps": len(i),
                "revoked": i.revoked,
                "sealed_at": i.hallmark.get("provenance", {}).get("sealed_at"),
                "verified_by": i.hallmark.get("provenance", {}).get("verified_by", []),
            }
            for i in self.vault.list()
        ]

    def state(self) -> dict:
        return {
            "summary": self.kernel.summary(),
            "skills": [r.to_dict() for r in self.kernel.all()],
        }

    # --------------------------------------------------------------- writes
    def seal(self, index: int) -> dict:
        """Verify, sign, store, and register for shadow comparison.

        Note what this does NOT do: promote to Sealed. A newly signed artifact
        enters SHADOW and must earn its way forward. There is no path from here
        to live execution.
        """
        groups = group_traces(self.traces.fetch_traces())
        if not 0 <= index < len(groups):
            return {"error": f"no candidate {index}"}
        group = groups[index]
        traces = list(group.traces)

        passed, refusals = [], []
        if baseline.evaluate(traces):
            passed.append("no_branching")
        else:
            refusals.append(baseline.evaluate(traces).reason)

        verdict = oracle.evaluate(traces)
        if verdict.impure_steps:
            for step in verdict.impure_steps:
                refusals.append(
                    f"purity: step {step.position} "
                    f"({step.tool_name.split('/')[-1]}) produced "
                    f"{step.distinct_outputs} distinct outputs for identical input"
                )
        else:
            passed.append("purity")

        if refusals:
            return {"sealed": False, "refusals": refusals, "passed": passed}

        try:
            cast = build_cast(traces, minimum=MIN_TRACES, source=self.traces.describe())
        except CompilationRejected as exc:
            return {"sealed": False, "refusals": [str(exc)], "passed": passed}

        hallmark = self.signer.sign(
            cast, verified_by=tuple(passed), trace_source=self.traces.describe()
        )
        ingot = from_cast(cast, hallmark, {"tools": list(group.tool_sequence)})
        path = self.vault.put(ingot)
        self.kernel.enter_shadow(group.key, ingot.ingot_id)

        return {
            "sealed": True,
            "ingot_id": ingot.ingot_id,
            "steps": len(ingot),
            "verified_by": passed,
            "state": "shadow",
            "path": path,
            "note": "registered for shadow comparison; not yet authorised to execute",
        }

    def shadow_result(self, skill_id: str, matched: bool) -> dict:
        record = self.kernel.record_shadow_run(skill_id, matched)
        return {"skill_id": skill_id, "state": record.state.value,
                "consecutive": record.consecutive_matches, "note": record.note}

    def drift(self, skill_id: str, reason: str = "") -> dict:
        record = self.kernel.record_drift(skill_id, reason)
        return {"skill_id": skill_id, "state": record.state.value,
                "drift_events": record.drift_events}

    def revoke(self, skill_id: str) -> dict:
        record = self.kernel.revoke(skill_id)
        if record.ingot_id:
            self.vault.revoke(record.ingot_id)
        return {"skill_id": skill_id, "state": record.state.value}


APP = Quench()


class Handler(BaseHTTPRequestHandler):
    """Minimal REST surface for the dashboard page and the CLI."""

    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, indent=2, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # quieter under the Gateway
        pass

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/")
        routes = {
            "/health": lambda: {"status": "ok", "app": "quench"},
            "/api/candidates": APP.candidates,
            "/api/ingots": APP.ingots,
            "/api/state": APP.state,
        }
        handler = routes.get(path) or routes.get(path.replace("/apps/quench", ""))
        if handler is None:
            return self._send({"error": f"no route {path}"}, 404)
        try:
            self._send(handler() if not isinstance(handler(), dict) else handler())
        except Exception as exc:  # a backend crash must not take the Gateway down
            self._send({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self) -> None:
        path = self.path.split("?")[0].rstrip("/").replace("/apps/quench", "")
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or "{}")
        except json.JSONDecodeError:
            return self._send({"error": "invalid JSON"}, 400)

        try:
            if path == "/api/seal":
                return self._send(APP.seal(int(body.get("index", -1))))
            if path == "/api/shadow":
                return self._send(
                    APP.shadow_result(body["skill_id"], bool(body.get("matched")))
                )
            if path == "/api/drift":
                return self._send(
                    APP.drift(body["skill_id"], body.get("reason", ""))
                )
            if path == "/api/revoke":
                return self._send(APP.revoke(body["skill_id"]))
        except Exception as exc:
            return self._send({"error": f"{type(exc).__name__}: {exc}"}, 500)
        self._send({"error": f"no route {path}"}, 404)


def main() -> int:
    # The Gateway assigns a port and passes it in; default is for local runs.
    port = int(os.environ.get("PORT") or os.environ.get("QUENCH_PORT") or 8471)
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"quench backend on 127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
