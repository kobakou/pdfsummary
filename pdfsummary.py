#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple


def parse_page_ranges(pages: Optional[str]) -> Optional[Sequence[int]]:
    if not pages:
        return None
    result: List[int] = []
    for part in pages.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            try:
                start = int(start_str)
                end = int(end_str)
            except ValueError:
                raise ValueError(f"無効なページ指定: {part}")
            if start <= 0 or end <= 0 or end < start:
                raise ValueError(f"無効なページ範囲: {part}")
            result.extend(list(range(start, end + 1)))
        else:
            try:
                page = int(part)
            except ValueError:
                raise ValueError(f"無効なページ番号: {part}")
            if page <= 0:
                raise ValueError(f"無効なページ番号: {part}")
            result.append(page)
    # 重複排除し昇順
    return sorted(set(result))


def read_pdf_text(input_path: str, target_pages: Optional[Sequence[int]] = None) -> str:
    """pdfminer.sixを利用してテキスト抽出。
    target_pages は1始まりのページ番号配列。
    """
    try:
        from pdfminer.high_level import extract_text
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "pdfminer.six が必要です。`pip install -r requirements.txt` を実行してください"
        ) from exc

    if target_pages:
        # pdfminerは0始まり指定のため変換
        page_numbers_zero_based = [p - 1 for p in target_pages if p > 0]
    else:
        page_numbers_zero_based = None

    text = extract_text(input_path, page_numbers=page_numbers_zero_based)
    if not text:
        return ""
    # 余分な空白を整形
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    if chunk_size <= 0:
        return [text]
    if overlap < 0:
        overlap = 0
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end == n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def ensure_command_available(cmd: Optional[str]) -> str:
    if cmd:
        return cmd
    # 環境変数優先
    env_cmd = os.environ.get("SUMMARIZE_CMD") or os.environ.get("CURSOR_SUMMARIZE_CMD")
    if env_cmd:
        return env_cmd
    # cursor が見つかる場合の暫定デフォルト（ユーザーが調整可能）
    if shutil.which("cursor"):
        # モデル名やフラグは環境/バージョンに依存するため、必要なら --cmd で上書き
        return "cursor chat --model gpt-4o-mini"
    raise RuntimeError(
        "要約コマンドが未指定です。--cmd または 環境変数 SUMMARIZE_CMD を設定してください"
    )


def run_summarize_command(command: str, prompt: str, timeout_sec: int) -> str:
    completed = subprocess.run(
        command,
        input=prompt.encode("utf-8"),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_sec,
    )
    if completed.returncode != 0:
        stderr_text = completed.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"要約コマンド失敗: {stderr_text.strip()}")
    return completed.stdout.decode("utf-8", errors="ignore").strip()


def build_chunk_prompt(language: str, extra_instruction: Optional[str], chunk_text: str) -> str:
    instruction = (
        extra_instruction.strip() + "\n\n"
        if extra_instruction and extra_instruction.strip()
        else ""
    )
    return (
        f"以下はPDFから抽出した一部テキストです。{language}でMarkdown要約してください。\n"
        f"- 箇条書き中心で簡潔に\n"
        f"- 重要な数値・期日・固有名詞は残す\n"
        f"- 無関係なノイズは省く\n"
        f"- 見出し（##）を付与\n\n"
        f"{instruction}"
        f"=== コンテンツ開始 ===\n{chunk_text}\n=== コンテンツ終了 ===\n"
    )


def build_final_prompt(language: str, extra_instruction: Optional[str], partial_markdowns: Sequence[str]) -> str:
    instruction = (
        extra_instruction.strip() + "\n\n"
        if extra_instruction and extra_instruction.strip()
        else ""
    )
    joined = "\n\n\n".join(partial_markdowns)
    return (
        f"以下は複数チャンクの要約結果です。重複を排除し、{language}で最終Markdown要約を作成してください。\n"
        f"- 章立て（##）と項目（- ）で構成\n"
        f"- 同義内容を統合\n"
        f"- 抜け・矛盾を可能な限り解消\n"
        f"- 最後に '## 要点' セクションで3-7行で箇条書き要点\n\n"
        f"{instruction}"
        f"=== チャンク要約集約開始 ===\n{joined}\n=== 集約終了 ===\n"
    )


def default_output_path(input_pdf: str, output_dir: Optional[str]) -> str:
    stem = os.path.splitext(os.path.basename(input_pdf))[0]
    out_dir = output_dir or os.getcwd()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(out_dir, f"{stem}.summary.{ts}.md")


def load_prompt_file(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PDFを要約してMarkdown出力")
    parser.add_argument("input", help="入力PDFパス")
    parser.add_argument(
        "--pages",
        help="ページ指定（例: 1,3-5）",
        default=None,
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=8000,
        help="チャンクサイズ（文字数）",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=400,
        help="チャンク重なり（文字数）",
    )
    parser.add_argument(
        "--cmd",
        help="要約に使う外部コマンド（Cursor CLI等）。stdinを受け取りstdoutに要約を出力すること",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="外部コマンドのタイムアウト秒",
    )
    parser.add_argument(
        "--output",
        help="出力Markdownパス。未指定なら自動命名",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="標準出力に出力（--outputより優先）",
    )
    parser.add_argument(
        "--language",
        default="日本語",
        help="要約言語（例: 日本語, English）",
    )
    parser.add_argument(
        "--prompt-file",
        help="追加指示プロンプトのテキストファイルパス",
    )
    parser.add_argument(
        "--output-dir",
        help="出力ディレクトリ（--output未指定時に使用）",
    )

    args = parser.parse_args(argv)

    input_pdf = os.path.abspath(args.input)
    if not os.path.exists(input_pdf):
        print(f"入力PDFが見つかりません: {input_pdf}", file=sys.stderr)
        return 2

    try:
        target_pages = parse_page_ranges(args.pages)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        raw_text = read_pdf_text(input_pdf, target_pages)
    except Exception as e:  # noqa: BLE001
        print(f"PDF抽出エラー: {e}", file=sys.stderr)
        return 1

    if not raw_text:
        print("PDFからテキストを抽出できませんでした", file=sys.stderr)
        return 1

    chunks = split_text(raw_text, args.chunk_size, args.overlap)
    extra_instruction = load_prompt_file(args.prompt_file)

    try:
        summarize_cmd = ensure_command_available(args.cmd)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2

    partial_markdowns: List[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        prompt = build_chunk_prompt(args.language, extra_instruction, chunk)
        try:
            md = run_summarize_command(summarize_cmd, prompt, args.timeout)
        except Exception as e:  # noqa: BLE001
            print(f"要約エラー（チャンク{idx}/{len(chunks)}）: {e}", file=sys.stderr)
            return 1
        partial_markdowns.append(md)

    final_prompt = build_final_prompt(args.language, extra_instruction, partial_markdowns)
    try:
        final_markdown = run_summarize_command(summarize_cmd, final_prompt, args.timeout)
    except Exception as e:  # noqa: BLE001
        print(f"最終要約エラー: {e}", file=sys.stderr)
        return 1

    if args.stdout:
        print(final_markdown)
        return 0

    output_path = os.path.abspath(args.output) if args.output else default_output_path(input_pdf, args.output_dir)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_markdown.rstrip() + "\n")

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


