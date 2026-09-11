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
