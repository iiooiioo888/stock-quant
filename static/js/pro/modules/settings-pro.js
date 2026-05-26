/* global Api */

(() => {
  const $id = (id) => document.getElementById(id);
  const Prefs = () => window.StockQPro?.Prefs;

  function updatePreview() {
    const box = $id('set-color-preview');
    if (!box) return;
    const up = box.querySelector('.settings-preview-chip.up');
    const down = box.querySelector('.settings-preview-chip.down');
    if (up) up.textContent = '+1.28%';
    if (down) down.textContent = '-0.85%';
  }

  function readForm() {
    const scheme = document.querySelector('input[name="set-quote-scheme"]:checked')?.value
      || Prefs()?.DEFAULTS?.quoteColorScheme;
    return {
      quoteColorScheme: scheme,
      chartDays: Number($id('set-chart-days')?.value) || 90,
      marketPollSec: Number($id('set-poll-sec')?.value),
      compactTopbar: !!$id('set-compact-topbar')?.checked,
    };
  }

  function fillForm(p) {
    const scheme = p.quoteColorScheme || 'cn-red-up';
    document.querySelectorAll('input[name="set-quote-scheme"]').forEach((el) => {
      el.checked = el.value === scheme;
    });
    if ($id('set-chart-days')) $id('set-chart-days').value = String(p.chartDays ?? 90);
    if ($id('set-poll-sec')) $id('set-poll-sec').value = String(p.marketPollSec ?? 90);
    if ($id('set-compact-topbar')) $id('set-compact-topbar').checked = p.compactTopbar !== false;
    updatePreview();
  }

  function fillLlmForm(settings, defaults = {}) {
    if ($id('set-llm-base')) {
      $id('set-llm-base').value = settings?.api_base || defaults?.api_base || '';
    }
    if ($id('set-llm-model')) {
      $id('set-llm-model').value = settings?.model || defaults?.model || '';
    }
    if ($id('set-llm-key')) {
      $id('set-llm-key').value = '';
      $id('set-llm-key').placeholder = settings?.has_api_key
        ? `已保存 ${settings.api_key_masked || '****'}（留空不修改）`
        : 'sk-…';
    }
  }

  function updateLlmStatusLine(text, ok) {
    const el = $id('set-llm-status');
    if (!el) return;
    el.textContent = text;
    el.style.color = ok ? 'var(--quote-down)' : 'var(--t3)';
  }

  async function loadLlmSettings() {
    const local = typeof Api.getLlmConfig === 'function' ? Api.getLlmConfig() : {};
    if (!Api.isLoggedIn?.()) {
      fillLlmForm({ has_api_key: !!local.api_key, api_key_masked: local.api_key ? '本機' : '' }, local);
      updateLlmStatusLine('未登錄：僅本機 Key 可用', false);
      return;
    }
    try {
      const d = await Api.getLlmSettings();
      const st = d?.settings || {};
      const defs = d?.defaults || {};
      fillLlmForm(st, defs);
      if (local.api_base && !$id('set-llm-base')?.value) $id('set-llm-base').value = local.api_base;
      if (local.model && !$id('set-llm-model')?.value) $id('set-llm-model').value = local.model;
      const envOk = !!d?.env_configured;
      const configured = d?.configured || !!local.api_key;
      const parts = [];
      if (st.has_api_key) parts.push('帳號已存 Key');
      else if (envOk) parts.push('環境變量 Key');
      if (local.api_key) parts.push('本機 Key');
      updateLlmStatusLine(
        configured ? `已就緒${parts.length ? `（${parts.join(' · ')}）` : ''}` : '未配置 Key',
        configured,
      );
    } catch (e) {
      fillLlmForm({ has_api_key: !!local.api_key }, local);
      updateLlmStatusLine(`載入失敗：${e?.message || e}`, false);
    }
  }

  async function saveLlmSettings() {
    const key = String($id('set-llm-key')?.value || '').trim();
    const api_base = String($id('set-llm-base')?.value || '').trim();
    const model = String($id('set-llm-model')?.value || '').trim();
    const localOnly = !!$id('set-llm-local-only')?.checked;

    const localPatch = {};
    if (api_base) localPatch.api_base = api_base;
    if (model) localPatch.model = model;
    if (key) localPatch.api_key = key;
    if (typeof Api.setLlmConfig === 'function') Api.setLlmConfig(localPatch);

    if (localOnly) {
      window.StockQPro?.App?.toast?.('LLM 設置已保存到本機', 'ok');
      await loadLlmSettings();
      return;
    }

    if (!Api.isLoggedIn?.()) {
      window.StockQPro?.App?.toast?.('已保存到本機；登錄後可同步到帳號', 'inf');
      return;
    }

    const llm = {};
    if (key) llm.api_key = key;
    if (api_base) llm.api_base = api_base;
    if (model) llm.model = model;

    if (!Object.keys(llm).length) {
      window.StockQPro?.App?.toast?.('請填寫 API Key、Base 或模型，或勾選「僅保存到本機」', 'inf');
      return;
    }

    try {
      const d = await Api.saveLlmSettings(llm);
      if (!d?.success) throw new Error(d?.message || '保存失敗');
      if ($id('set-llm-key')) $id('set-llm-key').value = '';
      window.StockQPro?.App?.toast?.('LLM 設置已保存到帳號', 'ok');
      await loadLlmSettings();
    } catch (e) {
      window.StockQPro?.App?.toast?.(`保存失敗：${e?.message || e}`, 'er');
    }
  }

  async function clearLlmKey() {
    if (typeof Api.setLlmConfig === 'function') {
      const c = Api.getLlmConfig();
      delete c.api_key;
      Api.setLlmConfig(c);
    }
    if ($id('set-llm-key')) $id('set-llm-key').value = '';
    if (Api.isLoggedIn?.()) {
      try {
        await Api.saveLlmSettings({ clear: true });
      } catch (_) { /* ignore */ }
    }
    window.StockQPro?.App?.toast?.('已清除 API Key', 'ok');
    await loadLlmSettings();
  }

  async function loadServerConfig() {
    const cfg = await Api.getConfig().catch(() => ({}));
    if (cfg && typeof cfg === 'object') {
      if (cfg.backtest_commission != null && $id('set-commission')) {
        $id('set-commission').value = Number(cfg.backtest_commission) * 100;
      }
      if (cfg.task_max_workers != null && $id('set-max-parallel')) {
        $id('set-max-parallel').value = Number(cfg.task_max_workers);
      }
      const tv = $id('set-src-tv');
      const ib = $id('set-src-ib');
      if (tv) tv.textContent = cfg.tradingview_enabled === false ? '關閉' : '啟用';
      if (ib) ib.textContent = cfg.ib_enabled ? '已連線配置' : '未啟用';
    }
    return cfg;
  }

  function load() {
    const p = Prefs()?.load?.() || {};
    fillForm(p);
    return Promise.all([loadServerConfig(), loadLlmSettings()]);
  }

  function save() {
    const partial = readForm();
    Prefs()?.save?.(partial);
    window.StockQPro?.MarketTicker?.setPollInterval?.(partial.marketPollSec * 1000);
    window.StockQPro?.MarketTicker?.refresh?.();
    window.StockQPro?.App?.toast?.('偏好已保存（本機）', 'ok');
  }

  async function clearCaches() {
    try {
      if (typeof Api.clearGetCache === 'function') Api.clearGetCache();
      await Api.post('/api/cache/clear', {}).catch(() => null);
      window.StockQPro?.App?.toast?.('已清除前端與服務端緩存', 'ok');
    } catch (_) {
      window.StockQPro?.App?.toast?.('清除緩存失敗', 'er');
    }
  }

  function bindSchemePreview() {
    document.querySelectorAll('input[name="set-quote-scheme"]').forEach((el) => {
      el.addEventListener('change', () => {
        Prefs()?.save?.(readForm());
        updatePreview();
      });
    });
  }

  function init() {
    if ($id('set-save-btn') && !$id('set-save-btn').dataset.bound) {
      $id('set-save-btn').dataset.bound = '1';
      $id('set-save-btn').addEventListener('click', () => save());
      $id('set-reload-btn')?.addEventListener('click', () => {
        load().catch(() => window.StockQPro?.App?.toast?.('載入設定失敗', 'er'));
      });
      $id('set-clear-cache')?.addEventListener('click', () => clearCaches());
      $id('set-reset-prefs')?.addEventListener('click', () => {
        localStorage.removeItem(Prefs()?.STORAGE_KEY || 'stockq:pro_prefs_v1');
        if (Prefs()) Prefs().save({ ...Prefs().DEFAULTS });
        fillForm(Prefs().DEFAULTS);
        window.StockQPro?.App?.toast?.('已恢復預設偏好', 'ok');
      });
      $id('set-llm-save')?.addEventListener('click', () => saveLlmSettings());
      $id('set-llm-clear')?.addEventListener('click', () => clearLlmKey());
      bindSchemePreview();
    }
    load().catch(() => window.StockQPro?.App?.toast?.('載入設定失敗', 'er'));
  }

  window.StockQPro = window.StockQPro || {};
  window.StockQPro.pages = window.StockQPro.pages || {};
  window.StockQPro.pages.settings = { init, load, save, loadLlmSettings };
})();
