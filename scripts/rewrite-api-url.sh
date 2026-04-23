#!/usr/bin/env bash
# Rewrite the API URL baked into the production JS bundle.
#
# Usage: ./scripts/rewrite-api-url.sh https://new-backend.example.com
#
# Updates assets/index-B-irygFq.js in place. Commit and redeploy afterward.
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <new-api-url>" >&2
  exit 1
fi

NEW_URL="$1"
BUNDLE="$(dirname "$0")/../assets/index-B-irygFq.js"

if [ ! -f "$BUNDLE" ]; then
  echo "Bundle not found at $BUNDLE" >&2
  exit 1
fi

# Extract the current backend URL by finding the *.fly.dev / *.devinapps.com
# / https:// URL that is NOT one of the known third-party libs.
# For safety, this script prompts for the current URL if it can't detect it.
CURRENT="$(grep -oE 'https://[a-z0-9-]+\.(fly\.dev|devinapps\.com|onrender\.com|up\.railway\.app|herokuapp\.com)' "$BUNDLE" | sort -u | head -1 || true)"

if [ -z "$CURRENT" ]; then
  read -r -p "Could not auto-detect current API URL. Enter it manually: " CURRENT
fi

echo "Rewriting $CURRENT -> $NEW_URL in $BUNDLE"
sed -i.bak "s|$CURRENT|$NEW_URL|g" "$BUNDLE"
rm -f "$BUNDLE.bak"
echo "Done. Remember to commit and redeploy."
