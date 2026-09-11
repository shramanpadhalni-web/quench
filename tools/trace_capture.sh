#!/bin/bash
# Quench trace capture — discovery harness.
# Appends the raw hook event JSON from stdin to a JSONL file, verbatim.
# MUST always exit 0: a non-zero exit from a PreToolUse hook blocks the tool call.

OUT_DIR="$HOME/.kiro/quench-traces"
mkdir -p "$OUT_DIR"

payload="$(cat)"
printf '%s\n' "$payload" >> "$OUT_DIR/raw.jsonl" 2>/dev/null

exit 0
