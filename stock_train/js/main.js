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
  let currentIndex = 0; // index = 當日交易日期所對應的 K 棒 index

  let cash = INITIAL_CASH;
  let position = 0;
  let lots = [];          // 分批買入
  let trades = [];        // 所有交易紀錄
  let realizedList = [];  // 已實現損益

  let indicators = null;
  let allSignals = null;

  let signalVisible = false;
  let maVisible = false;
  
  let tradeMode = "stock"; // "stock" | "future"

  const FUTURE_SPEC = {
    margin: 338000,
    pointValue: 200
  };

  // ----------------------------------------------------------
  // 1️⃣ 計算「總未實現損益」
  // ----------------------------------------------------------
  function calcUnrealTotal(currentPrice) {
    // 期貨
    if (tradeMode === "future") {
      return lots.reduce((sum, lot) => {
	    return sum + (currentPrice - lot.price) * FUTURE_SPEC.pointValue * lot.qty;
      }, 0);
	}

	// 股票
	return lots.reduce((sum, lot) => {
	  return sum + (currentPrice - lot.price) * lot.qty;
	}, 0);
  }

  // ----------------------------------------------------------
  // CSV 載入
  // ----------------------------------------------------------
  
  const STOCK_POOLS = {
	"ETF-00981A": {
	  folder: "data_981a",
	  stocks: [
        "2330","2317","6669","1475","2368","3665","2308","2345","6223","3653",
        "6274","6805","2449","2317","8210","2454","2059","3231","1303","3661",
        "6510","6139","6191","5536","3533","8358","4958","3515","2354","6515",
        "3715","3081","1560","3711","3211","5347","1319","3044","3217","5274",
        "3008","2327","2357","2439","2884","3037","3045","3583","8996","8299"
      ]
	},
    "大型權值股": {
	  folder: "data_big",
	  stocks: [
        "2330","2317","2454","2412","2881","2382","2303","2882","2891","3711"
      ]
	},
    "中小成長股": {
	  folder: "data_small",
	  stocks: [
        "6442","4749","4772","2374","2353","2409","3715","7749","6290","2377",
        "6415","2347","6409","3702"
      ]
	},
	"千金股": {
	  folder: "data_highprice",
	  stocks: [
        "5274","3661","2059","6669","3008","3529","5269","3653","3533","6781",
        "3131","2454","3443","6409","2330","2383","6515","6223","7734","3017",
		"6805"
      ]
	},
    "飇股": {
	  folder: "data_highest",
	  stocks: [
        "1519","2329","2344","2359","2408","3230","3231","3450","3661","3715",
		"4583","4722","4763","4946","5314","5475","6117","6139","6199","6235",
		"6442","6640","6739","6949","8021","8210","8358","8374","8937"
      ]
	},
    "今日台指期（5分K）": {
	  folder: "data_txf_5m_daily",
	  stocks: [
        "txf_5m_daily"
      ],
	  mode: "future"
	}
  };
    
  function initStockPoolSelect() {
    const sel = U.el("stockPoolSelect");
    if (!sel) {
      console.error("stockPoolSelect not found");
      return;
    }

    sel.innerHTML = "";

    Object.keys(STOCK_POOLS).forEach(name => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    });

    sel.selectedIndex = 0;
  }
  
  function loadCSV() {

    // 🔄 重置遊戲狀態（非常重要，給 restart 用）
    cash = INITIAL_CASH;
    position = 0;
    lots = [];
    trades = [];
    realizedList = [];
    signalVisible = false;
    maVisible = false;

    const poolName = U.el("stockPoolSelect").value;
    const pool = STOCK_POOLS[poolName];

    console.log("Loading pool:", poolName);

    if (!pool) {
      alert("找不到股票清單設定");
      return;
    }
	
	tradeMode = pool.mode || "stock";
    console.log("交易模式:", tradeMode);

    const statBox = U.el("assetStats");
    if (tradeMode === "future") {
      U.el("shareInput").step = 1;
      U.el("shareInput").value = 1;
	  if (!statBox.querySelector(".future-hint")) {
        statBox.insertAdjacentHTML(
          "afterbegin",
          `<div class="future-hint" style="color:#c00">
            台指期：1口保證金 338,000｜1點 = 200 元
           </div>`
        );
      }
    }

    const { folder, stocks } = pool;

    if (!stocks || !stocks.length) {
      alert("此清單沒有股票");
      return;
    }

    // 2️⃣ 隨機挑一檔股票
    const stock = stocks[Math.floor(Math.random() * stocks.length)];
    global.__currentStock = stock;

    // 3️⃣ 組出正確 CSV 路徑
    const csvPath = `${folder}/${stock}.csv`;

    console.log("📂 Load CSV:", csvPath);
    
    U.el("stockName").innerText = ""; // 一開始隱藏
	U.el("feedback").innerText = "";  // 一開始隱藏

    fetch(csvPath)
      .then(r => r.text())
      .then(text => {
        const lines = text.split("\n").slice(1);

		data = lines
		  .map(l => l.trim())
		  .filter(l => l)   // ✅ 先濾掉空行
		  .map(l => {
			const c = l.split(",");

			let timeValue;

			if (tradeMode === "future") {
			  // c[0] = "2024-03-15 09:00"
			  const [datePart, timePart] = c[0].split(" ");
			  const [y, m, d] = datePart.split("-").map(Number);
			  const [hh, mm] = timePart.split(":").map(Number);

			  // ✅ 關鍵：不要 -8
			  // 讓 chart(UTC顯示) 直接顯示 09:00
			  const utcMillis = Date.UTC(y, m - 1, d, hh, mm);
			  timeValue = Math.floor(utcMillis / 1000);
			} else {
			  if (!c[0]) return null;
			  timeValue = c[0];
			}

			return {
			  time: timeValue,
			  open: +c[1],
			  high: +c[2],
			  low: +c[3],
			  close: +c[4],
			  volume: +c[5]
			};
		  })
		  .filter(Boolean);   // ✅ 最後再清一次

        if (!data.length) return alert("CSV 空白");

        // ⭐ 起始交易日 = 2025-01-02
        //let startIdx = data.findIndex(d => d.time === "2025-01-02");
        //if (startIdx < 0) {
        //  alert("找不到 2025-01-02，請檢查 CSV");
        //  startIdx = 0;
        //}
		// ⭐ 起始交易日 = 第22根K棒
		let startIdx;

		if (tradeMode === "future") {
		  startIdx = Math.min(10, data.length - 1); // ✅ 從 09:50 左右開始
		} else {
		  startIdx = 22;
		}

        // ⭐ 交易日就是這一天
        currentIndex = startIdx;

        // MA / 指標相關資料
        indicators = Indicators.computeAll(data);
        allSignals = Signals.evaluateSignalsForAll(Signals.buildSignalContext(data));

        Chart.init();
        bindEvents();
        updateDisplays();
		//console.log(`✅ 已載入 ${poolName} → ${stock}`);
      })
      .catch(e => alert("CSV 載入失敗: " + e.message));
  }

  // ----------------------------------------------------------
  // 主畫面更新
  // ----------------------------------------------------------
  function updateDisplays() {
    const shown = data.slice(0, currentIndex + 1);

    // 型態偵測
    const tline = Trend.findTrendlines(shown);
    const w = WM.isWBottom(shown);
    const m = WM.isMTop(shown);
    const tri = TRI.detectTriangle(shown);

    if (signalVisible) {
      const sigArr = allSignals[currentIndex] || [];
      U.el("signalBox").innerText =
        sigArr.map(s => `[${s.side === "bull" ? "多" : "空"}] ${s.name}`).join("、") || "無";
    } else {
      U.el("signalBox").innerText = "多空訊號：OFF";
    }

    // 更新 K 線（含 40 根視窗）
    const sel = U.el("indicatorSelect").value;

    Chart.update(shown, indicators, {
      showMA: maVisible,
      showBB: sel === "bb",
      indicatorType: (sel === "bb") ? null : sel,
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
    const price = data[currentIndex].close;
    let holdingValue = 0;
	if (tradeMode === "stock") {
      holdingValue = position * price;
    }
    const unreal = calcUnrealTotal(price);
    const realized = realizedList.reduce((s, r) => s + r.realized, 0);
    const total = cash + unreal + holdingValue;
    const roi = (((total / INITIAL_CASH) - 1) * 100).toFixed(2);   

    U.el("cash").innerText = U.formatNumber(cash);
    U.el("position").innerText = position;
    U.el("holdingValue").innerText = tradeMode === "future" ? "—" : U.formatNumber(holdingValue);
    U.el("totalAsset").innerText = U.formatNumber(total);
    U.el("roi").innerText = roi;

    U.el("realizedTotalBox").innerText = U.formatNumber(realized) + " 元";
    U.el("unrealizedTotalBox").innerText = U.formatNumber(unreal) + " 元";
  }

  // ----------------------------------------------------------
  // 交易紀錄
  // ----------------------------------------------------------
  function updateTradeLog() {
    const ul = U.el("tradeLog");
    ul.innerHTML = "";

    trades.forEach(t => {
      ul.innerHTML += `<li>${t.date} ${
        t.type === "buy" ? "買" :
        t.type === "sell" ? "賣" : "不動作"
      } ${t.qty || ""} ${t.price ? "@ " + t.price : ""}</li>`;
    });

    ul.scrollTop = ul.scrollHeight;
  }

  // ----------------------------------------------------------
  // 持倉明細（分批）
  // ----------------------------------------------------------
  function updateHoldings() {
    const ul = U.el("holdings");
    ul.innerHTML = "";

    let unrealTotal = 0;

    if (!lots.length) {
      ul.innerHTML = "<li>無持倉</li>";
      U.el("unrealSummary").innerText = "";
      return;
    }

    const price = data[currentIndex].close;

    lots.forEach(l => {
      const u =
        tradeMode === "future"
          ? (price - l.price) * FUTURE_SPEC.pointValue * l.qty
          : (price - l.price) * l.qty;
      unrealTotal += u;
      ul.innerHTML += `<li>${l.date} ${l.qty} 股 @ ${l.price} → 未實現 ${U.formatNumber(u)} 元</li>`;
    });

    // ⭐ 關鍵補齊這一行
    U.el("unrealSummary").innerText =
      `未實現總損益：${U.formatNumber(unrealTotal)} 元`;
  }

  // ----------------------------------------------------------
  // 當天交易 → 隔天跳下一根 K
  // ----------------------------------------------------------
  function finishToday() {
    // 已經是最後一天 → 直接結束
    if (currentIndex >= data.length - 1) {
      gameEnd();
      return;
    }

    // 先推進一天
    currentIndex++;

    // 先更新畫面（讓最後一天K棒被畫出來）
    updateDisplays();

    // 如果推進後剛好到最後一天 → 立刻結束並顯示總結
    if (currentIndex >= data.length - 1) {
      // 用 setTimeout 讓 UI 先 render 完再顯示 alert/summary（避免閃或被擋）
      setTimeout(gameEnd, 0);
    }
  }

  function refreshTradeUI() {
    updateStats();
    updateTradeLog();
    updateHoldings();
  }

  function doBuy() {
    const qty = +U.el("shareInput").value;
    if (!qty || qty <= 0) return;

    const price = data[currentIndex].close;
    const cost = qty * price;
 
    if (tradeMode === "future") {
		const requiredMargin = qty * FUTURE_SPEC.margin;

        // 🔒 現金不足檢查
		if (requiredMargin > cash) {
		  alert("⚠️ 保證金不足，無法開倉");
		  return;
		}

		lots.push({ qty, price, date: data[currentIndex].time });

		// ⚠️ 期貨只佔用保證金
		cash -= requiredMargin;
		position += qty;

	} else {
	    // ===== 股票原邏輯 =====
		// 🔒 現金不足檢查
		const cost = qty * price;
		if (cost > cash) {
		  alert("⚠️ 現金不足");
		  return;
		}

		lots.push({ qty, price, date: data[currentIndex].time });
		cash -= cost;
		position += qty;
	} 
 
    trades.push({
      type: "buy",
      qty,
      price,
      date: data[currentIndex].time
    });

    refreshTradeUI();
    finishToday();
  }

  function doSell() {
    const qty = +U.el("shareInput").value;
    if (!qty || qty <= 0) return;

    if (position <= 0) {
      alert("⚠️ 目前無持股，無法賣出（只訓練多方思維）");
      return;
    }

    const price = data[currentIndex].close;
    let executedQty = 0;     // ⭐ 真正成交數量
    let realized = 0;

	if (tradeMode === "future") {
	  let sellQty = Math.min(qty, position);
	  if (sellQty <= 0) return;
	  
	  const originalQty = sellQty; // 用來回補保證金
	  
      while (sellQty > 0 && lots.length) {
        const lot = lots[0];
        const use = Math.min(lot.qty, sellQty);

        realized += (price - lot.price) * FUTURE_SPEC.pointValue * use;

        lot.qty -= use;
        sellQty -= use;
        if (lot.qty === 0) lots.shift();
      }

      cash += realized + (originalQty * FUTURE_SPEC.margin);
      position -= originalQty;
      executedQty = originalQty;

      realizedList.push({
        qty: executedQty,
        realized,
        date: data[currentIndex].time
      });
	  
    } else {
		
      // ===== 股票原邏輯 =====
      const sellQty = Math.min(qty, position);
      let remain = sellQty;

      while (remain > 0 && lots.length) {
        const lot = lots[0];
        const use = Math.min(lot.qty, remain);

        realized += (price - lot.price) * use;

        lot.qty -= use;
        remain -= use;
        if (lot.qty === 0) lots.shift();
      }

      cash += sellQty * price;
      position -= sellQty;
      executedQty = sellQty;

      realizedList.push({
        qty: executedQty,
        realized,
        date: data[currentIndex].time
      });
	}

    // ✅ 交易紀錄「只用 executedQty」
    trades.push({
      type: "sell",
      qty: executedQty,
      price,
      date: data[currentIndex].time
    });

    refreshTradeUI();
    finishToday();
  }

  function doHold() {
    trades.push({ type:"hold", date:data[currentIndex].time });
	refreshTradeUI();
    finishToday();
  }

  // ----------------------------------------------------------
  // 3️⃣ 遊戲結束：專業總結 + 公佈股票號碼
  // ----------------------------------------------------------
  function gameEnd() {
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

  // ----------------------------------------------------------
  // UI 綁定
  // ----------------------------------------------------------
  function bindEvents() {
	//loadCSV();
    U.el("loadGame").onclick = () => {
      loadCSV();
    };
  
    U.el("buy").onclick = doBuy;
    U.el("sell").onclick = doSell;
    U.el("hold").onclick = doHold;

    U.el("nextDay").onclick = () => {
      finishToday();
    };
    U.el("prevDay").onclick = () => {
      if (currentIndex > 0) currentIndex--;
      updateDisplays();
    };

    U.el("toggleMA").onclick = () => {
      maVisible = !maVisible;
      U.el("toggleMA").innerText = maVisible ? "均線：ON" : "均線：OFF";
      updateDisplays();
    };

    U.el("toggleSignal").onclick = () => {
      signalVisible = !signalVisible;
      U.el("toggleSignal").innerText =
        signalVisible ? "多空訊號：ON" : "多空訊號：OFF";

      // 只更新訊號顯示，不更新圖表
      const sigArr = allSignals[currentIndex] || [];
      U.el("signalBox").innerText = signalVisible
        ? (sigArr.map(s => `[${s.side === "bull" ? "多" : "空"}] ${s.name}`).join("、") || "無")
        : "多空訊號：OFF";
    };

    U.el("indicatorSelect").onchange = updateDisplays;
  }
  
  initStockPoolSelect();
  bindEvents();   // ✅ 一開始就綁定按鈕

})(window);
