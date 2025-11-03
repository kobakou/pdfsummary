#!/usr/bin/env bash
# @raycast.schemaVersion 1
# @raycast.title PDF要約（Markdown）
# @raycast.description 指定PDFをLLMで要約しMarkdownを出力
# @raycast.mode fullOutput
# @raycast.packageName PDF Tools
# @raycast.icon 📄
# @raycast.argument1 {"type": "file", "placeholder": "PDF file", "extensions": ["pdf"]}

set -euo pipefail
PDF_PATH="${1-}"
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

# 1) クリップボードの内容がPDFパス/URLなら最優先で使用（POSIX絶対パスに正規化）
_clip_raw=$(pbpaste | head -n1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//') || true
if [ -n "${_clip_raw}" ]; then
	_clip_norm="$(${PYTHON_BIN} - <<'PY' 2>/dev/null
import os, sys, urllib.parse
s = sys.stdin.read().strip()
# file:// URL をパスへ
if s.startswith('file://'):
	s = s[7:]
	if s.startswith('localhost/'):
		s = s[10:]
	s = urllib.parse.unquote(s)
	if not s.startswith('/'):
		s = '/' + s
# 引用符除去
if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
	s = s[1:-1]
# ~ 展開 + 絶対パス化
s = os.path.abspath(os.path.expanduser(s))
print(s)
PY
<<< "${_clip_raw}" || true)"
	if [ -f "${_clip_norm}" ]; then
		case "${_clip_norm}" in
			*.pdf|*.PDF) PDF_PATH="${_clip_norm}" ;;
			*) : ;;
		esac
	fi
fi

# 2) 引数が無く、かつクリップボードでも決まらなければファイルピッカー
if [ -z "${PDF_PATH}" ]; then
	PDF_PATH=$(osascript -e 'set theFile to choose file of type {"com.adobe.pdf"} with prompt "PDFを選択"' -e 'POSIX path of theFile')
fi

# パス検証
if [ ! -f "${PDF_PATH}" ]; then
	echo "PDFファイルが見つかりません: ${PDF_PATH}" >&2
	exit 1
fi
case "${PDF_PATH}" in
	*.pdf|*.PDF) : ;;
	*)
		echo "PDF拡張子ではありません: ${PDF_PATH}" >&2
		;;
	;
esac

# デバッグ（必要に応じて）: DEBUG=1 で有効化
if [ "${DEBUG:-0}" != "0" ]; then
	echo "[debug] PDF_PATH=${PDF_PATH}" >&2
	echo "[debug] CLIPBOARD_RAW=${_clip_raw:-}" >&2
	echo "[debug] PYTHON_BIN=${PYTHON_BIN}" >&2
fi

# LLM設定（環境変数で上書き可能）
: "${PDFSUMMARY_LLM:=auto}"
: "${PDFSUMMARY_MODEL:=}"
: "${PDFSUMMARY_LLM_CMD:=}"

# 実行してMarkdownを取得し、表示＆クリップボードへコピー
_md_output="$(
	"${PYTHON_BIN}" "${APP_DIR}/pdfsummary/cli.py" \
		--llm "${PDFSUMMARY_LLM}" \
		--model "${PDFSUMMARY_MODEL}" \
		--cmd "${PDFSUMMARY_LLM_CMD}" \
		"${PDF_PATH}"
)"

# Raycast出力
printf '%s\n' "${_md_output}"
# クリップボードへ
printf '%s' "${_md_output}" | pbcopy

# 末尾に簡易通知（stderrに出すことでMarkdown本文を汚さない）
if [ "${DEBUG:-0}" != "0" ]; then
	echo "[debug] Markdownをクリップボードにコピーしました" >&2
fi
