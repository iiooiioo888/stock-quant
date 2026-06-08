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
    "strategies",
    "backtest",
    "compare",
    "portfolio",
    "watchlist",
    "scanner",
    "alerts",
    "risk",
    "journal",
    "backhistory",
    "ai",
    "factor",
    "seasonal",
    "regime",
    "pricing",
    "settings",
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
          const el = document.getElementById('pg-' + name);
          return !!(el && el.classList.contains('on'));
        }""",
        tab,
    )


def _dismiss_modal(page: Page) -> None:
    close_btn = page.locator('[data-close="m-strat"]').first
    if close_btn.count() and close_btn.is_visible():
        close_btn.click()
        page.wait_for_timeout(150)
    # 關閉命令面板（如有開啟）— 輸入框聚焦時 Escape 被 JS 跳過，用 JS 直接關閉
    page.evaluate("""() => {
        const ov = document.getElementById('cmd-ov');
        if (ov) { ov.classList.remove('show'); ov.setAttribute('aria-hidden', 'true'); }
        document.querySelectorAll('.modal-ov.show').forEach(m => m.classList.remove('show'));
    }""")
    page.wait_for_timeout(100)


def _click_sidebar_tab(page: Page, tab: str) -> None:
    # 確保命令面板已關閉（輸入框聚焦時 Escape 無效，用 JS 直接關閉）
    page.evaluate("""() => {
        const ov = document.getElementById('cmd-ov');
        if (ov) { ov.classList.remove('show'); ov.setAttribute('aria-hidden', 'true'); }
    }""")
    page.wait_for_timeout(100)
    btn = page.locator(f'.sidebar button.sb[data-p="{tab}"]')
    btn.scroll_into_view_if_needed()
    btn.click(timeout=15_000)
    page.wait_for_function(
        """(name) => {
          const el = document.getElementById('pg-' + name);
          return el && el.classList.contains('on');
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
        pg.goto(BASE_URL + "/app", wait_until="domcontentloaded", timeout=30_000)
        pg.wait_for_timeout(800)
        _dismiss_modal(pg)
        yield pg
        context.close()
        browser.close()


@pytest.mark.ui
class TestUISiteEntrypoints:
    def test_marketing_home_has_portals(self, skip_without_server):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30_000)
            assert page.locator(".site-portals").count() >= 1
            assert page.locator('a[href="/app"]').count() >= 1
            page.wait_for_selector("#home-strat-grid .strat-card", timeout=15_000)
            assert page.locator("#home-strat-grid .strat-card").count() >= 50
            browser.close()

    def test_admin_shell_loads(self, skip_without_server):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(
                BASE_URL + "/admin", wait_until="domcontentloaded", timeout=30_000
            )
            assert page.locator("#admin-gate").count() == 1
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

    def test_cmd_palette_opens(self, page: Page):
        _click_sidebar_tab(page, "dashboard")
        page.locator("#cmd-open-btn").click()
        page.wait_for_timeout(200)
        assert page.locator("#cmd-ov").is_visible()
        page.locator("#cmd-in").fill("策略庫")
        page.wait_for_timeout(200)
        assert page.locator("#cmd-list .cmd-item").count() >= 1
        # Escape 在輸入框聚焦時無效，用 JS 直接關閉
        page.evaluate("""() => {
            const ov = document.getElementById('cmd-ov');
            if (ov) { ov.classList.remove('show'); ov.setAttribute('aria-hidden', 'true'); }
        }""")
        page.wait_for_timeout(100)
        assert not page.locator("#cmd-ov.show").is_visible()

    def test_no_switch_tab_console_error(self, page: Page):
        _dismiss_modal(page)
        errors: list[str] = []

        def on_console(msg):
            if msg.type == "error" and "switchTab" in (msg.text or ""):
                errors.append(msg.text)

        page.on("console", on_console)
        for tab in ("dashboard", "compare", "settings", "watchlist"):
            _click_sidebar_tab(page, tab)
            page.wait_for_timeout(200)
        assert not errors, errors
