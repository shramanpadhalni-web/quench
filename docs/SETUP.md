# Setup

**A tested runbook.** Every command here was run on a clean machine on
2026-09-09 and produced the stated result. Nothing is written from memory or
copied from upstream docs without verification.

**Goal:** clean machine → `kirocrew doctor` clean → ready to build Quench.

> ### Upstream docs are wrong in three places — read this box first
>
> We hit all three today. They cost an hour between them.
>
> | Upstream says | Reality |
> |---|---|
> | `pip install kirocrew` | **No such PyPI package.** `kirocrew`, `kiro-crew`, `kiro_crew` all 404. Use the signed installer in §4. |
> | "kiro-cli is installed automatically on first launch" | **It is not.** Install it yourself — §5. |
> | (kiro-cli prerequisites) | `unzip` is required but undeclared. The installer fails with `Missing required dependencies: unzip`. |

---

## 0. Platform requirement — non-negotiable

**Linux or macOS. On Windows, WSL2.**

Kiro Crew runs natively on Windows, but its OS-level filesystem sandbox does not:

> "The OS-level filesystem sandbox (Linux namespaces / macOS Seatbelt) is not
> available on Windows; every other feature works." — Crew installation docs

Quench's central security guarantee (§7 of the architecture brief) is that Mill
executes through the *same* sandbox a live agent turn would. On Windows there is
no sandbox to execute through, so the guarantee could only be asserted, never
tested. The deploy target is Linux regardless.

Full reasoning: [`adr/0005-linux-required-for-sandbox-parity.md`](adr/0005-linux-required-for-sandbox-parity.md)

---

## 1. Windows only — WSL2 + Ubuntu

Skip to §2 on Linux/macOS.

### 1.1 Check what exists

Open **PowerShell** (Windows key → `powershell` → Enter):

```powershell
wsl --version
wsl -l -v
```

- No version output → run `wsl --install`, reboot, come back.
- **A `docker-desktop` entry is NOT a usable distro.** It is Docker Desktop's
  internal utility VM. You still need a real one.

### 1.2 Install Ubuntu

```powershell
wsl --install -d Ubuntu-24.04 --no-launch
wsl --set-default Ubuntu-24.04
```

`--no-launch` avoids an install-time interactive prompt. ~600 MB download.

### 1.3 Create your Linux user — interactive, must be a human

```powershell
wsl -d Ubuntu-24.04
```

- Short lowercase username.
- Password, twice. **No characters appear as you type. This is normal.**
- You land at `you@MACHINE:~$`. Type `exit`.

Verify:

```powershell
wsl -d Ubuntu-24.04 -- id
```

Expect `uid=1000(you) ... groups=...,27(sudo),...`. The `sudo` group matters.

### 1.4 Keep the repo on the Linux filesystem

**Clone to `~/quench`. Never work from `/mnt/c/...`.**

Cross-filesystem I/O through `/mnt/c` is slow enough to distort the timing
measurements Quench exists to produce, and file-watching misbehaves across the
boundary.

Browse from Windows at `\\wsl.localhost\Ubuntu-24.04\home\<user>\quench` —
fine for editing; run every command inside WSL.

---

## 2. Toolchain

Everything below runs **inside Linux** (`wsl -d Ubuntu-24.04`, or a normal
terminal on Linux/macOS).

```bash
sudo apt-get update
sudo apt-get install -y python3.12-venv python3-pip curl ca-certificates git unzip

# Node 22 — only needed to build the dashboard bundle
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
```

**`unzip` is not optional** — kiro-cli's installer requires it and does not say so.

Optional but recommended:

```bash
sudo apt-get install -y pipx
```

Crew's installer uses `pipx` when present and falls back to a managed venv
otherwise. With pipx you also get `pipx inject kirocrew <pkg>`, which is how
Quench's in-gateway backend code will later be installed into Crew's environment.

Verify:

```bash
python3 --version   # 3.12.x
node --version      # v22.x
git --version
unzip -v | head -1
```

**Rust is not required for v1** — Mill ships in Python behind a port. See
`adr/0002-*`.

### Confirm the sandbox prerequisite

```bash
uname -r    # must be Linux; on WSL: ...-microsoft-standard-WSL2
sysctl kernel.unprivileged_userns_clone 2>/dev/null || echo "default (enabled)"
```

Unprivileged user namespaces are what Crew's sandbox is built on. Without them,
§7's guarantee does not hold.

> **Note on PEP 668:** Ubuntu 24.04 refuses system-wide `pip install`
> (`externally-managed-environment`). This does not affect us — Crew's installer
> provisions its own interpreter — but it is why a bare `pip install` of anything
> will fail here.

---

## 3. Kiro Crew — the signed installer

**Not pip.** The real installer:

