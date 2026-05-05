#!/bin/bash
# ArXiv Digest Daily Resend Script
# Usage: bash resend_daily_digest.sh [date]
# If no date provided, uses today's date.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MEMORY_DIR="$SKILL_DIR/memory"

# Resolve date
DATE="${1:-$(date +%Y-%m-%d)}"
DIGEST_FILE="$MEMORY_DIR/digests/${DATE}.md"
TARGET="qqbot:c2c:1FB5F196F88F0DFA248D864C0F7E5A42"

if [[ ! -f "$DIGEST_FILE" ]]; then
    echo "❌ Digest not found for $DATE: $DIGEST_FILE"
    echo "   Run: python3 scripts/generate_digest.py --raw && (evaluate papers) && python3 scripts/generate_digest.py --rerank-json memory/llm_scores.json --output memory/daily_digest.md"
    exit 1
fi

# Count lines and extract summary from the digest
TOTAL_LINES=$(wc -l < "$DIGEST_FILE")
echo "📰 Resending ArXiv Daily Digest — $DATE ($TOTAL_LINES lines)"

# Send the digest via QQBot
openclaw message send \
    --channel qqbot \
    --target "$TARGET" \
    -m "$(cat "$DIGEST_FILE")" \
    --verbose

echo "✅ Sent via QQ Bot."
