"""Generate the lease-abstraction agent configs and Crew App manifest."""
import json, os, pathlib

ROOT = pathlib.Path(os.path.expanduser("~/quench/examples/lease-abstraction"))
HOME = os.path.expanduser("~")
VENV_PY = f"{HOME}/quench/.venv/bin/python"
BACKEND = f"{ROOT}/backend"

def w(rel, obj):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n")
    print("  " + rel)

#: Wire every agent to the lease tool server. `cwd` matters: mcp_tools.py
#: resolves synthetic_data/ and output/ relative to its own location.
LEASE_MCP = {
    "lease-tools": {
        "command": VENV_PY,
        "args": ["-m", "backend.mcp_tools"],
        "cwd": str(ROOT),
    }
}

BASE = {
    "model": "auto",
    "includeMcpJson": False,
    "resources": [],
}


def agent(name, description, prompt, tools, allowed):
    return {
        **BASE,
        "name": name,
        "description": description,
        "prompt": prompt,
        "tools": tools,
        "allowedTools": allowed,
        "mcpServers": LEASE_MCP,
    }


# ---------------------------------------------------------------- subagents
w("agents/lease-intake.json", agent(
    "lease-intake",
    "Validates a lease document is readable and identifies its template family.",
    (
        "You are the INTAKE agent in a lease abstraction pipeline.\n\n"
        "Given a document id, call read_lease once. Then reply with exactly one "
        "line:\n"
        "  OK <document_id> <template_family>\n"
        "where template_family is alpha if the text starts with 'MASTER LEASE', "
        "beta if it starts with 'COMMERCIAL LEASE', gamma if it starts with "
        "'LEASE SCHEDULE'.\n\n"
        "Call no other tool. Do not summarise the lease. Do not explain."
    ),
    tools=["@lease-tools"],
    allowed=["@lease-tools/read_lease"],
))

w("agents/lease-extractor.json", agent(
    "lease-extractor",
    "Extracts the four fixed commercial clauses and writes the structured record.",
    (
        "You are the EXTRACTION agent in a lease abstraction pipeline.\n\n"
        "Given a document id, do exactly this, in order:\n"
        "  1. read_lease(document_id)\n"
        "  2. extract_clause(text, 'term')\n"
        "  3. extract_clause(text, 'annual_rent')\n"
        "  4. extract_clause(text, 'escalation')\n"
        "  5. extract_clause(text, 'renewal')\n"
        "  6. write_record(document_id, {term, annual_rent, escalation, renewal})\n\n"
        "One tool call per turn, in that order. Never skip a step, never "
        "reorder, never infer a value you did not extract.\n\n"
        "When the record is written, reply with exactly one line:\n"
        "  DONE <document_id> term=<t> rent=<r> esc=<e> renewal=<x>"
    ),
    tools=["@lease-tools"],
    allowed=[
        "@lease-tools/read_lease",
        "@lease-tools/extract_clause",
        "@lease-tools/write_record",
    ],
))

w("agents/lease-anomaly.json", agent(
    "lease-anomaly",
    "Checks extracted lease values against policy thresholds.",
    (
        "You are the ANOMALY agent in a lease abstraction pipeline.\n\n"
        "Given extracted values, do exactly this, in order:\n"
        "  1. lookup_threshold('annual_rent')\n"
        "  2. check_anomaly('annual_rent', <rent>)\n"
        "  3. lookup_threshold('term_months')\n"
        "  4. check_anomaly('term_months', <term>)\n\n"
        "One tool call per turn, in that order.\n\n"
        "Then reply with exactly one line:\n"
        "  FLAGGED <reasons>   if any check returned anomalous\n"
        "  CLEAN               otherwise"
    ),
    tools=["@lease-tools"],
    allowed=[
        "@lease-tools/lookup_threshold",
        "@lease-tools/check_anomaly",
    ],
))

# --------------------------------------------------------------- supervisor
w("agents/lease-supervisor.json", agent(
    "lease-supervisor",
    "Orchestrates the lease abstraction pipeline across three subagents.",
    (
        "You are the SUPERVISOR of a lease abstraction pipeline.\n\n"
        "You do NOT read leases or extract clauses yourself. You delegate.\n\n"
        "Given a document id, run this pipeline:\n"
        "  1. spawn_run(agent='lease-intake', task='Validate <id>')\n"
        "     Wait for the completion event.\n"
        "  2. spawn_run(agent='lease-extractor', task='Extract <id>')\n"
        "     Wait for the completion event.\n"
        "  3. spawn_run(agent='lease-anomaly', task='Check <values from step 2>')\n"
        "     Wait for the completion event.\n\n"
        "Never start a step before the previous completion event has arrived. "
        "Never call a lease tool directly.\n\n"
        "Finally reply with exactly one line:\n"
        "  ABSTRACTED <document_id> <CLEAN|FLAGGED> term=<t> rent=<r>"
    ),
    tools=["@kirocrew-core"],
    allowed=["@kirocrew-core/spawn_run"],
))

# ------------------------------------------------------------------ manifest
w("app.json", {
    "name": "lease-abstraction",
    "displayName": "Lease Abstraction",
    "description": (
        "A multi-agent lease abstraction pipeline - and the reference "
        "demonstration of Quench sealing a real workflow."
    ),
    "version": "0.1.0",
    "author": "Quench contributors",
    "license": "Apache-2.0",
    "minCrewVersion": "0.5.0",
    "tags": ["documents", "extraction", "real-estate", "quench"],
    "agents": [
        "agents/lease-supervisor.json",
        "agents/lease-intake.json",
        "agents/lease-extractor.json",
        "agents/lease-anomaly.json",
    ],
    "skills": ["skills/abstract-lease.md"],
    "backend": {
        "entryPoint": "backend/main.py",
        "type": "python",
        "port": "auto",
        "healthCheck": "/health",
    },
    "ui": {
        "entry": "ui/dist/index.mjs",
        "pages": [
            {
                "route": "/apps/lease-abstraction",
                "label": "Lease Abstraction",
                "icon": "FileText",
            }
        ],
    },
    # ADR-0000 finding 5: permissions.api is enforced today, deny-by-default on
    # out-of-scope paths. Omitting it denies every Gateway call this app makes.
    "permissions": {
        "api": ["/api/status", "/api/agents", "/api/sessions"],
        "events": ["tool_call", "chat_done", "subagent_done", "notification"],
        "storage": True,
        "network": False,
    },
    "dependencies": {"managedBy": "gateway", "commands": ["python3"]},
})

print("=== agents + manifest ===")
