// 共通ヘルパー + セッション終了ボタン

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
