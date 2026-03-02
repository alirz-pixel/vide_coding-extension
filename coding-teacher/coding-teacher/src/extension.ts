import * as vscode from "vscode";

const SERVER_URL = "http://localhost:8765/analyze";
const DEBOUNCE_MS = 5 * 1000; // 5초 

let panel: vscode.WebviewPanel | undefined;
let debounceTimer: NodeJS.Timeout | undefined;

// 대화 히스토리 (Extension 메모리)
let history: { role: string; content: string }[] = [];
let lastCode: string = "";

export function activate(context: vscode.ExtensionContext) {

	// 패널 열기/닫기
	context.subscriptions.push(
		vscode.commands.registerCommand("coding-teacher.toggle", () => {
			if (panel) {
				panel.dispose();
			} else {
				openPanel(context);
			}
		})
	);

	// 히스토리 초기화 커맨드
	context.subscriptions.push(
		vscode.commands.registerCommand("coding-teacher.reset", () => {
			history = [];
			panel?.webview.postMessage({ type: "reset" });
			vscode.window.showInformationMessage("코딩 선생님: 대화가 초기화됐어요!");
		})
	);

	// 타이핑 감지 → 디바운스
	context.subscriptions.push(
		vscode.workspace.onDidChangeTextDocument((event) => {
			const editor = vscode.window.activeTextEditor;
			if (!editor || event.document !== editor.document) { return; }
			if (event.contentChanges.length === 0) { return; }

			if (!panel) { openPanel(context); }

			clearTimeout(debounceTimer);
			debounceTimer = setTimeout(() => {
				const code = editor.document.getText();
				const language = editor.document.languageId;
				analyze(code, language);
			}, DEBOUNCE_MS);
		})
	);
}

function openPanel(context: vscode.ExtensionContext) {
	panel = vscode.window.createWebviewPanel(
		"codingTeacher",
		"코딩 선생님",
		vscode.ViewColumn.Beside,
		{ enableScripts: true }
	);

	panel.webview.html = getWebviewHtml(context, panel.webview);

	panel.onDidDispose(() => {
		panel = undefined;
	});
}

function extractDiff(oldCode: string, newCode: string): string {
	const oldLines = oldCode.split("\n");
	const newLines = newCode.split("\n");

	const added: string[] = [];
	const removed: string[] = [];

	// 추가된 코드에는 있지만, 예전 코드에는 없는 경우 +
	newLines.forEach((line) => {
		if (line.trim() && !oldLines.includes(line)) { added.push(`+ ${line}`); }
	});
	// 에전 코드에는 있지만, 추가된 코드에는 없는 경우 -
	oldLines.forEach((line) => {
		if (line.trim() && !newLines.includes(line)) { removed.push(`- ${line}`); }
	});

	if (added.length === 0 && removed.length === 0) { return ""; }
	return [...removed, ...added].join("\n");
}

async function analyze(code: string, language: string) {
	if (!panel) { return; }

	panel.webview.postMessage({ type: "start" });

	const diff = extractDiff(lastCode, code); // diff 추출
	console.log(diff);

	console.log(history)
	try {
		const response = await fetch(SERVER_URL, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ code, language, history, diff }),
		});

		if (!response.body) { return; }

		const reader = response.body.getReader();
		const decoder = new TextDecoder("utf-8");
		let buffer = "";
		const currentCode = code; // 히스토리에 저장할 코드 스냅샷

		while (true) {
			const { done, value } = await reader.read();
			if (done) { break; }

			buffer += decoder.decode(value, { stream: true });
			const lines = buffer.split("\n");
			buffer = lines.pop() ?? "";

			for (const line of lines) {
				if (!line.startsWith("data: ")) { continue; }
				const raw = line.slice(6).trim();

				try {
					const parsed = JSON.parse(raw);

					if (parsed.content) {
						panel?.webview.postMessage({ type: "token", content: parsed.content });
					}

					if (parsed.done && parsed.full) {
						lastCode = currentCode;

						// 히스토리에 누적
						if (diff) {
							history.push({ role: "user", content: `변경사항:\n${diff}` });
						}
						history.push({ role: "assistant", content: parsed.full });

						// 히스토리가 너무 길어지면 앞에서 자르기 (최근 3턴만 유지)
						if (history.length > 6) {
							history = history.slice(history.length - 6);
						}

						panel?.webview.postMessage({ type: "done" });
					}

				} catch { continue; }
			}
		}
	} catch (e) {
		panel?.webview.postMessage({
			type: "error",
			content: "server.py가 실행 중인지 확인하세요"
		});
	}
}

