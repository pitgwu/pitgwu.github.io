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
  const WINDOW = 40;

  let data = [];
  let currentIndex = 0; // index = 當日交易日期所對應的 K 棒 index（full data index）

  let cash = INITIAL_CASH;
  let position = 0;
  let lots = [];          // 分批買入
  let trades = [];        // 所有交易紀錄
  let realizedList = [];  // 已實現損益（每次賣出一筆）

  let indicators = null;  // 對應 full data 的指標 arrays
  let allSignals = null;  // 對應 full data 的 signals arrays

  let signalVisible = false;
  let maVisible = false;

  // ----------------------------------------------------------
  // 1️⃣ 計算「總未實現損益」
  // ----------------------------------------------------------
  function calcUnrealTotal(currentPrice) {
    return lots.reduce((sum, lot) => sum + (currentPrice - lot.price) * lot.qty, 0);
  }

  // ----------------------------------------------------------
  // CSV 載入
  // ----------------------------------------------------------
  function loadCSV() {
    const stockList = [
      "2330","2317","6669","1475","2368","3665","2308","2345","6223","3653",
      "6274","6805","2449","2317","8210","2454","2059","3231","1303","3661",
      "6510","6139","6191","5536","3533","8358","4958","3515","2354","6515",
      "3715","3081","1560","3711","3211","5347","1319","3044","3217","5274",
      "3008","2327","2357","2439","2884","3037","3045","3583","8996","8299"
    ];

    const stock = stockList[Math.floor(Math.random() * stockList.length)];
    global.__currentStock = stock;

    // 一開始隱藏股票號碼（結束時才公布）
    if (U.el("stockName")) U.el("stockName").innerText = "";

    fetch(`data/${stock}.csv`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.text();
      })
      .then(text => {
        const lines = text.split("\n").slice(1);
        data = lines
          .filter(l => l.trim())
          .map(l => {
            const c = l.split(",");
            return {
              time: c[0],  // YYYY-MM-DD
              open: +c[1],
              high: +c[2],
              low: +c[3],
              close: +c[4],
              volume: +c[5]
            };
          });

        if (!data.length) {
          alert("CSV 空白");
          return;
        }

        // ⭐ 起始：讓畫面停在「第 WINDOW 根」或資料尾端（但視窗要可滑動推進）
        // 例如資料很長 → currentIndex = WINDOW-1（先保留前 40 根歷史）
        // 資料不足 40 根 → currentIndex = data.length-1
        currentIndex = Math.min(data.length - 1, WINDOW - 1);

        // 計算 full indicators
        indicators = Indicators.computeAll(data);

        // signals（對應 full data index）
        const ctx = Signals.buildSignalContext(data);
        allSignals = Signals.evaluateSignalsForAll(ctx);

        Chart.init();
        bindEvents();
        updateDisplays();
      })
      .catch(e => alert("CSV 載入失敗: " + e.message));
  }

  // ----------------------------------------------------------
  // 主畫面更新（視窗固定 WINDOW 根，右端 = currentIndex）
  // ----------------------------------------------------------
  function updateDisplays() {
    if (!data.length) return;

    const viewStart = Math.max(0, currentIndex - WINDOW + 1);
    const shown = data.slice(viewStart, currentIndex + 1);
    const indType = U.el("indicatorSelect").value;

    // 型態偵測用 shown（index 以 shown 內部為準）
	// -----------------------------
    // 型態偵測（W 底 / M 頭 / 三角）
    // -----------------------------
    const tline = Trend.findTrendlines(shown);
    const w = WM.isWBottom(shown);
    const m = WM.isMTop(shown);
    const tri = TRI.detectTriangle(shown);

    // 型態文字（可留也可刪）
    const parts = [];
    if (w) parts.push(`W底(頸線 ${w.neck.toFixed(2)})`);
    if (m) parts.push(`M頭(頸線 ${m.neck.toFixed(2)})`);
    if (tri) parts.push(tri.type);
    U.el("kPattern").innerText = parts.length ? `即時型態偵測：${parts.join(" / ")}` : "即時型態偵測：尚無明顯型態";

    // 多空訊號（用 full index currentIndex）
    if (signalVisible) {
      const sigArr = allSignals[currentIndex] || [];
      const txt = sigArr.map(s => `[${s.side === "bull" ? "多" : "空"}] ${s.name}`).join("、");
      U.el("signalBox").innerText = "多空訊號：" + (txt || "無");
    } else {
      U.el("signalBox").innerText = "多空訊號：OFF";
    }

    // 更新 K 線（⭐ 用 shown 畫圖；用 offset 對齊 full indicators）
    Chart.update(shown, indicators, {
      offset: viewStart,               // ⭐ 關鍵：shown[0] 在 full data 的起點
      visibleBars: WINDOW,
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

  // ----------------------------------------------------------
  // 2️⃣ 資產統計（含已實現 / 未實現）
  // ----------------------------------------------------------
  function updateStats() {
    if (!data.length) return;

    const price = data[currentIndex].close;
    const holdingValue = position * price;

    const unreal = calcUnrealTotal(price);
    const realized = realizedList.reduce((s, r) => s + (r.realized || 0), 0);

    const total = cash + holdingValue;
    const roi = (((total / INITIAL_CASH) - 1) * 100).toFixed(2);

    U.el("cash").innerText = U.formatNumber(cash);
    U.el("position").innerText = position;
    U.el("holdingValue").innerText = U.formatNumber(holdingValue);
    U.el("totalAsset").innerText = U.formatNumber(total);
    U.el("roi").innerText = roi;

    U.el("realizedTotalBox").innerText = U.formatNumber(realized) + " 元";
    U.el("unrealizedTotalBox").innerText = U.formatNumber(unreal) + " 元";
  }

  // ----------------------------------------------------------
  // 交易紀錄（永遠顯示當日 date）
  // ----------------------------------------------------------
  function updateTradeLog() {
    const ul = U.el("tradeLog");
    ul.innerHTML = "";

    trades.forEach(t => {
      ul.innerHTML += `<li>${t.date} ${
        t.type === "buy" ? "買" :
        t.type === "sell" ? "賣" : "不動作"
      } ${t.qty || ""} ${t.price != null ? "@ " + t.price : ""}</li>`;
    });

    ul.scrollTop = ul.scrollHeight;
  }

  // ----------------------------------------------------------
  // 持倉明細（分批）
  // ----------------------------------------------------------
  function updateHoldings() {
    const ul = U.el("holdings");
    ul.innerHTML = "";

    if (!lots.length) {
      ul.innerHTML = "<li>無持倉</li>";
      return;
    }

    const price = data[currentIndex].close;

    lots.forEach(l => {
      const u = (price - l.price) * l.qty;
      ul.innerHTML += `<li>${l.date} ${l.qty} 股 @ ${l.price} → 未實現 ${U.formatNumber(u)} 元</li>`;
    });

    ul.scrollTop = ul.scrollHeight;
  }

  // ----------------------------------------------------------
  // 當天交易 → 隔天跳下一根 K
  // ----------------------------------------------------------
  function finishToday() {
    if (currentIndex < data.length - 1) {
      currentIndex++;
      updateDisplays();
    } else {
      gameEnd();
    }
  }

  function doBuy() {
    if (!data.length) return;

    const qty = +U.el("shareInput").value;
    if (!qty || qty <= 0) return;

    const day = data[currentIndex];           // ⭐ 當日 K 棒
    const price = day.close;
    const cost = qty * price;

    if (cost > cash) return alert("現金不足");

    // 記錄當日
    lots.push({ qty, price, date: day.time });
    cash -= cost;
    position += qty;
    trades.push({ type: "buy", qty, price, date: day.time });

    // 跳隔天
    finishToday();
  }

  function doSell() {
    if (!data.length) return;

    const qty = +U.el("shareInput").value;
    if (!qty || qty <= 0) return;

    if (qty > position) return alert("持股不足");

    const day = data[currentIndex];          // ⭐ 當日 K 棒
    const price = day.close;

    let remain = qty;
    let realized = 0;

    while (remain > 0 && lots.length) {
      const lot = lots[0];
      const use = Math.min(lot.qty, remain);

      realized += (price - lot.price) * use;
      lot.qty -= use;
      remain -= use;

      if (lot.qty === 0) lots.shift();
    }

    cash += qty * price;
    position -= qty;

    realizedList.push({ qty, realized, date: day.time });
    trades.push({ type: "sell", qty, price, date: day.time });

    finishToday();
  }

  function doHold() {
    if (!data.length) return;

    const day = data[currentIndex]; // ⭐ 當日 K 棒
    trades.push({ type: "hold", date: day.time });

    finishToday();
  }

  // ----------------------------------------------------------
  // 3️⃣ 遊戲結束：專業總結 + 公佈股票號碼
  // ----------------------------------------------------------
  function gameEnd() {
    if (!data.length) return;

    // 先停在最後一天顯示
    currentIndex = data.length - 1;
    updateDisplays();

    const finalPrice = data[data.length - 1].close;
    const holdingValue = position * finalPrice;
    const totalValue = cash + holdingValue;
    const roi = ((totalValue / INITIAL_CASH - 1) * 100).toFixed(2);

    const realizedTotal = realizedList.reduce((sum, r) => sum + (r.realized || 0), 0);
    const unrealTotal = calcUnrealTotal(finalPrice);

    const stock = global.__currentStock;

    const good = [];
    const bad = [];
    const suggest = [];

    if (roi >= 12)
      good.push("整體報酬率顯著優於大盤，策略具備明確正期望值");
    else if (roi >= 0)
      good.push("能有效控制回撤，整體資金曲線維持相對穩定");
    else
      bad.push("回撤過深，進出場規則與停損機制需要重新檢視");

    if (realizedTotal > 0)
      good.push("已實現損益為正，出場節奏與獲利了結策略相對合理");
    else
      bad.push("部分虧損單未及時處理，拖累整體績效表現");

    const tradeCount = trades.filter(t => t.type !== "hold").length;

    if (tradeCount > 20)
      bad.push("交易頻率偏高，可能過度反應短線雜訊");
    if (tradeCount < 4)
      bad.push("進場次數偏少，可能錯過多次關鍵波段行情");

    if (lots.length > 0)
      bad.push("結束時仍有未平倉部位，存在『凹單』或持股過久的風險");

    if (realizedTotal <= 0)
      suggest.push("建立明確停損機制（例如固定百分比或 ATR ），避免單筆虧損過度放大");
    if (tradeCount > 18)
      suggest.push("適度降低交易次數，聚焦於高勝率、高盈虧比的進出場機會");
    if (lots.length > 0)
      suggest.push("避免習慣性凹單，可規劃分批出場與移動停利等策略");

    if (!suggest.length)
      suggest.push("策略架構大致健康，可進一步優化加碼規則與獲利目標設定");

    const summary =
      `🎉【模擬交易結束】\n` +
      `交易標的：${stock}\n\n` +
      `最終總資產：${U.formatNumber(totalValue)} 元\n` +
      `報酬率：${roi}%\n` +
      `已實現總損益：${U.formatNumber(realizedTotal)} 元\n` +
      `未實現總損益：${U.formatNumber(unrealTotal)} 元\n\n` +
      `【策略優點】\n${good.join("；") || "暫無明顯優勢"}\n\n` +
      `【策略缺點】\n${bad.join("；") || "暫無重大缺失"}\n\n` +
      `【專業改善建議】\n${suggest.join("；")}`;

    U.el("feedback").innerText = summary;

    // ⭐ 結束才公布股票號碼
    if (U.el("stockName")) {
      U.el("stockName").innerText = `模擬結束，本次個股：${stock}`;
    }

    alert(`模擬結束（${stock}）\n報酬率：${roi}%`);
  }

  // ----------------------------------------------------------
  // UI 綁定
  // ----------------------------------------------------------
  function bindEvents() {
    U.el("buy").onclick = doBuy;
    U.el("sell").onclick = doSell;
    U.el("hold").onclick = doHold;

    // 手動切換天數：只移動 currentIndex，不改交易紀錄
    U.el("nextDay").onclick = () => {
      if (currentIndex < data.length - 1) currentIndex++;
      else return gameEnd();
      updateDisplays();
    };
    U.el("prevDay").onclick = () => {
      if (currentIndex > 0) currentIndex--;
      updateDisplays();
    };

    U.el("toggleMA").onclick = () => {
      maVisible = !maVisible;
      U.el("toggleMA").innerText = maVisible ? "均線：ON" : "均線：OFF";
      U.el("maLegend").style.display = maVisible ? "block" : "none";
      updateDisplays();
    };

    U.el("toggleSignal").onclick = () => {
      signalVisible = !signalVisible;
      U.el("toggleSignal").innerText = signalVisible ? "多空訊號：ON" : "多空訊號：OFF";
      updateDisplays();
    };

    U.el("indicatorSelect").onchange = updateDisplays;
  }

  loadCSV();
})(window);
