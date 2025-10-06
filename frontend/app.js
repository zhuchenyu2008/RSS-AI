let API_BASE = location.origin;
if (API_BASE.startsWith('file:')) {
  API_BASE = 'http://127.0.0.1:3601';
}

const q = (sel) => document.querySelector(sel);
const qa = (sel) => Array.from(document.querySelectorAll(sel));

let state = {
  page: 0,
  pageSize: 10,
  total: 0,
  items: [],
  settings: null,
};

function toast(msg) {
  const t = q('#toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 1600);
}

async function api(path, opts = {}) {
  const url = API_BASE + path;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function loadArticles() {
  const offset = state.page * state.pageSize;
  const data = await api(`/api/articles?limit=${state.pageSize}&offset=${offset}`);
  state.items = data.items || [];
  state.total = data.total || 0;
  renderArticles();
}

function renderArticles() {
  const root = q('#articles');
  root.innerHTML = '';
  state.items.forEach(item => {
    const el = document.createElement('div');
    el.className = 'card';
    el.innerHTML = `
      <h3 class="title">${escapeHtml(item.title)}</h3>
      <div class="meta">${escapeHtml(item.pub_date || '')} · ${escapeHtml(item.author || '')}</div>
      <div class="summary">${escapeHtml(item.summary_text)}</div>
      <div style="margin-top:8px"><a class="link" target="_blank" rel="noopener" href="${item.link}">原文链接</a></div>
    `;
    root.appendChild(el);
  });
  const pages = Math.ceil(state.total / state.pageSize) || 1;
  q('#pageInfo').textContent = `${state.page + 1} / ${pages}`;
}

function escapeHtml(s) {
  return (s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

async function manualFetch() {
  q('#statusText').textContent = '抓取中…';
  try {
    await api('/api/fetch', { method: 'POST', body: JSON.stringify({ force: false }) });
    await loadArticles();
    toast('抓取完成');
  } catch (e) {
    console.error(e);
    toast('抓取失败');
  } finally {
    q('#statusText').textContent = '';
  }
}

async function loadSettings() {
  const s = await api('/api/settings');
  state.settings = s;
  q('#interval').value = s.fetch.interval_minutes;
  q('#maxItems').value = s.fetch.max_items;
  q('#feeds').value = (s.fetch.feeds || []).join('\n');

  q('#aiEnabled').checked = !!s.ai.enabled;
  q('#aiBaseUrl').value = s.ai.base_url || '';
  q('#aiApiKey').value = ''; // 安全：不回显
  q('#aiModel').value = s.ai.model || '';
  q('#aiTemp').value = s.ai.temperature ?? 0.2;

  q('#tgEnabled').checked = !!s.telegram.enabled;
  q('#tgToken').value = ''; // 安全：不回显
  q('#tgChatId').value = s.telegram.chat_id || '';
}

function gatherSettingsFromForm() {
  const current = state.settings;
  const feeds = q('#feeds').value.split(/\n+/).map(s => s.trim()).filter(Boolean);
  return {
    server: current.server,
    fetch: {
      interval_minutes: parseInt(q('#interval').value, 10),
      max_items: parseInt(q('#maxItems').value, 10),
      feeds,
    },
    ai: {
      enabled: q('#aiEnabled').checked,
      base_url: q('#aiBaseUrl').value.trim(),
      api_key: q('#aiApiKey').value.trim() || '***',
      model: q('#aiModel').value.trim(),
      temperature: parseFloat(q('#aiTemp').value),
    },
    telegram: {
      enabled: q('#tgEnabled').checked,
      bot_token: q('#tgToken').value.trim() || '***',
      chat_id: q('#tgChatId').value.trim(),
    },
    logging: current.logging,
  };
}

async function saveSettings(e) {
  e.preventDefault();
  try {
    const body = gatherSettingsFromForm();
    await api('/api/settings', { method: 'PUT', body: JSON.stringify(body) });
    toast('设置已保存');
  } catch (err) {
    console.error(err);
    toast('保存失败');
  }
}

function bindEvents() {
  q('#refreshBtn').addEventListener('click', manualFetch);
  q('#prevPage').addEventListener('click', () => {
    if (state.page > 0) { state.page--; loadArticles(); }
  });
  q('#nextPage').addEventListener('click', () => {
    const pages = Math.ceil(state.total / state.pageSize) || 1;
    if (state.page + 1 < pages) { state.page++; loadArticles(); }
  });
  q('#settingsForm').addEventListener('submit', saveSettings);
}

async function init() {
  bindEvents();
  await loadSettings();
  await loadArticles();
}

init().catch(console.error);
