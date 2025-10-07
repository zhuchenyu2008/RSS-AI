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
  filterKeywords: [],
  filterFeed: '',
  autoRefresh: false,
  autoTimer: null,
  reports: [],
  reportPage: 0,
  reportPageSize: 10,
  reportTotal: 0,
  reportTypeFilter: '',
  reportGenerating: { hourly: false, daily: false },
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
    const keywordList = Array.isArray(item.matched_keywords) ? item.matched_keywords : [];
    const metaParts = [];
    if (item.pub_date) metaParts.push(escapeHtml(item.pub_date));
    if (item.author) metaParts.push(escapeHtml(item.author));
    if (keywordList.length) {
      metaParts.push(`关键词：${escapeHtml(keywordList.join('、'))}`);
    }
    const metaHtml = metaParts.join(' · ');
    el.innerHTML = `
      <h3 class="title clickable" data-id="${item.id}">${escapeHtml(item.title)}</h3>
      <div class="meta">${metaHtml}</div>
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
function formatDateTime(value) {
  if (!value) return '';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
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
  state.filterKeywords = s.fetch.filter_keywords || [];
  q('#interval').value = s.fetch.interval_minutes;
  q('#maxItems').value = s.fetch.max_items;
  q('#perFeedLimit').value = s.fetch.per_feed_limit ?? 20;
  q('#feeds').value = (s.fetch.feeds || []).join('\n');
  q('#filterKeywords').value = state.filterKeywords.join('\n');
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

  q('#reportHourly').checked = !!(s.reports?.hourly_enabled);
  q('#reportDaily').checked = !!(s.reports?.daily_enabled);
  q('#reportTimeout').value = s.reports?.report_timeout_seconds ?? 60;
  q('#reportSystemPrompt').value = s.reports?.system_prompt || '';
  q('#reportUserPrompt').value = s.reports?.user_prompt_template || '';

  // 渲染筛选源
  const sel = q('#feedSelect');
  sel.innerHTML = '<option value="">全部源</option>' + state.feeds.map(f => `<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`).join('');
  sel.value = state.filterFeed;
}

function gatherSettingsFromForm() {
  const current = state.settings;
  const feeds = q('#feeds').value.split(/\n+/).map(s => s.trim()).filter(Boolean);
  const filterKeywords = q('#filterKeywords').value.split(/\n+/).map(s => s.trim()).filter(Boolean);
  let reportTimeout = parseInt(q('#reportTimeout').value, 10);
  if (!Number.isFinite(reportTimeout)) {
    reportTimeout = 60;
  } else {
    reportTimeout = Math.min(Math.max(reportTimeout, 10), 300);
  }
  return {
    server: current.server,
    fetch: {
      interval_minutes: parseInt(q('#interval').value, 10),
      max_items: parseInt(q('#maxItems').value, 10),
      per_feed_limit: parseInt(q('#perFeedLimit').value, 10),
      feeds,
      filter_keywords: filterKeywords,
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
    reports: {
      hourly_enabled: q('#reportHourly').checked,
      daily_enabled: q('#reportDaily').checked,
      report_timeout_seconds: reportTimeout,
      system_prompt: q('#reportSystemPrompt').value,
      user_prompt_template: q('#reportUserPrompt').value,
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

async function loadReports() {
  const offset = state.reportPage * state.reportPageSize;
  const typeParam = state.reportTypeFilter ? `&report_type=${encodeURIComponent(state.reportTypeFilter)}` : '';
  const data = await api(`/api/reports?limit=${state.reportPageSize}&offset=${offset}${typeParam}`);
  state.reports = data.items || [];
  state.reportTotal = data.total || 0;
  renderReports();
}

async function triggerReport(reportType) {
  const btn = reportType === 'daily' ? q('#generateDailyReport') : q('#generateHourlyReport');
  if (!btn) return;
  if (state.reportGenerating[reportType]) return;
  state.reportGenerating[reportType] = true;
  const originalText = btn.textContent;
  btn.textContent = '生成中…';
  btn.disabled = true;
  try {
    await api('/api/reports/generate', {
      method: 'POST',
      body: JSON.stringify({ report_type: reportType }),
    });
    toast(reportType === 'daily' ? '日报已生成' : '小时报已生成');
    state.reportPage = 0;
    await loadReports();
  } catch (err) {
    console.error(err);
    toast('生成失败');
  } finally {
    btn.textContent = originalText;
    btn.disabled = false;
    state.reportGenerating[reportType] = false;
  }
}

function renderReports() {
  const root = q('#reportsList');
  if (!root) return;
  root.innerHTML = '';
  if (!state.reports.length) {
    root.innerHTML = '<div class="empty">暂无定时汇总报告</div>';
    q('#reportPageInfo').textContent = '0 / 0';
    return;
  }
  state.reports.forEach((report, idx) => {
    const el = document.createElement('div');
    el.className = 'card enter';
    el.style.animationDelay = `${Math.min(idx * 30, 300)}ms`;
    const typeLabel = report.report_type === 'daily' ? '日报' : '小时报';
    const start = formatDateTime(report.timeframe_start);
    const end = formatDateTime(report.timeframe_end);
    el.innerHTML = `
      <h3 class="title">${escapeHtml(report.title)}</h3>
      <div class="meta">类型：${typeLabel} · 时间范围：${escapeHtml(start)} ~ ${escapeHtml(end)} · 文章：${report.article_count}</div>
      <div class="summary">${escapeHtml(report.summary_text).replace(/\n/g,'<br/>')}</div>
    `;
    root.appendChild(el);
  });
  const pages = Math.ceil(state.reportTotal / state.reportPageSize) || 1;
  q('#reportPageInfo').textContent = `${state.reportPage + 1} / ${pages}`;
}

// 搜索高亮功能已移除

async function openModal(id) {
  try {
    const item = state.items.find(i=>i.id===id) || null;
    if (!item) return;
    const m = q('#modal');
    q('#modalTitle').textContent = item.title;
    const keywordList = Array.isArray(item.matched_keywords) ? item.matched_keywords : [];
    const metaParts = [];
    if (item.pub_date) metaParts.push(item.pub_date);
    if (item.author) metaParts.push(item.author);
    if (keywordList.length) {
      metaParts.push(`关键词：${keywordList.join('、')}`);
    }
    q('#modalMeta').textContent = metaParts.join(' · ');
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
  const reportTypeSel = q('#reportTypeFilter');
  if (reportTypeSel) {
    reportTypeSel.addEventListener('change', (e)=> {
      state.reportTypeFilter = e.target.value;
      state.reportPage = 0;
      loadReports().catch(()=>{});
    });
  }
  const reportPrev = q('#reportPrevPage');
  const reportNext = q('#reportNextPage');
  if (reportPrev && reportNext) {
    reportPrev.addEventListener('click', () => {
      if (state.reportPage > 0) {
        state.reportPage--;
        loadReports().catch(()=>{});
      }
    });
    reportNext.addEventListener('click', () => {
      const pages = Math.ceil(state.reportTotal / state.reportPageSize) || 1;
      if (state.reportPage + 1 < pages) {
        state.reportPage++;
        loadReports().catch(()=>{});
      }
    });
  }

  const generateHourly = q('#generateHourlyReport');
  const generateDaily = q('#generateDailyReport');
  if (generateHourly) {
    generateHourly.addEventListener('click', () => triggerReport('hourly'));
  }
  if (generateDaily) {
    generateDaily.addEventListener('click', () => triggerReport('daily'));
  }

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
  await loadReports();
}

init().catch(console.error);
