// js/chart.js
(function (global) {
  "use strict";

  const U = global.Util;

  let chart, candle;
  let volChart, volSeries;
  let indChart, indL1, indL2, indHist;

  let ma5, ma10, ma20;
  let bbU, bbM, bbL;

  // ✅ 這些是你目前 update() 內「有用到」但原本沒宣告/沒初始化的 series
  let resLine, supLine;         // 支撐壓力
  let trendUp, trendDn;         // 趨勢線
  let triUp, triLow;            // 三角收斂
  let wLine1, wLine2, wNeck;    // W 底

  function fixedChart(el, height) {
    return LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height,
      layout: { background: { color: "#fff" }, textColor: "#222" },
      rightPriceScale: { autoScale: true },
      timeScale: {
        timeVisible: true,
        barSpacing: 8,
        rightBarStaysOnScroll: true,
        scrollEnabled: false,
        zoomEnabled: false,
      },
      handleScroll: false,
      handleScale: false,
    });
  }

  function init() {
    chart = fixedChart(document.getElementById("chart"), 420);

    candle = chart.addCandlestickSeries({
      upColor: "#ff0000",        // 上漲紅
      downColor: "#00aa00",      // 下跌綠
      borderUpColor: "#ff0000",
      borderDownColor: "#00aa00",
      wickUpColor: "#ff0000",
      wickDownColor: "#00aa00",
    });

    ma5  = chart.addLineSeries({ color: "#f00", lineWidth: 1 });
    ma10 = chart.addLineSeries({ color: "#0a0", lineWidth: 1 });
    ma20 = chart.addLineSeries({ color: "#00f", lineWidth: 1 });

    bbU = chart.addLineSeries({ color: "#ffa500" });
    bbM = chart.addLineSeries({ color: "#0066cc" });
    bbL = chart.addLineSeries({ color: "#008800" });

    // ✅ 補上：支撐/壓力、趨勢線、三角、W底（避免 resLine / trendUp / triUp / wLine1 未定義）
    resLine = chart.addLineSeries({ color: "#dd4444", lineWidth: 1 });
    supLine = chart.addLineSeries({ color: "#44aa44", lineWidth: 1 });

    trendUp = chart.addLineSeries({ color: "#00aa88", lineWidth: 2 });
    trendDn = chart.addLineSeries({ color: "#aa0044", lineWidth: 2 });

    triUp  = chart.addLineSeries({ color: "#aa6600", lineWidth: 1 });
    triLow = chart.addLineSeries({ color: "#5588ff", lineWidth: 1 });

    wLine1 = chart.addLineSeries({ color: "#cc00cc", lineWidth: 1 });
    wLine2 = chart.addLineSeries({ color: "#cc00cc", lineWidth: 1 });
    wNeck  = chart.addLineSeries({ color: "#cc00cc", lineWidth: 1 });

    // ===== 成交量 =====
    volChart = fixedChart(document.getElementById("volume"), 100);
    volChart.timeScale().applyOptions({ visible: false });
    volSeries = volChart.addHistogramSeries({
      priceFormat: { type: "volume" }
    });

    // ===== 技術指標（關鍵：固定比例避免 ON/OFF 跳動）=====
    indChart = fixedChart(document.getElementById("indicator"), 150);
    indChart.timeScale().applyOptions({ visible: false });

    // 🔒 固定 MACD / 指標比例：保證 macd ON/OFF 尺度不跳
    const fixedScale = () => ({
      priceRange: {
        minValue: -5,
        maxValue: 5
      }
    });

    indL1 = indChart.addLineSeries({
      lineWidth: 2,
      autoscaleInfoProvider: fixedScale
    });

    indL2 = indChart.addLineSeries({
      lineWidth: 2,
      autoscaleInfoProvider: fixedScale
    });

    indHist = indChart.addHistogramSeries({
      autoscaleInfoProvider: fixedScale
    });
  }

  function update(shown, indicators, opt) {
    if (!shown || !shown.length) return;

    const visibleBars = opt.visibleBars || 40;

    // 1️⃣ K 線 / 成交量：只畫已發生資料
    candle.setData(shown);
    volSeries.setData(shown.map(c => ({ time: c.time, value: c.volume })));

    // 2️⃣ 均線（與 shown 對齊）
    if (opt.showMA) {
      const closes = shown.map(c => c.close);

      const s5  = U.sma(closes, 5);
      const s10 = U.sma(closes, 10);
      const s20 = U.sma(closes, 20);

      ma5.setData(
        s5.map((v, i) => (v != null ? { time: shown[i].time, value: v } : null)).filter(Boolean)
      );
      ma10.setData(
        s10.map((v, i) => (v != null ? { time: shown[i].time, value: v } : null)).filter(Boolean)
      );
      ma20.setData(
        s20.map((v, i) => (v != null ? { time: shown[i].time, value: v } : null)).filter(Boolean)
      );
    } else {
      ma5.setData([]); ma10.setData([]); ma20.setData([]);
    }

    // 3️⃣ 布林通道
    if (opt.showBB) {
      // ⚠️ indicators.BB.* 如果是「全資料長度」的陣列，且 shown 是 slice(0..currentIndex)
      // 這裡 i 對得上；若 shown 不是從 0 開始 slice，需 main.js 先對齊 index
      bbU.setData(shown.map((c, i) => ({ time: c.time, value: indicators.BB.upper[i] })));
      bbM.setData(shown.map((c, i) => ({ time: c.time, value: indicators.BB.mid[i] })));
      bbL.setData(shown.map((c, i) => ({ time: c.time, value: indicators.BB.lower[i] })));
    } else {
      bbU.setData([]); bbM.setData([]); bbL.setData([]);
    }

    // 4️⃣ 技術指標（KD / RSI / MACD，比例不再跳）
    indL1.setData([]); indL2.setData([]); indHist.setData([]);

    if (opt.indicatorType === "kd") {
      indL1.setData(shown.map((c, i) => ({ time: c.time, value: indicators.K[i] })));
      indL2.setData(shown.map((c, i) => ({ time: c.time, value: indicators.D[i] })));
    } else if (opt.indicatorType === "rsi") {
      indL1.setData(shown.map((c, i) => ({ time: c.time, value: indicators.RSI[i] })));
    } else if (opt.indicatorType === "macd") {
      indL1.setData(shown.map((c, i) => ({ time: c.time, value: indicators.MACD[i] })));
      indL2.setData(shown.map((c, i) => ({ time: c.time, value: indicators.MACDSignal[i] })));
      indHist.setData(
        shown.map((c, i) => ({
          time: c.time,
          value: indicators.MACDHist[i],
          color: indicators.MACDHist[i] >= 0 ? "#26a69a" : "#ff6b6b"
        }))
      );
    }

    // 5️⃣ 支撐壓力（如果你的 supportResistance.js 有載入）
    //    沒有就不畫，避免再噴錯
    if (global.SupportResistance && typeof global.SupportResistance.findLines === "function") {
      const SR = global.SupportResistance.findLines(shown, 20);
      const lastT = shown[shown.length - 1].time;
      resLine.setData(SR[0] ? [{ time: lastT, value: SR[0].price }] : []);
      supLine.setData(SR[1] ? [{ time: lastT, value: SR[1].price }] : []);
    } else {
      resLine.setData([]);
      supLine.setData([]);
    }

    // 6️⃣ 趨勢線 / 三角 / W 底：當 opt.showMA 關掉就清掉（避免殘影）
    trendUp.setData([]);
    trendDn.setData([]);
    triUp.setData([]);
    triLow.setData([]);
    wLine1.setData([]);
    wLine2.setData([]);
    wNeck.setData([]);

    if (opt.showMA && opt.trendlines) {
      const { upLines, downLines } = opt.trendlines;

      if (upLines?.length) {
        const u = upLines[upLines.length - 1];
        if (shown[u.p1.index] && shown[u.p2.index]) {
          trendUp.setData([
            { time: shown[u.p1.index].time, value: u.p1.price },
            { time: shown[u.p2.index].time, value: u.p2.price },
          ]);
        }
      }

      if (downLines?.length) {
        const d = downLines[downLines.length - 1];
        if (shown[d.p1.index] && shown[d.p2.index]) {
          trendDn.setData([
            { time: shown[d.p1.index].time, value: d.p1.price },
            { time: shown[d.p2.index].time, value: d.p2.price },
          ]);
        }
      }
    }

    if (opt.showMA && opt.triangle) {
      const T = opt.triangle;
      if (shown[T.upperLine.p1.index] && shown[T.upperLine.p2.index]) {
        triUp.setData([
          { time: shown[T.upperLine.p1.index].time, value: T.upperLine.p1.price },
          { time: shown[T.upperLine.p2.index].time, value: T.upperLine.p2.price },
        ]);
      }
      if (shown[T.lowerLine.p1.index] && shown[T.lowerLine.p2.index]) {
        triLow.setData([
          { time: shown[T.lowerLine.p1.index].time, value: T.lowerLine.p1.price },
          { time: shown[T.lowerLine.p2.index].time, value: T.lowerLine.p2.price },
        ]);
      }
    }

    if (opt.showMA && opt.wPattern) {
      const W = opt.wPattern;

      if (shown[W.p1.index] && shown[W.p2.index]) {
        wLine1.setData([
          { time: shown[W.p1.index].time, value: W.p1.price },
          { time: shown[W.p2.index].time, value: W.p2.price },
        ]);
      }

      if (shown[W.p3.index] && shown[W.p4.index]) {
        wLine2.setData([
          { time: shown[W.p3.index].time, value: W.p3.price },
          { time: shown[W.p4.index].time, value: W.p4.price },
        ]);
      }

      const lastT2 = shown[shown.length - 1].time;
      if (shown[W.p1.index]) {
        wNeck.setData([
          { time: shown[W.p1.index].time, value: W.neck },
          { time: lastT2, value: W.neck },
        ]);
      }
    }

    // 7️⃣ 固定視窗 40 根，右對齊當日 K 棒（不會影響你 main.js 的起始日邏輯）
    const start = Math.max(0, shown.length - visibleBars);
    const from = shown[start].time;
    const to = shown[shown.length - 1].time;

    chart.timeScale().setVisibleRange({ from, to });
    volChart.timeScale().setVisibleRange({ from, to });
    indChart.timeScale().setVisibleRange({ from, to });
  }

  global.ChartManager = { init, update };
})(window);
