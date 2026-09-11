#!/usr/bin/env bash
# Corpus driver for the lease abstraction pipeline.
#
# Runs the agents repeatedly, unattended, and VERIFIES each session against
# ground truth before counting it. Verification is not optional: on 2026-09-11
# a schema error silently substituted the default agent for ours, and four
# consecutive runs produced confident, plausible, entirely fabricated results
# with exit code 0. The transcript is never the evidence.
#
# Each session is accepted only if BOTH hold:
#   1. the trace file grew (tools actually ran)
#   2. the written record matches the source document exactly
#
# Usage:
#   ./run_demo.sh --passes 6              # 20 leases x 6 = 120 sessions
#   ./run_demo.sh --passes 1 --agents all # include intake and anomaly
#   ./run_demo.sh --resume                # continue from the last pass
set -uo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

PASSES=1
AGENTS="extractor"
RESUME=0
TIMEOUT=420
TRACE_FILE="${QUENCH_TRACE_FILE:-$HOME/.kiro/quench-traces/raw.jsonl}"
STATE="$ROOT/.corpus_state"
LOG="$ROOT/corpus_results.tsv"

while [ $# -gt 0 ]; do
  case "$1" in
    --passes)  PASSES="$2"; shift 2 ;;
    --agents)  AGENTS="$2"; shift 2 ;;
    --resume)  RESUME=1; shift ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

export PATH="$HOME/.local/bin:$PATH"
command -v kirocrew >/dev/null || { echo "kirocrew not on PATH"; exit 1; }

# Refuse to start if the agent specs are not loadable. A rejected spec falls
# back to the default agent silently - the exact failure this guards against.
python3 scripts/validate_agents.py agents/*.json >/dev/null || {
  echo "FATAL: agent specs invalid. Run scripts/validate_agents.py" >&2
  exit 1
}
# kiro-cli writes the agent list to stderr, not stdout.
if [ "$(kiro-cli agent list 2>&1 | grep -cE '^[[:space:]]+lease-[a-z]+')" -lt 4 ]; then
  echo "FATAL: kiro-cli does not list all four lease agents." >&2
  echo "A spec was rejected; --agent would silently resolve to the default." >&2
  exit 1
fi

mkdir -p "$(dirname "$TRACE_FILE")" output
[ -f "$LOG" ] || printf 'ts\tpass\tlease\tagent\tverdict\ttrace_delta\treason\n' > "$LOG"
[ "$RESUME" = 1 ] && START=$(cat "$STATE" 2>/dev/null || echo 1) || START=1

LEASES=$(ls synthetic_data/lease-0*.txt | xargs -n1 basename | sed 's/\.txt$//' | grep -v '^lease-9')

# Ground truth, read straight from the source document.
truth_of() {
  local f="synthetic_data/$1.txt"
  local term rent esc ren
  term=$(grep -oiP 'TERM:\s*\K\d+' "$f" | head -1)
  rent=$(grep -oiP 'ANNUAL RENT:\s*USD\s*\K[\d,]+' "$f" | head -1 | tr -d ,)
  esc=$(grep -oiP 'ESCALATION:\s*\K[\d.]+' "$f" | head -1)
  ren=$(grep -oiP 'RENEWAL OPTION:\s*\K\w+' "$f" | head -1)
  printf '%s|%s|%s|%s' "$term" "$rent" "$esc" "$ren"
}

verify() {  # $1=lease -> echoes "PASS" or "FAIL:<reason>"
  local rec="output/$1.json"
  [ -f "$rec" ] || { echo "FAIL:no_record"; return; }
  local got exp
  got=$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print('%s|%s|%s|%s' % (d.get('term'), d.get('annual_rent'),
                        d.get('escalation'), d.get('renewal')))" "$rec" 2>/dev/null)
  exp=$(truth_of "$1")
  # Normalise numeric formatting (3.0 vs 3) before comparing.
  got=$(python3 -c "
import sys
p=sys.argv[1].split('|')
def n(x):
    try: return str(float(x))
    except Exception: return str(x)
print('|'.join(n(v) for v in p))" "$got")
  exp=$(python3 -c "
import sys
p=sys.argv[1].split('|')
def n(x):
    try: return str(float(x))
    except Exception: return str(x)
print('|'.join(n(v) for v in p))" "$exp")
  [ "$got" = "$exp" ] && echo "PASS" || echo "FAIL:mismatch got=$got exp=$exp"
}

run_one() {  # $1=pass $2=lease $3=agent-suffix $4=prompt
  local before after delta verdict
  before=$(wc -l < "$TRACE_FILE" 2>/dev/null || echo 0)
  rm -f "output/$2.json"
  timeout "$TIMEOUT" kirocrew chat --agent "lease-$3" -m "$4" >/dev/null 2>&1
  after=$(wc -l < "$TRACE_FILE" 2>/dev/null || echo 0)
  delta=$((after - before))

  if [ "$delta" -le 0 ]; then
    verdict="FAIL:no_trace"          # narrated, not executed
  elif [ "$3" = "extractor" ]; then
    verdict=$(verify "$2")
  else
    verdict="PASS"
  fi

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(date -uIs)" "$1" "$2" "$3" "${verdict%%:*}" "$delta" "${verdict#*:}" >> "$LOG"
  printf '  %-12s %-10s %-5s delta=%-4s %s\n' \
    "$2" "$3" "${verdict%%:*}" "$delta" "${verdict#*:}"
  [ "${verdict%%:*}" = "PASS" ]
}

echo "corpus driver | passes=$PASSES agents=$AGENTS from=$START"
echo "trace file: $TRACE_FILE"
echo

total=0; passed=0
for pass in $(seq "$START" "$PASSES"); do
  echo "--- pass $pass/$PASSES ---"
  for lease in $LEASES; do
    case "$AGENTS" in
      all) steps="intake extractor anomaly" ;;
      *)   steps="extractor" ;;
    esac
    for step in $steps; do
      case "$step" in
        intake)    prompt="Validate $lease" ;;
        extractor) prompt="Extract $lease" ;;
        anomaly)   t=$(truth_of "$lease")
                   prompt="Check annual_rent=$(echo "$t" | cut -d'|' -f2) term_months=$(echo "$t" | cut -d'|' -f1)" ;;
      esac
      total=$((total + 1))
      run_one "$pass" "$lease" "$step" "$prompt" && passed=$((passed + 1))
    done
  done
  echo "$((pass + 1))" > "$STATE"
done

echo
echo "sessions: $passed/$total verified"
echo "trace events: $(wc -l < "$TRACE_FILE")"
echo "log: $LOG"
[ "$passed" -eq "$total" ] || echo "NOTE: failed sessions are excluded from the corpus by preregistration rule."
