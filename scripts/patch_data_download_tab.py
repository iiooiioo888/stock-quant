# -*- coding: utf-8 -*-
from pathlib import Path

D = "d" + "i" + "v"
p = Path(__file__).resolve().parents[1] / "static" / "index.html"
text = p.read_text(encoding="utf-8")

if 'data-dtab="download"' in text:
    print("download tab exists")
else:
    text = text.replace(
        '        <button class="a" data-dtab="sectors">🏭 板塊行情</button>',
        '        <button class="a" data-dtab="download">📥 下載入庫</button>\n'
        '        <button data-dtab="sectors">🏭 板塊行情</button>',
        1,
    )
    block = f"""
    <{D} id="dtab-download" class="mt-md">
        <{D} class="sec">
            <h2>📥 爬取數據並寫入本地庫</h2>
            <p class="sec-desc">從 AKShare / Yahoo / 東財等源拉取日 K，保存到 SQLite（<code>data/stock.db</code>）。回測、對比、基本數據均讀本地庫。</p>
            <{D} class="g" id="dbStatsGrid" style="grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
                <{D} class="c"><h3>標的數</h3><{D} class="v" id="dbStatStocks">-</{D}></{D}>
                <{D} class="c"><h3>K 線條數</h3><{D} class="v" id="dbStatKlines">-</{D}></{D}>
                <{D} class="c"><h3>庫大小</h3><{D} class="v" id="dbStatSize">-</{D}></{D}>
            </{D}>
            <{D} class="fr flex-wrap" style="align-items:flex-end">
                <{D} class="fg" style="flex:1;min-width:280px">
                    <label>A 股代碼（逗號或換行，留空=配置默認 watchlist）</label>
                    <textarea id="dbDownloadCodes" rows="3" class="input-wide" placeholder="000001,600519,000858"></textarea>
                </{D}>
                <{D} class="btn-group">
                    <button class="btn" type="button" onclick="Data.downloadToDb()" id="dbDownloadBtn">📥 下載日 K</button>
                    <button class="btn s" type="button" onclick="Data.incrementalToDb()" id="dbIncrementalBtn">🔄 增量更新</button>
                    <button class="btn s" type="button" onclick="Data.refreshDbStats()">📊 刷新統計</button>
                </{D}>
            </{D}>
            <label class="scr-filter-item mt-sm">
                <input type="checkbox" id="dbForceUpdate">
                <span class="scr-filter-label">強制全量重下（增量更新時）</span>
            </label>
            <{D} id="dbDownloadResult" class="mt-md"></{D}>
            <p class="sec-desc mt-sm">多市場（美股、指數、加密等）請到側欄 <strong>市場</strong> Tab，或儀表盤「下載數據」一鍵下載。</p>
            <button class="btn s mt-sm" type="button" onclick="App.loadTab('markets')">🌐 前往多市場下載</button>
        </{D}>
    </{D}>

"""
    marker = f'    <{D} id="dtab-sectors" class="mt-md">'
    if marker not in text:
        raise SystemExit("dtab-sectors not found")
    text = text.replace(marker, block + marker, 1)
    print("added download panel")

p.write_text(text, encoding="utf-8")
