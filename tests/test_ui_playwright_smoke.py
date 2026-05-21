"""
瀏覽器 UI 煙霧測試（Playwright）。

需先啟動服務並安裝瀏覽器：
  pip install -r requirements-dev.txt
  playwright install chromium
  python main.py serve   # 另開終端
  pytest tests/test_ui_playwright_smoke.py -v

環境變量：
  SQ_UI_BASE_URL — 預設 http://127.0.0.1:8000
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, sync_playwright

BASE_URL = os.environ.get("SQ_UI_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

SIDEBAR_TABS = [
    "dashboard",
    "backtest",
    "optimize",
    "walkforward",
    "heatmap",
    "history",
    "portfolio",
    "compare",
    "screener",
    "signals",
    "data",
    "analysis",
    "stock-detail",
    "polymarket",
    "tasks",
    "reports",
    "scheduler",
    "alerts",
    "markets",
    "crypto",
    "connectivity",
]

COMPARE_API_FRAGMENT = "/api/stocks/compare"


def _server_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _tab_visible(page: Page, tab: str) -> bool:
    return page.evaluate(
        """(name) => {
          const el = document.getElementById('tab-' + name);
          return !!(el && !el.classList.contains('h'));
        }""",
        tab,
    )


def _dismiss_modal(page: Page) -> None:
    cancel = page.locator(".modal button", has_text="取消")
    if cancel.count() and cancel.first.is_visible():
        cancel.first.click()
        page.wait_for_timeout(200)


def _click_sidebar_tab(page: Page, tab: str) -> None:
    btn = page.locator(f'.sidebar button[data-tab="{tab}"]')
    btn.scroll_into_view_if_needed()
    btn.click(timeout=15_000)
    page.wait_for_function(
        """(name) => {
          const el = document.getElementById('tab-' + name);
          return el && !el.classList.contains('h');
        }""",
        arg=tab,
        timeout=8000,
    )


@pytest.fixture(scope="module")
def skip_without_server():
    if not _server_reachable():
        pytest.skip(f"UI smoke 需要運行中的服務：{BASE_URL}")


@pytest.fixture(scope="module")
def page(skip_without_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        pg = context.new_page()
        pg.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30_000)
        pg.wait_for_timeout(800)
        _dismiss_modal(pg)
        yield pg
        context.close()
        browser.close()


@pytest.mark.ui
class TestUIPlaywrightSmoke:
    def test_all_sidebar_tabs_become_visible(self, page: Page):
        for tab in SIDEBAR_TABS:
            _click_sidebar_tab(page, tab)
            assert _tab_visible(page, tab), f"tab-{tab} 應為可見"

    def test_compare_tab_does_not_auto_fetch(self, page: Page):
        seen: list[str] = []

        def on_request(request):
            if COMPARE_API_FRAGMENT in request.url:
                seen.append(request.url)

        page.on("request", on_request)
        _click_sidebar_tab(page, "compare")
        page.wait_for_timeout(600)
        assert not seen, f"進入多股對比不應自動請求 compare API，實際：{seen}"

    def test_scheduler_tab_and_reports_shortcut(self, page: Page):
        _click_sidebar_tab(page, "scheduler")
        assert page.locator("#tab-scheduler").is_visible()
        assert page.locator("#schedStatsGrid").count() >= 1

        _click_sidebar_tab(page, "reports")
        page.locator('button:has-text("定時任務管理")').click()
        page.wait_for_function(
            "() => !document.getElementById('tab-scheduler').classList.contains('h')",
            timeout=8000,
        )
        assert _tab_visible(page, "scheduler")

    def test_global_search_navigates_to_scheduler(self, page: Page):
        _click_sidebar_tab(page, "dashboard")
        page.locator("#globalSearch").fill("定時")
        page.wait_for_timeout(400)
        result = page.locator("#searchResults .search-result-item").first
        assert result.count(), "全局搜索應出現「定時任務」等結果"
        result.click()
        page.wait_for_function(
            "() => !document.getElementById('tab-scheduler').classList.contains('h')",
            timeout=8000,
        )
        assert _tab_visible(page, "scheduler")

    def test_crypto_card_opens_crypto_tab(self, page: Page):
        _click_sidebar_tab(page, "dashboard")
        card = page.locator(".crypto-card").first
        try:
            card.wait_for(state="visible", timeout=12_000)
        except Exception:
            pytest.skip("儀表盤無加密卡片（可能未載入行情）")
        card.click()
        page.wait_for_function(
            "() => !document.getElementById('tab-crypto').classList.contains('h')",
            timeout=8000,
        )
        assert _tab_visible(page, "crypto")

    def test_no_switch_tab_console_error(self, page: Page):
        _dismiss_modal(page)
        errors: list[str] = []

        def on_console(msg):
            if msg.type == "error" and "switchTab" in (msg.text or ""):
                errors.append(msg.text)

        page.on("console", on_console)
        for tab in ("dashboard", "compare", "scheduler", "tasks"):
            _click_sidebar_tab(page, tab)
            page.wait_for_timeout(200)
        assert not errors, errors
