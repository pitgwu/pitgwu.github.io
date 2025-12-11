// js/main.js
(function (global) {
  "use strict";

  const U          = global.Util;
  const Chart      = global.ChartManager;
  const Indicators = global.Indicators;
  const Signals    = global.SignalEngine;
  const Trend      = global.Trendlines;
  const WM         = global.PatternWM;
  const TRI        = global.PatternTriangle;

  const INITIAL_CASH = 5000000;
  const VISIBLE_BARS = 40;          // 視窗最多 40 根

  let data = [];
  // currentIndex = 目前「正在交易的 K 棒」索引（0-based）
  let currentIndex = 0;

  let cash         = INITIAL_CASH;
  let position     = 0;
  let lots         = [];            // [{ qty, price, date }]
  let trades       = [];            // [{ type, qty?, price?, date }]
  let realizedList = [];            // [{ qty, realized, date }]

  let indicators = null;            // 全部資料的指標
  let allSignals = null;            // 每日多空訊號陣列

  let signalVisible = false;        // 多空訊號開關，預設 OFF
  let maVisible     = false;        // 均線開關，預設 OFF

  // ---------------------------------------------------
  // 工具：計算「總未實現損益」
  // ---------------------------------------------------
  function calcUnrealTotal(currentPrice) {
    return lots.reduce((sum, lot) => {
      return sum + (currentPrice - lot.price) * lot.qty;
    }, 0);
  }

  // ---------------------------------------------------
  // CSV 載入
  // ---------------------------------------------------
  function loadCSV() {
    const stockList = [
      "2330","2317","6669","1475","2368","3665","2308","2345","6223","3653",
      "6274","6805","2449","2317","8210","2454","2059","3231","1303","3661",
      "6510","6139","6191","5536","3533","8358","4958","3515","2354","6515",
      "3715","3081","1560","3711","3211","5347","1319","3044","3217","5274",
      "3008","2327","2357","2439","2884","3037","3045","3583","8996","8299"
    ];

    const stock = stockList[Math.floor(Math.random() * stockList.length)];
    global.__currentStock = stock;   // 僅在結束時公佈

    fetch(`data/${stock}.csv`)
      .then(r => r.text())
      .then(text => {
        const lines = text.split("\n").slice(1);
        data = lines
          .filter(l => l.trim() !== "")
          .map(l => {
            const c = l.split(",");
            return {
              time:   c[0],      // YYYY-MM-DD
              open:  +c[1],
              high:  +c[2],
              low:   +c[3],
              close: +c[4],
              volume:+c[5],
            };
          });

        if (!data.length) {
          alert("資料為空");
          return;
        }

        // 初始資金顯示
        if (U.el("initialCash"))
          U.el("initialCash").innerText = INITIAL_CASH.toLocaleString();

        // 一開始「不顯示股票號碼」，只維持原本的文字或空白
        if (U.el("stockName")) {
          // 你可以改成空字串或「模擬進行中」
          U.el("stockName").innerText = ""; // 不透露股票代號
        }

        // 一次算好全資料指標 & 多空訊號
        indicators = Indicators.computeAll(data);
        const ctx  = Signals.buildSignalContext(data);
        allSignals = Signals.evaluateSignalsForAll(ctx);

        // ★ 初始「交易起點」：若有 2025-01-02 就停在那一天，否則用最後一根
        const TARGET_START_DATE = "2025-01-02";
        const idx20250102 = data.findIndex(d => d.time === TARGET_START_DATE);
        if (idx20250102 !== -1) {
          currentIndex = idx20250102;
        } else {
          currentIndex = data.length - 1;
        }

        Chart.init();
        bindEvents();
        updateDisplays();
      })
      .catch(e => {
        alert("讀取 CSV 失敗：" + e.message);
        console.error(e);
      });
  }

  // ---------------------------------------------------
  // 主畫面更新（含 40 根視窗）
  // ---------------------------------------------------
  function updateDisplays() {
    if (!data.length) return;

    const indType = U.el("indicatorSelect").value;

    // 視窗左界：最多只看 VISIBLE_BARS 根，以 currentIndex 收尾
    let leftIndex = 0;
    if (data.length > VISIBLE_BARS) {
      leftIndex = Math.max(0, currentIndex - VISIBLE_BARS + 1);
    }

    const shown = data.slice(leftIndex, currentIndex + 1);

    // -----------------------------
    // 型態偵測（W 底 / M 頭 / 三角）
    // -----------------------------
    const tline = Trend.findTrendlines(shown);
    const w     = WM.isWBottom(shown);
    const m     = WM.isMTop(shown);
    const tri   = TRI.detectTriangle(shown);

    const parts = [];
    if (w)   parts.push(`W底(頸線 ${w.neck.toFixed(2)})`);
    if (m)   parts.push(`M頭(頸線 ${m.neck.toFixed(2)})`);
    if (tri) parts.push(tri.type);

    U.el("kPattern").innerText =
      "即時型態偵測：" + (parts.length ? parts.join(" / ") : "尚無明顯型態");

    // -----------------------------
    // 多空訊號（依 currentIndex 對應日）
    // -----------------------------
    if (signalVisible) {
      const sigArr = allSignals[currentIndex] || [];
      const txt = sigArr
        .map(s => `[${s.side === "bull" ? "多" : "空"}] ${s.name}`)
        .join("、");
      U.el("signalBox").innerText =
        "多空訊號：" + (txt || "暫無明確訊號");
    } else {
      U.el("signalBox").innerText = "多空訊號：OFF";
    }

    // -----------------------------
    // 更新圖表（傳入 leftIndex 讓指標對齊）
    // -----------------------------
    Chart.update(shown, indicators, {
      baseIndex:     leftIndex,          // ★ 指標陣列偏移
      showMA:        maVisible,
      showBB:        indType === "bb",
      indicatorType: indType,
      trendlines:    maVisible ? tline : null,
      wPattern:      maVisible ? w : null,
      triangle:      maVisible ? tri : null
    });

    updateStats();
    updateTradeLog();
    updateHoldings();
  }

  // ---------------------------------------------------
  // 資產統計（含已實現 / 未實現）
  // ---------------------------------------------------
  function updateStats() {
    if (!data.length) return;

    const price        = data[currentIndex].close;
    const holdingValue = position * price;
    const total        = cash + holdingValue;
    const roi          = ((total / INITIAL_CASH - 1) * 100).toFixed(2);

    const unrealTotal = calcUnrealTotal(price);
    const realizedTotal = realizedList.reduce(
      (sum, r) => sum + (r.realized || 0),
      0
    );

    U.el("cash").innerText         = U.formatNumber(cash);
    U.el("position").innerText     = position;
    U.el("holdingValue").innerText = U.formatNumber(holdingValue);
    U.el("totalAsset").innerText   = U.formatNumber(total);
    U.el("roi").innerText          = roi;

    U.el("realizedTotalBox").innerText   = U.formatNumber(realizedTotal) + " 元";
    U.el("unrealizedTotalBox").innerText = U.formatNumber(unrealTotal) + " 元";
  }

  // ---------------------------------------------------
  // 交易紀錄
  // ---------------------------------------------------
  function updateTradeLog() {
    const ul = U.el("tradeLog");
    ul.innerHTML = "";

    trades.forEach(t => {
      const li = document.createElement("li");
      if (t.type === "buy") {
        li.textContent = `${t.date} 買 ${t.qty} @ ${t.price}`;
      } else if (t.type === "sell") {
        li.textContent = `${t.date} 賣 ${t.qty} @ ${t.price}`;
      } else {
        li.textContent = `${t.date} 不動作`;
      }
      ul.appendChild(li);
    });

    ul.scrollTop = ul.scrollHeight;
  }

  // ---------------------------------------------------
  // 持倉明細（分批 + 未實現）
  // ---------------------------------------------------
  function updateHoldings() {
    const ul = U.el("holdings");
    ul.innerHTML = "";

    if (!lots.length) {
      ul.innerHTML = "<li>無持倉</li>";
      return;
    }

    const price = data[currentIndex].close;

    lots.forEach(l => {
      const unreal = (price - l.price) * l.qty;
      const li = document.createElement("li");
      li.textContent =
        `${l.date} ${l.qty} 股 @ ${l.price} → 未實現 ${U.formatNumber(unreal)} 元`;
      ul.appendChild(li);
    });

    ul.scrollTop = ul.scrollHeight;
  }

  // ---------------------------------------------------
  // 共用：往下一根 K 棒（視窗右移）
  // ---------------------------------------------------
  function goNextBar() {
    if (!data.length) return;

    if (currentIndex < data.length - 1) {
      currentIndex++;
      updateDisplays();
    } else {
      checkGameEnd();
    }
  }

  // ---------------------------------------------------
  // 買進（使用當日收盤價，紀錄完再往右移一天）
  // ---------------------------------------------------
  function doBuy() {
    if (!data.length) return;

    const qty = parseInt(U.el("shareInput").value, 10);
    if (!qty || qty <= 0) return;

    const price = data[currentIndex].close;
    const cost  = qty * price;

    if (cost > cash) return alert("現金不足");

    cash     -= cost;
    position += qty;

    const dateStr = data[currentIndex].time;

    lots.push({ qty, price, date: dateStr });
    trades.push({ type: "buy", qty, price, date: dateStr });

    // ★ 先用當日價格紀錄，再往右移到明天
    goNextBar();
  }

  // ---------------------------------------------------
  // 賣出（FIFO，使用當日收盤價）
  // ---------------------------------------------------
  function doSell() {
    if (!data.length) return;

    const qty = parseInt(U.el("shareInput").value, 10);
    if (!qty || qty <= 0) return;
    if (qty > position)   return alert("持股不足");

    const price = data[currentIndex].close;
    const dateStr = data[currentIndex].time;

    let remain   = qty;
    let realized = 0;

    while (remain > 0 && lots.length) {
      const lot = lots[0];
      const use = Math.min(remain, lot.qty);

      realized += (price - lot.price) * use;

      lot.qty -= use;
      remain  -= use;

      if (lot.qty === 0) lots.shift();
    }

    cash     += qty * price;
    position -= qty;

    realizedList.push({
      qty,
      realized,
      date: dateStr
    });

    trades.push({
      type: "sell",
      qty,
      price,
      date: dateStr
    });

    goNextBar();
  }

  // ---------------------------------------------------
  // 不動作（只是紀錄並往右移一天）
  // ---------------------------------------------------
  function doHold() {
    if (!data.length) return;

    const dateStr = data[currentIndex].time;

    trades.push({
      type: "hold",
      date: dateStr
    });

    goNextBar();
  }

  // ---------------------------------------------------
  // 前一日 / 下一日（手動切換，只移動 K 線，不產生交易）
  // ---------------------------------------------------
  function nextDay() {
    if (!data.length) return;
    if (currentIndex < data.length - 1) {
      currentIndex++;
      updateDisplays();
    } else {
      checkGameEnd();
    }
  }

  function prevDay() {
    if (!data.length) return;
    if (currentIndex > 0) {
      currentIndex--;
      updateDisplays();
    }
  }

  // ---------------------------------------------------
  // 遊戲結束：專業總結 + 公佈股票號碼
  // ---------------------------------------------------
  function checkGameEnd() {
    if (!data.length) return;

    currentIndex = data.length - 1;
    updateDisplays();

    const finalPrice   = data[data.length - 1].close;
    const holdingValue = position * finalPrice;
    const totalValue   = cash + holdingValue;
    const roi          = ((totalValue / INITIAL_CASH - 1) * 100).toFixed(2);

    const realizedTotal = realizedList.reduce(
      (sum, r) => sum + (r.realized || 0),
      0
    );
    const unrealTotal = calcUnrealTotal(finalPrice);

    const stock = global.__currentStock;

    const good    = [];
    const bad     = [];
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
    if (U.el("stockName")) {
      U.el("stockName").innerText = `模擬結束，本次個股：${stock}`;
    }

    alert(`模擬結束（${stock}）\n報酬率：${roi}%`);
  }

  // ---------------------------------------------------
  // 綁定 UI
  // ---------------------------------------------------
  function bindEvents() {
    U.el("nextDay").onclick = nextDay;
    U.el("prevDay").onclick = prevDay;
    U.el("buy").onclick     = doBuy;
    U.el("sell").onclick    = doSell;
    U.el("hold").onclick    = doHold;

    // 多空訊號（預設 OFF）
    U.el("toggleSignal").onclick = () => {
      signalVisible = !signalVisible;
      U.el("toggleSignal").innerText =
        signalVisible ? "多空訊號：ON" : "多空訊號：OFF";
      updateDisplays();
    };

    // MA（預設 OFF）
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
