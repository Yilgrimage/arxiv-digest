#!/usr/bin/env bash
# ArXiv Digest Pipeline: collect → LLM evaluate → deliver
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$SKILL_DIR/scripts"
MEMORY="$SKILL_DIR/memory"

echo "[1/3] Collecting raw paper data..."
python3 "$SCRIPTS/generate_digest.py" --raw

echo "[2/3] Raw data ready: $MEMORY/daily_raw.json"
echo "    → Next: LLM evaluates all papers and writes scores to $MEMORY/llm_scores.json"

echo "[3/3] Generating final digest..."
python3 "$SCRIPTS/generate_digest.py" \
  --rerank-json "$MEMORY/llm_scores.json" \
  --output "$MEMORY/daily_digest.md"

echo "Done. Final report: $MEMORY/daily_digest.md"