```bash
curl -fsSL https://download.crew.kiro.dev/cli.sh | sh
```

What it does, verified by reading the script before running it:

- Resolves the release channel feed and **verifies its RSA-SHA256 signature**
  against a public key pinned in the script
- Downloads the wheel over HTTPS and **verifies its SHA-256** against the signed
  digest — there is no unsigned or checksum-only fallback
- Provisions its own CPython (python-build-standalone via `uv`) rather than using
  system Python
- Installs via `pipx` if present, else a managed venv
- **Requires no sudo.** Everything lands in user-owned directories.

Useful flags: `--channel <stable|insider|nightly>`, `--version X.Y.Z`,
`--system-python` (opt out of the managed interpreter; sticky across updates).

Verify:

```bash
export PATH="$HOME/.local/bin:$PATH"
kirocrew --version      # 0.5.0 at time of writing
```

---

## 4. kiro-cli — the agent backend

Crew's docs claim this installs automatically. **It does not.**

```bash
curl -fsSL https://cli.kiro.dev/install | bash
```

Requires `unzip` (see §2). Installs three binaries into `~/.local/bin`:
`kiro-cli`, `kiro-cli-chat`, `kiro-cli-term` — roughly 1 GB total.

```bash
kiro-cli --version      # 2.21.2 at time of writing
```

---

## 5. Log in — interactive

```bash
kiro-cli login
```

- Choose **Use with Builder ID** (free; no AWS account, no card).
- It prints a code and a URL. Open the URL, confirm the code, sign in.
- The sign-in page offers Google / Apple / GitHub / email — any of them creates
  or links your Builder ID.

> **If the first attempt fails with "authorization failed":** the device code
> expires in a few minutes, and creating a Builder ID for the first time usually
> takes longer than that. Simply run `kiro-cli login` again — the second attempt
> is fast because the account now exists.
>
> If it keeps failing, check for clock drift between WSL and Windows — skew
> breaks token auth silently:
> ```bash
> date -u    # compare against Windows
> ```

Verify: `kirocrew doctor` should show `kiro login: ✅`.

---

## 6. Configure Crew — interactive

**Run this from the project root** — setup records the project directory:

```bash
cd ~/quench
kirocrew setup
```

Decline Slack / Discord / Telegram / WhatsApp prompts; Quench needs none of them.

---

## 7. Verify

```bash
kirocrew doctor
```

**Expected-clean:**

```
edition: standalone · kiro-cli ✅ · kiro login ✅ · git ✅ · node ✅
config dir ✅ · data home ✅ · agent config ✅ · project dir ✅
dashboard: http://localhost:5476, bind 127.0.0.1 (loopback only)
```

**Expected failures you should ignore** — voice-input extras, irrelevant to Quench:

```
❌ speech recogniser (stt_extra_missing)
❌ ffmpeg not found
```

Then start the gateway and confirm it responds:

```bash
kirocrew gateway        # foreground; Ctrl-C to stop
```

Dashboard at <http://localhost:5476>. WSL forwards localhost to Windows
automatically, so open it in your normal browser.

Also confirm the audit log works — Quench depends on it:

```bash
kirocrew security events
kirocrew security verify
```

`gateway` runs in the foreground and dies with the terminal. `kirocrew service
install` registers a systemd unit instead (needs sudo, survives logout, restarts
on crash). **Run only one — both bind the same port.**

---

## 8. Where everything lives

| Path | Contents |
|---|---|
| `~/.kiro/crew/` | All Crew state — **the data home** |
| `~/.kiro/crew/config.json` | Gateway config, incl. the `hooks` section |
| `~/.kiro/crew/security_events.jsonl` | Signed Event Log — HMAC-chained, append-only |
| `~/.kiro/crew/security_events.d/` | Rotated SEL segments |
| `~/.kiro/crew/trust/sel_hmac.key` | SEL signing key — deliberately outside the log dir |
| `~/.kiro/crew/security_policy.json` | Governance policy ceiling |
| `~/.kiro/crew/profiles/` | Per-surface governance profiles |
| `~/.kiro/crew/logs/crash-dumps/` | Loop-stall crash dumps |
| `~/.kiro/crew/apps/{name}/.app_secret` | Per-app secret → short-lived token |
| `~/.kiro/crew-python/` | Crew's **managed CPython** (see below) |
| `~/.kiro/agents/kirocrew.json` | Default agent spec |
| `~/.kiro/settings/` | Kiro-level settings |
| `~/.kiro/hooks/*.json` | User-scoped hooks — **where Quench's trace hook goes** |
| `~/.local/bin/` | `kirocrew`, `kiro-cli`, `kiro-cli-chat`, `kiro-cli-term` |
| `~/.local/share/pipx/venvs/kirocrew/` | Crew's pipx venv |

