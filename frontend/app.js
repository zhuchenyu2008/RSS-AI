let API_BASE = location.origin;
if (API_BASE.startsWith('file:')) {
  API_BASE = 'http://127.0.0.1:3602';
}

const q = (sel) => document.querySelector(sel);
const qa = (sel) => Array.from(document.querySelectorAll(sel));

let state = {
  page: 0,
  pageSize: 10,
  total: 0,
  items: [],
  settings: null,
  feeds: [],
  filterFeed: '',
  autoRefresh: false,
  autoTimer: null,
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
  showSkeleton(true);
  const offset = state.page * state.pageSize;
  const feedParam = state.filterFeed ? `&feed=${encodeURIComponent(state.filterFeed)}` : '';
  const data = await api(`/api/articles?limit=${state.pageSize}&offset=${offset}${feedParam}`);
  state.items = data.items || [];
  state.total = data.total || 0;
  renderArticles();
  showSkeleton(false);
}

function renderArticles() {
  const root = q('#articles');
  root.innerHTML = '';
  state.items.forEach((item, idx) => {
    const el = document.createElement('div');
    el.className = 'card enter';
    el.style.animationDelay = `${Math.min(idx * 30, 300)}ms`;
    el.innerHTML = `
      <h3 class="title clickable" data-id="${item.id}">${escapeHtml(item.title)}</h3>
      <div class="meta">${escapeHtml(item.pub_date || '')} · ${escapeHtml(item.author || '')}</div>
      <div class="summary">${escapeHtml(item.summary_text)}</div>
      <div class="actions-row">
        <a class="link" target="_blank" rel="noopener" href="${item.link}">原文链接</a>
        <button class="ghost" data-copy="${item.link}">复制链接</button>
      </div>
    `;
    root.appendChild(el);
  });
  const pages = Math.ceil(state.total / state.pageSize) || 1;
  q('#pageInfo').textContent = `${state.page + 1} / ${pages}`;

  // 绑定复制与详情
  qa('[data-copy]').forEach(b => b.addEventListener('click', async (e) => {
    try { await navigator.clipboard.writeText(b.dataset.copy); toast('已复制链接'); } catch {}
  }));
  qa('.title.clickable').forEach(t => t.addEventListener('click', () => openModal(parseInt(t.dataset.id,10))));
}

