"""MCP tool server for the lease abstraction pipeline.

Every tool here is **deterministic**: same arguments, same result, no clock, no
randomness, no network. That is deliberate and it is the whole demonstration.

The expensive, repeated part of this workflow is not the tools — it is the
*model deciding which tool to call with which arguments*, re-derived from
scratch on every single document. Quench seals the decisions. The tools keep
running for real, against live inputs.

Run standalone for a smoke test:

    python -m backend.mcp_tools --selftest
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "synthetic_data"
OUTPUT_DIR = HERE.parent / "output"

#: Acceptable ranges. In production this would be a policy service; here it is a
#: constant so the workflow is genuinely deterministic end to end.
THRESHOLDS: dict[str, dict[str, float]] = {
    "annual_rent": {"min": 10_000, "max": 5_000_000},
    "escalation_pct": {"min": 0.0, "max": 6.0},
    "term_months": {"min": 12, "max": 240},
}

#: One pattern per clause. All three synthetic template families use the same
#: labels with different surrounding layout — which is exactly why a single
#: sealed Cast can serve all of them.
CLAUSE_PATTERNS: dict[str, re.Pattern[str]] = {
    "term": re.compile(r"TERM:\s*(\d+)\s*months", re.I),
    "annual_rent": re.compile(r"ANNUAL RENT:\s*USD\s*([\d,]+)", re.I),
    "escalation": re.compile(r"ESCALATION:\s*([\d.]+)\s*%", re.I),
    "renewal": re.compile(r"RENEWAL OPTION:\s*(\w+)", re.I),
}

mcp = MCPServer("lease-tools")


@mcp.tool()
def read_lease(document_id: str) -> dict[str, Any]:
    """Read a lease document by id (e.g. 'lease-001')."""
    path = DATA_DIR / f"{document_id}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"no such lease: {document_id}. "
            f"Available ids look like 'lease-001' through 'lease-020'."
        )
    return {"document_id": document_id, "text": path.read_text()}


@mcp.tool()
def extract_clause(text: str, clause_type: str) -> dict[str, Any]:
    """Extract one clause from lease text.

    clause_type must be one of: term, annual_rent, escalation, renewal.
    """
    pattern = CLAUSE_PATTERNS.get(clause_type)
    if pattern is None:
        raise ValueError(
            f"unknown clause_type {clause_type!r}; "
            f"expected one of {sorted(CLAUSE_PATTERNS)}"
        )
    match = pattern.search(text)
    if not match:
        return {"clause_type": clause_type, "value": None, "found": False}

    raw = match.group(1)
    value: Any = raw
    if clause_type == "term":
        value = int(raw)
    elif clause_type == "annual_rent":
        value = int(raw.replace(",", ""))
    elif clause_type == "escalation":
        value = float(raw)
    return {"clause_type": clause_type, "value": value, "found": True}


@mcp.tool()
def lookup_threshold(field: str) -> dict[str, Any]:
    """Return the acceptable range for a field.

    field must be one of: annual_rent, escalation_pct, term_months.
    """
    bounds = THRESHOLDS.get(field)
    if bounds is None:
        raise ValueError(
            f"unknown field {field!r}; expected one of {sorted(THRESHOLDS)}"
        )
    return {"field": field, **bounds}


@mcp.tool()
def check_anomaly(field: str, value: float) -> dict[str, Any]:
    """Check whether a value falls outside its threshold."""
    bounds = THRESHOLDS.get(field)
    if bounds is None:
        raise ValueError(f"unknown field {field!r}")
    anomalous = value < bounds["min"] or value > bounds["max"]
    return {
        "field": field,
        "value": value,
        "anomalous": anomalous,
        "reason": (
            f"{value} outside [{bounds['min']}, {bounds['max']}]"
            if anomalous
            else "within range"
        ),
    }


@mcp.tool()
def write_record(document_id: str, record: dict) -> dict[str, Any]:
    """Persist the structured lease record as JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{document_id}.json"
    # sort_keys so the written bytes are stable for identical input — an impure
    # write here would make the step unsealable. See Assay's purity check.
    path.write_text(json.dumps(record, indent=2, sort_keys=True))
    return {"written": str(path), "fields": sorted(record)}


def _selftest() -> int:
    """Exercise every tool without the MCP transport."""
    doc = read_lease("lease-001")
    assert doc["text"].startswith("MASTER LEASE"), doc["text"][:40]

    for clause in ("term", "annual_rent", "escalation", "renewal"):
        got = extract_clause(doc["text"], clause)
        assert got["found"], got
        print(f"  {clause:<12} -> {got['value']!r}")

    bounds = lookup_threshold("annual_rent")
    print(f"  threshold    -> {bounds}")

    rent = extract_clause(doc["text"], "annual_rent")["value"]
    print(f"  anomaly      -> {check_anomaly('annual_rent', rent)}")

    anomalous = read_lease("lease-901")["text"]
    bad = extract_clause(anomalous, "annual_rent")["value"]
    verdict = check_anomaly("annual_rent", bad)
    assert verdict["anomalous"], verdict
    print(f"  anomaly(901) -> {verdict}")

    out = write_record("lease-001", {"term": 12, "annual_rent": rent})
    print(f"  write        -> {out}")

    # Determinism: the same input must produce byte-identical output.
    first = Path(out["written"]).read_bytes()
    write_record("lease-001", {"term": 12, "annual_rent": rent})
    assert Path(out["written"]).read_bytes() == first, "write_record is not pure"
    print("  purity       -> write_record is byte-stable")

    print("\nAll tools OK.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    mcp.run()
