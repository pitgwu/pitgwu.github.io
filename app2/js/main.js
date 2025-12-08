// js/main.js
(function (global) {
  "use strict";

  const U = global.Util;
  const Chart = global.ChartManager;
  const Signals = global.SignalEngine;
  const Indicators = global.Indicators;
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

  let signalVisible = false;
  let maVisible = false;

  // ---------------------------------------------------------
  // CSV 載入
  // ---------------------------------------------------------
  function loadCSV() {
    const stockList = [
      "2330","2317","6669","1475","2368","3665","2308","2345","6223","3653",
      "6274","6805","2449","2317","8210","2454","2059","3231","1303","3661",
      "6510","6139","6191","5536","3533","8358","4958","3515","2354","6515",
      "3715","3081","1560","3711","3211","5347","1319","3044","3217","5274",
      "3008","2327","2357","2439","2884","3037","3045","3583","8996","8299"
    ];
    const stock = list[Math.floor(Math.random() * list.length)];
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

  // ---------------------------------------------------------
  // 主 UI 更新
  // ---------------------------------------------------------
  function updateDisplays() {
    const shown = data.slice(0, currentIndex);
    const indType = U.el("indicatorSelect").value;

    // 型態偵測
    const tline = Trend.findTrendlines(shown);
    const w = WM.isWBottom(shown);
    const m = WM.isMTop(shown);
    const tri = TRI.detectTriangle(shown);

    let pat = "";
    if (w) pat += `W底(${w.neck.toFixed(2)}) `;
    if (m) pat += `M頭(${m.neck.toFixed(2)}) `;
    if (tri) pat += `${tri.type} `;

    U.el("kPattern").innerText = pat || "（無明顯型態）";

    // 多空訊號
    if (signalVisible) {
      const sig = allSignals[currentIndex - 1] || [];
      const txt = sig.map(s => `[${s.side === "bull" ? "多" : "空"}] ${s.name}`).join("、");
      U.el("signalBox").innerText = "多空訊號：" + (txt || "無");
    } else {
      U.el("signalBox").innerText = "多空訊號：OFF";
    }

    // 圖表更新
    Chart.update(shown, indicators, {
      showMA: maVisible,
      showBB: indType === "bb",
      indicatorType: indType,
      trendlines: tline,
      wPattern: w,
      triangle: tri
    });

    updateStats();
    updateTradeLog();
    updateHoldings();
  }

  // ---------------------------------------------------------
  // 資產統計（含已實現總損益）
  // ---------------------------------------------------------
  function updateStats() {
    const price = data[currentIndex - 1].close;
    const holdingValue = position * price;

    const realizedTotal = realizedList.reduce(
      (sum, r) => sum + (r.realized || 0),
      0
    );

    const total = cash + holdingValue;
    const roi = ((total / INITIAL_CASH - 1) * 100).toFixed(2);

    U.el("cash").innerText = U.formatNumber(cash);
    U.el("position").innerText = position;
    U.el("holdingValue").innerText = U.formatNumber(holdingValue);
    U.el("totalAsset").innerText = U.formatNumber(total);
    U.el("roi").innerText = roi;
    U.el("realizedTotalBox").innerText = U.formatNumber(realizedTotal) + " 元";
  }

  // ---------------------------------------------------------
  // 交易紀錄
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

    ul.scrollTop = ul.scrollHeight;
  }

  // ---------------------------------------------------------
  // 持倉（未實現）
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
  // 賣出（FIFO）
  // ---------------------------------------------------------
  function doSell() {
    const qty = parseInt(U.el("shareInput").value, 10);
    if (!qty) return;
    if (qty > position) return alert("持股不足");

    const price = data[currentIndex - 1].close;
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
  // 不動作
  // ---------------------------------------------------------
  function doHold() {
    trades.push({
      type: "hold",
      date: data[currentIndex - 1].time
    });
    nextDay();
  }

  // ---------------------------------------------------------
  // 時間軸控制
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

  // --------------------------------------------------------------
  // 遊戲結束專業總結
  // --------------------------------------------------------------
  function checkGameEnd() {
    if (currentIndex < data.length) return;

    const finalPrice = data[data.length - 1].close;
    const totalValue = cash + position * finalPrice;
    const roi = ((totalValue / INITIAL_CASH - 1) * 100).toFixed(2);

    const realizedTotal = realizedList.reduce(
      (s, r) => s + (r.realized || 0),
      0
    );

    const tradeCount = trades.filter(t => t.type !== "hold").length;

    const good = [];
    const bad = [];
    const suggest = [];

    if (roi > 8)
      good.push("整體策略具備正期望值，報酬表現優於同期間大盤");
    else if (roi >= 0)
      good.push("風險控管尚可，資金未出現明顯虧損");
    else
      bad.push("策略在波動行情中失靈，需檢討進出場基準與風險控管");

    if (realizedTotal > 0)
      good.push("已實現損益為正，進出場節奏整體健康");
    else
      bad.push("停損不夠果斷，虧損單拖累整體報酬");

    if (tradeCount > 20)
      bad.push("交易頻率過高，可能出現情緒化或過度反應");
    if (tradeCount < 4)
      bad.push("進場機會偏少，對於行情敏感度不足");

    if (lots.length > 0)
      bad.push("存在『不願停損而抱單』的傾向，需檢討持倉規劃");

    if (realizedTotal < 0)
      suggest.push("加強停損機制（固定% 或波動度停損），避免單筆虧損拉低整體績效");
    if (tradeCount > 18)
      suggest.push("降低交易次數，提升每次交易的勝率與理由，而非情緒性介入");
    if (lots.length > 0)
      suggest.push("避免『凹單』，可採固定減碼或分批出場策略");

    if (suggest.length === 0)
      suggest.push("維持現有策略架構，持續優化買進與獲利了結規則");

    const summary =
      `【遊戲結束】\n` +
      `本次操作個股：${selectedStock}\n\n` +
      `最終總資產：${U.formatNumber(totalValue)} 元\n` +
      `報酬率：${roi}%\n` +
      `已實現損益：${U.formatNumber(realizedTotal)} 元\n\n` +
      `【策略優點】\n${good.join("；") || "無明顯優勢"}\n\n` +
      `【策略缺點】\n${bad.join("；") || "無重大缺失"}\n\n` +
      `【專業改善建議】\n${suggest.join("；")}`;

    U.el("feedback").innerText = summary;

    alert(`遊戲結束（${selectedStock}）\n報酬率：${roi}%`);
  }

  // ---------------------------------------------------------
  // 綁定事件
  // ---------------------------------------------------------
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
