#!/bin/bash
# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Summarize PDF to Markdown
# @raycast.mode fullOutput

# Optional parameters:
# @raycast.icon 📄
# @raycast.packageName PDF Tools
# @raycast.argument1 { "type": "file", "dataType": "public.pdf", "placeholder": "PDF file" }
# @raycast.argument2 { "type": "text", "placeholder": "pages (e.g. 1,3-5)", "optional": true }

set -euo pipefail

PDF_PATH="$1"
PAGES="${2-}"

ROOT_DIR="${PDFSUMMARY_APP_DIR:-$(cd "$(dirname "$0")"/.. && pwd)}"
if [[ ! -d "$ROOT_DIR/pdfsummary" ]]; then
  if [[ -d "/Users/Kou.Kobayashi/Workspace/dev/pdfsummary/pdfsummary" ]]; then
    ROOT_DIR="/Users/Kou.Kobayashi/Workspace/dev/pdfsummary"
  fi
fi
SCRIPT="${PDFSUMMARY_SCRIPT:-"$ROOT_DIR/pdfsummary.py"}"

if [[ ! -f "$SCRIPT" ]]; then
  echo "script not found: $SCRIPT" >&2
  exit 1
fi

if [[ -z "$PAGES" ]]; then
  /usr/bin/env python3 "$SCRIPT" "$PDF_PATH" --stdout --language 日本語
else
  /usr/bin/env python3 "$SCRIPT" "$PDF_PATH" --pages "$PAGES" --stdout --language 日本語
fi


