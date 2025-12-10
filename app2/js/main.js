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
  let currentIndex = 0;

  let cash = INITIAL_CASH;
  let position = 0;
  let lots = [];
  let trades = [];
  let realizedList = [];

  let indicators = null;
  let allSignals = null;

  let signalVisible = false;
  let maVisible = false;

  // ----------------------------------------------------
  // 計算未實現損益
  // ----------------------------------------------------
  function calcUnrealTotal(price) {
    return lots.reduce((sum, lot) => {
      return sum + (price - lot.price) * lot.qty;
    }, 0);
  }

  // ----------------------------------------------------
  // 載入 CSV
  // ----------------------------------------------------
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

    fetch(`data/${stock}.csv`)
      .then(r => r.text())
      .then(text => {
        const lines = text.split("\n").slice(1);

        data = lines
          .filter(l => l.trim() !== "")
          .map(l => {
            const c = l.split(",");
            return {
              time: c[0],  // YYYY-MM-DD
              open: +c[1],
              high: +c[2],
              low: +c[3],
              close: +c[4],
              volume: +c[5],
            };
          });

        if (!data.length) {
          alert("CSV 為空");
          return;
        }

        // ✔ 找到第一筆 >= 2025 的資料
        const startIdx = data.findIndex(d => d.time >= "2025-01-01");
        currentIndex = startIdx >= 0 ? startIdx : data.length - 1;

        // 顯示個股
        U.el("initialCash").innerText = INITIAL_CASH.toLocaleString();
        U.el("stockName").innerText = `目前個股：${stock}`;

        indicators = Indicators.computeAll(data);
        const ctx = Signals.buildSignalContext(data);
        allSignals = Signals.evaluateSignalsForAll(ctx);

        Chart.init();
        bindEvents();
        updateDisplays();
      })
      .catch(e => {
        alert("讀取 CSV 失敗：" + e.message);
      });
  }

  // ----------------------------------------------------
  // 主畫面更新
  // ----------------------------------------------------
  function updateDisplays() {
    if (!data.length) return;

    const indType = U.el("indicatorSelect").value;
    const shownCount = currentIndex + 1;

    // 型態偵測必須用到 "目前顯示區間"
    const partial = data.slice(0, shownCount);

    const tline = Trend.findTrendlines(partial);
    const w = WM.isWBottom(partial);
    const m = WM.isMTop(partial);
    const tri = TRI.detectTriangle(partial);

    let txt = "即時型態偵測：";
    const parts = [];
    if (w) parts.push(`W底(頸線${w.neck.toFixed(2)})`);
    if (m) parts.push(`M頭(頸線${m.neck.toFixed(2)})`);
    if (tri) parts.push(tri.type);
    U.el("kPattern").innerText =
      parts.length ? txt + parts.join(" / ") : txt + "尚無明顯型態";

    // 多空訊號
    if (signalVisible) {
      const sig = allSignals[currentIndex] || [];
      U.el("signalBox").innerText =
        "多空訊號：" +
        (sig.length ? sig.map(s => `[${s.side === "bull" ? "多" : "空"}] ${s.name}`).join("、") : "暫無");
    } else {
      U.el("signalBox").innerText = "多空訊號：OFF";
    }

    // ✔ chart 不再使用 slice（避免 index 失真）
    Chart.update(
      data,
      indicators,
      {
        showMA: maVisible,
        showBB: indType === "bb",
        indicatorType: indType,
        trendlines: maVisible ? tline : null,
        wPattern: maVisible ? w : null,
        triangle: maVisible ? tri : null
      },
      currentIndex
    );

    updateStats();
    updateTradeLog();
    updateHoldings();
  }

  // ----------------------------------------------------
  // 資產顯示
  // ----------------------------------------------------
  function updateStats() {
    const price = data[currentIndex].close;
    const holdingValue = position * price;
    const total = cash + holdingValue;
    const roi = ((total / INITIAL_CASH - 1) * 100).toFixed(2);

    const unreal = calcUnrealTotal(price);
    const realized = realizedList.reduce((s, r) => s + r.realized, 0);

    U.el("cash").innerText = U.formatNumber(cash);
    U.el("position").innerText = position;
    U.el("holdingValue").innerText = U.formatNumber(holdingValue);
    U.el("totalAsset").innerText = U.formatNumber(total);
    U.el("roi").innerText = roi;

    U.el("realizedTotalBox").innerText = U.formatNumber(realized) + " 元";
    U.el("unrealizedTotalBox").innerText = U.formatNumber(unreal) + " 元";
  }

  // ----------------------------------------------------
  // 交易紀錄
  // ----------------------------------------------------
  function updateTradeLog() {
    const ul = U.el("tradeLog");
    ul.innerHTML = "";

    trades.forEach(t => {
      const li = document.createElement("li");
      li.textContent =
        t.type === "buy"
          ? `${t.date} 買 ${t.qty} @ ${t.price}`
          : t.type === "sell"
          ? `${t.date} 賣 ${t.qty} @ ${t.price}`
          : `${t.date} 不動作`;
      ul.appendChild(li);
    });

    ul.scrollTop = ul.scrollHeight;
  }

  // ----------------------------------------------------
  // 持倉紀錄
  // ----------------------------------------------------
  function updateHoldings() {
    const ul = U.el("holdings");
    ul.innerHTML = "";

    const price = data[currentIndex].close;

    if (!lots.length) {
      ul.innerHTML = "<li>無持倉</li>";
      return;
    }

    lots.forEach(l => {
      const unreal = (price - l.price) * l.qty;
      const li = document.createElement("li");
      li.textContent =
        `${l.date} ${l.qty} 股 @ ${l.price} → 未實現 ${U.formatNumber(unreal)} 元`;
      ul.appendChild(li);
    });

    ul.scrollTop = ul.scrollHeight;
  }

  // ----------------------------------------------------
  // 買進（使用今日收盤價）
  // ----------------------------------------------------
  function doBuy() {
    const qty = parseInt(U.el("shareInput").value, 10);
    if (!qty) return;

    const price = data[currentIndex].close;
    const cost = qty * price;
    if (cost > cash) return alert("現金不足");

    cash -= cost;
    position += qty;
    lots.push({
      qty,
      price,
      date: data[currentIndex].time
    });

    trades.push({
      type: "buy",
      qty,
      price,
      date: data[currentIndex].time
    });

    updateDisplays();
  }

  // ----------------------------------------------------
  // 賣出（FIFO）
  // ----------------------------------------------------
  function doSell() {
    const qty = parseInt(U.el("shareInput").value, 10);
    if (!qty) return;
    if (qty > position) return alert("持股不足");

    const price = data[currentIndex].close;
    let remain = qty;
    let realized = 0;

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
      date: data[currentIndex].time
    });

    trades.push({
      type: "sell",
      qty,
      price,
      date: data[currentIndex].time
    });

    updateDisplays();
  }

  // ----------------------------------------------------
  // 不動作
  // ----------------------------------------------------
  function doHold() {
    trades.push({
      type: "hold",
      date: data[currentIndex].time
    });
    updateDisplays();
  }

  // ----------------------------------------------------
  // 時間軸移動
  // ----------------------------------------------------
  function nextDay() {
    if (currentIndex < data.length - 1) {
      currentIndex++;
      updateDisplays();
    } else {
      checkGameEnd();
    }
  }

  function prevDay() {
    if (currentIndex > 0) {
      currentIndex--;
      updateDisplays();
    }
  }

  // ----------------------------------------------------
  // 模擬結束
  // ----------------------------------------------------
  function checkGameEnd() {
    currentIndex = data.length - 1;
    updateDisplays();

    const price = data[currentIndex].close;
    const holdingValue = price * position;
    const total = cash + holdingValue;

    const roi = ((total / INITIAL_CASH - 1) * 100).toFixed(2);
    const realized = realizedList.reduce((s, r) => s + r.realized, 0);
    const unreal = calcUnrealTotal(price);

    const stock = global.__currentStock;

    const good = [];
    const bad = [];
    const suggest = [];

    if (roi >= 12)
      good.push("整體報酬率顯著優於大盤，策略具備明確正期望值");
    else if (roi >= 0)
      good.push("能有效控制回撤，整體資金曲線維持穩定");
    else
      bad.push("回撤過深，進出場規則與停損機制需重新檢視");

    if (realizedTotal > 0)
      good.push("已實現損益為正，出場節奏與獲利了結相對合理");
    else
      bad.push("部分虧損單未及時處理，拖累整體績效");

    const tradeCount = trades.filter(t => t.type !== "hold").length;

    if (tradeCount > 20)
      bad.push("交易頻率偏高，可能過度反應短線雜訊");
    if (tradeCount < 4)
      bad.push("進場次數偏少，可能錯過多次關鍵波段行情");

    if (lots.length > 0)
      bad.push("結束時仍有持倉，存在『凹單』或持股過久的風險");

    if (realizedTotal <= 0)
      suggest.push("建立明確停損機制（例如固定% 或 ATR），避免單筆虧損過度放大");
    if (tradeCount > 18)
      suggest.push("降低交易次數，聚焦於高勝率、高盈虧比的型態與價量結構");
    if (lots.length > 0)
      suggest.push("避免習慣性凹單，可規劃分批出場與移動停利策略");

    if (!suggest.length)
      suggest.push("策略架構大致健康，可進一步優化加碼規則與獲利目標設定");

    const summary =
      `🎉【模擬交易結束】\n` +
      `交易標的：${stock}\n\n` +
      `最終總資產：${U.formatNumber(total)} 元\n` +
      `報酬率：${roi}%\n` +
      `已實現損益：${U.formatNumber(realized)} 元\n` +
      `未實現損益：${U.formatNumber(unreal)} 元\n\n` +
      `【策略優點】\n${good.join("；") || "暫無明顯優勢"}\n\n` +
      `【策略缺點】\n${bad.join("；") || "暫無"}\n\n` +
      `【專業改善建議】\n${suggest.join("；")}`;

    U.el("feedback").innerText = summary;
    U.el("stockName").innerText = `模擬結束，本次個股：${stock}`;

    alert(`模擬結束（${stock}）\n報酬率：${roi}%`);
  }

  // ----------------------------------------------------
  // 事件綁定
  // ----------------------------------------------------
  function bindEvents() {
    U.el("nextDay").onclick = nextDay;
    U.el("prevDay").onclick = prevDay;

    U.el("buy").onclick = doBuy;
    U.el("sell").onclick = doSell;
    U.el("hold").onclick = doHold;

    U.el("toggleSignal").onclick = () => {
      signalVisible = !signalVisible;
      U.el("toggleSignal").innerText =
        signalVisible ? "多空訊號：ON" : "多空訊號：OFF";
      updateDisplays();
    };

    U.el("toggleMA").onclick = () => {
      maVisible = !maVisible;
      U.el("toggleMA").innerText =
        maVisible ? "均線：ON" : "均線：OFF";
      U.el("maLegend").style.display = maVisible ? "block" : "none";
      updateDisplays();
    };

    U.el("indicatorSelect").onchange = updateDisplays;
  }

  loadCSV();

})(window);
