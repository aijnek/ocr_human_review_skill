// 共通ヘルパー + チャットウィジェット + セッション終了ボタン

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

const STATUS_LABELS = {
  uploaded: ['アップロード済', 'badge-gray'],
  ocr_running: ['OCR処理中', 'badge-blue'],
  awaiting_review: ['レビュー待ち', 'badge-yellow'],
  confirmed: ['確定済', 'badge-green'],
  error: ['エラー', 'badge-red'],
};

function statusBadge(status) {
  const [label, cls] = STATUS_LABELS[status] || [status, 'badge-gray'];
  return `<span class="badge ${cls}">${label}</span>`;
}

// ---- セッション終了 ----
document.getElementById('btn-shutdown').addEventListener('click', async () => {
  if (!confirm('エージェントのポーリングを終了します。よろしいですか?')) return;
  await fetch('/api/shutdown', { method: 'POST' });
  alert('終了をリクエストしました。エージェントは次のポーリングで停止します。');
});

// ---- エージェント接続状態 ----
let agentConnected = true;

async function refreshStatus() {
  try {
    const status = await fetchJSON('/api/status');
    agentConnected = status.agent_connected;
    document.getElementById('agent-banner').hidden =
      agentConnected || status.active_jobs === 0;
  } catch { /* サーバー停止中はバナー判定不能なので何もしない */ }
}
refreshStatus();
setInterval(refreshStatus, 2000);

// ---- チャットウィジェット ----
const chatWidget = document.getElementById('chat-widget');
const chatMessages = document.getElementById('chat-messages');
const chatPending = document.getElementById('chat-pending');
let lastChatCount = -1;

document.getElementById('chat-toggle').addEventListener('click', () => {
  chatWidget.classList.toggle('collapsed');
  if (!chatWidget.classList.contains('collapsed')) refreshChat();
});

document.getElementById('chat-form').addEventListener('submit', async e => {
  e.preventDefault();
  const input = document.getElementById('chat-input');
  const message = input.value.trim();
  if (!message) return;
  input.value = '';
  await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  refreshChat();
});

async function refreshChat() {
  if (chatWidget.classList.contains('collapsed')) return;
  const data = await fetchJSON('/api/chat');
  const pending = data.messages.some(m => m.pending);
  chatPending.hidden = !pending;
  if (pending && !agentConnected) {
    chatPending.textContent = '⚠ エージェントが接続していません。skill を起動すると回答されます。';
    chatPending.classList.add('chat-pending-warn');
  } else {
    chatPending.textContent = 'エージェントが回答中…';
    chatPending.classList.remove('chat-pending-warn');
  }
  if (data.messages.length === lastChatCount) return;
  lastChatCount = data.messages.length;
  chatMessages.innerHTML = data.messages.map(m => `
    <div class="chat-msg chat-${m.role}">
      <div class="chat-bubble">${esc(m.content)}</div>
    </div>`).join('');
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

setInterval(refreshChat, 2000);
