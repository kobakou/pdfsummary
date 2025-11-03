import argparse
import datetime
import os
import shutil
import subprocess
import sys
from typing import List, Optional

from pdfminer.high_level import extract_text


class _SafeDict(dict):
	def __missing__(self, key: str) -> str:
		return "{" + key + "}"


def _read_text_if_file(path: Optional[str]) -> Optional[str]:
	if not path:
		return None
	p = path.strip()
	if not p:
		return None
	if not os.path.isfile(p):
		return None
	with open(p, "r", encoding="utf-8") as f:
		return f.read()


def extract_text_from_pdf(pdf_path: str) -> str:
	return extract_text(pdf_path) or ""


def _is_likely_japanese(text: str) -> bool:
	# 判定: 日本語の文字（ひらがな/カタカナ/漢字/全角記号）が一定量含まれる
	if not text:
		return False
	jp_ranges = [
		(0x3040, 0x309F),  # ひらがな
		(0x30A0, 0x30FF),  # カタカナ
		(0x4E00, 0x9FFF),  # CJK統合漢字
		(0x3000, 0x303F),  # CJK記号・句読点
	]
	jp_count = 0
	for ch in text:
		cp = ord(ch)
		for a, b in jp_ranges:
			if a <= cp <= b:
				jp_count += 1
				break
	# 閾値: 最低10文字、または全体に対し1%以上
	return jp_count >= 10 or (jp_count / max(len(text), 1)) >= 0.01


def chunk_text(text: str, max_chars: int = 6000) -> List[str]:
	if not text:
		return []
	paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
	chunks: List[str] = []
	current: List[str] = []
	current_len = 0
	for p in paragraphs:
		# 長すぎる段落は強制分割
		if len(p) > max_chars:
			for i in range(0, len(p), max_chars):
				piece = p[i : i + max_chars]
				if current:
					chunks.append("\n\n".join(current))
					current = []
					current_len = 0
				chunks.append(piece)
			continue
		if current_len + len(p) + (2 if current else 0) <= max_chars:
			current.append(p)
			current_len += len(p) + (2 if current else 0)
		else:
			chunks.append("\n\n".join(current))
			current = [p]
			current_len = len(p)
	if current:
		chunks.append("\n\n".join(current))
	return chunks


def which(cmd: str) -> bool:
	return shutil.which(cmd) is not None


def run_cmd_with_stdin(cmd_str: str, input_text: str) -> str:
	"""汎用: 任意コマンドにSTDINでプロンプト/本文を渡し、その標準出力を返す"""
	completed = subprocess.run(
		cmd_str,
		input=input_text.encode("utf-8"),
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		shell=True,
		check=False,
	)
	if completed.returncode != 0:
		raise RuntimeError(
			f"Command failed: {cmd_str}\nSTDERR: {completed.stderr.decode('utf-8', errors='ignore')}"
		)
	return completed.stdout.decode("utf-8", errors="ignore").strip()


def summarize_with_ollama(prompt: str, model: str) -> str:
	if not which("ollama"):
		raise RuntimeError("ollama コマンドが見つかりません")
	if not model:
		model = "hf.co/SakanaAI/TinySwallow-1.5B-Instruct-GGUF:latest" # Default model
	cmd = f"ollama run {model}"
	return run_cmd_with_stdin(cmd, prompt)


def summarize_with_openai(prompt: str, model: str, system_prompt: str) -> str:
	try:
		from openai import OpenAI  # type: ignore
	except Exception as e:
		raise RuntimeError("openai パッケージが未インストールです。requirements をインストールしてください") from e
	api_key = os.getenv("OPENAI_API_KEY")
	if not api_key:
		raise RuntimeError("OPENAI_API_KEY が未設定です")
	client = OpenAI(api_key=api_key)
	resp = client.chat.completions.create(
		model=model,
		messages=[
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": prompt},
		],
		temperature=0.2,
	)
	return (resp.choices[0].message.content or "").strip()