Quench adds `~/.kiro/crew/ingots/` for the Vault.

> **Do not lose `~/.kiro/crew/`.** It holds every trace, every sealed artifact,
> and every proof this project accumulates. The Docker deployment mounts it as a
> volume for exactly this reason.

### Crew runs on its own interpreter — this matters for us

```
~/.kiro/crew-python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12
```

Crew does **not** use system Python. When Quench's app backend later runs
in-gateway (`backend.hooks`), that managed interpreter is the target — not
`/usr/bin/python3`. Install into it with `pipx inject kirocrew <pkg>`.

---

## 9. Quench dev environment

```bash
git clone <repo-url> ~/quench
cd ~/quench
./scripts/setup.sh
```

`scripts/setup.sh` is a contract: **one command, working environment.** If it
grows a "and then manually…" step, fix the script, not this page.

---

## 10. VS Code

Install the **WSL** extension (`ms-vscode-remote.remote-wsl`), then from
PowerShell:

```powershell
wsl -d Ubuntu-24.04 code ~/quench
```

A blue/green **WSL: Ubuntu-24.04** badge appears in the bottom-**left** of the
status bar. No badge → you are editing Windows files and builds will misbehave.

Sanity check in the VS Code terminal (`` Ctrl+` ``):

```bash
pwd     # /home/<user>/quench   ✅
        # /mnt/c/... or C:\...  ❌ reconnect
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `pip install kirocrew` → "No matching distribution" | Package doesn't exist. Use §3. |
| kiro-cli installer → `Missing required dependencies: unzip` | `sudo apt-get install -y unzip` |
| `kiro-cli login` → "authorization failed" | Code expired. Re-run it; second try is fast. Then check clock drift. |
| `kirocrew doctor` → sandbox unavailable | You're on Windows, not WSL. `uname -a` must say Linux. |
| Repo under `/mnt/c/...` | Move to `~/`. See §1.4. |
| `wsl -l -v` shows only `docker-desktop` | Not a usable distro. Install Ubuntu — §1.2. |
| Bare `wsl` opens the wrong distro | `wsl --set-default Ubuntu-24.04` |
| `docker info` → `dockerDesktopLinuxEngine ... cannot find the file` | Docker Desktop not running. Deployment-phase only; ignore for dev. |
| Port 5476 in use | `kirocrew gateway --port N`, or `KIROCREW_PORT=N` |
| `pip install` → `externally-managed-environment` | PEP 668. Use pipx or a venv; never `--break-system-packages`. |

### Scripting WSL from Windows

Nested quotes get mangled by Git Bash's argument translation. Pipe a script over
stdin instead of passing it inline:

```bash
wsl -d Ubuntu-24.04 -- bash -s < script.sh
```

And `sudo` cannot prompt for a password in that context — split privileged steps
into a separate `-u root` invocation:

```bash
wsl -d Ubuntu-24.04 -u root -- bash -s < privileged.sh
wsl -d Ubuntu-24.04 -u <user> -- bash -s < unprivileged.sh
```

---

## Open question — do not treat as settled

`kirocrew doctor` reports `jail: no jail provider (public edition)`, and
`kirocrew --help` states `--no-jail` is "a no-op on the public edition, which has
no jail backend."

That is the **process-isolation jail**, which is *not* the same thing as the
`agent.sandbox` OS sandbox (namespaces/seatbelt) that §7's security guarantee
depends on. But the two are close enough that the OS sandbox must be confirmed
genuinely active on the public edition **before** the Mill sandbox adapter is
built on that assumption.

Tracked in `adr/0000-crew-seam-verification.md`. Verify, then update this section
with the answer.

---

## Verified reference environment

Built and confirmed working **2026-09-09**. Diff against this when something breaks.

| | Value |
|---|---|
| Windows host | 11 Home Single Language, 10.0.26200.9168 |
| WSL | 2.7.11.0, kernel 6.18.33.2 |
| Distro | Ubuntu 24.04.4 LTS (`Ubuntu-24.04`), version 2, default |
| Linux kernel | 6.18.33.2-microsoft-standard-WSL2 |
| System Python | 3.12.3 |
| Crew managed Python | 3.12.13 (`~/.kiro/crew-python/`) |
| Node / npm | v22.23.2 / 10.9.8 |
| Git (Linux) | 2.43.0 |
| pipx | 1.4.3 |
| unzip | 6.00 |
| **kirocrew** | **0.5.0** (stable channel) |
| **kiro-cli** | **2.21.2** |
| Unprivileged userns | enabled (default) |
| Dashboard | http://localhost:5476, bind 127.0.0.1 |
| Repo | `~/quench` on the Linux filesystem |
