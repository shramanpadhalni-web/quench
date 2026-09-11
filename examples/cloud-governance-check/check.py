#!/usr/bin/env python3
"""Evaluate one resource against the policy. Pure: same input, same output."""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

def main(resource_id: str) -> int:
    resource = json.loads(
        (HERE / "synthetic_data/resources" / f"{resource_id}.json").read_text()
    )
    policy = json.loads(
        (HERE / "synthetic_data/policy/encryption-policy.json").read_text()
    )
    failures = [
        f"{field}={resource.get(field)!r} not in {allowed}"
        for field, allowed in policy["requires"].items()
        if resource.get(field) not in allowed
    ]
    print(json.dumps({
        "resource_id": resource_id,
        "policy_id": policy["policy_id"],
        "compliant": not failures,
        "failures": failures,
    }, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
