# pdfsummary

Mac上でPDFからテキストを抽出し、LLMで要約してMarkdownを出力するCLI。
Raycast Script Commandからの実行を想定。

## セットアップ

```bash
cd /Users/Kou.Kobayashi/Workspace/dev/pdfsummary
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
PDFSUMMARY_SUMMARY_PROMPT_FILE=/Users/Kou.Kobayashi/Workspace/dev/pdfsummary/templates/summary.tpl
PDFSUMMARY_SYSTEM_PROMPT="あなたは日本語で簡潔にMarkdown要約を生成するアシスタントです。"
```

### テンプレート例

- 単一パス要約テンプレ（`templates/summary.tpl`）
```text
以下はPDF全体のテキストです。重要情報を落とさず、日本語で簡潔に最終Markdown要約を出力してください。
- 見出し: # 要約
- 次に ## 重要ポイント（最大{max_bullets}点、箇条書き）
- 可能なら ## 次のアクション と ## リスク/注意点 も簡潔に箇条書き
- 数値/日付/指標は明示。冗長表現は避ける。

[PDF全文]
{text}
```

> 既存の `chunk.tpl` / `merge.tpl` は互換のため残していますが、既定は単一パスです。

## Raycast から実行

`raycast/pdfsummary-raycast.sh` を Raycast の Script Commands として登録してください。

1. スクリプトに実行権限を付与
   ```bash
   chmod +x /Users/Kou.Kobayashi/Workspace/dev/pdfsummary/raycast/pdfsummary-raycast.sh
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
chmod +x /Users/Kou.Kobayashi/Workspace/dev/pdfsummary/obsidian/pdfsummary.sh
/Users/Kou.Kobayashi/Workspace/dev/pdfsummary/obsidian/pdfsummary.sh \
	"/absolute/path/to/input.pdf"
# または クリップボードにPDFパス/file://URLをコピーしてから:
/Users/Kou.Kobayashi/Workspace/dev/pdfsummary/obsidian/pdfsummary.sh
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