def auto_summarize(prompt: str, llm: str, model: str, cmd: Optional[str], system_prompt: str) -> str:
	if llm == "ollama":
		return summarize_with_ollama(prompt, model)
	if llm == "openai":
		return summarize_with_openai(prompt, model, system_prompt)
	if llm == "cmd":
		if not cmd:
			raise RuntimeError("--cmd または PDFSUMMARY_LLM_CMD が必要です")
		return run_cmd_with_stdin(cmd, prompt)

	# auto
	env_cmd = cmd or os.getenv("PDFSUMMARY_LLM_CMD")
	if env_cmd:
		return run_cmd_with_stdin(env_cmd, prompt)
	if which("ollama"):
		return summarize_with_ollama(prompt, model or "hf.co/SakanaAI/TinySwallow-1.5B-Instruct-GGUF:latest")
	if os.getenv("OPENAI_API_KEY"):
		return summarize_with_openai(prompt, model or "gpt-4o-mini", system_prompt)
	raise RuntimeError(
		"LLMの実行方法が見つかりません。ollama または OPENAI_API_KEY または PDFSUMMARY_LLM_CMD を設定してください。"
	)


def build_chunk_prompt(chunk: str, max_bullets: int, template_path: Optional[str]) -> str:
	tpl = _read_text_if_file(template_path)
	if tpl:
		return tpl.format_map(_SafeDict({
			"chunk": chunk,
			"max_bullets": max_bullets,
		}))
	return (
		"以下はPDFテキストの一部です。重要情報を落とさず、日本語で簡潔にMarkdown要約してください.\n"
		"- 出力はMarkdownのみ。前置き/後置きは不要。\n"
		f"- 箇条書き優先（最大{max_bullets}点）。数値・日付・固有名詞は保持。\n"
		"- 出力は必ず日本語。英語は禁止。\n\n"
		f"[PDF部分]\n{chunk}\n"
	)


def build_merge_prompt(
	partials_md: List[str],
	max_bullets: int,
	include_actions: bool,
	include_risks: bool,
	template_path: Optional[str],
) -> str:
	joined = "\n\n".join(partials_md)
	tpl = _read_text_if_file(template_path)
	if tpl:
		return tpl.format_map(_SafeDict({
			"partials": joined,
			"max_bullets": max_bullets,
			"include_actions": include_actions,
			"include_risks": include_risks,
		}))
	lines: List[str] = []
	lines.append("以下はPDFの部分要約の集合です。重複を統合し、日本語で最終Markdown要約を出力してください。")
	lines.append("- 見出し: # 要約")
	lines.append(f"- 次に ## 重要ポイント（箇条書き 最大{max_bullets}点）")
	if include_actions:
		lines.append("- 任意で ## 次のアクション を箇条書き")
	if include_risks:
		lines.append("- 任意で ## リスク/注意点 も箇条書き")
	lines.append("- 数値/日付/指標は明示。冗長表現は避ける。")
	lines.append("- 出力は必ず日本語。英語は禁止。\n")
	lines.append(f"[部分要約]\n{joined}\n")
	return "\n".join(lines)


def build_summary_prompt(full_text: str, max_bullets: int, template_path: Optional[str]) -> str:
	tpl = _read_text_if_file(template_path)
	if tpl:
		return tpl.format_map(_SafeDict({
			"text": full_text,
			"max_bullets": max_bullets,
		}))
	return (
		"以下はPDF全体のテキストです。重要情報を落とさず、日本語で簡潔に最終Markdown要約を出力してください。\n"
		"- 見出し: # 要約\n"
		f"- 次に ## 重要ポイント（最大{max_bullets}点、箇条書き）\n"
		"- 可能なら ## 次のアクション と ## リスク/注意点 も簡潔に箇条書き\n"
		"- 数値/日付/指標は明示。冗長表現は避ける。\n"
		"- 出力は必ず日本語。英語は禁止。\n\n"
		f"[PDF全文]\n{full_text}\n"
	)


def generate_markdown(title: str, final_md_body: str, src_path: str) -> str:
	today = datetime.date.today().isoformat()
	source_abs = os.path.abspath(src_path)
	header = f"---\nsource: {source_abs}\ndate: {today}\n---\n\n# {title}\n\n"
	return header + final_md_body.strip() + "\n"


def _env_bool(name: str, default: bool) -> bool:
	val = os.getenv(name)
	if val is None:
		return default
	return val not in ("0", "false", "False", "no", "NO")


