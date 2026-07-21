#!/bin/bash
# deploy_bot_pages.sh — Build and deploy bot dashboard pages
#
# Usage:
#   ./deploy_bot_pages.sh              # Build all bots
#   ./deploy_bot_pages.sh fx           # Build only FX
#   ./deploy_bot_pages.sh fx-v2        # Build v2 parallel test page
#
# This script:
# 1. Generates bot pages from template (build_bot_pages.py)
# 2. Builds final HTML with nav/theme (build.py)
# 3. Verifies the output files exist
# 4. Reloads Caddy if running

set -euo pipefail

SITE_DIR="/root/.hermes/site"
cd "$SITE_DIR"

echo "=========================================="
echo " Bot Dashboard Deploy"
echo " $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=========================================="

# Step 1: Generate bot pages from template
BOTS="$@"
if [ -z "$BOTS" ]; then
    echo ""
    echo "[1/3] Building all bot pages from template..."
    python3 build_bot_pages.py
else
    echo ""
    echo "[1/3] Building bot pages: $BOTS"
    python3 build_bot_pages.py $BOTS
fi

# Step 2: Build final HTML
echo ""
echo "[2/3] Building site (build.py)..."
python3 build.py

# Step 3: Verify output
echo ""
echo "[3/3] Verifying output..."
ERRORS=0
for bot_json in src/data/bots/*.json; do
    bot_id=$(python3 -c "import json; print(json.load(open('$bot_json'))['bot_id'])")
    built="_build/${bot_id}.html"
    if [ -f "$built" ]; then
        lines=$(wc -l < "$built")
        echo "  ✅ $built ($lines lines)"
    else
        echo "  ❌ MISSING: $built"
        ERRORS=$((ERRORS + 1))
    fi
done

# Step 4: Reload Caddy if running
if systemctl is-active --quiet caddy 2>/dev/null; then
    echo ""
    echo "Reloading Caddy..."
    systemctl reload caddy 2>/dev/null && echo "  ✅ Caddy reloaded" || echo "  ⚠️  Caddy reload failed (non-critical)"
fi

echo ""
if [ $ERRORS -eq 0 ]; then
    echo "✅ Deploy complete — all pages built successfully."
    echo ""
    echo "Live URLs:"
    for bot_json in src/data/bots/*.json; do
        bot_id=$(python3 -c "import json; print(json.load(open('$bot_json'))['bot_id'])")
        echo "  https://hermes.nexusfortis.org/${bot_id}"
    done
else
    echo "❌ Deploy completed with $ERRORS error(s)."
    exit 1
fi
