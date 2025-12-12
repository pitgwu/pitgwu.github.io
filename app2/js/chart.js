// js/chart.js
(function (global) {
  "use strict";

  const U = global.Util;

  let chart, candle;
  let volChart, volSeries;
  let indChart, indL1, indL2, indHist;

  let ma5, ma10, ma20;
  let bbU, bbM, bbL;

  let resLine, supLine;
  let trendUp, trendDn;
  let triUp, triLow;
  let wLine1, wLine2, wNeck;

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
    // ===== 主圖 =====
    chart = fixedChart(document.getElementById("chart"), 420);

    candle = chart.addCandlestickSeries({
      upColor: "#ff0000",
      downColor: "#00aa00",
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

    // ===== 指標區 =====
    indChart = fixedChart(document.getElementById("indicator"), 150);
    indChart.timeScale().applyOptions({ visible: false });

    // ❗ MACD 專用固定 scale
    const macdScale = () => ({
      priceRange: { minValue: -5, maxValue: 5 }
    });

    indL1 = indChart.addLineSeries({ lineWidth: 2 });
    indL2 = indChart.addLineSeries({ lineWidth: 2 });
    indHist = indChart.addHistogramSeries();

    // 預設不鎖 scale（給 KD / RSI 用）
    indL1.applyOptions({ autoscaleInfoProvider: null });
    indL2.applyOptions({ autoscaleInfoProvider: null });
    indHist.applyOptions({ autoscaleInfoProvider: null });

    // 存給 update 用
    indChart.__macdScale = macdScale;
  }

  function update(shown, indicators, opt) {
    if (!shown || !shown.length) return;

    const visibleBars = opt.visibleBars || 40;

    // ===== K 線 / 成交量 =====
    candle.setData(shown);
    volSeries.setData(shown.map(c => ({ time: c.time, value: c.volume })));

    // ===== 均線 =====
    if (opt.showMA) {
      const closes = shown.map(c => c.close);
      ma5.setData(U.sma(closes,5).map((v,i)=>v?{time:shown[i].time,value:v}:null).filter(Boolean));
      ma10.setData(U.sma(closes,10).map((v,i)=>v?{time:shown[i].time,value:v}:null).filter(Boolean));
      ma20.setData(U.sma(closes,20).map((v,i)=>v?{time:shown[i].time,value:v}:null).filter(Boolean));
    } else {
      ma5.setData([]); ma10.setData([]); ma20.setData([]);
    }

    // ===== 布林通道（比例正常，不動）=====
    if (opt.showBB) {
      bbU.setData(shown.map((c,i)=>({time:c.time,value:indicators.BB.upper[i]})));
      bbM.setData(shown.map((c,i)=>({time:c.time,value:indicators.BB.mid[i]})));
      bbL.setData(shown.map((c,i)=>({time:c.time,value:indicators.BB.lower[i]})));
    } else {
      bbU.setData([]); bbM.setData([]); bbL.setData([]);
    }

    // ===== 指標清空 =====
    indL1.setData([]); indL2.setData([]); indHist.setData([]);

    // 🔑 根據指標切換 scale
    if (opt.indicatorType === "macd") {
      indL1.applyOptions({ autoscaleInfoProvider: indChart.__macdScale });
      indL2.applyOptions({ autoscaleInfoProvider: indChart.__macdScale });
      indHist.applyOptions({ autoscaleInfoProvider: indChart.__macdScale });
    } else {
      indL1.applyOptions({ autoscaleInfoProvider: null });
      indL2.applyOptions({ autoscaleInfoProvider: null });
      indHist.applyOptions({ autoscaleInfoProvider: null });
    }

    // ===== KD / RSI / MACD =====
    if (opt.indicatorType === "kd") {
      indL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.K[i]})));
      indL2.setData(shown.map((c,i)=>({time:c.time,value:indicators.D[i]})));
    }
    else if (opt.indicatorType === "rsi") {
      indL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.RSI[i]})));
    }
    else if (opt.indicatorType === "macd") {
      indL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.MACD[i]})));
      indL2.setData(shown.map((c,i)=>({time:c.time,value:indicators.MACDSignal[i]})));
      indHist.setData(shown.map((c,i)=>({
        time: c.time,
        value: indicators.MACDHist[i],
        color: indicators.MACDHist[i] >= 0 ? "#26a69a" : "#ff6b6b"
      })));
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
    const to   = shown[shown.length - 1].time;

    chart.timeScale().setVisibleRange({ from, to });
    volChart.timeScale().setVisibleRange({ from, to });
    indChart.timeScale().setVisibleRange({ from, to });
  }

  global.ChartManager = { init, update };
})(window);
