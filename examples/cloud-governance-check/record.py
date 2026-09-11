#!/usr/bin/env python3
"""Append a finding to the audit log.

Audit entries carry a timestamp, because audit entries carry timestamps.
This is not contrived impurity - it is what an audit log is. Whether the
resulting step is sealable is exactly the question under measurement.
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
from subprocess import run

HERE = Path(__file__).resolve().parent
LOG = HERE / "output" / "findings.jsonl"

def main(resource_id: str) -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    result = run(
        [sys.executable, str(HERE / "check.py"), resource_id],
        capture_output=True, text=True, check=True,
    )
    finding = json.loads(result.stdout)
    finding["recorded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with LOG.open("a") as fh:
        fh.write(json.dumps(finding, sort_keys=True) + "\n")
    print(json.dumps({
        "recorded": finding["resource_id"],
        "compliant": finding["compliant"],
        "recorded_at": finding["recorded_at"],
        "log": str(LOG),
    }, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
