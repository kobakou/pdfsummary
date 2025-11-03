#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${PDFSUMMARY_APP_DIR:-$(cd "$(dirname "$0")"/.. && pwd)}"
# 旧既定パスへのフォールバック（存在確認）
if [ ! -d "${APP_DIR}/pdfsummary" ]; then
    if [ -d "/Users/Kou.Kobayashi/Workspace/dev/pdfsummary/pdfsummary" ]; then
        APP_DIR="/Users/Kou.Kobayashi/Workspace/dev/pdfsummary"
    fi
fi
# PYTHON解決: 環境変数 > venv > システム
if [ -n "${PYTHON_BIN:-}" ]; then
	PYTHON_BIN="${PYTHON_BIN}"
elif [ -x "${APP_DIR}/.venv/bin/python3" ]; then
	PYTHON_BIN="${APP_DIR}/.venv/bin/python3"
else
	PYTHON_BIN="python3"
fi

# 引数またはクリップボードからPDFパスを取得（クリップボード優先）
PDF_PATH="${1-}"
_clip_raw=$(pbpaste | head -n1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//') || true
if [ -z "${PDF_PATH}" ] && [ -n "${_clip_raw}" ]; then
	PDF_PATH="$(${PYTHON_BIN} - <<'PY' 2>/dev/null
import os, sys, urllib.parse
s = sys.stdin.read().strip()
if s.startswith('file://'):
	s = s[7:]
	if s.startswith('localhost/'):
		s = s[10:]
	s = urllib.parse.unquote(s)
	if not s.startswith('/'):
		s = '/' + s
if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
	s = s[1:-1]
s = os.path.abspath(os.path.expanduser(s))
print(s)
PY
<<< "${_clip_raw}" || true)"
fi

# 検証
if [ -z "${PDF_PATH}" ] || [ ! -f "${PDF_PATH}" ]; then
	echo "PDFファイルが見つかりません: ${PDF_PATH:-<empty>}" >&2
	echo "使い方: ./obsidian/pdfsummary.sh /absolute/path/to/file.pdf" >&2
	echo "または クリップボードにPDFのPOSIXパス/file://URL をコピーして実行" >&2
	exit 1
fi
case "${PDF_PATH}" in
	*.pdf|*.PDF) : ;;
	*) echo "警告: PDF拡張子ではありません: ${PDF_PATH}" >&2 ;;
esac

# Python CLI 実行
CLI_PATH="${APP_DIR}/pdfsummary/cli.py"
MD_OUTPUT="$(
	"${PYTHON_BIN}" "${CLI_PATH}" \
		--llm "${PDFSUMMARY_LLM:-auto}" \
		--model "${PDFSUMMARY_MODEL:-}" \
		--cmd "${PDFSUMMARY_LLM_CMD:-}" \
		"${PDF_PATH}"
)"

# 保存先（Vault直下を想定: カレントがVault）
VAULT_DIR="${VAULT_DIR:-$PWD}"
OUT_DIR="${VAULT_DIR}/clips"
mkdir -p "${OUT_DIR}"
base="$(basename "${PDF_PATH}" .pdf)"
base="${base%.PDF}"
DATE="$(date +%F)"
fname="${base}-${DATE}.md"
out_path="${OUT_DIR}/${fname}"
c=1
while [ -e "${out_path}" ]; do
	out_path="${OUT_DIR}/${base}-${DATE}-${c}.md"
	c=$((c+1))
done

printf '%s' "${MD_OUTPUT}" > "${out_path}"
printf '%s' "${MD_OUTPUT}" | pbcopy

echo "Created: ${out_path}"