def main() -> None:
	parser = argparse.ArgumentParser(description="PDFを要約してMarkdownを出力")
	parser.add_argument("pdf", help="入力PDFパス")
	parser.add_argument("--out", help="出力Markdownパス（未指定はstdout）")
	parser.add_argument("--title", help="Markdownタイトル（未指定はPDFファイル名）")
	parser.add_argument(
		"--llm",
		choices=["auto", "ollama", "openai", "cmd"],
		default=os.getenv("PDFSUMMARY_LLM", "auto"),
		help="LLMの実行モード",
	)
	parser.add_argument(
		"--model",
		default=os.getenv("PDFSUMMARY_MODEL", ""),
		help="モデル名（ollama/openai時）",
	)
	parser.add_argument(
		"--cmd",
		default=os.getenv("PDFSUMMARY_LLM_CMD", ""),
		help="cmdモード時の実行コマンド（STDINでプロンプト入力するコマンド）",
	)
	parser.add_argument(
		"--single-pass",
		action="store_true",
		default=_env_bool("PDFSUMMARY_SINGLE_PASS", True),
		help="PDF全文を一括要約（既定）",
	)
	parser.add_argument(
		"--max-bullets",
		type=int,
		default=int(os.getenv("PDFSUMMARY_MAX_BULLETS", "10")),
		help="重要ポイントの最大箇条書き数（単一パス時）",
	)
	parser.add_argument(
		"--summary-prompt-file",
		default=os.getenv("PDFSUMMARY_SUMMARY_PROMPT_FILE", ""),
		help="単一パス用テンプレート（{text},{max_bullets}使用可）",
	)
	parser.add_argument(
		"--ensure-ja",
		dest="ensure_ja",
		action="store_true",
		default=_env_bool("PDFSUMMARY_ENSURE_JA", True),
		help="出力が日本語でない場合に自動リトライ（既定: 有効）",
	)
	parser.add_argument(
		"--no-ensure-ja",
		dest="ensure_ja",
		action="store_false",
		help="日本語強制リトライを無効化",
	)
	parser.add_argument(
		"--ja-retries",
		type=int,
		default=int(os.getenv("PDFSUMMARY_JA_RETRIES", "1")),
		help="日本語判定に失敗した際のリトライ回数（既定: 1）",
	)
	# 旧オプション（後方互換・未使用）
	parser.add_argument(
		"--max-chars",
		type=int,
		default=6000,
		help=argparse.SUPPRESS,
	)
	parser.add_argument(
		"--chunk-max-bullets",
		type=int,
		default=int(os.getenv("PDFSUMMARY_CHUNK_MAX_BULLETS", "5")),
		help=argparse.SUPPRESS,
	)
	parser.add_argument(
		"--merge-max-bullets",
		type=int,
		default=int(os.getenv("PDFSUMMARY_MERGE_MAX_BULLETS", "10")),
		help=argparse.SUPPRESS,
	)
	parser.add_argument(
		"--include-actions",
		dest="include_actions",
		action="store_true",
		default=_env_bool("PDFSUMMARY_INCLUDE_ACTIONS", True),
		help=argparse.SUPPRESS,
	)
	parser.add_argument(
		"--no-include-actions",
		dest="include_actions",
		action="store_false",
		help=argparse.SUPPRESS,
	)
	parser.add_argument(
		"--include-risks",
		dest="include_risks",
		action="store_true",
		default=_env_bool("PDFSUMMARY_INCLUDE_RISKS", True),
		help=argparse.SUPPRESS,
	)
	parser.add_argument(
		"--no-include-risks",
		dest="include_risks",
		action="store_false",
		help=argparse.SUPPRESS,
	)
	parser.add_argument(
		"--chunk-prompt-file",
		default=os.getenv("PDFSUMMARY_CHUNK_PROMPT_FILE", ""),
		help=argparse.SUPPRESS,
	)
	parser.add_argument(
		"--merge-prompt-file",
		default=os.getenv("PDFSUMMARY_MERGE_PROMPT_FILE", ""),
		help=argparse.SUPPRESS,
	)
	parser.add_argument(
		"--system-prompt",
		default=os.getenv("PDFSUMMARY_SYSTEM_PROMPT", "あなたは日本語で簡潔にMarkdown要約を生成するアシスタントです。出力は必ず日本語で、英語は禁止です。"),
		help="OpenAI用のsystemプロンプト（openaiモード時）",
	)

	args = parser.parse_args()

	pdf_path = args.pdf
	if not os.path.isfile(pdf_path):
		print(f"ファイルが見つかりません: {pdf_path}", file=sys.stderr)
		sys.exit(1)

	text = extract_text_from_pdf(pdf_path)
	if not text.strip():
		print("PDFからテキストを抽出できませんでした", file=sys.stderr)
		sys.exit(2)

	# 単一パス（既定）
	if args.single_pass:
		prompt = build_summary_prompt(text, args.max_bullets, args.summary_prompt_file or None)
		try:
			final_md = auto_summarize(prompt, args.llm, args.model, args.cmd or None, args.system_prompt)
		except Exception as e:
			print(f"要約に失敗: {e}", file=sys.stderr)
			sys.exit(3)
		# 日本語強制リトライ
		if args.ensure_ja and not _is_likely_japanese(final_md):
			for _ in range(max(args.ja_retries, 0)):
				retry_prompt = prompt + "\n\n注意: 前回の出力は日本語ではありませんでした。出力は必ず日本語のみで、英語は使用しないでください。"
				final_md = auto_summarize(retry_prompt, args.llm, args.model, args.cmd or None, args.system_prompt)
				if _is_likely_japanese(final_md):
					break

		title = args.title or os.path.splitext(os.path.basename(pdf_path))[0]
		rendered = generate_markdown(title, final_md, pdf_path)
		if args.out:
			out_path = args.out
			with open(out_path, "w", encoding="utf-8") as f:
				f.write(rendered)
			print(out_path)
		else:
			sys.stdout.write(rendered)
		return

	# 旧: 分割→統合（将来削除予定）
	chunks = chunk_text(text, max_chars=args.max_chars)
	partials: List[str] = []
	for idx, c in enumerate(chunks, start=1):
		prompt = build_chunk_prompt(c, args.chunk_max_bullets, args.chunk_prompt_file or None)
		try:
			md = auto_summarize(prompt, args.llm, args.model, args.cmd or None, args.system_prompt)
		except Exception as e:
			print(f"部分要約に失敗 (chunk {idx}/{len(chunks)}): {e}", file=sys.stderr)
			sys.exit(4)
		if args.ensure_ja and not _is_likely_japanese(md):
			for _ in range(max(args.ja_retries, 0)):
				retry_prompt = prompt + "\n\n注意: 前回の出力は日本語ではありませんでした。出力は必ず日本語のみで、英語は使用しないでください。"
				md = auto_summarize(retry_prompt, args.llm, args.model, args.cmd or None, args.system_prompt)
				if _is_likely_japanese(md):
					break
		partials.append(md)

	final_prompt = build_merge_prompt(
		partials_md=partials,
		max_bullets=args.merge_max_bullets,
		include_actions=args.include_actions,
		include_risks=args.include_risks,
		template_path=args.merge_prompt_file or None,
	)
	try:
		final_md = auto_summarize(final_prompt, args.llm, args.model, args.cmd or None, args.system_prompt)
	except Exception as e:
		print(f"最終要約に失敗: {e}", file=sys.stderr)
		sys.exit(5)
	if args.ensure_ja and not _is_likely_japanese(final_md):
		for _ in range(max(args.ja_retries, 0)):
			retry_prompt = final_prompt + "\n\n注意: 前回の出力は日本語ではありませんでした。出力は必ず日本語のみで、英語は使用しないでください。"
			final_md = auto_summarize(retry_prompt, args.llm, args.model, args.cmd or None, args.system_prompt)
			if _is_likely_japanese(final_md):
				break

	title = args.title or os.path.splitext(os.path.basename(pdf_path))[0]
	rendered = generate_markdown(title, final_md, pdf_path)

	if args.out:
		out_path = args.out
		with open(out_path, "w", encoding="utf-8") as f:
			f.write(rendered)
		print(out_path)
	else:
		sys.stdout.write(rendered)


if __name__ == "__main__":
	main()