function escapeHtml(s) {
  return (s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

async function manualFetch() {
  q('#statusText').textContent = '抓取中…';
  try {
    const force = q('#forceFetch').checked;
    await api('/api/fetch', { method: 'POST', body: JSON.stringify({ force }) });
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
  state.feeds = s.fetch.feeds || [];
  q('#interval').value = s.fetch.interval_minutes;
  q('#maxItems').value = s.fetch.max_items;
  q('#perFeedLimit').value = s.fetch.per_feed_limit ?? 20;
  q('#feeds').value = (s.fetch.feeds || []).join('\n');
  q('#useArticlePage').checked = !!s.fetch.use_article_page;
  q('#articleTimeout').value = s.fetch.article_timeout_seconds ?? 15;

  q('#aiEnabled').checked = !!s.ai.enabled;
  q('#aiBaseUrl').value = s.ai.base_url || '';
  q('#aiApiKey').value = ''; // 安全：不回显
  q('#aiModel').value = s.ai.model || '';
  q('#aiTemp').value = s.ai.temperature ?? 0.2;
  q('#aiSystemPrompt').value = s.ai.system_prompt || '';
  q('#aiUserPrompt').value = s.ai.user_prompt_template || '';

  q('#tgEnabled').checked = !!s.telegram.enabled;
  q('#tgToken').value = ''; // 安全：不回显
  q('#tgChatId').value = s.telegram.chat_id || '';
  q('#tgPushSummary').checked = !!s.telegram.push_summary;

  // 渲染筛选源
  const sel = q('#feedSelect');
  sel.innerHTML = '<option value="">全部源</option>' + state.feeds.map(f => `<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`).join('');
  sel.value = state.filterFeed;
}

function gatherSettingsFromForm() {
  const current = state.settings;
  const feeds = q('#feeds').value.split(/\n+/).map(s => s.trim()).filter(Boolean);
  return {
    server: current.server,
    fetch: {
      interval_minutes: parseInt(q('#interval').value, 10),
      max_items: parseInt(q('#maxItems').value, 10),
      per_feed_limit: parseInt(q('#perFeedLimit').value, 10),
      feeds,
      use_article_page: q('#useArticlePage').checked,
      article_timeout_seconds: parseInt(q('#articleTimeout').value, 10),
    },
    ai: {
      enabled: q('#aiEnabled').checked,
      base_url: q('#aiBaseUrl').value.trim(),
      api_key: q('#aiApiKey').value.trim() || '***',
      model: q('#aiModel').value.trim(),
      temperature: parseFloat(q('#aiTemp').value),
      system_prompt: q('#aiSystemPrompt').value,
      user_prompt_template: q('#aiUserPrompt').value,
    },
    telegram: {
      enabled: q('#tgEnabled').checked,
      bot_token: q('#tgToken').value.trim() || '***',
      chat_id: q('#tgChatId').value.trim(),
      push_summary: q('#tgPushSummary').checked,
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

function setAutoRefresh(enabled) {
  state.autoRefresh = enabled;
  localStorage.setItem('autoRefresh', enabled ? '1' : '0');
  if (state.autoTimer) { clearInterval(state.autoTimer); state.autoTimer = null; }
  if (enabled) {
    state.autoTimer = setInterval(() => { loadArticles().catch(()=>{}); }, 60000);
  }
}

function debounce(fn, delay=300) {
  let t; return (...args)=>{ clearTimeout(t); t=setTimeout(()=>fn(...args), delay); };
}

function showSkeleton(show) {
  const root = q('#articles');
  if (show) {
    root.innerHTML = Array.from({length: state.pageSize}).map(()=>`
      <div class="card skeleton">
        <div class="srect title"></div>
        <div class="srect sm"></div>
        <div class="srect"></div>
        <div class="srect"></div>
        <div class="srect half"></div>
      </div>
    `).join('');
  }
}

// 搜索高亮功能已移除

async function openModal(id) {
  try {
    const item = state.items.find(i=>i.id===id) || null;
    if (!item) return;
    const m = q('#modal');
    q('#modalTitle').textContent = item.title;
    q('#modalMeta').textContent = `${item.pub_date || ''} · ${item.author || ''}`;
    q('#modalSummary').innerHTML = escapeHtml(item.summary_text).replace(/\n/g,'<br/>');
    q('#modalLink').href = item.link;
    m.classList.add('show');
    document.body.classList.add('modal-open');
  } catch {}
}

function closeModal(){ q('#modal').classList.remove('show'); document.body.classList.remove('modal-open'); }

function bindEvents() {
  q('#refreshBtn').addEventListener('click', manualFetch);
  q('#feedSelect').addEventListener('change', (e)=>{ state.filterFeed=e.target.value; state.page=0; loadArticles(); });
  q('#prevPage').addEventListener('click', () => {
    if (state.page > 0) { state.page--; loadArticles(); }
  });
  q('#nextPage').addEventListener('click', () => {
    const pages = Math.ceil(state.total / state.pageSize) || 1;
    if (state.page + 1 < pages) { state.page++; loadArticles(); }
  });
  q('#settingsForm').addEventListener('submit', saveSettings);
  q('#autoRefresh').addEventListener('change', (e)=> setAutoRefresh(e.target.checked));
  q('#modal').addEventListener('click', (e)=>{ if (e.target.id==='modal' || e.target.dataset.close==='1') closeModal(); });
  q('#toTop').addEventListener('click', ()=> window.scrollTo({top:0,behavior:'smooth'}));

  // 显示/隐藏返回顶部（移动端更友好）
  const onScroll = () => {
    const btn = q('#toTop');
    if (window.scrollY > 400) btn.classList.add('show'); else btn.classList.remove('show');
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

async function init() {
  bindEvents();
  setAutoRefresh(localStorage.getItem('autoRefresh')==='1');
  await loadSettings();
  await loadArticles();
}

init().catch(console.error);
