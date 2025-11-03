const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function normalizeClipboardToPosixPath(raw) {
	if (!raw) return '';
	let s = raw.trim();
	if (s.startsWith('file://')) {
		s = s.slice(7);
		if (s.startsWith('localhost/')) s = s.slice(10);
		s = decodeURIComponent(s);
		if (!s.startsWith('/')) s = '/' + s;
	}
	if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
		s = s.slice(1, -1);
	}
	s = path.resolve(s.replace(/^~\//, `${process.env.HOME}/`));
	return s;
}

async function ensureUniqueFilePath(app, relPath) {
	let base = relPath;
	let ext = '';
	const dot = relPath.lastIndexOf('.');
	if (dot !== -1) {
		base = relPath.slice(0, dot);
		ext = relPath.slice(dot);
	}
	let candidate = relPath;
	let i = 1;
	while (app.vault.getAbstractFileByPath(candidate)) {
		candidate = `${base}-${i}${ext}`;
		i += 1;
	}
	return candidate;
}

module.exports = async (app) => {
	// 1) クリップボードからPDFパス取得（macOS想定）
	let clip = '';
	try {
		clip = execFileSync('pbpaste', [], { encoding: 'utf8' }).split('\n')[0] || '';
	} catch {}
	const pdfPath = normalizeClipboardToPosixPath(clip);
	if (!pdfPath || !fs.existsSync(pdfPath) || !/\.pdf$/i.test(pdfPath)) {
		throw new Error('クリップボードに有効なPDFパスがありません');
	}

	// 2) Python CLI 実行（venv優先）
	const DEFAULT_APP_DIR = (typeof __dirname === 'string') ? path.resolve(__dirname, '..') : process.cwd();
	let APP_DIR = process.env.PDFSUMMARY_APP_DIR || DEFAULT_APP_DIR;
	if (!fs.existsSync(path.join(APP_DIR, 'pdfsummary', 'cli.py'))) {
		const fallback = '/Users/Kou.Kobayashi/Workspace/dev/pdfsummary';
		if (fs.existsSync(path.join(fallback, 'pdfsummary', 'cli.py'))) {
			APP_DIR = fallback;
		}
	}
	const venvPython = path.join(APP_DIR, '.venv', 'bin', 'python3');
	const PYTHON = process.env.PYTHON_BIN || (fs.existsSync(venvPython) ? venvPython : 'python3');
	const cliPath = path.join(APP_DIR, 'pdfsummary', 'cli.py');
	const env = {
		...process.env,
		PDFSUMMARY_LLM: process.env.PDFSUMMARY_LLM || 'auto',
		PDFSUMMARY_MODEL: process.env.PDFSUMMARY_MODEL || '',
		PDFSUMMARY_LLM_CMD: process.env.PDFSUMMARY_LLM_CMD || '',
	};
	let markdown = '';
	try {
		markdown = execFileSync(PYTHON, [cliPath, pdfPath], { encoding: 'utf8', env });
	} catch (e) {
		throw new Error(`要約に失敗しました: ${e.stderr ? e.stderr.toString() : e.message}`);
	}
	if (!markdown) throw new Error('要約結果が空です');

	// 3) ノート作成（Vault内）
	const summariesFolder = 'clips';
	try {
		if (!app.vault.getAbstractFileByPath(summariesFolder)) {
			await app.vault.createFolder(summariesFolder);
		}
	} catch {}
	const pdfBase = path.basename(pdfPath, path.extname(pdfPath));
	const today = new Date().toISOString().slice(0, 10);
	const relPath = `${summariesFolder}/${pdfBase}-${today}.md`;
	const safePath = await ensureUniqueFilePath(app, relPath);
	const file = await app.vault.create(safePath, markdown);
	await app.workspace.getLeaf(true).openFile(file);

	return `Created: ${safePath}`;
};
