// 主脚本，负责从后端加载配置、保存配置以及显示摘要列表。

document.addEventListener('DOMContentLoaded', () => {
  const rssUrlsEl = document.getElementById('rssUrls');
  const apiKeyEl = document.getElementById('apiKey');
  const apiBaseEl = document.getElementById('apiBase');
  const modelEl = document.getElementById('model');
  const tgTokenEl = document.getElementById('tgToken');
  const tgChatIdEl = document.getElementById('tgChatId');
  const intervalEl = document.getElementById('interval');
  const messageEl = document.getElementById('message');
  const summaryListEl = document.getElementById('summaryList');

  // 显示提示信息并自动消失
  function showMessage(text) {
    messageEl.textContent = text;
    messageEl.classList.add('show');
    setTimeout(() => {
      messageEl.classList.remove('show');
    }, 3000);
  }

  // 加载配置
  async function loadConfig() {
    try {
      const resp = await fetch('/api/config');
      const cfg = await resp.json();
      rssUrlsEl.value = (cfg.rss_urls || []).join('\n');
      apiKeyEl.value = cfg.openai?.api_key || '';
      apiBaseEl.value = cfg.openai?.api_base || '';
      modelEl.value = cfg.openai?.model || '';
      tgTokenEl.value = cfg.telegram?.token || '';
      tgChatIdEl.value = cfg.telegram?.chat_id || '';
      intervalEl.value = cfg.fetch_interval || 3600;
    } catch (err) {
      console.error('加载配置失败', err);
      showMessage('加载配置失败');
    }
  }

  // 保存配置
  async function saveConfig() {
    const cfg = {
      rss_urls: rssUrlsEl.value
        .split('\n')
        .map((s) => s.trim())
        .filter((s) => s),
      openai: {
        api_key: apiKeyEl.value.trim(),
        api_base: apiBaseEl.value.trim(),
        model: modelEl.value.trim(),
      },
      telegram: {
        token: tgTokenEl.value.trim(),
        chat_id: tgChatIdEl.value.trim(),
      },
      fetch_interval: parseInt(intervalEl.value) || 3600,
    };
    try {
      const resp = await fetch('/api/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(cfg),
      });
      if (resp.ok) {
        showMessage('配置已保存');
        // 重新加载摘要
        loadSummaries();
      } else {
        showMessage('保存配置失败');
      }
    } catch (err) {
      console.error('保存配置出错', err);
      showMessage('保存配置出错');
    }
  }

  // 手动触发抓取
  async function runNow() {
    try {
      const resp = await fetch('/api/run');
      if (resp.ok) {
        showMessage('已开始抓取');
        // 稍后刷新摘要列表
        setTimeout(loadSummaries, 5000);
      } else {
        showMessage('触发抓取失败');
      }
    } catch (err) {
      console.error('触发抓取失败', err);
      showMessage('触发抓取失败');
    }
  }

  // 加载摘要列表
  async function loadSummaries() {
    try {
      const resp = await fetch('/api/summaries?limit=20');
      const list = await resp.json();
      summaryListEl.innerHTML = '';
      list.forEach((item) => {
        const card = document.createElement('div');
        card.className = 'summary-item';
        const title = document.createElement('h3');
        const link = document.createElement('a');
        link.href = item.link;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = item.title || '无标题';
        title.appendChild(link);
        const meta = document.createElement('div');
        meta.className = 'meta';
        meta.textContent = `作者: ${item.author || '未知'} | 发布时间: ${item.published || ''}`;
        const summary = document.createElement('p');
        summary.textContent = item.summary || '';
        card.appendChild(title);
        card.appendChild(meta);
        card.appendChild(summary);
        summaryListEl.appendChild(card);
      });
    } catch (err) {
      console.error('加载摘要失败', err);
      showMessage('加载摘要失败');
    }
  }

  // 绑定事件
  document.getElementById('saveBtn').addEventListener('click', saveConfig);
  document.getElementById('runBtn').addEventListener('click', runNow);

  // 初始加载
  loadConfig().then(loadSummaries);
});