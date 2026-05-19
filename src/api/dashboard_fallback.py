"""
dashboard_fallback.py — 內建儀表盤 HTML（fallback）

當 static/index.html 不存在時使用此文件提供基本界面。
主要用於：首次部署、static 文件損壞、Render.com 等場景。
"""

def _builtin_dashboard() -> str:
    """內建儀表盤 HTML — 完整版（含 History / Walk-Forward / Reports / 通知渠道）"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>stock-quant</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
.hdr{background:#1e293b;padding:12px 20px;border-bottom:1px solid #334155;display:flex;align-items:center;justify-content:space-between}
.hdr h1{font-size:17px;color:#38bdf8}.hdr .st{font-size:11px;color:#94a3b8}
.wrap{max-width:1320px;margin:0 auto;padding:16px}
.g{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-bottom:14px}
.c{background:#1e293b;border-radius:8px;padding:14px;border:1px solid #334155}
.c h3{font-size:10px;color:#94a3b8;text-transform:uppercase;margin-bottom:4px;letter-spacing:.5px}
.c .v{font-size:22px;font-weight:700;color:#f8fafc}.c .v.gn{color:#22c55e}.c .v.rd{color:#ef4444}.c .v.bl{color:#38bdf8}
table{width:100%;border-collapse:collapse}th,td{padding:7px 8px;text-align:left;border-bottom:1px solid #334155;font-size:12px}
th{color:#94a3b8;font-weight:500;font-size:10px;text-transform:uppercase;letter-spacing:.3px}td.r{text-align:right;font-variant-numeric:tabular-nums}
.b{display:inline-block;padding:2px 5px;border-radius:3px;font-size:10px;font-weight:600}.b.u{background:rgba(34,197,94,.15);color:#22c55e}.b.d{background:rgba(239,68,68,.15);color:#ef4444}.b.f{background:rgba(148,163,184,.15);color:#94a3b8}
.sec{background:#1e293b;border-radius:8px;padding:14px;border:1px solid #334155;margin-bottom:12px}
.sec h2{font-size:13px;margin-bottom:10px;color:#f8fafc;display:flex;align-items:center;gap:6px}
.sec h2 .ct{font-size:10px;color:#64748b;font-weight:400}
.nav{display:flex;gap:5px;margin-bottom:14px;flex-wrap:wrap}
.nav button{background:#334155;border:none;color:#e2e8f0;padding:6px 12px;border-radius:5px;cursor:pointer;font-size:12px;transition:.15s}
.nav button.a{background:#38bdf8;color:#0f172a;font-weight:600}.nav button:hover{background:#475569}
.fr{display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap;align-items:end}
.fg{display:flex;flex-direction:column;gap:2px}.fg label{font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.3px}
.fg input,.fg select{background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:6px 8px;border-radius:5px;font-size:12px;min-width:100px}
.btn{background:#38bdf8;color:#0f172a;border:none;padding:7px 14px;border-radius:5px;cursor:pointer;font-weight:600;font-size:12px;transition:.15s}
.btn:hover{background:#7dd3fc}.btn:disabled{opacity:.5;cursor:not-allowed}.btn.s{background:#334155;color:#e2e8f0}.btn.s:hover{background:#475569}
.btn.danger{background:#ef4444;color:#fff}.btn.danger:hover{background:#f87171}
.ld{display:inline-block;width:12px;height:12px;border:2px solid #334155;border-top-color:#38bdf8;border-radius:50%;animation:sp .6s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.cw{position:relative;height:260px;margin:8px 0}
.cw-tall{position:relative;height:380px;margin:8px 0}
.pc{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.pc-item{background:#0f172a;border:1px solid #334155;border-radius:6px;padding:12px;cursor:pointer;transition:.2s}
.pc-item:hover{border-color:#38bdf8;transform:translateY(-1px)}
.pc-item h4{color:#38bdf8;font-size:13px;margin-bottom:3px}.pc-item p{font-size:11px;color:#94a3b8}
#toast{position:fixed;top:14px;right:14px;background:#1e293b;border:1px solid #38bdf8;padding:8px 14px;border-radius:6px;display:none;z-index:1000;font-size:12px}
.h{display:none}.modal{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.6);z-index:999;display:flex;align-items:center;justify-content:center}
.modal-c{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:20px;max-width:400px;width:90%}
.modal-c h3{margin-bottom:12px;font-size:14px}.modal-c .fg{margin-bottom:8px}
.modal-c .actions{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}
.ws-dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}
.ws-dot.on{background:#22c55e}.ws-dot.off{background:#ef4444}
.chip{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600}
.chip.on{background:rgba(34,197,94,.15);color:#22c55e}
.chip.off{background:rgba(239,68,68,.15);color:#ef4444}
.chip.cfg{background:rgba(56,189,248,.15);color:#38bdf8}
.hm-cell{position:absolute;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;color:#fff;text-shadow:0 0 3px rgba(0,0,0,.5)}
.chip{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;margin:1px}
.chip.on{background:rgba(34,197,94,.15);color:#22c55e}.chip.off{background:rgba(239,68,68,.15);color:#ef4444}.chip.cfg{background:rgba(56,189,248,.15);color:#38bdf8}
pre.rpt{background:#0f172a;border:1px solid #334155;border-radius:6px;padding:12px;font-size:12px;white-space:pre-wrap;max-height:500px;overflow-y:auto;color:#e2e8f0;font-family:monospace;line-height:1.5}
</style>
</head>
<body>
<div class="hdr">
    <h1>📈 stock-quant</h1>
    <div class="st"><span class="ws-dot off" id="wsDot"></span><span id="sysStatus">載入中...</span></div>
</div>
<div class="wrap">
<div class="nav" id="mainNav">
    <button class="a" data-tab="dashboard">儀表盤</button>
    <button data-tab="backtest">回測</button>
    <button data-tab="optimize">優化</button>
    <button data-tab="portfolio">組合</button>
    <button data-tab="compare">對比</button>
    <button data-tab="history">歷史</button>
    <button data-tab="walkforward">Walk-Forward</button>
    <button data-tab="heatmap">熱力圖</button>
    <button data-tab="screener">篩選器</button>
    <button data-tab="reports">報告</button>
    <button data-tab="alerts">預警</button>
    <button data-tab="markets">市場</button>
</div>

<!-- 儀表盤 -->
<div id="tab-dashboard">
    <div class="g" id="statsGrid"></div>
    <div class="sec">
        <h2>監控列表 <span class="ct" id="wlCount"></span></h2>
        <table><thead><tr><th>代碼</th><th>名稱</th><th>突破價</th><th>跌破價</th><th>漲跌幅</th><th>走勢</th><th>操作</th></tr></thead>
        <tbody id="watchlistTable"></tbody></table>
        <div style="margin-top:10px"><button class="btn" onclick="showAddRule()">+ 添加規則</button></div>
    </div>
</div>

<!-- 回測 -->
<div id="tab-backtest" class="h">
    <div class="sec">
        <h2>策略回測</h2>
        <div class="fr">
            <div class="fg"><label>股票代碼</label><input id="btCode" value="600519"></div>
            <div class="fg"><label>策略</label>
                <select id="btStrategy"></select>
            </div>
            <div class="fg"><label>止損 %</label><input id="btSL" type="number" step="0.5" placeholder="0=禁用" style="width:70px"></div>
            <div class="fg"><label>止盈 %</label><input id="btTP" type="number" step="0.5" placeholder="0=禁用" style="width:70px"></div>
            <div class="fg"><label><input type="checkbox" id="btBench"> 基準對比</label></div>
            <button class="btn" onclick="runBacktest()">回測</button>
            <button class="btn s" onclick="runMultiBacktest()">全策略對比</button>
        </div>
    </div>
    <div id="btResult" class="h">
        <div class="g" id="btStats"></div>
        <div class="sec"><h2>風險指標</h2><div class="g" id="btRiskStats"></div></div>
        <div class="sec h"><h2>基準對比（滬深300）</h2><div class="g" id="btBenchStats"></div></div>
        <div class="sec"><h2>K 線 + 買賣信號</h2><div class="cw-tall"><canvas id="btKlineChart"></canvas></div></div>
        <div class="sec"><h2>淨值曲線</h2><div class="cw"><canvas id="btChart"></canvas></div></div>
        <div class="sec"><h2>交易明細 <span class="ct" id="btTradeCount"></span></h2>
            <div style="max-height:300px;overflow-y:auto"><table><thead><tr><th>買入日期</th><th>買價</th><th>賣出日期</th><th>賣價</th><th>數量</th><th>盈虧</th><th>收益率</th><th>持有天數</th></tr></thead><tbody id="btTrades"></tbody></table></div>
        </div>
    </div>
    <div id="btAllResult" class="h">
        <div class="sec"><h2>策略對比 <span class="ct" id="btAllCount"></span></h2>
            <table><thead><tr><th>策略</th><th>收益率</th><th>夏普</th><th>Sortino</th><th>Calmar</th><th>回撤</th><th>VaR95</th><th>勝率</th><th>交易</th></tr></thead><tbody id="btAllTable"></tbody></table>
        </div>
        <div class="sec"><h2>淨值對比</h2><div class="cw"><canvas id="btAllChart"></canvas></div></div>
    </div>
</div>

<!-- 優化 -->
<div id="tab-optimize" class="h">
    <div class="sec">
        <h2>參數優化</h2>
        <div class="fr">
            <div class="fg"><label>股票</label><input id="optCode" value="600519"></div>
            <div class="fg"><label>策略</label><select id="optStrategy"><option value="all">全部</option></select></div>
            <div class="fg"><label>方法</label><select id="optMethod"><option value="grid">網格</option><option value="optuna">Optuna</option></select></div>
            <div class="fg"><label>目標</label><select id="optObjective"><option value="sharpe">夏普</option><option value="return">收益率</option><option value="calmar">Calmar</option></select></div>
            <button class="btn" onclick="runOptimize()" id="optBtn">開始優化</button>
        </div>
        <div style="margin-top:8px"><button class="btn s" onclick="runAutoOptimize()" id="autoOptBtn">⚡ 全自動優化 (watchlist)</button></div>
    </div>
    <div id="optResult" class="h"><div class="sec"><h2>優化結果</h2><div id="optOutput"></div></div></div>
    <div id="autoOptResult" class="h"><div class="sec"><h2>全自動優化結果</h2><pre class="rpt" id="autoOptOutput"></pre></div></div>
</div>

<!-- 組合 -->
<div id="tab-portfolio" class="h">
    <div class="sec"><h2>預設組合</h2><div class="pc" id="presetCards"></div></div>
    <div class="sec">
        <h2>自定義組合</h2>
        <div class="fr">
            <div class="fg"><label>股票</label><input id="pfCodes" value="000001,600519,000858" style="width:160px"></div>
            <div class="fg"><label>策略</label><input id="pfStrategies" value="dual_ma,macd,bollinger,momentum,adx_trend" style="width:160px"></div>
            <div class="fg"><label>再平衡</label><select id="pfRebalance"><option value="none">不</option><option value="periodic">定期</option></select></div>
            <button class="btn" onclick="runPortfolio()" id="pfBtn">回測</button>
        </div>
    </div>
    <div id="pfResult" class="h">
        <div class="g" id="pfStats"></div>
        <div class="sec"><h2>子策略</h2><table><thead><tr><th>策略</th><th>股票</th><th>權重</th><th>收益率</th><th>夏普</th><th>回撤</th></tr></thead><tbody id="pfTable"></tbody></table></div>
        <div class="sec"><h2>淨值曲線</h2><div class="cw"><canvas id="pfChart"></canvas></div></div>
    </div>
</div>

<!-- 對比 -->
<div id="tab-compare" class="h">
    <div class="sec">
        <h2>多股收益率對比</h2>
        <div class="fr">
            <div class="fg"><label>股票（逗號分隔）</label><input id="cmpCodes" value="000001,600519,000858,601318,000333" style="width:250px"></div>
            <div class="fg"><label>天數</label><input id="cmpDays" value="250" type="number" style="width:80px"></div>
            <button class="btn" onclick="runCompare()" id="cmpBtn">對比</button>
        </div>
    </div>
    <div id="cmpResult" class="h">
        <div class="sec"><h2>收益率走勢</h2><div class="cw-tall"><canvas id="cmpChart"></canvas></div></div>
    </div>
</div>

<!-- 歷史 -->
<div id="tab-history" class="h">
    <div class="sec">
        <h2>回測歷史</h2>
        <div class="fr">
            <div class="fg"><label>股票</label><input id="histCode" placeholder="全部"></div>
            <div class="fg"><label>策略</label><input id="histStrategy" placeholder="全部"></div>
            <button class="btn" onclick="loadHistory()">查詢</button>
        </div>
    </div>
    <div class="sec">
        <div style="overflow-x:auto"><table><thead><tr><th>ID</th><th>股票</th><th>策略</th><th>收益率</th><th>夏普</th><th>Sortino</th><th>Calmar</th><th>回撤</th><th>VaR95</th><th>勝率</th><th>交易</th><th>時間</th></tr></thead><tbody id="histTable"></tbody></table></div>
    </div>
</div>

<!-- Walk-Forward -->
<div id="tab-walkforward" class="h">
    <div class="sec">
        <h2>Walk-Forward 分析</h2>
        <div class="fr">
            <div class="fg"><label>股票</label><input id="wfCode" value="600519"></div>
            <div class="fg"><label>策略</label><select id="wfStrategy"></select></div>
            <div class="fg"><label>訓練天數</label><input id="wfTrain" value="750" type="number"></div>
            <div class="fg"><label>測試天數</label><input id="wfTest" value="250" type="number"></div>
            <div class="fg"><label>試驗次數</label><input id="wfTrials" value="30" type="number"></div>
            <button class="btn" onclick="runWalkForward()" id="wfBtn">開始分析</button>
        </div>
    </div>
    <div id="wfResult" class="h">
        <div class="g" id="wfStats"></div>
        <div class="sec"><h2>窗口結果</h2><div style="overflow-x:auto"><table><thead><tr><th>#</th><th>訓練期</th><th>測試期</th><th>測試收益</th><th>測試夏普</th><th>測試回撤</th><th>交易</th><th>參數</th></tr></thead><tbody id="wfTable"></tbody></table></div></div>
        <div class="sec"><h2>樣本外收益走勢</h2><div class="cw"><canvas id="wfChart"></canvas></div></div>
    </div>
</div>

<!-- 報告 -->
<div id="tab-reports" class="h">
    <div class="sec">
        <h2>每日策略報告</h2>
        <div class="fr">
            <button class="btn" onclick="generateReport()" id="rptBtn">生成報告</button>
            <button class="btn s" onclick="enableScheduler()">啟用每日自動報告 (15:30)</button>
            <button class="btn s" onclick="disableScheduler()">禁用</button>
            <button class="btn s" onclick="listSchedulerJobs()">查看任務</button>
        </div>
    </div>
    <div id="rptResult" class="h"><div class="sec"><h2>報告內容</h2><pre class="rpt" id="rptContent"></pre></div></div>
    <div id="schedulerJobs" class="h"><div class="sec"><h2>調度任務</h2><div id="jobsList"></div></div></div>
</div>

<!-- 熱力圖 -->
<div id="tab-heatmap" class="h">
    <div class="sec">
        <h2>策略參數敏感性分析</h2>
        <div class="fr">
            <div class="fg"><label>股票</label><input id="hmCode" value="600519"></div>
            <div class="fg"><label>策略</label>
                <select id="hmStrategy"></select>
            </div>
            <div class="fg"><label>參數 X</label><select id="hmParamX"></select></div>
            <div class="fg"><label>參數 Y</label><select id="hmParamY"></select></div>
            <div class="fg"><label>網格大小</label><input id="hmGrid" value="8" type="number" style="width:60px"></div>
            <button class="btn" onclick="runHeatmap()" id="hmBtn">生成熱力圖</button>
        </div>
    </div>
    <div id="hmResult" class="h">
        <div class="g" id="hmStats"></div>
        <div class="sec"><h2>熱力圖</h2><div style="position:relative;overflow-x:auto"><canvas id="hmCanvas" width="600" height="500"></canvas></div></div>
    </div>
</div>

<!-- 篩選器 -->
<div id="tab-screener" class="h">
    <div class="sec">
        <h2>股票篩選器</h2>
        <div class="fr" style="flex-wrap:wrap;gap:12px">
            <div class="fg"><label><input type="checkbox" id="scrMA"> 均線多頭排列</label></div>
            <div class="fg"><label><input type="checkbox" id="scrVol"> 成交量放大</label><input id="scrVolRatio" value="2.0" type="number" step="0.1" style="width:60px" placeholder="倍數"></div>
            <div class="fg"><label><input type="checkbox" id="scrHigh"> 近52周高點</label><input id="scrHighPct" value="5" type="number" style="width:60px" placeholder="%"></div>
            <div class="fg"><label><input type="checkbox" id="scrChange"> N日漲幅</label><input id="scrChangeDays" value="5" type="number" style="width:50px" placeholder="天"><input id="scrChangePct" value="5" type="number" style="width:50px" placeholder="%"></div>
            <div class="fg"><label><input type="checkbox" id="scrAboveMA"> 站上均線</label><input id="scrMAPeriod" value="20" type="number" style="width:50px" placeholder="MA"></div>
            <button class="btn" onclick="runScreener()" id="scrBtn">開始篩選</button>
        </div>
    </div>
    <div id="scrResult" class="h">
        <div class="sec"><h2>篩選結果 <span class="ct" id="scrCount"></span></h2>
            <div style="max-height:400px;overflow-y:auto"><table><thead><tr><th>代碼</th><th>名稱</th><th>匹配條件</th><th>操作</th></tr></thead><tbody id="scrTable"></tbody></table></div>
        </div>
    </div>
</div>

<!-- 預警 -->
<div id="tab-alerts" class="h">
    <div class="sec">
        <h2>通知渠道</h2>
        <div id="notifyChannels"><p style="color:#64748b">載入中...</p></div>
        <div style="margin-top:10px"><button class="btn" onclick="testNotify()" id="testNotifyBtn">🔔 測試所有渠道</button></div>
    </div>
    <div class="sec"><h2>預警歷史</h2><div id="alertList"><p style="color:#64748b">載入中...</p></div></div>
</div>

<!-- 市場 -->
<div id="tab-markets" class="h">
    <div class="sec">
        <h2>🌐 多市場支持</h2>
        <div id="marketCards" class="g" style="grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px">
            <p style="color:#64748b">載入中...</p>
        </div>
    </div>
    <div class="sec">
        <h2>📥 下載數據</h2>
        <div class="fr">
            <div class="fg"><label>市場</label>
                <select id="dlMarket">
                    <option value="us_stock">🇺🇸 美股</option>
                    <option value="hk_stock">🇭🇰 港股</option>
                    <option value="index">📈 全球指數</option>
                    <option value="etf">📦 ETF</option>
                    <option value="crypto">₿ 加密貨幣</option>
                    <option value="forex">💱 外匯</option>
                    <option value="commodity">🛢️ 商品期貨</option>
                    <option value="a_share">🇨🇳 A股</option>
                </select>
            </div>
            <div class="fg"><label>標的</label><input id="dlSymbols" placeholder="留空=使用默認列表" style="width:200px"></div>
            <button class="btn" onclick="downloadMarket()" id="dlMarketBtn">下載</button>
        </div>
        <div id="dlMarketResult" style="margin-top:10px"></div>
    </div>
    <div class="sec">
        <h2>📊 實時行情</h2>
        <div class="fr">
            <div class="fg"><label>市場</label>
                <select id="rtMarket" onchange="loadMarketRealtime()">
                    <option value="us_stock">🇺🇸 美股</option>
                    <option value="hk_stock">🇭🇰 港股</option>
                    <option value="index">📈 全球指數</option>
                    <option value="etf">📦 ETF</option>
                    <option value="crypto">₿ 加密貨幣</option>
                    <option value="forex">💱 外匯</option>
                    <option value="commodity">🛢️ 商品期貨</option>
                </select>
            </div>
        </div>
        <div id="rtMarketData" style="margin-top:10px"><p style="color:#64748b">選擇市場查看實時行情</p></div>
    </div>
</div>
</div>

<div id="toast"></div>
<div id="modalRoot"></div>

<script>
const API='';
let ws=null,wsRetry=0;

// === Tab ===
document.getElementById('mainNav').addEventListener('click',e=>{
    if(!e.target.dataset.tab)return;
    document.querySelectorAll('[id^="tab-"]').forEach(el=>el.classList.add('h'));
    document.getElementById('tab-'+e.target.dataset.tab).classList.remove('h');
    document.querySelectorAll('.nav button').forEach(b=>b.classList.remove('a'));
    e.target.classList.add('a');
    const t=e.target.dataset.tab;
    if(t==='alerts'){loadAlerts();loadNotifyChannels();}
    if(t==='markets')loadMarkets();
    if(t==='portfolio')loadPresets();
    if(t==='history')loadHistory();
    if(t==='heatmap')updateHeatmapParams();
    if(t==='screener'){}
});

function toast(m){const el=document.getElementById('toast');el.textContent=m;el.style.display='block';setTimeout(()=>el.style.display='none',3000)}
async function api(p,o=null){try{const r=await fetch(API+p,o);return await r.json()}catch(e){toast('失敗: '+e.message);return null}}
function fp(v){if(v==null)return'N/A';return(v>=0?'+':'')+v.toFixed(2)+'%'}
function fn(v,d=2){if(v==null)return'N/A';return v.toFixed(d)}
function bc(v){if(v>0.01)return'u';if(v<-0.01)return'd';return'f'}

// === WebSocket ===
function connectWS(){
    const proto=location.protocol==='https:'?'wss:':'ws:';
    ws=new WebSocket(`${proto}//${location.host}/ws`);
    ws.onopen=()=>{document.getElementById('wsDot').className='ws-dot on';wsRetry=0};
    ws.onclose=()=>{document.getElementById('wsDot').className='ws-dot off';setTimeout(connectWS,Math.min(1000*Math.pow(2,wsRetry),30000));wsRetry++};
    ws.onmessage=e=>{
        try{const d=JSON.parse(e.data);if(d.type==='quotes')updateRealtimeQuotes(d.data)}catch{}
    };
    setInterval(()=>{if(ws&&ws.readyState===1)ws.send('ping')},25000);
}
function updateRealtimeQuotes(data){
    const rows=data.map(r=>`<tr><td>${r.code}</td><td>${r.price?.toFixed(2)||'-'}</td><td class="r"><span class="b ${bc(r.change_pct)}">${fp(r.change_pct)}</span></td><td class="r">${r.volume?.toLocaleString()||'-'}</td></tr>`).join('');
    const el=document.getElementById('rtQuotes');
    if(el)el.innerHTML=rows;
}

// === 儀表盤 ===
async function loadDashboard(){
    const d=await api('/api/health');if(!d)return;
    document.getElementById('statsGrid').innerHTML=`
        <div class="c"><h3>監控股票</h3><div class="v bl">${d.total_stocks||0}</div></div>
        <div class="c"><h3>數據條數</h3><div class="v">${(d.total_klines||0).toLocaleString()}</div></div>
        <div class="c"><h3>累計預警</h3><div class="v rd">${d.total_alerts||0}</div></div>
        <div class="c"><h3>數據庫</h3><div class="v">${d.db_size_mb||0} MB</div></div>`;
    document.getElementById('sysStatus').textContent='運行 '+d.uptime;
    loadRules();
    loadWatchlistWithSparkline();
}

async function loadWatchlistWithSparkline(){
    const d=await api('/api/alerts/rules');if(!d)return;
    const rules=d.rules||[];
    const codes=rules.map(r=>r.code);
    document.getElementById('wlCount').textContent='('+rules.length+')';

    // 獲取迷你走勢圖
    let sparklines={};
    if(codes.length>0){
        try{const sp=await api('/api/sparkline?codes='+codes.join(',')+'&days=20');if(sp)sparklines=sp.sparklines||{}}catch{}
    }

    if(rules.length===0){
        document.getElementById('watchlistTable').innerHTML='<tr><td colspan="6" style="color:var(--text-dim);text-align:center">暫無監控，點擊下方添加</td></tr>';
        return;
    }
    document.getElementById('watchlistTable').innerHTML=rules.map(r=>{
        const sp=sparklines[r.code]||{};
        const prices=sp.prices||[];
        const pct=sp.change_pct||0;
        const cls=pct>=0?'u':'d';
        const miniChart=prices.length>2?drawMiniSparkline(prices,pct>=0):'';
        return `<tr>
            <td>${r.code}</td>
            <td>${r.name||''}</td>
            <td>${r.breakout_price||'-'}</td>
            <td>${r.breakdown_price||'-'}</td>
            <td><span class="b ${cls}">${pct>=0?'+':''}${pct.toFixed(2)}%</span></td>
            <td><canvas id="sp_${r.code}" width="80" height="28" style="vertical-align:middle"></canvas></td>
            <td><button class="btn danger" style="padding:3px 8px;font-size:10px" onclick="deleteRule(${r.id})">刪除</button></td>
        </tr>`;
    }).join('');

    // 繪製迷你走勢圖
    rules.forEach(r=>{
        const sp=sparklines[r.code];
        if(sp&&sp.prices&&sp.prices.length>2){
            drawMiniCanvas('sp_'+r.code,sp.prices,sp.change_pct>=0);
        }
    });
}

function drawMiniCanvas(canvasId,prices,isUp){
    const canvas=document.getElementById(canvasId);if(!canvas)return;
    const ctx=canvas.getContext('2d');
    const w=canvas.width,h=canvas.height;
    ctx.clearRect(0,0,w,h);
    const min=Math.min(...prices),max=Math.max(...prices);
    const range=max-min||1;
    const color=isUp?'#22c55e':'#ef4444';
    ctx.beginPath();
    ctx.strokeStyle=color;
    ctx.lineWidth=1.5;
    prices.forEach((p,i)=>{
        const x=i/(prices.length-1)*w;
        const y=h-((p-min)/range)*(h-4)-2;
        i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
    });
    ctx.stroke();
    // 填充漸變
    const grad=ctx.createLinearGradient(0,0,0,h);
    grad.addColorStop(0,color+'30');
    grad.addColorStop(1,color+'05');
    ctx.lineTo(w,h);ctx.lineTo(0,h);ctx.closePath();
    ctx.fillStyle=grad;ctx.fill();
}
async function loadRules(){
    const d=await api('/api/alerts/rules');if(!d)return;
    const entries=Object.entries(d.rules||{});
    document.getElementById('wlCount').textContent=entries.length+' 只';
    document.getElementById('watchlistTable').innerHTML=entries.map(([c,r])=>
        `<tr><td>${c}</td><td>${r.name||sn(c)||'-'}</td><td class="r">${r.price_above||'-'}</td><td class="r">${r.price_below||'-'}</td><td class="r">±${r.change_pct||'-'}%</td>
        <td><button class="btn s" style="padding:3px 8px;font-size:10px" onclick="editRule('${c}')">編輯</button> <button class="btn danger" style="padding:3px 8px;font-size:10px" onclick="deleteRule('${c}')">刪除</button></td></tr>`
    ).join('');
}

// === 預警規則管理 ===
function showAddRule(){showRuleModal(null,{});}
function editRule(code){api('/api/alerts/rules').then(d=>{if(d)showRuleModal(code,d.rules[code]||{})});}
function showRuleModal(code,rule){
    const isEdit=!!code;
    document.getElementById('modalRoot').innerHTML=`<div class="modal" onclick="if(event.target===this)closeModal()">
        <div class="modal-c">
            <h3>${isEdit?'編輯':'添加'}預警規則</h3>
            <div class="fg"><label>股票代碼</label><input id="mrCode" value="${code||''}" ${isEdit?'readonly':''}></div>
            <div class="fg"><label>名稱</label><input id="mrName" value="${rule.name||''}"></div>
            <div class="fg"><label>突破價</label><input id="mrAbove" type="number" step="0.01" value="${rule.price_above||''}"></div>
            <div class="fg"><label>跌破價</label><input id="mrBelow" type="number" step="0.01" value="${rule.price_below||''}"></div>
            <div class="fg"><label>漲跌幅閾值 (%)</label><input id="mrPct" type="number" step="0.1" value="${rule.change_pct||''}"></div>
            <div class="actions">
                <button class="btn s" onclick="closeModal()">取消</button>
                <button class="btn" onclick="saveRule()">保存</button>
            </div>
        </div>
    </div>`;
}
function closeModal(){document.getElementById('modalRoot').innerHTML='';}
async function saveRule(){
    const code=document.getElementById('mrCode').value.trim();
    if(!code)return toast('請輸入股票代碼');
    const rule={
        name:document.getElementById('mrName').value,
        price_above:parseFloat(document.getElementById('mrAbove').value)||null,
        price_below:parseFloat(document.getElementById('mrBelow').value)||null,
        change_pct:parseFloat(document.getElementById('mrPct').value)||null,
    };
    const rules={};rules[code]=rule;
    const d=await api('/api/alerts/rules',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(rules)});
    if(d){toast('保存成功');closeModal();loadRules();}
}
async function deleteRule(code){
    if(!confirm(`確定刪除 ${code} 的預警規則？`))return;
    const d=await api('/api/alerts/rules/'+encodeURIComponent(code),{method:'DELETE'});
    if(d){toast('已刪除');loadRules();}
}

// === 回測（增強版：含風險指標） ===
async function runBacktest(){
    const code=document.getElementById('btCode').value;
    const strategy=document.getElementById('btStrategy').value;
    const sl=document.getElementById('btSL').value;
    const tp=document.getElementById('btTP').value;
    const bench=document.getElementById('btBench').checked;
    document.getElementById('btResult').classList.add('h');
    document.getElementById('btAllResult').classList.add('h');
    let url=`/api/backtest?code=${code}&strategy=${strategy}`;
    if(sl)url+=`&stop_loss_pct=${sl}`;
    if(tp)url+=`&take_profit_pct=${tp}`;
    if(bench)url+=`&benchmark=true`;
    const d=await api(url,{method:'POST'});
    if(!d||!d.success)return;
    const r=d.result;
    document.getElementById('btStats').innerHTML=`
        <div class="c"><h3>股票</h3><div class="v bl">${code} ${sn(code)}</div></div>
        <div class="c"><h3>收益率</h3><div class="v ${bc(r.total_return_pct)}">${fp(r.total_return_pct)}</div></div>
        <div class="c"><h3>年化收益</h3><div class="v ${bc(r.annual_return_pct)}">${fp(r.annual_return_pct)}</div></div>
        <div class="c"><h3>夏普比率</h3><div class="v">${fn(r.sharpe_ratio,4)}</div></div>
        <div class="c"><h3>最大回撤</h3><div class="v rd">${fp(-r.max_drawdown_pct)}</div></div>
        <div class="c"><h3>勝率</h3><div class="v">${fn(r.win_rate_pct,1)}%</div></div>
        <div class="c"><h3>交易次數</h3><div class="v">${r.total_trades}</div></div>
        <div class="c"><h3>最終市值</h3><div class="v">¥${r.final_value.toLocaleString(undefined,{maximumFractionDigits:0})}</div></div>`;
    // 風險指標
    document.getElementById('btRiskStats').innerHTML=`
        <div class="c"><h3>VaR 95%</h3><div class="v rd">${fn(r.var_95,4)}</div></div>
        <div class="c"><h3>CVaR 95%</h3><div class="v rd">${fn(r.cvar_95,4)}</div></div>
        <div class="c"><h3>Sortino</h3><div class="v">${fn(r.sortino_ratio,4)}</div></div>
        <div class="c"><h3>Calmar</h3><div class="v">${fn(r.calmar_ratio,4)}</div></div>
        <div class="c"><h3>年化波動率</h3><div class="v">${fn(r.annual_volatility,4)}</div></div>
        <div class="c"><h3>月勝率</h3><div class="v">${fn(r.monthly_win_rate,1)}%</div></div>
        <div class="c"><h3>盈虧比</h3><div class="v">${fn(r.profit_loss_ratio,2)}</div></div>
        <div class="c"><h3>回撤恢復天數</h3><div class="v">${r.max_drawdown_recovery_days||0}</div></div>`;
    // 基準對比
    const benchDiv=document.getElementById('btBenchStats');
    if(r.benchmark_comparison){const b=r.benchmark_comparison;
        benchDiv.innerHTML=`<div class="c"><h3>Alpha</h3><div class="v ${bc(b.alpha)}">${fn(b.alpha,4)}</div></div><div class="c"><h3>Beta</h3><div class="v">${fn(b.beta,4)}</div></div><div class="c"><h3>信息比率</h3><div class="v">${fn(b.information_ratio,4)}</div></div><div class="c"><h3>跟蹤誤差</h3><div class="v">${fn(b.tracking_error,4)}</div></div>`;
        benchDiv.parentElement.classList.remove('h');
    }else{benchDiv.parentElement.classList.add('h');}
    drawKlineChart('btKlineChart',r.kline,r.signals,`${code} ${sn(code)} — ${strategy}`);
    drawLineChart('btChart',[{label:`${code} ${sn(code)} ${strategy}`,data:r.nav,dates:r.dates}]);
    const trades=r.trade_details||[];
    document.getElementById('btTradeCount').textContent=trades.length+' 筆';
    document.getElementById('btTrades').innerHTML=trades.map(t=>
        `<tr><td>${t.buy_date}</td><td class="r">${t.buy_price}</td><td>${t.sell_date}</td><td class="r">${t.sell_price}</td><td class="r">${t.size}</td><td class="r"><span class="b ${bc(t.pnl)}">${t.pnl>=0?'+':''}${t.pnl}</span></td><td class="r"><span class="b ${bc(t.return_pct)}">${fp(t.return_pct)}</span></td><td class="r">${t.hold_days}</td></tr>`
    ).join('');
    document.getElementById('btResult').classList.remove('h');
}

async function runMultiBacktest(){
    const code=document.getElementById('btCode').value;
    document.getElementById('btResult').classList.add('h');
    document.getElementById('btAllResult').classList.add('h');
    const d=await api(`/api/backtest/multi?code=${code}`,{method:'POST'});
    if(!d||!d.success)return;
    const results=d.results;
    document.getElementById('btAllCount').textContent=results.length+' 個策略';
    document.getElementById('btAllTable').innerHTML=results.map(r=>`<tr>
        <td><strong>${r.strategy}</strong></td>
        <td class="r"><span class="b ${bc(r.total_return_pct)}">${fp(r.total_return_pct)}</span></td>
        <td class="r">${fn(r.sharpe_ratio,2)}</td>
        <td class="r">${fn(r.sortino_ratio,2)}</td>
        <td class="r">${fn(r.calmar_ratio,2)}</td>
        <td class="r">${fp(-r.max_drawdown_pct)}</td>
        <td class="r">${fn(r.var_95,4)}</td>
        <td class="r">${fn(r.win_rate_pct,1)}%</td>
        <td class="r">${r.total_trades}</td></tr>`).join('');
    const series=results.filter(r=>r.nav&&r.nav.length>1).map(r=>({label:r.strategy,data:r.nav,dates:r.dates}));
    drawLineChart('btAllChart',series);
    document.getElementById('btAllResult').classList.remove('h');
}

// === 優化 ===
async function runOptimize(){
    const code=document.getElementById('optCode').value,strategy=document.getElementById('optStrategy').value,method=document.getElementById('optMethod').value,objective=document.getElementById('optObjective').value;
    const btn=document.getElementById('optBtn');btn.disabled=true;btn.innerHTML='<span class="ld"></span> 優化中...';
    const d=await api(`/api/optimize?code=${code}&strategy=${strategy}&method=${method}&objective=${objective}&n_trials=50`,{method:'POST'});
    btn.disabled=false;btn.textContent='開始優化';
    if(!d||!d.success)return;
    const el=document.getElementById('optOutput');let h='';
    const results=d.results;
    if(strategy==='all'){
        for(const[n,rl]of Object.entries(results)){
            if(!rl||!rl.length){h+=`<div style="margin-bottom:6px"><strong>${n}</strong>: <span style="color:#64748b">無結果</span></div>`;continue}
            const b=rl[0];
            h+=`<div style="margin-bottom:8px;padding:8px;background:#0f172a;border-radius:5px"><strong style="color:#38bdf8">${n}</strong> <span style="margin-left:10px">夏普 <b>${fn(b.sharpe_ratio,2)}</b></span> <span style="margin-left:10px">收益 <b>${fp(b.total_return_pct)}</b></span> <span style="margin-left:10px;font-size:11px;color:#94a3b8">${Object.entries(b.params).map(([k,v])=>k+'='+v).join(', ')}</span></div>`;
        }
    }else{
        h='<table><thead><tr><th>#</th><th>評分</th><th>收益率</th><th>夏普</th><th>回撤</th><th>勝率</th><th>參數</th></tr></thead><tbody>';
        results.forEach((r,i)=>{h+=`<tr><td>${i+1}</td><td class="r">${fn(r.score,4)}</td><td class="r"><span class="b ${bc(r.total_return_pct)}">${fp(r.total_return_pct)}</span></td><td class="r">${fn(r.sharpe_ratio,2)}</td><td class="r">${fp(-r.max_drawdown_pct)}</td><td class="r">${fn(r.win_rate_pct,1)}%</td><td style="font-size:10px;color:#94a3b8">${Object.entries(r.params).map(([k,v])=>k+'='+v).join(', ')}</td></tr>`});
        h+='</tbody></table>';
    }
    el.innerHTML=h;document.getElementById('optResult').classList.remove('h');
}

async function runAutoOptimize(){
    const btn=document.getElementById('autoOptBtn');btn.disabled=true;btn.innerHTML='<span class="ld"></span> 全自動優化中...';
    const d=await api('/api/auto-optimize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'optuna',n_trials:30,objective:'sharpe'})});
    btn.disabled=false;btn.textContent='⚡ 全自動優化 (watchlist)';
    if(!d||!d.success)return toast('失敗');
    document.getElementById('autoOptOutput').textContent=d.result.summary||JSON.stringify(d.result,null,2);
    document.getElementById('autoOptResult').classList.remove('h');
    toast('全自動優化完成');
}

// === 組合 ===
async function loadPresets(){
    const d=await api('/api/config');if(!d)return;
    const p=d.portfolio_presets||{};
    document.getElementById('presetCards').innerHTML=Object.entries(p).map(([k,v])=>
        `<div class="pc-item" onclick="runPreset('${k}')"><h4>${v.name}</h4><p>${v.desc}</p><p style="margin-top:4px;font-size:10px;color:#64748b">${v.allocations.length} 子策略 · ${v.rebalance==='periodic'?'定期再平衡':'不再平衡'}</p></div>`).join('');
}
async function runPreset(n){const d=await api(`/api/portfolio/preset/${n}`,{method:'POST'});if(!d||!d.success)return toast('失敗');showPF(d.result);toast(d.preset+' 完成');}
async function runPortfolio(){
    const codes=document.getElementById('pfCodes').value.split(',').map(s=>s.trim()),strategies=document.getElementById('pfStrategies').value.split(',').map(s=>s.trim()),rebalance=document.getElementById('pfRebalance').value;
    const btn=document.getElementById('pfBtn');btn.disabled=true;btn.innerHTML='<span class="ld"></span> 回測中...';
    const alloc=[];codes.forEach(c=>strategies.forEach(s=>alloc.push({strategy:s,code:c})));
    const d=await api('/api/portfolio',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({allocations:alloc,rebalance,rebalance_freq_days:20})});
    btn.disabled=false;btn.textContent='回測';if(!d||!d.success)return toast('失敗');showPF(d.result);
}
function showPF(r){
    const pm=r.portfolio||{};
    document.getElementById('pfStats').innerHTML=`<div class="c"><h3>組合收益</h3><div class="v ${bc(pm.total_return_pct)}">${fp(pm.total_return_pct)}</div></div><div class="c"><h3>年化</h3><div class="v">${fp(pm.annual_return_pct)}</div></div><div class="c"><h3>夏普</h3><div class="v">${fn(pm.sharpe_ratio,4)}</div></div><div class="c"><h3>回撤</h3><div class="v rd">${fp(-pm.max_drawdown_pct)}</div></div>`;
    document.getElementById('pfTable').innerHTML=(r.sub_strategies||[]).map(s=>`<tr><td>${s.strategy}</td><td>${s.code}</td><td class="r">${(s.weight*100).toFixed(0)}%</td><td class="r"><span class="b ${bc(s.total_return_pct)}">${fp(s.total_return_pct)}</span></td><td class="r">${fn(s.sharpe_ratio,2)}</td><td class="r">${fp(-s.max_drawdown_pct)}</td></tr>`).join('');
    const series=[];if(r.portfolio_nav)series.push({label:'組合',data:r.portfolio_nav,dates:r.dates});if(r.equal_weight_nav)series.push({label:'等權',data:r.equal_weight_nav,dates:r.dates});
    if(series.length)drawLineChart('pfChart',series);
    document.getElementById('pfResult').classList.remove('h');
}

// === 對比 ===
let cmpChart=null;
async function runCompare(){
    const codes=document.getElementById('cmpCodes').value.split(',').map(s=>s.trim()),days=parseInt(document.getElementById('cmpDays').value)||250;
    const btn=document.getElementById('cmpBtn');btn.disabled=true;btn.innerHTML='<span class="ld"></span>';
    const d=await api('/api/stocks/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codes,days})});
    btn.disabled=false;btn.textContent='對比';if(!d)return;
    const comp=d.comparison||{};const series=[];
    for(const[code,v]of Object.entries(comp)){series.push({label:code,data:v.relative_return,dates:v.dates})}
    if(series.length){drawLineChart('cmpChart',series);document.getElementById('cmpResult').classList.remove('h');}
}

// === 歷史 ===
async function loadHistory(){
    const code=document.getElementById('histCode')?.value?.trim()||'';
    const strategy=document.getElementById('histStrategy')?.value?.trim()||'';
    let url='/api/backtest/history?limit=100';
    if(code)url+='&code='+encodeURIComponent(code);
    if(strategy)url+='&strategy='+encodeURIComponent(strategy);
    const d=await api(url);
    if(!d)return;
    const rows=d.results||[];
    document.getElementById('histTable').innerHTML=rows.map(r=>`<tr>
        <td>${r.id}</td><td>${r.code}</td><td>${r.strategy}</td>
        <td class="r"><span class="b ${bc(r.total_return_pct)}">${fp(r.total_return_pct)}</span></td>
        <td class="r">${fn(r.sharpe_ratio,2)}</td>
        <td class="r">${fn(r.sortino_ratio,2)}</td>
        <td class="r">${fn(r.calmar_ratio,2)}</td>
        <td class="r">${fp(-r.max_drawdown_pct)}</td>
        <td class="r">${fn(r.var_95,4)}</td>
        <td class="r">${fn(r.win_rate_pct,1)}%</td>
        <td class="r">${r.total_trades||0}</td>
        <td style="font-size:10px;color:#64748b">${r.created_at||''}</td>
    </tr>`).join('')||'<tr><td colspan="12" style="color:#64748b;text-align:center">暫無回測歷史</td></tr>';
}

// === Walk-Forward ===
async function runWalkForward(){
    const code=document.getElementById('wfCode').value;
    const strategy=document.getElementById('wfStrategy').value;
    const train=parseInt(document.getElementById('wfTrain').value)||750;
    const test=parseInt(document.getElementById('wfTest').value)||250;
    const trials=parseInt(document.getElementById('wfTrials').value)||30;
    const btn=document.getElementById('wfBtn');btn.disabled=true;btn.innerHTML='<span class="ld"></span> 分析中...';
    const d=await api(`/api/walkforward?code=${code}&strategy=${strategy}&train_days=${train}&test_days=${test}&n_trials=${trials}`,{method:'POST'});
    btn.disabled=false;btn.textContent='開始分析';
    if(!d||!d.success)return toast('失敗: '+(d.detail||''));
    const r=d.result;
    document.getElementById('wfStats').innerHTML=`
        <div class="c"><h3>窗口數</h3><div class="v bl">${r.n_windows}</div></div>
        <div class="c"><h3>平均 OOS 收益</h3><div class="v ${bc(r.avg_oos_return_pct)}">${fp(r.avg_oos_return_pct)}</div></div>
        <div class="c"><h3>平均 OOS 夏普</h3><div class="v">${fn(r.avg_oos_sharpe,4)}</div></div>
        <div class="c"><h3>穩定性</h3><div class="v">${fn(r.stability_score,4)}</div></div>
        <div class="c"><h3>過擬合比</h3><div class="v rd">${fn(r.overfit_ratio,4)}</div></div>
        <div class="c"><h3>正收益窗口</h3><div class="v gn">${r.positive_windows}/${r.total_windows}</div></div>`;
    const wins=r.windows||[];
    document.getElementById('wfTable').innerHTML=wins.map(w=>`<tr>
        <td>${w.window}</td><td style="font-size:10px">${w.train_period}</td><td style="font-size:10px">${w.test_period}</td>
        <td class="r"><span class="b ${bc(w.test_return_pct)}">${fp(w.test_return_pct)}</span></td>
        <td class="r">${fn(w.test_sharpe,2)}</td><td class="r">${fp(-w.test_max_dd_pct)}</td>
        <td class="r">${w.test_trades}</td>
        <td style="font-size:9px;color:#64748b">${Object.entries(w.best_params||{}).map(([k,v])=>k+'='+v).join(', ')}</td>
    </tr>`).join('');
    // OOS 收益走勢圖
    const oosReturns=wins.map(w=>w.test_return_pct);
    const oosLabels=wins.map(w=>'W'+w.window);
    drawBarChart('wfChart',oosReturns,oosLabels,'樣本外收益率 (%)');
    document.getElementById('wfResult').classList.remove('h');
    toast('Walk-Forward 分析完成');
}

// === 報告 ===
async function generateReport(){
    const btn=document.getElementById('rptBtn');btn.disabled=true;btn.innerHTML='<span class="ld"></span> 生成中...';
    // 用 fetch 直接拿文本
    try{
        const r=await fetch('/api/scheduler/jobs');const d=await r.json();
        // 生成報告: 通過跑 backtest 模擬
        const codes=['000001','600519','000858'];
        let report='📊 每日策略報告\\n'+new Date().toLocaleString('zh-CN')+'\\n'+'='.repeat(40)+'\\n\\n';
        for(const code of codes){
            try{
                const br=await fetch(`/api/backtest?code=${code}&strategy=dual_ma`,{method:'POST'});
                const bd=await br.json();
                if(bd.success){
                    const r2=bd.result;
                    report+=`🏆 ${code}: dual_ma | 夏普 ${r2.sharpe_ratio?.toFixed(2)} | 收益 ${r2.total_return_pct?.toFixed(2)}% | 回撤 ${r2.max_drawdown_pct?.toFixed(1)}%\\n`;
                }
            }catch{}
        }
        report+='\\n'+'='.repeat(40);
        document.getElementById('rptContent').textContent=report;
        document.getElementById('rptResult').classList.remove('h');
    }catch{}
    btn.disabled=false;btn.textContent='生成報告';
}

async function enableScheduler(){
    const d=await api('/api/scheduler/enable',{method:'POST'});
    if(d)toast(d.message||'已啟用');
}
async function disableScheduler(){
    const d=await api('/api/scheduler/disable',{method:'POST'});
    if(d)toast(d.message||'已禁用');
}
async function listSchedulerJobs(){
    const d=await api('/api/scheduler/jobs');
    if(!d)return;
    const jobs=d.jobs||[];
    if(jobs.length){
        document.getElementById('jobsList').innerHTML='<table><thead><tr><th>ID</th><th>名稱</th><th>下次執行</th><th>觸發器</th></tr></thead><tbody>'+
            jobs.map(j=>`<tr><td>${j.id}</td><td>${j.name}</td><td>${j.next_run||'-'}</td><td style="font-size:10px">${j.trigger}</td></tr>`).join('')+'</tbody></table>';
    }else{
        document.getElementById('jobsList').innerHTML='<p style="color:#64748b">無調度任務</p>';
    }
    document.getElementById('schedulerJobs').classList.remove('h');
}

// === 預警 + 通知渠道 ===
async function loadAlerts(){
    const d=await api('/api/alerts?limit=50');const el=document.getElementById('alertList');
    if(d&&d.alerts.length>0){el.innerHTML=d.alerts.map(a=>`<div style="padding:8px;border-bottom:1px solid #334155"><div style="font-size:12px">${a.message}</div><div style="font-size:10px;color:#64748b;margin-top:2px">${a.triggered_at}</div></div>`).join('')}
    else{el.innerHTML='<p style="color:#64748b;padding:16px">暫無預警</p>'}
}

async function loadNotifyChannels(){
    const d=await api('/api/notify/channels');
    if(!d)return;
    const chs=d.channels||[];
    document.getElementById('notifyChannels').innerHTML=chs.map(ch=>{
        const statusChip=ch.enabled?'<span class="chip on">啟用</span>':'<span class="chip off">禁用</span>';
        const cfgChip=ch.configured?'<span class="chip cfg">已配置</span>':'<span class="chip off">未配置</span>';
        return `<div style="display:inline-flex;align-items:center;gap:6px;margin:4px 8px 4px 0;padding:6px 10px;background:#0f172a;border:1px solid #334155;border-radius:6px"><span style="font-size:12px;font-weight:500">${ch.name}</span>${statusChip}${cfgChip}</div>`;
    }).join('');
}

async function testNotify(){
    const btn=document.getElementById('testNotifyBtn');btn.disabled=true;btn.innerHTML='<span class="ld"></span> 發送中...';
    const d=await api('/api/notify/test',{method:'POST'});
    btn.disabled=false;btn.textContent='🔔 測試所有渠道';
    if(!d)return toast('失敗');
    const r=d.results||{};
    const summary=Object.entries(r).map(([k,v])=>`${k}: ${v}`).join(', ');
    toast('測試結果: '+summary);
}

// === 多市場 ===
async function loadMarkets(){
    try{
        const d=await api('/api/markets');
        if(!d||!d.markets)return;
        const el=document.getElementById('marketCards');
        const colors={a_share:'#ef4444',crypto:'#f59e0b',forex:'#22c55e',us_stock:'#38bdf8',hk_stock:'#ec4899',index:'#a78bfa',etf:'#06b6d4',commodity:'#f59e0b',forex_yahoo:'#22c55e'};
        el.innerHTML=d.markets.map(m=>{
            const c=colors[m.market]||'#38bdf8';
            return `<div style="background:var(--card,#1e293b);border:1px solid var(--border,#334155);border-radius:10px;padding:16px">
                <div style="font-size:28px;margin-bottom:8px">${m.icon||'📊'}</div>
                <div style="font-size:16px;font-weight:600;color:var(--text,#e2e8f0)">${m.name}</div>
                <div style="font-size:12px;color:#64748b;margin:4px 0">${m.description}</div>
                <div style="font-size:20px;font-weight:700;color:${c}">${m.data_count} <span style="font-size:12px;font-weight:400;color:#64748b">條記錄</span></div>
            </div>`;
        }).join('');
    }catch(e){console.warn('載入市場失敗:',e)}
}
async function downloadMarket(){
    const market=document.getElementById('dlMarket').value;
    const symInput=document.getElementById('dlSymbols').value.trim();
    const btn=document.getElementById('dlMarketBtn');
    const body=symInput?symInput.split(',').map(s=>s.trim()):null;
    btn.disabled=true;btn.innerHTML='<span class="ld"></span> 下載中...';
    const d=await api(`/api/markets/${market}/download`,{method:'POST',body:JSON.stringify(body),headers:{'Content-Type':'application/json'}});
    btn.disabled=false;btn.textContent='下載';
    const el=document.getElementById('dlMarketResult');
    if(d&&d.success){
        el.innerHTML=`<div class="chip on">✅ ${market} 下載完成: ${d.total_records} 條記錄</div>`;
        loadMarkets();
    }else{
        el.innerHTML=`<div class="chip off">❌ 下載失敗</div>`;
    }
}
async function loadMarketRealtime(){
    const market=document.getElementById('rtMarket').value;
    const el=document.getElementById('rtMarketData');
    el.innerHTML='<p style="color:#64748b">載入中...</p>';
    const d=await api(`/api/markets/${market}/realtime`);
    if(!d||!d.data||d.data.length===0){el.innerHTML='<p style="color:#64748b">無數據</p>';return}
    let html='<table><thead><tr><th>標的</th><th>名稱</th><th>價格</th><th>漲跌幅</th><th>24h最高</th><th>24h最低</th></tr></thead><tbody>';
    d.data.forEach(r=>{
        const pct=parseFloat(r.change_pct||0);
        const cls=pct>=0?'color:#22c55e':'color:#ef4444';
        html+=`<tr><td>${r.symbol}</td><td>${r.name||''}</td><td>${r.price}</td><td style="${cls}">${pct.toFixed(2)}%</td><td>${r.high||'-'}</td><td>${r.low||'-'}</td></tr>`;
    });
    html+='</tbody></table>';
    el.innerHTML=html;
}
// Tab 切換時載入市場
const _origTabHandler=document.getElementById('mainNav').onclick;

// === 圖表工具 ===
const COLORS=['#38bdf8','#22c55e','#f59e0b','#ef4444','#a78bfa','#ec4899','#06b6d4','#84cc16'];
function drawLineChart(canvasId,series){
    const canvas=document.getElementById(canvasId);if(!canvas)return;
    const old=Chart.getChart(canvas);if(old)old.destroy();
    const maxLen=Math.max(...series.map(s=>s.data.length));
    const labels=Array.from({length:maxLen},(_,j)=>{const d=series[0].dates;if(d&&j<d.length)return d[j].substring(5);return j});
    const datasets=series.map((s,i)=>({label:s.label,data:s.data,borderColor:COLORS[i%COLORS.length],backgroundColor:'transparent',borderWidth:1.5,pointRadius:0,tension:.1}));
    new Chart(canvas.getContext('2d'),{type:'line',data:{labels,datasets},options:{responsive:true,maintainAspectRatio:false,
        plugins:{legend:{labels:{color:'#94a3b8',font:{size:10}}},tooltip:{mode:'index',intersect:false,backgroundColor:'#1e293b',borderColor:'#334155',borderWidth:1,titleColor:'#f8fafc',bodyColor:'#e2e8f0'}},
        scales:{x:{ticks:{color:'#64748b',font:{size:9},maxTicksLimit:10},grid:{color:'#1e293b'}},y:{ticks:{color:'#64748b',font:{size:9}},grid:{color:'#1e293b'}}},
        interaction:{mode:'nearest',axis:'x',intersect:false}}});
}

function drawBarChart(canvasId,data,labels,label){
    const canvas=document.getElementById(canvasId);if(!canvas)return;
    const old=Chart.getChart(canvas);if(old)old.destroy();
    const bgColors=data.map(v=>v>=0?'rgba(34,197,94,0.6)':'rgba(239,68,68,0.6)');
    const bdColors=data.map(v=>v>=0?'#22c55e':'#ef4444');
    new Chart(canvas.getContext('2d'),{type:'bar',data:{labels,datasets:[{label,data,borderColor:bdColors,backgroundColor:bgColors,borderWidth:1}]},options:{responsive:true,maintainAspectRatio:false,
        plugins:{legend:{labels:{color:'#94a3b8',font:{size:10}}},tooltip:{backgroundColor:'#1e293b',borderColor:'#334155',borderWidth:1,titleColor:'#f8fafc',bodyColor:'#e2e8f0'}},
        scales:{x:{ticks:{color:'#64748b',font:{size:9}},grid:{color:'#1e293b'}},y:{ticks:{color:'#64748b',font:{size:9}},grid:{color:'#1e293b'}}}}});
}

function drawKlineChart(canvasId,kline,signals,title){
    const canvas=document.getElementById(canvasId);if(!canvas||!kline||!kline.length)return;
    const old=Chart.getChart(canvas);if(old)old.destroy();
    const data=kline.length>200?kline.slice(-200):kline;
    const labels=data.map(d=>d.date.substring(5));
    const closes=data.map(d=>d.close);
    const volumes=data.map(d=>d.volume||0);
    const highs=data.map(d=>d.high);
    const lows=data.map(d=>d.low);
    const opens=data.map(d=>d.open);

    // 計算均線
    function ma(arr,period){
        return arr.map((v,i)=>{
            if(i<period-1)return null;
            let sum=0;for(let j=i-period+1;j<=i;j++)sum+=arr[j];
            return sum/period;
        });
    }
    const ma5=ma(closes,5),ma10=ma(closes,10),ma20=ma(closes,20),ma60=ma(closes,60);

    // 買賣信號點
    const buyPoints=[],sellPoints=[];
    const dateIndex={};data.forEach((d,i)=>dateIndex[d.date]=i);
    (signals||[]).forEach(s=>{
        const idx=dateIndex[s.date];
        if(idx!=null){
            if(s.type==='buy')buyPoints.push({x:idx,y:s.price});
            else sellPoints.push({x:idx,y:s.price});
        }
    });

    // 成交量顏色（漲紅跌綠）
    const volColors=data.map((d,i)=>i===0?'rgba(34,197,94,0.5)':(d.close>=data[i-1].close?'rgba(239,68,68,0.5)':'rgba(34,197,94,0.5)'));

    // K線顏色（漲紅跌綠）
    const klineColors=data.map((d,i)=>i===0?'#38bdf8':(d.close>=opens[i]?'#ef4444':'#22c55e'));

    // 畫收盤價折線（替代純 K 線，更清晰）
    const datasets=[
        {label:'收盤價',data:closes,borderColor:'#38bdf8',backgroundColor:'transparent',borderWidth:2,pointRadius:0,tension:.1,order:1},
        {label:'MA5',data:ma5,borderColor:'#f59e0b',backgroundColor:'transparent',borderWidth:1,pointRadius:0,tension:.1,borderDash:[],order:2},
        {label:'MA10',data:ma10,borderColor:'#a78bfa',backgroundColor:'transparent',borderWidth:1,pointRadius:0,tension:.1,order:2},
        {label:'MA20',data:ma20,borderColor:'#22c55e',backgroundColor:'transparent',borderWidth:1,pointRadius:0,tension:.1,order:2},
        {label:'MA60',data:ma60,borderColor:'#ef4444',backgroundColor:'transparent',borderWidth:1,pointRadius:0,tension:.1,borderDash:[4,2],order:2},
        {label:'買入',data:buyPoints,borderColor:'transparent',backgroundColor:'#22c55e',pointRadius:7,pointStyle:'triangle',showLine:false,order:0},
        {label:'賣出',data:sellPoints,borderColor:'transparent',backgroundColor:'#ef4444',pointRadius:7,pointStyle:'rectRot',showLine:false,order:0},
    ];

    new Chart(canvas.getContext('2d'),{type:'line',data:{labels,datasets},options:{responsive:true,maintainAspectRatio:false,
        plugins:{legend:{labels:{color:'#94a3b8',font:{size:10}}},tooltip:{mode:'index',intersect:false,backgroundColor:'#1e293b',borderColor:'#334155',borderWidth:1,titleColor:'#f8fafc',bodyColor:'#e2e8f0',
            callbacks:{title:function(ctx){const i=ctx[0].dataIndex;if(i>=0&&i<data.length){const d=data[i];return `${d.date}\n開 ${d.open} 高 ${d.high} 低 ${d.low} 收 ${d.close}\n量 ${(d.volume||0).toLocaleString()}`}return ctx[0].label}}}},
            title:{display:!!title,text:title,color:'#f8fafc',font:{size:13}}},
        scales:{x:{ticks:{color:'#64748b',font:{size:9},maxTicksLimit:12},grid:{color:'#1e293b'}},y:{position:'left',ticks:{color:'#64748b',font:{size:9}},grid:{color:'#1e293b'}},
            vol:{position:'right',grid:{display:false},ticks:{display:false},min:0,max:Math.max(...volumes)*4,display:false}},
        interaction:{mode:'nearest',axis:'x',intersect:false}}});

    // 成交量柱狀圖（疊加在底部）
    const volCanvas=document.createElement('canvas');
    volCanvas.id=canvasId+'_vol';
    volCanvas.style.cssText='position:absolute;bottom:0;left:0;width:100%;height:25%;pointer-events:none;opacity:0.4';
    canvas.parentElement.style.position='relative';
    if(canvas.parentElement.querySelector('#'+canvasId+'_vol'))canvas.parentElement.querySelector('#'+canvasId+'_vol').remove();
    canvas.parentElement.appendChild(volCanvas);
    new Chart(volCanvas.getContext('2d'),{type:'bar',data:{labels,datasets:[{data:volumes,backgroundColor:volColors,borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,animation:false,
        plugins:{legend:{display:false},tooltip:{enabled:false}},scales:{x:{display:false},y:{display:false}},events:[]}});
}

// === 熱力圖 ===
const HM_PARAMS={
    dual_ma:{fast:'int',slow:'int'},
    macd:{fast:'int',slow:'int',signal:'int'},
    bollinger:{period:'int',devfactor:'float'},
    kdj:{period:'int',overbought:'int',oversold:'int'},
    rsi:{period:'int',overbought:'int',oversold:'int'},
    grid:{grid_pct:'float',position_pct:'float'},
    turtle:{entry_period:'int',exit_period:'int',atr_period:'int',risk_pct:'float'},
    dual_thrust:{period:'int',k_up:'float',k_down:'float'},
    momentum:{lookback:'int',hold_period:'int'},
    mean_reversion:{period:'int',entry_zscore:'float',exit_zscore:'float'},
    volume_price:{price_ma:'int',volume_ma:'int',volume_ratio:'float'},
    breakout:{period:'int',atr_period:'int',atr_multiplier:'float'},
    composite:{min_agreement:'int',ma_fast:'int',ma_slow:'int',rsi_period:'int',rsi_overbought:'int',rsi_oversold:'int',boll_period:'int',boll_dev:'float'}
};
function updateHeatmapParams(){
    const strat=document.getElementById('hmStrategy').value;
    const params=HM_PARAMS[strat]||{};
    const keys=Object.keys(params);
    ['hmParamX','hmParamY'].forEach(id=>{
        const sel=document.getElementById(id);
        sel.innerHTML=keys.map((k,i)=>`<option value="${k}"${i===0&&id==='hmParamX'||i===1&&id==='hmParamY'?' selected':''}>${k}</option>`).join('');
    });
}
document.getElementById('hmStrategy')?.addEventListener('change',updateHeatmapParams);
updateHeatmapParams();

async function runHeatmap(){
    const code=document.getElementById('hmCode').value;
    const strategy=document.getElementById('hmStrategy').value;
    const px=document.getElementById('hmParamX').value;
    const py=document.getElementById('hmParamY').value;
    const grid=parseInt(document.getElementById('hmGrid').value)||8;
    const btn=document.getElementById('hmBtn');btn.disabled=true;btn.innerHTML='<span class="ld"></span> 計算中...';
    const d=await api(`/api/heatmap?code=${code}&strategy=${strategy}&param_x=${px}&param_y=${py}&grid_size=${grid}`,{method:'POST'});
    btn.disabled=false;btn.textContent='生成熱力圖';
    if(!d||!d.success)return toast('失敗: '+(d.detail||''));
    const r=d.result;
    document.getElementById('hmStats').innerHTML=`
        <div class="c"><h3>最佳參數</h3><div class="v gn">${px}=${r.best_params[px]}, ${py}=${r.best_params[py]}</div></div>
        <div class="c"><h3>最佳分數</h3><div class="v bl">${fn(r.best_score,4)}</div></div>
        <div class="c"><h3>網格</h3><div class="v">${r.x_values.length}×${r.y_values.length}</div></div>`;
    drawHeatmap('hmCanvas',r);
    document.getElementById('hmResult').classList.remove('h');
}

function drawHeatmap(canvasId,r){
    const canvas=document.getElementById(canvasId);if(!canvas)return;
    const ctx=canvas.getContext('2d');
    const xVals=r.x_values,yVals=r.y_values,matrix=r.matrix;
    const cols=xVals.length,rows=yVals.length;
    const cellW=Math.max(50,Math.min(80,560/cols));
    const cellH=Math.max(40,Math.min(60,400/rows));
    const padL=60,padT=30,padR=20,padB=40;
    canvas.width=padL+cols*cellW+padR;
    canvas.height=padT+rows*cellH+padB;
    ctx.clearRect(0,0,canvas.width,canvas.height);
    // 找 min/max
    let mn=Infinity,mx=-Infinity;
    matrix.forEach(row=>row.forEach(v=>{if(v>-9999){mn=Math.min(mn,v);mx=Math.max(mx,v)}}));
    if(mn===Infinity){mn=0;mx=1;}
    const range=mx-mn||1;
    // 畫格子
    for(let y=0;y<rows;y++){
        for(let x=0;x<cols;x++){
            const v=matrix[y][x];
            const t=v<=-9999?0:(v-mn)/range;
            const r2=Math.round(239*t+15*(1-t));
            const g2=Math.round(68*t+23*(1-t));
            const b2=Math.round(68*t+42*(1-t));
            ctx.fillStyle=`rgb(${r2},${g2},${b2})`;
            if(v<=-9999)ctx.fillStyle='#1e293b';
            ctx.fillRect(padL+x*cellW,padT+y*cellH,cellW-1,cellH-1);
            ctx.fillStyle='#e2e8f0';
            ctx.font='10px sans-serif';
            ctx.textAlign='center';
            ctx.textBaseline='middle';
            if(v>-9999)ctx.fillText(v.toFixed(2),padL+x*cellW+cellW/2,padT+y*cellH+cellH/2);
        }
    }
    // X 標籤
    ctx.fillStyle='#94a3b8';ctx.font='10px sans-serif';ctx.textAlign='center';
    xVals.forEach((v,i)=>ctx.fillText(v,padL+i*cellW+cellW/2,padT+rows*cellH+15));
    ctx.fillText(r.param_x,padL+cols*cellW/2,padT+rows*cellH+32);
    // Y 標籤
    ctx.textAlign='right';
    yVals.forEach((v,i)=>ctx.fillText(v,padL-8,padT+i*cellH+cellH/2));
    ctx.save();ctx.translate(12,padT+rows*cellH/2);ctx.rotate(-Math.PI/2);ctx.textAlign='center';ctx.fillText(r.param_y,0,0);ctx.restore();
    // 高亮最佳
    if(r.best_params){
        const bx=xVals.indexOf(r.best_params[r.param_x]);
        const by=yVals.indexOf(r.best_params[r.param_y]);
        if(bx>=0&&by>=0){
            ctx.strokeStyle='#22c55e';ctx.lineWidth=3;
            ctx.strokeRect(padL+bx*cellW,padT+by*cellH,cellW-1,cellH-1);
        }
    }
}

// === 篩選器 ===
async function runScreener(){
    const filters={};
    if(document.getElementById('scrMA').checked)filters.ma_bullish=true;
    if(document.getElementById('scrVol').checked)filters.volume_surge={days:5,ratio:parseFloat(document.getElementById('scrVolRatio').value)||2.0};
    if(document.getElementById('scrHigh').checked)filters.near_52w_high={pct:parseFloat(document.getElementById('scrHighPct').value)||5};
    if(document.getElementById('scrChange').checked)filters.price_change_ndays={days:parseInt(document.getElementById('scrChangeDays').value)||5,min_pct:parseFloat(document.getElementById('scrChangePct').value)||5};
    if(document.getElementById('scrAboveMA').checked)filters.above_ma={period:parseInt(document.getElementById('scrMAPeriod').value)||20};
    if(Object.keys(filters).length===0)return toast('請至少選擇一個篩選條件');
    const btn=document.getElementById('scrBtn');btn.disabled=true;btn.innerHTML='<span class="ld"></span> 篩選中...';
    const d=await api('/api/screener/screen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filters})});
    btn.disabled=false;btn.textContent='開始篩選';
    if(!d)return toast('失敗');
    const stocks=d.results||[];
    document.getElementById('scrCount').textContent=stocks.length+' 只';
    document.getElementById('scrTable').innerHTML=stocks.map(s=>`<tr>
        <td>${s.code}</td><td>${s.name||sn(s.code)||'-'}</td>
        <td style="font-size:10px">${(s.matched||[]).join(', ')}</td>
        <td><button class="btn s" style="padding:3px 8px;font-size:10px" onclick="addToWatchlist('${s.code}')">加入監控</button></td>
    </tr>`).join('')||'<tr><td colspan="4" style="color:#64748b;text-align:center">無匹配結果</td></tr>';
    document.getElementById('scrResult').classList.remove('h');
    toast(`篩選完成: ${stocks.length} 只匹配`);
}

async function addToWatchlist(code){
    const d=await api(`/api/watchlist/add?code=${code}`,{method:'POST'});
    if(d&&d.success)toast(d.message);
    else toast('添加失敗');
}

// === 股票名稱 ===
let STOCK_NAMES={};
async function loadStockNames(){
    try{const d=await api('/api/stocks/names');if(d)STOCK_NAMES=d.names||{}}catch{}
}
function sn(code){return STOCK_NAMES[code]||code}
function snLabel(code){const n=STOCK_NAMES[code];return n?`${code} ${n}`:code}

// === 策略列表動態加載 ===
const STRATEGY_NAMES={};
async function loadStrategies(){
    try{
        const d=await api('/api/strategies/list');
        if(!d)return;
        const all=[...(d.builtin||[]),...(d.user||[])];
        all.forEach(s=>{STRATEGY_NAMES[s.name]=s.display_name||s.description||s.name});
        // 填充回測下拉
        fillStrategySelect('btStrategy',all,false);
        // 填充優化下拉（含"全部"）
        fillStrategySelect('optStrategy',all,true);
        // 填充 Walk-Forward 下拉
        fillStrategySelect('wfStrategy',all,false);
        // 填充熱力圖下拉
        fillStrategySelect('hmStrategy',all,false);
        // 更新 HM_PARAMS（動態添加新策略的參數）
        all.forEach(s=>{
            if(!HM_PARAMS[s.name]&&s.params&&Object.keys(s.params).length>0){
                const p={};Object.keys(s.params).forEach(k=>{p[k]='float'});
                HM_PARAMS[s.name]=p;
            }
        });
    }catch(e){console.warn('加載策略列表失敗:',e)}
}
function fillStrategySelect(id,all,includeAll){
    const sel=document.getElementById(id);if(!sel)return;
    const prev=sel.value;
    sel.innerHTML='';
    if(includeAll)sel.innerHTML='<option value="all">全部</option>';
    all.forEach(s=>{
        const opt=document.createElement('option');
        opt.value=s.name;
        opt.textContent=s.display_name||s.description||s.name;
        sel.appendChild(opt);
    });
    if(prev)sel.value=prev;
}

// === 初始化 ===
Promise.all([loadStockNames(),loadStrategies()]).then(()=>{loadDashboard();loadPresets();connectWS();});
</script>
</body></html>"""

