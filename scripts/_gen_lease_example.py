"""Scaffold examples/lease-abstraction as a real Kiro Crew App. Safe to re-run."""
import os, pathlib, textwrap, json, random

ROOT = pathlib.Path(os.path.expanduser("~/quench/examples/lease-abstraction"))
HOME = os.path.expanduser("~")

def w(rel, content, executable=False):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if isinstance(content, str) else json.dumps(content, indent=2))
    if executable:
        p.chmod(0o755)
    print("  " + rel)

def wd(rel, content, executable=False):
    w(rel, textwrap.dedent(content).lstrip("\n"), executable)


# ============================================================= synthetic data
TEMPLATES = {
    "alpha": """MASTER LEASE AGREEMENT - FORM A
PROPERTY: {prop}
TENANT: {tenant}

SECTION 1 - TERM
TERM: {term} months commencing {start}

SECTION 2 - RENT
ANNUAL RENT: USD {rent}
ESCALATION: {esc} % per annum

SECTION 3 - OPTIONS
RENEWAL OPTION: {renewal}
""",
    "beta": """COMMERCIAL LEASE (FORM B)
Premises....: {prop}
Lessee......: {tenant}

-- COMMERCIAL TERMS --
TERM: {term} months
ANNUAL RENT: USD {rent}
ESCALATION: {esc} %
RENEWAL OPTION: {renewal}

-- END --
""",
    "gamma": """LEASE SCHEDULE / TYPE C
{prop} | {tenant}
================================
TERM: {term} months
ANNUAL RENT: USD {rent}
ESCALATION: {esc} %
RENEWAL OPTION: {renewal}
================================
""",
}

PROPS = ["Tower One, Level 12", "Riverside Park B", "Meridian Business Centre",
         "Northgate Industrial Unit 7", "Harbour Point Retail 3"]
TENANTS = ["Acme Logistics Pvt Ltd", "Vertex Analytics", "Northwind Retail",
           "Calder & Sons", "Orion Manufacturing"]

rng = random.Random(20260910)  # deterministic corpus

for i in range(1, 21):
    family = ["alpha", "beta", "gamma"][(i - 1) % 3]
    body = TEMPLATES[family].format(
        prop=rng.choice(PROPS),
        tenant=rng.choice(TENANTS),
        term=rng.choice([12, 24, 36, 60, 84, 120]),
        start=f"2026-{rng.randint(1,12):02d}-01",
        rent=f"{rng.randint(50, 900) * 1000:,}",
        esc=rng.choice(["2.5", "3.0", "3.5", "4.0", "5.0"]),
        renewal=rng.choice(["YES", "NO"]),
    )
    w(f"synthetic_data/lease-{i:03d}.txt", body)

# Two deliberately anomalous leases, for the drift/anomaly demo.
w("synthetic_data/lease-901.txt", TEMPLATES["alpha"].format(
    prop="Anomaly Test Site", tenant="Test Tenant Ltd", term=360,
    start="2026-01-01", rent="9,500", esc="12.0", renewal="YES"))
w("synthetic_data/lease-902.txt", TEMPLATES["beta"].format(
    prop="Anomaly Test Site 2", tenant="Test Tenant Ltd", term=6,
    start="2026-01-01", rent="7,200,000", esc="9.5", renewal="NO"))

wd("synthetic_data/README.md", """
    # Synthetic data

    Generated, deterministic (seed 20260910), and entirely fictional. Three
    template families (alpha / beta / gamma) so trace convergence per family can
    be demonstrated honestly rather than by using twenty copies of one document.

    `lease-901` and `lease-902` are deliberately anomalous - out-of-threshold rent,
    escalation and term - for the anomaly and drift demonstrations.

    **No client data, document, or workflow detail from any engagement appears
    here, ever.** See CONTRIBUTING.md.
""")

print("=== synthetic data: 22 leases ===")
