#!/usr/bin/env bash
# Corpus driver for the cloud governance sweep.
#
# Purity is only observable where an INPUT RECURS (see DEVIATION D1), so this
# driver deliberately runs a small resource set many times rather than a large
# set once. Ten resources times three passes gives three observations per input;
# twenty resources once gives none.
#
# Every session is verified against ground truth before it is counted: a session
# that produced no tool events was narrated, not executed, and is excluded by
# the preregistration's corpus rules.
#
# Usage:
#   ./run_demo.sh --passes 3 --resources 10
set -uo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

PASSES=3
RESOURCES=10
TIMEOUT=420
TRACE_FILE="${QUENCH_TRACE_FILE:-$HOME/.kiro/quench-traces/raw.jsonl}"
LOG="$ROOT/corpus_results.tsv"

while [ $# -gt 0 ]; do
  case "$1" in
    --passes)    PASSES="$2"; shift 2 ;;
    --resources) RESOURCES="$2"; shift 2 ;;
    --timeout)   TIMEOUT="$2"; shift 2 ;;
    -h|--help)   sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

export PATH="$HOME/.local/bin:$PATH"
command -v kirocrew >/dev/null || { echo "kirocrew not on PATH"; exit 1; }

# A rejected agent spec falls back to the DEFAULT agent silently, producing
# confident fabrications with exit code 0. Refuse to start unless the agent is
# actually registered. See ADR-0000.
if ! kiro-cli agent list 2>&1 | grep -qE '^[[:space:]]+governance-checker'; then
  echo "FATAL: kiro-cli does not list governance-checker." >&2
  echo "The spec was rejected; --agent would resolve to the default agent." >&2
  exit 1
fi

mkdir -p "$(dirname "$TRACE_FILE")" output
[ -f "$LOG" ] || printf 'ts\tpass\tresource\tverdict\ttrace_delta\treason\n' > "$LOG"

total=0; passed=0
echo "governance corpus | passes=$PASSES resources=$RESOURCES"
echo

for pass in $(seq 1 "$PASSES"); do
  echo "--- pass $pass/$PASSES ---"
  for n in $(seq -w 1 "$RESOURCES"); do
    rid="bucket-0$n"
    [ -f "synthetic_data/resources/$rid.json" ] || continue

    before=$(wc -l < "$TRACE_FILE" 2>/dev/null || echo 0)
    lines_before=$(wc -l < output/findings.jsonl 2>/dev/null || echo 0)

    timeout "$TIMEOUT" kirocrew chat --agent governance-checker \
      -m "Check $rid" >/dev/null 2>&1

    after=$(wc -l < "$TRACE_FILE" 2>/dev/null || echo 0)
    lines_after=$(wc -l < output/findings.jsonl 2>/dev/null || echo 0)
    delta=$((after - before))

    if [ "$delta" -le 0 ]; then
      verdict="FAIL"; reason="no_trace"            # narrated, not executed
    elif [ "$lines_after" -le "$lines_before" ]; then
      verdict="FAIL"; reason="no_finding_recorded"
    else
      # The recorded finding must match what check.py computes independently.
      expected=$(python3 check.py "$rid" | python3 -c \
        "import json,sys; print(json.load(sys.stdin)['compliant'])")
      actual=$(tail -1 output/findings.jsonl | python3 -c \
        "import json,sys; print(json.load(sys.stdin)['compliant'])")
      if [ "$expected" = "$actual" ]; then
        verdict="PASS"; reason="ok"
      else
        verdict="FAIL"; reason="mismatch exp=$expected got=$actual"
      fi
    fi

    total=$((total + 1))
    [ "$verdict" = "PASS" ] && passed=$((passed + 1))
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$(date -uIs)" "$pass" "$rid" "$verdict" "$delta" "$reason" >> "$LOG"
    printf '  %-12s %-5s delta=%-4s %s\n' "$rid" "$verdict" "$delta" "$reason"
  done
done

echo
echo "sessions: $passed/$total verified"
echo "trace events: $(wc -l < "$TRACE_FILE")"
[ "$passed" -eq "$total" ] || echo "NOTE: failed sessions are excluded by preregistration rule."
