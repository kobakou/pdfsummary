# pdfsummary

Mac上でPDFからテキストを抽出し、LLMで要約してMarkdownを出力するCLI。
Raycast Script Commandや、Shell Script等でObisidianからの実行を想定。

> [!IMPORTANT]
> LLMバックエンドについては、ローカルのollama以外は未確認です。

## セットアップ

```bash
# リポジトリルートへ移動
cd /path/to/pdfsummary
# 任意: 以後のスクリプトで参照されるアプリディレクトリ
export PDFSUMMARY_APP_DIR="$(pwd)"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使い方（CLI）

```bash
# 標準出力にMarkdownを出す（単一パス要約が既定）
python3 pdfsummary/cli.py --llm auto sample.pdf

# ファイルに保存
python3 pdfsummary/cli.py --llm auto --out output.md sample.pdf

# モデル指定（ollama の例）
PDFSUMMARY_LLM=ollama PDFSUMMARY_MODEL=llama3.1 \
python3 pdfsummary/cli.py sample.pdf

# 任意コマンド（STDINを受け取りMarkdownを返すコマンド）
PDFSUMMARY_LLM=cmd PDFSUMMARY_LLM_CMD="your_cursor_cli_command" \
python3 pdfsummary/cli.py sample.pdf
```

- `--llm`: `auto | ollama | openai | cmd`
  - `auto`: `PDFSUMMARY_LLM_CMD` があればそれを優先、次に `ollama`、次に `OPENAI_API_KEY` を使った OpenAI。
  - `ollama`: `ollama run <model>` を使用。
  - `openai`: `OPENAI_API_KEY` を使用（python SDK）。`--model` 例: `gpt-4o-mini`。
  - `cmd`: `--cmd` または `PDFSUMMARY_LLM_CMD` で指定したコマンド（STDINにプロンプトを渡し、Markdownを標準出力へ返す必要あり）。

## 出力の調整（単一パス要約）

- 箇条書き数: `--max-bullets 10`（既定: 10）
- テンプレート差し替え: `--summary-prompt-file /path/to/summary.tpl`
  - 変数: `{text}`, `{max_bullets}`
- OpenAIのsystemプロンプト（openaiモード時）: `--system-prompt "..."`

環境変数でも指定可能:

```bash
PDFSUMMARY_MAX_BULLETS=10
PDFSUMMARY_SUMMARY_PROMPT_FILE=${PDFSUMMARY_APP_DIR}/templates/summary.tpl
PDFSUMMARY_SYSTEM_PROMPT="あなたは日本語で簡潔にMarkdown要約を生成するアシスタントです。"
```

### テンプレート例

- 単一パス要約テンプレ（`templates/summary.tpl`）
```text
以下はPDF全体のテキストです。プレゼンテーションのPDFであるためにスライドのヘッダやフッダ情報が冗長な可能性があります。重要情報を落とさず、日本語で簡潔に最終Markdown要約を出力してください。後で検索等で利用しやすいように、重要なキーワードを含めるようにしてください。
- 見出し: # 要約
- 次に ## 重要ポイント（最大{max_bullets}点、箇条書き）
- 数値/日付/指標は明示。冗長表現は避ける。
- 出力は必ず日本語。英語は禁止。
- 最後に ## 関連リソース（最大{max_bullets}点、箇条書き）のURLを列挙

[PDF全文]
{text}
```

> 既存の `chunk.tpl` / `merge.tpl` は互換のため残していますが、既定は単一パスです。
> 内蔵のデフォルトプロンプトでは「次のアクション」「リスク/注意点」を任意で出力する指示が含まれます。テンプレートを使う場合は必要に応じて追記してください。

## Raycast から実行

`raycast/pdfsummary-raycast.sh` を Raycast の Script Commands として登録してください。

1. スクリプトに実行権限を付与
   ```bash
   chmod +x ${PDFSUMMARY_APP_DIR}/raycast/pdfsummary-raycast.sh
   ```
2. Raycast の「Script Commands」で当該スクリプトを指定
3. 引数にPDFファイルを指定して実行

環境変数例（Raycast 側で設定可能）:

```bash
PDFSUMMARY_LLM=auto
PDFSUMMARY_MODEL=gpt-4o-mini   # または llama3.1 など
PDFSUMMARY_LLM_CMD=your_cursor_cli_command
```

## Obsidian Terminal から実行

- Terminalプラグインを開き、Vaultルートで次を実行:
```bash
chmod +x ${PDFSUMMARY_APP_DIR}/obsidian/pdfsummary.sh
${PDFSUMMARY_APP_DIR}/obsidian/pdfsummary.sh \
	"/absolute/path/to/input.pdf"
# または クリップボードにPDFパス/file://URLをコピーしてから:
${PDFSUMMARY_APP_DIR}/obsidian/pdfsummary.sh
```
- 生成先: Vaultの `clips/` に `<PDF名>-YYYY-MM-DD.md`
- 生成Markdownはクリップボードにもコピーされます
- 必要に応じて環境変数を事前に設定:
```bash
export PDFSUMMARY_LLM=auto
export PDFSUMMARY_MODEL=llama3.1   # 例
export PDFSUMMARY_LLM_CMD="your_cursor_cli_command"
```

## 出力形式

- YAMLフロントマター（source, date）
- `# <タイトル>`
- 本文はMarkdown（見出し: 「要約」「重要ポイント」「次のアクション」「リスク/注意点」等）

## 備考

- 既定はPDF全文の単一パス要約です。非常に大きなPDFではトークン制限に注意してください。
- ネットワーク不要なローカル推論を使う場合は `ollama` 推奨。
-
- 旧スクリプト: `raycast/pdfsummary.py` および `raycast/pdfsummary.sh` は旧方式です。Raycastからは `raycast/pdfsummary-raycast.sh` の利用を推奨します。
- ObsidianのJS版: `obsidian/pdfsummary.js` はObsidian APIから直接ノートを作成するための簡易スクリプトです（Terminalプラグイン不要の運用に利用可能）。

### パス設定の外部化について

- すべてのスクリプトは `${PDFSUMMARY_APP_DIR}` を参照するように変更済みです。
- 未設定の場合は、各スクリプトの位置からリポジトリルートを自動推定します（`bin/`/`obsidian/`/`raycast/` → `..`）。
- 明示的に指定したい場合は、事前に次を設定してください:

```bash
export PDFSUMMARY_APP_DIR=/absolute/path/to/pdfsummary
```

- 互換のため、上記の自動検出で判別できない場合は、旧固定パス `/Users/Kou.Kobayashi/Workspace/dev/pdfsummary` を最終フォールバックします（存在する場合のみ有効）。
