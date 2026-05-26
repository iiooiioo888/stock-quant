/* global Api */

(() => {
  const $id = (id) => document.getElementById(id);
  let history = [];
  let sending = false;
  let bound = false;

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function useStream() {
    const el = $id('ai-stream');
    return el ? el.checked : true;
  }

  function renderMessages() {
    const el = $id('ai-messages');
    if (!el) return;
    if (!history.length) {
      el.innerHTML = '<div class="ai-msg ai-msg--sys">輸入問題後，助手會自動調用本機數據工具並整合回答。可提交回測任務並查詢進度。</div>';
      return;
    }
    el.innerHTML = history.map((m, idx) => {
      const role = m.role === 'user' ? 'user' : 'assistant';
      let toolsHtml = '';
      if (m.tool_status) {
        toolsHtml = `<div class="ai-msg-tools">${escapeHtml(m.tool_status)}</div>`;
      } else if (m.tool_calls?.length) {
        toolsHtml = `<div class="ai-msg-tools">已調用 ${m.tool_calls.length} 個工具</div>`;
      }
      const streaming = m.streaming ? ' ai-msg--streaming' : '';
      const body = m.role === 'assistant' && m.streaming && !m.content
        ? '…'
        : escapeHtml(m.content).replace(/\n/g, '<br>');
      return `<div class="ai-msg ai-msg--${role}${streaming}" data-idx="${idx}">
        <div class="ai-msg-role">${role === 'user' ? '你' : '助手'}</div>
        <div class="ai-msg-body">${body}</div>
        ${toolsHtml}
      </div>`;
    }).join('');
    el.scrollTop = el.scrollHeight;
  }

  function getLocalLlmConfig() {
    return typeof Api.getLlmConfig === 'function' ? Api.getLlmConfig() : {};
  }

  function hasLocalKey() {
    return !!String(getLocalLlmConfig().api_key || '').trim();
  }

  /** 本機 Key 或服務端（帳號 / 環境變量）已配置 */
  async function isLlmReady() {
    if (hasLocalKey()) return true;
    try {
      if (Api.isLoggedIn?.()) {
        const st = await Api.getLlmSettings();
        return !!st?.configured;
      }
      const st = await Api.getLlmStatus();
      return !!st?.configured;
    } catch (_) {
      return false;
    }
  }

  function buildChatHistory() {
    return history
      .filter((m) => (m.role === 'user' || m.role === 'assistant') && String(m.content || '').trim())
      .map((m) => ({ role: m.role, content: String(m.content).trim() }));
  }

  async function loadStatus() {
    const badge = $id('ai-status-badge');
    const hint = $id('ai-hint');
    const countEl = $id('ai-tool-count');
    const listEl = $id('ai-tools-list');

    let serverOk = false;
    let model = '';
    let sourceHint = '';

    try {
      if (Api.isLoggedIn?.()) {
        const st = await Api.getLlmSettings();
        serverOk = !!st?.configured;
        model = st?.settings?.model || st?.defaults?.model || '';
        if (st?.settings?.has_api_key) {
          sourceHint = '帳號 Key';
        } else if (st?.env_configured) {
          sourceHint = '服務端環境變量';
        }
        const local = getLocalLlmConfig();
        if (local.api_base || local.model) {
          Api.setLlmConfig({
            api_base: local.api_base || st?.settings?.api_base || st?.defaults?.api_base,
            model: local.model || st?.settings?.model || st?.defaults?.model,
          });
        }
      } else {
        const st = await Api.getLlmStatus();
        serverOk = !!st?.configured;
        model = st?.model || '';
        if (st?.env_configured) sourceHint = '服務端環境變量';
      }
    } catch (_) { /* ignore */ }

    try {
      const toolsRes = await Api.getLlmStatus();
      const n = toolsRes?.tool_count ?? (toolsRes?.tools?.length || 0);
      if (countEl) countEl.textContent = String(n);
      if (listEl && Array.isArray(toolsRes?.tools)) {
        listEl.innerHTML = toolsRes.tools.map((t) => `<li><code>${escapeHtml(t)}</code></li>`).join('');
      }
    } catch (_) { /* ignore */ }

    const localOk = hasLocalKey();
    const ok = serverOk || localOk;

    if (!ok) {
      if (badge) {
        badge.textContent = '未配置';
        badge.className = 'badge b-rd';
      }
      if (hint) {
        hint.innerHTML = '請到 <strong>設定 → LLM 智能問答</strong> 填寫 API Key，或配置服務端環境變量 <code>SQ_LLM_API_KEY</code>。支援流式輸出與回測任務觸發。';
      }
      return false;
    }

    if (badge) {
      const parts = [model || '就緒'];
      if (localOk) parts.push('本機 Key');
      else if (sourceHint) parts.push(sourceHint);
      badge.textContent = parts.join(' · ');
      badge.className = 'badge b-gn';
    }
    if (hint) {
      hint.textContent = '已連接 LLM。可查數據、北向資金、板塊、回測任務；勾選「流式回答」可實時顯示工具調用與回答。';
    }
    return true;
  }

  async function sendNonStream(msg, chatHistory) {
    const d = await Api.llmChat(msg, chatHistory);
    if (!d?.success || !d.answer) {
      throw new Error(d?.error || d?.detail || '問答失敗');
    }
    history.push({
      role: 'assistant',
      content: d.answer,
      tool_calls: d.tool_calls || [],
    });
  }

  async function sendStream(msg, chatHistory) {
    const assistantIdx = history.length;
    history.push({
      role: 'assistant',
      content: '',
      tool_calls: [],
      tool_status: '',
      streaming: true,
    });
    renderMessages();

    const toolCalls = [];
    let gotDone = false;

    await Api.llmChatStream(msg, chatHistory, (ev) => {
      const m = history[assistantIdx];
      if (!m) return;

      if (ev.type === 'status') {
        m.tool_status = ev.message || '';
        renderMessages();
      } else if (ev.type === 'tool_start') {
        m.tool_status = `調用 ${ev.name}…`;
        renderMessages();
      } else if (ev.type === 'tool_end') {
        toolCalls.push({ name: ev.name, ok: ev.ok, error: ev.error });
        m.tool_calls = [...toolCalls];
        m.tool_status = `完成 ${ev.name}${ev.ok ? '' : '（失敗）'}`;
        renderMessages();
      } else if (ev.type === 'token') {
        m.content += ev.content || '';
        renderMessages();
      } else if (ev.type === 'done') {
        gotDone = true;
        m.content = ev.answer || m.content;
        m.tool_calls = ev.tool_calls || toolCalls;
        m.streaming = false;
        m.tool_status = m.tool_calls.length ? `已調用 ${m.tool_calls.length} 個工具` : '';
        renderMessages();
      } else if (ev.type === 'error') {
        m.content = `抱歉：${ev.message || '處理失敗'}`;
        m.streaming = false;
        renderMessages();
        throw new Error(ev.message || '流式問答失敗');
      }
    });

    const final = history[assistantIdx];
    if (final?.streaming) {
      final.streaming = false;
      if (!final.content) final.content = gotDone ? '（無回覆內容）' : '（連線中斷，未收到完整回覆）';
      renderMessages();
    }
    if (final && !String(final.content || '').trim()) {
      throw new Error('未收到有效回答');
    }
  }

  async function send() {
    if (sending) return;
    const input = $id('ai-input');
    const msg = String(input?.value || '').trim();
    if (!msg) return;

    if (typeof Api !== 'undefined' && Api.isLoggedIn && !Api.isLoggedIn()) {
      Api.showLoginModal?.(false);
      window.StockQPro?.App?.toast?.('請先登錄後使用 AI 問答', 'inf');
      return;
    }

    if (!(await isLlmReady())) {
      window.StockQPro?.App?.toast?.('請先在設定頁配置 LLM API Key', 'inf');
      window.StockQPro?.App?.nav?.('settings', { syncHash: true });
      return;
    }

    const chatHistory = buildChatHistory();

    history.push({ role: 'user', content: msg });
    renderMessages();
    if (input) input.value = '';

    sending = true;
    const btn = $id('ai-send-btn');
    if (btn) btn.disabled = true;

    try {
      if (useStream()) {
        await sendStream(msg, chatHistory);
      } else {
        await sendNonStream(msg, chatHistory);
      }
      renderMessages();
      window.StockQPro?.App?.toast?.('回答已生成', 'ok');
    } catch (e) {
      const errText = e?.message || String(e);
      const last = history[history.length - 1];
      if (last?.role === 'assistant') {
        if (!last.content || last.streaming) {
          last.content = `抱歉，處理失敗：${errText}`;
        }
        last.streaming = false;
      } else {
        history.push({ role: 'assistant', content: `抱歉，處理失敗：${errText}` });
      }
      window.StockQPro?.App?.toast?.(errText, 'er');
      renderMessages();
    } finally {
      sending = false;
      if (btn) btn.disabled = false;
    }
  }

  function clearChat() {
    history = [];
    renderMessages();
  }

  function bindOnce() {
    if (bound) return;
    bound = true;
    $id('ai-send-btn')?.addEventListener('click', () => send());
    $id('ai-clear-btn')?.addEventListener('click', () => clearChat());
    $id('ai-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
  }

  async function init() {
    bindOnce();
    renderMessages();
    await loadStatus();
  }

  function onShow() {
    loadStatus();
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.ai = { init, onShow, clearChat };
})();
