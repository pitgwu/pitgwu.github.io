// js/main.js
// ==============================================================
// 主控制：資料載入 / 按鈕事件 / 資產狀態 / 多空訊號 / 遊戲結束
// ==============================================================

(function (global) {
  "use strict";

  const U = global.Util;
  const Chart = global.ChartManager;
  const Signals = global.SignalEngine;
  const Indicators = global.Indicators;
  const Trend = global.Trendlines;
  const WM = global.PatternWM;
  const TRI = global.PatternTriangle;
  const KPattern = global.KPattern;

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
  let selectedStock = "";

  let maVisible = false;
  let signalVisible = false;

  // --------------------------------------------------------------
  // 載入 CSV
  // --------------------------------------------------------------
  function loadCSV() {
    const stockList = [
      "2330","2317","6669","1475","2368","3665","2308","2345","6223","3653",
      "6274","6805","2449","2317","8210","2454","2059","3231","1303","3661",
      "6510","6139","6191","5536","3533","8358","4958","3515","2354","6515",
      "3715","3081","1560","3711","3211","5347","1319","3044","3217","5274",
      "3008","2327","2357","2439","2884","3037","3045","3583","8996","8299"
    ];
    selectedStock = stockList[Math.floor(Math.random() * stockList.length)];

    U.el("initialCash").innerText = U.formatNumber(INITIAL_CASH);
    U.el("cash").innerText = U.formatNumber(INITIAL_CASH);

    fetch(`data/${selectedStock}.csv`)
      .then((r) => r.text())
      .then((text) => {
        const lines = text.split("\n").slice(1);
        data = lines
          .filter((l) => l.trim() !== "")
          .map((l) => {
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

        const ctx = Signals.buildSignalContext(data, indicators);
        allSignals = Signals.evaluateSignalsForAll(ctx);

        Chart.init();
        bindEvents();
        updateDisplays();
      })
      .catch((e) => alert("讀取 CSV 失敗：" + e));
  }

  // --------------------------------------------------------------
  // 主畫面更新
  // --------------------------------------------------------------
  function updateDisplays() {
    const shown = data.slice(0, currentIndex);
    const indicatorType = U.el("indicatorSelect").value;

    const tline = Trend.findTrendlines(shown);
    const w = WM.isWBottom(shown);
    const m = WM.isMTop(shown);
    const tri = TRI.detectTriangle(shown);

    let pat = KPattern.detect(shown);
    if (w) pat += `｜W底(${w.neck.toFixed(2)})`;
    if (m) pat += `｜M頭(${m.neck.toFixed(2)})`;
    if (tri) pat += `｜${tri.type}`;
    U.el("kPattern").innerText = "即時型態偵測：" + pat;

    if (signalVisible) {
      const sigArr = allSignals[currentIndex - 1] || [];
      const txt = sigArr
        .map((s) => `[${s.side === "bull" ? "多" : "空"}] ${s.name}`)
        .join("、");
      U.el("signalBox").innerText = "多空訊號：" + (txt || "無");
    } else {
      U.el("signalBox").innerText = "多空訊號：OFF";
    }

    Chart.update(shown, indicators, {
      showMA: maVisible,
      showBB: indicatorType === "bb",
      indicatorType,
      trendlines: maVisible ? tline : { upLines: [], downLines: [] },
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

    // ★ 正確加入已實現總損益
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

    // ★ 新增：右側固定欄位（已實現總損益）
    U.el("realizedTotalBox").innerText =
      U.formatNumber(realizedTotal) + " 元";
  }

  // --------------------------------------------------------------
  // 交易紀錄
  // --------------------------------------------------------------
  function updateTradeLog() {
    const ul = U.el("tradeLog");
    ul.innerHTML = "";

    trades.forEach((t) => {
      const li = document.createElement("li");
      if (t.type === "buy") {
        li.textContent = `${t.date} 買 ${t.qty} @ ${t.price}`;
      } else if (t.type === "sell") {
        li.textContent = `${t.date} 賣 ${t.qty} @ ${t.price} → 已實現：${U.formatNumber(
          t.realized
        )}`;
      } else {
        li.textContent = `${t.date} 不動作`;
      }
      ul.appendChild(li);
    });

    ul.scrollTop = ul.scrollHeight;
  }

  // --------------------------------------------------------------
  // 持倉明細 + 損益
  // --------------------------------------------------------------
  function updateHoldings() {
    const ul = U.el("holdings");
    ul.innerHTML = "";

    if (!lots.length) {
      ul.innerHTML = "<li>無持倉</li>";
      U.el("unrealSummary").innerText = "未實現損益：0 元";
      U.el("realizedTotalBox").innerText =
        U.formatNumber(realizedTotal) + " 元";
      return;
    }

    const price = data[currentIndex - 1].close;
    let unrealSum = 0;

    lots.forEach((l) => {
      const unreal = (price - l.price) * l.qty;
      unrealSum += unreal;

      const li = document.createElement("li");
      li.textContent = `${l.date} ${l.qty} 股 @ ${l.price} → 未實現：${U.formatNumber(
        unreal
      )}`;
      ul.appendChild(li);
    });

    ul.scrollTop = ul.scrollHeight;

    U.el("unrealSummary").innerText =
      "未實現損益：" + U.formatNumber(unrealSum) + " 元";
  }

  // --------------------------------------------------------------
  // 下單操作
  // --------------------------------------------------------------
  function doBuy() {
    const qty = parseInt(U.el("shareInput").value, 10);
    const price = data[currentIndex - 1].close;

    if (qty * price > cash) return alert("現金不足");

    cash -= qty * price;
    position += qty;
    lots.push({ qty, price, date: data[currentIndex - 1].time });

    trades.push({
      type: "buy",
      qty,
      price,
      date: data[currentIndex - 1].time,
    });

    nextDay();
  }

  function doSell() {
    const qty = parseInt(U.el("shareInput").value, 10);
    if (qty > position) return alert("持股不足");

    const price = data[currentIndex - 1].close;
    const date = data[currentIndex - 1].time;
    cash += qty * price;
    position -= qty;

    let remain = qty;
    let realizedTotal = 0;

    while (remain > 0 && lots.length) {
      const lot = lots[0];
      if (lot.qty > remain) {
        const realized = (price - lot.price) * remain;
        realizedTotal += realized;
        lot.qty -= remain;
        remain = 0;
      } else {
        const realized = (price - lot.price) * lot.qty;
        realizedTotal += realized;
        remain -= lot.qty;
        lots.shift();
      }
    }

    realizedList.push({ date, qty, realized: realizedTotal });

    trades.push({
      type: "sell",
      qty,
      price,
      realized: realizedTotal,
      date,
    });

    nextDay();
  }

  function doHold() {
    trades.push({ type: "hold", date: data[currentIndex - 1].time });
    nextDay();
  }

  // --------------------------------------------------------------
  // 前/後 移動
  // --------------------------------------------------------------
  function nextDay() {
    if (currentIndex < data.length) {
      currentIndex++;
      updateDisplays();
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

  // --------------------------------------------------------------
  // 事件綁定
  // --------------------------------------------------------------
  function bindEvents() {
    U.el("nextDay").onclick = nextDay;
    U.el("prevDay").onclick = prevDay;
    U.el("buy").onclick = doBuy;
    U.el("sell").onclick = doSell;
    U.el("hold").onclick = doHold;

    U.el("toggleSignal").onclick = () => {
      signalVisible = !signalVisible;
      U.el("toggleSignal").innerText = signalVisible
        ? "多空訊號：ON"
        : "多空訊號：OFF";
      updateDisplays();
    };

    U.el("toggleMA").onclick = () => {
      maVisible = !maVisible;
      U.el("toggleMA").innerText = maVisible ? "均線：ON" : "均線：OFF";
      U.el("maLegend").style.display = maVisible ? "block" : "none";
      updateDisplays();
    };

    U.el("indicatorSelect").onchange = updateDisplays;
  }

  loadCSV();

})(window);
