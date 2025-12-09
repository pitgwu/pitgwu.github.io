// js/main.js
(function (global) {
  "use strict";

  const U = global.Util;
  const Chart = global.ChartManager;
  const Indicators = global.Indicators;
  const Signals = global.SignalEngine;
  const Trend = global.Trendlines;
  const WM = global.PatternWM;
  const TRI = global.PatternTriangle;

  const INITIAL_CASH = 5000000;

  let data = [];
  let currentIndex = 22;

  let cash = INITIAL_CASH;
  let position = 0;
  let lots = [];
  let trades = [];
  let realizedList = [];

  let indicators = null;
  let allSignals = null;

  // MA / 訊號預設 OFF
  let signalVisible = false;
  let maVisible = false;

  // -------------------------------------------------------------------
  // CSV 載入
  // -------------------------------------------------------------------
  function loadCSV() {

    const stockList = [
      "2330","2317","6669","1475","2368","3665","2308","2345","6223","3653",
      "6274","6805","2449","2317","8210","2454","2059","3231","1303","3661",
      "6510","6139","6191","5536","3533","8358","4958","3515","2354","6515",
      "3715","3081","1560","3711","3211","5347","1319","3044","3217","5274",
      "3008","2327","2357","2439","2884","3037","3045","3583","8996","8299"
    ];

    const stock = stockList[Math.floor(Math.random() * stockList.length)];
    global.__currentStock = stock;  // 用於遊戲結束顯示

    fetch(`data/${stock}.csv`)
      .then(r => r.text())
      .then(text => {

        const lines = text.split("\n").slice(1);
        data = lines
          .filter(l => l.trim() !== "")
          .map(l => {
            const c = l.split(",");
            return {
              time: c[0],
              open: +c[1],
              high: +c[2],
              low: +c[3],
              close: +c[4],
              volume: +c[5],
            };
          });

        indicators = Indicators.computeAll(data);

        const ctx = Signals.buildSignalContext(data);
        allSignals = Signals.evaluateSignalsForAll(ctx);

        Chart.init();
        bindEvents();
        updateDisplays();
      })
      .catch(e => {
        alert("讀取 CSV 失敗：" + e.message);
        console.error(e);
      });
  }

  // -------------------------------------------------------------------
  // 主畫面更新
  // -------------------------------------------------------------------
  function updateDisplays() {
    const shown = data.slice(0, currentIndex);
    const indType = U.el("indicatorSelect").value;

    // -----------------------------
    // 型態偵測（W 底 / 三角 / M 頭）
    // -----------------------------
    const tline = Trend.findTrendlines(shown); // 趨勢線
    const w = WM.isWBottom(shown);
    const m = WM.isMTop(shown);
    const tri = TRI.detectTriangle(shown);

    let pat = "";
    if (w) pat += `W底 (頸線 ${w.neck.toFixed(2)}) `;
    if (m) pat += `M頭 (頸線 ${m.neck.toFixed(2)}) `;
    if (tri) pat += `${tri.type} `;

    U.el("kPattern").innerText = pat || "（無明顯型態）";

    // -----------------------------
    // 多空訊號
    // -----------------------------
    if (signalVisible) {
      const sig = allSignals[currentIndex - 1] || [];
      const txt = sig.map(s => `[${s.side === "bull" ? "多" : "空"}] ${s.name}`).join("、");
      U.el("signalBox").innerText = "多空訊號：" + (txt || "無");
    } else {
      U.el("signalBox").innerText = "多空訊號：OFF";
    }

    // -----------------------------
    // 更新 K 線圖（呼叫 chart.js）
    // -----------------------------
    Chart.update(shown, indicators, {
      showMA: maVisible,
      showBB: indType === "bb",
      indicatorType: indType,
      trendlines: maVisible ? tline : null,
      wPattern: maVisible ? w : null,
      triangle: maVisible ? tri : null
    });

    updateStats();
    updateTradeLog();
    updateHoldings();
  }

// ---------------------------------------------------------
// 資產統計（含已實現 & 未實現）
// ---------------------------------------------------------
function updateStats() {
  const price = data[currentIndex - 1].close;

  // 未實現總損益（所有 lots）
  const unrealTotal = lots.reduce((sum, lot) => {
    return sum + (price - lot.price) * lot.qty;
  }, 0);

  // 已實現損益
  const realizedTotal = realizedList.reduce(
    (sum, r) => sum + (r.realized || 0),
    0
  );

  const holdingValue = position * price;
  const total = cash + holdingValue;
  const roi = ((total / INITIAL_CASH - 1) * 100).toFixed(2);

  U.el("cash").innerText = U.formatNumber(cash);
  U.el("position").innerText = position;
  U.el("holdingValue").innerText = U.formatNumber(holdingValue);
  U.el("totalAsset").innerText = U.formatNumber(total);
  U.el("roi").innerText = roi;

  // ★ 新增：更新未實現 & 已實現總損益 UI
  U.el("realizedTotalBox").innerText =
    U.formatNumber(realizedTotal) + " 元";

  U.el("unrealizedTotalBox").innerText =
    U.formatNumber(unrealTotal) + " 元";
}


// ---------------------------------------------------------
// 交易紀錄（捲軸、隨時間自動下移）
// ---------------------------------------------------------
function updateTradeLog() {
  const ul = U.el("tradeLog");
  ul.innerHTML = "";

  trades.forEach(t => {
    const li = document.createElement("li");
    if (t.type === "buy")
      li.textContent = `${t.date} 買 ${t.qty} @ ${t.price}`;
    else if (t.type === "sell")
      li.textContent = `${t.date} 賣 ${t.qty} @ ${t.price}`;
    else
      li.textContent = `${t.date} 不動作`;
    ul.appendChild(li);
  });

  // 自動捲到最新一筆
  ul.scrollTop = ul.scrollHeight;
}


// ---------------------------------------------------------
// 持倉明細（未實現損益，固定捲軸）
// ---------------------------------------------------------
function updateHoldings() {
  const ul = U.el("holdings");
  ul.innerHTML = "";

  if (!lots.length) {
    ul.innerHTML = "<li>無持倉</li>";
    return;
  }

  const price = data[currentIndex - 1].close;

  lots.forEach(l => {
    const unreal = (price - l.price) * l.qty;
    const li = document.createElement("li");
    li.textContent =
      `${l.date} ${l.qty} @ ${l.price} → 未實現 ${U.formatNumber(unreal)} 元`;
    ul.appendChild(li);
  });

  ul.scrollTop = ul.scrollHeight;
}


// ---------------------------------------------------------
// 買進
// ---------------------------------------------------------
function doBuy() {
  const qty = parseInt(U.el("shareInput").value, 10);
  if (!qty) return;

  const price = data[currentIndex - 1].close;
  const cost = qty * price;

  if (cost > cash) return alert("現金不足");

  cash -= cost;
  position += qty;

  lots.push({ qty, price, date: data[currentIndex - 1].time });
  trades.push({ type: "buy", qty, price, date: data[currentIndex - 1].time });

  nextDay();
}


// ---------------------------------------------------------
// 賣出（FIFO 出場）
// ---------------------------------------------------------
function doSell() {
  const qty = parseInt(U.el("shareInput").value, 10);
  if (!qty) return;
  if (qty > position) return alert("持股不足");

  const price = data[currentIndex - 1].close;

  let remain = qty;
  let realized = 0;

  // FIFO 實現損益
  while (remain > 0 && lots.length) {
    const lot = lots[0];
    const use = Math.min(remain, lot.qty);

    realized += (price - lot.price) * use;

    lot.qty -= use;
    remain -= use;

    if (lot.qty === 0) lots.shift();
  }

  cash += qty * price;
  position -= qty;

  realizedList.push({
    qty,
    realized,
    date: data[currentIndex - 1].time
  });

  trades.push({
    type: "sell",
    qty,
    price,
    date: data[currentIndex - 1].time
  });

  nextDay();
}


// ---------------------------------------------------------
// 不動作（進入下一天）
// ---------------------------------------------------------
function doHold() {
  trades.push({
    type: "hold",
    date: data[currentIndex - 1].time
  });
  nextDay();
}


// ---------------------------------------------------------
// 前一天 / 下一天（動畫右移）
// ---------------------------------------------------------
function nextDay() {
  if (currentIndex < data.length - 1) {
    currentIndex++;
    updateDisplays();
  } else {
    checkGameEnd();
  }
}

function prevDay() {
  if (currentIndex > 1) {
    currentIndex--;
    updateDisplays();
  }
}


// ---------------------------------------------------------
// 🎯 遊戲結束：專業總結 + 個股顯示 + 建議
// ---------------------------------------------------------
function checkGameEnd() {
  if (currentIndex < data.length - 1) return;

  const finalPrice = data[data.length - 1].close;
  const holdingValue = position * finalPrice;
  const totalValue = cash + holdingValue;

  const roi = ((totalValue / INITIAL_CASH - 1) * 100).toFixed(2);

  const realizedTotal = realizedList.reduce(
    (sum, r) => sum + (r.realized || 0),
    0
  );

  const stock = global.__currentStock;

  // 專業評估
  const good = [];
  const bad = [];
  const suggest = [];

  if (roi >= 12)
    good.push("報酬率顯著優於市場基準，策略具備明確正期望值");
  else if (roi >= 0)
    good.push("具備穩定度，控管回撤尚稱良好");
  else
    bad.push("策略回撤過深，進場基準與停損機制需重新調整");

  if (realizedTotal > 0)
    good.push("已實現損益為正，顯示出場節奏良好");
  else
    bad.push("虧損單未能有效控制，停損應更加明確果斷");

  const tradeCount = trades.filter(t => t.type !== "hold").length;

  if (tradeCount > 20)
    bad.push("過度頻繁交易，容易因噪音造成錯誤判斷");
  if (tradeCount < 4)
    bad.push("進場過少，可能錯失多次重要行情");

  if (lots.length > 0)
    bad.push("存在未實現虧損持續累積的情況（凹單），需檢討持倉策略");

  if (realizedTotal <= 0)
    suggest.push("採用紀律性停損，例如 ATR 或固定百分比停損");
  if (tradeCount > 18)
    suggest.push("降低交易頻率，聚焦於高勝率、高報酬比的進出場機會");
  if (lots.length > 0)
    suggest.push("避免凹單，可採分批出場、移動停利等控管方法");

  if (suggest.length === 0)
    suggest.push("策略整體健全，可進一步優化獲利了結點與風險承擔模型");

  // 輸出文字
  const summary =
    `🎉【模擬交易結束】\n` +
    `交易標的：${stock}\n\n` +
    `最終總資產：${U.formatNumber(totalValue)} 元\n` +
    `報酬率：${roi}%\n` +
    `已實現損益：${U.formatNumber(realizedTotal)} 元\n` +
    `未實現損益：${U.formatNumber(holdingValue)} 元\n\n` +
    `【策略優點】\n${good.join("；") || "無明顯優勢"}\n\n` +
    `【策略缺點】\n${bad.join("；") || "無重大缺失"}\n\n` +
    `【專業改善建議】\n${suggest.join("；")}`;

  U.el("feedback").innerText = summary;

  alert(`模擬結束（${stock}）\n報酬率：${roi}%`);
}


// ---------------------------------------------------------
// 綁定 UI 控制
// ---------------------------------------------------------
function bindEvents() {
  U.el("nextDay").onclick = nextDay;
  U.el("prevDay").onclick = prevDay;
  U.el("buy").onclick = doBuy;
  U.el("sell").onclick = doSell;
  U.el("hold").onclick = doHold;

  // 多空訊號 ON/OFF（預設 OFF）
  U.el("toggleSignal").onclick = () => {
    signalVisible = !signalVisible;
    U.el("toggleSignal").innerText =
      signalVisible ? "多空訊號：ON" : "多空訊號：OFF";
    updateDisplays();
  };

  // MA ON/OFF（預設 OFF）
  U.el("toggleMA").onclick = () => {
    maVisible = !maVisible;
    U.el("toggleMA").innerText =
      maVisible ? "均線：ON" : "均線：OFF";
    U.el("maLegend").style.display = maVisible ? "block" : "none";
    updateDisplays();
  };

  U.el("indicatorSelect").onchange = updateDisplays;
}


// ---------------------------------------------------------
loadCSV();

})(window);
