"""Scaffold examples/cloud-governance-check.

Deliberately built on Crew's BUILT-IN tools (fs_read, execute_bash, fs_write)
rather than a purpose-built MCP server. The lease example used tools written to
be deterministic — no clock, no randomness, sort_keys on write — and so could
not exhibit output impurity at all. See docs/paper/RESULTS.json and the
2026-09-11 commit cab7c25.

The workflow below is written the way an engineer would naturally write it. No
impurity is manufactured: a governance sweep lists a directory to discover
resources, and appends findings to a timestamped audit log, because that is what
audit logs do. Whether those steps turn out impure is the measurement, not the
design.
"""
import json, os, pathlib, random, textwrap

ROOT = pathlib.Path(os.path.expanduser("~/quench/examples/cloud-governance-check"))
HOME = os.path.expanduser("~")


def w(rel, content):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if isinstance(content, str) else json.dumps(content, indent=2) + "\n")
    print("  " + rel)


rng = random.Random(20260911)

# ------------------------------------------------------------------ resources
REGIONS = ["ap-south-1", "eu-west-1", "us-east-1", "ap-southeast-2"]
for i in range(1, 21):
    compliant = i % 4 != 0  # a quarter deliberately non-compliant
    w(f"synthetic_data/resources/bucket-{i:03d}.json", {
        "resource_id": f"bucket-{i:03d}",
        "type": "object_store",
        "region": rng.choice(REGIONS),
        "encryption": "AES256" if compliant else "none",
        "versioning": "enabled" if compliant else "disabled",
        "public_access_block": compliant,
        "owner": f"team-{rng.randint(1, 6)}",
    })

w("synthetic_data/policy/encryption-policy.json", {
    "policy_id": "enc-baseline-v3",
    "requires": {
        "encryption": ["AES256", "aws:kms"],
        "versioning": ["enabled"],
        "public_access_block": [True],
    },
})

# --------------------------------------------------------------------- agent
AGENT_PROMPT = textwrap.dedent(f"""
    You are the CLOUD GOVERNANCE agent. You check one resource against the
    encryption baseline policy and record the finding.

    Given a resource id, do exactly this, in order, one tool call per turn:

      1. fs_read  — list the directory
         {ROOT}/synthetic_data/resources
         (this is the inventory step; it confirms the resource exists)

      2. fs_read  — read the resource config
         {ROOT}/synthetic_data/resources/<resource_id>.json

      3. fs_read  — read the policy
         {ROOT}/synthetic_data/policy/encryption-policy.json

      4. execute_bash — evaluate compliance, exactly this command:
         python3 {ROOT}/check.py <resource_id>

      5. execute_bash — append the finding to the audit log, exactly this:
         python3 {ROOT}/record.py <resource_id>

    Never skip a step, never reorder, never infer a result you did not obtain
    from a tool. If a tool is unavailable, say so and stop — do not describe
    what the call would have returned.

    When step 5 completes, reply with exactly one line:
      CHECKED <resource_id> <COMPLIANT|NON_COMPLIANT>
""").strip()

w("agents/governance-checker.json", {
    "name": "governance-checker",
    "description": "Checks one cloud resource against the encryption baseline policy.",
    "model": "auto",
    "includeMcpJson": False,
    "resources": [],
    "prompt": AGENT_PROMPT,
    "tools": ["fs_read", "execute_bash"],
    "allowedTools": ["fs_read", "execute_bash"],
    "hooks": {
        "postToolUse": [{"command": f"{HOME}/.kiro/hooks/quench-trace-post.sh"}],
        "preToolUse": [{"command": f"{HOME}/.kiro/hooks/quench-trace-pre.sh"}],
        "userPromptSubmit": [{"command": f"{HOME}/.kiro/hooks/quench-trace-prompt.sh"}],
    },
})

# ------------------------------------------------------------------- helpers
w("check.py", textwrap.dedent('''
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
''').lstrip())

w("record.py", textwrap.dedent('''
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
            fh.write(json.dumps(finding, sort_keys=True) + "\\n")
        print(json.dumps({
            "recorded": finding["resource_id"],
            "compliant": finding["compliant"],
            "recorded_at": finding["recorded_at"],
            "log": str(LOG),
        }, indent=2, sort_keys=True))
        return 0

    if __name__ == "__main__":
        raise SystemExit(main(sys.argv[1]))
''').lstrip())

w("README.md", textwrap.dedent('''
    # cloud-governance-check

    A scheduled compliance sweep, built on Crew's **built-in** tools (`fs_read`,
    `execute_bash`) rather than a purpose-built MCP server.

    ## Why it exists

    The `lease-abstraction` example uses tools written to be deterministic: no
    clock, no randomness, no network, `sort_keys` on write. Its corpus therefore
    measured 0% output impurity — a corpus built from tools that cannot be impure
    cannot measure impurity. See `docs/paper/RESULTS.json` and commit `cab7c25`.

    The original observation that motivated the purity hypothesis — an `ls`-style
    mtime in a directory listing — came from Crew's own built-in tools. This
    example exercises those.

    ## The workflow

    | Step | Tool | What it does |
    |---|---|---|
    | 1 | `fs_read` | list the resources directory (inventory) |
    | 2 | `fs_read` | read the resource config |
    | 3 | `fs_read` | read the policy |
    | 4 | `execute_bash` | `check.py <id>` — evaluate compliance |
    | 5 | `execute_bash` | `record.py <id>` — append to the audit log |

    **No impurity is manufactured.** A governance sweep lists a directory to
    discover resources, and an audit entry carries a timestamp because that is
    what audit entries do. Whether steps 1 and 5 turn out impure is the
    measurement, not the design.

    ## Data

    20 synthetic resources, deterministic (seed 20260911); every fourth one is
    non-compliant. No client data, ever.

    ## Run

    ```bash
    ./run_demo.sh --passes 2
    ```
''').lstrip())

print("=== cloud-governance-check ===")
