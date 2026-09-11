#!/usr/bin/env bash
# Installs Quench's trace-capture hooks.
#
# Uses Crew's supported autoimport seam - NOT by editing any file Crew owns.
# ``agent.kiro_hooks_autoimport`` (default true) scans ``agent.kiro_hooks_dir``
# (default ~/.kiro/hooks) for executable scripts and merges them into the
# generated agent config on every gateway start.
#
# This matters: ~/.kiro/agents/kirocrew.json is REGENERATED on every start, so
# hand-edits there are silently wiped. See ADR-0000, empirical addendum.
set -euo pipefail

HOOKS_DIR="${QUENCH_HOOKS_DIR:-$HOME/.kiro/hooks}"
TRACE_FILE="${QUENCH_TRACE_FILE:-$HOME/.kiro/quench-traces/raw.jsonl}"

mkdir -p "$HOOKS_DIR" "$(dirname "$TRACE_FILE")"

install_hook() {
  local suffix="$1" event="$2"
  local target="$HOOKS_DIR/quench-trace-${suffix}.sh"
  cat > "$target" <<HOOK
#!/bin/bash
# event: ${event}
# Quench trace capture. Installed by scripts/install_hooks.sh - do not edit.
# MUST always exit 0: a nonzero preToolUse exit blocks the tool call.
OUT="${TRACE_FILE}"
mkdir -p "\$(dirname "\$OUT")"
cat >> "\$OUT" 2>/dev/null
printf '\n' >> "\$OUT" 2>/dev/null
exit 0
HOOK
  chmod +x "$target"
  echo "  installed $target  (${event})"
}

install_hook post   postToolUse
install_hook pre    preToolUse
install_hook prompt userPromptSubmit

echo
echo "Restart the gateway for Crew to pick these up:  kirocrew restart"