function getWebviewHtml(
	context: vscode.ExtensionContext,
	webview: vscode.Webview
): string {
	const characterUri = webview.asWebviewUri(
		vscode.Uri.joinPath(context.extensionUri, "assets", "character.png")
	);
	const nonce = Math.random().toString(36).substring(2);

	return `
<!DOCTYPE html>
<html lang="ko">
<head>
	<meta charset="UTF-8">
	<meta http-equiv="Content-Security-Policy"
		content="default-src 'none';
				img-src ${webview.cspSource} https:;
				script-src 'nonce-${nonce}';
				style-src 'unsafe-inline';
				connect-src http://localhost:8765;">
	<style>
		body {
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: flex-end;
			height: 100vh;
			margin: 0;
			background: var(--vscode-editor-background);
			color: var(--vscode-editor-foreground);
			font-family: var(--vscode-font-family);
			padding: 20px;
			box-sizing: border-box;
		}
		.speech-bubble {
			background: var(--vscode-input-background);
			border: 1px solid var(--vscode-input-border);
			border-radius: 16px;
			padding: 14px 18px;
			font-size: 13px;
			line-height: 1.7;
			width: 90%;
			max-width: 640px;
			min-height: 60px;
			max-height: 60vh;
			overflow-y: auto;
			white-space: pre-wrap;
			word-break: break-word;
			position: relative;
			box-shadow: 0 2px 12px rgba(0,0,0,0.3);
		}
		.speech-bubble::after {
			content: '';
			position: absolute;
			bottom: -12px;
			left: 50%;
			transform: translateX(-50%);
			border: 7px solid transparent;
			border-top-color: var(--vscode-input-border);
		}
		.typing::after {
			content: '▍';
			animation: blink 0.6s infinite;
			color: var(--vscode-focusBorder);
		}
		@keyframes blink {
			0%, 100% { opacity: 1; }
			50%      { opacity: 0; }
		}
		.character {
			width: 160px;
			height: 160px;
			object-fit: cover;
			border-radius: 12px;
			margin-top: 16px;
			border: 2px solid var(--vscode-input-border);
		}
	</style>
	</head>
	<body>
	<div class="speech-bubble" id="bubble">
		코드를 작성하면 피드백을 줄게요
	</div>
	<img src="${characterUri}" class="character"
		onerror="this.style.display='none'" alt="선생님">

	<script nonce="${nonce}">
		const bubble = document.getElementById('bubble');

		window.addEventListener('message', (event) => {
		const msg = event.data;

		if (msg.type === 'start') {
			bubble.textContent = '';
			bubble.classList.add('typing');
		} else if (msg.type === 'token') {
			bubble.textContent += msg.content;
			bubble.scrollTop = bubble.scrollHeight;
		} else if (msg.type === 'done') {
			bubble.classList.remove('typing');
		} else if (msg.type === 'reset') {
			bubble.textContent = '대화가 초기화됐어요! 새로 시작해봐요;';
		} else if (msg.type === 'error') {
			bubble.textContent = '⚠️ ' + msg.content;
			bubble.classList.remove('typing');
		}
		});
  </script>
</body>
</html>`;
}

export function deactivate() {
	clearTimeout(debounceTimer);
}